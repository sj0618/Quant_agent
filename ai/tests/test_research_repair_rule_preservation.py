"""A repair turn fixes the named fault; it does not get to rewrite the researched rule.

Observed on the deployed release (job_d4267b1043a5, trace a5b5bb219863d8db): the first
research turn for "RSI(14)가 30 이하로 떨어진 코스피 종목을 사고, 70 이상이면 파는 전략"
compiled (rsi lte 30 / rsi gte 70) and was refused for a fault outside the rule. The
repair turn answered with the same rule plus ``window=14, aggregate="last"``, which the
compiler refuses, so a basic request ended in need_clarification.  The repair is now
judged with the first turn's rule whenever it changed one, and stands on its own only
when that first rule was itself the fault.
"""

from __future__ import annotations

import copy

import pytest

from ai_graph.llm.base import LLMJsonRequest
from ai_graph.nodes import strategy_research
from ai_graph.nodes.strategy_research import (
    StrategyResearchError,
    research_strategy_execution_spec,
)

QUERY = "RSI(14)가 30 이하로 떨어진 코스피 종목을 사고, 70 이상이면 파는 전략"
METRICS = ["rsi", "close", "volume"]

ENTRY = {"left": "rsi", "operator": "lte", "right": 30, "description": "RSI(14)가 30 이하"}
EXIT = {"left": "rsi", "operator": "gte", "right": 70, "description": "RSI(14)가 70 이상"}
# What the deployed repair turn actually returned: the rule with a lookback bolted on.
REWRITTEN_ENTRY = {**ENTRY, "window": 14, "aggregate": "last"}
REWRITTEN_EXIT = {**EXIT, "window": 14, "aggregate": "last"}


class _ScriptedClient:
    def __init__(self, *responses: dict) -> None:
        self._responses = list(responses)
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.requests.append(request)
        return self._responses[min(len(self.requests) - 1, len(self._responses) - 1)]


def _source(index: int, *, scheme: str = "https") -> dict:
    return {
        "source_id": f"source-{index}",
        "title": f"Source {index}",
        "url": f"{scheme}://example.com/rsi-{index}",
        "claim": f"Evidence angle {index} on RSI mean reversion in KRX names.",
        "limitation": f"Source {index} is not a post-cost KRX proof.",
    }


def _response(*, entry: dict, exit_: dict, sources: int = 1, scheme: str = "https", **overrides: object) -> dict:
    candidate: dict[str, object] = {
        "candidate_id": "research-candidate-1",
        "title": "RSI(14) 과매도 평균회귀",
        "hypothesis": "과매도 후 평균회귀",
        "counter_hypothesis": "추세장에서는 과매도가 지속된다",
        "entry_conditions": [entry],
        "exit_conditions": [exit_],
        "required_metrics": ["rsi", "close"],
        "assumptions": ["universe는 point-in-time KOSPI 보통주"],
        "backtest_years": 5,
        "backtest_period_basis": "최근 5개년 KOSPI 거래일",
        "source_ids": [f"source-{index}" for index in range(1, sources + 1)],
    }
    candidate.update(overrides)
    return {
        "resolution_summary": "요청한 RSI(14) 규칙은 지원 metric인 rsi로 직접 표현 가능하다.",
        "sources": [_source(index, scheme=scheme) for index in range(1, sources + 1)],
        "candidates": [candidate],
    }


def _deep(response: dict) -> dict:
    """The evidence fields a live brief must carry; the rule is left alone."""

    deep = copy.deepcopy(response)
    deep["candidates"][0].update(
        {
            "ai_assumptions": ["청산 규칙이 RSI 70으로 명시돼 보유 기간 가정은 없다."],
            "economic_rationale": "단기 과잉반응 후 평균회귀",
            "falsification_conditions": [
                {"condition": "비용 차감 후 초과성과 0 이하", "interpretation": "가설 기각"}
            ],
            "expected_turnover": "중간 수준의 회전율 (repair turn)",
            "regime_risks": ["강한 하락 추세"],
        }
    )
    return deep


def _rule(spec) -> tuple[list[tuple], list[tuple]]:
    candidate = spec.candidates[0]
    fields = ("left", "operator", "right", "window", "aggregate")
    return (
        [tuple(getattr(c, f) if f != "operator" else c.operator.value for f in fields) for c in candidate.entry_conditions],
        [tuple(getattr(c, f) if f != "operator" else c.operator.value for f in fields) for c in candidate.exit_conditions],
    )


