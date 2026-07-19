from __future__ import annotations

import json
import time
from typing import Any

from ai_graph.audit import begin_model_call, finish_model_call
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.prompts import BACKTEST_CODE_SCHEMA_NAME
from ai_graph.schemas import StrategySpec


SAFE_RSI_CODE = '''def build_signals(prices):
    signals = []
    for row in prices:
        rsi = float(row.get("rsi", 50))
        if rsi <= 30:
            action = "BUY"
        elif rsi >= 70:
            action = "SELL"
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": float(row["close"])})
    return signals
'''

CONSERVATIVE_RSI_CODE = '''def build_signals(prices):
    signals = []
    for row in prices:
        rsi = float(row.get("rsi", 50))
        action = "BUY" if rsi <= 28 else "SELL" if rsi >= 72 else "HOLD"
        signals.append({"date": row["date"], "action": action, "price": float(row["close"])})
    return signals
'''

SMOOTHED_RSI_CODE = '''def build_signals(prices):
    signals = []
    previous_rsi = 50.0
    for row in prices:
        rsi = float(row.get("rsi", previous_rsi))
        smoothed = (previous_rsi + rsi) / 2
        if smoothed <= 32:
            action = "BUY"
        elif smoothed >= 68:
            action = "SELL"
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": float(row["close"])})
        previous_rsi = rsi
    return signals
'''

MOCK_BACKTEST_CODE_CANDIDATES = [SAFE_RSI_CODE, CONSERVATIVE_RSI_CODE, SMOOTHED_RSI_CODE]

BREAKOUT_VOLUME_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    highs = []
    volumes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        high = float(row.get("high", close))
        volume = float(row.get("volume", 0))
        lookback = min(20, len(closes))
        if lookback:
            recent_closes = closes[-lookback:]
            recent_highs = highs[-lookback:]
            recent_volumes = volumes[-lookback:]
            sma = sum(recent_closes) / len(recent_closes)
            avg_volume = sum(recent_volumes) / len(recent_volumes)
            breakout = close > max(recent_highs)
            volume_ratio = volume / avg_volume if avg_volume > 0 else 0
            relative_strength = float(row.get("relative_strength_20d", close / recent_closes[0] - 1))
            buy = breakout and volume_ratio >= 1.5 and close > sma and relative_strength >= 0
            sell = in_position and close < sma
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
        highs.append(high)
        volumes.append(volume)
    return signals
'''

BREAKOUT_VOLUME_CONSERVATIVE_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    volumes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        volume = float(row.get("volume", 0))
        lookback = min(20, len(closes))
        if lookback:
            recent_closes = closes[-lookback:]
            recent_volumes = volumes[-lookback:]
            sma = sum(recent_closes) / lookback
            prior_high = max(recent_closes)
            avg_volume = sum(recent_volumes) / lookback
            volume_ratio = volume / avg_volume if avg_volume > 0 else 0
            relative_strength = float(row.get("relative_strength_20d", close / recent_closes[0] - 1))
            buy = close > prior_high and volume_ratio >= 1.5 and close > sma and relative_strength >= 0
            sell = in_position and close < sma
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
        volumes.append(volume)
    return signals
'''

BREAKOUT_VOLUME_EARLY_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    highs = []
    volumes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        high = float(row.get("high", close))
        volume = float(row.get("volume", 0))
        lookback = min(10, len(closes))
        if lookback:
            recent_closes = closes[-lookback:]
            recent_highs = highs[-lookback:]
            recent_volumes = volumes[-lookback:]
            sma = sum(recent_closes) / lookback
            avg_volume = sum(recent_volumes) / lookback
            volume_ratio = volume / avg_volume if avg_volume > 0 else 0
            relative_strength = float(row.get("relative_strength_20d", close / recent_closes[0] - 1))
            buy = close > max(recent_highs) and volume_ratio >= 1.2 and close > sma and relative_strength >= 0
            sell = in_position and close < sma
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
        highs.append(high)
        volumes.append(volume)
    return signals
'''

BREAKOUT_VOLUME_CANDIDATES = [
    BREAKOUT_VOLUME_CODE,
    BREAKOUT_VOLUME_CONSERVATIVE_CODE,
    BREAKOUT_VOLUME_EARLY_CODE,
]

RELATIVE_STRENGTH_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    previous_close = None
    in_position = False
    for row in ordered:
        close = float(row["close"])
        relative_strength = float(row.get("relative_strength_20d", 0 if previous_close is None else close / previous_close - 1))
        if previous_close is None:
            action = "HOLD"
        elif not in_position and close > previous_close and relative_strength >= 0:
            action = "BUY"
            in_position = True
        elif in_position and close < previous_close:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        previous_close = close
    return signals
'''

