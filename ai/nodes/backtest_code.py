"""Fixture/mock 기반 백테스트 코드 생성 노드."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from security.ast_validator import ASTValidationResult, validate_backtest_code


DEFAULT_BACKTEST_CODE = '''def build_signals(prices):
    """Return BUY/SELL/HOLD signals from close-price momentum."""
    signals = []
    previous_close = None
    for row in prices:
        close = float(row["close"])
        if previous_close is None:
            action = "HOLD"
        elif close > previous_close:
            action = "BUY"
        elif close < previous_close:
            action = "SELL"
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        previous_close = close
    return signals
'''


class LLMClient(Protocol):
    """LLM 교체 가능성을 보장하는 최소 인터페이스."""

    def complete(self, prompt: str) -> str:
        """프롬프트에 대한 텍스트 응답을 반환한다."""


class MockLLMClient:
    """기본 fixture 전용 LLM 클라이언트."""

    def __init__(self, response: str = DEFAULT_BACKTEST_CODE) -> None:
        self._response = response

    def complete(self, prompt: str) -> str:
        return self._response


class BacktestCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_summary: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)


class BacktestCodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    validation: ASTValidationResult
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)


def generate_backtest_code(
    request: BacktestCodeRequest,
    *,
    llm_client: LLMClient | None = None,
) -> BacktestCodeResult:
    """전략 설명을 백테스트 코드로 변환하고 AST 검증을 수행한다."""

    client = llm_client or MockLLMClient()
    prompt = (
        "Generate Python backtest code with exactly one entrypoint named "
        f"build_signals(prices). Strategy: {request.strategy_summary}"
    )
    code = client.complete(prompt)
    validation = validate_backtest_code(code)
    validation.raise_for_violations()
    return BacktestCodeResult(
        code=code,
        validation=validation,
        trace_id=request.trace_id,
        debug_ref=request.debug_ref,
    )
