"""Stage progress reporting from graph execution back to the job store.

The job store and the graph must not import each other, so the running analysis
publishes its progress through a context-local callback that whoever drives the
run (``run_job_sync``) installs. When nobody installs one - unit tests, direct
``run_analysis`` calls - reporting is a no-op.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_logger = logging.getLogger(__name__)

StageReporter = Callable[[str], None]

_STAGE_REPORTER: ContextVar[StageReporter | None] = ContextVar("stage_reporter", default=None)

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
