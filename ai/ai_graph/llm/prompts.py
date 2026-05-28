from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.llm.base import LLMJsonRequest
from ai_graph.schemas import StrategySpec


BACKTEST_CODE_SCHEMA_NAME = "backtest_code_candidates.v1"
BACKTEST_CODE_SYSTEM_PROMPT = """\
You are QuantAgent's backtest-code generation node.
Return only JSON that conforms to the requested schema.
Each candidate must define a pure Python function named build_signals(prices).
The function must return date/action/price dictionaries and use only supplied price rows.
Do not import network, filesystem, subprocess, OS, eval, exec, or reflection APIs.
"""


class BacktestCodeLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[str] = Field(min_length=3, max_length=3)
    fallback_reasons: list[str] = Field(default_factory=list)


def build_backtest_code_json_request(strategy: StrategySpec, variant: str) -> LLMJsonRequest:
    schema = BacktestCodeLLMOutput.model_json_schema()
    user_prompt = {
        "task": "Generate exactly three build_signals Python implementations.",
        "variant": variant,
        "strategy_spec": strategy.model_dump(mode="json"),
        "expected_json_schema": schema,
        "output_contract": {
            "candidates": "array of exactly three Python code strings",
            "fallback_reasons": "array of strings, empty when generation succeeded",
        },
    }
    return LLMJsonRequest(
        schema_name=BACKTEST_CODE_SCHEMA_NAME,
        system_prompt=BACKTEST_CODE_SYSTEM_PROMPT,
        user_prompt=json.dumps(user_prompt, ensure_ascii=False, sort_keys=True),
        temperature=0.0,
    )
