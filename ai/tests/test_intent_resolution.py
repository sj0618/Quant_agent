"""What the interpreter does with a request that does not spell the strategy out.

The product promise is that "돈 버는 전략 만들어서 검증해줘" gets a backtested strategy,
not a form. These cover the two halves of that: the interpreter commits to a concrete
strategy, and every stage after it works on that strategy rather than the vague words.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from ai_graph.data_sources.db import PipelineDataBundle
from ai_graph.graph import (
    _unverifiable_ambiguity,
    _strategy_query,
    ambiguity_classifier_node,
    classify_query,
    data_node,
    envelope_node,
    strategy_candidate_cards,
)
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.role_calls import resolve_strategy_intent
from ai_graph.schemas import AmbiguityCode, EnvelopeStatus

RESOLVED = (
    "KOSPI·KOSDAQ 화학 업종에서 200일 이동평균 위에 있고 RSI(14)가 40 이하로 눌린 뒤 "
    "거래량이 20일 평균의 1.5배 이상인 종목을 매수, RSI 65 이상에서 청산. 최근 3년 백테스트."
)


class StubIntentClient:
    def __init__(self, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        self.payloads = payload if isinstance(payload, list) else [payload]
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict[str, Any]:
        self.requests.append(request)
        return self.payloads.pop(0)


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
        "backtest_years": 3,
        "backtest_period_basis": "최근 변동성 국면과 KRX PIT 자료 가용성을 조사해 3년을 선택했습니다.",
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
    assert client.requests[0].web_search_context_size == "high"
    assert client.requests[0].reasoning_effort == "medium"
    assert client.requests[0].max_tool_calls == 8
    assert client.requests[0].prompt_version == "v3"
    assert "never make a\nuser-stated material rule appear tested" in client.requests[0].system_prompt
    assert resolved["resolved_query"] == RESOLVED
    assert resolved["backtest_years"] == 3


def test_live_intent_repairs_a_missing_period_once(live_intent) -> None:
    invalid = _intent_payload()
    invalid.pop("backtest_years")
    client = live_intent([invalid, _intent_payload(backtest_years=2)])

    resolved = resolve_strategy_intent(query="화학 관련주 사줘", capabilities=[])

    assert resolved is not None
    assert resolved["backtest_years"] == 2
    assert [request.task_type for request in client.requests] == [
        "strategy_intent",
        "strategy_intent_repair",
    ]
    assert client.requests[1].enable_web_search is False


@pytest.mark.parametrize("invalid_period", [0, 6, "3"])
def test_live_intent_rejects_invalid_period_after_one_repair(live_intent, invalid_period: object) -> None:
    invalid = _intent_payload(backtest_years=invalid_period)
    client = live_intent([invalid, invalid])

    with pytest.raises(ValidationError):
        resolve_strategy_intent(query="화학 관련주 사줘", capabilities=[])
    assert len(client.requests) == 2


def test_missing_data_preserves_the_exact_rule_and_hides_candidate_cards() -> None:
    ambiguity = _unverifiable_ambiguity(
        [{"label": "공매도 잔고", "reason": "필요한 데이터가 적재되어 있지 않습니다."}]
    )
    cards = [card.model_dump() for card in strategy_candidate_cards("RSI 평균회귀 전략")]
    state: dict[str, Any] = {
        "status": EnvelopeStatus.NEED_CLARIFICATION.value,
        "trace_id": "missing-data-rule",
        "debug_ref": "missing-data-rule",
        "ambiguity": ambiguity,
        "data": {"candidate_cards": cards},
    }

    payload = envelope_node(state)["envelope"]["user_payload"]

    assert "원래 규칙 그대로는 백테스트할 수 없습니다" in payload["message"]
    assert "임의로 빼거나 다른 지표로 바꾸지 않고" in payload["question"]
    assert payload["candidate_cards"] == []
    assert [option["label"] for option in payload["options"]] == [
        "원래 규칙 유지",
        "별도 탐색 가설 만들기",
    ]


def test_vague_request_becomes_a_concrete_strategy_the_rest_of_the_graph_runs(
    live_intent,
) -> None:
    live_intent(_intent_payload())

    state = ambiguity_classifier_node({"user_query": "화학 관련주 사줘", "trace_id": "t"})

    assert state["status"] == EnvelopeStatus.READY.value
    assert state["resolved_query"] == RESOLVED
    # Downstream stages must never see the words that were too vague to act on.
    assert _strategy_query({"user_query": "화학 관련주 사줘", **state}) == RESOLVED


def test_resolved_strategy_is_what_gets_screened(
    live_intent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unit test owns its data adapter; it must not start a live PostgreSQL read."""

    live_intent(_intent_payload())
    captured: dict[str, Any] = {}

    def load_unit_data(*_args: Any, **kwargs: Any) -> PipelineDataBundle:
        captured.update(kwargs)
        return PipelineDataBundle(data_availability={}, metadata={"source": "unit-test"})

    monkeypatch.setattr(
        "ai_graph.graph.load_pipeline_data_from_env",
        load_unit_data,
    )
    monkeypatch.setattr(
        "ai_graph.graph.generate_analyst_strategy_candidates",
        lambda **_kwargs: [],
    )

    state: dict[str, Any] = {"user_query": "화학 관련주 사줘", "trace_id": "t"}
    state.update(ambiguity_classifier_node(state))
    data = data_node(state)

    # parse_semantic_slots reads the resolved sentence, so the indicators it plans for
    # come from the strategy the interpreter chose - not from a query that named none.
    assert "rsi" in data["semantic_slots"]["indicator"]
    assert "sma_200" in data["semantic_slots"]["indicator"]
    assert captured["backtest_lookback_years"] == 3
    assert captured["period_locked"] is True


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


def test_missing_ai_period_stops_before_the_data_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    """A READY state that carries no model-selected period must stop before any data read."""

    monkeypatch.setattr(
        "ai_graph.graph.load_pipeline_data_from_env",
        lambda *_args, **_kwargs: pytest.fail("the loader must not receive an unsealed period"),
    )

    data = data_node(
        {
            "user_query": "돈 버는 전략 만들어서 검증해줘",
            "trace_id": "t",
            "status": EnvelopeStatus.READY.value,
        }
    )

    assert data["status"] == EnvelopeStatus.NEED_CLARIFICATION.value
    assert "백테스트 기간" in data["ambiguity"]["reason"]


def test_mock_mode_period_is_a_recorded_model_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a live provider the mock model still selects the period explicitly, so the
    documented deterministic profile runs end to end without a hidden local default."""

    monkeypatch.setenv("AI_LLM_PROVIDER", "mock")

    state = ambiguity_classifier_node({"user_query": "돈 버는 전략 만들어서 검증해줘", "trace_id": "t"})

    assert state["status"] == EnvelopeStatus.READY.value
    assert state["backtest_period"]["period_locked"] is True
    assert state["backtest_period"]["backtest_years"] == 2
    assert "mock" in state["backtest_period"]["basis"]
    assert classify_query("돈 버는 전략 만들어서 검증해줘") == AmbiguityCode.READY
