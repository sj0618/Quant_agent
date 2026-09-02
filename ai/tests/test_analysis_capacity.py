"""Concurrent analyses are capped, because past a certain number the process dies."""

from __future__ import annotations

import threading
import time

import pytest

from ai_graph.analysis_capacity import (
    AI_ANALYSIS_MAX_CONCURRENCY_ENV,
    AI_ANALYSIS_QUEUE_WAIT_SECONDS_ENV,
    DEFAULT_MAX_CONCURRENCY,
    AnalysisCapacityGate,
    gate_from_env,
)
from ai_graph.jobs import AnalysisJobStatus, InMemoryAnalysisJobStore, run_job_sync
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


def test_only_the_configured_number_of_analyses_run_at_once() -> None:
    gate = AnalysisCapacityGate(max_concurrency=2, queue_wait_seconds=5.0)
    store = InMemoryAnalysisJobStore()
    live = 0
    peak = 0
    guard = threading.Lock()
    release = threading.Event()

    def runner(_query: str, trace_id: str) -> APIEnvelope:
        nonlocal live, peak
        with guard:
            live += 1
            peak = max(peak, live)
        release.wait(timeout=5)
        with guard:
            live -= 1
        return _envelope(trace_id)

    jobs = [store.create_job(f"전략 {index}") for index in range(6)]
    threads = [
        threading.Thread(target=run_job_sync, args=(store, job.job_id, runner), kwargs={"capacity": gate})
        for job in jobs
    ]
    for thread in threads:
        thread.start()
    time.sleep(0.3)
    observed_peak = peak
    release.set()
    for thread in threads:
        thread.join(timeout=10)

    assert observed_peak <= 2
    assert all(store.get_job(job.job_id).status is AnalysisJobStatus.COMPLETED for job in jobs)


def test_a_job_over_the_limit_waits_rather_than_being_refused() -> None:
    """The client is already polling a queued job, so waiting costs it nothing new."""

    gate = AnalysisCapacityGate(max_concurrency=1, queue_wait_seconds=5.0)
    store = InMemoryAnalysisJobStore()
    started = threading.Event()
    release = threading.Event()

    def blocking_runner(_query: str, trace_id: str) -> APIEnvelope:
        started.set()
        release.wait(timeout=5)
        return _envelope(trace_id)

    first = store.create_job("먼저 들어온 전략")
    holder = threading.Thread(
        target=run_job_sync, args=(store, first.job_id, blocking_runner), kwargs={"capacity": gate}
    )
    holder.start()
    assert started.wait(timeout=5)

    second = store.create_job("뒤에 들어온 전략")
    waiter = threading.Thread(
        target=run_job_sync,
        args=(store, second.job_id, lambda _q, t: _envelope(t)),
        kwargs={"capacity": gate},
    )
    waiter.start()
    time.sleep(0.2)

    # Still queued, not running and not failed: it is waiting for a slot.
    assert store.get_job(second.job_id).status is AnalysisJobStatus.QUEUED

    release.set()
    holder.join(timeout=10)
    waiter.join(timeout=10)
    assert store.get_job(second.job_id).status is AnalysisJobStatus.COMPLETED


def test_waiting_is_bounded_and_fails_with_a_retryable_message() -> None:
    """A thread parked forever is how a queue becomes the exhaustion it was preventing."""

    gate = AnalysisCapacityGate(max_concurrency=1, queue_wait_seconds=0.05)
    store = InMemoryAnalysisJobStore()
    release = threading.Event()
    started = threading.Event()

    def blocking_runner(_query: str, trace_id: str) -> APIEnvelope:
        started.set()
        release.wait(timeout=5)
        return _envelope(trace_id)

    first = store.create_job("슬롯을 쥔 전략")
    holder = threading.Thread(
        target=run_job_sync, args=(store, first.job_id, blocking_runner), kwargs={"capacity": gate}
    )
    holder.start()
    assert started.wait(timeout=5)

    second = store.create_job("대기하다 포기하는 전략")
    result = run_job_sync(store, second.job_id, lambda _q, t: _envelope(t), capacity=gate)

    assert result.status is AnalysisJobStatus.FAILED
    assert "다시 시도" in result.error_message
    assert result.result.retryable is True

    release.set()
    holder.join(timeout=10)


