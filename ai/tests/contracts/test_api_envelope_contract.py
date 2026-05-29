from fastapi.testclient import TestClient

from ai_graph.api import ANALYSIS_JOBS_PATH, create_app
from ai_graph.jobs import InMemoryAnalysisJobStore


QUERY = "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어"

ANALYSIS_JOB_FIELDS = {
    "job_id",
    "trace_id",
    "query",
    "created_at",
    "updated_at",
    "stages",
    "result",
}
STAGE_FIELDS = {"stage", "status", "updated_at", "message"}
API_ENVELOPE_FIELDS = {
    "status",
    "trace_id",
    "schema_version",
    "user_payload",
    "strategy_spec",
    "debug_ref",
    "retryable",
}
USER_PAYLOAD_FIELDS = {
    "headline",
    "message",
    "next_actions",
    "candidate_cards",
    "report",
    "performance",
    "question",
    "options",
    "recommended",
}
REPORT_FIELDS = {"web_projection", "email_projection", "risk_adjustments"}
PROJECTION_FIELDS = {"title", "summary", "sections"}


def test_analysis_job_and_api_envelope_public_fields_are_frozen() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.post(ANALYSIS_JOBS_PATH, json={"query": QUERY})

    assert response.status_code == 201
    job = response.json()
    result = job["result"]
    user_payload = result["user_payload"]
    report = user_payload["report"]

    assert set(job) == ANALYSIS_JOB_FIELDS
    assert set(job["stages"][0]) == STAGE_FIELDS
    assert set(result) == API_ENVELOPE_FIELDS
    assert set(user_payload) == USER_PAYLOAD_FIELDS
    assert user_payload["performance"]["selected_candidate_id"]
    assert set(user_payload["performance"]["metrics_by_variant"]) == {"A", "B"}
    assert set(report) == REPORT_FIELDS
    assert set(report["web_projection"]) == PROJECTION_FIELDS
    assert set(report["email_projection"]) == PROJECTION_FIELDS


def test_public_envelope_keeps_debug_ref_but_excludes_internal_payload() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.post(ANALYSIS_JOBS_PATH, json={"query": QUERY})

    result = response.json()["result"]
    assert result["debug_ref"]
    assert "internal_payload" not in result
    assert "node_outputs" not in result
    assert "llm_prompts" not in result
