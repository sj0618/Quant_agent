from fastapi.testclient import TestClient

from ai_graph.api import (
    AI_CORS_ALLOW_ORIGINS_ENV,
    ANALYSIS_JOB_DETAIL_PATH,
    ANALYSIS_JOBS_PATH,
    API_STATUS_PATH,
    DOCS_URL,
    HEALTH_PATH,
    OPENAPI_URL,
    SPEC_STRATEGY_PARSE_PATH,
    create_app,
)
from ai_graph.jobs import InMemoryAnalysisJobStore
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
    assert created_job["result"]["status"] == "ready"
    assert "internal_payload" not in created_job["result"]
    assert {stage["status"] for stage in created_job["stages"]} == {"succeeded"}
    performance = created_job["result"]["user_payload"]["performance"]
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


def test_spec_strategy_parse_accepts_natural_language_and_supports_resource_adapters() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    create_response = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={
            "natural_language": "최근 52주 신고가를 돌파했고 거래량이 20일 평균 대비 150% 이상 증가한 종목을 찾아줘.",
            "market": "KR",
            "universe": "KOSPI200",
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

    report_response = client.get(f"/api/reports/{created_job['job_id']}")
    assert report_response.status_code == 200
    assert report_response.json()["status"] == "ready"
    assert report_response.json()["user_payload"]["report"]["web_projection"]["sections"]


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
    assert [stage["stage"] for stage in created_job["stages"]] == [stage.value for stage in Stage]
    assert {stage["status"] for stage in created_job["stages"]} == {"succeeded"}
    assert created_job["result"]["status"] == "ready"
    assert created_job["result"]["trace_id"] == created_job["trace_id"]

    poll_response = client.get(f"{ANALYSIS_JOBS_PATH}/{created_job['job_id']}")

    assert poll_response.status_code == 200
    assert poll_response.json()["job_id"] == created_job["job_id"]


def test_failed_analysis_job_returns_error_contract() -> None:
    def failing_runner(query: str, trace_id: str) -> APIEnvelope:
        raise RuntimeError(f"runner failed for {query} with {trace_id}")

    client = TestClient(create_app(InMemoryAnalysisJobStore(), analysis_runner=failing_runner))

    response = client.post(ANALYSIS_JOBS_PATH, json={"query": "broken strategy"})

    assert response.status_code == 201
    failed_job = response.json()
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
