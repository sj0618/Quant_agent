import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_graph.api import ANALYSIS_JOBS_PATH, create_app
from ai_graph.jobs import InMemoryAnalysisJobStore
from ai_graph.research_contract import CanonicalRuleV1, canonical_rule_digest
from ai_graph.schemas import (
    APIEnvelope,
    canonical_execution_spec_digest,
    EnvelopeStatus,
    FailureDiagnostic,
    Stage,
    StrategyExecutionSpecV1,
    UserPayload,
)

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
    "execution_spec",
    "execution_spec_version",
    "execution_spec_hash",
    "debug_ref",
    "retryable",
    "semantic_slots",
    "data_requirements",
    "source_usage",
    "freshness_status",
    "freshness_evidence",
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
    assert set(result["freshness_evidence"]) == {
        "status",
        "as_of",
        "reason",
        "source",
        "no_recommendation",
    }
    assert set(user_payload) == USER_PAYLOAD_FIELDS
    performance = user_payload["performance"]
    assert performance["availability"] in {"available", "unavailable"}
    if performance["availability"] == "available":
        public = performance["performance"]
        assert public["selected_candidate_id"]
        assert "metrics" in public
        assert "equity_curve" in public
        assert "engine_summary" not in public
        assert "metrics_by_variant" not in public
        assert performance["method_manifest"]["evaluated_rule"]
    else:
        assert "performance" not in performance
        assert "metrics" not in performance
        assert "equity_curve" not in performance
        assert performance["reason_code"]
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


def _execution_spec() -> StrategyExecutionSpecV1:
    return StrategyExecutionSpecV1.model_validate(
        {
            "market": "KRX",
            "timeframe": "daily",
            "entry_conditions": [
                {"metric": "rsi", "comparator": "lte", "value": 30, "role": "entry"}
            ],
            "exit_conditions": [
                {"metric": "rsi", "comparator": "gte", "value": 70, "role": "exit"}
            ],
        }
    )


def _public_envelope(**overrides) -> APIEnvelope:
    values = {
        "status": EnvelopeStatus.READY,
        "trace_id": "contract-trace",
        "debug_ref": "contract-debug",
        "retryable": False,
        "user_payload": UserPayload(headline="완료", message="완료"),
    }
    values.update(overrides)
    return APIEnvelope(**values)


def test_public_execution_contract_requires_a_complete_versioned_hash_binding() -> None:
    spec = _execution_spec()
    envelope = _public_envelope(
        execution_spec=spec,
        execution_spec_version="strategy-execution-spec.v1",
        execution_spec_hash=canonical_execution_spec_digest(spec),
    )

    assert envelope.execution_spec == spec
    assert envelope.execution_spec_version == "strategy-execution-spec.v1"
    assert envelope.execution_spec_hash == canonical_execution_spec_digest(spec)

    with pytest.raises(ValidationError, match="execution spec, version, and hash"):
        _public_envelope(execution_spec=spec)

    with pytest.raises(ValidationError, match="canonical execution spec"):
        _public_envelope(
            execution_spec=spec,
            execution_spec_version="strategy-execution-spec.v1",
            execution_spec_hash="a" * 64,
        )


def test_execution_envelope_hash_matches_the_parse_issued_spec_hash() -> None:
    spec = _execution_spec()
    parse_rule = CanonicalRuleV1.model_validate(spec.model_dump(mode="json"))

    assert canonical_execution_spec_digest(spec) == canonical_rule_digest(parse_rule)


def test_public_terminal_contract_keeps_typed_failure_on_failed_envelopes_only() -> None:
    diagnostic = FailureDiagnostic(
        category="infrastructure_failure",
        subcause="aoai_response_timeout",
        failure_stage=Stage.INTERPRETING,
        owner="ai_graph",
        retryable=True,
        safe_message="응답 시간이 초과되었습니다.",
    )

    failed = _public_envelope(status=EnvelopeStatus.FAILED, retryable=True, failure_cause=diagnostic)
    assert failed.failure_cause == diagnostic

    with pytest.raises(ValidationError, match="only failed envelopes"):
        _public_envelope(failure_cause=diagnostic)


def test_failed_envelope_requires_a_typed_diagnostic() -> None:
    with pytest.raises(ValidationError, match="failed envelopes require"):
        _public_envelope(status=EnvelopeStatus.FAILED, retryable=False)


def test_failure_stage_is_closed_to_public_pipeline_stages() -> None:
    with pytest.raises(ValidationError, match="failure_stage"):
        FailureDiagnostic.model_validate(
            {
                "category": "infrastructure_failure",
                "subcause": "aoai_response_timeout",
                "failure_stage": "provider stack trace",
                "owner": "ai_graph",
                "retryable": True,
                "safe_message": "응답 시간이 초과되었습니다.",
            }
        )
