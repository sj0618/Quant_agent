"""The hybrid scope guard: deterministic floor, LLM second opinion only in the gray zone."""

from __future__ import annotations

import pytest

from ai_graph.preflight import classify_research_request
from ai_graph.scope_review import review_research_scope


def _judge(verdict: str | None):
    calls: list[str] = []

    def judge(query: str) -> str | None:
        calls.append(query)
        return verdict

    judge.calls = calls  # type: ignore[attr-defined]
    return judge


@pytest.mark.parametrize(
    "query",
    (
        "사람들이 많이 쓰는 검증된 퀀트 전략으로 자동 추천해줘",
        "괜찮은 방식 하나 골라줘",
    ),
)
def test_a_recommendation_verb_without_an_object_is_refused_but_adjudicable(query: str) -> None:
    decision = classify_research_request(query)

    assert decision.allowed is False
    assert decision.adjudicable is True


@pytest.mark.parametrize(
    "query",
    (
        "추천 종목을 알려줘",
        "종목 추천 좀",
        "내 계좌 위험성향에 맞는 주식을 추천해 줘",
        "지금 뭘 사야 해?",
        "콜옵션 양매도 전략을 검토해 주세요.",
    ),
)
def test_wording_that_settles_the_question_is_never_adjudicable(query: str) -> None:
    """Whatever already names its object must not get a second opinion, or the guard
    becomes a suggestion."""

    decision = classify_research_request(query)

    assert decision.allowed is False
    assert decision.adjudicable is False

    judge = _judge("strategy")
    assert review_research_scope(query, decision, judge=judge) is decision
    assert judge.calls == []


def test_a_strategy_verdict_overturns_the_ambiguous_refusal() -> None:
    query = "사람들이 많이 쓰는 검증된 퀀트 전략으로 자동 추천해줘"
    decision = classify_research_request(query)

    reviewed = review_research_scope(query, decision, judge=_judge("strategy"))

    assert reviewed.allowed is True
    assert reviewed.reason_code is None


@pytest.mark.parametrize("verdict", ("stocks", "unclear", None, "", "yes"))
def test_anything_other_than_strategy_keeps_the_refusal(verdict: str | None) -> None:
    query = "사람들이 많이 쓰는 검증된 퀀트 전략으로 자동 추천해줘"
    decision = classify_research_request(query)

    assert review_research_scope(query, decision, judge=_judge(verdict)).allowed is False


def test_a_judge_that_raises_leaves_the_request_refused() -> None:
    """Fail closed: a provider outage must not open the guard."""

    def exploding_judge(_query: str) -> str | None:
        raise RuntimeError("provider unavailable")

    query = "사람들이 많이 쓰는 검증된 퀀트 전략으로 자동 추천해줘"
    decision = classify_research_request(query)

    assert review_research_scope(query, decision, judge=exploding_judge).allowed is False


def test_an_allowed_request_is_never_sent_to_the_judge() -> None:
    """The adjudication is one-directional, so an ordinary request pays nothing for it."""

    query = "KOSPI에서 RSI가 30 이하인 종목을 조건식으로 검토해 주세요."
    decision = classify_research_request(query)
    assert decision.allowed is True

    judge = _judge("stocks")
    assert review_research_scope(query, decision, judge=judge).allowed is True
    assert judge.calls == []


def test_mock_provider_keeps_the_deterministic_verdict() -> None:
    """With no live provider the default judge returns None, so nothing is overturned."""

    query = "사람들이 많이 쓰는 검증된 퀀트 전략으로 자동 추천해줘"
    decision = classify_research_request(query)

    assert review_research_scope(query, decision).allowed is False


def test_the_api_lets_an_adjudicated_strategy_request_through(monkeypatch) -> None:
    """Proves the async endpoint actually runs the blocking adjudication off the loop."""

    from fastapi.testclient import TestClient

    from ai_graph.api import ANALYSIS_JOBS_PATH, create_app
    from ai_graph.jobs import InMemoryAnalysisJobStore
    from ai_graph.llm import role_calls

    monkeypatch.setattr(
        role_calls, "classify_recommendation_object", lambda *, query: "strategy"
    )
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.post(
        ANALYSIS_JOBS_PATH,
        json={"query": "사람들이 많이 쓰는 검증된 퀀트 전략으로 자동 추천해줘"},
    )

    assert response.status_code == 201


def test_the_api_still_refuses_when_the_object_is_stocks(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from ai_graph.api import ANALYSIS_JOBS_PATH, create_app
    from ai_graph.jobs import InMemoryAnalysisJobStore
    from ai_graph.llm import role_calls

    monkeypatch.setattr(
        role_calls, "classify_recommendation_object", lambda *, query: "stocks"
    )
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.post(
        ANALYSIS_JOBS_PATH,
        json={"query": "지금 오를 만한 거 추천해줘"},
    )

    assert response.status_code == 422
    assert response.json()["reason_code"] == "personalized_investment_request"
