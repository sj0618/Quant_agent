from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from ai_graph.api import (
    AI_CORS_ALLOW_ORIGINS_ENV,
    ANALYSIS_JOB_DETAIL_PATH,
    ANALYSIS_JOBS_PATH,
    API_STATUS_PATH,
    DAILY_DIGEST_PATH,
    DOCS_URL,
    HEALTH_PATH,
    OPENAPI_URL,
    SPEC_STRATEGY_PARSE_PATH,
    STRATEGY_DESCRIPTIONS_PATH,
    create_app,
)
from ai_graph.audit import NoOpAuditSink, RecordingAuditSink
from ai_graph.audit_postgres import _create_test_audit_sink
from ai_graph.jobs import InMemoryAnalysisJobStore
from ai_graph.schemas import APIEnvelope, EnvelopeStatus, UserPayload

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

def _daily_digest_strategy_payload(
    strategy_id: str,
    name: str,
    signal: str,
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "name": name,
        "timeframe": "1d",
        "today_signal": signal,
        "targets": ["삼성전자"],
        "metrics": {
            "sharpe_ratio": 1.12,
            "max_drawdown": -0.06,
            "win_rate": 0.58,
            "total_return": 0.14,
            "in_sample_sharpe": 1.12,
            "out_sample_sharpe": 1.12,
            "degradation": 0.0,
        },
        "win_rate": 0.583,
        "trade_count": 24,
    }


def test_swagger_openapi_lists_current_api_surface() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    docs_response = client.get(DOCS_URL)
    assert docs_response.status_code == 200
    assert "SwaggerUIBundle" in docs_response.text

    schema_response = client.get(OPENAPI_URL)
    assert schema_response.status_code == 200
    paths = schema_response.json()["paths"]

    assert HEALTH_PATH in paths
    assert API_STATUS_PATH in paths
    assert ANALYSIS_JOBS_PATH in paths
    assert ANALYSIS_JOB_DETAIL_PATH in paths
    assert SPEC_STRATEGY_PARSE_PATH in paths
    assert STRATEGY_DESCRIPTIONS_PATH in paths
    assert DAILY_DIGEST_PATH in paths
    assert "/api/analysis-jobs/{job_id}" in paths
    assert "/api/backtests/{strategy_id}" in paths
    assert "/api/reports/{report_id}" in paths


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


def test_api_status_reports_persistent_job_store_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AI_JOB_STORE", "persistent")
    monkeypatch.delenv("AI_DATABASE_DSN", raising=False)
    client = TestClient(create_app())

    response = client.get(API_STATUS_PATH)

    assert response.status_code == 200
    job_store = response.json()["job_store"]
    assert job_store["requested_mode"] == "persistent"
    assert job_store["active_mode"] == "memory"
    assert job_store["fallback"] is True
    assert "AI_DATABASE_DSN" in job_store["fallback_reason"]


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
    assert performance["selected_candidate_id"]
    assert "metrics_by_variant" not in performance
    assert "selected_variant" not in performance
    assert performance["metrics"]["total_return"] > 0
    assert performance["equity_curve"][-1]["cumulative_return"] > 0


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
    assert performance["selected_candidate_id"]
    assert "metrics_by_variant" not in performance
    assert "selected_variant" not in performance
    assert performance["metrics"]["total_return"] > 0
    assert performance["equity_curve"][-1]["cumulative_return"] > 0

    poll_response = client.get(f"{ANALYSIS_JOBS_PATH}/{created_job['job_id']}")
    assert poll_response.status_code == 200
    polled_job = poll_response.json()
    assert polled_job["job_id"] == created_job["job_id"]
    assert polled_job["trace_id"] == created_job["trace_id"]
    assert polled_job["result"] == created_result
    assert polled_job["result"]["status"] == "ready"

    assert MOCK_PROVIDER_CREDENTIAL_SENTINEL not in create_response.text
    assert MOCK_PROVIDER_CREDENTIAL_SENTINEL not in poll_response.text

    # An asset class outside KRX cash equities is the one input that still comes back
    # without a result; an underspecified stock request no longer does.
    rejected_response = client.post(ANALYSIS_JOBS_PATH, json={"query": "옵션 양매도 전략 만들어줘"})
    assert rejected_response.status_code == 201
    rejected_job = _poll_job(client, rejected_response.json()["job_id"])
    rejected_result = rejected_job["result"]
    rejected_payload = rejected_result["user_payload"]

    assert rejected_result["status"] == "rejected"
    assert rejected_payload["question"]
    assert len(rejected_payload["candidate_cards"]) == 3
    assert len(rejected_payload["options"]) == 3
    assert rejected_payload["report"] is None
    assert rejected_payload["performance"] is None

    rejected_poll = client.get(f"{ANALYSIS_JOBS_PATH}/{rejected_job['job_id']}")
    assert rejected_poll.status_code == 200
    rejected_polled = rejected_poll.json()
    assert rejected_polled["job_id"] == rejected_job["job_id"]
    assert rejected_polled["trace_id"] == rejected_job["trace_id"]
    assert rejected_polled["result"] == rejected_result
    assert rejected_polled["result"]["status"] == "rejected"

    assert MOCK_PROVIDER_CREDENTIAL_SENTINEL not in rejected_response.text
    assert MOCK_PROVIDER_CREDENTIAL_SENTINEL not in rejected_poll.text

