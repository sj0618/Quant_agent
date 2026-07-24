from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.llm.base import LLMJsonRequest
from ai_graph.schemas import CandidateParameters, StrategyIR, StrategySpec


BACKTEST_CODE_SCHEMA_NAME = "backtest_strategy_candidates.v2"
BACKTEST_CODE_PROMPT_TEMPLATE_NAME = "backtest_strategy_generation"
BACKTEST_CODE_PROMPT_VERSION = "v5"
BACKTEST_CODE_SYSTEM_PROMPT = """\
Return only the requested JSON object. Produce one StrategyIR and exactly three bounded
CandidateParameters objects. Copy the supplied entry/exit conditions into StrategyIR and vary
parameters, not program text. Prefer profile="compiled_conditions" and return fallback_code=[]
whenever StrategyIR can express the rule. Preserve risk constraints and record an OHLCV proxy in
proxy_feature when a requested metric is unavailable. proxy_feature is always required and
non-empty; when no substitution is needed, use the primary direct input feature such as "rsi".

Python fallback is exceptional. If unavoidable, explain it in fallback_reasons and make one
deterministic chronological O(N) pass, with bounded state per ticker and one signal per input row.
Never copy or rescan the full input, slice growing history inside the row loop, use future rows,
mix ticker histories, or import network, filesystem, subprocess, OS, reflection, eval, exec, or
concurrency APIs. Do not repeat the schema or add prose.
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
        "task": "Normalize this strategy and produce exactly three parameter candidates.",
        "variant": variant,
        "strategy_spec": strategy.model_dump(mode="json"),
        "constraints": {
            "candidate_count": 3,
            "lookback_range": [3, 252],
            "preferred_profile": "compiled_conditions",
            "preserve_entry_exit_conditions": True,
            "preserve_risk_constraints": True,
        },
        "fallback_code_performance_contract": {
            "use_only_when": "StrategyIR cannot express the supplied rule",
            "target": "one chronological O(N) pass",
            "state": "bounded incremental state per ticker",
            "required": [
                "one output signal per input row",
                "row-provided indicators before calculated rolling values",
                "incremental rolling state isolated by ticker",
            ],
            "forbidden": [
                "full-input copy, sort, nested scan, or filter",
                "history slicing or rolling aggregation inside the row loop",
                "future-row access or cross-ticker state",
            ],
        },
        "response_shape": {
            "strategy_ir": "object",
            "candidates": "array[3]",
            "fallback_code": "array, normally empty",
            "fallback_reasons": "array, normally empty",
        },
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
        max_output_tokens=2048,
        task_type="backtest_code_generation",
        prompt_template_name=BACKTEST_CODE_PROMPT_TEMPLATE_NAME,
        prompt_version=BACKTEST_CODE_PROMPT_VERSION,
        variables_jsonb={**user_prompt, "expected_json_schema": schema},
        response_schema=schema,
    )
