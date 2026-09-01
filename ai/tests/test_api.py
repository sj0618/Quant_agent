from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError

if TYPE_CHECKING:
    from offline_test_environment import OfflineTestEnvironment

from ai_graph.api import (
    AI_CORS_ALLOW_ORIGINS_ENV,
    ANALYSIS_JOB_EVIDENCE_PROBE_PATH,
    ANALYSIS_JOB_CANCEL_PATH,
    ANALYSIS_JOB_DETAIL_PATH,
    ANALYSIS_JOBS_PATH,
    API_STATUS_PATH,
    DAILY_DIGEST_PATH,
    DOCS_URL,
    HEALTH_PATH,
    OPENAPI_URL,
    READINESS_PATH,
    SPEC_STRATEGY_PARSE_PATH,
    STRATEGY_DESCRIPTIONS_PATH,
    create_app,
)
from ai_graph.audit import NoOpAuditSink, RecordingAuditSink
from ai_graph.audit_postgres import _create_test_audit_sink
from ai_graph.jobs import (
    AnalysisJobStatus,
    InMemoryAnalysisJobStore,
    JobStoreConfigurationError,
    JobStoreRuntime,
)
from ai_graph.research_contract import (
    ExplorationCandidateRefV2,
    ExplorationExecutionSpecV2,
    RuleDraftSigner,
    canonical_rule_digest,
)
from ai_graph.research_eligibility import PerformanceAvailable
from ai_graph.schemas import (
    APIEnvelope,
    EnvelopeStatus,
    FreshnessEvidence,
    ReportBundle,
    ReportProjection,
    UserPayload,
)

pytest_plugins = ("offline_test_environment",)
pytestmark = pytest.mark.usefixtures("offline_test_environment")

DATA_SOURCE_ENV_KEYS = (
    "AI_DATABASE_DSN",
    "QUANT_DB_DSN",
    "DATABASE_URL",
    "AI_DEFAULT_TICKER",
    "AI_BACKTEST_LOOKBACK_DAYS",
    "AI_L4_EVIDENCE_LIMIT",
    "AI_DB_CONNECT_TIMEOUT_SECONDS",
    "AI_DB_STATEMENT_TIMEOUT_MS",
    "AI_SECTOR_CACHE_TTL_SECONDS",
)
MOCK_PROVIDER_CREDENTIAL_ENV = "AI_AOAI_API_KEY"
MOCK_PROVIDER_CREDENTIAL_SENTINEL = "qa-mock-provider-sentinel-key"
MOCK_PROVIDER_STAGES = ["interpreting", "code_generation", "backtest", "debate", "finalizing"]


def _poll_job(client, job_id: str) -> dict:
    """Read a job back through the polling endpoint.

    POST /analysis-jobs only queues the analysis, so the finished envelope is never
    on the create response - this is the same create-then-poll path the FE takes.
    TestClient drains the background task before returning, so one poll is enough.
    """

    response = client.get(f"{ANALYSIS_JOBS_PATH}/{job_id}")
    assert response.status_code == 200
    return response.json()


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

def test_swagger_openapi_lists_current_api_surface() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    docs_response = client.get(DOCS_URL)
    assert docs_response.status_code == 200
    assert "SwaggerUIBundle" in docs_response.text

    schema_response = client.get(OPENAPI_URL)
    assert schema_response.status_code == 200
    paths = schema_response.json()["paths"]

    assert HEALTH_PATH in paths
    assert READINESS_PATH in paths
    assert API_STATUS_PATH in paths
    assert ANALYSIS_JOBS_PATH in paths
    assert ANALYSIS_JOB_DETAIL_PATH in paths
    assert SPEC_STRATEGY_PARSE_PATH in paths
    assert STRATEGY_DESCRIPTIONS_PATH in paths
    assert DAILY_DIGEST_PATH in paths
    assert "/api/analysis-jobs/{job_id}" in paths
    assert "/api/backtests/{strategy_id}" in paths
    assert "/api/reports/{report_id}" in paths


def _persistent_job_store_runtime() -> JobStoreRuntime:
    return JobStoreRuntime(
        store=InMemoryAnalysisJobStore(),
        requested_mode="persistent",
        active_mode="persistent",
        fallback=False,
        fallback_reason=None,
        dsn_configured=True,
    )


def _configure_live_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    monkeypatch.setenv("AI_AOAI_RESPONSES_URL", "https://example.test/openai/v1/responses")
    monkeypatch.setenv("AI_AOAI_API_KEY", "test-readiness-key")
    monkeypatch.setenv("AI_AOAI_MODEL", "test-readiness-model")


def test_release_readiness_requires_durable_job_store_before_other_dependencies() -> None:
    migration_calls = 0

    def migration_probe() -> bool:
        nonlocal migration_calls
        migration_calls += 1
        return True

    response = TestClient(
        create_app(InMemoryAnalysisJobStore(), readiness_migration_probe=migration_probe)
    ).get(READINESS_PATH)

    assert response.status_code == 503
    checks = {check["name"]: check for check in response.json()["checks"]}
    assert checks["durable_job_store"] == {
        "name": "durable_job_store",
        "ready": False,
        "reason": "durable_job_store_required",
    }
    assert checks["migration_revision"]["reason"] == "migration_revision_required"
    assert migration_calls == 0


def test_release_readiness_rejects_missing_migration_and_contract_drift(monkeypatch) -> None:
    _configure_live_provider(monkeypatch)
    missing_migration = TestClient(
        create_app(
            job_store_runtime=_persistent_job_store_runtime(),
            readiness_migration_probe=lambda: False,
            rule_draft_signer=RuleDraftSigner("test-rule-draft-secret"),
        )
    ).get(READINESS_PATH)
    assert missing_migration.status_code == 503
    checks = {check["name"]: check for check in missing_migration.json()["checks"]}
    assert checks["migration_revision"]["reason"] == "migration_revision_required"

    ready_client = TestClient(
        create_app(
            job_store_runtime=_persistent_job_store_runtime(),
            readiness_migration_probe=lambda: True,
            rule_draft_signer=RuleDraftSigner("test-rule-draft-secret"),
        )
    )
    ready = ready_client.get(READINESS_PATH)
    assert ready.status_code == 200
    assert ready.json()["migration_revision"] == "025_exploration_policy_v2"

    monkeypatch.setattr("ai_graph.api.SCHEMA_VERSION", "ai-mvp.v0")
    drifted = ready_client.get(READINESS_PATH)
    assert drifted.status_code == 503
    checks = {check["name"]: check for check in drifted.json()["checks"]}
    assert checks["ai_contract_version"] == {
        "name": "ai_contract_version",
        "ready": False,
        "reason": "ai_contract_version_mismatch",
    }


