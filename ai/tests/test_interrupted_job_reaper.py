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


# A sibling worker that is alive and mid-run. The distinction the reaper cannot draw is
# between this and OTHER_PROCESS above: both are "not my incarnation".
LIVE_SIBLING_PROCESS = "8888:alivecafe0001"


def test_the_reaper_would_take_a_live_sibling_workers_job() -> None:
    """RMP-JOB-01's 2-worker claim, asserted as it actually behaves today.

    The claim rule is `owner_incarnation != mine`. Under one worker that means "a dead
    process", which is correct. Under two it also matches a sibling that is alive and
    mid-analysis, and this sweep would fail work in flight - the client sees a run that
    was progressing turn into `interrupted_by_restart` for no reason it can observe.

    There is no lease behind the rule: no heartbeat, no expiry, nothing the owner
    refreshes while it works. So the reaper has no way to tell a dead owner from a busy
    one, and the safety comes entirely from the startup guard below rather than from the
    claim itself.

    This asserts the unsafe behaviour on purpose. It is not a description of what should
    happen under two workers - it is the tripwire that makes anyone lifting the worker
    limit come here and build the lease first.
    """

    store, job_id = _store_with_running_job()
    store.jobs[job_id] = store.jobs[job_id].model_copy(
        update={"owner_incarnation": LIVE_SIBLING_PROCESS}
    )

    assert reap_interrupted_jobs(store, incarnation=PROCESS_INCARNATION) == [job_id]
    assert store.get_job(job_id).status is AnalysisJobStatus.FAILED


def test_the_startup_guard_the_claim_rule_depends_on_is_in_force() -> None:
    """The claim rule above is only sound while a second worker cannot start.

    Paired with the test above deliberately: together they say "the reaper is unsafe
    under N workers, and N workers cannot happen". Either one alone reads as a
    complete story and is not.
    """

    from ai_graph.single_process import (
        WEB_CONCURRENCY_ENV,
        MultiProcessStartupError,
        enforce_single_process,
    )

    with pytest.raises(MultiProcessStartupError):
        enforce_single_process(argv=["uvicorn", "combined_main:app", "--workers", "2"], environ={})
    with pytest.raises(MultiProcessStartupError):
        enforce_single_process(
            argv=["uvicorn", "combined_main:app"], environ={WEB_CONCURRENCY_ENV: "2"}
        )
