from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.schemas import BacktestMetrics, CodeCandidate, StrategySpec
from ai_graph.security.ast_validator import validate_backtest_code


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


class LLMClient(Protocol):
    def generate_backtest_candidates(self, strategy: StrategySpec, variant: str) -> list[str]:
        """Return three generated Python code candidates for a StrategySpec variant."""


class MockBacktestCodeLLM:
    def generate_backtest_candidates(self, strategy: StrategySpec, variant: str) -> list[str]:
        return [SAFE_RSI_CODE, CONSERVATIVE_RSI_CODE, SMOOTHED_RSI_CODE]


class Loop3Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: StrategySpec
    variant: str = Field(pattern="^(A|B)$")
    trace_id: str = Field(min_length=1)


class Loop3Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant: str
    candidates: list[CodeCandidate] = Field(min_length=3, max_length=3)
    selected_candidate: CodeCandidate


def generate_loop3_candidates(
    request: Loop3Request, *, llm_client: LLMClient | None = None
) -> Loop3Result:
    client = llm_client or MockBacktestCodeLLM()
    raw_codes = client.generate_backtest_candidates(request.strategy, request.variant)
    candidates: list[CodeCandidate] = []
    for index, code in enumerate(raw_codes[:3], start=1):
        validation = validate_backtest_code(code)
        metrics = mock_candidate_metrics(request.variant, index) if validation.ok else None
        candidates.append(
            CodeCandidate(
                candidate_id=f"{request.variant}{index}",
                variant=request.variant,  # type: ignore[arg-type]
                code=code,
                validation_ok=validation.ok,
                violations=[violation.message for violation in validation.violations],
                metrics=metrics,
            )
        )
    if len(candidates) != 3:
        raise ValueError("Loop3 requires exactly three candidates")
    valid_candidates = [candidate for candidate in candidates if candidate.validation_ok]
    if not valid_candidates:
        raise ValueError("all generated candidates failed AST validation")
    selected = max(valid_candidates, key=lambda candidate: candidate.metrics.sharpe_ratio)  # type: ignore[union-attr]
    return Loop3Result(variant=request.variant, candidates=candidates, selected_candidate=selected)


def backtest_code_node(state: dict) -> dict:
    strategy_a = StrategySpec.model_validate(state["strategy_spec"])
    strategy_b = StrategySpec.model_validate(state.get("improved_strategy_spec") or state["strategy_spec"])
    result_a = generate_loop3_candidates(
        Loop3Request(strategy=strategy_a, variant="A", trace_id=state["trace_id"])
    )
    result_b = generate_loop3_candidates(
        Loop3Request(strategy=strategy_b, variant="B", trace_id=state["trace_id"])
    )
    candidates = result_a.candidates + result_b.candidates
    selected = max(candidates, key=lambda candidate: candidate.metrics.sharpe_ratio)  # type: ignore[union-attr]
    return {
        "backtest_code": {
            "candidates": [candidate.model_dump() for candidate in candidates],
            "selected_candidate": selected.model_dump(),
        }
    }


def mock_candidate_metrics(variant: str, index: int) -> BacktestMetrics:
    base = 0.85 if variant == "A" else 1.0
    sharpe = base + (index * 0.17)
    return BacktestMetrics(
        sharpe_ratio=round(sharpe, 3),
        max_drawdown=round(-0.08 + (index * 0.005), 3),
        win_rate=round(0.49 + (index * 0.04), 3),
        total_return=round(0.08 + (index * 0.025), 3),
        in_sample_sharpe=round(sharpe + 0.08, 3),
        out_sample_sharpe=round(sharpe - 0.06, 3),
        degradation=round(0.06 / (sharpe + 0.08), 3),
    )
