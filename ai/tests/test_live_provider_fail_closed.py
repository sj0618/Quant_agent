import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_graph.api import create_app
from ai_graph.data_sources.db import PostgresPipelineDataSource
from ai_graph.jobs import InMemoryAnalysisJobStore
from ai_graph.llm import role_calls
from ai_graph.llm.base import LLMClientError, LLMJsonRequest
from ai_graph.llm.role_calls import RoleDebatePayload
from ai_graph.nodes.backtest_code import (
    MAX_VALIDATION_FEEDBACK_CHARS,
    MAX_VALIDATION_FEEDBACK_ITEMS,
    TRUNCATED_VALIDATION_FEEDBACK,
    Loop3Request,
    _candidate_validation_feedback,
    generate_loop3_candidates,
)
from ai_graph.schemas import StrategySpec


class FailingLLMClient:
    def generate_json(self, _request: LLMJsonRequest) -> dict:
        raise LLMClientError("provider unavailable")


class InvalidSchemaLLMClient:
    def generate_json(self, _request: LLMJsonRequest) -> dict:
        return {"candidates": ["not a valid candidate"]}


class UnsafeCodeLLMClient:
    def generate_json(self, _request: LLMJsonRequest) -> dict:
        return {
            "candidates": [
                "import os\ndef build_signals(prices):\n    return []\n",
                "def helper(prices):\n    return []\n",
                "class Strategy:\n    pass\n",
            ],
            "fallback_reasons": [],
        }


class UnsafeThenSafeCodeLLMClient(UnsafeCodeLLMClient):
    def __init__(self) -> None:
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.requests.append(request)
        if len(self.requests) == 1:
            return super().generate_json(request)
        safe_code = (
            "def build_signals(prices):\n"
            "    signals = []\n"
            "    for row in prices:\n"
            "        signals.append({'date': row['date'], 'action': 'HOLD', 'price': row['close']})\n"
            "    return signals\n"
        )
        return {"candidates": [safe_code, safe_code, safe_code], "fallback_reasons": []}


class RuntimeIncompatibleThenSafeCodeLLMClient(UnsafeThenSafeCodeLLMClient):
    def generate_json(self, request: LLMJsonRequest) -> dict:
        if not self.requests:
            self.requests.append(request)
            return {
                "candidates": [
                    "import pandas\n"
                    "def build_signals(prices):\n"
                    f"    return []  # candidate {index}\n"
                    for index in range(12)
                ],
                "fallback_reasons": [],
            }
        return super().generate_json(request)


class IncompleteRoleLLMClient:
    def generate_json(self, _request: LLMJsonRequest) -> dict:
        return {"summary": "summary", "unexpected": "ignored before strict validation"}


class CompleteRoleLLMClient:
    def generate_json(self, _request: LLMJsonRequest) -> dict:
        return {
            "role": "REPORT_JUDGE",
            "summary": "summary",
            "evidence": [],
            "concerns": [],
            "recommendation": "HOLD",
            "confidence": 0.5,
            "validation_results": {"checks": []},
            "citations": [],
            "fallback_reasons": ["provider-controlled internal metadata"],
        }


class ExtraRoleLLMClient(CompleteRoleLLMClient):
    def generate_json(self, request: LLMJsonRequest) -> dict:
        return {**super().generate_json(request), "unexpected": "must be rejected"}


class OutOfRangeRoleLLMClient(CompleteRoleLLMClient):
    def generate_json(self, request: LLMJsonRequest) -> dict:
        return {**super().generate_json(request), "confidence": 1.5}


def test_aoai_role_call_failure_is_not_replaced_with_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    monkeypatch.setattr(role_calls, "create_llm_client", lambda *, role: FailingLLMClient())

    with pytest.raises(LLMClientError, match="provider unavailable"):
        role_calls.generate_role_debate(
            role="RESEARCH_BULL",
            task="Find supporting evidence.",
            context={"query": "005930 RSI"},
            fallback=RoleDebatePayload(role="RESEARCH_BULL", summary="fallback"),
        )


