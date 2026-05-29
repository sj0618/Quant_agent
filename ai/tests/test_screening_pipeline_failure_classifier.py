from __future__ import annotations

from ai_graph.jobs import InMemoryAnalysisJobStore, run_job_sync
from ai_graph.schemas import APIEnvelope, EnvelopeStatus

from screening_pipeline_test_support import FAILURE_CATEGORIES, FAILURE_FIELDS


def test_failure_parent_category_and_subcause_shape() -> None:
    failure = {
        "failure_category": "infrastructure_failure",
        "failure_subcause": "db_connect_timeout",
        "failure_stage": "data_source",
        "failure_owner": "data_source_config",
        "retryable": True,
        "evidence_refs": ["debug:job-error"],
    }

    assert set(failure) == FAILURE_FIELDS
    assert failure["failure_category"] in FAILURE_CATEGORIES
    assert failure["failure_subcause"].endswith("timeout")


def test_raw_connection_timeout_failure_is_flagged_as_public_safety_gap() -> None:
    store = InMemoryAnalysisJobStore()
    job = store.create_job("RSI 조건을 분석해줘")

    def timeout_runner(_query: str, _trace_id: str) -> APIEnvelope:
        raise TimeoutError("connection timeout expired")

    failed_job = run_job_sync(store, job.job_id, timeout_runner)
    assert failed_job.result is not None
    message = failed_job.result.user_payload.message
    qa_verdict = {
        "verdict": "fail" if "connection timeout expired" in message else "pass",
        "failure_cause": "db_connect_timeout",
        "failure_category": "infrastructure_failure",
        "failure_stage": "finalizing",
        "failure_owner": "data_source_config",
        "evidence_refs": [failed_job.result.debug_ref],
    }

    assert failed_job.result.status == EnvelopeStatus.FAILED
    assert qa_verdict["verdict"] == "fail"
    assert qa_verdict["failure_cause"] == "db_connect_timeout"
    assert qa_verdict["evidence_refs"] == [f"job-error:{job.job_id}"]
