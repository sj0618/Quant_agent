"""Whether the backtest acceptance floor blocks a strategy, or only reports on it.

The product is in a test phase where every strategy is meant to come back with a result
to look at, so the acceptance floor is currently **report-only**: it is still evaluated,
its verdict and reasons are still published, but it no longer turns `strategy_validated`
off. Restoring enforcement is one environment variable, and the evaluation it switches on
is the same code that runs today - nothing has to be re-derived or re-implemented.

Keeping the evaluation live while it does not block is the point. A gate that is deleted
while "temporarily off" is a gate that has to be rewritten from memory later, and by then
nobody can say whether the thresholds still mean what they meant.

The floor this controls is the acceptance floor only - the out-of-sample Sharpe, drawdown,
trade-count, selection-adjusted Sharpe, and official-benchmark checks. Data-quality gates
are a different thing and are not touched here: freshness withholds recommendations
because the prices are stale, and the L4 evidence gate withholds them because the evidence
is missing. Neither is a judgement about whether a strategy is good, so neither belongs
behind this switch.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from os import environ

_logger = logging.getLogger(__name__)

AI_VALIDATION_GATES_ENV = "AI_VALIDATION_GATES"

ENFORCED = "enforced"
REPORT_ONLY = "report_only"
_MODES = (ENFORCED, REPORT_ONLY)

# The test-phase default. Flip to `enforced` to put the floor back in the path.
DEFAULT_MODE = REPORT_ONLY


def validation_gate_mode(environ_map: Mapping[str, str] | None = None) -> str:
    resolved = environ if environ_map is None else environ_map
    raw = str(resolved.get(AI_VALIDATION_GATES_ENV, "")).strip().lower()
    if not raw:
        return DEFAULT_MODE
    if raw in _MODES:
        return raw
    _logger.warning(
        "%s=%r is not one of %s; using %s",
        AI_VALIDATION_GATES_ENV,
        raw,
        ", ".join(_MODES),
        DEFAULT_MODE,
    )
    return DEFAULT_MODE


def objective_floor_is_enforced(environ_map: Mapping[str, str] | None = None) -> bool:
    """True when failing the acceptance floor actually withholds validation."""

    return validation_gate_mode(environ_map) == ENFORCED
