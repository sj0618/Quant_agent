"""A greeting must not pay for a web-grounded research call.

"안녕" was classified "automatic", spent ~26s on a V3 research call, and the API then
showed the INPUT_AMBIGUOUS question "먼저 어떤 후보 전략으로 구체화할까요?" with three
generic strategy options - a question about nothing the user said.
"""

from __future__ import annotations

import pytest

from ai_graph.api import _clarification_envelope
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.research_contract import RuleDraftSigner, build_rule_draft
from ai_graph.schemas import EnvelopeStatus

NO_STRATEGY_INTENT_QUESTION = "어떤 투자 전략이나 매매 조건을 분석할까요?"
RESEARCH_FIRST_QUESTION = "최신 애널리스트 리포트를 조사해 백테스트 후보를 도출하겠습니다."


class _RefusingClient:
    """Any call at all is the failure this test is about."""

    def generate_json(self, request: LLMJsonRequest) -> dict:
        raise AssertionError("small talk must not reach the research provider")


def _signer() -> RuleDraftSigner:
    return RuleDraftSigner("test-rule-draft-secret", key_version="test-v1")


@pytest.mark.parametrize("query", ["안녕", "안녕하세요", "고마워요", "오늘 날씨 어때"])
def test_small_talk_returns_a_non_executable_draft_without_any_research_call(
    query: str,
) -> None:
    draft = build_rule_draft(
        query=query,
        user_id="user-1",
        signer=_signer(),
        llm_client=_RefusingClient(),
        use_llm=True,
    )

    assert draft.is_executable is False
    assert draft.clarification_required is True
    assert draft.strategy_execution_spec is None
    assert draft.parse_token is None
    assert draft.editable_summary == NO_STRATEGY_INTENT_QUESTION
    assert query not in draft.model_dump_json()


def test_small_talk_clarification_asks_what_to_analyse_not_which_candidate() -> None:
    query = "안녕"
    draft = build_rule_draft(
        query=query,
        user_id="user-1",
        signer=_signer(),
        llm_client=_RefusingClient(),
        use_llm=True,
    )

    envelope = _clarification_envelope(draft, query=query, trace_id="trace-1")

    assert envelope.status is EnvelopeStatus.NEED_CLARIFICATION
    assert envelope.user_payload.question == NO_STRATEGY_INTENT_QUESTION
    assert envelope.user_payload.options == []
    assert envelope.user_payload.recommended is None


def test_a_real_strategy_request_gets_the_research_first_answer_not_the_greeting() -> None:
    """A real request that cannot be sealed from keywords is answered with the
    research-first message (no static candidate menu), never with the greeting."""

    query = "RSI가 30 이하인 KRX 종목을 검토해 주세요."
    draft = build_rule_draft(query=query, user_id="user-1", signer=_signer(), use_llm=False)

    envelope = _clarification_envelope(draft, query=query, trace_id="trace-2")

    assert draft.is_executable is False
    assert envelope.user_payload.question == RESEARCH_FIRST_QUESTION
    assert envelope.user_payload.question != NO_STRATEGY_INTENT_QUESTION
    assert envelope.user_payload.options
