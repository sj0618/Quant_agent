"""One request has a ceiling, not just each phase it happens to pass through."""

from __future__ import annotations

import time

import pytest

from ai_graph.jobs import (
    AI_JOB_DEADLINE_SECONDS_ENV,
    DEFAULT_JOB_DEADLINE_SECONDS,
    AnalysisJobStatus,
    InMemoryAnalysisJobStore,
    job_deadline_seconds,
    run_job_sync,
)
from ai_graph.progress import (
    AnalysisDeadlineExceeded,
    analysis_deadline,
    deadline_remaining_seconds,
    raise_if_past_deadline,
)
from ai_graph.schemas import APIEnvelope, EnvelopeStatus, UserPayload


def _envelope(trace_id: str) -> APIEnvelope:
    return APIEnvelope(
        status=EnvelopeStatus.READY,
        trace_id=trace_id,
        user_payload=UserPayload(headline="ready", message="done", next_actions=[]),
        strategy_spec=None,
        debug_ref=f"debug:{trace_id}",
        retryable=False,
    )


def test_a_checkpoint_passes_while_budget_remains() -> None:
    with analysis_deadline(30.0):
        raise_if_past_deadline()
        remaining = deadline_remaining_seconds()
    assert remaining is not None and 0 < remaining <= 30.0


def test_a_checkpoint_stops_the_run_once_the_budget_is_spent() -> None:
    with analysis_deadline(0.01):
        time.sleep(0.05)
        with pytest.raises(AnalysisDeadlineExceeded):
            raise_if_past_deadline()


def test_an_unbounded_run_has_no_ceiling() -> None:
    with analysis_deadline(None):
        raise_if_past_deadline()
        assert deadline_remaining_seconds() is None


def test_the_scope_is_restored_so_one_run_cannot_bound_the_next() -> None:
    with analysis_deadline(30.0):
        assert deadline_remaining_seconds() is not None
    assert deadline_remaining_seconds() is None


def test_a_job_that_outlives_its_budget_fails_with_a_retryable_message(monkeypatch) -> None:
    """완료 판정: with a deadline set, the job does not run past it."""

    monkeypatch.setenv(AI_JOB_DEADLINE_SECONDS_ENV, "0.05")
    store = InMemoryAnalysisJobStore()
    job = store.create_job("오래 도는 전략")

    def slow_runner(_query: str, trace_id: str) -> APIEnvelope:
        # Stands in for a node boundary reached after the budget is gone.
        time.sleep(0.2)
        raise_if_past_deadline()
        return _envelope(trace_id)

    started = time.monotonic()
    result = run_job_sync(store, job.job_id, slow_runner)
    elapsed = time.monotonic() - started

    assert result.status is AnalysisJobStatus.FAILED
    assert "다시 시도" in result.error_message
    assert result.result.retryable is True
    assert result.result.failure_cause.subcause == "job_deadline_exceeded"
    # The point of the ceiling: the run does not keep going past it.
    assert elapsed < 5.0


def test_a_job_inside_its_budget_still_completes(monkeypatch) -> None:
    monkeypatch.setenv(AI_JOB_DEADLINE_SECONDS_ENV, "30")
    store = InMemoryAnalysisJobStore()
    job = store.create_job("정상 전략")

    def runner(_query: str, trace_id: str) -> APIEnvelope:
        raise_if_past_deadline()
        return _envelope(trace_id)

    assert run_job_sync(store, job.job_id, runner).status is AnalysisJobStatus.COMPLETED


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("", DEFAULT_JOB_DEADLINE_SECONDS),
        ("900", 900.0),
        # A typo must not be what removes the ceiling.
        ("오래", DEFAULT_JOB_DEADLINE_SECONDS),
        # An explicit zero is the documented way to opt out.
        ("0", None),
        ("-1", None),
    ),
)
def test_the_ceiling_survives_a_bad_setting(value: str, expected: float | None) -> None:
    assert job_deadline_seconds({AI_JOB_DEADLINE_SECONDS_ENV: value} if value else {}) == expected


def test_cancelling_a_job_actually_fails_it() -> None:
    """The cancel path built a FailureDiagnostic the schema rejected.

    `category="cancelled"` and `subcause="user_cancelled"` were not in the literals, so
    the ValidationError escaped from inside the `except AnalysisCancelled` handler and
    the job was left RUNNING - the spinner-forever state, on every cancellation.
    """

    from ai_graph.jobs import CancellationRegistry
    from ai_graph.progress import AnalysisCancelled

    store = InMemoryAnalysisJobStore()
    job = store.create_job("취소할 전략")
    cancellations = CancellationRegistry()
    cancellations.cancel(job.job_id)

    def cancelling_runner(_query: str, _trace_id: str) -> APIEnvelope:
        raise AnalysisCancelled("analysis cancelled by user")

    result = run_job_sync(store, job.job_id, cancelling_runner, cancellations=cancellations)

    assert result.status is AnalysisJobStatus.FAILED
    assert store.get_job(job.job_id).status is AnalysisJobStatus.FAILED
    assert result.result.failure_cause.category == "cancelled"
    assert result.result.failure_cause.subcause == "user_cancelled"
