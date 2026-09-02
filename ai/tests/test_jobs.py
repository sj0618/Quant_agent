from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import sha256

import pytest

from ai_graph.graph import DEBUG_STORE
from ai_graph.job_repository_postgres import _job_document
from ai_graph.job_store_persistent import PersistentAnalysisJobStore
from ai_graph.jobs import (
    AnalysisJob,
    AnalysisJobStatus,
    InMemoryAnalysisJobStore,
    JobStoreConfigurationError,
    classify_failure,
    create_analysis_job_store_from_env,
)
from ai_graph.nodes.strategy_research import StrategyResearchError
from ai_graph.research_eligibility import PerformanceAvailable, PerformanceMethodManifest
from ai_graph.schemas import (
    APIEnvelope,
    BacktestEquityPoint,
    BacktestMetrics,
    BacktestPerformance,
    EnvelopeStatus,
    InternalPayload,
    Stage,
    UserPayload,
)


def _ready_envelope(trace_id: str) -> APIEnvelope:
    return APIEnvelope(
        status=EnvelopeStatus.READY,
        trace_id=trace_id,
        user_payload=UserPayload(
            headline="ready",
            message="analysis completed",
            next_actions=[],
        ),
        strategy_spec=None,
        debug_ref=f"debug:{trace_id}",
        retryable=False,
    )


def test_strategy_research_failure_keeps_its_typed_subcause() -> None:
    diagnostic = classify_failure(
        StrategyResearchError(
            "strategy research provider is temporarily unavailable",
            cause_code="research_provider_failure",
        ),
        stage="interpreting",
    )

    assert diagnostic.category == "infrastructure_failure"
    assert diagnostic.subcause == "strategy_research_provider_failure"
    assert diagnostic.failure_stage == "interpreting"