RELATIVE_STRENGTH_SMOOTHED_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        lookback = min(5, len(closes))
        if lookback:
            recent = closes[-lookback:]
            trend = close / recent[0] - 1
            average = sum(recent) / lookback
            buy = close >= average and trend >= 0
            sell = in_position and close < average
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
    return signals
'''

RELATIVE_STRENGTH_VOLUME_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    volumes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        volume = float(row.get("volume", 0))
        lookback = min(20, len(closes))
        if lookback:
            avg_close = sum(closes[-lookback:]) / lookback
            avg_volume = sum(volumes[-lookback:]) / lookback
            volume_ok = volume >= avg_volume if avg_volume > 0 else True
            buy = close > avg_close and volume_ok
            sell = in_position and close < avg_close
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
        volumes.append(volume)
    return signals
'''

RELATIVE_STRENGTH_CANDIDATES = [
    RELATIVE_STRENGTH_CODE,
    RELATIVE_STRENGTH_SMOOTHED_CODE,
    RELATIVE_STRENGTH_VOLUME_CODE,
]

TREND_PULLBACK_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        lookback = min(20, len(closes))
        if lookback:
            sma = sum(closes[-lookback:]) / lookback
            previous = closes[-1]
            buy = close > sma and close >= previous
            sell = in_position and close < sma
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
    return signals
'''

TREND_PULLBACK_RSI_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        rsi = float(row.get("rsi", 45))
        lookback = min(20, len(closes))
        if lookback:
            sma = sum(closes[-lookback:]) / lookback
            buy = close > sma and rsi <= 50
            sell = in_position and close < sma
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
    return signals
'''

TREND_PULLBACK_BREAKOUT_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    highs = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        high = float(row.get("high", close))
        lookback = min(20, len(closes))
        if lookback:
            sma = sum(closes[-lookback:]) / lookback
            near_high = close >= max(highs[-lookback:]) * 0.98
            buy = close > sma and near_high
            sell = in_position and close < sma
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
        highs.append(high)
    return signals
'''

TREND_PULLBACK_CANDIDATES = [
    TREND_PULLBACK_CODE,
    TREND_PULLBACK_RSI_CODE,
    TREND_PULLBACK_BREAKOUT_CODE,
]

BOLLINGER_SQUEEZE_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        lookback = min(20, len(closes))
        if lookback:
            recent = closes[-lookback:]
            middle = sum(recent) / lookback
            upper = max(recent)
            lower = min(recent)
            squeeze_proxy = (upper - lower) / middle if middle else 0
            buy = close > middle and (close >= upper or squeeze_proxy <= 0.05)
            sell = in_position and close < middle
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
    return signals
'''

BOLLINGER_REENTRY_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    was_below = False
    in_position = False
    for row in ordered:
        close = float(row["close"])
        lookback = min(20, len(closes))
        if lookback:
            recent = closes[-lookback:]
            middle = sum(recent) / lookback
            lower = min(recent)
            if close < lower:
                was_below = True
            buy = close > middle or (was_below and close >= lower)
            sell = in_position and close < middle
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
            was_below = False
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
    return signals
'''

BOLLINGER_VOLUME_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    volumes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        volume = float(row.get("volume", 0))
        lookback = min(20, len(closes))
        if lookback:
            recent = closes[-lookback:]
            middle = sum(recent) / lookback
            avg_volume = sum(volumes[-lookback:]) / lookback
            buy = close > middle and (volume >= avg_volume if avg_volume > 0 else True)
            sell = in_position and close < middle
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
        volumes.append(volume)
    return signals
'''

BOLLINGER_CANDIDATES = [
    BOLLINGER_SQUEEZE_CODE,
    BOLLINGER_REENTRY_CODE,
    BOLLINGER_VOLUME_CODE,
]

VALUE_QUALITY_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    previous_close = None
    in_position = False
    for row in ordered:
        close = float(row["close"])
        per_ok = float(row.get("per_percentile", 0.3)) <= 0.4
        roe_ok = float(row.get("roe", 0.16)) >= 0.15
        debt_ok = float(row.get("debt_ratio", 80)) <= 100
        relative_strength = 0 if previous_close is None else close / previous_close - 1
        buy = previous_close is not None and close > previous_close and relative_strength >= 0 and per_ok and roe_ok and debt_ok
        sell = in_position and previous_close is not None and close < previous_close
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        previous_close = close
    return signals
