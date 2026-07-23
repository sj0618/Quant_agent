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
# Metrics for which db.py attaches a `{metric}_up_streak` consecutive-rise count. Must
# stay in sync with _STREAK_METRICS there; a consecutive condition on anything else has no
# streak column to read, so it falls back to templates rather than silently never matching.
_STREAK_METRICS = frozenset({"revenue", "operating_income", "operating_margin", "roe"})

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


class CompiledConditions:
    """A strategy's entry rule split into the two kinds build_signals evaluates.

    per_stock: a boolean expression judged on one stock's own bars/financials.
    rank_filters: cross-sectional cuts (top-percentile on a metric) that can only be
        judged against the whole day's universe, applied by build_signals separately.
    """

    def __init__(self, per_stock: str, rank_filters: list[tuple[str, float, bool]]):
        self.per_stock = per_stock
        self.rank_filters = rank_filters


def compile_conditions(conditions: Sequence[Condition]) -> CompiledConditions | None:
    """Split conditions into a per-stock expression and cross-sectional rank cuts.

    All-or-nothing: if any condition compiles to neither, return None so the caller keeps
    its template profiles rather than trading a subset of the rule that looks validated
    while testing something else.
    """

    if not conditions:
        return None
    parts: list[str] = []
    rank_filters: list[tuple[str, float, bool]] = []
    for condition in conditions:
        rank = _rank_filter(condition)
        if rank is not None:
            rank_filters.append(rank)
            continue
        expr = _compile_one(condition)
        if expr is None:
            return None
        parts.append(expr)
    # A rule made only of rank cuts still needs a per-stock expression; "True" lets the
    # ranking do the selecting.
    per_stock = " and ".join(parts) if parts else "True"
    return CompiledConditions(per_stock, rank_filters)


def _rank_filter(condition: Condition) -> tuple[str, float, bool] | None:
    """A cross-sectional top/bottom-percentile cut, or None if this is not one.

    Returns (metric, pct, top) - top True selects the highest pct of the universe on the
    metric (e.g. revenue growth in the top 20%), False the lowest.
    """

    if condition.universe_rank_pct is None:
        return None
    metric = condition.left.strip().lower()
    if metric not in _CURRENT and metric not in _FINANCIAL_METRICS:
        return None
    # gt/gte -> want the top of the distribution; lt/lte -> the bottom.
    top = condition.operator in {ConditionOperator.GT, ConditionOperator.GTE}
    return (metric, float(condition.universe_rank_pct), top)


def compile_entry_expression(conditions: Sequence[Condition]) -> str | None:
    """Back-compat: the per-stock expression only, or None if a rank cut is present.

    Callers that cannot apply cross-sectional cuts fall back to templates when one
    appears, rather than silently dropping it.
    """

    compiled = compile_conditions(conditions)
    if compiled is None or compiled.rank_filters:
        return None
    return compiled.per_stock


def _compile_one(condition: Condition) -> str | None:
    if condition.consecutive is not None:
        # "N consecutive quarters of rising revenue/profit". db.py forward-fills a
        # {metric}_up_streak count onto each bar (see _fetch_financial_timeline), so the
        # test is just: streak >= N. Only rising streaks are tracked, so a falling
        # (lt/lte) direction has no column and falls back to templates.
        metric = condition.left.strip().lower()
        if metric not in _STREAK_METRICS:
            return None
        if condition.operator not in {ConditionOperator.GT, ConditionOperator.GTE}:
            return None
        return f"(_fin(fin, '{metric}_up_streak') >= {int(condition.consecutive)})"
    if condition.universe_rank_pct is not None:
        # Cross-sectional cuts are pulled out by _rank_filter before this point.
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
