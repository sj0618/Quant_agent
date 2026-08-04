from __future__ import annotations

from array import array
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any

import numpy as np

from ai_graph.nodes.condition_compiler import (
    boolean_comparison,
    boolean_window_rule,
    canonical_metric,
    derived_ratio,
    derived_series_spec,
    percent_scale,
)
from ai_graph.schemas import CandidateParameters, Condition, ConditionOperator, StrategyIR


FEATURE_DEFINITION_VERSION = "structured-features.v1"

READY = 0
AVERAGE = 1
SHORT_AVERAGE = 2
MEDIUM_AVERAGE = 3
HIGH = 4
LOW = 5
PREVIOUS = 6
TREND = 7
MEDIUM_RETURN = 8
VOLATILITY = 9
LONG_AVERAGE = 10
LONG_HIGH = 11
LONG_RETURN = 12
LONG_DRAWDOWN = 13
ROLLING_SHARPE = 14
VOLUME_RATIO = 15
RETURN_TO_VOLATILITY = 16
PULLBACK = 17
FEATURE_COLUMN_COUNT = 18


@dataclass(frozen=True)
class FeaturePreparationStats:
    input_rows: int
    ticker_count: int
    cached_lookbacks: tuple[int, ...]
    estimated_bytes: int


class PreparedFeatureStore:
    """Columnar, read-only feature arrays shared by all structured candidates."""

    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self.rows = tuple(
            sorted(
                rows,
                key=lambda row: (
                    str(row.get("date") or ""),
                    str(row.get("ticker") or "000000").zfill(6),
                ),
            )
        )
        self.dates = tuple(str(row.get("date") or "") for row in self.rows)
        self.tickers = tuple(
            str(row.get("ticker") or "000000").zfill(6) for row in self.rows
        )
        self.close = np.asarray([float(row["close"]) for row in self.rows], dtype=np.float64)
        self.volume = np.asarray(
            [float(row.get("volume", 0.0) or 0.0) for row in self.rows],
            dtype=np.float64,
        )
        # A missing RSI is missing, not neutral. It used to default to 50.0, so a bar
        # the warehouse had no RSI for read as perfectly average momentum and could
        # satisfy a band condition on the strength of a number nobody measured. NaN
        # fails every comparison instead, so the condition simply does not match.
        self.rsi = np.asarray(
            [_optional_metric(row, "rsi", "RSI_14") for row in self.rows],
            dtype=np.float64,
        )
        self.close.setflags(write=False)
        self.volume.setflags(write=False)
        self.rsi.setflags(write=False)
        groups: dict[str, list[int]] = {}
        for index, ticker in enumerate(self.tickers):
            groups.setdefault(ticker, []).append(index)
        self.indices_by_ticker = {
            ticker: np.asarray(indices, dtype=np.int64)
            for ticker, indices in groups.items()
        }
        for indices in self.indices_by_ticker.values():
            indices.setflags(write=False)
        self.previous_index = np.full(len(self.rows), -1, dtype=np.int64)
        for indices in self.indices_by_ticker.values():
            if len(indices) > 1:
                self.previous_index[indices[1:]] = indices[:-1]
        self.previous_index.setflags(write=False)
        self.date_ranges: tuple[tuple[int, int], ...] = self._date_ranges()
        self._lookback_cache: dict[int, np.ndarray] = {}
        self._metric_cache: dict[str, np.ndarray] = {}
        self._rolling_cache: dict[tuple[str, int, str], np.ndarray] = {}
        self._condition_cache: dict[str, np.ndarray] = {}

    def _date_ranges(self) -> tuple[tuple[int, int], ...]:
        ranges: list[tuple[int, int]] = []
        start = 0
        while start < len(self.rows):
            end = start + 1
            while end < len(self.rows) and self.dates[end] == self.dates[start]:
                end += 1
            ranges.append((start, end))
            start = end
        return tuple(ranges)

    def stats(self) -> FeaturePreparationStats:
        estimated = (
            self.close.nbytes
            + self.volume.nbytes
            + self.rsi.nbytes
            + sum(value.nbytes for value in self._lookback_cache.values())
            + sum(value.nbytes for value in self._metric_cache.values())
            + sum(value.nbytes for value in self._rolling_cache.values())
            + sum(value.nbytes for value in self._condition_cache.values())
        )
        return FeaturePreparationStats(
            input_rows=len(self.rows),
            ticker_count=len(self.indices_by_ticker),
            cached_lookbacks=tuple(sorted(self._lookback_cache)),
            estimated_bytes=estimated,
        )

    def build_actions(
        self,
        strategy_ir: StrategyIR,
        parameters: CandidateParameters,
    ) -> array:
        if parameters.profile == "compiled_conditions":
            return self._compiled_actions(strategy_ir, parameters)
        return self._profile_actions(parameters)

    def features(self, lookback: int) -> np.ndarray:
        cached = self._lookback_cache.get(lookback)
        if cached is not None:
            return cached
        matrix = np.zeros((len(self.rows), FEATURE_COLUMN_COUNT), dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            closes = self.close[indices]
            volumes = self.volume[indices]
            close_prefix = np.concatenate(([0.0], np.cumsum(closes)))
            volume_prefix = np.concatenate(([0.0], np.cumsum(volumes)))
            returns = np.zeros(len(indices), dtype=np.float64)
            if len(indices) > 1:
                before = closes[:-1]
                after = closes[1:]
                valid = before != 0.0
                returns[1:][valid] = after[valid] / before[valid] - 1.0
            return_prefix = np.concatenate(([0.0], np.cumsum(returns)))
            return_square_prefix = np.concatenate(([0.0], np.cumsum(returns * returns)))
            main_highs = _prior_rolling_extreme(closes, lookback, maximum=True)
            main_lows = _prior_rolling_extreme(closes, lookback, maximum=False)
            long_limit = max(60, lookback)
            long_highs = _prior_rolling_extreme(closes, long_limit, maximum=True)

            for local_index, global_index in enumerate(indices):
                window = min(lookback, local_index)
                if window <= 0:
                    continue
                start = local_index - window
                short_window = min(max(3, window // 4), local_index)
                medium_window = min(max(5, window // 2), local_index)
                long_window = min(long_limit, local_index)
                medium_start = local_index - medium_window
                long_start = local_index - long_window

                average = _prefix_average(close_prefix, start, local_index)
                short_average = _prefix_average(
                    close_prefix, local_index - short_window, local_index
                )
                medium_average = _prefix_average(
                    close_prefix, medium_start, local_index
                )
                long_average = _prefix_average(close_prefix, long_start, local_index)
                high = main_highs[local_index]
                low = main_lows[local_index]
                long_high = long_highs[local_index]
                close = closes[local_index]
                first = closes[start]
                medium_first = closes[medium_start]
                long_first = closes[long_start]
                trend = close / first - 1.0 if first else 0.0
                medium_return = close / medium_first - 1.0 if medium_first else 0.0
                long_return = close / long_first - 1.0 if long_first else 0.0
                pullback = (high - close) / high if high > 0.0 else 0.0
                volatility = (high - low) / average if average else 0.0
                long_drawdown = (
                    (long_high - close) / long_high if long_high > 0.0 else 0.0
                )
                return_count = max(0, window - 1)
                if return_count:
                    return_start = start + 1
                    total = return_prefix[local_index] - return_prefix[return_start]
                    square_total = (
                        return_square_prefix[local_index]
                        - return_square_prefix[return_start]
                    )
                    mean_return = total / return_count
                    variance = max(
                        0.0,
                        square_total / return_count - mean_return * mean_return,
                    )
                    rolling_sharpe = (
                        mean_return / sqrt(variance) if variance > 0.0 else 0.0
                    )
                else:
                    rolling_sharpe = 0.0
                average_volume = _prefix_average(
                    volume_prefix, start, local_index
                )
                volume_ratio = (
                    volumes[local_index] / average_volume
                    if average_volume > 0.0
                    else 1.0
                )
                return_to_volatility = (
                    trend / volatility if volatility > 0.0 else 0.0
                )
                matrix[global_index] = (
                    1.0,
                    average,
                    short_average,
                    medium_average,
                    high,
                    low,
                    closes[local_index - 1],
                    trend,
                    medium_return,
                    volatility,
                    long_average,
                    long_high,
                    long_return,
                    long_drawdown,
                    rolling_sharpe,
                    volume_ratio,
                    return_to_volatility,
                    pullback,
                )
        matrix.setflags(write=False)
        self._lookback_cache[lookback] = matrix
        return matrix

    def _profile_actions(self, parameters: CandidateParameters) -> array:
        features = self.features(parameters.lookback)
        actions = array("b", [0]) * len(self.rows)
        states: dict[str, list[float | bool | int]] = {}
        profile = parameters.profile
        threshold = parameters.threshold
        for start, end in self.date_ranges:
            evaluations: list[tuple[int, str, float, bool, bool, float, list[float | bool | int]]] = []
            for index in range(start, end):
                ticker = self.tickers[index]
                close = self.close[index]
                state = states.setdefault(ticker, [False, 0.0, 0, 0.0])
                row = features[index]
                buy = False
                sell = False
                score = -999.0
                if row[READY]:
                    average = row[AVERAGE]
                    short_average = row[SHORT_AVERAGE]
                    medium_average = row[MEDIUM_AVERAGE]
                    high = row[HIGH]
                    previous = row[PREVIOUS]
                    trend = row[TREND]
                    medium_return = row[MEDIUM_RETURN]
                    volatility = row[VOLATILITY]
                    long_average = row[LONG_AVERAGE]
                    long_high = row[LONG_HIGH]
                    long_return = row[LONG_RETURN]
                    long_drawdown = row[LONG_DRAWDOWN]
                    rolling_sharpe = row[ROLLING_SHARPE]
                    volume_ratio = row[VOLUME_RATIO]
                    return_to_volatility = row[RETURN_TO_VOLATILITY]
                    pullback = row[PULLBACK]
                    rsi = self.rsi[index]
                    in_position = bool(state[0])
                    score = (
                        rolling_sharpe
                        + medium_return * 4.0
                        + long_return * 2.0
                        - volatility
                    )
                    if profile == "long_regime_momentum":
                        score = (
                            rolling_sharpe
                            + long_return * 3.0
                            + medium_return * 2.0
                            - volatility
                        )
                        buy = (
                            close >= long_average
                            and medium_average >= long_average * 0.98
                            and long_return > 0.0
                        )
                        sell = in_position and (
                            close < long_average * 0.97 or long_drawdown > 0.18
                        )
                    elif profile == "quality_trend_hold":
                        score = (
                            medium_return * 3.0
                            + long_return * 2.0
                            + rolling_sharpe * 0.5
                            - volatility * 0.5
                        )
                        buy = (
                            close >= medium_average >= long_average * 0.97
                            and medium_return >= -0.02
                            and volatility <= 0.28
                        )
                        sell = in_position and (
                            close < medium_average * 0.96 or medium_return < -0.08
                        )
                    elif profile == "volatility_breakout_hold":
                        score = (
                            (close / long_high - 0.96) * 6.0
                            + medium_return * 3.0
                            + volume_ratio * 0.1
                            - volatility
                            if long_high
                            else -999.0
                        )
                        buy = (
                            long_high > 0.0
                            and close >= long_high * 0.96
                            and volume_ratio >= 0.85
                            and volatility <= 0.32
                            and medium_return >= 0.0
                        )
                        sell = in_position and (
                            close < medium_average * 0.95 or long_drawdown > 0.2
                        )
                    elif profile == "rolling_sharpe_momentum":
                        score = rolling_sharpe + trend * 2.0 - volatility
                        buy = (
                            rolling_sharpe >= threshold / 10.0
                            and close >= medium_average
                            and trend > 0.0
                        )
                        sell = in_position and (
                            rolling_sharpe <= 0.0 or close < medium_average
                        )
                    elif profile == "dual_sma_trend":
                        score = (
                            medium_return * 3.0
                            + (short_average / medium_average - 1.0) * 8.0
                            if medium_average
                            else 0.0
                        )
                        buy = (
                            short_average > medium_average > average * 0.98
                            and close >= short_average
                        )
                        sell = in_position and (
                            short_average < medium_average or close < average
                        )
                    elif profile == "low_vol_momentum":
                        score = trend * 3.0 + medium_return * 2.0 - volatility * 1.5
                        buy = (
                            trend >= threshold
                            and medium_return >= 0.0
                            and volatility <= 0.28
                            and close >= medium_average
                        )
                        sell = in_position and (
                            close < medium_average * 0.96
                            or medium_return < -0.06
                            or long_drawdown > 0.22
                        )
                    elif profile == "breakout_volume":
                        score = (
                            (close / high - 0.99) * 10.0
                            + volume_ratio * 0.2
                            + trend * 2.0
                            if high
                            else -999.0
                        )
                        buy = (
                            high > 0.0
                            and close >= high * 0.995
                            and volume_ratio >= threshold
                            and trend >= 0.0
                        )
                        sell = in_position and close < short_average
                    elif profile == "rsi_trend_rebound":
                        score = (
                            medium_return * 3.0
                            + (55.0 - abs(rsi - 45.0)) / 50.0
                            - volatility
                        )
                        buy = (
                            close >= medium_average
                            and trend >= 0.0
                            and 35.0 <= rsi <= 62.0
                            and close >= previous
                        )
                        sell = in_position and (
                            rsi >= 72.0 or close < medium_average
                        )
                    elif profile == "mean_reversion_band":
                        score = pullback * 2.0 + (50.0 - rsi) / 50.0 - volatility
                        buy = (
                            close
                            <= average * (1.0 - max(0.0, min(0.20, threshold)))
                            and rsi <= 45.0
                        )
                        sell = in_position and (
                            close >= medium_average or rsi >= 60.0
                        )
                    elif profile == "return_to_volatility":
                        score = return_to_volatility + medium_return * 2.0
                        buy = (
                            return_to_volatility >= threshold * 4.0
                            and close >= medium_average
                        )
                        sell = in_position and (
                            return_to_volatility <= 0.0 or close < medium_average
                        )
                    elif profile == "cash_preserving_trend":
                        score = rolling_sharpe + trend * 2.0 - volatility * 2.0
                        buy = (
                            trend >= threshold
                            and rolling_sharpe > 0.05
                            and volatility <= 0.3
                        )
                        sell = in_position and (
                            trend < 0.01 or rolling_sharpe < 0.0
                        )
                    else:
                        score = trend * 2.0 + medium_return - volatility
                        buy = (
                            trend >= threshold
                            and close >= average
                            and close >= previous
                        )
                        sell = in_position and close < average
                    if in_position and float(state[1]) > 0.0:
                        pnl = close / float(state[1]) - 1.0
                        trailing_stop = (
                            float(state[3]) > 0.0 and close < float(state[3]) * 0.93
                        )
                        sell = (
                            sell
                            or pnl <= -parameters.stop_loss_pct
                            or pnl >= parameters.take_profit_pct
                            or trailing_stop
                        )
                evaluations.append(
                    (index, ticker, close, buy, sell, score, state)
                )

            open_positions = sum(1 for state in states.values() if bool(state[0]))
            open_slots = max(0, parameters.max_positions - open_positions)
            ranked = [
                item for item in evaluations if item[3] and not bool(item[6][0])
            ]
            ranked.sort(key=lambda item: (item[5], item[1]), reverse=True)
            selected = {item[1] for item in ranked[:open_slots]}
            for index, ticker, close, _, sell, _, state in evaluations:
                if sell and bool(state[0]):
                    actions[index] = -1
                    state[:] = [False, 0.0, 0, 0.0]
                elif ticker in selected:
                    actions[index] = 1
                    state[:] = [True, close, 0, close]
                elif bool(state[0]):
                    state[2] = int(state[2]) + 1
                    state[3] = max(float(state[3]), close)
        return actions

    def _compiled_actions(
        self,
        strategy_ir: StrategyIR,
        parameters: CandidateParameters,
    ) -> array:
        actions = array("b", [0]) * len(self.rows)
        states: dict[str, list[float | bool]] = {}
        entry_conditions = [
            item for item in strategy_ir.entry_conditions if item.universe_rank_pct is None
        ]
        rank_conditions = [
            item for item in strategy_ir.entry_conditions if item.universe_rank_pct is not None
        ]
        exit_conditions = [
            item for item in strategy_ir.exit_conditions if item.universe_rank_pct is None
        ]
        for start, end in self.date_ranges:
            entries: list[tuple[int, str, float]] = []
            exits: list[tuple[int, str]] = []
            for index in range(start, end):
                ticker = self.tickers[index]
                close = self.close[index]
                state = states.setdefault(ticker, [False, 0.0])
                if bool(state[0]):
                    exit_match = bool(exit_conditions) and all(
                        self._condition_matches(condition, index)
                        for condition in exit_conditions
                    )
                    entry_price = float(state[1])
                    pnl = close / entry_price - 1.0 if entry_price else 0.0
                    if (
                        exit_match
                        or pnl <= -parameters.stop_loss_pct
                        or pnl >= parameters.take_profit_pct
                    ):
                        exits.append((index, ticker))
                elif all(
                    self._condition_matches(condition, index)
                    for condition in entry_conditions
                ):
                    entries.append((index, ticker, close))

            for condition in rank_conditions:
                scored: list[tuple[str, float]] = []
                for index in range(start, end):
                    value = self._current_metric(condition.left, index)
                    if value is not None:
                        scored.append((self.tickers[index], value))
                top = condition.operator in {
                    ConditionOperator.GT,
                    ConditionOperator.GTE,
                }
                scored.sort(key=lambda item: item[1], reverse=top)
                cutoff = max(
                    1,
                    int(len(scored) * float(condition.universe_rank_pct or 0.0)),
                )
                kept = {ticker for ticker, _ in scored[:cutoff]}
                entries = [entry for entry in entries if entry[1] in kept]

            for index, ticker in exits:
                actions[index] = -1
                states[ticker] = [False, 0.0]
            held = sum(1 for state in states.values() if bool(state[0]))
            for index, ticker, close in entries:
                if held >= parameters.max_positions:
                    break
                actions[index] = 1
                states[ticker] = [True, close]
                held += 1
        return actions

    def _condition_matches(self, condition: Condition, index: int) -> bool:
        if condition.consecutive is not None:
            key = condition.model_dump_json()
            cached = self._condition_cache.get(key)
            if cached is None:
                base = condition.model_copy(update={"consecutive": None})
                base_matches = np.asarray(
                    [
                        self._base_condition_matches(base, row_index)
                        for row_index in range(len(self.rows))
                    ],
                    dtype=np.bool_,
                )
                cached = np.zeros(len(self.rows), dtype=np.bool_)
                for indices in self.indices_by_ticker.values():
                    streak = 0
                    for row_index in indices:
                        streak = streak + 1 if base_matches[row_index] else 0
                        cached[row_index] = streak >= int(condition.consecutive)
                cached.setflags(write=False)
                self._condition_cache[key] = cached
            return bool(cached[index])
        return self._base_condition_matches(condition, index)

    def _base_condition_matches(self, condition: Condition, index: int) -> bool:
        # Flags and ratios are conditions in disguise. The compiler rewrites them when
        # it emits Python; this evaluator - the one that actually runs - has to make the
        # same rewrite, or a rule that "compiled" would silently match nothing here.
        flag = boolean_comparison(condition.left)
        if flag is not None:
            return self._boolean_comparison_matches(condition, flag, index)
        window_rule = boolean_window_rule(condition.left)
        if window_rule is not None:
            return self._boolean_window_matches(condition, window_rule, index)
        if isinstance(condition.right, str):
            left = self._current_metric(condition.left, index)
            right = self._condition_series_value(
                condition.right,
                condition.window,
                condition.aggregate,
                index,
            )
        else:
            left = self._condition_series_value(
                condition.left,
                condition.window,
                condition.aggregate,
                index,
            )
            right = (
                float(condition.right) * percent_scale(condition.left)
                if isinstance(condition.right, (int, float))
                else None
            )
        if left is None:
            return False
        operator = condition.operator
        if operator == ConditionOperator.BETWEEN:
            if not isinstance(condition.right, list) or len(condition.right) != 2:
                return False
            low, high = float(condition.right[0]), float(condition.right[1])
            if condition.scale is not None:
                low *= condition.scale
                high *= condition.scale
            return low <= left <= high
        if right is None:
            return False
        if condition.scale is not None:
            right *= condition.scale
        if operator in {
            ConditionOperator.CROSS_ABOVE,
            ConditionOperator.CROSS_BELOW,
        }:
            previous = int(self.previous_index[index])
            if previous < 0 or not isinstance(condition.right, str):
                return False
            previous_left = self._current_metric(condition.left, previous)
            previous_right = self._condition_series_value(
                condition.right,
                condition.window,
                condition.aggregate,
                previous,
            )
            if previous_left is None or previous_right is None:
                return False
            if condition.scale is not None:
                previous_right *= condition.scale
            if operator == ConditionOperator.CROSS_ABOVE:
                return left > right and previous_left <= previous_right
            return left < right and previous_left >= previous_right
        if operator == ConditionOperator.LT:
            return left < right
        if operator == ConditionOperator.LTE:
            return left <= right
        if operator == ConditionOperator.GT:
            return left > right
        if operator == ConditionOperator.GTE:
            return left >= right
        if operator == ConditionOperator.EQ:
            return left == right
        if operator == ConditionOperator.NE:
            return left != right
        return False

    def _boolean_comparison_matches(
        self, condition: Condition, rule: tuple[str, str, str], index: int
    ) -> bool:
        left_metric, operator, right_metric = rule
        asserted = _flag_is_asserted(condition)
        if asserted is None:
            return False
        left = self._current_metric(left_metric, index)
        right = self._current_metric(right_metric, index)
        if left is None or right is None:
            return False
        holds = left > right if operator == ">" else left < right
        return holds if asserted else not holds

    def _boolean_window_matches(
        self, condition: Condition, rule: tuple[str, str, str, int, float], index: int
    ) -> bool:
        metric, aggregate, comparison, window, factor = rule
        asserted = _flag_is_asserted(condition)
        if asserted is None:
            return False
        close = self._current_metric("close", index)
        extreme = self._condition_series_value(metric, window, aggregate, index)
        if close is None or extreme is None:
            return False
        threshold = extreme * factor
        holds = close >= threshold if comparison == ">=" else close <= threshold
        return holds if asserted else not holds

    def _condition_series_value(
        self,
        metric: str,
        window: int | None,
        aggregate: str | None,
        index: int,
    ) -> float | None:
        if window and aggregate:
            values = self._rolling_metric(metric, window, aggregate)
            value = float(values[index])
            return value if isfinite(value) else None
        return self._current_metric(metric, index)

    def _current_metric(self, metric: str, index: int) -> float | None:
        value = float(self._metric_series(metric)[index])
        return value if isfinite(value) else None

    def _metric_series(self, metric: str) -> np.ndarray:
        normalized = canonical_metric(metric)
        cached = self._metric_cache.get(normalized)
        if cached is not None:
            return cached
        if normalized in {"price", "close"}:
            return self.close
        if normalized == "volume":
            return self.volume
        if normalized == "rsi":
            return self.rsi
        ratio = derived_ratio(metric)
        if ratio is not None:
            series = self._derived_ratio_series(ratio)
            self._metric_cache[normalized] = series
            return series
        spec = derived_series_spec(normalized)
        if spec is not None:
            series = self._derived_from_bars(spec)
            self._metric_cache[normalized] = series
            return series
        values: list[float] = []
        for row in self.rows:
            raw = row.get(metric)
            if raw is None and normalized != metric:
                raw = row.get(normalized)
            if not isinstance(raw, (int, float)) or isinstance(raw, bool):
                values.append(np.nan)
                continue
            parsed = float(raw)
            values.append(parsed if isfinite(parsed) else np.nan)
        source = np.asarray(values, dtype=np.float64)
        source.setflags(write=False)
        self._metric_cache[normalized] = source
        return source

    def _derived_ratio_series(self, ratio: tuple[str, str, int]) -> np.ndarray:
        """A ratio metric like volume_ratio_20, evaluated the compiler's way.

        window > 0 divides by the denominator's trailing average; window 0 divides by
        the denominator's current bar.
        """

        numerator_name, denominator_name, window = ratio
        numerator = self._metric_series(numerator_name)
        denominator = (
            self._rolling_metric(denominator_name, window, "avg")
            if window
            else self._metric_series(denominator_name)
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            series = np.divide(
                numerator,
                denominator,
                out=np.full(len(self.rows), np.nan, dtype=np.float64),
                where=np.isfinite(denominator) & (denominator != 0.0),
            )
        series.setflags(write=False)
        return series

    def _daily_returns(self) -> np.ndarray:
        cached = self._metric_cache.get("__daily_returns__")
        if cached is not None:
            return cached
        out = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            closes = self.close[indices]
            if len(closes) > 1:
                prior, later = closes[:-1], closes[1:]
                with np.errstate(divide="ignore", invalid="ignore"):
                    out[indices[1:]] = np.where(prior != 0.0, later / prior - 1.0, np.nan)
        out.setflags(write=False)
        self._metric_cache["__daily_returns__"] = out
        return out

    def _derived_from_bars(self, spec: tuple[str, str, int]) -> np.ndarray:
        """Realised volatility, relative strength, or a cross-sectional percentile.

        All three are answerable from the OHLCV already loaded; they were untranslatable
        only because the derivation had not been written, and that gap was silently
        turning a user's strategy into a generic template.
        """

        kind, base, window = spec
        out = np.full(len(self.rows), np.nan, dtype=np.float64)

        if kind == "realized_volatility":
            returns = self._daily_returns()
            for indices in self.indices_by_ticker.values():
                series = returns[indices]
                for position in range(len(indices)):
                    start = position - window + 1
                    if start < 1:
                        continue
                    sample = series[start : position + 1]
                    sample = sample[np.isfinite(sample)]
                    if sample.size >= 2:
                        # Annualised, matching how the thresholds are written
                        # (realized_volatility_20d <= 0.25 means 25% a year).
                        out[indices[position]] = float(sample.std(ddof=1) * sqrt(252))

        elif kind == "relative_strength":
            own = np.full(len(self.rows), np.nan, dtype=np.float64)
            for indices in self.indices_by_ticker.values():
                closes = self.close[indices]
                if len(closes) > window:
                    prior, later = closes[:-window], closes[window:]
                    with np.errstate(divide="ignore", invalid="ignore"):
                        own[indices[window:]] = np.where(
                            prior > 0.0, later / prior - 1.0, np.nan
                        )
            # Excess over the same-date universe mean, so "상대강도" means the same
            # thing here as it does in the screen.
            for start, end in self.date_ranges:
                window_slice = own[start:end]
                finite = window_slice[np.isfinite(window_slice)]
                if finite.size:
                    out[start:end] = window_slice - float(finite.mean())

        elif kind == "percentile":
            values = self._metric_series(base)
            for start, end in self.date_ranges:
                day = values[start:end]
                finite_mask = np.isfinite(day)
                finite = day[finite_mask]
                if finite.size < 2:
                    continue
                order = finite.argsort().argsort().astype(np.float64)
                ranks = order / (finite.size - 1)
                filled = np.full(day.shape, np.nan)
                filled[finite_mask] = ranks
                out[start:end] = filled

        out.setflags(write=False)
        return out

    def _rolling_metric(self, metric: str, window: int, aggregate: str) -> np.ndarray:
        normalized_aggregate = aggregate.strip().lower()
        key = (metric.strip().lower(), window, normalized_aggregate)
        cached = self._rolling_cache.get(key)
        if cached is not None:
            return cached
        source = self._metric_series(metric)
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            values = source[indices]
            finite = np.isfinite(values)
            if normalized_aggregate in {"avg", "sum"}:
                totals = np.concatenate(
                    ([0.0], np.cumsum(np.where(finite, values, 0.0)))
                )
                counts = np.concatenate(([0], np.cumsum(finite, dtype=np.int64)))
                for local_index, global_index in enumerate(indices):
                    start = max(0, local_index - window)
                    count = int(counts[local_index] - counts[start])
                    if count:
                        total = float(totals[local_index] - totals[start])
                        output[global_index] = (
                            total / count
                            if normalized_aggregate == "avg"
                            else total
                        )
                continue

            candidates: deque[int] = deque()
            for local_index, global_index in enumerate(indices):
                prior_index = local_index - 1
                if prior_index >= 0 and finite[prior_index]:
                    if normalized_aggregate == "max":
                        while candidates and values[candidates[-1]] <= values[prior_index]:
                            candidates.pop()
                    elif normalized_aggregate == "min":
                        while candidates and values[candidates[-1]] >= values[prior_index]:
                            candidates.pop()
                    candidates.append(prior_index)
                oldest = local_index - window
                while candidates and candidates[0] < oldest:
                    candidates.popleft()
                if not candidates:
                    continue
                selected = (
                    candidates[-1]
                    if normalized_aggregate == "last"
                    else candidates[0]
                )
                output[global_index] = float(values[selected])
        output.setflags(write=False)
        self._rolling_cache[key] = output
        return output


def _optional_metric(row: Mapping[str, Any], *keys: str) -> float:
    """The first numeric value among `keys`, or NaN when the bar carries none."""

    for key in keys:
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        parsed = float(value)
        if isfinite(parsed):
            return parsed
    return float("nan")


def _flag_is_asserted(condition: Condition) -> bool | None:
    """Whether a flag-style condition asserts its rule or negates it."""

    if not isinstance(condition.right, (int, float)) or isinstance(condition.right, bool):
        return None
    truthy = float(condition.right) != 0.0
    if condition.operator in {
        ConditionOperator.EQ,
        ConditionOperator.GTE,
        ConditionOperator.GT,
    }:
        return truthy
    if condition.operator in {
        ConditionOperator.NE,
        ConditionOperator.LT,
        ConditionOperator.LTE,
    }:
        return not truthy
    return None


def _prefix_average(prefix: np.ndarray, start: int, end: int) -> float:
    count = end - start
    return float((prefix[end] - prefix[start]) / count) if count > 0 else 0.0


def _prior_rolling_extreme(
    values: np.ndarray,
    window: int,
    *,
    maximum: bool,
) -> np.ndarray:
    output = np.zeros(len(values), dtype=np.float64)
    candidates: deque[int] = deque()
    for index in range(len(values)):
        prior = index - 1
        if prior >= 0:
            while candidates and (
                values[candidates[-1]] <= values[prior]
                if maximum
                else values[candidates[-1]] >= values[prior]
            ):
                candidates.pop()
            candidates.append(prior)
        start = max(0, index - window)
        while candidates and candidates[0] < start:
            candidates.popleft()
        if candidates:
            output[index] = values[candidates[0]]
    return output
