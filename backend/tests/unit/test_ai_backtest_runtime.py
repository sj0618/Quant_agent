from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai_graph.llm.prompts import BACKTEST_CODE_SCHEMA_NAME, BACKTEST_CODE_SYSTEM_PROMPT
from app.schemas.ai_backtest import (
    AI_BACKTEST_MAX_MEMORY_LIMIT_MB,
    AI_BACKTEST_MAX_PROMPT_CHARS,
    AI_BACKTEST_MAX_TIMEOUT_SECONDS,
    AICodeBacktestFlowRequest,
    AICodeBacktestPublicRequest,
    GeneratedCodeResult,
)
from app.services.ai_backtest_runtime import (
    AOAICodeGenerator,
    ASTCodeValidator,
    CodeGenerationFailure,
    SandboxedBacktestExecutor,
)


@pytest.mark.parametrize("request_type", [AICodeBacktestPublicRequest, AICodeBacktestFlowRequest])
def test_backtest_request_resource_limits_accept_configured_maximums(request_type):
    request = request_type(
        natural_language_prompt="x" * AI_BACKTEST_MAX_PROMPT_CHARS,
        target_runtime="python-sandbox",
        code_purpose="backtest",
        timeout_seconds=AI_BACKTEST_MAX_TIMEOUT_SECONDS,
        memory_limit_mb=AI_BACKTEST_MAX_MEMORY_LIMIT_MB,
    )

    assert len(request.natural_language_prompt) == AI_BACKTEST_MAX_PROMPT_CHARS
    assert request.timeout_seconds == AI_BACKTEST_MAX_TIMEOUT_SECONDS
    assert request.memory_limit_mb == AI_BACKTEST_MAX_MEMORY_LIMIT_MB


@pytest.mark.parametrize("request_type", [AICodeBacktestPublicRequest, AICodeBacktestFlowRequest])
@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    [
        ("natural_language_prompt", "x" * (AI_BACKTEST_MAX_PROMPT_CHARS + 1), "string_too_long"),
        ("timeout_seconds", AI_BACKTEST_MAX_TIMEOUT_SECONDS + 1, "less_than_equal"),
        ("memory_limit_mb", AI_BACKTEST_MAX_MEMORY_LIMIT_MB + 1, "less_than_equal"),
    ],
)
def test_backtest_request_resource_limits_reject_oversized_values(
    request_type,
    field_name,
    value,
    error_type,
):
    payload = {
        "natural_language_prompt": "bounded request",
        "target_runtime": "python-sandbox",
        "code_purpose": "backtest",
    }
    payload[field_name] = value

    with pytest.raises(ValidationError) as exc_info:
        request_type(**payload)

    assert exc_info.value.errors()[0]["type"] == error_type

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


def test_sandboxed_backtest_executor_enforces_timeout(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_backtest_runtime._limit_subprocess_resources",
        lambda _memory_limit_mb, _timeout_seconds: None,
    )
    executor = SandboxedBacktestExecutor()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="무한 루프 전략",
        parsed_strategy_jsonb={
            "strategy_id": "loop_strategy",
            "name": "Loop Strategy",
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
        generated_code=(
            "def build_signals(prices):\n"
            "    for left in range(10000):\n"
            "        for right in range(10000):\n"
            "            pass\n"
            "    return []\n"
        ),
    )

    persisted_identity = []

    async def persist_identity(identity):
        persisted_identity.append(identity)

    async def authorize_release(_identity):
        return None
    result = asyncio.run(
        executor.execute(
            request,
            generated,
            trace_id=uuid4(),
            execution_run_id=uuid4(),
            process_identity_recorder=persist_identity,
            release_authorizer=authorize_release,
        )
    )

    assert result.status == "timeout"
    assert result.timeout_seconds == 1
    assert result.memory_limit_mb == 128
    assert result.backtest_result is None
    assert len(persisted_identity) == 1
    assert persisted_identity[0].worker_pid > 0
    assert persisted_identity[0].worker_pgid > 0


