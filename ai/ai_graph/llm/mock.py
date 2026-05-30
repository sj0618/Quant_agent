from __future__ import annotations

from typing import Any

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


class MockLLMClient:
    def generate_json(self, request: LLMJsonRequest) -> dict[str, Any]:
        if request.schema_name == BACKTEST_CODE_SCHEMA_NAME:
            if "breakout_volume_momentum" in request.user_prompt:
                return {"candidates": BREAKOUT_VOLUME_CANDIDATES, "fallback_reasons": []}
            if "bollinger" in request.user_prompt or "볼린저" in request.user_prompt:
                return {"candidates": BOLLINGER_CANDIDATES, "fallback_reasons": []}
            if any(strategy_id in request.user_prompt for strategy_id in ("value_quality", "reasonable_growth", "quality_growth", "growth_momentum")):
                return {"candidates": VALUE_QUALITY_CANDIDATES, "fallback_reasons": []}
            if any(strategy_id in request.user_prompt for strategy_id in ("pullback", "fcf_recovery", "dividend_defensive", "low_vol_defensive")):
                return {"candidates": TREND_PULLBACK_CANDIDATES, "fallback_reasons": []}
            if "relative_strength" in request.user_prompt:
                return {"candidates": RELATIVE_STRENGTH_CANDIDATES, "fallback_reasons": []}
            return {"candidates": MOCK_BACKTEST_CODE_CANDIDATES, "fallback_reasons": []}
        return {"fallback_reasons": [f"unsupported mock schema: {request.schema_name}"]}


class MockBacktestCodeLLM(MockLLMClient):
    def generate_backtest_candidates(self, strategy: StrategySpec, variant: str) -> list[str]:
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
