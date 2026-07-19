from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.llm.base import LLMJsonRequest
from ai_graph.schemas import StrategySpec


BACKTEST_CODE_SCHEMA_NAME = "backtest_code_candidates.v1"
BACKTEST_CODE_PROMPT_TEMPLATE_NAME = "backtest_code_generation"
BACKTEST_CODE_PROMPT_VERSION = "v1"
BACKTEST_CODE_SYSTEM_PROMPT = """\
You are QuantAgent's backtest-code generation node.
Return only JSON that conforms to the requested schema.
Each candidate must define a pure Python function named build_signals(prices).
The function must return date/action/price dictionaries and use only supplied price rows.
Generate strategy-specific logic from StrategySpec instead of falling back to RSI unless RSI is explicitly requested.
When a requested fundamental, consensus, flow, macro, or disclosure metric is absent from price rows,
use a clearly named OHLCV proxy that still reflects the StrategySpec assumption.
Do not require a full 20/52/120-day warm-up before emitting any signal; use the available partial lookback
so fixture and short-window validation cannot silently return all HOLD.
Do not import network, filesystem, subprocess, OS, eval, exec, or reflection APIs.
"""


class BacktestCodeLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[str] = Field(min_length=3, max_length=12)
    fallback_reasons: list[str] = Field(default_factory=list)


def build_backtest_code_json_request(
    strategy: StrategySpec,
    variant: str,
    *,
    validation_feedback: list[str] | None = None,
) -> LLMJsonRequest:
    schema = BacktestCodeLLMOutput.model_json_schema()
    user_prompt = {
        "task": "Generate three to twelve build_signals Python implementations.",
        "variant": variant,
        "strategy_spec": strategy.model_dump(mode="json"),
        "expected_json_schema": schema,
        "output_contract": {
            "candidates": "array of three to twelve Python code strings",
            "fallback_reasons": "array of strings, empty when generation succeeded",
        },
        "quality_checks": [
            "Use build_signals as the top-level entrypoint; keep any helper functions nested and do not define classes.",
            "Avoid imports; if needed, use only datetime, math, or statistics.",
            "Do not use eval, exec, open, reflection, network, filesystem, subprocess, or OS APIs.",
            "Each candidate should emit one signal per supplied price row.",
            "At least one candidate should be capable of BUY/SELL/WATCH-equivalent behavior on a short fixture.",
            "The code should reference the StrategySpec's main indicators or documented OHLCV proxies.",
            "Avoid unconditional empty lists, unconditional HOLD, or warm-up gates that skip all short fixtures.",
        ],
    }
    if validation_feedback:
        user_prompt["validation_feedback"] = validation_feedback
        user_prompt["task"] = (
            "Regenerate three to twelve build_signals implementations that correct every "
            "listed validation failure."
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
    )