def test_release_readiness_requires_a_rule_draft_signer() -> None:
    response = TestClient(
        create_app(
            job_store_runtime=_persistent_job_store_runtime(),
            readiness_migration_probe=lambda: True,
        )
    ).get(READINESS_PATH)

    assert response.status_code == 503
    checks = {check["name"]: check for check in response.json()["checks"]}
    assert checks["rule_draft_signer"] == {
        "name": "rule_draft_signer",
        "ready": False,
        "reason": "rule_draft_signer_required",
    }


def test_release_readiness_requires_live_aoai_configuration(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "mock")
    client = TestClient(
        create_app(
            job_store_runtime=_persistent_job_store_runtime(),
            readiness_migration_probe=lambda: True,
            rule_draft_signer=RuleDraftSigner("test-rule-draft-secret"),
        )
    )

    mock_provider = client.get(READINESS_PATH)
    assert mock_provider.status_code == 503
    checks = {check["name"]: check for check in mock_provider.json()["checks"]}
    assert checks["live_provider_configuration"] == {
        "name": "live_provider_configuration",
        "ready": False,
        "reason": "live_provider_configuration_required",
    }

    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    monkeypatch.setenv("AI_AOAI_RESPONSES_URL", "https://example.test/openai/v1/responses")
    monkeypatch.setenv("AI_AOAI_API_KEY", "test-readiness-key")
    monkeypatch.delenv("AI_AOAI_MODEL", raising=False)
    incomplete_provider = client.get(READINESS_PATH)
    assert incomplete_provider.status_code == 503
    checks = {check["name"]: check for check in incomplete_provider.json()["checks"]}
    assert checks["live_provider_configuration"]["reason"] == "live_provider_configuration_required"

    _configure_live_provider(monkeypatch)
    assert client.get(READINESS_PATH).status_code == 200


def test_api_status_exposes_data_source_without_dsn_value(monkeypatch) -> None:
    monkeypatch.setenv("AI_DATABASE_DSN", "postgresql://secret-user:secret-pass@db/quant_agent")
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.get(API_STATUS_PATH)

    assert response.status_code == 200
    data_source = response.json()["data_source"]
    assert data_source["configured"] is True
    assert data_source["dsn_env"] == "AI_DATABASE_DSN"
    assert "secret" not in str(data_source)
    assert data_source["price_source"] == "feature.kis_adjusted_ohlcv_daily"
    assert response.json()["job_store"]["active_mode"] == "memory"
    assert "secret" not in str(response.json()["job_store"])


def test_isolated_staging_evidence_probe_requires_the_operator_token_and_projects_no_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_DATA_EVIDENCE_PROBE_TOKEN", "operator-test-token")
    monkeypatch.setenv("AI_AUDIT_GATE_B_DEPLOYMENT_REVISION", "a" * 40)
    evidence = {
        "job_id": "job-1",
        "execution_spec_version": "strategy-execution-spec.v1",
        "execution_spec_hash": "b" * 64,
        "analysis_result_id": "result-1",
        "manifest_hash": "c" * 64,
        "source": "postgres",
        "as_of": "2026-08-28",
        "observations": 500,
        "candidate_count": 2,
        "successful_aoai_calls": 1,
        "immutable_trigger_present": True,
    }
    client = TestClient(
        create_app(
            InMemoryAnalysisJobStore(),
            immutable_result_evidence_probe=lambda _job_id: evidence,
        )
    )

    denied = client.get(ANALYSIS_JOB_EVIDENCE_PROBE_PATH.format(job_id="job-1"))
    accepted = client.get(
        ANALYSIS_JOB_EVIDENCE_PROBE_PATH.format(job_id="job-1"),
        headers={"X-AI-Evidence-Probe": "operator-test-token"},
    )
    status = client.get(API_STATUS_PATH)

    assert denied.status_code == 404
    assert accepted.status_code == 200
    assert accepted.json() == evidence
    assert status.json()["deployment_revision"] == "a" * 40
    assert "operator-test-token" not in accepted.text


def test_api_status_uses_database_url_alias_for_data_source(monkeypatch) -> None:
    monkeypatch.delenv("AI_DATABASE_DSN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://secret-user:secret-pass@db/quant_agent")
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.get(API_STATUS_PATH)

    assert response.status_code == 200
    data_source = response.json()["data_source"]
    assert data_source["configured"] is True
    assert data_source["dsn_env"] == "DATABASE_URL"
    assert "secret" not in str(data_source)


def test_api_rejects_unconfigured_persistent_job_store(monkeypatch) -> None:
    monkeypatch.setenv("AI_JOB_STORE", "persistent")
    monkeypatch.delenv("AI_DATABASE_DSN", raising=False)

    with pytest.raises(JobStoreConfigurationError, match="requires a configured database DSN"):
        create_app()


def test_api_status_activates_postgres_job_store_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("AI_JOB_STORE", "persistent")
    monkeypatch.setenv("AI_DATABASE_DSN", "postgresql://db/quant_agent")
    client = TestClient(create_app())

    job_store = client.get(API_STATUS_PATH).json()["job_store"]

    assert job_store["active_mode"] == "persistent"
    assert job_store["fallback"] is False


