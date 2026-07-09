from __future__ import annotations

from collections.abc import Sequence

from ai_graph.job_store_persistent import PersistentAnalysisJobStore
from ai_graph.jobs import (
    AnalysisJob,
    AnalysisJobStatus,
    InMemoryAnalysisJobStore,
    create_analysis_job_store_from_env,
)
from ai_graph.schemas import APIEnvelope, EnvelopeStatus, Stage, UserPayload


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


def test_job_store_factory_defaults_to_memory_without_env() -> None:
    runtime = create_analysis_job_store_from_env({})

    assert runtime.requested_mode == "memory"
    assert runtime.active_mode == "memory"
    assert runtime.fallback is False


def test_job_store_factory_falls_back_when_persistent_repository_missing() -> None:
    runtime = create_analysis_job_store_from_env({"AI_JOB_STORE": "persistent"})

    assert runtime.requested_mode == "persistent"
    assert runtime.active_mode == "memory"
    assert runtime.fallback is True
    assert "AI_DATABASE_DSN" in runtime.fallback_reason


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

    def list_jobs(self, *, limit: int = 100) -> list[AnalysisJob]:
        self.calls.append("list_jobs")
        return self.inner.list_jobs(limit=limit)


def test_persistent_job_store_delegates_to_repository_contract() -> None:
    repository = RecordingRepository()
    store = PersistentAnalysisJobStore(repository)

    created = store.create_job("RSI strategy", user_id="user-1")
    updated = store.update_job_status(created.job_id, "running", Stage.CODE_GENERATION)
    completed = store.complete_job(updated.job_id, _ready_envelope(updated.trace_id))
    listed = store.list_jobs()

    assert completed.status == AnalysisJobStatus.COMPLETED
    assert listed == [completed]
    assert repository.calls == [
        "create_job",
        "update_job_status",
        "complete_job",
        "list_jobs",
    ]


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
