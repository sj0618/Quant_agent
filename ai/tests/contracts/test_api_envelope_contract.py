import pytest
from fastapi.testclient import TestClient

from ai_graph.api import ANALYSIS_JOBS_PATH, create_app
from ai_graph.jobs import InMemoryAnalysisJobStore

pytest_plugins = ("offline_test_environment",)
pytestmark = pytest.mark.usefixtures("offline_test_environment")


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
    "semantic_slots",
    "data_requirements",
    "source_usage",
    "freshness_status",
    "proxy_disclosure",
    "failure_cause",
    "evidence_refs",
    # Added deliberately: the backtest's own statement of which rule it traded. Without
    # it a report where the user's conditions were silently replaced by a generic
    # template is byte-identical to one where they were actually tested.
    "rule_provenance",
}
USER_PAYLOAD_FIELDS = {
    "headline",
    "message",
    "next_actions",
    "candidate_cards",
    "report",
    "performance",
    "recommendation_gate",
    "ticker_actions",
    "question",
    "options",
    "recommended",
}
REPORT_FIELDS = {"web_projection", "email_projection", "risk_adjustments"}
PROJECTION_FIELDS = {"title", "summary", "sections"}


def _create_and_poll_job(client) -> dict:
    """POST queues the analysis, so the envelope is read back through polling."""

    response = client.post(ANALYSIS_JOBS_PATH, json={"query": QUERY})
    assert response.status_code == 201
    polled = client.get(f"{ANALYSIS_JOBS_PATH}/{response.json()['job_id']}")
    assert polled.status_code == 200
    return polled.json()


def test_analysis_job_and_api_envelope_public_fields_are_frozen() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    job = _create_and_poll_job(client)

    result = job["result"]
    user_payload = result["user_payload"]
    report = user_payload["report"]

    assert set(job) == ANALYSIS_JOB_FIELDS
    assert set(job["stages"][0]) == STAGE_FIELDS
    assert set(result) == API_ENVELOPE_FIELDS
    assert result["semantic_slots"]["indicator"]
    assert result["data_requirements"]
    assert result["source_usage"]
    assert all(source["fallback_used"] for source in result["source_usage"])
    assert result["evidence_refs"]
    assert set(user_payload) == USER_PAYLOAD_FIELDS
    assert user_payload["performance"]["selected_candidate_id"]
    assert "metrics" in user_payload["performance"]
    assert "equity_curve" in user_payload["performance"]
    assert "metrics_by_variant" not in user_payload["performance"]
    assert set(report) == REPORT_FIELDS
    assert set(report["web_projection"]) == PROJECTION_FIELDS
    assert set(report["email_projection"]) == PROJECTION_FIELDS


def test_public_envelope_keeps_debug_ref_but_excludes_internal_payload() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    result = _create_and_poll_job(client)["result"]

    assert result["debug_ref"]
    assert "internal_payload" not in result
    assert "node_outputs" not in result
    assert "llm_prompts" not in result
