from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

_SHARPE_SOURCE = "https://web.stanford.edu/~wfsharpe/art/sr/SR.htm"
_QUANTSTATS_SOURCE = "https://github.com/ranaroussi/quantstats"
METRIC_REGISTRY_VERSION = "quant-metric-registry.v3"

# This is deliberately independent of the engine's much larger debug summary.  A new
# engine scalar must be registered here before it can become a public performance fact.
PUBLIC_METRIC_KEYS = (
    "total_return",
    "cagr",
    "annualized_volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "calmar_ratio",
    "win_rate",
    "profit_factor",
    "benchmark_return",
    "excess_return",
    "out_sample_excess_return",
    "benchmark_period_win_rate",
    "benchmark_period_loss_rate",
    "out_sample_benchmark_period_loss_rate",
    "in_sample_sharpe",
    "out_sample_sharpe",
    "degradation",
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_IMPLEMENTATION_SOURCES = {
    "engine": "backtest_module/backtest_module/performance.py",
    "trade": "backtest_module/backtest_module/backtest.py",
    "analysis": "ai/ai_graph/nodes/backtest.py",
    "projection": "ai/ai_graph/quant_performance.py",
}
_DEFAULT_AS_OF_POLICY = "입력 가격열의 마지막 거래일을 기준 시각으로 기록합니다."
_DEFAULT_NULL_POLICY = (
    "값이 없거나 비유한값이면 0으로 대체하지 않고 value=null, is_available=false로 "
    "표시합니다. 신뢰도 부족이면 공개 지표 전체를 숨깁니다."
)


_METRIC_EXPLANATIONS: dict[str, dict[str, Any]] = {
    "total_return": {
        "label": "누적수익률",
        "unit": "percent",
        "plain_explanation": "전 기간 기준 투자금 변화율입니다.",
        "why_used": "전략의 기본 성과 크기를 판단해 추천의 수익성 가능성을 보여줍니다.",
        "caution": "과거구간 특성에 따라 과대·과소 추정될 수 있으므로 향후 구간은 별도 확인해야 합니다.",
        "source_refs": [],
    },
    "cagr": {
        "label": "연환산수익률(CAGR)",
        "unit": "percent",
        "plain_explanation": "누적수익률을 연 단위로 환산한 값입니다.",
        "why_used": "분석 기간 길이가 다를 때 서로 다른 전략을 기간 기준으로 비교할 수 있습니다.",
        "caution": "거래일 수가 짧으면 연환산이 과대해질 수 있습니다.",
        "source_refs": [_QUANTSTATS_SOURCE],
    },
    "annualized_volatility": {
        "label": "연환산 변동성",
        "unit": "percent",
        "plain_explanation": "일별 수익률 표준편차를 연환산한 위험 지표입니다.",
        "why_used": "수익률 대비 리스크를 정량화해 전략 안정성을 보조적으로 평가합니다.",
        "caution": "극단치에 민감하고 표본 수가 적으면 불안정해질 수 있습니다.",
        "source_refs": [_QUANTSTATS_SOURCE],
    },
    "sharpe_ratio": {
        "label": "샤프비율",
        "unit": "ratio",
        "plain_explanation": "초과수익 대비 변동성 위험 비율입니다.",
        "why_used": "위험 대비 보상 효율을 측정해 전략 적합성을 비교합니다.",
        "caution": "참조 무위험 수익률 가정이 간단할수록 수치 해석이 제한됩니다.",
        "source_refs": [_SHARPE_SOURCE, _QUANTSTATS_SOURCE],
    },
    "sortino_ratio": {
        "label": "소르티노비율",
        "unit": "ratio",
        "plain_explanation": "음의 변동만을 위험으로 본 샤프 유사 지표입니다.",
        "why_used": "하방 위험을 중심으로 손실 구간의 전략 성격을 점검합니다.",
        "caution": "하방 표본이 적으면 해석이 제한됩니다.",
        "source_refs": [_QUANTSTATS_SOURCE],
    },
    "max_drawdown": {
        "label": "최대낙폭",
        "unit": "percent",
        "plain_explanation": "누적수익곡선 기준 누적 최고점 대비 최저점 하락 폭의 최대값입니다.",
        "why_used": "심각한 손실 구간을 빠르게 파악해 전략의 방어력을 판단합니다.",
        "caution": "짧은 구간에서는 실전 극단 구간을 충분히 반영하지 못할 수 있습니다.",
        "source_refs": [],
    },
    "calmar_ratio": {
        "label": "칼마비율",
        "unit": "ratio",
        "plain_explanation": "연환산수익률을 최대낙폭으로 나눈 값입니다.",
        "why_used": "수익과 하락 리스크를 하나의 지표로 비교하기 위해 사용합니다.",
        "caution": "낙폭이 매우 작으면 분모가 불안정해질 수 있습니다.",
        "source_refs": [_QUANTSTATS_SOURCE],
    },
    "win_rate": {
        "label": "승률",
        "unit": "percent",
        "plain_explanation": "매매에서 수익 거래 비중입니다. 백테스트 메트릭의 trade_win_rate를 사용합니다.",
        "why_used": "진입/청산 패턴의 일관성과 안정적 신호 빈도를 보조 점검합니다.",
        "caution": "수익률 크기 없이 단순 횟수 중심으로 계산되어 성능을 완전히 설명하지 못할 수 있습니다.",
        "source_refs": [],
    },
    "profit_factor": {
        "label": "수익팩터",
        "unit": "ratio",
        "plain_explanation": "청산된 거래의 총이익을 총손실로 나눈 값입니다. 실현손익 기반이며 승률과는 별개입니다.",
        "why_used": "이긴 거래가 진 거래를 얼마나 덮는지를 보여줍니다. 승률이 높아도 이 값이 1 미만이면 손실입니다.",
        "caution": (
            "거래 수가 적으면 과도하게 변동할 수 있습니다. 진 거래가 없으면 비율이 정의되지 "
            "않아 표시하지 않습니다."
        ),
        "source_refs": [],
    },
    "benchmark_return": {
        "label": "프록시 벤치마크 수익률",
        "unit": "percent",
        "plain_explanation": "가격열 상위집합의 고정 유니버스 동등가중 보유수익률입니다.",
        "why_used": "전략 성과를 동일 기간의 대체 기준과 비교해 초과 성과를 점검합니다.",
        "caution": "과거 살아남은 종목만으로 구성된 고정 유니버스여서 생존편향 경고가 포함됩니다.",
        "source_refs": [],
    },
    "excess_return": {
        "label": "초과수익률",
        "unit": "percent",
        "plain_explanation": "전략 누적수익률에서 벤치마크 누적수익률을 뺀 값입니다.",
        "why_used": "기준 대비 전략의 상대적 우위를 직관적으로 확인하기 위해 사용합니다.",
        "caution": "벤치마크가 계산되지 않으면 비교값이 없습니다.",
        "source_refs": [],
    },
    "out_sample_excess_return": {
        "label": "검증구간 초과수익률",
        "unit": "percent",
        "plain_explanation": "후보 선택에 쓰지 않은 마지막 30%에서 전략 수익률과 벤치마크 수익률의 차이입니다.",
        "why_used": "과거 학습구간에서만 지수를 이긴 과최적화 전략을 걸러내기 위해 사용합니다.",
        "caution": "한 번의 홀드아웃 결과만으로 미래의 모든 시장 국면을 대표할 수는 없습니다.",
        "source_refs": [],
    },
    "benchmark_period_win_rate": {
        "label": "벤치마크 승리 구간 비율",
        "unit": "percent",
        "plain_explanation": "고정된 63거래일 구간 중 전략 수익률이 벤치마크보다 높았던 구간의 비율입니다.",
        "why_used": "몇 번의 큰 성공뿐 아니라 서로 다른 시장 구간에서 초과성과가 반복되는지 확인합니다.",
        "caution": "구간 길이는 결과를 본 뒤 바꾸지 않으며, 126일 미만의 마지막 미완료 구간은 제외합니다.",
        "source_refs": [],
    },
    "benchmark_period_loss_rate": {
        "label": "벤치마크 패배 구간 비율",
        "unit": "percent",
        "plain_explanation": "고정된 63거래일 구간 중 전략 수익률이 벤치마크보다 낮았던 구간의 비율입니다.",
        "why_used": "사용자 기준에 따라 이 값이 50% 이상이면 자동 전략을 패배로 판정합니다.",
        "caution": "큰 초과수익 구간이 있어도 패배 구간이 절반 이상이면 검증을 통과하지 못합니다.",
        "source_refs": [],
    },
    "out_sample_benchmark_period_loss_rate": {
        "label": "검증구간 벤치마크 패배 비율",
        "unit": "percent",
        "plain_explanation": "마지막 30%를 다시 63거래일 단위로 나눴을 때 벤치마크에 진 구간의 비율입니다.",
        "why_used": "전략 선택 이후의 데이터에서도 패배 구간이 절반 미만인지 확인합니다.",
        "caution": "검증기간이 짧으면 비교 구간 수가 적어 비율 하나의 영향이 커집니다.",
        "source_refs": [],
    },
    "in_sample_sharpe": {
        "label": "학습구간 샤프비율",
        "unit": "ratio",
        "plain_explanation": "데이터 1차 분할 구간 샤프비율입니다.",
        "why_used": "개선·선택 단계의 내부 지표 추적에 활용합니다.",
        "caution": "교차검증 구간과 다를 수 있어 실제 운영 성과로 과잉해석하지 않습니다.",
        "source_refs": [_QUANTSTATS_SOURCE],
    },
    "out_sample_sharpe": {
        "label": "검증구간 샤프비율",
        "unit": "ratio",
        "plain_explanation": "홀드아웃 구간 샤프비율입니다.",
        "why_used": "선택 후 일반화 성능을 가늠해 객관적 문턱을 적용합니다.",
        "caution": "홀드아웃 기간 분산이 낮으면 오차가 커질 수 있습니다.",
        "source_refs": [_QUANTSTATS_SOURCE],
    },
    "degradation": {
        "label": "열화도",
        "unit": "percent",
        "plain_explanation": "학습구간 대비 홀드아웃 구간 성과 하락 정도입니다.",
        "why_used": "과적합 또는 구간 의존성을 점검하는 보조 지표로 사용합니다.",
        "caution": "매우 짧은 홀드아웃 구간에서는 불안정하게 나타날 수 있습니다.",
        "source_refs": [],
    },
}


def _contract(
    formula: str,
    *,
    inputs: list[str],
    input_window: str,
    implementation_source: str,
    implementation_ref: str,
    denominator: str = "해당 없음",
    clip_policy: str = "유한한 엔진 값을 임의로 상한/하한 처리하지 않습니다.",
    null_policy: str = _DEFAULT_NULL_POLICY,
    as_of_policy: str = _DEFAULT_AS_OF_POLICY,
) -> dict[str, Any]:
    return {
        "formula": formula,
        "inputs": inputs,
        "input_window": input_window,
        "denominator": denominator,
        "clip_policy": clip_policy,
        "null_policy": null_policy,
        "as_of_policy": as_of_policy,
        "implementation_source": implementation_source,
        "implementation_ref": implementation_ref,
    }


_METRIC_CONTRACTS: dict[str, dict[str, Any]] = {
    "total_return": _contract(
        "R_total = V_T / V_0 - 1",
        inputs=["초기 총자산 V_0", "최종 총자산 V_T"],
        input_window="전체 백테스트 기간",
        implementation_source="engine",
        implementation_ref="backtest_module.performance.calculate_quantstats_metrics → quantstats.stats.comp",
    ),
    "cagr": _contract(
        "CAGR = (V_T / V_0)^(1 / years) - 1",
        inputs=["초기·최종 총자산", "기간의 달력일/연수"],
        input_window="전체 백테스트 기간",
        implementation_source="engine",
        implementation_ref="backtest_module.performance.calculate_quantstats_metrics → quantstats.stats.cagr",
    ),
    "annualized_volatility": _contract(
        "σ_ann = std(R_t) × √252",
        inputs=["일별 기간수익률 R_t", "연환산 거래일 252"],
        input_window="전체 백테스트 기간의 일별 수익률",
        implementation_source="engine",
        implementation_ref="backtest_module.performance.calculate_quantstats_metrics → quantstats.stats.volatility",
    ),
    "sharpe_ratio": _contract(
        "Sharpe = mean(R_t - R_f) / std(R_t - R_f) × √252",
        inputs=["일별 기간수익률 R_t", "QuantStats 무위험수익률 R_f"],
        input_window="전체 백테스트 기간의 일별 수익률",
        implementation_source="engine",
        implementation_ref="backtest_module.performance.calculate_quantstats_metrics → quantstats.stats.sharpe",
    ),
    "sortino_ratio": _contract(
        "Sortino = mean(R_t - target) / downside_deviation(R_t) × √252",
        inputs=["일별 기간수익률 R_t", "목표수익률", "하방 수익률"],
        input_window="전체 백테스트 기간의 일별 수익률",
        implementation_source="engine",
        implementation_ref="backtest_module.performance.calculate_quantstats_metrics → quantstats.stats.sortino",
    ),
    "max_drawdown": _contract(
        "MDD = min_t(V_t / max_{u≤t}(V_u) - 1)",
        inputs=["일별 총자산 V_t"],
        input_window="전체 백테스트 기간의 자산곡선",
        implementation_source="engine",
        implementation_ref="backtest_module.performance.calculate_quantstats_metrics → quantstats.stats.max_drawdown",
    ),
    "calmar_ratio": _contract(
        "Calmar = CAGR / |MDD|",
        inputs=["연환산수익률 CAGR", "최대낙폭 MDD"],
        input_window="전체 백테스트 기간",
        implementation_source="engine",
        implementation_ref="backtest_module.performance.calculate_quantstats_metrics → quantstats.stats.calmar",
        denominator="|MDD|",
    ),
    "win_rate": _contract(
        "trade_win_rate = count(net_pnl > 0) / count(completed_trades)",
        inputs=["완결 거래별 순손익 net_pnl"],
        input_window="전체 백테스트 기간의 완료 거래",
        implementation_source="analysis",
        implementation_ref="ai_graph.nodes.backtest._metrics_from_engine_result ← engine trade_win_rate",
        denominator="완료 거래 수",
    ),
    "profit_factor": _contract(
        "PF = Σ max(net_pnl, 0) / |Σ min(net_pnl, 0)|",
        inputs=["청산 거래별 순손익 net_pnl"],
        input_window="전체 백테스트 기간의 청산 거래",
        implementation_source="trade",
        implementation_ref=(
            "backtest_module.backtest.BacktestEngine._summary → trade_profit_factor; "
            "ai_graph.nodes.backtest._profit_factor"
        ),
        denominator="|Σ min(net_pnl, 0)| (손실 청산 거래의 절대 손익 합)",
        clip_policy="상한/하한이나 승률 기반 프록시를 사용하지 않습니다.",
        null_policy=(
            "손실 청산 거래가 없어 분모가 0이거나 값이 없으면 value=null, "
            "is_available=false로 표시합니다."
        ),
    ),
    "benchmark_return": _contract(
        "R_benchmark = V_b,T / V_b,0 - 1",
        inputs=["고정 유니버스 종목별 종가"],
        input_window="전략과 동일한 전체 백테스트 기간",
        implementation_source="analysis",
        implementation_ref="ai_graph.nodes.backtest._equal_weight_benchmark_curve",
    ),
    "excess_return": _contract(
        "R_excess = R_strategy - R_benchmark",
        inputs=["전략 누적수익률", "동일 기간 벤치마크 수익률"],
        input_window="전략과 동일한 전체 백테스트 기간",
        implementation_source="projection",
        implementation_ref="ai_graph.quant_performance._build_public_metric_details",
    ),
    "out_sample_excess_return": _contract(
        "R_OOS,excess = Π(1 + R_strategy,t) - Π(1 + R_benchmark,t)",
        inputs=["홀드아웃 전략·벤치마크 일별 수익률"],
        input_window="후보 선택에 사용하지 않은 마지막 30% hold-out",
        implementation_source="analysis",
        implementation_ref="ai_graph.nodes.backtest._metrics_from_engine_result",
    ),
    "benchmark_period_win_rate": _contract(
        "win_rate = count(R_strategy,block > R_benchmark,block) / count(complete_blocks)",
        inputs=["전략·벤치마크 일별 수익률", "63거래일 고정 블록"],
        input_window="전체 기간의 완료된 63거래일 블록",
        implementation_source="analysis",
        implementation_ref="ai_graph.nodes.backtest._benchmark_period_stats",
        denominator="완료된 63거래일 블록 수",
    ),
    "benchmark_period_loss_rate": _contract(
        "loss_rate = count(R_strategy,block < R_benchmark,block) / count(complete_blocks)",
        inputs=["전략·벤치마크 일별 수익률", "63거래일 고정 블록"],
        input_window="전체 기간의 완료된 63거래일 블록",
        implementation_source="analysis",
        implementation_ref="ai_graph.nodes.backtest._benchmark_period_stats",
        denominator="완료된 63거래일 블록 수",
    ),
    "out_sample_benchmark_period_loss_rate": _contract(
        "OOS loss_rate = count(R_strategy,block < R_benchmark,block) / count(complete_blocks)",
        inputs=["홀드아웃 전략·벤치마크 일별 수익률", "63거래일 고정 블록"],
        input_window="마지막 30% hold-out의 완료된 63거래일 블록",
        implementation_source="analysis",
        implementation_ref="ai_graph.nodes.backtest._benchmark_period_stats",
        denominator="hold-out 완료 블록 수",
    ),
    "in_sample_sharpe": _contract(
        "Sharpe_train = mean(R_t - R_f) / std(R_t - R_f) × √252",
        inputs=["학습구간 일별 기간수익률", "무위험수익률"],
        input_window="후보 선택에 쓴 최초 70% 학습구간",
        implementation_source="analysis",
        implementation_ref="ai_graph.nodes.backtest._split_sharpes",
    ),
    "out_sample_sharpe": _contract(
        "Sharpe_holdout = mean(R_t - R_f) / std(R_t - R_f) × √252",
        inputs=["홀드아웃 일별 기간수익률", "무위험수익률"],
        input_window="후보 선택에 쓰지 않은 마지막 30% hold-out",
        implementation_source="analysis",
        implementation_ref="ai_graph.nodes.backtest._split_sharpes",
    ),
    "degradation": _contract(
        "degradation = max(0, (Sharpe_train - Sharpe_holdout) / |Sharpe_train|)",
        inputs=["학습구간 샤프비율", "홀드아웃 샤프비율"],
        input_window="70% 학습구간과 30% hold-out",
        implementation_source="analysis",
        implementation_ref="ai_graph.nodes.backtest._degradation",
        denominator="|Sharpe_train|; Sharpe_train=0이면 구현 정책값 0",
    ),
}


def _implementation_hash(source_key: str) -> str:
    relative_path = _IMPLEMENTATION_SOURCES[source_key]
    try:
        source = (_REPOSITORY_ROOT / relative_path).read_bytes()
    except OSError as error:
        raise RuntimeError(
            f"metric implementation source is unavailable: {relative_path}"
        ) from error
    return sha256(source).hexdigest()


def metric_registry_entry(key: str) -> dict[str, Any]:
    """Return the canonical contract for a public quantitative metric."""

    explanation = _METRIC_EXPLANATIONS.get(key)
    contract = _METRIC_CONTRACTS.get(key)
    if explanation is None or contract is None:
        raise KeyError(f"metric is not registered for public output: {key}")
    source_key = contract["implementation_source"]
    return {
        "key": key,
        **explanation,
        **contract,
        "formula_version": METRIC_REGISTRY_VERSION,
        "implementation_path": _IMPLEMENTATION_SOURCES[source_key],
        "implementation_hash": _implementation_hash(source_key),
    }


def public_metric_registry() -> list[dict[str, Any]]:
    """Ordered whitelist and semantic registry for all public metric cards."""

    return [metric_registry_entry(key) for key in PUBLIC_METRIC_KEYS]


def metric_explanation(key: str) -> dict[str, Any]:
    if key in _METRIC_EXPLANATIONS:
        return metric_registry_entry(key)
    return {
        "label": key,
        "unit": "ratio",
        "plain_explanation": f"{key}는 백테스트 성능 지표입니다.",
        "why_used": "성능의 보조 판별값으로 사용됩니다.",
        "caution": "지표 정의가 제한되어 있어 보조적으로 해석합니다.",
        "source_refs": [],
    }