def test_sandboxed_backtest_executor_withholds_release_when_identity_persistence_fails():
    executor = SandboxedBacktestExecutor()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="ownership persistence failure",
        target_runtime="python-sandbox",
        code_purpose="backtest",
        timeout_seconds=5,
        memory_limit_mb=128,
    )
    generated = GeneratedCodeResult(
        target_runtime="python-sandbox",
        code_purpose="backtest",
        generated_code="def build_signals(prices):\n    return []\n",
    )

    async def reject_identity(_identity):
        raise RuntimeError("database commit failed")

    result = asyncio.run(
        executor.execute(
            request,
            generated,
            trace_id=uuid4(),
            execution_run_id=uuid4(),
            process_identity_recorder=reject_identity,
        )
    )

    assert result.status == "failed"
    assert result.backtest_result is None
    assert result.stdout == ""
    assert result.stderr == "subprocess ownership persistence failed; execution was not released"

def test_sandboxed_backtest_executor_withholds_release_when_release_cas_fails():
    executor = SandboxedBacktestExecutor()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="release CAS failure",
        target_runtime="python-sandbox",
        code_purpose="backtest",
        timeout_seconds=5,
        memory_limit_mb=128,
    )
    generated = GeneratedCodeResult(
        target_runtime="python-sandbox",
        code_purpose="backtest",
        generated_code="def build_signals(prices):\n    return []\n",
    )

    async def persist_identity(_identity):
        return None

    async def reject_release(_identity):
        raise RuntimeError("state version changed")

    result = asyncio.run(
        executor.execute(
            request,
            generated,
            trace_id=uuid4(),
            execution_run_id=uuid4(),
            process_identity_recorder=persist_identity,
            release_authorizer=reject_release,
        )
    )

    assert result.status == "failed"
    assert result.backtest_result is None
    assert result.stdout == ""
    assert result.stderr == "subprocess release authorization failed; execution was not released"

def test_aoai_code_generator_captures_full_model_call(monkeypatch):
    monkeypatch.setenv("AI_LLM_PROVIDER", "mock")
    monkeypatch.setenv("AI_LLM_BACKTEST_CODE_MODEL", "gpt-backtest-stage1")
    generator = AOAICodeGenerator()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="RSI 반등 전략을 코드 생성해서 실행해줘",
        parsed_strategy_jsonb={
            "strategy_id": "rsi_rebound",
            "name": "RSI 반등",
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
    assert result.model_call.model_name == "deterministic"
    assert result.model_call.status == "succeeded"
    assert result.model_call.provider_request_id is None
    assert result.model_call.prompt_tokens is None
    assert result.model_call.completion_tokens is None
    assert result.model_call.total_tokens is None
    assert result.model_call.latency_ms is not None
    assert result.model_call.cost is None
    assert result.model_call.error_message is None
    assert result.model_call.prompt_log is not None
    assert result.model_call.prompt_log.prompt_template_name
    assert result.model_call.prompt_log.system_prompt == BACKTEST_CODE_SYSTEM_PROMPT
    assert json.loads(result.model_call.prompt_log.user_prompt)["strategy_spec"]["strategy_id"] == "rsi_rebound"
    assert json.loads(result.model_call.prompt_log.assistant_response)["candidates"]
    assert result.model_call.prompt_log.variables_jsonb["strategy_spec"]["strategy_id"] == "rsi_rebound"
    assert result.model_call.prompt_log.masked is False


def test_aoai_code_generator_marks_provider_failure_and_keeps_prompt_for_fallback(monkeypatch):
    from ai_graph.audit import begin_model_call, finish_model_call
    from ai_graph.llm.base import LLMClientError

    class FailingClient:
        def generate_json(self, request):
            call_id = begin_model_call(
                task_type=request.task_type or request.schema_name,
                provider="aoai",
                model_name="gpt-failing",
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                variables_jsonb=request.variables_jsonb,
                prompt_template_name=request.prompt_template_name,
                prompt_version=request.prompt_version,
                temperature=request.temperature,
                response_schema_name=request.schema_name,
                web_search_used=request.enable_web_search,
            )
            finish_model_call(
                call_id,
                status="failed",
                assistant_response=None,
                model_name="gpt-failing",
                retry_count=2,
                error_type="LLMClientError",
                error_message="LLMClientError during model call",
            )
            raise LLMClientError("provider detail", retry_count=2)

    monkeypatch.setattr("ai_graph.llm.factory.create_llm_client", lambda role=None: FailingClient())
    generator = AOAICodeGenerator()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="모델 실패 뒤 fallback 코드를 만들어줘",
        parsed_strategy_jsonb={
            "strategy_id": "provider_failure",
            "name": "Provider Failure",
            "market": "KRX",
            "timeframe": "daily",
            "entry_conditions": [{"left": "rsi", "operator": "lte", "right": 30}],
            "exit_conditions": [],
            "indicators": ["RSI"],
            "risk_constraints": {"max_position_pct": 0.1},
            "assumptions": [],
            "source_refs": [],
            "confidence": 0.8,
        },
        strategy_id="provider_failure",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )

    result = asyncio.run(generator.generate(request, trace_id=uuid4()))

    assert result.model_call is not None
    assert result.model_call.provider == "aoai"
    assert result.model_call.model_name == "gpt-failing"
    assert result.model_call.status == "failed"
    assert result.model_call.error_type == "LLMClientError"
    assert result.model_call.retry_count == 2
    assert result.model_call.prompt_log is not None
    assert result.model_call.prompt_log.system_prompt == BACKTEST_CODE_SYSTEM_PROMPT
    assert result.model_call.prompt_log.assistant_response is None
    assert result.model_call.prompt_log.masked is False