def test_aoai_role_call_requires_the_complete_output_contract(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    monkeypatch.setattr(role_calls, "create_llm_client", lambda *, role: IncompleteRoleLLMClient())

    with pytest.raises(ValidationError, match="validation errors"):
        role_calls.generate_role_debate(
            role="RESEARCH_BULL",
            task="Find supporting evidence.",
            context={"query": "005930 RSI"},
            fallback=RoleDebatePayload(role="RESEARCH_BULL", summary="fallback"),
        )


def test_aoai_role_call_keeps_caller_role_and_internal_metadata(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    monkeypatch.setattr(role_calls, "create_llm_client", lambda *, role: CompleteRoleLLMClient())

    payload = role_calls.generate_role_debate(
        role="RESEARCH_BULL",
        task="Find supporting evidence.",
        context={"query": "005930 RSI"},
        fallback=RoleDebatePayload(role="RESEARCH_BULL", summary="fallback"),
    )

    assert payload.role == "RESEARCH_BULL"
    assert payload.fallback_reasons == []


def test_aoai_role_call_rejects_unexpected_fields(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    monkeypatch.setattr(role_calls, "create_llm_client", lambda *, role: ExtraRoleLLMClient())

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        role_calls.generate_role_debate(
            role="RESEARCH_BULL",
            task="Find supporting evidence.",
            context={"query": "005930 RSI"},
            fallback=RoleDebatePayload(role="RESEARCH_BULL", summary="fallback"),
        )


def test_aoai_role_call_keeps_local_semantic_constraints(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    monkeypatch.setattr(role_calls, "create_llm_client", lambda *, role: OutOfRangeRoleLLMClient())

    with pytest.raises(ValidationError, match="less than or equal to 1"):
        role_calls.generate_role_debate(
            role="RESEARCH_BULL",
            task="Find supporting evidence.",
            context={"query": "005930 RSI"},
            fallback=RoleDebatePayload(role="RESEARCH_BULL", summary="fallback"),
        )


def test_aoai_backtest_schema_failure_is_not_replaced_with_generated_code(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    strategy = StrategySpec(
        strategy_id="rsi_rebound_a",
        name="RSI rebound",
        market="KRX",
        timeframe="daily",
        entry_conditions=[{"left": "rsi", "operator": "lte", "right": 30}],
        exit_conditions=[],
        indicators=["RSI"],
        risk_constraints={"max_position_pct": 0.1},
        assumptions=[],
        source_refs=[],
        confidence=0.8,
    )

    with pytest.raises(ValidationError, match="validation error"):
        generate_loop3_candidates(
            Loop3Request(strategy=strategy, variant="A", trace_id="trace-live-llm"),
            llm_client=InvalidSchemaLLMClient(),
        )


def test_aoai_unsafe_code_is_not_replaced_with_generated_code(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    strategy = StrategySpec(
        strategy_id="custom_a",
        name="Custom strategy",
        market="KRX",
        timeframe="daily",
        entry_conditions=[{"left": "rsi", "operator": "lte", "right": 30}],
        exit_conditions=[],
        indicators=["RSI"],
        risk_constraints={"max_position_pct": 0.1},
        assumptions=[],
        source_refs=[],
        confidence=0.8,
    )

    with pytest.raises(ValueError, match="no safe backtest candidates"):
        generate_loop3_candidates(
            Loop3Request(strategy=strategy, variant="A", trace_id="trace-unsafe-llm"),
            llm_client=UnsafeCodeLLMClient(),
        )


def test_aoai_unsafe_code_is_regenerated_once_with_validation_feedback(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    client = UnsafeThenSafeCodeLLMClient()
    strategy = StrategySpec(
        strategy_id="custom_a",
        name="Custom strategy",
        market="KRX",
        timeframe="daily",
        entry_conditions=[{"left": "rsi", "operator": "lte", "right": 30}],
        exit_conditions=[],
        indicators=["RSI"],
        risk_constraints={"max_position_pct": 0.1},
        assumptions=[],
        source_refs=[],
        confidence=0.8,
    )

    result = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="trace-live-retry"),
        llm_client=client,
    )

    assert len(client.requests) == 2
    feedback = client.requests[1].variables_jsonb["validation_feedback"]
    assert "import 'os' is not allowed" in feedback
    assert result.selected_candidate.validation_ok is True


def test_aoai_regeneration_feedback_is_bounded() -> None:
    candidate = "\n".join(f"def helper_{index}(prices):\n    return []" for index in range(100))

    feedback = _candidate_validation_feedback([candidate])

    assert len(feedback) <= MAX_VALIDATION_FEEDBACK_ITEMS
    assert sum(len(item) for item in feedback) <= MAX_VALIDATION_FEEDBACK_CHARS
    assert feedback[-1] == TRUNCATED_VALIDATION_FEEDBACK


def test_aoai_runtime_incompatible_imports_are_regenerated_before_backtest(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "aoai")
    client = RuntimeIncompatibleThenSafeCodeLLMClient()
    strategy = StrategySpec(
        strategy_id="custom_a",
        name="Custom strategy",
        market="KRX",
        timeframe="daily",
        entry_conditions=[{"left": "rsi", "operator": "lte", "right": 30}],
        exit_conditions=[],
        indicators=["RSI"],
        risk_constraints={"max_position_pct": 0.1},
        assumptions=[],
        source_refs=[],
        confidence=0.8,
    )

    result = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="trace-runtime-import-retry"),
        llm_client=client,
    )

    assert len(client.requests) == 2
    assert (
        "import 'pandas' is not allowed"
        in client.requests[1].variables_jsonb["validation_feedback"]
    )
    assert result.selected_candidate.validation_ok is True


def test_analysis_api_returns_failed_job_when_configured_database_is_down(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "0")
    monkeypatch.setenv("AI_LLM_PROVIDER", "mock")
    monkeypatch.setenv("AI_DATABASE_DSN", "postgresql://quant-db")

    def fail_to_load(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(PostgresPipelineDataSource, "load", fail_to_load)
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.post(
        "/analysis-jobs",
        json={"query": "005930 RSI가 30 이하이면 매수하고 70 이상이면 매도"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["result"]["status"] == "failed"
    assert payload["result"]["failure_cause"] is not None
    assert payload["result"]["user_payload"]["performance"] is None
    assert payload["result"]["user_payload"]["report"] is None