def test_a_slot_is_returned_when_the_analysis_raises() -> None:
    """A crashed run must not leak its slot, or the limit ratchets down to zero."""

    gate = AnalysisCapacityGate(max_concurrency=1, queue_wait_seconds=1.0)
    store = InMemoryAnalysisJobStore()

    def exploding(_query: str, _trace_id: str) -> APIEnvelope:
        raise RuntimeError("backtest blew up")

    failed = store.create_job("터지는 전략")
    run_job_sync(store, failed.job_id, exploding, capacity=gate)

    survivor = store.create_job("그 다음 전략")
    result = run_job_sync(store, survivor.job_id, lambda _q, t: _envelope(t), capacity=gate)
    assert result.status is AnalysisJobStatus.COMPLETED


@pytest.mark.parametrize(
    ("environ", "expected"),
    (
        ({}, DEFAULT_MAX_CONCURRENCY),
        ({AI_ANALYSIS_MAX_CONCURRENCY_ENV: "8"}, 8),
        ({AI_ANALYSIS_MAX_CONCURRENCY_ENV: "  "}, DEFAULT_MAX_CONCURRENCY),
        # A misconfiguration must not remove the limit entirely - that is the state this
        # module exists to prevent.
        ({AI_ANALYSIS_MAX_CONCURRENCY_ENV: "많이"}, DEFAULT_MAX_CONCURRENCY),
        ({AI_ANALYSIS_MAX_CONCURRENCY_ENV: "0"}, 1),
        ({AI_ANALYSIS_MAX_CONCURRENCY_ENV: "-3"}, 1),
    ),
)
def test_the_limit_survives_a_bad_setting(environ: dict[str, str], expected: int) -> None:
    assert gate_from_env(environ).max_concurrency == expected


def test_the_wait_window_survives_a_bad_setting() -> None:
    assert gate_from_env({AI_ANALYSIS_QUEUE_WAIT_SECONDS_ENV: "0"}).queue_wait_seconds > 0
    assert gate_from_env({AI_ANALYSIS_QUEUE_WAIT_SECONDS_ENV: "느리게"}).queue_wait_seconds > 0
    assert gate_from_env({AI_ANALYSIS_QUEUE_WAIT_SECONDS_ENV: "30"}).queue_wait_seconds == 30.0


def test_liveness_endpoints_do_not_share_the_analysis_worker_pool() -> None:
    """Sync handlers run in the same anyio pool the analyses occupy.

    A burst of analyses used to make liveness time out, so whatever was watching the
    service concluded it was dead while it was merely busy. Neither endpoint blocks, so
    neither needs a worker thread - this pins that they stay coroutines.
    """

    import inspect

    from ai_graph.api import HEALTH_PATH, READINESS_PATH, create_app

    app = create_app(InMemoryAnalysisJobStore())
    endpoints = {
        route.path: route.endpoint
        for route in app.routes
        if getattr(route, "path", None) in {HEALTH_PATH, READINESS_PATH}
    }

    assert set(endpoints) == {HEALTH_PATH, READINESS_PATH}
    for path, endpoint in endpoints.items():
        assert inspect.iscoroutinefunction(endpoint), f"{path} must not occupy a worker thread"


def test_default_queue_wait_outlasts_one_analysis_deadline() -> None:
    """A job queued behind a full run must not time out before that run can."""

    from ai_graph.analysis_capacity import DEFAULT_QUEUE_WAIT_SECONDS
    from ai_graph.jobs import DEFAULT_JOB_DEADLINE_SECONDS

    assert DEFAULT_QUEUE_WAIT_SECONDS >= DEFAULT_JOB_DEADLINE_SECONDS
