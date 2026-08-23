from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from offline_test_environment import OfflineTestEnvironment

from ai_graph.api import (
    AI_CORS_ALLOW_ORIGINS_ENV,
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
from ai_graph.jobs import InMemoryAnalysisJobStore, JobStoreConfigurationError, JobStoreRuntime
from ai_graph.research_contract import RuleDraftSigner
from ai_graph.schemas import APIEnvelope, EnvelopeStatus, UserPayload

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
    assert ready_client.get(READINESS_PATH).status_code == 200

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


def test_unknown_analysis_job_returns_404() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.get(f"{ANALYSIS_JOBS_PATH}/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "analysis job not found"}
