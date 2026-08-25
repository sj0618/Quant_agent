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

import re
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
    # Indicators the warehouse computes and db.py now carries onto every bar, keyed by
    # this codebase's name for them. Previously only `rsi` made it this far, so any rule
    # mentioning a moving average or a band could not be backtested as written - and the
    # screen, which did have them, selected on a definition the backtest never saw.
    "rsi": "rsi",
    "sma20": "sma20",
    "sma50": "sma50",
    "sma200": "sma200",
    "ema20": "ema20",
    "ema50": "ema50",
    "ema200": "ema200",
    "macd": "macd",
    "macd_signal": "macd_signal",
    "macd_hist": "macd_hist",
    "adx": "adx",
    "bb_upper": "bb_upper",
    "bb_lower": "bb_lower",
    "bb_middle": "bb_middle",
    "bb_width": "bb_width",
    "bb_pct": "bb_pct",
    "atr": "atr",
    "natr": "natr",
    "mfi": "mfi",
    "cci": "cci",
    "willr": "willr",
    "roc": "roc",
    "stoch_k": "stoch_k",
    "stoch_d": "stoch_d",
    "obv": "obv",
    "cmf": "cmf",
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

# Names that mean an existing metric but are spelled differently by whoever wrote the
# condition. Every one of these was observed rejecting a real strategy: the built-in
# profiles say `debt_ratio` where the warehouse says `debt_to_equity`, and the model is
# asked for market-standard indicator names, which are not this codebase's identifiers.
# Compiling used to be all-or-nothing on exact spelling, so one unfamiliar alias sent
# the whole rule back to the generic templates.
_ALIASES: dict[str, str] = {
    "price": "close",
    "closing_price": "close",
    "adj_close": "close",
    "rsi_14": "rsi",
    "rsi14": "rsi",
    "sma_20": "sma20",
    "sma_50": "sma50",
    "sma_200": "sma200",
    "ma20": "sma20",
    "ma50": "sma50",
    "ma200": "sma200",
    "ema_20": "ema20",
    "ema_50": "ema50",
    "ema_200": "ema200",
    "bollinger_upper": "bb_upper",
    "bollinger_lower": "bb_lower",
    "bollinger_middle": "bb_middle",
    "bb_width_pct": "bb_width",
    "atr_14": "atr",
    "macd_line": "macd",
    "signal_line": "macd_signal",
    "obv_line": "obv",
    "debt_to_equity_ratio": "debt_to_equity",
    "operating_profit": "operating_income",
    "sales": "revenue",
    "turnover": "revenue",
}

# Metrics whose conventional unit is a percentage while the row carries a ratio, with
# the factor that converts the condition's right-hand side into the row's unit.
# `debt_ratio <= 100` and `debt_to_equity <= 1.0` are the same rule; without this the
# first either failed to compile or, worse, compared 100 against a ratio near 1.
_PERCENT_SCALED: dict[str, tuple[str, float]] = {
    "debt_ratio": ("debt_to_equity", 0.01),
    "부채비율": ("debt_to_equity", 0.01),
    "roe_pct": ("roe", 0.01),
    "operating_margin_pct": ("operating_margin", 0.01),
}

# `close_above_sma_200 == 1` is how the strategy profiles and the model both express
# "the close is above its 200-day average". It is a comparison wearing a boolean's
# clothes, so it is rewritten into one rather than looked up as a metric that no row
# will ever carry.
_BOOLEAN_COMPARISONS: dict[str, tuple[str, str, str]] = {
    "close_above_sma_20": ("close", ">", "sma20"),
    "close_above_sma_50": ("close", ">", "sma50"),
    "close_above_sma_200": ("close", ">", "sma200"),
    "close_below_sma_20": ("close", "<", "sma20"),
    "close_below_sma_50": ("close", "<", "sma50"),
    "close_below_sma_200": ("close", "<", "sma200"),
    "close_above_bb_upper": ("close", ">", "bb_upper"),
    "close_below_bb_lower": ("close", "<", "bb_lower"),
}


# Metrics that are a ratio of things the bar already has. Expressed here rather than
# demanded of the data, so a rule can say "거래량이 20일 평균의 1.5배" the way people
# write it. Guarded against a zero denominator because the template catches only
# ValueError/ZeroDivisionError/IndexError around the whole expression, and one bad bar
# should fail its own condition rather than the day's.
_DERIVED: dict[str, str] = {
    "volume_ratio_20": "(volume / _avg(volumes[-20:]) if _avg(volumes[-20:]) else 0.0)",
    "volume_ratio": "(volume / _avg(volumes[-20:]) if _avg(volumes[-20:]) else 0.0)",
    "close_to_sma20": "(close / sma20 if sma20 else 0.0)",
    "close_to_sma200": "(close / sma200 if sma200 else 0.0)",
    "high_252": "max(highs[-252:])",
    "low_252": "min(lows[-252:])",
}