def test_cors_preflight_allows_configured_fe_origin(monkeypatch) -> None:
    origin = "http://localhost:5173"
    monkeypatch.setenv(AI_CORS_ALLOW_ORIGINS_ENV, origin)
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.options(
        ANALYSIS_JOBS_PATH,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_analysis_job_api_runs_real_graph_and_can_be_polled() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    create_response = client.post(
        ANALYSIS_JOBS_PATH,
        json={
            "query": "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어"
        },
    )

    assert create_response.status_code == 201
    created_job = create_response.json()
    assert created_job["result"] is None

    polled_job = _poll_job(client, created_job["job_id"])

    assert polled_job["job_id"] == created_job["job_id"]
    assert polled_job["trace_id"] == created_job["trace_id"]
    assert polled_job["result"]["status"] == "ready"
    assert "internal_payload" not in polled_job["result"]
    assert [stage["stage"] for stage in polled_job["stages"]] == MOCK_PROVIDER_STAGES
    assert all(stage["status"] == "succeeded" for stage in polled_job["stages"])
    performance = polled_job["result"]["user_payload"]["performance"]
    assert performance["availability"] == "unavailable"
    assert performance["reason_code"] == "insufficient_reliability"
    assert "performance" not in performance
    assert "metrics" not in performance
    assert "equity_curve" not in performance
    assert polled_job["result"]["user_payload"]["ticker_actions"] == []


def test_production_rejects_unready_core_execution_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    store = InMemoryAnalysisJobStore()
    sink = RecordingAuditSink()
    runner_calls = 0

    def runner(_query: str, _trace_id: str) -> APIEnvelope:
        nonlocal runner_calls
        runner_calls += 1
        raise AssertionError("unready core endpoint reached the analysis runner")

    client = TestClient(
        create_app(
            store,
            analysis_runner=runner,
            audit_sink=_create_test_audit_sink(sink),
        )
    )

    response = client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI 30 이하 종목"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "analysis_execution_unavailable"
    assert store.list_jobs() == []
    assert runner_calls == 0
    assert sink.sessions == ()


def test_ready_release_accepts_parse_bound_core_natural_language_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release admission accepts only a parse-bound natural-language execution spec."""

    monkeypatch.setenv("APP_ENV", "production")
    _configure_live_provider(monkeypatch)
    signer = RuleDraftSigner("test-rule-draft-secret")
    client = TestClient(
        create_app(
            job_store_runtime=_persistent_job_store_runtime(),
            analysis_runner=lambda _query, trace_id: _ready_envelope(trace_id),
            readiness_migration_probe=lambda: True,
            rule_draft_signer=signer,
        )
    )

    parse = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={"natural_language": "RSI 30 이하 진입, RSI 70 이상 청산 전략"},
    )
    assert parse.status_code == 200
    draft = parse.json()
    response = client.post(
        ANALYSIS_JOBS_PATH,
        json={
            "parse_token": draft["parse_token"],
            "client_idempotency_key": "32ecc88e-a50d-4b4d-9c5e-573d817b410a",
            "spec_version": draft["spec_version"],
            "spec_hash": draft["spec_hash"],
            "strategy_execution_spec": draft["strategy_execution_spec"],
        },
    )

    assert response.status_code == 201
    assert response.json()["job_id"]


def test_live_v3_parse_uses_the_server_metric_catalog_before_sealing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown strategy cannot be sealed against a static prompt-only vocabulary."""

    import ai_graph.llm

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(ai_graph.llm, "is_live_llm_provider", lambda: True)
    monkeypatch.setattr("ai_graph.api._live_provider_configuration_is_ready", lambda: True)

    captured: list[object] = []

    class _ResearchClient:
        def generate_json(self, request):
            captured.append(request)
            return {
                "resolution_summary": "돈치안 채널을 20일 최고가 돌파 규칙으로 해석했습니다.",
                "sources": [
                    {
                        "source_id": "source-1",
                        "title": "Donchian channel definition",
                        "url": "https://example.com/donchian",
                        "claim": "돈치안 채널은 일정 기간의 최고가와 최저가 범위입니다.",
                    }
                ],
                "candidates": [
                    {
                        "candidate_id": "research-donchian-breakout-20",
                        "title": "20일 돈치안 상단 돌파",
                        "hypothesis": "상단 돌파 뒤 추세가 이어질 수 있습니다.",
                        "counter_hypothesis": "횡보장에서는 거짓 돌파가 잦을 수 있습니다.",
                        "entry_conditions": [
                            {
                                "left": "close",
                                "operator": "gte",
                                "right": "high",
                                "window": 20,
                                "aggregate": "max",
                                "scale": 0.995,
                            }
                        ],
                        "exit_conditions": [
                            {"left": "close", "operator": "lte", "right": "sma20"}
                        ],
                        "required_metrics": ["close", "high", "sma20"],
                        "assumptions": ["일봉 종가 기준으로 다음 거래일 체결을 가정합니다."],
                        "source_ids": ["source-1"],
                    }
                ],
            }

    monkeypatch.setattr(
        "ai_graph.nodes.strategy_research.create_llm_client",
        lambda **_kwargs: _ResearchClient(),
    )
    client = TestClient(
        create_app(
            job_store_runtime=_persistent_job_store_runtime(),
            readiness_migration_probe=lambda: True,
            rule_draft_signer=RuleDraftSigner("test-rule-draft-secret"),
            indicator_catalog_resolver=lambda: ["sma20"],
        )
    )

    response = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={"natural_language": "돈치안 채널 돌파 전략으로 검증해줘"},
    )

    assert response.status_code == 200
    review = response.json()
    assert review["spec_version"] == "research-candidate-execution-spec.v3"
    assert review["strategy_execution_spec"]["candidates"][0]["title"] == "20일 돈치안 상단 돌파"
    assert len(captured) == 1
    request = captured[0]
    assert request.enable_web_search is True
    assert '"sma20"' in request.user_prompt


def test_malformed_live_v3_research_returns_a_no_admission_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider/schema failures must not become a 500 or create an execution token."""

    monkeypatch.setenv("APP_ENV", "production")
    _configure_live_provider(monkeypatch)

    class _MalformedResearchClient:
        def generate_json(self, _request):
            return {"unexpected": True}

    monkeypatch.setattr(
        "ai_graph.nodes.strategy_research.create_llm_client",
        lambda **_kwargs: _MalformedResearchClient(),
    )
    client = TestClient(
        create_app(
            job_store_runtime=_persistent_job_store_runtime(),
            readiness_migration_probe=lambda: True,
            rule_draft_signer=RuleDraftSigner("test-rule-draft-secret"),
            indicator_catalog_resolver=lambda: ["sma20"],
        )
    )

    response = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={"natural_language": "돈 벌 수 있는 전략 만들어줘"},
    )

    assert response.status_code == 200
    review = response.json()
    assert review["is_executable"] is False
    assert review["parse_token"] is None
    assert review["strategy_execution_spec"] is None


def test_production_rejects_catalogue_fallback_when_ai_research_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    signer = RuleDraftSigner("test-rule-draft-secret")
    app = create_app(
        job_store_runtime=_persistent_job_store_runtime(),
        readiness_migration_probe=lambda: True,
        rule_draft_signer=signer,
        indicator_catalog_resolver=lambda: ["sma20"],
    )
    app.state.strategy_parser_uses_llm = False
    client = TestClient(app)

    parse = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={"natural_language": "돈 벌 수 있는 전략 만들어줘"},
    )

    assert parse.status_code == 503
    assert parse.json()["detail"]["code"] == "strategy_research_unavailable"

    legacy_spec = ExplorationExecutionSpecV2(
        policy_version="v2-test",
        policy_hash="a" * 64,
        catalog_version="v2-test",
        catalog_hash="b" * 64,
        candidates=[
            ExplorationCandidateRefV2(catalog_id="qb-v2-momentum", execution_signature="c" * 64),
            ExplorationCandidateRefV2(catalog_id="qb-v2-value", execution_signature="d" * 64),
        ],
    )
    legacy_token = signer.issue(rule=legacy_spec, user_id="local-dev-user")
    admission = client.post(
        ANALYSIS_JOBS_PATH,
        json={
            "parse_token": legacy_token.token,
            "client_idempotency_key": "v3-regression-reject-v2-0001",
            "spec_version": "exploration-execution-spec.v2",
            "spec_hash": canonical_rule_digest(legacy_spec),
            "strategy_execution_spec": legacy_spec.model_dump(mode="json"),
        },
    )

    assert admission.status_code == 503
    assert admission.json()["detail"]["code"] == "strategy_research_required"


def test_ready_release_accepts_raw_natural_language_and_seals_it_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    _configure_live_provider(monkeypatch)
    client = TestClient(
        create_app(
            job_store_runtime=_persistent_job_store_runtime(),
            analysis_runner=lambda _query, trace_id: _ready_envelope(trace_id),
            readiness_migration_probe=lambda: True,
            rule_draft_signer=RuleDraftSigner("test-rule-draft-secret"),
        )
    )

    response = client.post(
        ANALYSIS_JOBS_PATH,
        json={"query": "RSI 30 이하 진입, RSI 70 이상 청산 전략"},
    )

    assert response.status_code == 201
    job_id = response.json()["job_id"]
    persisted = _poll_job(client, job_id)
    assert persisted["result"]["status"] == "ready", persisted
    # The browser supplies one human-readable query only. The server creates and
    # consumes the short-lived parse nonce inside the durable admission path, so a
    # stale client-side token cannot cause the 409 replay failure that this route
    # replaced.
    # The execution spec, not this text, is the authority for the backtest.  Keeping
    # the original request gives the later AOAI Research node the user's actual
    # strategy context while the signed contract still prevents it from changing the
    # entry/exit rules.
    assert persisted["query"] == "RSI 30 이하 진입, RSI 70 이상 청산 전략"


def test_core_execution_keeps_restart_reconciliation_for_prior_process_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The active creation path must not weaken startup reconciliation."""

    monkeypatch.setenv("APP_ENV", "production")
    inner = InMemoryAnalysisJobStore()
    job = inner.create_job("이전 프로세스의 분석", user_id="local-dev-user")
    running = inner.update_job_status(job.job_id, AnalysisJobStatus.RUNNING, "backtest")
    inner.jobs[job.job_id] = running.model_copy(update={"owner_incarnation": "previous-process"})

    app = create_app(inner)
    with TestClient(app):
        assert app.state.job_store is inner

    settled = inner.get_job(job.job_id)
    assert settled is not None
    assert settled.status is AnalysisJobStatus.FAILED
    assert settled.error_message is not None


