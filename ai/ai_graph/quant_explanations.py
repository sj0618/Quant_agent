from __future__ import annotations

from typing import Any


_METRIC_EXPLANATIONS: dict[str, dict[str, str]] = {
    "total_return": {
        "label": "누적수익률",
        "unit": "ratio",
        "plain_explanation": "전 기간 기준 투자금 변화율입니다.",
        "why_used": "전략의 기본 성과 크기를 판단해 추천의 수익성 가능성을 보여줍니다.",
        "caution": "과거구간 특성에 따라 과대·과소 추정될 수 있으므로 향후 구간은 별도 확인해야 합니다.",
    },
    "cagr": {
        "label": "연환산수익률(CAGR)",
        "unit": "ratio",
        "plain_explanation": "누적수익률을 연 단위로 환산한 값입니다.",
        "why_used": "분석 기간 길이가 다를 때 서로 다른 전략을 기간 기준으로 비교할 수 있습니다.",
        "caution": "거래일 수가 짧으면 연환산이 과대해질 수 있습니다.",
    },
    "annualized_volatility": {
        "label": "연환산 변동성",
        "unit": "ratio",
        "plain_explanation": "일별 수익률 표준편차를 연환산한 위험 지표입니다.",
        "why_used": "수익률 대비 리스크를 정량화해 전략 안정성을 보조적으로 평가합니다.",
        "caution": "극단치에 민감하고 표본 수가 적으면 불안정할 수 있습니다.",
    },
    "sharpe_ratio": {
        "label": "샤프비율",
        "unit": "ratio",
        "plain_explanation": "초과수익 대비 변동성 위험 비율입니다.",
        "why_used": "위험 대비 보상 효율을 측정해 전략 적합성을 비교합니다.",
        "caution": "참조 무위험 수익률 가정이 간단할수록 수치 해석이 제한됩니다.",
    },
    "sortino_ratio": {
        "label": "소르티노비율",
        "unit": "ratio",
        "plain_explanation": "음의 변동만을 위험으로 본 샤프 유사 지표입니다.",
        "why_used": "하방 위험을 중심으로 손실 구간의 전략 성격을 점검합니다.",
        "caution": "하방 표본이 적으면 해석이 제한됩니다.",
    },
    "max_drawdown": {
        "label": "최대낙폭",
        "unit": "ratio",
        "plain_explanation": "누적수익곡선 기준 누적 최고점 대비 최저점 하락 폭의 최대값입니다.",
        "why_used": "심각한 손실 구간을 빠르게 파악해 전략의 방어력을 판단합니다.",
        "caution": "짧은 구간에서는 실전 극단 구간을 충분히 반영하지 못할 수 있습니다.",
    },
    "calmar_ratio": {
        "label": "칼마비율",
        "unit": "ratio",
        "plain_explanation": "연환산수익률을 최대낙폭으로 나눈 값입니다.",
        "why_used": "수익과 하락 리스크를 하나의 지표로 비교하기 위해 사용합니다.",
        "caution": "낙폭이 매우 작으면 분모가 불안정해질 수 있습니다.",
    },
    "win_rate": {
        "label": "승률",
        "unit": "ratio",
        "plain_explanation": "매매에서 수익 거래 비중입니다.",
        "why_used": "진입/청산 패턴의 일관성과 안정적 신호 빈도를 보조 점검합니다.",
        "caution": "수익률 크기 없이 단순 횟수 중심으로 계산되어 성능을 완전히 설명하지 못할 수 있습니다.",
    },
    "profit_factor": {
        "label": "수익팩터",
        "unit": "ratio",
        "plain_explanation": "총이익을 총손실로 나눈 값입니다.",
        "why_used": "이익 기여 구간과 손실 구간의 상대 비율을 보조적으로 보여줍니다.",
        "caution": "거래 수가 적으면 과도하게 변동할 수 있습니다.",
    },
    "benchmark_return": {
        "label": "프록시 벤치마크 수익률",
        "unit": "ratio",
        "plain_explanation": "가격열 상위집합의 고정 유니버스 동등가중 보유수익률입니다.",
        "why_used": "전략 성과를 동일 기간의 대체 기준과 비교해 초과 성과를 점검합니다.",
        "caution": "과거 살아남은 종목만으로 구성된 고정 유니버스여서 생존편향 경고가 포함됩니다.",
    },
    "excess_return": {
        "label": "초과수익률",
        "unit": "ratio",
        "plain_explanation": "전략 누적수익률에서 벤치마크 누적수익률을 뺀 값입니다.",
        "why_used": "기준 대비 전략의 상대적 우위를 직관적으로 확인하기 위해 사용합니다.",
        "caution": "벤치마크가 계산되지 않으면 비교값이 없습니다.",
    },
    "in_sample_sharpe": {
        "label": "학습구간 샤프비율",
        "unit": "ratio",
        "plain_explanation": "데이터 1차 분할 구간 샤프비율입니다.",
        "why_used": "개선·선택 단계의 내부 지표 추적에 활용합니다.",
        "caution": "교차검증 구간과 다를 수 있어 실제 운영 성과로 과잉해석하지 않습니다.",
    },
    "out_sample_sharpe": {
        "label": "검증구간 샤프비율",
        "unit": "ratio",
        "plain_explanation": "홀드아웃 구간 샤프비율입니다.",
        "why_used": "선택 후 일반화 성능을 가늠해 객관적 문턱을 적용합니다.",
        "caution": "홀드아웃 기간 분산이 낮으면 오차가 커질 수 있습니다.",
    },
    "degradation": {
        "label": "열화도",
        "unit": "ratio",
        "plain_explanation": "학습구간 대비 홀드아웃 구간 성과 하락 정도입니다.",
        "why_used": "과적합 또는 구간 의존성을 점검하는 보조 지표로 사용합니다.",
        "caution": "매우 짧은 홀드아웃 구간에서는 불안정하게 나타날 수 있습니다.",
    },
}



def metric_explanation(key: str) -> dict[str, str]:
    return _METRIC_EXPLANATIONS.get(
        key,
        {
            "label": key,
            "unit": "ratio",
            "plain_explanation": f"{key}는 백테스트 성능 지표입니다.",
            "why_used": "성능의 보조 판별값으로 사용됩니다.",
            "caution": "지표 정의가 제한되어 있어 보조적으로 해석합니다.",
        },
    )
