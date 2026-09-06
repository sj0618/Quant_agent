"""An over-long prose field must not discard a researched strategy.

Observed on the deployed release (job_d4267b1043a5): the researcher answered
"RSI(14)가 30 이하로 떨어진 코스피 종목을 사고, 70 이상이면 파는 전략" with a candidate whose
rule compiled cleanly (rsi lte 30 / rsi gte 70) and was refused with
research_response_schema_invalid solely because ``expected_turnover`` exceeded 400
characters.  The repair turn then rewrote the rule with ``window=14, aggregate="last"``,
which the compiler cannot execute, so a basic request ended in need_clarification.
"""

from ai_graph.nodes import strategy_research as sr

QUERY = "RSI(14)가 30 이하로 떨어진 코스피 종목을 사고, 70 이상이면 파는 전략"


def _payload(*, expected_turnover: str) -> dict:
    return {
        "resolution_summary": "요청한 RSI(14) 규칙은 지원 metric인 rsi로 직접 표현 가능하다.",
        "sources": [
            {
                "source_id": "source-1",
                "title": "KRX market overview",
                "url": "https://global.krx.co.kr/",
                "claim": "KOSPI is a separate KRX market.",
                "limitation": "No point-in-time constituent list. " * 20,
            }
        ],
        "candidates": [
            {
                "candidate_id": "research-candidate-1",
                "title": "RSI(14) 과매도 평균회귀",
                "hypothesis": "과매도 후 평균회귀",
                "counter_hypothesis": "추세장에서는 과매도가 지속된다",
                "entry_conditions": [
                    {"left": "rsi", "operator": "lte", "right": 30, "description": "RSI(14)가 30 이하"}
                ],
                "exit_conditions": [
                    {"left": "rsi", "operator": "gte", "right": 70, "description": "RSI(14)가 70 이상"}
                ],
                "required_metrics": ["rsi", "close", "volume"],
                "assumptions": ["universe는 point-in-time KOSPI 보통주"],
                "ai_assumptions": ["이벤트 기반 청산"],
                "economic_rationale": "단기 과잉반응 후 평균회귀",
                "falsification_conditions": [
                    {"condition": "비용 차감 후 초과성과 0 이하. " * 30, "interpretation": "가설 기각"}
                ],
                "expected_turnover": expected_turnover,
                "regime_risks": ["강한 하락 추세"],
                "backtest_years": 5,
                "backtest_period_basis": "최근 5개년 KOSPI 거래일",
                "source_ids": ["source-1"],
            }
        ],
    }


def test_an_over_long_prose_field_is_trimmed_instead_of_rejecting_the_rule() -> None:
    long_turnover = "중간~높음. RSI 임계값 도달이 국면에 따라 반복된다. " * 20
    assert len(long_turnover) > 400

    normalized = sr._normalize_research_response_aliases(
        _payload(expected_turnover=long_turnover), query=QUERY
    )
    response = sr._ResearchResponse.model_validate(normalized)

    candidate = response.candidates[0]
    assert len(candidate.expected_turnover) <= 400
    assert candidate.expected_turnover.endswith("…")
    assert len(candidate.falsification_conditions[0].condition) <= 400
    assert len(response.sources[0].limitation) <= 400
    # Strategy-bearing fields are exactly what the researcher returned.
    assert [(c.left, c.operator.value, c.right) for c in candidate.entry_conditions] == [("rsi", "lte", 30)]
    assert [(c.left, c.operator.value, c.right) for c in candidate.exit_conditions] == [("rsi", "gte", 70)]
    assert candidate.required_metrics == ["rsi", "close", "volume"]
    assert candidate.backtest_years == 5


def test_prose_within_limits_is_left_untouched() -> None:
    normalized = sr._normalize_research_response_aliases(
        _payload(expected_turnover="중간 수준의 회전율"), query=QUERY
    )
    response = sr._ResearchResponse.model_validate(normalized)

    assert response.candidates[0].expected_turnover == "중간 수준의 회전율"