def test_backtest_api_redacts_legacy_insufficient_performance_before_serialization() -> None:
    legacy_available = PerformanceAvailable.model_construct(
        availability="available",
        performance={
            "metrics": {"total_return": 0.12, "sharpe_ratio": 0.3},
            "equity_curve": [{"date": "2026-01-01", "cumulative_return": 0.12}],
            "reliability": {
                "source": "fixture",
                "status": "insufficient",
                "row_count": 4,
                "ticker_count": 1,
                "trading_days": 4,
                "trade_count": 7,
            },
        },
        method_manifest=None,
        limitations=[],
    )
    envelope = APIEnvelope.model_construct(
        status=EnvelopeStatus.READY,
        trace_id="legacy-warmup-trace",
        user_payload=UserPayload.model_construct(
            headline="ready",
            message="analysis completed",
            next_actions=[],
            performance=legacy_available,
        ),
        strategy_spec=None,
        debug_ref="debug:legacy-warmup",
        retryable=False,
    )
    store = InMemoryAnalysisJobStore()
    job = store.create_job("legacy warm-up RSI 전략", user_id="local-dev-user")
    store.complete_job(job.job_id, envelope)
    client = TestClient(create_app(store))
    response = client.get(f"{ANALYSIS_JOBS_PATH}/{job.job_id}")

    assert response.status_code == 200
    public_performance = response.json()["result"]["user_payload"]["performance"]
    assert public_performance["availability"] == "unavailable"
    assert public_performance["reason_code"] == "insufficient_reliability"
    assert public_performance["safe_facts"] == {
        "source": "fixture",
        "row_count": 4,
        "ticker_count": 1,
        "trading_days": 4,
        "trade_count": 7,
        "history_start": None,
        "history_end": None,
    }
    assert "metrics" not in public_performance
    assert "equity_curve" not in public_performance


def test_job_api_redacts_legacy_available_performance_when_source_is_stale() -> None:
    legacy_available = PerformanceAvailable.model_construct(
        availability="available",
        performance={
            "metrics": {"total_return": 0.12, "sharpe_ratio": 0.3},
            "equity_curve": [{"date": "2026-01-01", "cumulative_return": 0.12}],
            "reliability": {
                "source": "postgres",
                "status": "sufficient",
                "row_count": 1_260,
                "ticker_count": 5,
                "trading_days": 252,
                "trade_count": 8,
            },
        },
        method_manifest=None,
        limitations=[],
    )
    envelope = APIEnvelope.model_construct(
        status=EnvelopeStatus.READY,
        trace_id="legacy-stale-trace",
        user_payload=UserPayload.model_construct(
            headline="ready",
            message="analysis completed",
            next_actions=[],
            performance=legacy_available,
            report=ReportBundle(
                web_projection=ReportProjection(
                    title="legacy report",
                    summary="legacy stale result",
                    sections=[
                        {
                            "id": "performance",
                            "title": "후보 코드 백테스트",
                            "items": legacy_available.model_dump(mode="json"),
                        }
                    ],
                ),
                email_projection=ReportProjection(
                    title="legacy report",
                    summary="legacy stale result",
                    sections=[],
                ),
                risk_adjustments=[],
            ),
        ),
        strategy_spec=None,
        debug_ref="debug:legacy-stale",
        retryable=False,
        freshness_evidence=FreshnessEvidence(
            status="stale",
            as_of=date(2026, 8, 18),
            reason="price source exceeded the configured freshness window",
            source="postgres",
            no_recommendation=True,
        ),
    )
    store = InMemoryAnalysisJobStore()
    job = store.create_job("legacy stale RSI 전략", user_id="local-dev-user")
    store.complete_job(job.job_id, envelope)
    client = TestClient(create_app(store))

    response = client.get(f"{ANALYSIS_JOBS_PATH}/{job.job_id}")

    assert response.status_code == 200
    public_performance = response.json()["result"]["user_payload"]["performance"]
    assert public_performance == {
        "availability": "unavailable",
        "reason_code": "stale_source",
        "safe_facts": {
            "source": "postgres",
            "row_count": 1_260,
            "ticker_count": 5,
            "trading_days": 252,
            "trade_count": 8,
            "history_start": None,
            "history_end": None,
            "freshness_status": "stale",
            "freshness_as_of": "2026-08-18",
            "freshness_reason": "price source exceeded the configured freshness window",
        },
    }
    report_performance = next(
        section
        for section in response.json()["result"]["user_payload"]["report"]["web_projection"][
            "sections"
        ]
        if section["id"] == "performance"
    )
    assert report_performance["items"] == public_performance

    status_only_job = store.create_job("legacy stale status-only RSI 전략", user_id="local-dev-user")
    store.complete_job(
        status_only_job.job_id,
        envelope.model_copy(
            update={"freshness_evidence": None, "freshness_status": "stale"}
        ),
    )
    status_only_response = client.get(f"{ANALYSIS_JOBS_PATH}/{status_only_job.job_id}")

    assert status_only_response.status_code == 200
    status_only_performance = status_only_response.json()["result"]["user_payload"][
        "performance"
    ]
    assert status_only_performance["availability"] == "unavailable"
    assert status_only_performance["reason_code"] == "stale_source"
    assert status_only_performance["safe_facts"]["freshness_status"] == "stale"
    assert "performance" not in status_only_performance

    report_only_job = store.create_job("legacy stale report-only RSI 전략", user_id="local-dev-user")
    store.complete_job(
        report_only_job.job_id,
        envelope.model_copy(
            update={
                "user_payload": envelope.user_payload.model_copy(update={"performance": None})
            }
        ),
    )
    report_only_response = client.get(f"{ANALYSIS_JOBS_PATH}/{report_only_job.job_id}")

    assert report_only_response.status_code == 200
    report_only_performance = report_only_response.json()["result"]["user_payload"][
        "performance"
    ]
    assert report_only_performance["availability"] == "unavailable"
    assert report_only_performance["reason_code"] == "stale_source"
    report_only_section = next(
        section
        for section in report_only_response.json()["result"]["user_payload"]["report"][
            "web_projection"
        ]["sections"]
        if section["id"] == "performance"
    )
    assert report_only_section["items"] == report_only_performance


