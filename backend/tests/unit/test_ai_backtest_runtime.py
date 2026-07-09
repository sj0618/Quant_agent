from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.ai_backtest import AICodeBacktestFlowRequest, GeneratedCodeResult
from app.services.ai_backtest_runtime import AOAICodeGenerator, ASTCodeValidator, SandboxedBacktestExecutor


def test_ast_code_validator_blocks_non_runtime_imports_and_file_io_calls():
    validator = ASTCodeValidator()
    code = """
import pandas

def build_signals(prices):
    pandas.read_csv('prices.csv')
    return []
"""
    result = validator.validate(
        GeneratedCodeResult(
            target_runtime="python-sandbox",
            code_purpose="backtest",
            generated_code=code,
        ),
        trace_id=uuid4(),
    )

    assert result.is_safe is False
    assert result.uses_allowed_imports is False
    assert result.blocks_file_write is False
    assert any("runtime import 'pandas' is not allowed" in error["message"] for error in result.errors_jsonb)
    assert any("pandas.read_csv" in error["message"] for error in result.errors_jsonb)


def test_sandboxed_backtest_executor_enforces_timeout():
    executor = SandboxedBacktestExecutor()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="무한 루프 전략",
        parsed_strategy_jsonb={
            "strategy_id": "loop_strategy",
            "name": "Loop Strategy",
            "universe": "KOSPI200",
            "market": "KRX",
            "timeframe": "daily",
            "entry_conditions": [{"left": "rsi", "operator": "lte", "right": 30}],
            "exit_conditions": [],
            "indicators": ["RSI"],
            "risk_constraints": {"max_position_pct": 0.1},
            "assumptions": [],
            "source_refs": [],
            "confidence": 0.5,
        },
        strategy_id="loop_strategy",
        target_runtime="python-sandbox",
        code_purpose="backtest",
        timeout_seconds=1,
        memory_limit_mb=128,
    )
    generated = GeneratedCodeResult(
        target_runtime="python-sandbox",
        code_purpose="backtest",
        generated_code="def build_signals(prices):\n    while True:\n        pass\n",
    )

    result = asyncio.run(executor.execute(request, generated, trace_id=uuid4(), execution_run_id=uuid4()))

    assert result.status == "timeout"
    assert result.timeout_seconds == 1
    assert result.memory_limit_mb == 128
    assert result.backtest_result is None

def test_aoai_code_generator_populates_minimal_truthful_model_call(monkeypatch):
    monkeypatch.setenv("AI_LLM_PROVIDER", "mock")
    monkeypatch.setenv("AI_LLM_BACKTEST_CODE_MODEL", "gpt-backtest-stage1")
    generator = AOAICodeGenerator()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="RSI 반등 전략을 코드 생성해서 실행해줘",
        parsed_strategy_jsonb={
            "strategy_id": "rsi_rebound",
            "name": "RSI 반등",
            "universe": "KOSPI200",
            "market": "KRX",
            "timeframe": "daily",
            "entry_conditions": [{"left": "rsi", "operator": "lte", "right": 30}],
            "exit_conditions": [{"left": "rsi", "operator": "gte", "right": 70}],
            "indicators": ["RSI"],
            "risk_constraints": {"max_position_pct": 0.1},
            "assumptions": [],
            "source_refs": [],
            "confidence": 0.9,
        },
        strategy_id="rsi_rebound",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )

    result = asyncio.run(generator.generate(request, trace_id=uuid4()))

    assert result.model_name is None
    assert result.model_call is not None
    assert result.model_call.task_type == "backtest_code_generation"
    assert result.model_call.provider == "mock"
    assert result.model_call.model_name is None
    assert result.model_call.status == "succeeded"
    assert result.model_call.provider_request_id is None
    assert result.model_call.prompt_tokens is None
    assert result.model_call.completion_tokens is None
    assert result.model_call.total_tokens is None
    assert result.model_call.latency_ms is None
    assert result.model_call.cost is None
    assert result.model_call.error_message is None
    assert result.model_call.prompt_log is not None
    assert result.model_call.prompt_log.prompt_template_name
    assert result.model_call.prompt_log.system_prompt.startswith("[redacted")
    assert result.model_call.prompt_log.user_prompt.startswith("[redacted")
    assert result.model_call.prompt_log.assistant_response is None
    assert result.model_call.prompt_log.variables_jsonb["strategy_id"] == "rsi_rebound"
    assert result.model_call.prompt_log.variables_jsonb["request_text_sha256"]
    assert result.model_call.prompt_log.variables_jsonb["system_prompt_sha256"]
    assert result.model_call.prompt_log.variables_jsonb["user_prompt_sha256"]
    assert result.model_call.prompt_log.masked is True


def test_aoai_code_generator_marks_deterministic_fallback_model_call_as_failed(monkeypatch):
    class DummyMockClient:
        pass

    class DummyAOAIClient:
        pass

    prompt_request = SimpleNamespace(
        schema_name="quantagent.backtest_code.v1",
        system_prompt="system prompt",
        user_prompt="user prompt",
    )
    fallback_result = SimpleNamespace(
        candidates=[SimpleNamespace(validation_ok=True, code="def build_signals(prices):\n    return []\n")],
        selected_candidate=SimpleNamespace(code="def build_signals(prices):\n    return []\n"),
        fallback_reasons=["all generated candidates failed AST validation"],
    )
    monkeypatch.setattr(
        "app.services.ai_backtest_runtime._load_generation_modules",
        lambda: (
            lambda prompt, variant, retrieval: SimpleNamespace(strategy_id="fallback_demo"),
            lambda strategy, variant: prompt_request,
            lambda role=None: DummyMockClient(),
            lambda request, llm_client=None: fallback_result,
            lambda strategy, variant, trace_id: SimpleNamespace(strategy=strategy, variant=variant, trace_id=trace_id),
            type(
                "StrategySpec",
                (),
                {"model_validate": staticmethod(lambda payload: SimpleNamespace(strategy_id=payload["strategy_id"]))},
            ),
            DummyAOAIClient,
            DummyMockClient,
        ),
    )
    generator = AOAICodeGenerator()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="fallback 경로를 검증해줘",
        parsed_strategy_jsonb={"strategy_id": "fallback_demo"},
        strategy_id="fallback_demo",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )

    result = asyncio.run(generator.generate(request, trace_id=uuid4()))

    assert result.model_name is None
    assert result.model_call is not None
    assert result.model_call.provider == "mock"
    assert result.model_call.model_name is None
    assert result.model_call.status == "failed"
    assert result.model_call.error_message == "LLM generated candidates failed validation; deterministic fallback code was executed."
    assert result.model_call.prompt_log is not None
