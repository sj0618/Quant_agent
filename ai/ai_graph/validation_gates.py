"""Whether the backtest acceptance floor blocks a strategy, or only reports on it.

The default now depends on the runtime profile. A dev profile stays **report-only** so
every strategy still comes back with a result to look at: the acceptance floor is
evaluated, its verdict and reasons are published, but it does not turn
`strategy_validated` off. A release profile (`AI_RELEASE_PROFILE` or `APP_ENV` in
`{release, production}`) defaults to **enforced** so production never silently ships the
report-only floor. Either default can be overridden in either direction by setting
`AI_VALIDATION_GATES`, and the evaluation it switches on is the same code that runs today
- nothing has to be re-derived or re-implemented.

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

from ai_graph.source_manifest import is_release_profile

_logger = logging.getLogger(__name__)

AI_VALIDATION_GATES_ENV = "AI_VALIDATION_GATES"

ENFORCED = "enforced"
REPORT_ONLY = "report_only"
_MODES = (ENFORCED, REPORT_ONLY)

# The dev-phase default: keep every strategy coming back with a result to look at.
DEFAULT_MODE = REPORT_ONLY
# A release profile restores the acceptance floor by default. An operator can still
# override either direction with AI_VALIDATION_GATES.
RELEASE_DEFAULT_MODE = ENFORCED


def _default_mode(resolved: Mapping[str, str]) -> str:
    return RELEASE_DEFAULT_MODE if is_release_profile(resolved) else DEFAULT_MODE


def validation_gate_mode(environ_map: Mapping[str, str] | None = None) -> str:
    resolved = environ if environ_map is None else environ_map
    raw = str(resolved.get(AI_VALIDATION_GATES_ENV, "")).strip().lower()
    if not raw:
        return _default_mode(resolved)
    if raw in _MODES:
        return raw
    _logger.warning(
        "%s=%r is not one of %s; using %s",
        AI_VALIDATION_GATES_ENV,
        raw,
        ", ".join(_MODES),
        _default_mode(resolved),
    )
    return _default_mode(resolved)


def objective_floor_is_enforced(environ_map: Mapping[str, str] | None = None) -> bool:
    """True when failing the acceptance floor actually withholds validation."""

    return validation_gate_mode(environ_map) == ENFORCED