def test_analysis_job_api_turns_vague_request_into_automatic_tournament() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    created = client.post(
        ANALYSIS_JOBS_PATH,
        json={"query": "뭐 좀 괜찮은 거 없냐"},
    )
    assert created.status_code == 201

    result = _poll_job(client, created.json()["job_id"])["result"]

    assert result["status"] == "ready"
    assert result["strategy_spec"]["selection_mode"] == "automatic"
    assert result["strategy_spec"]["strategy_id"].startswith(
        "automatic_performance_momentum"
    )
    assert result["rule_provenance"]["substituted"] is False
    projection = result["user_payload"]["performance"]
    assert projection["availability"] == "unavailable"
    assert projection["reason_code"] == "insufficient_reliability"
    assert "performance" not in projection


def test_analysis_job_api_lists_only_authenticated_users_jobs_newest_first() -> None:
    store = InMemoryAnalysisJobStore()
    client = TestClient(create_app(store))

    first = client.post(ANALYSIS_JOBS_PATH, json={"query": "첫 번째 RSI 전략"}).json()
    second = client.post(ANALYSIS_JOBS_PATH, json={"query": "두 번째 이동평균 전략"}).json()
    store.create_job("다른 사용자 전략", user_id="other-user")

    response = client.get(ANALYSIS_JOBS_PATH)

    assert response.status_code == 200
    assert [job["job_id"] for job in response.json()] == [second["job_id"], first["job_id"]]


def test_analysis_job_api_list_honors_limit() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))
    _ = client.post(ANALYSIS_JOBS_PATH, json={"query": "첫 번째 RSI 전략"})
    second = client.post(ANALYSIS_JOBS_PATH, json={"query": "두 번째 이동평균 전략"}).json()

    response = client.get(f"{ANALYSIS_JOBS_PATH}?limit=1")

    assert response.status_code == 200
    assert [job["job_id"] for job in response.json()] == [second["job_id"]]


def test_documented_fixture_mvp_profile_reports_and_executes_expected_spine(monkeypatch) -> None:
    for key in DATA_SOURCE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("BE_JOB_STORE_MODE", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("AUTH_SESSION_COOKIE_NAME", raising=False)
    monkeypatch.delenv(AI_CORS_ALLOW_ORIGINS_ENV, raising=False)

    monkeypatch.setenv("AUTH_ENABLED", "0")
    monkeypatch.setenv("AI_LLM_PROVIDER", "mock")
    monkeypatch.setenv("AI_JOB_STORE", "memory")
    monkeypatch.setenv("AI_AUDIT_SINK", "noop")
    monkeypatch.setenv(MOCK_PROVIDER_CREDENTIAL_ENV, MOCK_PROVIDER_CREDENTIAL_SENTINEL)

    client = TestClient(create_app())

    api_status = client.get(API_STATUS_PATH)
    assert api_status.status_code == 200
    assert MOCK_PROVIDER_CREDENTIAL_SENTINEL not in api_status.text
    assert api_status.json()["data_source"]["configured"] is False
    job_store = api_status.json()["job_store"]
    assert job_store["requested_mode"] == "memory"
    assert job_store["active_mode"] == "memory"
    assert job_store["fallback"] is False

    create_response = client.post(
        ANALYSIS_JOBS_PATH,
        json={
            "query": "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어"
        },
    )
    assert create_response.status_code == 201
    created_job = create_response.json()
    assert created_job["result"] is None

    polled_job = _poll_job(client, created_job["job_id"])
    created_result = polled_job["result"]

    assert created_result["status"] == "ready"
    assert created_job["trace_id"] == created_result["trace_id"]
    assert [stage["stage"] for stage in polled_job["stages"]] == MOCK_PROVIDER_STAGES
    assert all(stage["status"] == "succeeded" for stage in polled_job["stages"])
    assert "internal_payload" not in created_result
    assert "node_outputs" not in created_result
    assert "llm_prompts" not in created_result

    assert created_result["strategy_spec"] is not None
    assert created_result["user_payload"]["performance"] is not None
    assert created_result["user_payload"]["report"] is not None
    report = created_result["user_payload"]["report"]
    assert report["web_projection"]
    assert report["email_projection"]
    performance = created_result["user_payload"]["performance"]
    assert performance["availability"] == "unavailable"
    assert performance["reason_code"] == "insufficient_reliability"
    assert "performance" not in performance
    assert "metrics" not in performance
    assert "equity_curve" not in performance

    poll_response = client.get(f"{ANALYSIS_JOBS_PATH}/{created_job['job_id']}")
    assert poll_response.status_code == 200
    polled_job = poll_response.json()
    assert polled_job["job_id"] == created_job["job_id"]
    assert polled_job["trace_id"] == created_job["trace_id"]
    assert polled_job["result"] == created_result
    assert polled_job["result"]["status"] == "ready"

    assert MOCK_PROVIDER_CREDENTIAL_SENTINEL not in create_response.text
    assert MOCK_PROVIDER_CREDENTIAL_SENTINEL not in poll_response.text

    # Out-of-scope assets are rejected before a job, audit, provider, or data-source
    # path can start.  The former queued "rejected" job retained prohibited input.
    rejected_response = client.post(ANALYSIS_JOBS_PATH, json={"query": "옵션 양매도 전략 만들어줘"})
    assert rejected_response.status_code == 422
    rejected_payload = rejected_response.json()
    assert rejected_payload["kind"] == "unsupported_scope"
    assert rejected_payload["reason_code"] == "unsupported_asset_family"
    assert "job_id" not in rejected_payload
    assert "trace_id" not in rejected_payload

    assert MOCK_PROVIDER_CREDENTIAL_SENTINEL not in rejected_response.text

def test_spec_strategy_parse_returns_a_signed_rule_review_without_creating_a_job(
    offline_test_environment: "OfflineTestEnvironment",
) -> None:
    store = InMemoryAnalysisJobStore()
    sink = RecordingAuditSink()
    client = TestClient(
        create_app(
            store,
            audit_sink=_create_test_audit_sink(sink),
            rule_draft_signer=RuleDraftSigner("test-rule-draft-secret"),
        )
    )

    create_response = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={
            "natural_language": "최근 52주 신고가를 돌파했고 거래량이 20일 평균 대비 150% 이상 증가한 종목을 찾아줘.",
            "market": "KR",
            "client_request_id": "client-1",
        },
    )

    assert create_response.status_code == 200
    review = create_response.json()
    assert review["kind"] == "rule_draft"
    assert review["is_executable"] is False
    assert len(review["clarifications"]) <= 3
    assert "최근 52주 신고가" not in create_response.text
    assert store.jobs == {}
    assert sink.sessions == ()


