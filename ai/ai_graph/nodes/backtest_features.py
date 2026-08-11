from __future__ import annotations

from array import array
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
import re
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from ai_graph.nodes.condition_compiler import (
    boolean_comparison,
    boolean_window_rule,
    canonical_metric,
    derived_ratio,
    derived_series_spec,
    percent_scale,
)
from ai_graph.quant_strategy import (
    AUTOMATIC_TOURNAMENT_PROFILES,
    MOMENTUM_LONG_LOOKBACK,
    compute_academic_factor_arrays,
)
from ai_graph.schemas import CandidateParameters, Condition, ConditionOperator, StrategyIR


FEATURE_DEFINITION_VERSION = "structured-features.v3"

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
MOMENTUM_12_1 = 18
SMA_50 = 19
SMA_200 = 20
REALIZED_VOLATILITY_21D = 21
REBALANCE_ELIGIBLE = 22
FEATURE_COLUMN_COUNT = 23


@dataclass(frozen=True)
class FeaturePreparationStats:
    input_rows: int
    ticker_count: int
    cached_lookbacks: tuple[int, ...]
    estimated_bytes: int


class PreparedFeatureStore:
    """Columnar, read-only feature arrays shared by all structured candidates."""

    def __init__(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        rows_are_sorted: bool = False,
    ) -> None:
        self.rows = (
            tuple(rows)
            if rows_are_sorted
            else tuple(
                sorted(
                    rows,
                    key=lambda row: (
                        str(row.get("date") or ""),
                        str(row.get("ticker") or "000000").zfill(6),
                    ),
                )
            )
        )
        self.dates = tuple(str(row.get("date") or "") for row in self.rows)
        self.tickers = tuple(str(row.get("ticker") or "000000").zfill(6) for row in self.rows)
        self.close = np.asarray([float(row["close"]) for row in self.rows], dtype=np.float64)
        self.open = np.asarray(
            [float(row.get("open", row["close"]) or row["close"]) for row in self.rows],
            dtype=np.float64,
        )
        self.high = np.asarray(
            [float(row.get("high", row["close"]) or row["close"]) for row in self.rows],
            dtype=np.float64,
        )
        self.low = np.asarray(
            [float(row.get("low", row["close"]) or row["close"]) for row in self.rows],
            dtype=np.float64,
        )
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
        self.open.setflags(write=False)
        self.high.setflags(write=False)
        self.low.setflags(write=False)
        self.volume.setflags(write=False)
        self.rsi.setflags(write=False)
        groups: dict[str, list[int]] = {}
        for index, ticker in enumerate(self.tickers):
            groups.setdefault(ticker, []).append(index)
        self.indices_by_ticker = {
            ticker: np.asarray(indices, dtype=np.int64) for ticker, indices in groups.items()
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
            + self.open.nbytes
            + self.high.nbytes
            + self.low.nbytes
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
            count = len(indices)
            if count <= 1:
                continue
            academic_factors = compute_academic_factor_arrays(closes)
            close_prefix = np.concatenate(([0.0], np.cumsum(closes)))
            volume_prefix = np.concatenate(([0.0], np.cumsum(volumes)))
            returns = np.zeros(count, dtype=np.float64)
            before = closes[:-1]
            after = closes[1:]
            nonzero_before = before != 0.0
            returns[1:][nonzero_before] = (
                after[nonzero_before] / before[nonzero_before] - 1.0
            )
            return_prefix = np.concatenate(([0.0], np.cumsum(returns)))
            return_square_prefix = np.concatenate(([0.0], np.cumsum(returns * returns)))
            main_highs = _prior_rolling_extreme(closes, lookback, maximum=True)
            main_lows = _prior_rolling_extreme(closes, lookback, maximum=False)
            long_limit = max(60, lookback)
            long_highs = _prior_rolling_extreme(closes, long_limit, maximum=True)

            local = np.arange(count, dtype=np.int64)
            # A window is only itself once there are `lookback` prior bars to fill it.
            # This was `local > 0`, so every indicator reported a shorter window under
            # its own name: a 20-day average was the previous close on the second bar,
            # and `high` was a single prior close, letting a breakout fire on bar two
            # against a one-day "high". Rows inside the warm-up are left out of `target`
            # and so stay zeroed, which keeps READY false and keeps them untradable
            # rather than tradable on a number nobody measured.
            #
            # This matters most where it is least visible: a name that lists mid-backtest
            # warms up during its post-IPO stretch, its most volatile. Enforcing it moved
            # individual candidates by up to 16 percentage points of ten-year return on
            # the live universe.
            #
            # `window` still clamps to `local` so the index arithmetic below never goes
            # negative for the rows being skipped; the mask, not the arithmetic, is what
            # excludes them.
            valid = local >= lookback
            target = indices[valid]
            window = np.minimum(lookback, local)
            start = local - window
            short_window = np.minimum(np.maximum(3, window // 4), local)
            medium_window = np.minimum(np.maximum(5, window // 2), local)
            long_window = np.minimum(long_limit, local)
            short_start = local - short_window
            medium_start = local - medium_window
            long_start = local - long_window

            average = np.zeros(count, dtype=np.float64)
            short_average = np.zeros(count, dtype=np.float64)
            medium_average = np.zeros(count, dtype=np.float64)
            long_average = np.zeros(count, dtype=np.float64)
            average[valid] = (
                close_prefix[local[valid]] - close_prefix[start[valid]]
            ) / window[valid]
            short_average[valid] = (
                close_prefix[local[valid]] - close_prefix[short_start[valid]]
            ) / short_window[valid]
            medium_average[valid] = (
                close_prefix[local[valid]] - close_prefix[medium_start[valid]]
            ) / medium_window[valid]
            long_average[valid] = (
                close_prefix[local[valid]] - close_prefix[long_start[valid]]
            ) / long_window[valid]

            trend = _safe_return(closes, closes[start])
            medium_return = _safe_return(closes, closes[medium_start])
            long_return = _safe_return(closes, closes[long_start])
            pullback = _safe_ratio(main_highs - closes, main_highs, positive=True)
            volatility = _safe_ratio(main_highs - main_lows, average)
            long_drawdown = _safe_ratio(long_highs - closes, long_highs, positive=True)

            return_count = np.maximum(0, window - 1)
            return_valid = return_count > 0
            return_start = start + 1
            total = return_prefix[local] - return_prefix[return_start]
            square_total = return_square_prefix[local] - return_square_prefix[return_start]
            mean_return = np.zeros(count, dtype=np.float64)
            mean_return[return_valid] = total[return_valid] / return_count[return_valid]
            variance = np.zeros(count, dtype=np.float64)
            variance[return_valid] = np.maximum(
                0.0,
                square_total[return_valid] / return_count[return_valid]
                - mean_return[return_valid] * mean_return[return_valid],
            )
            rolling_sharpe = np.zeros(count, dtype=np.float64)
            nonzero_variance = variance > 0.0
            rolling_sharpe[nonzero_variance] = (
                mean_return[nonzero_variance] / np.sqrt(variance[nonzero_variance])
            )

            average_volume = np.zeros(count, dtype=np.float64)
            average_volume[valid] = (
                volume_prefix[local[valid]] - volume_prefix[start[valid]]
            ) / window[valid]
            volume_ratio = np.zeros(count, dtype=np.float64)
            positive_average_volume = valid & (average_volume > 0.0)
            volume_ratio[valid] = 1.0
            volume_ratio[positive_average_volume] = (
                volumes[positive_average_volume] / average_volume[positive_average_volume]
            )
            return_to_volatility = _safe_ratio(trend, volatility, positive=True)

            matrix[target, READY] = 1.0
            matrix[target, AVERAGE] = average[valid]
            matrix[target, SHORT_AVERAGE] = short_average[valid]
            matrix[target, MEDIUM_AVERAGE] = medium_average[valid]
            matrix[target, HIGH] = main_highs[valid]
            matrix[target, LOW] = main_lows[valid]
            matrix[target, PREVIOUS] = closes[local[valid] - 1]
            matrix[target, TREND] = trend[valid]
            matrix[target, MEDIUM_RETURN] = medium_return[valid]
            matrix[target, VOLATILITY] = volatility[valid]
            matrix[target, LONG_AVERAGE] = long_average[valid]
            matrix[target, LONG_HIGH] = long_highs[valid]
            matrix[target, LONG_RETURN] = long_return[valid]
            matrix[target, LONG_DRAWDOWN] = long_drawdown[valid]
            matrix[target, ROLLING_SHARPE] = rolling_sharpe[valid]
            matrix[target, VOLUME_RATIO] = volume_ratio[valid]
            matrix[target, RETURN_TO_VOLATILITY] = return_to_volatility[valid]
            matrix[target, PULLBACK] = pullback[valid]
            matrix[target, MOMENTUM_12_1] = academic_factors.momentum_12_1[valid]
            matrix[target, SMA_50] = academic_factors.sma_50[valid]
            matrix[target, SMA_200] = academic_factors.sma_200[valid]
            matrix[target, REALIZED_VOLATILITY_21D] = (
                academic_factors.realized_volatility_21d[valid]
            )
            matrix[target, REBALANCE_ELIGIBLE] = academic_factors.rebalance_eligible[valid]
        matrix.setflags(write=False)
        self._lookback_cache[lookback] = matrix
        return matrix

    def _profile_actions(self, parameters: CandidateParameters) -> array:
        features = self.features(parameters.lookback)
        if parameters.profile in AUTOMATIC_TOURNAMENT_PROFILES:
            return self._rotation_profile_actions(parameters, features)
        actions = array("b", [0]) * len(self.rows)
        states: dict[str, list[float | bool | int]] = {}
        profile = parameters.profile
        threshold = parameters.threshold
        for start, end in self.date_ranges:
            evaluations: list[
                tuple[int, str, float, bool, bool, float, list[float | bool | int]]
            ] = []
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
                    momentum_12_1 = row[MOMENTUM_12_1]
                    sma_50 = row[SMA_50]
                    sma_200 = row[SMA_200]
                    realized_volatility_21d = row[REALIZED_VOLATILITY_21D]
                    rebalance_eligible = bool(row[REBALANCE_ELIGIBLE])
                    rsi = self.rsi[index]
                    in_position = bool(state[0])
                    score = rolling_sharpe + medium_return * 4.0 + long_return * 2.0 - volatility
                    if profile == "academic_momentum_trend":
                        factors_available = all(
                            isfinite(value)
                            for value in (
                                momentum_12_1,
                                sma_50,
                                sma_200,
                                realized_volatility_21d,
                            )
                        )
                        if factors_available:
                            score = (
                                momentum_12_1 * 4.0
                                + (sma_50 / sma_200 - 1.0) * 2.0
                                - realized_volatility_21d
                            )
                            buy = (
                                rebalance_eligible
                                and momentum_12_1 > threshold
                                and close >= sma_200
                                and sma_50 >= sma_200
                                and realized_volatility_21d <= 0.35
                            )
                            sell = in_position and (
                                close < sma_200 * 0.95
                                or (
                                    rebalance_eligible
                                    and (momentum_12_1 <= 0.0 or sma_50 < sma_200)
                                )
                            )
                    elif profile == "long_regime_momentum":
                        score = (
                            rolling_sharpe + long_return * 3.0 + medium_return * 2.0 - volatility
                        )
                        buy = (
                            close >= long_average
                            and medium_average >= long_average * 0.98
                            and long_return > 0.0
                        )
                        sell = in_position and (close < long_average * 0.97 or long_drawdown > 0.18)
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
                        sell = in_position and (rolling_sharpe <= 0.0 or close < medium_average)
                    elif profile == "dual_sma_trend":
                        score = (
                            medium_return * 3.0 + (short_average / medium_average - 1.0) * 8.0
                            if medium_average
                            else 0.0
                        )
                        buy = (
                            short_average > medium_average > average * 0.98
                            and close >= short_average
                        )
                        sell = in_position and (short_average < medium_average or close < average)
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
                            (close / high - 0.99) * 10.0 + volume_ratio * 0.2 + trend * 2.0
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
                        score = medium_return * 3.0 + (55.0 - abs(rsi - 45.0)) / 50.0 - volatility
                        buy = (
                            close >= medium_average
                            and trend >= 0.0
                            and 35.0 <= rsi <= 62.0
                            and close >= previous
                        )
                        sell = in_position and (rsi >= 72.0 or close < medium_average)
                    elif profile == "mean_reversion_band":
                        score = pullback * 2.0 + (50.0 - rsi) / 50.0 - volatility
                        buy = (
                            close <= average * (1.0 - max(0.0, min(0.20, threshold)))
                            and rsi <= 45.0
                        )
                        sell = in_position and (close >= medium_average or rsi >= 60.0)
                    elif profile == "return_to_volatility":
                        score = return_to_volatility + medium_return * 2.0
                        buy = return_to_volatility >= threshold * 4.0 and close >= medium_average
                        sell = in_position and (
                            return_to_volatility <= 0.0 or close < medium_average
                        )
                    elif profile == "cash_preserving_trend":
                        score = rolling_sharpe + trend * 2.0 - volatility * 2.0
                        buy = trend >= threshold and rolling_sharpe > 0.05 and volatility <= 0.3
                        sell = in_position and (trend < 0.01 or rolling_sharpe < 0.0)
                    else:
                        score = trend * 2.0 + medium_return - volatility
                        buy = trend >= threshold and close >= average and close >= previous
                        sell = in_position and close < average
                    if in_position and float(state[1]) > 0.0:
                        # The trailing stop is part of the profile's own rule - it tracks
                        # the peak since entry, which the engine does not model - so it
                        # stays here. The fixed stop-loss and take-profit do not: the
                        # engine applies both against the price actually paid, and this
                        # loop only knows the signal-day close. Keeping both meant one
                        # stop evaluated twice from two entry prices a bar apart.
                        trailing_stop = float(state[3]) > 0.0 and close < float(state[3]) * (
                            1.0 - parameters.trailing_stop_pct
                        )
                        sell = sell or trailing_stop
                evaluations.append((index, ticker, close, buy, sell, score, state))

            open_positions = sum(1 for state in states.values() if bool(state[0]))
            open_slots = max(0, parameters.max_positions - open_positions)
            ranked = [item for item in evaluations if item[3] and not bool(item[6][0])]
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

    def _rotation_profile_actions(
        self,
        parameters: CandidateParameters,
        features: np.ndarray,
    ) -> array:
        """Monthly cross-sectional momentum rotation with past-only features.

        The previous automatic profiles treated each stock independently and took
        profits at a fixed percentage. That systematically cut the few large winners
        which drive a momentum portfolio. Rotation instead constructs one portfolio:
        rank the whole universe on a fixed schedule, keep leaders that remain leaders,
        and replace only names that fall out of the target set.
        """

        actions = array("b", [0]) * len(self.rows)
        states: dict[str, list[float | bool | int]] = {}
        profile = parameters.profile
        threshold = parameters.threshold

        for date_index, (start, end) in enumerate(self.date_ranges):
            rotation_day = (
                date_index >= MOMENTUM_LONG_LOOKBACK
                and (date_index - MOMENTUM_LONG_LOOKBACK) % parameters.rebalance_interval_days == 0
            )
            observations: list[tuple[int, str, float, float, float, float, float]] = []
            for index in range(start, end):
                row = features[index]
                if not row[READY]:
                    continue
                values = [
                    row[MOMENTUM_12_1],
                    row[MEDIUM_RETURN],
                    row[SMA_200],
                ]
                if profile == "risk_adjusted_momentum_rotation":
                    values.append(row[REALIZED_VOLATILITY_21D])
                if not all(isfinite(value) for value in values):
                    continue
                observations.append(
                    (
                        index,
                        self.tickers[index],
                        float(self.close[index]),
                        float(row[MOMENTUM_12_1]),
                        float(row[MEDIUM_RETURN]),
                        float(row[REALIZED_VOLATILITY_21D]),
                        float(row[SMA_200]),
                    )
                )

            target: set[str] = set()
            if rotation_day and observations:
                momentum_ranks = _percentile_ranks(
                    [(ticker, momentum) for _, ticker, _, momentum, _, _, _ in observations]
                )
                medium_ranks = _percentile_ranks(
                    [(ticker, medium) for _, ticker, _, _, medium, _, _ in observations]
                )
                risk_adjusted_long_ranks = (
                    _percentile_ranks(
                        [
                            (ticker, momentum / max(volatility, 0.05))
                            for _, ticker, _, momentum, _, volatility, _ in observations
                        ]
                    )
                    if profile == "risk_adjusted_momentum_rotation"
                    else {}
                )
                risk_adjusted_medium_ranks = (
                    _percentile_ranks(
                        [
                            (ticker, medium / max(volatility, 0.05))
                            for _, ticker, _, _, medium, volatility, _ in observations
                        ]
                    )
                    if profile == "risk_adjusted_momentum_rotation"
                    else {}
                )
                ranked: list[tuple[float, str]] = []
                for _, ticker, close, momentum, medium, volatility, sma_200 in observations:
                    if profile == "relative_momentum_rotation":
                        eligible = momentum > threshold and close >= sma_200
                        score = momentum_ranks[ticker]
                    elif profile == "risk_adjusted_momentum_rotation":
                        eligible = (
                            momentum > threshold
                            and medium > 0.0
                            and close >= sma_200
                            and volatility <= 0.65
                        )
                        # Borrow only MSCI's pre-registered idea of risk-adjusting two
                        # horizons and combining them equally. This implementation is
                        # deliberately labelled as a simplification: it uses 21-day
                        # daily volatility and percentile ranks, not MSCI's three-year
                        # weekly volatility and z-score construction.
                        score = (
                            risk_adjusted_long_ranks[ticker] * 0.50
                            + risk_adjusted_medium_ranks[ticker] * 0.50
                        )
                    else:
                        eligible = medium > threshold and close >= sma_200
                        medium_weight = parameters.medium_momentum_weight
                        score = medium_ranks[ticker] * medium_weight + momentum_ranks[ticker] * (
                            1.0 - medium_weight
                        )
                    if eligible:
                        ranked.append((score, ticker))
                ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
                target = {ticker for _, ticker in ranked[: parameters.max_positions]}

            for index in range(start, end):
                ticker = self.tickers[index]
                close = float(self.close[index])
                state = states.setdefault(ticker, [False, 0.0, 0, 0.0])
                in_position = bool(state[0])
                risk_exit = False
                if in_position and float(state[1]) > 0.0:
                    state[2] = int(state[2]) + 1
                    state[3] = max(float(state[3]), close)
                    # Trailing stop only, for the same reason as the other two action
                    # paths: the engine applies the fixed stop and target against the
                    # price actually paid at the next open, while this loop only knows
                    # the signal-day close, so keeping both evaluated one stop twice from
                    # entry prices a bar apart. Dropping the fixed take-profit here also
                    # matches this profile's own stated intent - the docstring above says
                    # a fixed percentage systematically cuts the few large winners that
                    # drive a momentum portfolio.
                    risk_exit = float(state[3]) > 0.0 and close < float(state[3]) * (
                        1.0 - parameters.trailing_stop_pct
                    )

                if in_position and (risk_exit or (rotation_day and ticker not in target)):
                    actions[index] = -1
                    state[:] = [False, 0.0, 0, 0.0]
                elif rotation_day and ticker in target and not in_position:
                    actions[index] = 1
                    state[:] = [True, close, 0, close]

        return actions

    def _compiled_actions(
        self,
        strategy_ir: StrategyIR,
        parameters: CandidateParameters,
    ) -> array:
        actions = array("b", [0]) * len(self.rows)
        # in_position, entry_price, highest_close_since_entry
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
        for date_number, (start, end) in enumerate(self.date_ranges):
            eligible: list[tuple[int, str, float, float]] = []
            exits: list[tuple[int, str]] = []
            for index in range(start, end):
                ticker = self.tickers[index]
                close = self.close[index]
                state = states.setdefault(ticker, [False, 0.0, 0.0])
                in_position = bool(state[0])
                if in_position:
                    state[2] = max(float(state[2]), close)
                matches_entry = all(
                    self._condition_matches(condition, index)
                    for condition in entry_conditions
                )
                if matches_entry:
                    score = 0.0
                    if strategy_ir.ranking_metric:
                        measured = self._current_metric(strategy_ir.ranking_metric, index)
                        if measured is None:
                            matches_entry = False
                        else:
                            score = measured
                    if matches_entry:
                        eligible.append((index, ticker, close, score))
                if in_position:
                    exit_match = bool(exit_conditions) and all(
                        self._condition_matches(condition, index) for condition in exit_conditions
                    )
                    # Rule exit and the trailing stop only. The fixed stop-loss and
                    # take-profit belong to the engine, which is the side that knows the
                    # price actually paid: this loop records the signal-day close as the
                    # entry, while the fill happens at the next open plus slippage.
                    # Testing one stop against two entry prices a bar apart applied it
                    # twice, from figures that drift by a whole bar's move plus costs.
                    # The trailing stop stays - it tracks the peak since entry, which the
                    # engine does not model.
                    trailing_stop = float(state[2]) > 0.0 and close < float(state[2]) * (
                        1.0 - parameters.trailing_stop_pct
                    )
                    if exit_match or trailing_stop:
                        exits.append((index, ticker))

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
                eligible = [entry for entry in eligible if entry[1] in kept]

            if strategy_ir.ranking_metric:
                eligible.sort(
                    key=lambda item: (item[3], item[1]),
                    reverse=strategy_ir.ranking_direction == "desc",
                )
            rotation_day = (
                strategy_ir.execution_mode == "scheduled_rotation"
                and date_number % parameters.rebalance_interval_days == 0
            )
            target = {
                item[1] for item in eligible[: parameters.max_positions]
            } if rotation_day else set()
            if rotation_day:
                for index in range(start, end):
                    ticker = self.tickers[index]
                    if bool(states.setdefault(ticker, [False, 0.0, 0.0])[0]) and ticker not in target:
                        exits.append((index, ticker))

            exited: set[str] = set()
            for index, ticker in exits:
                if ticker in exited or not bool(states[ticker][0]):
                    continue
                actions[index] = -1
                states[ticker] = [False, 0.0, 0.0]
                exited.add(ticker)
            held = sum(1 for state in states.values() if bool(state[0]))
            entries = (
                [item for item in eligible if item[1] in target]
                if strategy_ir.execution_mode == "scheduled_rotation"
                else eligible
            )
            if strategy_ir.execution_mode == "scheduled_rotation" and not rotation_day:
                entries = []
            for index, ticker, close, _ in entries:
                if held >= parameters.max_positions:
                    break
                if ticker in exited or bool(states[ticker][0]):
                    continue
                actions[index] = 1
                states[ticker] = [True, close, close]
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
        if normalized == "open":
            return self.open
        if normalized == "high":
            return self.high
        if normalized == "low":
            return self.low
        if normalized == "volume":
            return self.volume
        if normalized == "rsi":
            computed = self._rsi_series(14)
            series = np.where(np.isfinite(self.rsi), self.rsi, computed)
            series.setflags(write=False)
            self._metric_cache[normalized] = series
            return series
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
        catalog_series = self._catalog_metric_series(normalized)
        if catalog_series is not None:
            # Point-in-time warehouse indicators are authoritative when present; the
            # OHLCV implementation fills only missing values.  This preserves exact
            # production indicator policy while keeping the catalog executable on raw
            # OHLCV fixtures and preventing the old "missing means neutral" fallback.
            row_series = self._row_metric_series(metric, normalized)
            if np.any(np.isfinite(row_series)):
                catalog_series = np.where(
                    np.isfinite(row_series), row_series, catalog_series
                )
            catalog_series.setflags(write=False)
            self._metric_cache[normalized] = catalog_series
            return catalog_series
        source = self._row_metric_series(metric, normalized)
        self._metric_cache[normalized] = source
        return source

    def _row_metric_series(self, metric: str, normalized: str) -> np.ndarray:
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
        return source

    def _catalog_metric_series(self, name: str) -> np.ndarray | None:
        """Derive every V2 catalog metric from same-day-and-earlier OHLCV only."""

        match = re.fullmatch(r"return_(\d+)d", name)
        if match:
            return self._period_return(int(match.group(1)))
        if name == "momentum_12_1":
            return self._skip_month_momentum()
        match = re.fullmatch(r"sma_?(\d+)", name)
        if match:
            return self._inclusive_rolling(self.close, int(match.group(1)), "avg")
        match = re.fullmatch(r"ema_?(\d+)", name)
        if match:
            return self._ema(self.close, int(match.group(1)))
        match = re.fullmatch(r"close_to_high_(\d+)", name)
        if match:
            high = self._inclusive_rolling(self.close, int(match.group(1)), "max")
            return _array_ratio(self.close, high)
        match = re.fullmatch(r"sharpe_(\d+)", name)
        if match:
            return self._return_ratio(int(match.group(1)), downside=False)
        match = re.fullmatch(r"sortino_(\d+)", name)
        if match:
            return self._return_ratio(int(match.group(1)), downside=True)
        match = re.fullmatch(r"return_vol_ratio_(\d+)", name)
        if match:
            window = int(match.group(1))
            returns = self._period_return(window)
            volatility = self._realized_volatility(window)
            return _array_ratio(returns, volatility)
        match = re.fullmatch(r"price_volume_score_(\d+)", name)
        if match:
            window = int(match.group(1))
            returns = self._period_return(window)
            volume_ratio = self._volume_ratio(20)
            return returns * (0.5 + np.nan_to_num(volume_ratio, nan=0.0))
        if name == "momentum_blend":
            return (
                0.5 * self._period_return(63)
                + 0.3 * self._period_return(126)
                + 0.2 * self._period_return(252)
            )
        if name in {"macd", "macd_signal", "macd_hist"}:
            return self._macd_series(name)
        if name in {"ppo", "ppo_signal", "ppo_hist"}:
            return self._ppo_series(name, self.close)
        match = re.fullmatch(r"(adx|plus_di|minus_di)_(\d+)", name)
        if match:
            return self._directional_movement(int(match.group(2)), match.group(1))
        match = re.fullmatch(r"aroon_(up|down)_(\d+)", name)
        if match:
            return self._aroon(int(match.group(2)), match.group(1))
        match = re.fullmatch(r"(slope|r_squared)_(\d+)", name)
        if match:
            return self._regression(self.close, int(match.group(2)), match.group(1))
        match = re.fullmatch(r"efficiency_ratio_(\d+)", name)
        if match:
            return self._efficiency_ratio(int(match.group(1)))
        match = re.fullmatch(r"trix_(\d+)", name)
        if match:
            return self._trix(int(match.group(1)))
        if name == "trix_signal_9":
            return self._ema(self._metric_series("trix_15"), 9)
        if name == "supertrend_direction_10_3":
            return self._supertrend_direction(10, 3.0)
        match = re.fullmatch(r"donchian_(high|low)_(\d+)", name)
        if match:
            source = self.high if match.group(1) == "high" else self.low
            aggregate = "max" if match.group(1) == "high" else "min"
            return self._rolling_from_array(
                source,
                int(match.group(2)),
                aggregate,
                prior=True,
            )
        match = re.fullmatch(r"bollinger_(upper|lower|middle|width|pct)_(\d+)", name)
        if match:
            return self._bollinger(int(match.group(2)), match.group(1))
        match = re.fullmatch(r"keltner_(upper|lower)_(\d+)", name)
        if match:
            middle = self._ema(self.close, int(match.group(2)))
            atr = self._atr(10)
            return middle + (2.0 * atr if match.group(1) == "upper" else -2.0 * atr)
        match = re.fullmatch(r"atr_expansion_(\d+)", name)
        if match:
            return _array_ratio(self._true_range(), self._atr(int(match.group(1))))
        match = re.fullmatch(r"atr_trailing_floor_(\d+)", name)
        if match:
            window = int(match.group(1))
            return self._metric_series(f"donchian_high_{window}") - 3.0 * self._atr(window)
        if name == "squeeze_breakout":
            width = self._metric_series("bollinger_width_20")
            usual_width = self._rolling_from_array(width, 120, "avg", prior=True)
            high = self._metric_series("donchian_high_20")
            return ((width < 0.6 * usual_width) & (self.close > high)).astype(np.float64)
        if name == "nr7_breakout":
            return self._nr7_breakout()
        if name == "inside_bar_breakout":
            return self._inside_bar_breakout()
        if name == "outside_bar_continuation":
            previous_high = self._shift(self.high, 1)
            previous_low = self._shift(self.low, 1)
            return (
                (self.high > previous_high)
                & (self.low < previous_low)
                & (self.close > self.open)
            ).astype(np.float64)
        if name == "gap_pct":
            return _array_return(self.open, self._shift(self.close, 1))
        if name == "gap_up_volume_breakout":
            gap = self._metric_series("gap_pct")
            volume_ratio = self._volume_ratio(20)
            return (
                (gap > 0.02) & (self.close > self.open) & (volume_ratio > 1.5)
            ).astype(np.float64)
        if name == "range_expansion_breakout":
            expansion = self._metric_series("atr_expansion_20")
            high = self._metric_series("donchian_high_20")
            location = _array_ratio(self.close - self.low, self.high - self.low)
            return (
                (expansion > 1.5) & (location > 0.8) & (self.close > high)
            ).astype(np.float64)
        match = re.fullmatch(r"price_zscore_(\d+)", name)
        if match:
            window = int(match.group(1))
            mean = self._inclusive_rolling(self.close, window, "avg")
            std = self._inclusive_rolling(self.close, window, "std")
            return _array_ratio(self.close - mean, std)
        match = re.fullmatch(r"stoch_k_(\d+)", name)
        if match:
            return self._stochastic(int(match.group(1)))
        if name == "stoch_d_3":
            return self._rolling_from_array(self._metric_series("stoch_k_14"), 3, "avg")
        match = re.fullmatch(r"williams_r_(\d+)", name)
        if match:
            window = int(match.group(1))
            high = self._inclusive_rolling(self.high, window, "max")
            low = self._inclusive_rolling(self.low, window, "min")
            return -100.0 * _array_ratio(high - self.close, high - low)
        match = re.fullmatch(r"cci_(\d+)", name)
        if match:
            return self._cci(int(match.group(1)))
        match = re.fullmatch(r"mfi_(\d+)", name)
        if match:
            return self._mfi(int(match.group(1)))
        match = re.fullmatch(r"close_to_vwap_(\d+)", name)
        if match:
            return _array_ratio(self.close, self._vwap(int(match.group(1))))
        if name == "loss_streak":
            return self._loss_streak()
        if name == "obv":
            return self._obv()
        match = re.fullmatch(r"obv_slope_(\d+)", name)
        if match:
            return self._regression(self._metric_series("obv"), int(match.group(1)), "slope_raw")
        match = re.fullmatch(r"cmf_(\d+)", name)
        if match:
            return self._cmf(int(match.group(1)))
        if name == "adl":
            return self._adl()
        match = re.fullmatch(r"adl_slope_(\d+)", name)
        if match:
            return self._regression(self._metric_series("adl"), int(match.group(1)), "slope_raw")
        if name in {"pvi", "nvi"}:
            return self._volume_index(positive=name == "pvi")
        if name in {"pvi_sma_100", "nvi_sma_100"}:
            return self._rolling_from_array(self._metric_series(name[:3]), 100, "avg")
        if name in {"pvi_trend_gap", "nvi_trend_gap"}:
            base = name[:3]
            return self._metric_series(base) - self._metric_series(f"{base}_sma_100")
        match = re.fullmatch(r"force_index_(\d+)", name)
        if match:
            raw = (self.close - self._shift(self.close, 1)) * self.volume
            return self._ema(raw, int(match.group(1)))
        match = re.fullmatch(r"eom_(\d+)", name)
        if match:
            midpoint = (self.high + self.low) / 2.0
            raw = _array_ratio(
                (midpoint - self._shift(midpoint, 1)) * (self.high - self.low),
                self.volume,
            )
            return self._rolling_from_array(raw, int(match.group(1)), "avg")
        if name in {"pvo", "pvo_signal", "pvo_hist"}:
            return self._ppo_series(name, self.volume, prefix="pvo")
        match = re.fullmatch(r"ulcer_index_(\d+)", name)
        if match:
            return self._ulcer_index(int(match.group(1)))
        match = re.fullmatch(r"drawdown_(\d+)", name)
        if match:
            peak = self._inclusive_rolling(self.close, int(match.group(1)), "max")
            return _array_return(self.close, peak)
        match = re.fullmatch(r"drawdown_recovery_(\d+)", name)
        if match:
            drawdown = np.abs(self._metric_series(f"drawdown_{match.group(1)}"))
            return _array_ratio(self._period_return(20), drawdown)
        return None

    def _period_return(self, window: int) -> np.ndarray:
        return _array_return(self.close, self._shift(self.close, window))

    def _skip_month_momentum(self) -> np.ndarray:
        past_month = self._shift(self.close, 21)
        year_ago = self._shift(self.close, 252)
        return _array_return(past_month, year_ago)

    def _shift(self, source: np.ndarray, periods: int) -> np.ndarray:
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            if len(indices) > periods:
                output[indices[periods:]] = source[indices[:-periods]]
        return output

    def _inclusive_rolling(
        self, source: np.ndarray, window: int, aggregate: str
    ) -> np.ndarray:
        return self._rolling_from_array(source, window, aggregate, prior=False)

    def _rolling_from_array(
        self,
        source: np.ndarray,
        window: int,
        aggregate: str,
        *,
        prior: bool = False,
    ) -> np.ndarray:
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            values = source[indices]
            if prior:
                values = np.concatenate(([np.nan], values[:-1]))
            if len(values) < window:
                continue
            windows = sliding_window_view(values, window)
            finite = np.all(np.isfinite(windows), axis=1)
            if aggregate == "avg":
                reduced = np.mean(windows, axis=1)
            elif aggregate == "sum":
                reduced = np.sum(windows, axis=1)
            elif aggregate == "max":
                reduced = np.max(windows, axis=1)
            elif aggregate == "min":
                reduced = np.min(windows, axis=1)
            elif aggregate == "std":
                reduced = np.std(windows, axis=1, ddof=0)
            else:
                raise ValueError(f"unsupported rolling aggregate: {aggregate}")
            reduced = np.where(finite, reduced, np.nan)
            output[indices[window - 1 :]] = reduced
        return output

    def _ema(self, source: np.ndarray, period: int) -> np.ndarray:
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        alpha = 2.0 / (period + 1.0)
        for indices in self.indices_by_ticker.values():
            values = source[indices]
            finite_positions = np.flatnonzero(np.isfinite(values))
            if finite_positions.size < period:
                continue
            seed_positions = finite_positions[:period]
            if int(seed_positions[-1] - seed_positions[0]) != period - 1:
                continue
            seed_at = int(seed_positions[-1])
            ema = float(np.mean(values[seed_positions]))
            output[indices[seed_at]] = ema
            for position in range(seed_at + 1, len(indices)):
                value = values[position]
                if not isfinite(float(value)):
                    continue
                ema = alpha * float(value) + (1.0 - alpha) * ema
                output[indices[position]] = ema
        return output

    def _wilder(self, source: np.ndarray, period: int) -> np.ndarray:
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            values = source[indices]
            finite_positions = np.flatnonzero(np.isfinite(values))
            if finite_positions.size < period:
                continue
            seed_positions = finite_positions[:period]
            if int(seed_positions[-1] - seed_positions[0]) != period - 1:
                continue
            seed_at = int(seed_positions[-1])
            average = float(np.mean(values[seed_positions]))
            output[indices[seed_at]] = average
            for position in range(seed_at + 1, len(indices)):
                value = float(values[position])
                if not isfinite(value):
                    continue
                average = (average * (period - 1) + value) / period
                output[indices[position]] = average
        return output

    def _realized_volatility(self, window: int) -> np.ndarray:
        returns = self._daily_returns()
        std = self._rolling_from_array(returns, window, "std")
        return std * sqrt(252)

    def _return_ratio(self, window: int, *, downside: bool) -> np.ndarray:
        returns = self._daily_returns()
        mean = self._rolling_from_array(returns, window, "avg")
        if not downside:
            risk = self._rolling_from_array(returns, window, "std")
        else:
            downside_returns = np.minimum(np.nan_to_num(returns, nan=np.nan), 0.0)
            squared = downside_returns * downside_returns
            risk = np.sqrt(self._rolling_from_array(squared, window, "avg"))
        return _array_ratio(mean, risk) * sqrt(252)

    def _volume_ratio(self, window: int) -> np.ndarray:
        average = self._rolling_from_array(self.volume, window, "avg", prior=True)
        return _array_ratio(self.volume, average)

    def _macd_series(self, name: str) -> np.ndarray:
        fast = self._ema(self.close, 12)
        slow = self._ema(self.close, 26)
        line = fast - slow
        signal = self._ema(line, 9)
        values = {"macd": line, "macd_signal": signal, "macd_hist": line - signal}
        for key, value in values.items():
            value.setflags(write=False)
            self._metric_cache.setdefault(key, value)
        return values[name]

    def _ppo_series(
        self, name: str, source: np.ndarray, *, prefix: str = "ppo"
    ) -> np.ndarray:
        fast = self._ema(source, 12)
        slow = self._ema(source, 26)
        line = 100.0 * _array_ratio(fast - slow, slow)
        signal = self._ema(line, 9)
        values = {
            prefix: line,
            f"{prefix}_signal": signal,
            f"{prefix}_hist": line - signal,
        }
        for key, value in values.items():
            value.setflags(write=False)
            self._metric_cache.setdefault(key, value)
        return values[name]

    def _true_range(self) -> np.ndarray:
        cached = self._metric_cache.get("__true_range__")
        if cached is not None:
            return cached
        previous_close = self._shift(self.close, 1)
        output = np.maximum(
            self.high - self.low,
            np.maximum(np.abs(self.high - previous_close), np.abs(self.low - previous_close)),
        )
        missing_previous = ~np.isfinite(previous_close)
        output[missing_previous] = self.high[missing_previous] - self.low[missing_previous]
        output.setflags(write=False)
        self._metric_cache["__true_range__"] = output
        return output

    def _atr(self, period: int) -> np.ndarray:
        key = f"atr_{period}"
        cached = self._metric_cache.get(key)
        if cached is not None:
            return cached
        output = self._wilder(self._true_range(), period)
        output.setflags(write=False)
        self._metric_cache[key] = output
        return output

    def _directional_movement(self, period: int, requested: str) -> np.ndarray:
        keys = {item: f"{item}_{period}" for item in ("adx", "plus_di", "minus_di")}
        cached = self._metric_cache.get(keys[requested])
        if cached is not None:
            return cached
        previous_high = self._shift(self.high, 1)
        previous_low = self._shift(self.low, 1)
        up = self.high - previous_high
        down = previous_low - self.low
        plus_dm = np.where((up > down) & (up > 0.0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0.0), down, 0.0)
        atr = self._atr(period)
        plus_di = 100.0 * _array_ratio(self._wilder(plus_dm, period), atr)
        minus_di = 100.0 * _array_ratio(self._wilder(minus_dm, period), atr)
        dx = 100.0 * _array_ratio(np.abs(plus_di - minus_di), plus_di + minus_di)
        adx = self._wilder(dx, period)
        values = {"adx": adx, "plus_di": plus_di, "minus_di": minus_di}
        for item, value in values.items():
            value.setflags(write=False)
            self._metric_cache[keys[item]] = value
        return values[requested]

    def _aroon(self, window: int, direction: str) -> np.ndarray:
        source = self.high if direction == "up" else self.low
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            values = source[indices]
            if len(values) < window:
                continue
            windows = sliding_window_view(values, window)
            if direction == "up":
                positions = window - 1 - np.argmax(windows[:, ::-1], axis=1)
            else:
                positions = window - 1 - np.argmin(windows[:, ::-1], axis=1)
            output[indices[window - 1 :]] = 100.0 * positions / max(1, window - 1)
        return output

    def _regression(self, source: np.ndarray, window: int, kind: str) -> np.ndarray:
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        x = np.arange(window, dtype=np.float64)
        centered_x = x - float(x.mean())
        denominator = float(np.sum(centered_x * centered_x))
        for indices in self.indices_by_ticker.values():
            values = source[indices]
            if len(values) < window:
                continue
            windows = sliding_window_view(values, window)
            finite = np.all(np.isfinite(windows), axis=1)
            means = np.mean(windows, axis=1)
            slopes = np.sum((windows - means[:, None]) * centered_x, axis=1) / denominator
            if kind == "slope":
                result = _array_ratio(slopes, means)
            elif kind == "slope_raw":
                result = slopes
            else:
                fitted = means[:, None] + slopes[:, None] * centered_x
                residual = np.sum((windows - fitted) ** 2, axis=1)
                total = np.sum((windows - means[:, None]) ** 2, axis=1)
                result = 1.0 - _array_ratio(residual, total)
            result = np.where(finite, result, np.nan)
            output[indices[window - 1 :]] = result
        return output

    def _efficiency_ratio(self, window: int) -> np.ndarray:
        direction = np.abs(self.close - self._shift(self.close, window))
        changes = np.abs(self.close - self._shift(self.close, 1))
        distance = self._rolling_from_array(changes, window, "sum")
        return _array_ratio(direction, distance)

    def _trix(self, period: int) -> np.ndarray:
        first = self._ema(self.close, period)
        second = self._ema(first, period)
        third = self._ema(second, period)
        return 100.0 * _array_return(third, self._shift(third, 1))

    def _supertrend_direction(self, period: int, multiplier: float) -> np.ndarray:
        atr = self._atr(period)
        midpoint = (self.high + self.low) / 2.0
        upper = midpoint + multiplier * atr
        lower = midpoint - multiplier * atr
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            local_upper = upper[indices].copy()
            local_lower = lower[indices].copy()
            closes = self.close[indices]
            direction = 1.0
            for position in range(len(indices)):
                if not isfinite(float(local_upper[position])):
                    continue
                if position > 0 and isfinite(float(local_upper[position - 1])):
                    if closes[position - 1] <= local_upper[position - 1]:
                        local_upper[position] = min(local_upper[position], local_upper[position - 1])
                    if closes[position - 1] >= local_lower[position - 1]:
                        local_lower[position] = max(local_lower[position], local_lower[position - 1])
                    if direction < 0.0 and closes[position] > local_upper[position - 1]:
                        direction = 1.0
                    elif direction > 0.0 and closes[position] < local_lower[position - 1]:
                        direction = -1.0
                output[indices[position]] = direction
        return output

    def _bollinger(self, window: int, part: str) -> np.ndarray:
        middle = self._inclusive_rolling(self.close, window, "avg")
        std = self._inclusive_rolling(self.close, window, "std")
        upper = middle + 2.0 * std
        lower = middle - 2.0 * std
        values = {
            "upper": upper,
            "lower": lower,
            "middle": middle,
            "width": _array_ratio(upper - lower, middle),
            "pct": _array_ratio(self.close - lower, upper - lower),
        }
        return values[part]

    def _nr7_breakout(self) -> np.ndarray:
        output = np.zeros(len(self.rows), dtype=np.float64)
        ranges = self.high - self.low
        for indices in self.indices_by_ticker.values():
            for position in range(7, len(indices)):
                previous = position - 1
                prior_ranges = ranges[indices[position - 7 : position]]
                if ranges[indices[previous]] <= float(np.min(prior_ranges)) and (
                    self.close[indices[position]] > self.high[indices[previous]]
                ):
                    output[indices[position]] = 1.0
        return output

    def _inside_bar_breakout(self) -> np.ndarray:
        output = np.zeros(len(self.rows), dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            for position in range(2, len(indices)):
                current = indices[position]
                previous = indices[position - 1]
                before = indices[position - 2]
                if (
                    self.high[previous] < self.high[before]
                    and self.low[previous] > self.low[before]
                    and self.close[current] > self.high[previous]
                ):
                    output[current] = 1.0
        return output

    def _rsi_series(self, period: int) -> np.ndarray:
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            closes = self.close[indices]
            if len(closes) <= period:
                continue
            changes = np.diff(closes)
            gains = np.maximum(changes, 0.0)
            losses = np.maximum(-changes, 0.0)
            average_gain = float(np.mean(gains[:period]))
            average_loss = float(np.mean(losses[:period]))

            def value() -> float:
                if average_loss == 0.0:
                    return 100.0 if average_gain > 0.0 else 50.0
                relative_strength = average_gain / average_loss
                return 100.0 - 100.0 / (1.0 + relative_strength)

            output[indices[period]] = value()
            for position in range(period + 1, len(indices)):
                change_index = position - 1
                average_gain = (
                    average_gain * (period - 1) + float(gains[change_index])
                ) / period
                average_loss = (
                    average_loss * (period - 1) + float(losses[change_index])
                ) / period
                output[indices[position]] = value()
        return output

    def _stochastic(self, window: int) -> np.ndarray:
        high = self._inclusive_rolling(self.high, window, "max")
        low = self._inclusive_rolling(self.low, window, "min")
        return 100.0 * _array_ratio(self.close - low, high - low)

    def _cci(self, window: int) -> np.ndarray:
        typical = (self.high + self.low + self.close) / 3.0
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            values = typical[indices]
            if len(values) < window:
                continue
            windows = sliding_window_view(values, window)
            means = np.mean(windows, axis=1)
            deviations = np.mean(np.abs(windows - means[:, None]), axis=1)
            output[indices[window - 1 :]] = _array_ratio(
                values[window - 1 :] - means,
                0.015 * deviations,
            )
        return output

    def _mfi(self, window: int) -> np.ndarray:
        typical = (self.high + self.low + self.close) / 3.0
        previous = self._shift(typical, 1)
        money = typical * self.volume
        positive = np.where(typical > previous, money, 0.0)
        negative = np.where(typical < previous, money, 0.0)
        positive_sum = self._rolling_from_array(positive, window, "sum")
        negative_sum = self._rolling_from_array(negative, window, "sum")
        ratio = _array_ratio(positive_sum, negative_sum)
        output = 100.0 - 100.0 / (1.0 + ratio)
        output[(negative_sum == 0.0) & (positive_sum > 0.0)] = 100.0
        return output

    def _vwap(self, window: int) -> np.ndarray:
        typical = (self.high + self.low + self.close) / 3.0
        numerator = self._rolling_from_array(typical * self.volume, window, "sum")
        denominator = self._rolling_from_array(self.volume, window, "sum")
        return _array_ratio(numerator, denominator)

    def _loss_streak(self) -> np.ndarray:
        output = np.zeros(len(self.rows), dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            streak = 0
            for position in range(1, len(indices)):
                current = indices[position]
                previous = indices[position - 1]
                streak = streak + 1 if self.close[current] < self.close[previous] else 0
                output[current] = float(streak)
        return output

    def _obv(self) -> np.ndarray:
        output = np.zeros(len(self.rows), dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            value = 0.0
            for position in range(1, len(indices)):
                current = indices[position]
                previous = indices[position - 1]
                value += float(np.sign(self.close[current] - self.close[previous])) * self.volume[current]
                output[current] = value
        return output

    def _money_flow_multiplier(self) -> np.ndarray:
        return _array_ratio(2.0 * self.close - self.high - self.low, self.high - self.low)

    def _cmf(self, window: int) -> np.ndarray:
        flow = self._money_flow_multiplier() * self.volume
        return _array_ratio(
            self._rolling_from_array(flow, window, "sum"),
            self._rolling_from_array(self.volume, window, "sum"),
        )

    def _adl(self) -> np.ndarray:
        flow = np.nan_to_num(self._money_flow_multiplier(), nan=0.0) * self.volume
        output = np.zeros(len(self.rows), dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            output[indices] = np.cumsum(flow[indices])
        return output

    def _volume_index(self, *, positive: bool) -> np.ndarray:
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            value = 1000.0
            if len(indices):
                output[indices[0]] = value
            for position in range(1, len(indices)):
                current = indices[position]
                previous = indices[position - 1]
                volume_matches = (
                    self.volume[current] > self.volume[previous]
                    if positive
                    else self.volume[current] < self.volume[previous]
                )
                if volume_matches and self.close[previous] != 0.0:
                    value *= self.close[current] / self.close[previous]
                output[current] = value
        return output

    def _ulcer_index(self, window: int) -> np.ndarray:
        output = np.full(len(self.rows), np.nan, dtype=np.float64)
        for indices in self.indices_by_ticker.values():
            values = self.close[indices]
            for position in range(window - 1, len(indices)):
                sample = values[position - window + 1 : position + 1]
                peaks = np.maximum.accumulate(sample)
                drawdowns = 100.0 * (sample / peaks - 1.0)
                output[indices[position]] = sqrt(float(np.mean(drawdowns * drawdowns)))
        return output

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
                        own[indices[window:]] = np.where(prior > 0.0, later / prior - 1.0, np.nan)
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
                totals = np.concatenate(([0.0], np.cumsum(np.where(finite, values, 0.0))))
                counts = np.concatenate(([0], np.cumsum(finite, dtype=np.int64)))
                for local_index, global_index in enumerate(indices):
                    start = max(0, local_index - window)
                    count = int(counts[local_index] - counts[start])
                    if count:
                        total = float(totals[local_index] - totals[start])
                        output[global_index] = (
                            total / count if normalized_aggregate == "avg" else total
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
                selected = candidates[-1] if normalized_aggregate == "last" else candidates[0]
                output[global_index] = float(values[selected])
        output.setflags(write=False)
        self._rolling_cache[key] = output
        return output


def _percentile_ranks(values: Sequence[tuple[str, float]]) -> dict[str, float]:
    """Cross-sectional percentile ranks with equal values receiving equal ranks."""

    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    if not ordered:
        return {}
    if len(ordered) == 1:
        return {ordered[0][0]: 1.0}
    output: dict[str, float] = {}
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average_position = (start + end - 1) / 2.0
        percentile = average_position / (len(ordered) - 1)
        for index in range(start, end):
            output[ordered[index][0]] = percentile
        start = end
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


def _safe_return(values: np.ndarray, bases: np.ndarray) -> np.ndarray:
    output = np.zeros(len(values), dtype=np.float64)
    valid = bases != 0.0
    output[valid] = values[valid] / bases[valid] - 1.0
    return output


def _array_ratio(numerators: np.ndarray, denominators: np.ndarray) -> np.ndarray:
    """NaN-preserving division used by the catalog's indicator formulas."""

    output = np.full(np.shape(numerators), np.nan, dtype=np.float64)
    valid = (
        np.isfinite(numerators)
        & np.isfinite(denominators)
        & (denominators != 0.0)
    )
    np.divide(numerators, denominators, out=output, where=valid)
    return output


def _array_return(values: np.ndarray, bases: np.ndarray) -> np.ndarray:
    output = _array_ratio(values, bases)
    output[np.isfinite(output)] -= 1.0
    return output


def _safe_ratio(
    numerators: np.ndarray,
    denominators: np.ndarray,
    *,
    positive: bool = False,
) -> np.ndarray:
    output = np.zeros(len(numerators), dtype=np.float64)
    valid = denominators > 0.0 if positive else denominators != 0.0
    output[valid] = numerators[valid] / denominators[valid]
    return output


def _prior_rolling_extreme(
    values: np.ndarray,
    window: int,
    *,
    maximum: bool,
) -> np.ndarray:
    output = np.zeros(len(values), dtype=np.float64)
    if len(values) <= 1 or window <= 0:
        return output
    prefix_end = min(window, len(values))
    accumulate = np.maximum.accumulate if maximum else np.minimum.accumulate
    if prefix_end > 1:
        output[1:prefix_end] = accumulate(values[: prefix_end - 1])
    if window < len(values):
        windows = sliding_window_view(values[:-1], window)
        output[window:] = windows.max(axis=1) if maximum else windows.min(axis=1)
    return output