'''

VALUE_QUALITY_TREND_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        quality_ok = float(row.get("roe", 0.16)) >= 0.12 and float(row.get("debt_ratio", 80)) <= 120
        lookback = min(20, len(closes))
        if lookback:
            average = sum(closes[-lookback:]) / lookback
            buy = close > average and quality_ok
            sell = in_position and close < average
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
    return signals
'''

VALUE_QUALITY_VOLUME_CODE = '''def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda row: row["date"])
    closes = []
    volumes = []
    in_position = False
    for row in ordered:
        close = float(row["close"])
        volume = float(row.get("volume", 0))
        lookback = min(20, len(closes))
        if lookback:
            avg_close = sum(closes[-lookback:]) / lookback
            avg_volume = sum(volumes[-lookback:]) / lookback
            buy = close > avg_close and (volume >= avg_volume if avg_volume > 0 else True)
            sell = in_position and close < avg_close
        else:
            buy = False
            sell = False
        if buy and not in_position:
            action = "BUY"
            in_position = True
        elif sell:
            action = "SELL"
            in_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        closes.append(close)
        volumes.append(volume)
    return signals
'''

VALUE_QUALITY_CANDIDATES = [
    VALUE_QUALITY_CODE,
    VALUE_QUALITY_TREND_CODE,
    VALUE_QUALITY_VOLUME_CODE,
]

PULLBACK_RSI40_VOLUME_CODE = '''def build_signals(prices):
    signals = []
    closes = []
    volumes = []
    has_position = False
    for row in prices:
        close = float(row.get("close", 0))
        volume = float(row.get("volume", 0))
        rsi = float(row.get("rsi", row.get("rsi_14", 50)))
        closes.append(close)
        volumes.append(volume)
        sma_window = closes[-200:]
        volume_window = volumes[-20:]
        sma_200 = sum(sma_window) / len(sma_window)
        avg_volume = sum(volume_window) / len(volume_window)
        above_trend = close >= sma_200
        volume_ok = volume >= avg_volume
        if (not has_position) and above_trend and rsi <= 40 and volume_ok:
            action = "BUY"
            has_position = True
        elif has_position and (rsi >= 60 or close < sma_200):
            action = "SELL"
            has_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
    return signals
'''

CONSERVATIVE_PULLBACK_RSI40_VOLUME_CODE = '''def build_signals(prices):
    signals = []
    closes = []
    volumes = []
    has_position = False
    for row in prices:
        close = float(row.get("close", 0))
        volume = float(row.get("volume", 0))
        rsi = float(row.get("rsi", row.get("rsi_14", 50)))
        closes.append(close)
        volumes.append(volume)
        sma_window = closes[-200:]
        volume_window = volumes[-20:]
        sma_200 = sum(sma_window) / len(sma_window)
        avg_volume = sum(volume_window) / len(volume_window)
        above_trend = close >= sma_200
        volume_ok = volume >= avg_volume * 1.05
        if (not has_position) and above_trend and rsi <= 38 and volume_ok:
            action = "BUY"
            has_position = True
        elif has_position and (rsi >= 58 or close < sma_200):
            action = "SELL"
            has_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
    return signals
'''

REBOUND_PULLBACK_RSI40_VOLUME_CODE = '''def build_signals(prices):
    signals = []
    closes = []
    volumes = []
    previous_rsi = 50.0
    has_position = False
    for row in prices:
        close = float(row.get("close", 0))
        volume = float(row.get("volume", 0))
        rsi = float(row.get("rsi", row.get("rsi_14", previous_rsi)))
        closes.append(close)
        volumes.append(volume)
        sma_window = closes[-200:]
        volume_window = volumes[-20:]
        sma_200 = sum(sma_window) / len(sma_window)
        avg_volume = sum(volume_window) / len(volume_window)
        above_trend = close >= sma_200
        volume_ok = volume >= avg_volume
        rebound = previous_rsi <= 40 and rsi > previous_rsi
        if (not has_position) and above_trend and rebound and volume_ok:
            action = "BUY"
            has_position = True
        elif has_position and (rsi >= 62 or close < sma_200):
            action = "SELL"
            has_position = False
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        previous_rsi = rsi
    return signals
'''

