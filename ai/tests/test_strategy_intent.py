import pytest

import ai_graph.graph as graph
from ai_graph.schemas import AmbiguityCode, EnvelopeStatus


@pytest.mark.parametrize("query", ["ㅎㅇㅎㅇ", "안녕하세요", "고마워", "오늘 날씨 어때?"])
def test_chitchat_has_no_strategy_intent(query: str) -> None:
    assert graph.classify_query(query) == AmbiguityCode.NO_STRATEGY_INTENT


@pytest.mark.parametrize(
    "query",
    [
        "RSI가 30 이하일 때 매수하는 전략",
        "저평가주 찾아줘",
        "코스피 종목을 백테스트해줘",
        # An allowlist of strategy words decides by what it fails to recognise, and
        # greeted these perfectly clear requests instead of running them.
        "화학 관련주 사줘",
        "돈 버는 전략 만들어서 검증해줘",
        "네가 알아서 설정해",
        "돈 되는 거 없나",
        "요즘 뭐가 오를까",
    ],
)
def test_strategy_requests_keep_entering_the_analysis_pipeline(query: str) -> None:
    assert graph.classify_query(query) != AmbiguityCode.NO_STRATEGY_INTENT


def test_greeting_returns_guidance_without_running_strategy_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        graph,
        "data_node",
        lambda _state: pytest.fail("strategy data node must not run"),
    )

    result = graph.run_analysis("ㅎㅇㅎㅇ", trace_id="no-strategy-intent")

    assert result.status == EnvelopeStatus.NEED_CLARIFICATION
    assert result.strategy_spec is None
    assert result.semantic_slots is None
    assert result.data_requirements == []
    assert result.user_payload.candidate_cards == []
    assert result.user_payload.headline == "전략 입력을 기다리고 있습니다."
    assert result.user_payload.message == "안녕하세요! 분석할 투자 전략이나 매매 조건을 말씀해 주세요."