def test_spec_strategy_parse_accepts_natural_language_and_supports_resource_adapters() -> None:
    store = InMemoryAnalysisJobStore()
    sink = RecordingAuditSink()
    client = TestClient(create_app(store, audit_sink=_create_test_audit_sink(sink)))

    create_response = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={
            "natural_language": "최근 52주 신고가를 돌파했고 거래량이 20일 평균 대비 150% 이상 증가한 종목을 찾아줘.",
            "market": "KR",
            "client_request_id": "client-1",
        },
    )

    assert create_response.status_code == 201
    created_job = create_response.json()
    assert created_job["result"]["status"] == "ready"

    poll_response = client.get(f"/api/analysis-jobs/{created_job['job_id']}")
    assert poll_response.status_code == 200
    assert poll_response.json()["job_id"] == created_job["job_id"]

    backtest_response = client.get("/api/backtests/breakout_volume_momentum")
    assert backtest_response.status_code == 200
    assert backtest_response.json()["status"] == "ready"
    assert backtest_response.json()["user_payload"]["performance"]["selected_candidate_id"]

    stored_job = store.get_job(created_job["job_id"])
    assert stored_job is not None
    assert stored_job.report_id is not None

    report_response = client.get(f"/api/reports/{stored_job.report_id}")
    assert report_response.status_code == 200
    assert report_response.json()["status"] == "ready"
    assert report_response.json()["user_payload"]["report"]["web_projection"]["sections"]

    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert len(session.model_calls) == len(session.prompt_logs)
    assert "strategy_conditions" in {call.task_type for call in session.model_calls}
    assert all(call.execution_id is not None for call in session.model_calls)


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
def test_daily_digest_route_records_success_audit_steps() -> None:
    sink = RecordingAuditSink()
    client = TestClient(create_app(InMemoryAnalysisJobStore(), audit_sink=_create_test_audit_sink(sink)))

    response = client.post(
        DAILY_DIGEST_PATH,
        json={
            "user_name": "홍길동",
            "report_date": "2026-06-29",
            "strategies": [
                _daily_digest_strategy_payload("rsi", "RSI 전략", "BUY"),
                _daily_digest_strategy_payload("macd", "MACD 전략", "HOLD"),
            ],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["header"]["strategy_count"] == 2
    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert isinstance(session.correlation.db_trace_id, UUID)
    assert session.correlation.trace_id is None
    assert session.correlation.entrypoint == "api.daily_digest"
    assert session.correlation.feature == "daily_digest"
    assert [event.kind for event in session.buffered_events] == ["step", "step", "step", "step", "finalization"]
    assert [event.step for event in session.buffered_events if event.kind == "step"] == [
        "daily_digest_started",
        "daily_digest_card_ready",
        "daily_digest_card_ready",
        "daily_digest_market_brief",
    ]
    assert "strategy_id=rsi" in session.buffered_events[1].message
    assert "strategy_id=macd" in session.buffered_events[2].message
    assert session.buffered_events[-1].status == "completed"
    assert len(session.model_calls) == len(session.prompt_logs) == 4
    assert all(call.execution_id is None for call in session.model_calls)


def test_report_route_uses_injected_report_resolver_for_real_report_ids() -> None:
    resolved_ids: list[str] = []

    def report_resolver(report_id: str) -> APIEnvelope | None:
        resolved_ids.append(report_id)
        return APIEnvelope(
            status=EnvelopeStatus.READY,
            trace_id="trace-report-resolver",
            user_payload=UserPayload(
                headline="ready",
                message="report resolved",
                next_actions=[],
                report={
                    "web_projection": {"title": "웹", "summary": "요약", "sections": []},
                    "email_projection": {"title": "메일", "summary": "요약", "sections": []},
                    "risk_adjustments": [],
                },
            ),
            strategy_spec=None,
            debug_ref="debug:trace-report-resolver",
            retryable=False,
        )

    client = TestClient(create_app(InMemoryAnalysisJobStore(), report_resolver=report_resolver))

    response = client.get("/api/reports/backend-report-1")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["user_payload"]["report"]["web_projection"]["title"] == "웹"
    assert resolved_ids == ["backend-report-1"]
def test_daily_digest_route_records_sanitized_error_audit_events(monkeypatch) -> None:
    sink = RecordingAuditSink()

    def failing_build_daily_digest(*args, **kwargs):
        raise ValueError("daily digest exploded with raw request details")

    monkeypatch.setattr("ai_graph.api.build_daily_digest", failing_build_daily_digest)
    client = TestClient(create_app(InMemoryAnalysisJobStore(), audit_sink=_create_test_audit_sink(sink)))

    response = client.post(
        DAILY_DIGEST_PATH,
        json={
            "user_name": "홍길동",
            "report_date": "2026-06-29",
            "strategies": [_daily_digest_strategy_payload("rsi", "RSI 전략", "BUY")],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "daily digest exploded with raw request details"
    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert [event.kind for event in session.buffered_events] == ["step", "error", "finalization"]
    assert [event.step for event in session.buffered_events if event.kind in {"step", "error"}] == [
        "daily_digest_started",
        "daily_digest_validation",
    ]
    error_event = session.buffered_events[-2]
    assert error_event.error_type == "ValueError"
    assert "raw request details" not in error_event.message
    assert session.buffered_events[-1].status == "failed"
def test_spec_resource_adapters_return_failed_envelope_instead_of_404() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    backtest_response = client.get("/api/backtests/missing")
    report_response = client.get("/api/reports/missing")

    assert backtest_response.status_code == 200
    assert backtest_response.json()["status"] == "failed"
    assert report_response.status_code == 200
    assert report_response.json()["status"] == "failed"


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


def test_all_ai_entrypoints_keep_business_responses_when_audit_open_fails(capsys) -> None:
    class FailingOpenAuditSink:

        def open_session(self, correlation):
            raise RuntimeError("postgresql://user:secret@db must not leak")

    def client(audit_sink):
        return TestClient(
            create_app(
                InMemoryAnalysisJobStore(),
                analysis_runner=lambda query, trace_id: _ready_envelope(trace_id),
                audit_sink=audit_sink,
            )
        )

    normal = client(NoOpAuditSink())
    broken = client(_create_test_audit_sink(FailingOpenAuditSink()))

    def stable_job_payload(client, response):
        body = response.json()
        # /analysis-jobs queues the run and answers before a result exists; the spec
        # parse adapter still resolves synchronously.
        if body["result"] is None:
            body = _poll_job(client, body["job_id"])
        result = dict(body["result"])
        result.pop("trace_id")
        result.pop("debug_ref")
        return result, [(stage["stage"], stage["status"]) for stage in body["stages"]]

    job_payloads = [
        (ANALYSIS_JOBS_PATH, {"query": "RSI strategy"}),
        (
            SPEC_STRATEGY_PARSE_PATH,
            {
                "natural_language": "RSI strategy",
                "strategy_id": "rsi",
                "client_request_id": "request-1",
            },
        ),
    ]
    for path, payload in job_payloads:
        normal_response = normal.post(path, json=payload)
        broken_response = broken.post(path, json=payload)
        assert broken_response.status_code == normal_response.status_code
        assert stable_job_payload(broken, broken_response) == stable_job_payload(
            normal, normal_response
        )

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

    digest_payload = {
        "user_name": "홍길동",
        "report_date": "2026-07-13",
        "strategies": [_daily_digest_strategy_payload("rsi", "RSI", "BUY")],
    }
    normal_response = normal.post(DAILY_DIGEST_PATH, json=digest_payload)
    broken_response = broken.post(DAILY_DIGEST_PATH, json=digest_payload)
    assert broken_response.status_code == normal_response.status_code
    assert broken_response.json() == normal_response.json()

    stderr = capsys.readouterr().err
    assert stderr.count("ai_audit_failure") == 4
    assert "postgresql://" not in stderr
    assert "secret" not in stderr


def test_parse_strategy_route_records_failure_audit_events_with_request_metadata() -> None:
    sink = RecordingAuditSink()

    def failing_runner(query: str, trace_id: str) -> APIEnvelope:
        raise RuntimeError(f"runner failed for {query} with {trace_id}")

    client = TestClient(
        create_app(
            InMemoryAnalysisJobStore(),
            analysis_runner=failing_runner,
            audit_sink=_create_test_audit_sink(sink),
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

    assert response.status_code == 201
    failed_job = response.json()
    assert failed_job["result"]["status"] == "failed"
    assert failed_job["result"]["debug_ref"].startswith("job-error:")
    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert isinstance(session.correlation.db_trace_id, UUID)
    assert session.correlation.trace_id == failed_job["trace_id"]
    assert session.correlation.entrypoint == "api.strategy_parse"
    assert session.correlation.feature == "strategy_parse"
    assert session.correlation.strategy_id == "breakout_volume_momentum"
    assert session.correlation.client_request_id == "client-parse-1"
    assert [event.kind for event in session.buffered_events] == ["step", "step", "error", "finalization"]
    assert [event.step for event in session.buffered_events if event.kind in {"step", "error"}] == [
        "job_dispatched",
        "analysis_started",
        "analysis_execution",
    ]
    error_event = session.buffered_events[-2]
    assert error_event.error_type == "RuntimeError"
    assert "runner failed" not in error_event.message
    assert session.buffered_events[-1].status == "failed"
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
