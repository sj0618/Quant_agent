"""Admission control in front of Azure OpenAI, sized from the provider's own signals.

Concurrent analyses used to fail as a group: nothing serialised the provider calls, so
every job posted at once, Azure rate-limited the deployment, and the deliberately thin
retry budget in `aoai.py` (two retries, sub-second linear backoff) burned through before
capacity freed up. The result was that one request effectively won and the rest reported
an error, which reads to a user as "AOAI only accepts one request at a time".

The fix is to queue rather than pile on. A request waits for a slot instead of being sent
into a saturated deployment, so concurrency is bounded by what Azure will actually serve.

The bound is not a number an operator has to guess. Azure reports what is left on every
response (`x-ratelimit-remaining-requests` and friends), so capacity starts modest and
moves with that signal: it drops immediately on a rate-limit signal and climbs back only
after a run of healthy responses. Shrinking fast and growing slowly is deliberate - being
briefly too conservative costs latency, while being too aggressive costs failed analyses,
which is the bug this module exists to prevent.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from os import environ

from ai_graph.llm.base import LLMClientError

_logger = logging.getLogger(__name__)


# The only knob deliberately left to operators: how long a queued analysis should wait
# before it is better to fail it than to keep the user staring at a stalled run. Every
# other value below is derived from provider responses at runtime rather than configured,
# because an operator has no way to know Azure's real per-deployment ceiling up front.
AI_AOAI_GATE_MAX_WAIT_SECONDS_ENV = "AI_AOAI_GATE_MAX_WAIT_SECONDS"

# A held slot spans a whole streamed completion, which routinely runs for minutes, so the
# wait has to be generous enough to outlast a couple of queued analyses ahead of it.
DEFAULT_MAX_WAIT_SECONDS = 300.0

# Start above one so two users are not serialised before any evidence says they must be,
# but well under any plausible Azure ceiling so the first burst does not trigger the very
# rate limiting this gate exists to avoid.
DEFAULT_INITIAL_CAPACITY = 2
# One in-flight request is the floor: at zero nothing would ever drain the queue.
DEFAULT_MIN_CAPACITY = 1
# Growth stops here regardless of how healthy responses look. Past a handful of concurrent
# streamed completions the bottleneck stops being admission control anyway, and an
# unbounded ceiling would let a quiet period grow capacity far past what a burst can use.
DEFAULT_MAX_CAPACITY = 8
# Capacity rises one step at a time and only after this many consecutive clean responses,
# so a single lucky call cannot undo a shrink that a real rate limit caused.
DEFAULT_HEALTHY_OBSERVATIONS_TO_GROW = 10
# Azure reports remaining quota per window; treat the last tenth as the danger zone rather
# than waiting for outright exhaustion, which is already too late to avoid a 429.
LOW_REMAINING_RATIO = 0.1

REMAINING_REQUESTS_HEADER = "x-ratelimit-remaining-requests"
REMAINING_TOKENS_HEADER = "x-ratelimit-remaining-tokens"
LIMIT_REQUESTS_HEADER = "x-ratelimit-limit-requests"
LIMIT_TOKENS_HEADER = "x-ratelimit-limit-tokens"


class AOAIGateBusyError(LLMClientError):
    """Raised when no provider slot became available within the caller's wait budget.

    Deliberately not one of the retryable provider errors: the gate is already the queue,
    so an immediate retry would only re-enter the same saturated wait.
    """


class AOAIConcurrencyGate:
    """Bounds in-flight AOAI requests, resizing itself from provider rate-limit signals.

    Capacity has to be able to move, which is why this is a condition variable and a
    counter rather than a `threading.Semaphore` - a semaphore fixes its permit count at
    construction, and the whole point here is that the right count is discovered from
    Azure's responses rather than declared up front.
    """

    def __init__(
        self,
        *,
        initial_capacity: int = DEFAULT_INITIAL_CAPACITY,
        min_capacity: int = DEFAULT_MIN_CAPACITY,
        max_capacity: int = DEFAULT_MAX_CAPACITY,
        max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS,
        healthy_observations_to_grow: int = DEFAULT_HEALTHY_OBSERVATIONS_TO_GROW,
    ) -> None:
        if min_capacity < 1:
            raise ValueError("min_capacity must be at least 1")
        if max_capacity < min_capacity:
            raise ValueError("max_capacity must be at least min_capacity")
        self._min_capacity = min_capacity
        self._max_capacity = max_capacity
        self._max_wait_seconds = max_wait_seconds
        self._healthy_observations_to_grow = healthy_observations_to_grow
        self._condition = threading.Condition()
        self._capacity = _clamp(initial_capacity, min_capacity, max_capacity)
        self._in_flight = 0
        self._healthy_streak = 0

    @contextmanager
    def acquire_slot(self, max_wait_seconds: float | None = None) -> Iterator[None]:
        """Hold one provider slot for the duration of the block, or raise AOAIGateBusyError."""

        budget = self._max_wait_seconds if max_wait_seconds is None else max_wait_seconds
        deadline = time.monotonic() + budget
        with self._condition:
            while self._in_flight >= self._capacity:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AOAIGateBusyError(
                        "no AOAI capacity became available within "
                        f"{budget:.0f}s (in_flight={self._in_flight}, capacity={self._capacity})"
                    )
                # A timed wait rather than a plain one: capacity can shrink while this
                # thread sleeps, so it has to re-check its own deadline regardless of
                # whether a release ever notifies it.
                self._condition.wait(remaining)
            self._in_flight += 1
        try:
            yield
        finally:
            with self._condition:
                self._in_flight -= 1
                self._condition.notify()

    def observe_rate_limit_headers(self, headers: Mapping[str, str]) -> None:
        """Shrink when Azure says the window is nearly spent, otherwise count it healthy."""

        if _is_near_exhaustion(headers):
            self._shrink("rate limit headers report the window is nearly spent")
            return
        self._record_healthy()

    def observe_rate_limited_response(self) -> None:
        """Shrink on an explicit 429, whether or not usable headers came with it."""

        self._shrink("provider returned a rate-limit status")

    def current_capacity(self) -> int:
        with self._condition:
            return self._capacity

    def in_flight(self) -> int:
        with self._condition:
            return self._in_flight

    def _shrink(self, reason: str) -> None:
        with self._condition:
            self._healthy_streak = 0
            if self._capacity <= self._min_capacity:
                return
            self._capacity -= 1
            _logger.warning(
                "AOAI concurrency reduced to %d (%s)", self._capacity, reason
            )

    def _record_healthy(self) -> None:
        with self._condition:
            if self._capacity >= self._max_capacity:
                return
            self._healthy_streak += 1
            if self._healthy_streak < self._healthy_observations_to_grow:
                return
            self._healthy_streak = 0
            self._capacity += 1
            _logger.info("AOAI concurrency raised to %d", self._capacity)
            # Waiters are parked on a capacity check they could not pass before, and no
            # slot is being released here, so nothing else would ever wake them.
            self._condition.notify_all()


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def _is_near_exhaustion(headers: Mapping[str, str]) -> bool:
    """True when either the request or token budget is down to its last sliver.

    Azure does not always send the matching `limit` header, so a bare `remaining` is
    judged only on outright exhaustion - inventing a threshold for an unknown ceiling
    would shrink capacity on deployments that simply report large absolute numbers.
    """

    for remaining_header, limit_header in (
        (REMAINING_REQUESTS_HEADER, LIMIT_REQUESTS_HEADER),
        (REMAINING_TOKENS_HEADER, LIMIT_TOKENS_HEADER),
    ):
        remaining = _int_header(headers, remaining_header)
        if remaining is None:
            continue
        if remaining <= 0:
            return True
        limit = _int_header(headers, limit_header)
        if limit and remaining / limit <= LOW_REMAINING_RATIO:
            return True
    return False


def _int_header(headers: Mapping[str, str], name: str) -> int | None:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


def _max_wait_seconds_from_env(env: Mapping[str, str] | None = None) -> float:
    source = environ if env is None else env
    raw = (source.get(AI_AOAI_GATE_MAX_WAIT_SECONDS_ENV) or "").strip()
    if not raw:
        return DEFAULT_MAX_WAIT_SECONDS
    try:
        parsed = float(raw)
    except ValueError:
        _logger.warning(
            "%s is not a number; using %.0fs",
            AI_AOAI_GATE_MAX_WAIT_SECONDS_ENV,
            DEFAULT_MAX_WAIT_SECONDS,
        )
        return DEFAULT_MAX_WAIT_SECONDS
    if parsed <= 0:
        return DEFAULT_MAX_WAIT_SECONDS
    return parsed


_shared_gate_lock = threading.Lock()
_shared_gate: AOAIConcurrencyGate | None = None


def get_shared_gate() -> AOAIConcurrencyGate:
    """The process-wide gate, mirroring the shared httpx client in `factory.py`.

    One gate per process is the correct scope today: deployment runs a single uvicorn
    process, so every AOAI call in flight passes through this object. Were the service
    ever to run multiple workers or hosts, this would need to move behind Redis - each
    process would otherwise enforce the limit against its own private counter and the
    deployment would see the sum.
    """

    global _shared_gate
    with _shared_gate_lock:
        if _shared_gate is None:
            _shared_gate = AOAIConcurrencyGate(
                max_wait_seconds=_max_wait_seconds_from_env()
            )
        return _shared_gate


def reset_shared_gate() -> None:
    """Drop the process-wide gate; tests use this to avoid leaking state between cases."""

    global _shared_gate
    with _shared_gate_lock:
        _shared_gate = None