def _completed_backtest_envelope(trace_id: str) -> APIEnvelope:
    envelope = _ready_envelope(trace_id)
    internal_performance = BacktestPerformance.model_construct(
        selected_candidate_id="candidate-1",
        metrics=BacktestMetrics(
            sharpe_ratio=0.5,
            max_drawdown=-0.1,
            win_rate=0.5,
            total_return=0.01,
            in_sample_sharpe=0.5,
            out_sample_sharpe=None,
            degradation=0.0,
        ),
        engine_summary={
            "execution_audit": {
                "has_real_fills": True,
                "recent_events": [
                    {"date": "2026-01-02", "ticker": "005930", "side": "buy", "status": "submitted", "reason": "entry_signal", "requested_quantity": 10, "filled_quantity": 0, "cost_policy_id": "kr-equity-v1"},
                    {"date": "2026-01-03", "ticker": "005930", "side": "buy", "status": "executed", "reason": "next_open_fill", "requested_quantity": 10, "filled_quantity": 8, "price": 70000.0, "commission_cost": 12.0, "tax_cost": 0.0, "slippage_cost": 5.0, "cost_policy_id": "kr-equity-v1"},
                ],
            },
            "ai_backtest_context": {"max_position_pct": 0.1, "applied_max_positions": 10},
            "benchmark_provenance": {"source": "krx-universe-return"},
        },
        equity_curve=[BacktestEquityPoint(date="2026-01-03", cumulative_return=0.01)],
        reliability=None,
        benchmark=None,
    )
    audit = internal_performance.engine_summary["execution_audit"]["recent_events"]
    ledger = {
        "signals": [audit[0]], "order_audit": audit, "fills": [audit[1]],
        "positions": [{"date": "2026-01-03", "ticker": "005930", "quantity": 8, "fill_quantity": 8, "side": "buy", "reason": "next_open_fill"}],
        "trades": [{"exit_date": "2026-01-03", "ticker": "005930", "quantity": 8, "reason": "closed"}],
        "equity": [{"date": "2026-01-03", "cash": 440000.0, "positions_value": 560000.0, "total_equity": 1000000.0, "daily_return": 0.01}],
    }
    ledger["source_event_count"] = sum(len(value) for value in ledger.values() if isinstance(value, list))
    ledger["source_event_hash"] = sha256(
        json.dumps(
            {
                key: ledger[key]
                for key in ("signals", "order_audit", "fills", "positions", "trades", "equity")
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    internal_performance.engine_summary["_storage_execution_ledger"] = ledger
    DEBUG_STORE.put(
        envelope.debug_ref,
        InternalPayload(
            trace_id=trace_id,
            backtest_artifacts={"engine_summary": internal_performance.engine_summary},
        ),
    )
    performance = PerformanceAvailable(
        performance={"selected_candidate_id": "candidate-1", "metrics": {}},
        method_manifest=PerformanceMethodManifest(
            evaluated_rule="rsi", rule_version="v1", substituted=False,
            market="KRX", universe="test", start_date="2026-01-01", end_date="2026-01-03",
            eod_basis="test", initial_capital=1_000_000, rebalance_timing="weekly",
            fill_timing="next_open", corporate_action_method="none", cost_tax_slippage_liquidity="test",
            observations=3, trades=1, data_version="test", result_version="test", execution_version="test",
            historical_simulation_warning="test",
        ),
    )
    return envelope.model_copy(update={"user_payload": envelope.user_payload.model_copy(update={"performance": performance})})


def test_in_memory_job_store_implements_status_lifecycle() -> None:
    store = InMemoryAnalysisJobStore()

    created = store.create_job("RSI strategy")
    assert created.status == AnalysisJobStatus.QUEUED
    assert created.polling_stage == Stage.INTERPRETING
    assert [stage.stage for stage in created.stages] == list(Stage)
    assert {stage.status.value for stage in created.stages} == {"queued"}

    running = store.update_job_status(created.job_id, AnalysisJobStatus.RUNNING, Stage.BACKTEST)
    assert running.status == AnalysisJobStatus.RUNNING
    assert running.polling_stage == Stage.BACKTEST
    assert [stage.status.value for stage in running.stages] == [
        "succeeded",
        "succeeded",
        "running",
        "queued",
        "queued",
    ]

    completed = store.complete_job(created.job_id, _ready_envelope(created.trace_id))
    assert completed.status == AnalysisJobStatus.COMPLETED
    assert completed.polling_stage == Stage.FINALIZING
    assert completed.completed_at is not None
    assert completed.debug_ref == f"debug:{created.trace_id}"
    assert completed.result is not None
    assert completed.result.status == EnvelopeStatus.READY
    assert {stage.status for stage in completed.stages} == {"succeeded"}


def test_memory_completion_populates_reconstructable_execution_manifest() -> None:
    store = InMemoryAnalysisJobStore()
    created = store.create_job("RSI strategy")
    completed = store.complete_job(created.job_id, _completed_backtest_envelope(created.trace_id))

    manifest = completed.execution_manifest
    assert manifest.events.signals
    assert manifest.events.orders
    assert manifest.events.fills
    assert manifest.events.positions
    assert manifest.events.trades
    assert manifest.events.equity
    fill = manifest.events.fills[0]
    assert (fill.requested_qty, fill.filled_qty) == (10.0, 8.0)
    assert fill.component_costs == {"commission_cost": 12.0, "tax_cost": 0.0, "slippage_cost": 5.0}
    assert {"strategy", "data", "cost", "sizing", "benchmark"} <= set(manifest.policy_hashes)
    assert all(len(value) == 64 for value in manifest.policy_hashes.values())
    assert "dsn" not in str(manifest.model_dump(mode="json")).lower()
    assert "password" not in str(manifest.model_dump(mode="json")).lower()


def test_in_memory_job_store_failure_contract_includes_error_envelope() -> None:
    store = InMemoryAnalysisJobStore()
    created = store.create_job("broken strategy")

    failed = store.fail_job(
        created.job_id,
        "execution failed",
        fallback_reasons=["fixture fallback"],
    )

    assert failed.status == AnalysisJobStatus.FAILED
    assert failed.error_message == "execution failed"
    assert failed.fallback_reasons == ["fixture fallback"]
    assert failed.result is not None
    assert failed.result.status == EnvelopeStatus.FAILED
    assert failed.result.failure_cause is not None
    assert failed.result.failure_cause.subcause == "unknown"
    assert failed.result.user_payload.message != "execution failed"


def test_persistent_job_document_round_trips_storage_only_fields() -> None:
    store = InMemoryAnalysisJobStore()
    created = store.create_job("RSI strategy", user_id="42")
    completed = store.complete_job(created.job_id, _completed_backtest_envelope(created.trace_id))

    restored = AnalysisJob.model_validate(_job_document(completed))

    assert restored.user_id == "42"
    assert restored.status == AnalysisJobStatus.COMPLETED
    assert restored.completed_at == completed.completed_at
    assert restored.result == completed.result
    assert restored.execution_manifest == completed.execution_manifest
    # Load-bearing for the restart reaper: if this does not survive the round trip it
    # cannot tell a job this process owns from one a dead process left behind.
    assert restored.owner_incarnation == completed.owner_incarnation
    assert restored.owner_incarnation is not None
    assert _job_document(restored) == _job_document(completed)
    assert "execution_manifest" not in completed.model_dump(mode="json")


def test_job_store_factory_defaults_to_memory_without_env() -> None:
    runtime = create_analysis_job_store_from_env({})

    assert runtime.requested_mode == "memory"
    assert runtime.active_mode == "memory"
    assert runtime.fallback is False


def test_job_store_factory_allows_explicit_memory_mode_for_local_fixtures() -> None:
    runtime = create_analysis_job_store_from_env({"AI_JOB_STORE": "memory"})

    assert runtime.requested_mode == "memory"
    assert runtime.active_mode == "memory"
    assert runtime.fallback is False


def test_job_store_factory_rejects_persistent_mode_without_dsn_or_repository() -> None:
    with pytest.raises(JobStoreConfigurationError, match="configured database DSN"):
        create_analysis_job_store_from_env({"AI_JOB_STORE": "persistent"})


def test_job_store_factory_rejects_persistent_mode_without_repository() -> None:
    with pytest.raises(JobStoreConfigurationError, match="repository adapter"):
        create_analysis_job_store_from_env(
            {"AI_JOB_STORE": "persistent", "AI_DATABASE_DSN": "postgresql://configured"}
        )


def test_canonical_job_document_requires_versioned_secret_free_execution_manifest() -> None:
    store = InMemoryAnalysisJobStore()
    created = store.create_job("RSI strategy", strategy_id="strategy-1", run_id="run-1")
    running = store.update_job_status(created.job_id, AnalysisJobStatus.RUNNING, Stage.BACKTEST)
    document = _job_document(running)

    manifest = document["execution_manifest"]
    assert manifest["schema_version"] == "1"
    assert manifest["run_identity"] == {
        "job_id": created.job_id,
        "trace_id": created.trace_id,
        "strategy_id": "strategy-1",
        "run_id": "run-1",
    }
    assert manifest["policy_hashes"]
    assert manifest["session"]["started_at"] is not None
    assert set(manifest["events"]) == {"signals", "orders", "fills", "positions", "trades", "equity"}
    assert "dsn" not in str(manifest).lower()
    assert "password" not in str(manifest).lower()

class RecordingRepository:
    def __init__(self) -> None:
        self.inner = InMemoryAnalysisJobStore()
        self.calls: list[str] = []

    def create_job(
        self,
        request_text: str,
        *,
        user_id: str | None = None,
        strategy_id: str | None = None,
        run_id: str | None = None,
        fallback_reasons: Sequence[str] | None = None,
    ) -> AnalysisJob:
        self.calls.append("create_job")
        return self.inner.create_job(
            request_text,
            user_id=user_id,
            strategy_id=strategy_id,
            run_id=run_id,
            fallback_reasons=fallback_reasons,
        )

    def get_job(self, job_id: str) -> AnalysisJob | None:
        self.calls.append("get_job")
        return self.inner.get_job(job_id)

    def update_job_status(
        self,
        job_id: str,
        status: AnalysisJobStatus | str,
        polling_stage: Stage | str,
        *,
        fallback_reasons: Sequence[str] | None = None,
        error_message: str | None = None,
        message: str | None = None,
    ) -> AnalysisJob:
        self.calls.append("update_job_status")
        return self.inner.update_job_status(
            job_id,
            status,
            polling_stage,
            fallback_reasons=fallback_reasons,
            error_message=error_message,
            message=message,
        )

    def complete_job(
        self,
        job_id: str,
        result_envelope: APIEnvelope,
        *,
        fallback_reasons: Sequence[str] | None = None,
    ) -> AnalysisJob:
        self.calls.append("complete_job")
        return self.inner.complete_job(
            job_id,
            result_envelope,
            fallback_reasons=fallback_reasons,
        )

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        *,
        fallback_reasons: Sequence[str] | None = None,
        result_envelope: APIEnvelope | None = None,
    ) -> AnalysisJob:
        self.calls.append("fail_job")
        return self.inner.fail_job(
            job_id,
            error_message,
            fallback_reasons=fallback_reasons,
            result_envelope=result_envelope,
        )

    def list_jobs(self, *, limit: int = 100, user_id: str | None = None) -> list[AnalysisJob]:
        self.calls.append("list_jobs")
        return self.inner.list_jobs(limit=limit, user_id=user_id)


def test_persistent_job_store_delegates_to_repository_contract() -> None:
    repository = RecordingRepository()
    store = PersistentAnalysisJobStore(repository)

    created = store.create_job("RSI strategy", user_id="user-1")
    updated = store.update_job_status(created.job_id, "running", Stage.CODE_GENERATION)
    completed = store.complete_job(updated.job_id, _ready_envelope(updated.trace_id))
    reloaded = store.get_job(completed.job_id)
    listed = store.list_jobs()

    assert completed.status == AnalysisJobStatus.COMPLETED
    assert reloaded == completed
    assert listed == [completed]
    assert repository.calls == [
        "create_job",
        "update_job_status",
        "complete_job",
        "get_job",
        "list_jobs",
    ]


def test_persistent_factory_rejects_memory_store_factory() -> None:
    with pytest.raises(JobStoreConfigurationError, match="memory fallback is forbidden"):
        create_analysis_job_store_from_env(
            {"AI_JOB_STORE": "persistent", "AI_DATABASE_DSN": "postgresql://configured"},
            repository=RecordingRepository(),
            persistent_store_factory=lambda _: InMemoryAnalysisJobStore(),
        )

def test_job_store_factory_uses_persistent_repository_when_configured() -> None:
    repository = RecordingRepository()

    runtime = create_analysis_job_store_from_env(
        {
            "AI_JOB_STORE": "persistent",
            "AI_DATABASE_DSN": "postgresql://db-team-provided",
        },
        repository=repository,
        persistent_store_factory=PersistentAnalysisJobStore,
    )

    assert runtime.requested_mode == "persistent"
    assert runtime.active_mode == "persistent"
    assert runtime.fallback is False
    created = runtime.store.create_job("RSI strategy")
    assert created.query == "RSI strategy"
    assert repository.calls == ["create_job"]


def test_job_store_factory_uses_database_url_alias_when_configured() -> None:
    repository = RecordingRepository()

    runtime = create_analysis_job_store_from_env(
        {
            "AI_JOB_STORE": "persistent",
            "DATABASE_URL": "postgresql+asyncpg://db-team-provided",
        },
        repository=repository,
        persistent_store_factory=PersistentAnalysisJobStore,
    )

    assert runtime.requested_mode == "persistent"
    assert runtime.active_mode == "persistent"
    assert runtime.fallback is False
    assert runtime.dsn_configured is True
    assert runtime.dsn_env == "DATABASE_URL"