def test_strategy_descriptions_endpoint_returns_strategy_only_copy() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.post(
        STRATEGY_DESCRIPTIONS_PATH,
        json={
            "strategies": [
                {
                    "strategy_id": "semiconductor-momentum",
                    "name": "반도체 모멘텀 + 기관 매수",
                    "timeframe": "daily",
                    "entry_summary": "20일 상대강도 상위권이면서 외국인 순매수가 동반된 종목만 진입 후보로 올립니다.",
                    "exit_summary": "상대강도 둔화 또는 외국인 수급 반전이 확인되면 비중을 축소합니다.",
                    "risk_summary": "실적 발표와 환율 급등 구간에서는 신규 비중 확대를 늦춥니다.",
                    "tags": ["모멘텀", "외국인 수급"],
                }
            ]
        },
    )

    assert response.status_code == 201
    payload = response.json()["items"][0]
    assert payload["strategy_id"] == "semiconductor-momentum"
    assert payload["description"]
    assert "이메일" not in payload["description"]


def test_strategy_descriptions_route_records_per_item_audit_steps() -> None:
    sink = RecordingAuditSink()
    client = TestClient(create_app(InMemoryAnalysisJobStore(), audit_sink=_create_test_audit_sink(sink)))

    response = client.post(
        STRATEGY_DESCRIPTIONS_PATH,
        json={
            "strategies": [
                {
                    "strategy_id": "semiconductor-momentum",
                    "name": "반도체 모멘텀 + 기관 매수",
                    "timeframe": "daily",
                    "entry_summary": "20일 상대강도 상위권이면서 외국인 순매수가 동반된 종목만 진입 후보로 올립니다.",
                    "exit_summary": "상대강도 둔화 또는 외국인 수급 반전이 확인되면 비중을 축소합니다.",
                    "risk_summary": "실적 발표와 환율 급등 구간에서는 신규 비중 확대를 늦춥니다.",
                    "tags": ["모멘텀", "외국인 수급"],
                },
                {
                    "strategy_id": "dividend-defensive",
                    "name": "배당 방어주",
                    "timeframe": "daily",
                    "entry_summary": "배당수익률과 재무안정성이 높은 종목을 찾습니다.",
                    "exit_summary": "배당 컷 또는 추세 훼손 시 비중을 줄입니다.",
                    "risk_summary": "금리 급등 구간에서는 방어력이 약해질 수 있습니다.",
                    "tags": ["배당", "방어"],
                },
            ]
        },
    )

    assert response.status_code == 201
    assert len(response.json()["items"]) == 2
    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert isinstance(session.correlation.db_trace_id, UUID)
    assert session.correlation.trace_id is None
    assert session.correlation.entrypoint == "api.strategy_descriptions"
    assert session.correlation.feature == "strategy_descriptions"
    assert [event.kind for event in session.buffered_events] == ["step", "step", "step", "finalization"]
    assert [event.step for event in session.buffered_events if event.kind == "step"] == [
        "descriptions_started",
        "description_generated",
        "description_generated",
    ]
    assert "strategy_id=semiconductor-momentum" in session.buffered_events[1].message
    assert "strategy_id=dividend-defensive" in session.buffered_events[2].message
    assert session.buffered_events[-1].status == "completed"
    assert len(session.model_calls) == len(session.prompt_logs) == 2
    assert all(call.execution_id is None for call in session.model_calls)


def test_strategy_descriptions_route_records_sanitized_error_audit_events(monkeypatch) -> None:
    sink = RecordingAuditSink()

    def failing_generate_strategy_description(*args, **kwargs):
        raise RuntimeError("description generation exploded with raw request details")

    monkeypatch.setattr("ai_graph.api.generate_strategy_description", failing_generate_strategy_description)
    client = TestClient(create_app(InMemoryAnalysisJobStore(), audit_sink=_create_test_audit_sink(sink)))

    with pytest.raises(RuntimeError, match="description generation exploded with raw request details"):
        client.post(
            STRATEGY_DESCRIPTIONS_PATH,
            json={
                "strategies": [
                    {
                        "strategy_id": "semiconductor-momentum",
                        "name": "반도체 모멘텀 + 기관 매수",
                        "timeframe": "daily",
                        "entry_summary": "20일 상대강도 상위권이면서 외국인 순매수가 동반된 종목만 진입 후보로 올립니다.",
                        "exit_summary": "상대강도 둔화 또는 외국인 수급 반전이 확인되면 비중을 축소합니다.",
                        "risk_summary": "실적 발표와 환율 급등 구간에서는 신규 비중 확대를 늦춥니다.",
                        "tags": ["모멘텀", "외국인 수급"],
                    }
                ]
            },
        )

    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert [event.kind for event in session.buffered_events] == ["step", "error", "finalization"]
    assert [event.step for event in session.buffered_events if event.kind in {"step", "error"}] == [
        "descriptions_started",
        "description_generation",
    ]
    error_event = session.buffered_events[-2]
    assert error_event.error_type == "RuntimeError"
    assert "raw request details" not in error_event.message
    assert session.buffered_events[-1].status == "failed"
def test_retired_daily_digest_returns_gone_without_audit_or_llm(monkeypatch) -> None:
    sink = RecordingAuditSink()

    def llm_path_must_not_run(*_args, **_kwargs) -> None:
        raise AssertionError("retired daily digest route invoked the LLM path")

    monkeypatch.setattr(
        "ai_graph.nodes.daily_digest.generate_daily_digest_overall_comment",
        llm_path_must_not_run,
    )
    client = TestClient(create_app(InMemoryAnalysisJobStore(), audit_sink=_create_test_audit_sink(sink)))

    response = client.post(DAILY_DIGEST_PATH, json={"legacy": "payload"})

    assert response.status_code == 410
    assert response.json()["detail"] == {
        "code": "daily_digest_retired",
        "message": "정기 다이제스트 생성은 현재 제공하지 않습니다.",
    }
    assert sink.sessions == ()


def test_mutable_ai_report_route_is_retired() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.get("/api/reports/backend-report-1")

    assert response.status_code == 410
    assert response.json()["detail"] == {
        "code": "mutable_ai_report_projection_retired",
        "message": "요청형 리포트는 보관된 읽기 전용 스냅샷에서만 제공합니다.",
        "read_only_alternative": "/api/v1/reports",
    }


