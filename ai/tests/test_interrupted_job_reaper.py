"""A restart must not leave analysis jobs saying RUNNING forever."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_graph.api import create_app
from ai_graph.jobs import (
    INTERRUPTED_BY_RESTART_REASON,
    PROCESS_INCARNATION,
    AnalysisJobStatus,
    InMemoryAnalysisJobStore,
    InterruptedJobReconciliationError,
    Stage,
    reap_interrupted_jobs,
)
from ai_graph.schemas import EnvelopeStatus

# What a restart looks like from the store's side: the rows are there, the process that
# was working on them is not.
OTHER_PROCESS = "9999:deadbeefcafe"


def _store_with_running_job() -> tuple[InMemoryAnalysisJobStore, str]:
    store = InMemoryAnalysisJobStore()
    job = store.create_job("RSI 30 이하 매수 전략을 검토해 주세요")
    store.update_job_status(job.job_id, AnalysisJobStatus.RUNNING, Stage.INTERPRETING)
    return store, job.job_id


def test_a_job_left_running_by_a_dead_process_is_failed() -> None:
    store, job_id = _store_with_running_job()

    reaped = reap_interrupted_jobs(store, incarnation=OTHER_PROCESS)

    assert reaped == [job_id]
    job = store.get_job(job_id)
    assert job is not None
    assert job.status is AnalysisJobStatus.FAILED
    assert job.completed_at is not None
    assert INTERRUPTED_BY_RESTART_REASON in job.fallback_reasons
    # The client polls the envelope, so the failure has to be visible there too.
    assert job.result is not None
    assert job.result.status is EnvelopeStatus.FAILED


def test_a_queued_job_is_reaped_too() -> None:
    """Queued work lives in this process's background tasks; a dead process never runs it."""

    store = InMemoryAnalysisJobStore()
    job = store.create_job("이동평균 교차 전략을 검토해 주세요")
    assert job.status is AnalysisJobStatus.QUEUED

    assert reap_interrupted_jobs(store, incarnation=OTHER_PROCESS) == [job.job_id]


def test_this_process_does_not_reap_its_own_running_jobs() -> None:
    """The sweep must not kill live work - that would be worse than the bug it fixes."""

    store, job_id = _store_with_running_job()

    assert reap_interrupted_jobs(store, incarnation=PROCESS_INCARNATION) == []
    job = store.get_job(job_id)
    assert job is not None
    assert job.status is AnalysisJobStatus.RUNNING


def test_settled_jobs_are_left_alone() -> None:
    store = InMemoryAnalysisJobStore()
    completed = store.create_job("완료된 전략")
    store.complete_job(completed.job_id, _ready_envelope(completed.trace_id))
    failed = store.create_job("실패한 전략")
    store.fail_job(failed.job_id, "provider unavailable")

    assert reap_interrupted_jobs(store, incarnation=OTHER_PROCESS) == []
    assert store.get_job(failed.job_id).error_message == "provider unavailable"


def test_a_job_with_no_recorded_incarnation_is_reaped() -> None:
    """Rows written before this field existed came from an earlier process by definition."""

    store, job_id = _store_with_running_job()
    store.jobs[job_id] = store.jobs[job_id].model_copy(update={"owner_incarnation": None})

    assert reap_interrupted_jobs(store, incarnation=PROCESS_INCARNATION) == [job_id]


def test_one_unreapable_job_fails_the_reconciliation() -> None:
    store, first = _store_with_running_job()
    second = store.create_job("두 번째 전략")
    store.update_job_status(second.job_id, AnalysisJobStatus.RUNNING, Stage.INTERPRETING)

    original_fail = store.fail_job

    def fail_once_then_work(job_id: str, *args, **kwargs):
        if job_id == first:
            raise RuntimeError("row is locked")
        return original_fail(job_id, *args, **kwargs)

    store.fail_job = fail_once_then_work  # type: ignore[method-assign]

    with pytest.raises(InterruptedJobReconciliationError):
        reap_interrupted_jobs(store, incarnation=OTHER_PROCESS)
    # The first row remains ambiguous, so serving job endpoints would be unsafe even
    # though a later row happened to settle.
    assert store.get_job(first).status is AnalysisJobStatus.RUNNING


def test_startup_sweeps_the_store_before_serving() -> None:
    """The 완료 판정: a job left RUNNING transitions to FAILED when the app comes up."""

    store, job_id = _store_with_running_job()
    store.jobs[job_id] = store.jobs[job_id].model_copy(
        update={"owner_incarnation": OTHER_PROCESS}
    )

    with TestClient(create_app(store)):
        job = store.get_job(job_id)
        assert job is not None
        assert job.status is AnalysisJobStatus.FAILED


def test_startup_refuses_to_serve_when_the_sweep_fails() -> None:
    """A store that cannot reconcile stale rows must fail closed before /health."""

    store, _ = _store_with_running_job()

    def exploding_list(**_kwargs):
        raise RuntimeError("job store unavailable")

    store.list_jobs = exploding_list  # type: ignore[method-assign]

    with pytest.raises(InterruptedJobReconciliationError):
        with TestClient(create_app(store)):
            pass


def _ready_envelope(trace_id: str):
    from ai_graph.schemas import APIEnvelope, UserPayload

    return APIEnvelope(
        status=EnvelopeStatus.READY,
        trace_id=trace_id,
        user_payload=UserPayload(headline="ready", message="done", next_actions=[]),
        strategy_spec=None,
        debug_ref=f"debug:{trace_id}",
        retryable=False,
    )
