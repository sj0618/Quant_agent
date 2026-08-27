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
        "내 주식 100주를 자동 주문으로 팔아줘",
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
        "KRX 일봉에서 RSI가 30 이하일 때 진입하고 70 이상일 때 청산하는 전략을 최근 1년 구간으로 백테스트 실행해줘.",
        "배당수익률 4% 이상, 부채비율 100% 이하 조건을 비교해 주세요.",
        "국내 보유 비중과 무관하게 KRX 일봉에서 RSI 30 이하 진입, 70 이상 청산 규칙을 검토해 주세요.",
        "보유 종목이 아닌 KRX 전체를 대상으로 RSI 30 이하 진입 규칙을 검토해줘.",
    ),
)
def test_preflight_allows_general_research_rules(query: str) -> None:
    decision = classify_research_request(query)

    assert decision.allowed is True
    assert decision.reason_code is None


@pytest.mark.parametrize(
    "query",
    (
        "이 규칙으로 자동 주문을 실행해 줘.",
        "RSI 30 이하일 때 매수하고 자동매매해 줘.",
        "내 계좌에서 주문 넣어 줘.",
    ),
)
def test_preflight_refuses_automatic_or_direct_order_requests(query: str) -> None:
    decision = classify_research_request(query)

    assert decision.allowed is False
    assert decision.reason_code == SCOPE_REFUSAL_REASON


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


def test_analysis_job_openapi_example_declares_neutral_entry_and_exit_conditions() -> None:
    example = CreateAnalysisJobRequest.model_config["json_schema_extra"]["examples"][0]
    strategy_execution_spec = example["strategy_execution_spec"]

    assert strategy_execution_spec["market"] == "KRX"
    assert strategy_execution_spec["entry_conditions"][0]["role"] == "entry"
    assert strategy_execution_spec["exit_conditions"][0]["role"] == "exit"
