"""Stage progress reporting from graph execution back to the job store.

The job store and the graph must not import each other, so the running analysis
publishes its progress through a context-local callback that whoever drives the
run (``run_job_sync``) installs. When nobody installs one - unit tests, direct
``run_analysis`` calls - reporting is a no-op.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_logger = logging.getLogger(__name__)

StageReporter = Callable[[str], None]
ActivityReporter = Callable[[dict[str, Any]], None]

_STAGE_REPORTER: ContextVar[StageReporter | None] = ContextVar("stage_reporter", default=None)
_ACTIVITY_REPORTER: ContextVar[ActivityReporter | None] = ContextVar(
    "activity_reporter", default=None
)
# Which debate voice the current LLM call speaks for, so activity can be grouped into
# the 정/반/합 sections without the provider client knowing anything about debates.
_ACTIVITY_ROLE: ContextVar[str | None] = ContextVar("activity_role", default=None)

# Graph nodes mapped onto the five user-facing stages of AnalysisJob. Several nodes
# share a stage; the mapping is kept monotonic in graph execution order so a polled
# job never appears to move backwards.
NODE_STAGES: dict[str, str] = {
    "Supervisor": "interpreting",
    "Ambiguity Classifier": "interpreting",
    "Data": "interpreting",
    "Research": "code_generation",
    "BacktestCode": "code_generation",
    "Backtest": "backtest",
    "Signal": "backtest",
    "Risk Manager": "debate",
    "Report": "debate",
    "Envelope": "finalizing",
}


@contextmanager
def stage_reporter(reporter: StageReporter) -> Iterator[None]:
    token = _STAGE_REPORTER.set(reporter)
    try:
        yield
    finally:
        _STAGE_REPORTER.reset(token)


@contextmanager
def activity_reporter(reporter: ActivityReporter) -> Iterator[None]:
    token = _ACTIVITY_REPORTER.set(reporter)
    try:
        yield
    finally:
        _ACTIVITY_REPORTER.reset(token)


@contextmanager
def activity_role(role: str) -> Iterator[None]:
    token = _ACTIVITY_ROLE.set(role)
    try:
        yield
    finally:
        _ACTIVITY_ROLE.reset(token)


def report_activity(kind: str, **fields: Any) -> None:
    """Publish one live activity event, tagged with the current debate role.

    Fields carry provider output verbatim (search queries, text deltas, citation
    titles/urls); nothing here summarises or rewrites what the provider returned.
    """

    reporter = _ACTIVITY_REPORTER.get()
    if reporter is None:
        return
    event = {"kind": kind, "role": _ACTIVITY_ROLE.get(), **fields}
    try:
        reporter(event)
    except Exception:
        _logger.exception("failed to report activity kind=%s", kind)


class AnalysisCancelled(RuntimeError):
    """Raised at a checkpoint when the run has been cancelled."""


_CANCEL_CHECK: ContextVar[Callable[[], bool] | None] = ContextVar("cancel_check", default=None)


@contextmanager
def cancellation_check(is_cancelled: Callable[[], bool]) -> Iterator[None]:
    token = _CANCEL_CHECK.set(is_cancelled)
    try:
        yield
    finally:
        _CANCEL_CHECK.reset(token)


def raise_if_cancelled() -> None:
    """Stop at the next checkpoint if the run was cancelled.

    A provider call already in flight cannot be recalled, so cancellation cannot refund
    what is already spent - it prevents the run from paying for everything after this
    point, which is where the cost actually is.
    """

    check = _CANCEL_CHECK.get()
    if check is not None and check():
        raise AnalysisCancelled("analysis cancelled by user")


class AnalysisDeadlineExceeded(RuntimeError):
    """Raised at a checkpoint when the run has used its whole time budget."""


# A monotonic instant, not a duration: every checkpoint has to measure against the same
# point, and the phases each carry their own separate budget already.
_DEADLINE: ContextVar[float | None] = ContextVar("analysis_deadline", default=None)


@contextmanager
def analysis_deadline(seconds: float | None) -> Iterator[None]:
    """Bound one whole request, not just the phase that happens to be running.

    The per-phase budgets are each honoured on their own, so their sum has no ceiling:
    the backtest node's wall budget is checked between self-improvement rounds, and the
    round's own budget is `timeout x wave_count`, which grows with the candidate count.
    Screening relaxation rounds and provider calls upstream have no aggregate budget at
    all. A run could therefore take far longer than any single number in the code, and
    with a bounded number of analysis slots one such run holds a slot the whole time.

    `None` disables the ceiling, which is what the existing per-phase budgets did.
    """

    if seconds is None or seconds <= 0:
        token = _DEADLINE.set(None)
    else:
        token = _DEADLINE.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def deadline_remaining_seconds() -> float | None:
    """Time left for this request, or None when it is not bounded."""

    deadline = _DEADLINE.get()
    if deadline is None:
        return None
    return deadline - time.monotonic()


def raise_if_past_deadline() -> None:
    """Stop at the next checkpoint if the request has spent its whole budget."""

    remaining = deadline_remaining_seconds()
    if remaining is not None and remaining <= 0:
        raise AnalysisDeadlineExceeded("analysis exceeded its total time budget")


def report_node_stage(node_name: str) -> None:
    """Publish the stage `node_name` belongs to, if anyone is listening."""

    reporter = _STAGE_REPORTER.get()
    stage = NODE_STAGES.get(node_name)
    if reporter is None or stage is None:
        return
    try:
        reporter(stage)
    except Exception:
        # Progress is cosmetic: a store hiccup must never abort the analysis that
        # is already running. Logged rather than swallowed so it stays diagnosable.
        _logger.exception("failed to report stage progress for node=%s stage=%s", node_name, stage)
