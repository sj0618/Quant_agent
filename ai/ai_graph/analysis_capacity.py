"""How many analyses this process will run at once, and what happens past that.

An analysis is not a cheap request. It loads years of price rows, fans candidates out
across a process pool, and holds that working set for as long as the graph runs. Nothing
bounded how many of those could be in flight: every accepted job went straight to a
background task, so N users starting analyses meant N simultaneous backtests competing
for the same memory and CPU. Past a certain N the process does not slow down, it dies -
and every job it was running dies with it, which is the failure this module exists to
prevent.

The limit is a slot count rather than a rejection: a job that arrives over the limit
waits for a slot. The client is already polling a queued job, so waiting costs it
nothing it was not already doing, and the alternative - refusing work the service could
do a minute later - is worse for the user than a slower answer.

The wait is bounded. A job that cannot get a slot within the window fails with a message
that says to retry, because a thread parked forever is how a queue turns into the same
exhaustion it was meant to prevent.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from os import environ

_logger = logging.getLogger(__name__)

AI_ANALYSIS_MAX_CONCURRENCY_ENV = "AI_ANALYSIS_MAX_CONCURRENCY"
AI_ANALYSIS_QUEUE_WAIT_SECONDS_ENV = "AI_ANALYSIS_QUEUE_WAIT_SECONDS"

# The production node has 2 vCPUs and a single-process service. One analysis can hold
# a multi-year PIT universe and use backtest workers, so the safe default is one; an
# operator may raise it explicitly after sizing the host. Queuing preserves accepted
# jobs instead of letting four full extracts compete until the process is killed.
DEFAULT_MAX_CONCURRENCY = 1
# Longer than a single analysis's wall budget, so a job queued behind one full run still
# gets its turn instead of failing while a slot was about to free up. That budget is
# ``jobs.DEFAULT_JOB_DEADLINE_SECONDS`` (1800s); this stayed at 600s and made a queued
# job fail before the run ahead of it could even hit its own deadline. `jobs` imports
# this module, so the ceiling is restated here rather than imported.
DEFAULT_QUEUE_WAIT_SECONDS = 1_860.0

CAPACITY_TIMEOUT_MESSAGE = (
    "분석 대기열이 가득 차 시간 안에 실행하지 못했습니다. 잠시 후 다시 시도해 주세요."
)


class AnalysisCapacityTimeout(RuntimeError):
    """Raised when a job waited for a slot longer than the configured window."""


def _positive_int(environ_map: Mapping[str, str], key: str, default: int) -> int:
    raw = str(environ_map.get(key, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        _logger.warning("%s=%r is not an integer; using %d", key, raw, default)
        return default
    if value < 1:
        _logger.warning("%s=%d is below 1; using 1", key, value)
        return 1
    return value


def _positive_float(environ_map: Mapping[str, str], key: str, default: float) -> float:
    raw = str(environ_map.get(key, "")).strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        _logger.warning("%s=%r is not a number; using %s", key, raw, default)
        return default
    return value if value > 0 else default


class AnalysisCapacityGate:
    """A slot counter shared by every analysis running in this process."""

    def __init__(self, *, max_concurrency: int, queue_wait_seconds: float) -> None:
        self.max_concurrency = max_concurrency
        self.queue_wait_seconds = queue_wait_seconds
        self._slots = threading.BoundedSemaphore(max_concurrency)
        self._waiting = 0
        self._waiting_lock = threading.Lock()

    @property
    def waiting(self) -> int:
        with self._waiting_lock:
            return self._waiting

    @contextmanager
    def slot(self) -> Iterator[None]:
        with self._waiting_lock:
            self._waiting += 1
        try:
            acquired = self._slots.acquire(timeout=self.queue_wait_seconds)
        finally:
            with self._waiting_lock:
                self._waiting -= 1
        if not acquired:
            raise AnalysisCapacityTimeout(CAPACITY_TIMEOUT_MESSAGE)
        try:
            yield
        finally:
            self._slots.release()


def gate_from_env(environ_map: Mapping[str, str] | None = None) -> AnalysisCapacityGate:
    resolved = environ if environ_map is None else environ_map
    return AnalysisCapacityGate(
        max_concurrency=_positive_int(
            resolved, AI_ANALYSIS_MAX_CONCURRENCY_ENV, DEFAULT_MAX_CONCURRENCY
        ),
        queue_wait_seconds=_positive_float(
            resolved, AI_ANALYSIS_QUEUE_WAIT_SECONDS_ENV, DEFAULT_QUEUE_WAIT_SECONDS
        ),
    )


# One gate per process, because the resources it protects - memory, CPU, the process
# pool - are per process. `single_process` keeps that from being two gates.
ANALYSIS_CAPACITY = gate_from_env()