def test_api_status_marks_retired_report_and_digest_endpoints() -> None:
    status_response = TestClient(create_app(InMemoryAnalysisJobStore())).get(API_STATUS_PATH)

    endpoints = {(entry["method"], entry["path"]): entry for entry in status_response.json()["endpoints"]}
    assert endpoints[("GET", "/api/reports/{report_id}")]["state"] == "retired"
    assert endpoints[("POST", DAILY_DIGEST_PATH)]["state"] == "retired"
def test_spec_resource_adapters_return_failed_envelope_instead_of_404() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    backtest_response = client.get("/api/backtests/missing")
    report_response = client.get("/api/reports/missing")

    assert backtest_response.status_code == 200
    assert backtest_response.json()["status"] == "failed"
    assert report_response.status_code == 410
    assert report_response.json()["detail"]["code"] == "mutable_ai_report_projection_retired"


def test_analysis_job_route_uses_injected_store_and_preserves_polling_contract() -> None:
    class RecordingJobStore(InMemoryAnalysisJobStore):
        def __init__(self) -> None:
            super().__init__()
            self.created_requests: list[str] = []

        def create_job(self, request_text: str, **kwargs) -> object:
            self.created_requests.append(request_text)
            return super().create_job(request_text, **kwargs)

    store = RecordingJobStore()
    client = TestClient(create_app(store, analysis_runner=lambda query, trace_id: _ready_envelope(trace_id)))

    create_response = client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI strategy"})

    assert create_response.status_code == 201
    created_job = create_response.json()
    assert store.created_requests == ["RSI strategy"]
    assert created_job["result"] is None

    polled_job = _poll_job(client, created_job["job_id"])

    assert polled_job["job_id"] == created_job["job_id"]
    assert [stage["stage"] for stage in polled_job["stages"]] == MOCK_PROVIDER_STAGES
    assert all(stage["status"] == "succeeded" for stage in polled_job["stages"])
    assert polled_job["result"]["status"] == "ready"
    assert polled_job["result"]["trace_id"] == created_job["trace_id"]


def test_analysis_job_route_records_audit_events_with_real_runner() -> None:
    sink = RecordingAuditSink()
    client = TestClient(create_app(InMemoryAnalysisJobStore(), audit_sink=_create_test_audit_sink(sink)))

    response = client.post(
        ANALYSIS_JOBS_PATH,
        json={
            "query": "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어",
        },
    )

    assert response.status_code == 201
    created_job = response.json()
    assert created_job["result"] is None
    completed_job = _poll_job(client, created_job["job_id"])

    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert isinstance(session.correlation.db_trace_id, UUID)
    assert session.correlation.db_trace_id.version == 4
    assert session.correlation.trace_id == created_job["trace_id"]
    assert session.correlation.debug_ref is None
    assert session.correlation.entrypoint == "api.analysis_jobs"
    assert session.correlation.feature == "analysis_job"
    assert [event.kind for event in session.buffered_events] == ["step", "step", "step", "finalization"]
    assert [event.step for event in session.buffered_events if event.kind == "step"] == [
        "job_dispatched",
        "analysis_started",
        "analysis_completed",
    ]
    assert session.buffered_events[-1].status == "completed"
    assert completed_job["result"]["trace_id"] == created_job["trace_id"]
    assert "internal_payload" not in completed_job["result"]
    assert len(session.model_calls) == len(session.prompt_logs)
    assert "strategy_conditions" in {call.task_type for call in session.model_calls}
    assert all(call.execution_id is not None for call in session.model_calls)


def test_analysis_audit_session_opens_only_after_job_runner_entry(monkeypatch) -> None:
    sink = RecordingAuditSink()

    def fail_before_runner(*args, **kwargs):
        raise RuntimeError("job store failed before runner")

    monkeypatch.setattr("ai_graph.api.run_job_sync", fail_before_runner)
    client = TestClient(create_app(InMemoryAnalysisJobStore(), audit_sink=_create_test_audit_sink(sink)))

    with pytest.raises(RuntimeError, match="job store failed before runner"):
        client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI strategy"})

    assert sink.sessions == ()


def test_all_ai_entrypoints_keep_business_responses_when_audit_open_fails(
    capsys,
    offline_test_environment: "OfflineTestEnvironment",
) -> None:
    class FailingOpenAuditSink:

        def open_session(self, correlation):
            raise RuntimeError("postgresql://user:secret@db must not leak")

    def client(audit_sink):
        return TestClient(
            create_app(
                InMemoryAnalysisJobStore(),
                analysis_runner=lambda query, trace_id: _ready_envelope(trace_id),
                audit_sink=audit_sink,
                rule_draft_signer=RuleDraftSigner("test-rule-draft-secret"),
            )
        )

    normal = client(NoOpAuditSink())
    broken = client(_create_test_audit_sink(FailingOpenAuditSink()))

    def stable_job_payload(client, response):
        body = response.json()
        # /analysis-jobs queues the run and answers before a result exists.
        if body["result"] is None:
            body = _poll_job(client, body["job_id"])
        result = dict(body["result"])
        result.pop("trace_id")
        result.pop("debug_ref")
        return result, [(stage["stage"], stage["status"]) for stage in body["stages"]]

    job_payloads = [(ANALYSIS_JOBS_PATH, {"query": "RSI strategy"})]
    for path, payload in job_payloads:
        normal_response = normal.post(path, json=payload)
        broken_response = broken.post(path, json=payload)
        assert broken_response.status_code == normal_response.status_code
        assert stable_job_payload(broken, broken_response) == stable_job_payload(
            normal, normal_response
        )

    parse_payload = {"natural_language": "RSI 30 이하, RSI 70 이상"}
    normal_parse = normal.post(SPEC_STRATEGY_PARSE_PATH, json=parse_payload)
    broken_parse = broken.post(SPEC_STRATEGY_PARSE_PATH, json=parse_payload)
    assert normal_parse.status_code == broken_parse.status_code == 200
    assert normal_parse.json()["kind"] == broken_parse.json()["kind"] == "rule_draft"

    descriptions_payload = {
        "strategies": [
            {
                "strategy_id": "rsi",
                "name": "RSI",
                "timeframe": "daily",
                "entry_summary": "RSI 30 이하",
                "exit_summary": "RSI 70 이상",
                "risk_summary": "시장 급락",
                "tags": ["RSI"],
            }
        ]
    }
    normal_response = normal.post(STRATEGY_DESCRIPTIONS_PATH, json=descriptions_payload)
    broken_response = broken.post(STRATEGY_DESCRIPTIONS_PATH, json=descriptions_payload)
    assert broken_response.status_code == normal_response.status_code
    assert broken_response.json() == normal_response.json()

    normal_response = normal.post(DAILY_DIGEST_PATH, json={})
    broken_response = broken.post(DAILY_DIGEST_PATH, json={})
    assert broken_response.status_code == normal_response.status_code == 410
    assert broken_response.json() == normal_response.json()

    stderr = capsys.readouterr().err
    assert stderr.count("ai_audit_failure") == 2
    assert "postgresql://" not in stderr
    assert "secret" not in stderr


