"""Compile structured strategy conditions into build_signals decision expressions.

The screen (SQL) and the backtest (build_signals) used to encode a strategy's rule
separately, so "the stocks recommended today" and "the rule the backtest actually
traded" could differ. The screen now emits the rule as structured Conditions; this
module turns those same Conditions into the boolean expressions build_signals evaluates
per stock per date, so both run one definition.

Only price-series conditions compile: build_signals is handed daily price rows
(open/high/low/close/volume and rsi), and nothing else. Financial conditions
(4 quarters of rising operating income) and cross-sectional ones (top 20% by revenue
growth) reference data the backtest does not carry, so they return None and the caller
keeps its template profiles. window/aggregate attach to whichever side is a series -
the metric side - so "close >= 252-day max of high" and "20-day average close >= 1000"
both read naturally.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ai_graph.schemas import Condition, ConditionOperator

# Metrics build_signals has per date, mapped to the current-bar variable and the rolling
# history list the template maintains. A metric absent here cannot be backtested.
_CURRENT: dict[str, str] = {
    "open": "open_price",
    "high": "high_price",
    "low": "low_price",
    "close": "close",
    "volume": "volume",
    "rsi": "rsi",
    # Point-in-time financials forward-filled onto each row (see db.py). Current-bar
    # only - a filing has no meaningful rolling window here.
    "roe": "roe",
    "debt_to_equity": "debt_to_equity",
    "operating_margin": "operating_margin",
    "operating_income": "operating_income",
    "revenue": "revenue",
}
_HISTORY: dict[str, str] = {
    "open": "opens",
    "high": "highs",
    "low": "lows",
    "close": "closes",
    "volume": "volumes",
}
# Financials are forward-filled and may be missing on early dates; a condition on them
# must treat "not yet filed" as not-matched rather than erroring.
_FINANCIAL_METRICS = frozenset(
    {"roe", "debt_to_equity", "operating_margin", "operating_income", "revenue"}
)

_OPERATOR: dict[ConditionOperator, str] = {
    ConditionOperator.LT: "<",
    ConditionOperator.LTE: "<=",
    ConditionOperator.GT: ">",
    ConditionOperator.GTE: ">=",
    ConditionOperator.EQ: "==",
    ConditionOperator.NE: "!=",
}
_AGGREGATE: dict[str, str] = {
    "max": "max",
    "min": "min",
    "sum": "sum",
    "last": "_last",
}


def compile_entry_expression(conditions: Sequence[Condition]) -> str | None:
    """AND the conditions into one boolean expression, or None if any cannot compile.

    All-or-nothing on purpose: a partially compiled rule would trade on a subset of the
    strategy and look validated while testing something else.
    """

    if not conditions:
        return None
    parts: list[str] = []
    for condition in conditions:
        expr = _compile_one(condition)
        if expr is None:
            return None
        parts.append(expr)
    return " and ".join(parts)


def _compile_one(condition: Condition) -> str | None:
    if condition.consecutive is not None or condition.universe_rank_pct is not None:
        # Consecutive-period and cross-sectional tests need financial/ranked series the
        # price-only backtest does not hold.
        return None
    if condition.operator not in _OPERATOR:
        return None

    if isinstance(condition.right, str):
        left = _series_value(condition.left, None, None)
        right = _series_value(condition.right, condition.window, condition.aggregate)
    elif isinstance(condition.right, (int, float)):
        left = _series_value(condition.left, condition.window, condition.aggregate)
        right = repr(float(condition.right))
    else:
        return None
    if left is None or right is None:
        return None

    if condition.scale is not None:
        right = f"({right} * {float(condition.scale)!r})"
    return f"({left} {_OPERATOR[condition.operator]} {right})"


def _series_value(metric: str, window: int | None, aggregate: str | None) -> str | None:
    """Current bar value, or an aggregate over the metric's rolling history."""

    metric = metric.strip().lower()
    if window and aggregate:
        history = _HISTORY.get(metric)
        if history is None:
            return None
        window_slice = f"{history}[-{int(window)}:]"
        if aggregate == "avg":
            return f"_avg({window_slice})"
        if aggregate == "last":
            return f"{history}[-1]"
        agg = _AGGREGATE.get(aggregate)
        if agg is None:
            return None
        return f"{agg}({window_slice})"
    if metric in _FINANCIAL_METRICS:
        # Forward-filled from filings and absent before the first one; _fin() returns a
        # sentinel that fails any numeric comparison so an un-filed name never matches.
        return f"_fin(fin, '{metric}')"
    return _CURRENT.get(metric)


def conditions_from_metadata(raw: Sequence[Any]) -> list[Condition]:
    """Validate raw condition dicts (from screening metadata) into Conditions, dropping bad ones."""

    out: list[Condition] = []
    for item in raw or []:
        try:
            out.append(Condition.model_validate(item))
        except Exception:
            continue
    return out
