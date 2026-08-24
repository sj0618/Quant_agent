from __future__ import annotations

import pytest

from ai_graph.api import CreateAnalysisJobRequest
from ai_graph.preflight import (
    SCOPE_REFUSAL_REASON,
    UNSUPPORTED_SCOPE_REASON,
    classify_research_request,
)


@pytest.mark.parametrize(
    "query",
    (
        "내 보유 종목을 지금 팔아줘",
        "내 계좌 위험성향에 맞는 주식을 추천해 줘",
        "지금 뭘 사야 해?",
        "몇 주 사야 하는지 알려줘",
        "추천 종목을 알려줘",
    ),
)
def test_preflight_refuses_personalized_or_imperative_investment_requests(query: str) -> None:
    decision = classify_research_request(query)

    assert decision.allowed is False
    assert decision.reason_code == SCOPE_REFUSAL_REASON
    public = f"{decision.public_message} {decision.public_example} {decision.public_guidance}"
    assert query not in public


@pytest.mark.parametrize(
    "query",
    (
        "KOSPI에서 RSI가 30 이하이고 거래량이 20일 평균보다 큰 종목을 조건식으로 검토해 주세요.",
        "RSI 30 이하에서 매수하고 70 이상에서 매도하는 규칙을 백테스트해 주세요.",
        "배당수익률 4% 이상, 부채비율 100% 이하 조건을 비교해 주세요.",
    ),
)
def test_preflight_allows_general_research_rules(query: str) -> None:
    decision = classify_research_request(query)

    assert decision.allowed is True
    assert decision.reason_code is None


@pytest.mark.parametrize(
    "query",
    (
        "비트코인 가격으로 전략을 만들어 주세요.",
        "콜옵션 양매도 전략을 검토해 주세요.",
        "미국 주식 나스닥 종목을 찾아주세요.",
    ),
)
def test_preflight_refuses_unambiguous_unsupported_asset_families(query: str) -> None:
    decision = classify_research_request(query)

    assert decision.allowed is False
    assert decision.kind == "unsupported_scope"
    assert decision.reason_code == UNSUPPORTED_SCOPE_REASON
    public = f"{decision.public_message} {decision.public_example} {decision.public_guidance}"
    assert query not in public


def test_analysis_job_openapi_example_uses_a_research_rule_not_an_action_prompt() -> None:
    example = CreateAnalysisJobRequest.model_config["json_schema_extra"]["examples"][0]["query"]

    assert classify_research_request(example).allowed is True
    assert not {term for term in ("매수", "매도", "보유", "추천") if term in example}


@pytest.mark.parametrize(
    "query",
    (
        "사람들이 많이 쓰는 검증된 퀀트 전략을 자동으로 선택해 검토해 주세요",
        "널리 쓰이는 검증된 퀀트 전략을 자동으로 만들어 검토해 주세요",
        "KOSPI 대형주 중에서 모멘텀이 강한 종목을 조건식으로 검토해 주세요",
    ),
)
def test_the_automatic_strategy_path_is_reachable_through_the_preflight(query: str) -> None:
    """The scope guard and the automatic strategy mode have to agree on the same request.

    These two classifiers live in different modules and were written at different times,
    so nothing structural stops one from closing over what the other treats as its main
    entry point. That already happened once: every phrasing containing "추천해" is
    refused as an action imperative, which silently rejected the automatic path's own
    test prompt. Automatic mode is the default for free-form requests, so a request does
    not need that word - but something has to assert the two still meet.
    """

    from ai_graph.quant_strategy import classify_strategy_request

    assert classify_research_request(query).allowed is True
    assert classify_strategy_request(query) in {"automatic", "user_defined"}
