import json

import pytest

from ai_graph.graph import run_analysis
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.prompts import BacktestCodeLLMOutput, build_backtest_code_json_request
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

    assert "KOSPI200" in serialized["universe"]
    assert "sector" in serialized
    assert any(
        condition.left.lower() == "rsi" and condition.operator == "lte" and condition.right == 30
        for condition in spec.entry_conditions
    )
    assert any(
        condition.left.lower() == "rsi" and condition.operator == "gte" and condition.right == 70
        for condition in spec.exit_conditions
    )


def test_backtest_code_prompt_declares_expected_json_schema() -> None:
    envelope = run_analysis(QUERY, trace_id="trace-prompt-contract")
    spec = StrategySpec.model_validate(envelope.strategy_spec)

    request = build_backtest_code_json_request(spec, "A")
    prompt_payload = json.loads(request.user_prompt)
    schema = prompt_payload["expected_json_schema"]

    assert request.schema_name == "backtest_code_candidates.v1"
    assert "candidates" in schema["properties"]
    assert schema["properties"]["candidates"]["minItems"] == 3
    assert schema["properties"]["candidates"]["maxItems"] == 12


def test_backtest_code_schema_validation_failure_records_fallback_reason() -> None:
    envelope = run_analysis(QUERY, trace_id="trace-schema-fallback")
    spec = StrategySpec.model_validate(envelope.strategy_spec)

    result = generate_loop3_candidates(
        Loop3Request(strategy=spec, variant="A", trace_id="trace-schema-fallback"),
        llm_client=InvalidSchemaLLMClient(),
    )

    assert len(result.candidates) >= 6
    assert result.fallback_reasons
    assert "ValidationError" in result.fallback_reasons[0]


def test_backtest_code_ast_validation_failure_uses_safe_fallback_candidates() -> None:
    envelope = run_analysis(QUERY, trace_id="trace-ast-fallback")
    spec = StrategySpec.model_validate(envelope.strategy_spec)

    result = generate_loop3_candidates(
        Loop3Request(strategy=spec, variant="A", trace_id="trace-ast-fallback"),
        llm_client=UnsafeCodeLLMClient(),
    )

    assert len(result.candidates) >= 6
    assert sum(candidate.validation_ok for candidate in result.candidates) >= 6
    assert any("import 'os' is not allowed" in reason or "build_signals" in reason for reason in result.fallback_reasons)


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
