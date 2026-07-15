from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_MAX_POSITIONS = 10
DEFAULT_FIXTURE_TICKER = "005930"


def requested_max_positions(max_position_pct: float | None) -> int:
    if max_position_pct is None:
        return DEFAULT_MAX_POSITIONS
    return max(1, math.ceil(1.0 / max_position_pct))


def applied_max_positions(
    max_position_pct: float | None, available_ticker_count: int | None = None
) -> int:
    requested = requested_max_positions(max_position_pct)
    if available_ticker_count is None or available_ticker_count <= 0:
        return requested
    return max(1, min(requested, available_ticker_count))


def available_ticker_count(price_rows: Sequence[Mapping[str, Any]]) -> int:
    tickers = {
        str(row.get("ticker") or DEFAULT_FIXTURE_TICKER).zfill(6)
        for row in price_rows
        if row.get("date") is not None
    }
    return max(1, len(tickers))


def max_position_pct_from_risk_constraints(risk_constraints: Mapping[str, Any]) -> float | None:
    """Best-effort, non-raising parse of `max_position_pct` for code generation.

    Unlike backtest.py's strict `_optional_positive_float` (which raises on bad
    input), candidate-code generation should degrade to the default max
    positions instead of failing outright on a malformed strategy spec.
    """
    value = risk_constraints.get("max_position_pct")
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0 or parsed > 1.0:
        return None
    return parsed