PULLBACK_RSI40_VOLUME_CANDIDATES = [
    PULLBACK_RSI40_VOLUME_CODE,
    CONSERVATIVE_PULLBACK_RSI40_VOLUME_CODE,
    REBOUND_PULLBACK_RSI40_VOLUME_CODE,
]


class MockLLMClient:
    def generate_json(self, request: LLMJsonRequest) -> dict[str, Any]:
        call_id = begin_model_call(
            task_type=request.task_type or request.schema_name,
            provider="mock",
            model_name="deterministic",
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            variables_jsonb=request.variables_jsonb,
            prompt_template_name=request.prompt_template_name,
            prompt_version=request.prompt_version,
            temperature=request.temperature,
            response_schema_name=request.schema_name,
            web_search_used=request.enable_web_search,
        )
        started_at = time.perf_counter()
        try:
            if request.schema_name == BACKTEST_CODE_SCHEMA_NAME:
                strategy, variant = _strategy_and_variant_from_request(request)
                result = {
                    "candidates": self.generate_backtest_candidates(strategy, variant),
                    "fallback_reasons": [],
                }
            else:
                result = {"fallback_reasons": [f"unsupported mock schema: {request.schema_name}"]}
        except Exception as exc:
            finish_model_call(
                call_id,
                status="failed",
                assistant_response=None,
                model_name="deterministic",
                latency_ms=(time.perf_counter() - started_at) * 1000,
                error_type=type(exc).__name__,
                error_message=f"{type(exc).__name__} during model call",
            )
            raise

        finish_model_call(
            call_id,
            status="succeeded",
            assistant_response=json.dumps(
                result, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ),
            model_name="deterministic",
            latency_ms=(time.perf_counter() - started_at) * 1000,
        )
        return result

    def generate_backtest_candidates(self, strategy: StrategySpec, variant: str) -> list[str]:
        if strategy.strategy_id.startswith("pullback_rsi_volume"):
            return list(PULLBACK_RSI40_VOLUME_CANDIDATES)
        return list(MOCK_BACKTEST_CODE_CANDIDATES)


class MockBacktestCodeLLM(MockLLMClient):
    def generate_backtest_candidates(self, strategy: StrategySpec, variant: str) -> list[str]:
        if strategy.strategy_id.startswith("pullback_rsi_volume"):
            return list(PULLBACK_RSI40_VOLUME_CANDIDATES)
        if strategy.strategy_id.startswith("breakout_volume_momentum"):
            return list(BREAKOUT_VOLUME_CANDIDATES)
        if strategy.strategy_id.startswith("bollinger"):
            return list(BOLLINGER_CANDIDATES)
        if strategy.strategy_id.startswith(("value_quality", "reasonable_growth", "quality_growth", "growth_momentum", "asset_value_catalyst", "margin_improvement", "margin_inventory_quality", "operating_profit_pullback")):
            return list(VALUE_QUALITY_CANDIDATES)
        if strategy.strategy_id.startswith(("pullback", "breakout_pullback", "midterm_pullback", "trend_rsi_volume_pullback", "dividend_defensive", "low_vol_defensive", "rate_sensitive_income", "fcf_recovery")):
            return list(TREND_PULLBACK_CANDIDATES)
        if strategy.strategy_id.startswith(("relative_strength", "earnings", "oversold_quality", "fx_exporter_revision")):
            return list(RELATIVE_STRENGTH_CANDIDATES)
        if strategy.strategy_id.startswith(("flow_accumulation", "short_covering_proxy", "gap_hold_momentum", "breakout_setup")):
            return list(BREAKOUT_VOLUME_CANDIDATES)
        return list(MOCK_BACKTEST_CODE_CANDIDATES)


def _strategy_and_variant_from_request(request: LLMJsonRequest) -> tuple[StrategySpec, str]:
    try:
        payload = json.loads(request.user_prompt)
        strategy = StrategySpec.model_validate(payload["strategy_spec"])
        variant = str(payload.get("variant") or "A")
    except (KeyError, TypeError, ValueError):
        strategy = _default_rsi_strategy()
        variant = "A"
    return strategy, variant


def _default_rsi_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="rsi_rebound_a",
        name="RSI 과매도 반등",
        market="KRX",
        timeframe="daily",
        entry_conditions=[],
        exit_conditions=[],
        indicators=["RSI"],
        risk_constraints={},
        assumptions=[],
        source_refs=[],
        confidence=0.68,
    )
