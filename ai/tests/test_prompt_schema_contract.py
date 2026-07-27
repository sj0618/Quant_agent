import json

import pytest

from ai_graph.graph import run_analysis
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.prompts import (
    BACKTEST_CODE_PROMPT_VERSION,
    BacktestCodeLLMOutput,
    build_backtest_code_json_request,
)
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.schemas import StrategySpec


QUERY = "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어"


class InvalidSchemaLLMClient:
    def generate_json(self, request: LLMJsonRequest) -> dict:
        return {"candidates": ["def build_signals(prices):\n    return []\n"]}


class UnsafeCodeLLMClient:
    def generate_json(self, request: LLMJsonRequest) -> dict:
        return {
            "candidates": [
                "import os\ndef build_signals(prices):\n    return []\n",
                "def helper(prices):\n    return []\n",
                "class Strategy:\n    pass\n",
            ],
            "fallback_reasons": [],
        }


def test_strategy_spec_contract_preserves_rsi_buy_sell_semantics() -> None:
    envelope = run_analysis(QUERY, trace_id="trace-strategy-contract")

    spec = StrategySpec.model_validate(envelope.strategy_spec)
    serialized = json.loads(spec.model_dump_json())

    assert "universe" not in serialized
    assert "sector" in serialized
    assert any(
        condition.left.lower() == "rsi" and condition.operator == "lte" and condition.right == 30
        for condition in spec.entry_conditions
    )
    assert any(
        condition.left.lower() == "rsi" and condition.operator == "gte" and condition.right == 70
        for condition in spec.exit_conditions
    )


def test_backtest_code_prompt_keeps_schema_out_of_transport_prompt() -> None:
    envelope = run_analysis(QUERY, trace_id="trace-prompt-contract")
    spec = StrategySpec.model_validate(envelope.strategy_spec)

    request = build_backtest_code_json_request(spec, "A")
    prompt_payload = json.loads(request.user_prompt)
    schema = request.variables_jsonb["expected_json_schema"]

    assert request.schema_name == "backtest_strategy_candidates.v2"
    assert request.task_type == "backtest_code_generation"
    assert request.prompt_template_name == "backtest_strategy_generation"
    assert request.prompt_version == BACKTEST_CODE_PROMPT_VERSION
    assert request.max_output_tokens == 2048
    assert "expected_json_schema" not in prompt_payload
    assert request.variables_jsonb == {
        **prompt_payload,
        "expected_json_schema": schema,
    }
    assert request.response_schema == schema
    assert "strategy_ir" in schema["properties"]
    assert "candidates" in schema["properties"]
    assert schema["properties"]["candidates"]["minItems"] == 3
    assert schema["properties"]["candidates"]["maxItems"] == 3

    performance = prompt_payload["fallback_code_performance_contract"]
    assert performance["target"] == "one chronological O(N) pass"
    forbidden = " ".join(performance["forbidden"])
    required = " ".join(performance["required"])
    assert "full-input copy" in forbidden
    assert "history slicing" in forbidden
    assert "nested scan" in forbidden
    assert "incremental" in required
    assert "ticker" in required


def test_backtest_code_schema_validation_failure_records_fallback_reason() -> None:
    envelope = run_analysis(QUERY, trace_id="trace-schema-fallback")
    spec = StrategySpec.model_validate(envelope.strategy_spec)

    result = generate_loop3_candidates(
        Loop3Request(strategy=spec, variant="A", trace_id="trace-schema-fallback"),
        llm_client=InvalidSchemaLLMClient(),
    )

    assert len(result.candidates) == 3
    assert all(candidate.representation == "structured" for candidate in result.candidates)
    assert result.fallback_reasons
    assert "ValidationError" in result.fallback_reasons[0]


def test_backtest_code_ast_validation_failure_uses_safe_fallback_candidates() -> None:
    envelope = run_analysis(QUERY, trace_id="trace-ast-fallback")
    spec = StrategySpec.model_validate(envelope.strategy_spec)

    result = generate_loop3_candidates(
        Loop3Request(strategy=spec, variant="A", trace_id="trace-ast-fallback"),
        llm_client=UnsafeCodeLLMClient(),
    )

    assert len(result.candidates) == 3
    assert all(candidate.validation_ok for candidate in result.candidates)
    assert all(candidate.representation == "structured" for candidate in result.candidates)
    assert any("ValidationError" in reason for reason in result.fallback_reasons)


def test_backtest_code_fallback_reason_is_available_in_internal_payload_only() -> None:
    envelope = run_analysis(QUERY, trace_id="trace-fallback-boundary")
    spec = StrategySpec.model_validate(envelope.strategy_spec)

    result = generate_loop3_candidates(
        Loop3Request(strategy=spec, variant="A", trace_id="trace-fallback-boundary"),
        llm_client=InvalidSchemaLLMClient(),
    )

    public_dump = envelope.model_dump(mode="json")
    assert "fallback_reasons" not in public_dump
    assert result.fallback_reasons


def test_backtest_code_llm_output_rejects_extra_fields() -> None:
    payload = {"candidates": ["a", "b", "c"], "fallback_reasons": [], "extra": True}

    with pytest.raises(Exception) as exc_info:
        BacktestCodeLLMOutput.model_validate(payload)

    assert "extra" in str(exc_info.value)
