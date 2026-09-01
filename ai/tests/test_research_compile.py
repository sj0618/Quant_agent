from __future__ import annotations

import pytest

from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.base import LLMTimeoutError
from ai_graph.nodes.research_compile import ResearchCompileV2, compile_research
from ai_graph.schemas import Condition, ConditionOperator, StrategySpec


class _StructuredClient:
    def __init__(self) -> None:
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.requests.append(request)
        return {
            "interpretation": "RSI 조건을 확정된 규칙 그대로 과거 데이터에서 검토합니다.",
            "supporting_rationale": ["진입과 종료 조건이 수치로 명시돼 있습니다."],
            "counterpoints": ["추세가 강한 국면에서는 과매수 상태가 길게 이어질 수 있습니다."],
            "limitations": ["성과 수치는 백테스트 엔진이 계산한 값만 사용합니다."],
        }


class _TimeoutClient:
    def generate_json(self, _request: LLMJsonRequest) -> dict:
        raise LLMTimeoutError("simulated timeout")


def _strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="rsi-14-30-70",
        name="RSI 전략",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator=ConditionOperator.LTE, right=30)],
        exit_conditions=[Condition(left="rsi", operator=ConditionOperator.GTE, right=70)],
        indicators=["rsi"],
        confidence=1.0,
    )


def test_live_research_compile_is_one_bounded_structured_call_without_web_search() -> None:
    client = _StructuredClient()

    compiled = compile_research(
        query="RSI 30 이하 매수, 70 이상 매도",
        strategy=_strategy(),
        data={"pipeline_data_source": {"source": "postgres", "as_of": "2026-08-28"}},
        llm_client=client,
        use_llm=True,
    )

    assert compiled.provider == "aoai"
    assert compiled.interpretation
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.enable_web_search is False
    assert request.max_output_tokens == 700
    assert request.task_type == "research_compile"
    assert "Do not change, add, remove" in request.system_prompt


def test_non_live_research_compile_is_explicitly_marked_deterministic() -> None:
    compiled = compile_research(
        query="RSI 30 이하 매수, 70 이상 매도",
        strategy=_strategy(),
        data=None,
        use_llm=False,
    )

    assert isinstance(compiled, ResearchCompileV2)
    assert compiled.provider == "deterministic"
    assert compiled.limitations


def test_live_research_compile_preserves_provider_failure_subclasses() -> None:
    with pytest.raises(LLMTimeoutError, match="simulated timeout"):
        compile_research(
            query="RSI 30 이하 매수, 70 이상 매도",
            strategy=_strategy(),
            data=None,
            llm_client=_TimeoutClient(),
            use_llm=True,
        )
