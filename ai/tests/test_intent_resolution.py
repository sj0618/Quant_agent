"""What the interpreter does with a request that does not spell the strategy out.

The product promise is that "돈 버는 전략 만들어서 검증해줘" gets a backtested strategy,
not a form. These cover the two halves of that: the interpreter commits to a concrete
strategy, and every stage after it works on that strategy rather than the vague words.
"""

from typing import Any

import pytest

from ai_graph.graph import (
    _strategy_query,
    ambiguity_classifier_node,
    classify_query,
    data_node,
    envelope_node,
)
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.role_calls import resolve_strategy_intent
from ai_graph.schemas import AmbiguityCode, EnvelopeStatus


RESOLVED = (
    "KOSPI·KOSDAQ 화학 업종에서 200일 이동평균 위에 있고 RSI(14)가 40 이하로 눌린 뒤 "
    "거래량이 20일 평균의 1.5배 이상인 종목을 매수, RSI 65 이상에서 청산. 최근 3년 백테스트."
)


class StubIntentClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict[str, Any]:
        self.requests.append(request)
        return self.payload


def _intent_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "interpretation": "화학 업종에서 매수할 종목을 찾아달라는 요청입니다.",
        "resolved_query": RESOLVED,
        "assumptions": [
            "기간 미지정 → 최근 3년으로 백테스트합니다.",
            "위험 성향 미지정 → 중립으로 두고 손절 8%를 적용합니다.",
        ],
        "scope": "supported",
        "scope_reason": "",
        "citations": [{"title": "KRX 업종 분류", "url": "https://example.com/krx"}],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def live_intent(monkeypatch):
    """Put the interpreter on its live path with a stubbed provider."""

    def install(payload: dict[str, Any]) -> StubIntentClient:
        client = StubIntentClient(payload)
        monkeypatch.setattr(
            "ai_graph.llm.role_calls.create_llm_client",
            lambda environ=None, *, role=None: client,
        )
        monkeypatch.setattr("ai_graph.llm.role_calls.is_live_llm_provider", lambda: True)
        return client

    return install


def test_intent_resolution_searches_the_web_before_committing(live_intent) -> None:
    """A strategy picked from memory alone is the same textbook rule every time; the
    point of resolving vagueness here is to ground the choice in current conditions."""

    client = live_intent(_intent_payload())

    resolved = resolve_strategy_intent(query="화학 관련주 사줘", capabilities=[])

    assert resolved is not None
    assert client.requests[0].enable_web_search is True
    assert resolved["resolved_query"] == RESOLVED


def test_vague_request_becomes_a_concrete_strategy_the_rest_of_the_graph_runs(
    live_intent,
) -> None:
    live_intent(_intent_payload())

    state = ambiguity_classifier_node({"user_query": "화학 관련주 사줘", "trace_id": "t"})

    assert state["status"] == EnvelopeStatus.READY.value
    assert state["resolved_query"] == RESOLVED
    # Downstream stages must never see the words that were too vague to act on.
    assert _strategy_query({"user_query": "화학 관련주 사줘", **state}) == RESOLVED


def test_resolved_strategy_is_what_gets_screened(live_intent) -> None:
    live_intent(_intent_payload())

    state: dict[str, Any] = {"user_query": "화학 관련주 사줘", "trace_id": "t"}
    state.update(ambiguity_classifier_node(state))
    data = data_node(state)

    # parse_semantic_slots reads the resolved sentence, so the indicators it plans for
    # come from the strategy the interpreter chose - not from a query that named none.
    assert "rsi" in data["semantic_slots"]["indicator"]
    assert "sma_200" in data["semantic_slots"]["indicator"]


def test_the_decisions_made_for_the_user_are_disclosed_on_the_result(live_intent) -> None:
    """Deciding on the user's behalf is only acceptable if they can see what was
    decided - the disclosure moves to the answer instead of blocking it as a question."""

    live_intent(_intent_payload())

    state: dict[str, Any] = {"user_query": "화학 관련주 사줘", "trace_id": "t", "debug_ref": "d"}
    state.update(ambiguity_classifier_node(state))
    state["data"] = {"candidate_cards": []}
    envelope = envelope_node(state)["envelope"]

    message = envelope["user_payload"]["message"]
    assert "최근 3년으로 백테스트합니다" in message
    assert "손절 8%" in message
    assert envelope["user_payload"]["question"] is None


def test_small_talk_is_answered_without_paying_for_a_web_search(live_intent) -> None:
    """A greeting should not run a backtest - but it should not cost an AOAI call with
    web search either, so the obvious cases are settled before the model is reached."""

    client = live_intent(_intent_payload())

    state = ambiguity_classifier_node({"user_query": "ㅎㅇㅎㅇ", "trace_id": "t"})

    assert state["ambiguity"]["category"] == AmbiguityCode.NO_STRATEGY_INTENT.value
    assert client.requests == []


def test_the_model_can_also_call_a_message_not_a_request(live_intent) -> None:
    """Whatever the cheap check does not settle, the model decides - phrased so that
    only "not asking for anything" qualifies, never "asking vaguely"."""

    live_intent(
        _intent_payload(
            scope="not_a_request",
            resolved_query="",
            scope_reason="전략 요청이 아니라 서비스 사용법을 묻는 메시지입니다.",
        )
    )

    state = ambiguity_classifier_node(
        {"user_query": "이 서비스는 어떤 데이터를 쓰나요?", "trace_id": "t"}
    )

    assert state["ambiguity"]["category"] == AmbiguityCode.NO_STRATEGY_INTENT.value
    assert "resolved_query" not in state


def test_out_of_scope_asset_class_still_stops(live_intent) -> None:
    live_intent(
        _intent_payload(scope="unsupported", scope_reason="옵션은 KRX 현물 데이터로 검증할 수 없습니다.")
    )

    state = ambiguity_classifier_node({"user_query": "옵션 양매도 해줘", "trace_id": "t"})

    assert state["status"] == EnvelopeStatus.REJECTED.value
    assert state["ambiguity"]["reason"] == "옵션은 KRX 현물 데이터로 검증할 수 없습니다."
    assert "resolved_query" not in state


def test_an_empty_resolution_is_refused_rather_than_passed_downstream(live_intent) -> None:
    """Handing an empty or blank resolution to the screener would silently restore the
    raw vague query - the exact failure this call exists to prevent."""

    live_intent(_intent_payload(resolved_query="   "))

    assert resolve_strategy_intent(query="화학 관련주 사줘", capabilities=[]) is None


def test_a_citation_without_a_title_still_resolves(live_intent) -> None:
    """Deployed AOAI models cite as {"url": ...} with no title whenever provider-side
    structured outputs are not enforced; that shape killed every production analysis
    at the Ambiguity Classifier and must validate instead."""

    live_intent(_intent_payload(citations=[{"url": "https://example.com/krx"}]))

    resolved = resolve_strategy_intent(query="화학 관련주 사줘", capabilities=[])

    assert resolved is not None
    assert resolved["citations"] == [{"title": "", "url": "https://example.com/krx"}]


def test_provider_failure_still_runs_the_analysis() -> None:
    """Mock mode and provider outages must not turn into questions either; without a
    model to interpret with, the fallback answers the one question that needs no
    model - is this a KRX equity request at all."""

    state = ambiguity_classifier_node({"user_query": "돈 버는 전략 만들어서 검증해줘", "trace_id": "t"})

    assert state["status"] == EnvelopeStatus.READY.value
    assert "intent" not in state
    assert classify_query("돈 버는 전략 만들어서 검증해줘") == AmbiguityCode.READY
