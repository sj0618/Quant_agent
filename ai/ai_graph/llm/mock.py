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


class MockLLMClient:
    def generate_json(self, request: LLMJsonRequest) -> dict[str, Any]:
        if request.schema_name == BACKTEST_CODE_SCHEMA_NAME:
            return {"candidates": MOCK_BACKTEST_CODE_CANDIDATES, "fallback_reasons": []}
        return {"fallback_reasons": [f"unsupported mock schema: {request.schema_name}"]}


class MockBacktestCodeLLM(MockLLMClient):
    def generate_backtest_candidates(self, strategy: StrategySpec, variant: str) -> list[str]:
        return list(MOCK_BACKTEST_CODE_CANDIDATES)