# Flag-style names that stand for a comparison against a rolling window rather than
# against another current-bar metric.
_BOOLEAN_EXPRESSIONS: dict[str, str] = {
    "breakout_high": "(close >= max(highs[-252:]) * 0.995)",
    "breakout_high_20": "(close >= max(highs[-20:]) * 0.995)",
    "close_below_lower_band_recent": "(min(closes[-5:]) <= bb_lower)",
    "close_cross_above_lower_band": "(close > bb_lower and closes[-2] <= bb_lower)",
    "close_cross_above_sma20": "(close > sma20 and closes[-2] <= sma20)",
    "close_cross_below_sma20": "(close < sma20 and closes[-2] >= sma20)",
}


# Metrics derived from the bars the store already holds, rather than demanded of the
# warehouse. OHLCV is fully loaded, so a rule phrased in terms of realised volatility,
# relative strength or a cross-sectional percentile is answerable - it was only
# untranslatable because nobody had written the derivation. Blocking those conditions
# meant recommending a different strategy than the user asked for.
#
#   realized_volatility_{N}d  stdev of daily returns over N bars, annualised (x sqrt(252))
#   relative_strength_{N}d    own N-day return minus the same-date universe mean
#   {metric}_percentile       cross-sectional rank of {metric} on that date, 0..1
_REALIZED_VOL = re.compile(r"^realized_volatility_(\d+)d$")
_RELATIVE_STRENGTH = re.compile(r"^relative_strength_(\d+)d$")
_PERCENTILE = re.compile(r"^(?P<metric>.+)_percentile$")


def derived_series_spec(name: str) -> tuple[str, str, int] | None:
    """(kind, base metric, window) for a store-derived metric, or None.

    kind is one of "realized_volatility", "relative_strength", "percentile".
    """

    normalized = str(name).strip().lower()
    match = _REALIZED_VOL.match(normalized)
    if match:
        return ("realized_volatility", "close", int(match.group(1)))
    match = _RELATIVE_STRENGTH.match(normalized)
    if match:
        return ("relative_strength", "close", int(match.group(1)))
    match = _PERCENTILE.match(normalized)
    if match:
        base = canonical_metric(match.group("metric"))
        return ("percentile", base, 0)
    return None


def canonical_metric(name: str) -> str:
    """The row key a condition's metric name refers to."""

    normalized = str(name).strip().lower()
    if normalized in _PERCENT_SCALED:
        return _PERCENT_SCALED[normalized][0]
    return _ALIASES.get(normalized, normalized)


def percent_scale(name: str) -> float:
    """Factor converting a condition's threshold into the row's unit (1.0 if none)."""

    scaled = _PERCENT_SCALED.get(str(name).strip().lower())
    return scaled[1] if scaled else 1.0


def boolean_comparison(name: str) -> tuple[str, str, str] | None:
    """(left metric, operator, right metric) for a `close_above_sma_200`-style flag."""

    return _BOOLEAN_COMPARISONS.get(str(name).strip().lower())


def derived_ratio(name: str) -> tuple[str, str, int] | None:
    """(numerator, denominator, window) for a ratio metric, or None.

    A window of 0 means the denominator is another current-bar metric rather than a
    rolling average. Kept as data, not as the Python source string used by the code
    generator, so the two evaluators - generated code and the in-process feature
    matcher - can share one definition of what `volume_ratio_20` means.
    """

    return _DERIVED_RATIOS.get(str(name).strip().lower())


def boolean_window_rule(name: str) -> tuple[str, str, str, int, float] | None:
    """(metric, aggregate, comparison, window, factor) for a window-flag, or None."""

    return _BOOLEAN_WINDOW_RULES.get(str(name).strip().lower())


# Data twins of _DERIVED / _BOOLEAN_EXPRESSIONS, for evaluators that work on values
# rather than on generated source.
_DERIVED_RATIOS: dict[str, tuple[str, str, int]] = {
    "volume_ratio_20": ("volume", "volume", 20),
    "volume_ratio": ("volume", "volume", 20),
    "close_to_sma20": ("close", "sma20", 0),
    "close_to_sma200": ("close", "sma200", 0),
}
_BOOLEAN_WINDOW_RULES: dict[str, tuple[str, str, str, int, float]] = {
    # metric, aggregate over its window, comparison of close against it, window, factor
    "breakout_high": ("high", "max", ">=", 252, 0.995),
    "breakout_high_20": ("high", "max", ">=", 20, 0.995),
    "close_below_lower_band_recent": ("close", "min", "<=", 5, 1.0),
}


