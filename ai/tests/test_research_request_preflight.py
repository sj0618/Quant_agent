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