def test_a_repair_that_rewrites_a_compiled_rule_keeps_the_first_turn_rule() -> None:
    # First turn: the rule compiles; a source URL is not https, so the schema refuses it.
    first = _response(entry=ENTRY, exit_=EXIT, scheme="http")
    # Repair turn: fixes the URL, but bolts a 14-bar lookback onto both conditions.
    repair = _deep(_response(entry=REWRITTEN_ENTRY, exit_=REWRITTEN_EXIT))
    client = _ScriptedClient(first, repair)

    spec = research_strategy_execution_spec(query=QUERY, available_metrics=METRICS, llm_client=client)

    assert [r.task_type for r in client.requests] == [
        "strategy_research_resolution",
        "strategy_research_resolution_repair",
    ]
    assert _rule(spec) == ([("rsi", "lte", 30, None, None)], [("rsi", "gte", 70, None, None)])
    # Everything outside the rule is the repaired turn's.
    assert spec.sources[0].url == "https://example.com/rsi-1"
    assert spec.candidates[0].expected_turnover == "중간 수준의 회전율 (repair turn)"
    assert spec.candidates[0].regime_risks == ["강한 하락 추세"]


def test_a_repair_that_fixes_an_unexecutable_first_rule_stands_on_its_own() -> None:
    first = _response(entry=REWRITTEN_ENTRY, exit_=REWRITTEN_EXIT)
    repair = _response(entry=ENTRY, exit_=EXIT)
    client = _ScriptedClient(first, repair)

    spec = research_strategy_execution_spec(query=QUERY, available_metrics=METRICS, llm_client=client)

    failure = client.requests[1].variables_jsonb["untrusted_quoted_context"]
    assert failure["previous_validation_failure"]["code"] == "research_semantics_unsupported"
    assert _rule(spec) == ([("rsi", "lte", 30, None, None)], [("rsi", "gte", 70, None, None)])


def test_a_repair_that_changes_the_period_of_a_compiled_rule_keeps_the_first_period() -> None:
    first = _response(entry=ENTRY, exit_=EXIT, scheme="http")
    repair = _deep(_response(entry=ENTRY, exit_=EXIT, backtest_years=2, required_metrics=["rsi", "close", "volume"]))
    client = _ScriptedClient(first, repair)

    spec = research_strategy_execution_spec(query=QUERY, available_metrics=METRICS, llm_client=client)

    assert spec.candidates[0].backtest_years == 5
    assert spec.candidates[0].required_metrics == ["rsi", "close"]


def test_a_live_repair_for_a_shallow_brief_keeps_the_compiled_first_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The live lane refuses a one-source brief; the repair deepens the evidence but
    # rewrites the rule on the way.  The reader still gets the rule they asked for.
    first = _response(entry=ENTRY, exit_=EXIT)
    repair = _deep(_response(entry=REWRITTEN_ENTRY, exit_=REWRITTEN_EXIT, sources=5))
    client = _ScriptedClient(first, repair)
    monkeypatch.setattr(strategy_research, "create_llm_client", lambda *, role: client)

    spec = research_strategy_execution_spec(query=QUERY, available_metrics=METRICS)

    failure = client.requests[1].variables_jsonb["untrusted_quoted_context"]
    assert failure["previous_validation_failure"]["code"] == "research_evidence_incomplete"
    assert _rule(spec) == ([("rsi", "lte", 30, None, None)], [("rsi", "gte", 70, None, None)])
    assert len(spec.sources) == 5
    assert spec.candidates[0].source_ids == [f"source-{i}" for i in range(1, 6)]


def test_a_rule_that_is_unexecutable_in_both_turns_is_still_refused() -> None:
    first = _response(entry=REWRITTEN_ENTRY, exit_=REWRITTEN_EXIT, scheme="http")
    repair = _response(entry=REWRITTEN_ENTRY, exit_=REWRITTEN_EXIT)
    client = _ScriptedClient(first, repair)

    with pytest.raises(StrategyResearchError) as failure:
        research_strategy_execution_spec(query=QUERY, available_metrics=METRICS, llm_client=client)

    assert failure.value.cause_code == "research_resolution_invalid_after_repair"


def test_a_description_only_difference_is_not_a_rewrite() -> None:
    first = _response(entry=ENTRY, exit_=EXIT, scheme="http")
    repair = _response(entry={**ENTRY, "description": "RSI 30 이하"}, exit_={**EXIT, "description": None})

    assert strategy_research._with_first_turn_rules(first, repair, query=QUERY) is None


def test_a_missing_first_candidate_leaves_the_repair_alone() -> None:
    repair = _response(entry=ENTRY, exit_=EXIT)

    assert strategy_research._with_first_turn_rules({"candidates": []}, repair, query=QUERY) is None
    assert strategy_research._with_first_turn_rules("not json", repair, query=QUERY) is None


def test_the_repair_prompt_freezes_the_rule() -> None:
    client = _ScriptedClient(_response(entry=ENTRY, exit_=EXIT, scheme="http"), _response(entry=ENTRY, exit_=EXIT))

    research_strategy_execution_spec(query=QUERY, available_metrics=METRICS, llm_client=client)

    prompt = client.requests[1].system_prompt
    assert "Correct only what previous_validation_failure names" in prompt
    assert "do not add window, aggregate, scale" in prompt
    assert "do not substitute a different strategy" in prompt