def supported_metrics() -> list[str]:
    """Every metric name a condition may use, for the prompt that generates them.

    Published from here so the generator and the compiler cannot drift apart. They did:
    the prompt named no metrics at all and offered "sma_20" as an example, which this
    module had never heard of, so six of the seven built-in strategy profiles compiled
    to nothing and were silently backtested as generic templates instead.
    """

    return sorted(
        {
            "realized_volatility_20d",
            "realized_volatility_60d",
            "relative_strength_20d",
            "relative_strength_60d",
            "per_percentile",
            *_CURRENT,
            *_ALIASES,
            *_PERCENT_SCALED,
            *_BOOLEAN_COMPARISONS,
            *_BOOLEAN_EXPRESSIONS,
            *_DERIVED,
            *_HISTORY,
        }
    )


# Names the generated build_signals already binds from the bar itself.
_BOUND_BY_TEMPLATE = frozenset({"open", "high", "low", "close", "volume"})


def indicator_row_keys() -> list[str]:
    """Row keys the generated build_signals must read off each bar.

    Kept here rather than listed in the template so a metric added to `_CURRENT` is
    bound automatically. A compiled expression naming an unbound variable raises
    NameError, which the template does not catch - it would abort the whole backtest
    rather than fail the one condition.
    """

    return sorted(
        name
        for name in _CURRENT
        if name not in _BOUND_BY_TEMPLATE and name not in _FINANCIAL_METRICS
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

# How far past its threshold a condition sits, signed so positive always means "holds
# with room to spare". Shared with the structured evaluator so both readings of the
# same rule agree on which of two names has the stronger entry. Operators absent here
# (eq, ne, between) either hold or do not; there is no "more satisfied".
MARGIN_SIGN: dict[ConditionOperator, float] = {
    ConditionOperator.GT: 1.0,
    ConditionOperator.GTE: 1.0,
    ConditionOperator.CROSS_ABOVE: 1.0,
    ConditionOperator.LT: -1.0,
    ConditionOperator.LTE: -1.0,
    ConditionOperator.CROSS_BELOW: -1.0,
}
# Zero thresholds would otherwise divide the margin by nothing.
MARGIN_EPSILON = 1e-9
# Raw levels off the bar. How far one of these sits past a fixed number is a fact about
# the size of the company, not about the strength of its signal, so those conditions
# contribute no margin. Compared against another series - a moving average, a prior
# high - the same metric yields a scale-free ratio and does count.
LEVEL_METRICS = frozenset({"open", "high", "low", "close", "price", "volume"})


class CompiledConditions:
    """A strategy's entry rule split into the two kinds build_signals evaluates.

    per_stock: a boolean expression judged on one stock's own bars/financials.
    rank_filters: cross-sectional cuts (top-percentile on a metric) that can only be
        judged against the whole day's universe, applied by build_signals separately.
    """

    def __init__(
        self,
        per_stock: str,
        rank_filters: list[tuple[str, float, bool]],
        warmup_bars: int = 1,
    ):
        self.per_stock = per_stock
        self.rank_filters = rank_filters
        # Bars of history the widest condition needs before it means what it says. A
        # 52-week-high rule evaluated on a stock's third bar compares against a
        # three-day high; the generated build_signals waits this many bars instead.
        self.warmup_bars = warmup_bars


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
    warmup_bars = 1
    for condition in conditions:
        # `consecutive` needs that many evaluated bars; `window` needs a full window.
        warmup_bars = max(
            warmup_bars, int(condition.window or 1), int(condition.consecutive or 1)
        )
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
    return CompiledConditions(per_stock, rank_filters, warmup_bars)


def _rank_filter(condition: Condition) -> tuple[str, float, bool] | None:
    """A cross-sectional top/bottom-percentile cut, or None if this is not one.

    Returns (metric, pct, top) - top True selects the highest pct of the universe on the
    metric (e.g. revenue growth in the top 20%), False the lowest.
    """

    if condition.universe_rank_pct is None:
        return None
    metric = canonical_metric(condition.left)
    if metric not in _CURRENT and metric not in _FINANCIAL_METRICS:
        return None
    # gt/gte -> want the top of the distribution; lt/lte -> the bottom.
    top = condition.operator in {ConditionOperator.GT, ConditionOperator.GTE}
    return (metric, float(condition.universe_rank_pct), top)


def compile_score_expression(conditions: Sequence[Condition]) -> str | None:
    """Entry strength for a rule that declares no ranking metric, or None.

    The rule's own thresholds are the only stated measure of strength, so the score is
    how far inside its entry region a name sits, on the tightest condition that has a
    distance at all, normalized by the threshold so conditions on different scales stay
    comparable. Cross-sectional cuts are excluded here: build_signals ranks on those
    directly, the same order of preference the structured evaluator applies.
    """

    margins = [
        expression
        for condition in conditions
        if (expression := _margin_expression(condition)) is not None
    ]
    if not margins:
        return None
    if len(margins) == 1:
        return margins[0]
    return f"min({', '.join(margins)})"


def _margin_expression(condition: Condition) -> str | None:
    sign = MARGIN_SIGN.get(condition.operator)
    if sign is None:
        return None
    if condition.universe_rank_pct is not None or condition.consecutive is not None:
        return None
    flag = condition.left.strip().lower()
    if flag in _BOOLEAN_EXPRESSIONS or flag in _BOOLEAN_COMPARISONS:
        return None
    if isinstance(condition.right, str):
        left = _series_value(condition.left, None, None)
        right = _series_value(condition.right, condition.window, condition.aggregate)
    elif isinstance(condition.right, (int, float)):
        if canonical_metric(condition.left) in LEVEL_METRICS:
            return None
        left = _series_value(condition.left, condition.window, condition.aggregate)
        scale = _PERCENT_SCALED.get(condition.left.strip().lower())
        right = repr(float(condition.right) * (scale[1] if scale else 1.0))
    else:
        return None
    if left is None or right is None:
        return None
    if condition.scale is not None:
        right = f"({right} * {float(condition.scale)!r})"
    return (
        f"({sign!r} * (({left}) - ({right})) / max(abs({right}), {MARGIN_EPSILON!r}))"
    )


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
    flag = condition.left.strip().lower()
    expression = _BOOLEAN_EXPRESSIONS.get(flag)
    if expression is not None:
        asserted = _boolean_is_asserted(condition)
        if asserted is None:
            return None
        return expression if asserted else f"(not {expression})"
    boolean = _BOOLEAN_COMPARISONS.get(flag)
    if boolean is not None:
        # `close_above_sma_200 == 1` (or `!= 0`, or `>= 1`) asserts the comparison;
        # comparing it to 0 asserts its negation.
        left_metric, operator, right_metric = boolean
        asserted = _boolean_is_asserted(condition)
        if asserted is None:
            return None
        left = _CURRENT.get(left_metric)
        right = _CURRENT.get(right_metric)
        if left is None or right is None:
            return None
        if not asserted:
            operator = "<=" if operator == ">" else ">="
        return f"({left} {operator} {right})"
    if condition.consecutive is not None:
        # "N consecutive quarters of rising revenue/profit". db.py forward-fills a
        # {metric}_up_streak count onto each bar (see _fetch_financial_timeline), so the
        # test is just: streak >= N. Only rising streaks are tracked, so a falling
        # (lt/lte) direction has no column and falls back to templates.
        metric = canonical_metric(condition.left)
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
        # A percentage-quoted metric compares against a percentage; the row holds the
        # ratio, so the threshold is converted rather than the series.
        scale = _PERCENT_SCALED.get(condition.left.strip().lower())
        value = float(condition.right) * (scale[1] if scale else 1.0)
        right = repr(value)
    else:
        return None
    if left is None or right is None:
        return None

    if condition.scale is not None:
        right = f"({right} * {float(condition.scale)!r})"
    return f"({left} {_OPERATOR[condition.operator]} {right})"


def _boolean_is_asserted(condition: Condition) -> bool | None:
    """Whether a `close_above_sma_200`-style flag is being asserted or negated."""

    if not isinstance(condition.right, (int, float)) or isinstance(condition.right, bool):
        return None
    truthy = float(condition.right) != 0.0
    if condition.operator in {ConditionOperator.EQ, ConditionOperator.GTE, ConditionOperator.GT}:
        return truthy
    if condition.operator in {ConditionOperator.NE, ConditionOperator.LT, ConditionOperator.LTE}:
        return not truthy
    return None


def _series_value(metric: str, window: int | None, aggregate: str | None) -> str | None:
    """Current bar value, or an aggregate over the metric's rolling history."""

    metric = canonical_metric(metric)
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
    derived = _DERIVED.get(metric)
    if derived is not None:
        return derived
    if derived_series_spec(metric) is not None:
        # Computed by the feature store from the bars it holds. The generated-code path
        # binds it via _ind() and therefore sees NaN; that path is already unreachable
        # (the AST validator rejects every candidate it emits) and must be revisited
        # before it is relied on again.
        return metric
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
