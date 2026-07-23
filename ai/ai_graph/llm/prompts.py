from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.llm.base import LLMJsonRequest
from ai_graph.schemas import CandidateParameters, StrategyIR, StrategySpec


BACKTEST_CODE_SCHEMA_NAME = "backtest_strategy_candidates.v2"
BACKTEST_CODE_PROMPT_TEMPLATE_NAME = "backtest_strategy_generation"
BACKTEST_CODE_PROMPT_VERSION = "v2"
BACKTEST_CODE_SYSTEM_PROMPT = """\
You are QuantAgent's structured backtest-strategy generation node.
Return only JSON that conforms to the requested schema.
Return one StrategyIR and exactly three bounded CandidateParameters objects.
Reuse entry_conditions and exit_conditions already present in StrategySpec; do not restate
the same strategy as three Python programs. Vary only profile, lookback, threshold, stop loss,
take profit, and max positions.
Choose profile="compiled_conditions" when the supplied conditions are expressible by StrategyIR.
Use a clearly named OHLCV proxy only when a requested metric is absent, and preserve that mapping
in proxy_feature. Python fallback_code is exceptional: use it only when StrategyIR cannot express
the user strategy, and explain why in fallback_reasons.

Any fallback build_signals implementation must be deterministic, keep state per ticker, emit one
signal per input row, and make one chronological pass. Target O(N), at worst O(N log N), with O(N)
additional memory. Never scan or filter all prices from inside the row loop. Never use nested
full-data loops, unbounded slicing, or sum/max/min over a growing history inside a loop. Rolling
values must use incremental state or supplied precomputed columns. Do not use future rows or mix
history across tickers. Do not import network, filesystem, subprocess, OS, eval, exec, reflection,
or concurrency APIs.

Verified O(N) fallback shape:
def build_signals(prices):
    signals = []
    previous_by_ticker = {}
    for row in prices:
        ticker = str(row.get("ticker", "000000"))
        close = float(row["close"])
        previous = previous_by_ticker.get(ticker)
        action = "HOLD"
        if previous is not None:
            action = "BUY" if close > previous else "SELL" if close < previous else "HOLD"
        signals.append({"date": row["date"], "ticker": ticker, "action": action, "price": close})
        previous_by_ticker[ticker] = close
    return signals
"""


class BacktestCodeLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_ir: StrategyIR
    candidates: list[CandidateParameters] = Field(min_length=3, max_length=3)
    fallback_code: list[str] = Field(default_factory=list, max_length=3)
    fallback_reasons: list[str] = Field(default_factory=list)


def build_backtest_code_json_request(
    strategy: StrategySpec,
    variant: str,
    *,
    validation_feedback: list[str] | None = None,
) -> LLMJsonRequest:
    schema = BacktestCodeLLMOutput.model_json_schema()
    user_prompt = {
        "task": "Generate one StrategyIR and exactly three CandidateParameters objects.",
        "variant": variant,
        "strategy_spec": strategy.model_dump(mode="json"),
        "expected_json_schema": schema,
        "output_contract": {
            "strategy_ir": "one normalized strategy rule shared by all candidates",
            "candidates": "exactly three bounded parameter objects",
            "fallback_code": "zero to three Python strings; only for unrepresentable StrategyIR",
            "fallback_reasons": "array of strings, empty when generation succeeded",
        },
        "quality_checks": [
            "Reuse StrategySpec entry_conditions and exit_conditions in StrategyIR.",
            "Keep the candidate count equal to the evaluator limit of three.",
            "Vary parameters, not duplicated program text.",
            "Keep lookback between 3 and 252 and preserve supplied risk constraints.",
            "Use compiled_conditions when StrategyIR can represent the user rule.",
            "Document any OHLCV proxy in proxy_feature.",
            "Use fallback_code only when the structured rule cannot represent the strategy.",
        ],
    }
    if validation_feedback:
        user_prompt["validation_feedback"] = validation_feedback
        user_prompt["task"] = (
            "Regenerate one StrategyIR and exactly three parameter candidates that correct "
            "every listed validation failure."
        )
    return LLMJsonRequest(
        schema_name=BACKTEST_CODE_SCHEMA_NAME,
        system_prompt=BACKTEST_CODE_SYSTEM_PROMPT,
        user_prompt=json.dumps(user_prompt, ensure_ascii=False, sort_keys=True),
        temperature=0.0,
        task_type="backtest_code_generation",
        prompt_template_name=BACKTEST_CODE_PROMPT_TEMPLATE_NAME,
        prompt_version=BACKTEST_CODE_PROMPT_VERSION,
        variables_jsonb=user_prompt,
        response_schema=schema,
    )