@pytest.mark.parametrize(
    ("finish_values", "fallback_exception", "expected_error_type", "expected_error_message"),
    [
        (
            {
                "status": "failed",
                "assistant_response": None,
                "retry_count": 2,
                "error_type": "LLMClientError",
                "error_message": "Model request timed out after retry attempts.",
            },
            "private deterministic fallback detail",
            "LLMClientError",
            "Model request timed out after retry attempts.",
        ),
        (
            {
                "status": "succeeded",
                "assistant_response": '{"candidates":["unsafe"]}',
                "retry_count": 0,
            },
            "safe fallback candidates failed AST validation",
            "LLMOutputValidationError",
            "LLM-generated and deterministic fallback candidates failed validation.",
        ),
    ],
    ids=["provider-and-fallback-failed", "model-output-and-safe-fallback-invalid"],
)
def test_aoai_code_generator_keeps_model_call_when_fallback_also_fails(
    monkeypatch,
    finish_values,
    fallback_exception,
    expected_error_type,
    expected_error_message,
):
    from ai_graph.audit import begin_model_call, finish_model_call

    class DummyClient:
        pass

    class DummyAOAIClient:
        pass

    class DummyMockClient:
        pass

    prompt_request = SimpleNamespace(
        schema_name="backtest_code_candidates.v1",
        prompt_template_name="quantagent.backtest_code.v1",
        prompt_version="quantagent.backtest_code.v1",
        system_prompt="full system prompt",
        user_prompt="full user prompt",
        variables_jsonb={"strategy_id": "double_failure"},
    )

    def fail_after_model_call(request, llm_client=None):
        call_id = begin_model_call(
            task_type="backtest_code_generation",
            provider="aoai",
            model_name="gpt-failed",
            system_prompt=prompt_request.system_prompt,
            user_prompt=prompt_request.user_prompt,
            variables_jsonb=prompt_request.variables_jsonb,
            prompt_template_name=prompt_request.prompt_template_name,
            prompt_version=prompt_request.prompt_version,
            temperature=None,
            response_schema_name=prompt_request.schema_name,
            web_search_used=False,
        )
        finish_model_call(
            call_id,
            model_name="gpt-failed",
            **finish_values,
        )
        raise ValueError(fallback_exception)

    monkeypatch.setattr(
        "app.services.ai_backtest_runtime._load_generation_modules",
        lambda: (
            lambda prompt, variant, retrieval: SimpleNamespace(strategy_id="double_failure"),
            lambda strategy, variant: prompt_request,
            lambda role=None: DummyClient(),
            fail_after_model_call,
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
        natural_language_prompt="모델과 fallback이 모두 실패하는 요청",
        parsed_strategy_jsonb={"strategy_id": "double_failure"},
        strategy_id="double_failure",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )

    with pytest.raises(CodeGenerationFailure) as exc_info:
        asyncio.run(generator.generate(request, trace_id=uuid4()))

    model_call = exc_info.value.model_call
    assert model_call.status == "failed"
    assert model_call.error_type == expected_error_type
    assert model_call.error_message == expected_error_message
    assert model_call.retry_count == finish_values["retry_count"]
    assert model_call.prompt_log.system_prompt == "full system prompt"
    assert model_call.prompt_log.user_prompt == "full user prompt"
    assert model_call.prompt_log.assistant_response == finish_values["assistant_response"]
    assert fallback_exception not in model_call.error_message


def test_aoai_code_generator_marks_response_schema_fallback_as_failed(monkeypatch):
    from ai_graph.audit import begin_model_call, finish_model_call

    class WrongSchemaClient:
        def generate_json(self, request):
            call_id = begin_model_call(
                task_type=request.task_type or request.schema_name,
                provider="aoai",
                model_name="gpt-wrong-schema",
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                variables_jsonb=request.variables_jsonb,
                prompt_template_name=request.prompt_template_name,
                prompt_version=request.prompt_version,
                temperature=request.temperature,
                response_schema_name=request.schema_name,
                web_search_used=request.enable_web_search,
            )
            finish_model_call(
                call_id,
                status="succeeded",
                assistant_response='{"unexpected":true}',
                model_name="gpt-wrong-schema",
            )
            return {"unexpected": True}

    monkeypatch.setattr("ai_graph.llm.factory.create_llm_client", lambda role=None: WrongSchemaClient())
    generator = AOAICodeGenerator()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="잘못된 응답 스키마를 fallback 처리해줘",
        parsed_strategy_jsonb={
            "strategy_id": "wrong_schema",
            "name": "Wrong Schema",
            "market": "KRX",
            "timeframe": "daily",
            "entry_conditions": [{"left": "rsi", "operator": "lte", "right": 30}],
            "exit_conditions": [],
            "indicators": ["RSI"],
            "risk_constraints": {"max_position_pct": 0.1},
            "assumptions": [],
            "source_refs": [],
            "confidence": 0.8,
        },
        strategy_id="wrong_schema",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )

    result = asyncio.run(generator.generate(request, trace_id=uuid4()))

    assert result.model_call is not None
    assert result.model_call.status == "failed"
    assert result.model_call.error_type == "LLMResponseSchemaError"
    assert result.model_call.error_message == (
        "Model response did not match the required schema; deterministic fallback code was executed."
    )
    assert result.model_call.response_schema_name == BACKTEST_CODE_SCHEMA_NAME
    assert result.model_call.web_search_used is False
    assert result.model_call.prompt_log is not None
    assert result.model_call.prompt_log.assistant_response == '{"unexpected":true}'


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
    assert result.model_call.error_type == "LLMOutputValidationError"
    assert result.model_call.error_message == "LLM generated candidates failed validation; deterministic fallback code was executed."
    assert result.model_call.prompt_log is not None
    assert result.model_call.prompt_log.system_prompt == "system prompt"
    assert result.model_call.prompt_log.user_prompt == "user prompt"
    assert result.model_call.prompt_log.masked is False