def test_parse_strategy_route_does_not_open_an_audit_or_run_analysis() -> None:
    sink = RecordingAuditSink()

    def failing_runner(query: str, trace_id: str) -> APIEnvelope:
        raise RuntimeError(f"runner failed for {query} with {trace_id}")

    client = TestClient(
        create_app(
            InMemoryAnalysisJobStore(),
            analysis_runner=failing_runner,
            audit_sink=_create_test_audit_sink(sink),
            rule_draft_signer=RuleDraftSigner("test-rule-draft-secret"),
        )
    )

    response = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={
            "natural_language": "최근 52주 신고가 돌파 종목을 찾아줘.",
            "strategy_id": "breakout_volume_momentum",
            "client_request_id": "client-parse-1",
        },
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "rule_draft"
    assert sink.sessions == ()


def test_failed_analysis_job_returns_error_contract() -> None:
    def failing_runner(query: str, trace_id: str) -> APIEnvelope:
        raise RuntimeError(f"runner failed for {query} with {trace_id}")

    client = TestClient(create_app(InMemoryAnalysisJobStore(), analysis_runner=failing_runner))

    response = client.post(ANALYSIS_JOBS_PATH, json={"query": "broken strategy"})

    assert response.status_code == 201
    queued_job = response.json()
    assert queued_job["result"] is None

    failed_job = _poll_job(client, queued_job["job_id"])

    assert failed_job["result"]["status"] == "failed"
    assert failed_job["result"]["failure_cause"]["subcause"] == "unknown"
    assert "runner failed" not in failed_job["result"]["user_payload"]["message"]
    assert failed_job["result"]["debug_ref"].startswith("job-error:")
    assert failed_job["stages"][-1]["status"] == "failed"


def test_database_connection_failure_has_a_safe_retryable_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PostgreSQL connection error must not degrade into ``unknown`` for the UI."""

    monkeypatch.setenv("AUTH_ENABLED", "0")

    def failing_runner(_query: str, _trace_id: str) -> APIEnvelope:
        raise OperationalError("password=must-not-leak connection refused")

    client = TestClient(
        create_app(InMemoryAnalysisJobStore(), analysis_runner=failing_runner)
    )
    response = client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI 30 이하 조건"})

    assert response.status_code == 201
    failed_job = _poll_job(client, response.json()["job_id"])
    result = failed_job["result"]
    public = repr(result)
    assert result["status"] == "failed"
    assert result["retryable"] is True
    assert result["failure_cause"] == {
        "category": "infrastructure_failure",
        "subcause": "db_connection_unavailable",
        "failure_stage": "interpreting",
        "owner": "data_source_config",
        "retryable": True,
        "safe_message": "운영 데이터 소스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        "evidence_refs": ["failure:db_connection_unavailable"],
    }
    assert result["strategy_spec"] is None
    assert result["user_payload"]["candidate_cards"] == []
    assert result["user_payload"]["performance"] is None
    assert result["user_payload"]["report"] is None
    assert "must-not-leak" not in public


def test_unknown_analysis_job_returns_404() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.get(f"{ANALYSIS_JOBS_PATH}/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "analysis job not found"}


def _other_users_job(store: InMemoryAnalysisJobStore):
    """A job belonging to someone other than the authenticated caller."""

    return store.create_job("다른 사용자의 RSI 전략", user_id="someone-else")


def test_another_users_analysis_job_is_not_readable() -> None:
    """RMP-JOB-01: reads are owner-only, and a stranger cannot even confirm it exists.

    404 rather than 403 on purpose. 403 would answer "this job exists but is not yours",
    which turns job ids into an enumerable directory of other people's activity.
    """

    store = InMemoryAnalysisJobStore()
    client = TestClient(create_app(store))
    job = _other_users_job(store)

    response = client.get(ANALYSIS_JOB_DETAIL_PATH.format(job_id=job.job_id))

    assert response.status_code == 404
    assert "someone-else" not in response.text


def test_another_users_analysis_job_cannot_be_cancelled() -> None:
    """Cancel is a write, so owner-only matters more here than on the read path.

    Checking the status afterwards is the part that counts: a 404 that still signalled
    the cancellation would stop a stranger's run while reporting that nothing happened.
    """

    store = InMemoryAnalysisJobStore()
    client = TestClient(create_app(store))
    job = _other_users_job(store)

    response = client.post(ANALYSIS_JOB_CANCEL_PATH.format(job_id=job.job_id))

    assert response.status_code == 404
    still_there = store.get_job(job.job_id)
    assert still_there is not None
    assert still_there.status is not AnalysisJobStatus.FAILED


def test_a_job_id_that_does_not_exist_is_indistinguishable_from_someone_elses() -> None:
    """The two must answer identically, or the difference itself is the disclosure."""

    store = InMemoryAnalysisJobStore()
    client = TestClient(create_app(store))
    owned_by_other = _other_users_job(store)

    missing = client.get(ANALYSIS_JOB_DETAIL_PATH.format(job_id="no-such-job"))
    foreign = client.get(ANALYSIS_JOB_DETAIL_PATH.format(job_id=owned_by_other.job_id))

    assert missing.status_code == foreign.status_code == 404
    assert missing.json() == foreign.json()


def _analysis_job_create_status(client: TestClient) -> str:
    inventory = client.get(API_STATUS_PATH).json()["endpoints"]
    entry = next(
        item
        for item in inventory
        if item["method"] == "POST" and item["path"] == ANALYSIS_JOBS_PATH
    )
    return entry["state"]


def test_the_endpoint_inventory_advertises_core_execution_and_unready_release_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The inventory must describe the core route and its fail-closed release mode."""

    monkeypatch.setenv("APP_ENV", "production")
    release_client = TestClient(create_app(InMemoryAnalysisJobStore()))

    assert _analysis_job_create_status(release_client) == "job_async"
    response = release_client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI 30 이하 종목"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "analysis_execution_unavailable"

    monkeypatch.delenv("APP_ENV", raising=False)
    live_client = TestClient(create_app(InMemoryAnalysisJobStore()))

    assert _analysis_job_create_status(live_client) == "job_async"
    assert live_client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI 30 이하 종목"}).status_code == 201


def test_the_inventory_summary_describes_core_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The state word is machine-readable; the summary is what a person reads."""

    monkeypatch.setenv("APP_ENV", "production")
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    inventory = client.get(API_STATUS_PATH).json()["endpoints"]
    entry = next(
        item
        for item in inventory
        if item["method"] == "POST" and item["path"] == ANALYSIS_JOBS_PATH
    )

    assert entry["state"] == "job_async"
    assert "Parse natural-language input on the server" in entry["summary"]
    assert "queue an authenticated analysis job" in entry["summary"]
