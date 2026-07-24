from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from pydantic import ValidationError

from ai_graph.llm.aoai import AOAIResponsesClient
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.factory import create_llm_client
from ai_graph.llm.prompts import (
    BacktestCodeLLMOutput,
    build_backtest_code_json_request,
)
from ai_graph.schemas import Condition, ConditionOperator, StrategySpec


def _strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="live-aoai-latency-rsi-volume",
        name="Live AOAI latency RSI volume",
        market="KRX",
        timeframe="daily",
        entry_conditions=[
            Condition(left="rsi", operator=ConditionOperator.LTE, right=40.0),
            Condition(
                left="volume",
                operator=ConditionOperator.GTE,
                right="volume",
                window=20,
                aggregate="avg",
                scale=1.5,
            ),
        ],
        exit_conditions=[
            Condition(left="rsi", operator=ConditionOperator.GTE, right=70.0)
        ],
        indicators=["rsi", "volume"],
        risk_constraints={
            "max_position_pct": 0.1,
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.3,
        },
        confidence=0.9,
    )


def _request_size(request: LLMJsonRequest) -> dict[str, int]:
    schema_text = json.dumps(
        request.response_schema,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        "system_prompt_chars": len(request.system_prompt),
        "user_prompt_chars": len(request.user_prompt),
        "response_schema_chars": len(schema_text),
        "transport_prompt_chars": len(request.system_prompt) + len(request.user_prompt),
    }


def _run_live_request(
    label: str,
    request: LLMJsonRequest,
    *,
    validate_backtest: bool,
) -> dict[str, Any]:
    client = create_llm_client(role="BACKTEST_CODE")
    if not isinstance(client, AOAIResponsesClient):
        raise RuntimeError("live benchmark requires AI_LLM_PROVIDER=aoai")

    started = time.perf_counter()
    payload = client.generate_json(request)
    wall_seconds = time.perf_counter() - started
    if validate_backtest:
        try:
            parsed = BacktestCodeLLMOutput.model_validate(payload)
        except ValidationError as exc:
            output_summary = {
                "validation_ok": False,
                "validation_errors": exc.errors(
                    include_url=False,
                    include_input=False,
                ),
            }
        else:
            output_summary = {
                "validation_ok": True,
                "candidate_count": len(parsed.candidates),
                "fallback_code_count": len(parsed.fallback_code),
                "fallback_reason_count": len(parsed.fallback_reasons),
            }
    else:
        if payload.get("ok") is not True:
            raise RuntimeError("minimal AOAI response did not satisfy the JSON contract")
        output_summary = {"ok": True}

    return {
        "label": label,
        "wall_seconds": round(wall_seconds, 6),
        "request": _request_size(request),
        "timings": dict(client.last_call_timings),
        "output": output_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-backtest-wall-seconds", type=float, default=180.0)
    args = parser.parse_args()

    if os.environ.get("AI_LLM_PROVIDER", "").strip().lower() != "aoai":
        raise RuntimeError("set AI_LLM_PROVIDER=aoai; mocked providers are not allowed")

    # Run the real backtest prompt cold, then a tiny request on the same process-wide
    # connection pool. The difference separates prompt/generation latency from the warm
    # network floor, while physical_http_posts exposes provider compatibility retries.
    backtest_request = build_backtest_code_json_request(_strategy(), "A")
    backtest_result = _run_live_request(
        "backtest_prompt_cold",
        backtest_request,
        validate_backtest=True,
    )
    minimal_result = _run_live_request(
        "minimal_json_warm",
        LLMJsonRequest(
            schema_name="live_latency_floor.v1",
            system_prompt="Return only the requested JSON.",
            user_prompt='Return {"ok":true}.',
            temperature=0.0,
            max_output_tokens=128,
            task_type="live_aoai_latency_floor",
            prompt_template_name="live_aoai_latency_floor",
            prompt_version="v1",
            response_schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        ),
        validate_backtest=False,
    )
    output = {
        "provider": "aoai",
        "model": os.environ.get("AI_LLM_BACKTEST_CODE_MODEL")
        or os.environ.get("AI_AOAI_MODEL"),
        "results": [backtest_result, minimal_result],
        "diagnosis": {
            "backtest_minus_warm_floor_seconds": round(
                float(backtest_result["wall_seconds"])
                - float(minimal_result["wall_seconds"]),
                6,
            ),
            "backtest_physical_http_posts": backtest_result["timings"].get(
                "physical_http_posts"
            ),
        },
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))

    if float(backtest_result["wall_seconds"]) > args.max_backtest_wall_seconds:
        return 2
    if backtest_result["output"].get("validation_ok") is not True:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
