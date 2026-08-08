from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any, Literal

import numpy as np


StrategyRequestMode = Literal["standard", "automatic", "user_defined"]

MOMENTUM_LONG_LOOKBACK = 252
MOMENTUM_SKIP_LOOKBACK = 21
REALIZED_VOLATILITY_LOOKBACK = 21
REBALANCE_INTERVAL_DAYS = 21

AQR_TREND_SOURCE = (
    "https://www.aqr.com/Insights/Research/Journal-Article/"
    "A-Century-of-Evidence-on-Trend-Following-Investing"
)
FABER_TACTICAL_SOURCE = "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461"
JEGADEESH_TITMAN_SOURCE = "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=299107"
KEN_FRENCH_MOMENTUM_SOURCE = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html"
)
NBER_VOLATILITY_SOURCE = "https://www.nber.org/papers/w22208"
BACKTEST_OVERFITTING_SOURCE = "https://academic.oup.com/jrssig/article/18/6/22/7038278"

# These are deliberately three different ideas, not three nearby thresholds of one
# idea.  Keeping the menu small and fixed before a backtest limits the chance that the
# apparent winner is merely the luckiest of many data-mined variants.
AUTOMATIC_TOURNAMENT_PROFILES = (
    "academic_momentum_trend",
    "dual_sma_trend",
    "low_vol_momentum",
)

_AUTOMATIC_TERMS = (
    "auto",
    "automatic",
    "recommend",
    "popular",
    "evidence-based",
    "validated",
    "자동",
    "추천",
    "권장",
    "인기",
    "많이 쓰는",
    "사람들이 쓰는",
    "사람들이 사용하는",
    "대중적인",
    "검증된",
    "검증된 퀀트",
    "알아서",
)
_INFORMATIONAL_TERMS = (
    "설명",
    "뜻",
    "뭐야",
    "무엇",
    "뉴스",
    "시황",
    "시장 상황",
    "전망",
    "explain",
    "what is",
    "news",
    "outlook",
)
_STRATEGY_CREATION_TERMS = (
    "전략",
    "퀀트",
    "투자",
    "수익",
    "벌",
    "매수",
    "매도",
    "종목",
    "포트폴리오",
    "백테스트",
    "만들",
    "짜",
    "골라",
    "찾아",
    "추천",
    "strategy",
    "quant",
    "invest",
    "return",
    "portfolio",
    "backtest",
)
# A named preference is useful even without a numerical threshold.  Preserve it and
# let the normal strategy builder fill in a reproducible default instead of silently
# replacing it with the automatic tournament.
_NAMED_STRATEGY_TERMS = (
    "rsi",
    "sma",
    "이동평균",
    "모멘텀",
    "momentum",
    "macd",
    "볼린저",
    "bollinger",
    "변동성",
    "volatility",
    "거래량",
    "volume",
    "눌림목",
    "pullback",
    "돌파",
    "breakout",
    "배당",
    "dividend",
    "가치",
    "저평가",
    "value",
    "성장",
    "growth",
    "실적",
    "earnings",
    "상대강도",
    "relative strength",
    "주도주",
    "저변동",
    "low vol",
    "퀄리티",
    "quality",
    "per",
    "pbr",
    "roe",
    "fcf",
    "현금흐름",
    "부채",
    "순현금",
    "자사주",
    "재고",
    "영업이익",
    "가이던스",
    "컨센서스",
    "기관",
    "외국인",
    "공매도",
    "숏커버링",
    "환율",
    "금리",
    "원자재",
)
_ENTRY_EXIT_TERMS = (
    "entry",
    "exit",
    "buy when",
    "sell when",
    "진입",
    "청산",
    "매수 조건",
    "매도 조건",
)
_ACTION_TERMS = ("buy", "sell", "매수", "매도", "사라", "팔아")
_PRICE_TERMS = ("price", "close", "가격", "주가", "종가")
_INDICATOR_TERMS = (
    "rsi",
    "sma",
    "이동평균",
    "모멘텀",
    "momentum",
    "macd",
    "볼린저",
    "bollinger",
    "변동성",
    "volatility",
    "거래량",
    "volume",
)
_OPERATOR_TERMS = (
    "<=",
    ">=",
    "<",
    ">",
    "이하",
    "이상",
    "초과",
    "미만",
    "상회",
    "하회",
    "교차",
    "아래",
    "위로",
    "넘으면",
    "떨어지면",
    "오르면",
    "above",
    "below",
    "cross",
)
_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?\s*%?")


@dataclass(frozen=True)
class AcademicFactorArrays:
    momentum_12_1: np.ndarray
    sma_50: np.ndarray
    sma_200: np.ndarray
    realized_volatility_21d: np.ndarray
    rebalance_eligible: np.ndarray


def classify_strategy_request(query: str) -> StrategyRequestMode:
    """Preserve explicit intent and make every other strategy request autonomous.

    Users should not need to know the phrase "automatic recommendation".  A non-empty
    request that is neither informational nor a named/concrete rule is treated as an
    automatic strategy-generation request.
    """

    lowered = (query or "").casefold()
    if not lowered.strip():
        return "standard"
    has_entry_or_exit_clause = any(term in lowered for term in _ENTRY_EXIT_TERMS)
    has_action = any(term in lowered for term in _ACTION_TERMS)
    has_indicator = any(term in lowered for term in _INDICATOR_TERMS)
    has_price = any(term in lowered for term in _PRICE_TERMS)
    has_operator = any(term in lowered for term in _OPERATOR_TERMS)
    has_number = bool(_NUMBER_RE.search(lowered))
    has_concrete_rule = has_entry_or_exit_clause or (
        has_number and has_operator and (has_indicator or has_action or has_price)
    )
    if has_concrete_rule:
        return "user_defined"
    is_information_only = any(term in lowered for term in _INFORMATIONAL_TERMS) and not any(
        term in lowered for term in _STRATEGY_CREATION_TERMS
    )
    if is_information_only:
        return "standard"
    if any(term in lowered for term in _AUTOMATIC_TERMS):
        return "automatic"
    if any(term in lowered for term in _NAMED_STRATEGY_TERMS):
        return "standard"
    return "automatic"


def compute_academic_factor_arrays(
    closes: Sequence[float],
) -> AcademicFactorArrays:
    """Compute past-only 12-1 momentum, trend and risk arrays.

    At row ``t`` momentum is ``close[t-21] / close[t-252] - 1``.  The
    most recent month is intentionally skipped.  Moving averages and volatility
    only use observations available at ``t``; future rows cannot affect an earlier
    result.
    """

    values = np.asarray(closes, dtype=np.float64)
    size = len(values)
    valid = np.isfinite(values) & (values > 0.0)
    momentum = np.full(size, np.nan, dtype=np.float64)
    sma_50 = _rolling_mean(values, valid, 50)
    sma_200 = _rolling_mean(values, valid, 200)
    realized_volatility = np.full(size, np.nan, dtype=np.float64)
    rebalance = np.zeros(size, dtype=np.bool_)

    if size > MOMENTUM_LONG_LOOKBACK:
        indices = np.arange(MOMENTUM_LONG_LOOKBACK, size)
        numerator_indices = indices - MOMENTUM_SKIP_LOOKBACK
        denominator_indices = indices - MOMENTUM_LONG_LOOKBACK
        usable = valid[numerator_indices] & valid[denominator_indices]
        selected = indices[usable]
        momentum[selected] = (
            values[numerator_indices[usable]] / values[denominator_indices[usable]] - 1.0
        )
        rebalance[MOMENTUM_LONG_LOOKBACK::REBALANCE_INTERVAL_DAYS] = True

    if size > REALIZED_VOLATILITY_LOOKBACK:
        daily_returns = np.full(size, np.nan, dtype=np.float64)
        valid_pairs = valid[1:] & valid[:-1]
        daily_returns[1:][valid_pairs] = values[1:][valid_pairs] / values[:-1][valid_pairs] - 1.0
        finite_returns = np.isfinite(daily_returns)
        safe_returns = np.where(finite_returns, daily_returns, 0.0)
        return_prefix = np.concatenate(([0.0], np.cumsum(safe_returns)))
        square_prefix = np.concatenate(([0.0], np.cumsum(safe_returns * safe_returns)))
        count_prefix = np.concatenate(([0], np.cumsum(finite_returns.astype(np.int64))))
        indices = np.arange(REALIZED_VOLATILITY_LOOKBACK, size)
        starts = indices - REALIZED_VOLATILITY_LOOKBACK + 1
        counts = count_prefix[indices + 1] - count_prefix[starts]
        complete = counts == REALIZED_VOLATILITY_LOOKBACK
        selected = indices[complete]
        if len(selected):
            selected_starts = starts[complete]
            totals = return_prefix[selected + 1] - return_prefix[selected_starts]
            square_totals = square_prefix[selected + 1] - square_prefix[selected_starts]
            means = totals / REALIZED_VOLATILITY_LOOKBACK
            variances = np.maximum(
                0.0,
                square_totals / REALIZED_VOLATILITY_LOOKBACK - means * means,
            )
            realized_volatility[selected] = np.sqrt(variances) * np.sqrt(252.0)

    for output in (momentum, sma_50, sma_200, realized_volatility, rebalance):
        output.setflags(write=False)
    return AcademicFactorArrays(
        momentum_12_1=momentum,
        sma_50=sma_50,
        sma_200=sma_200,
        realized_volatility_21d=realized_volatility,
        rebalance_eligible=rebalance,
    )


def build_strategy_explanation(
    strategy: Any,
    *,
    selected_profile: str | None = None,
    selected_parameters: Mapping[str, Any] | Any | None = None,
) -> dict[str, Any]:
    mode: StrategyRequestMode = getattr(strategy, "selection_mode", "standard")
    indicators = [str(item) for item in getattr(strategy, "indicators", [])]
    if mode == "automatic":
        automatic = _automatic_profile_explanation(
            selected_profile,
            selected_parameters=selected_parameters,
        )
        indicator_keys = automatic["indicator_keys"]
        title = automatic["title"]
        summary = automatic["summary"]
        why_selected = automatic["why_selected"]
        rebalance = automatic["rebalance"]
    else:
        indicator_keys = tuple(_indicator_key(item) for item in indicators)
        title = str(getattr(strategy, "name", "사용자 전략"))
        summary = "입력한 진입·청산 조건을 그대로 백테스트하는 전략입니다."
        why_selected = (
            "구체적인 매매 조건은 일반 추천 템플릿보다 사용자의 의도가 우선이므로 "
            "자동 전략으로 바꾸지 않았습니다."
            if mode == "user_defined"
            else "입력 문장에서 확인된 지표와 조건을 기준으로 구성했습니다."
        )
        rebalance = None

    explanations = [_indicator_explanation(key) for key in dict.fromkeys(indicator_keys)]
    source_refs = list(
        dict.fromkeys(
            str(source) for item in explanations for source in item.get("source_refs", [])
        )
    )
    if mode == "automatic":
        source_refs = list(dict.fromkeys([*source_refs, BACKTEST_OVERFITTING_SOURCE]))
    return {
        "selection_mode": mode,
        "title": title,
        "summary": summary,
        "why_selected": why_selected,
        "rebalance_explanation": rebalance,
        "caution": (
            "연구 결과와 과거 백테스트는 미래 수익을 보장하지 않습니다. "
            "거래비용, 세금, 유동성, 시장 국면 변화에 따라 실제 결과가 달라질 수 있습니다."
        ),
        "indicators": explanations,
        "source_refs": source_refs,
    }


def academic_strategy_source_refs() -> list[str]:
    return [
        AQR_TREND_SOURCE,
        FABER_TACTICAL_SOURCE,
        JEGADEESH_TITMAN_SOURCE,
        KEN_FRENCH_MOMENTUM_SOURCE,
        NBER_VOLATILITY_SOURCE,
    ]


def robust_strategy_source_refs() -> list[str]:
    return [*academic_strategy_source_refs(), BACKTEST_OVERFITTING_SOURCE]


def _automatic_profile_explanation(
    selected_profile: str | None,
    *,
    selected_parameters: Mapping[str, Any] | Any | None,
) -> dict[str, Any]:
    lookback = _parameter_value(selected_parameters, "lookback")
    threshold = _parameter_value(selected_parameters, "threshold")
    selection_reason = (
        "서로 원리가 다른 고정 후보 3개를 같은 비용 가정으로 비교했습니다. "
        "앞 70% 구간의 샤프지수·손실폭·거래회전율·거래 수를 함께 본 점수로 "
        "이 후보를 골랐고, 마지막 30% 구간은 선택에 쓰지 않고 별도로 표시합니다."
    )
    if selected_profile == "academic_momentum_trend":
        return {
            "indicator_keys": (
                "momentum_12_1",
                "sma_50_200",
                "realized_volatility_21d",
                "rebalance_21d",
            ),
            "title": "12-1 모멘텀·장기 추세 전략",
            "summary": (
                "최근 한 달을 뺀 약 1년 상승력이 양수이고 50일선이 200일선보다 "
                "강한 종목 중, 최근 변동성이 지나치게 높지 않은 종목을 고릅니다."
            ),
            "why_selected": selection_reason,
            "rebalance": (
                "21거래일마다 후보를 다시 골라 단기 잡음과 불필요한 매매비용을 줄입니다."
            ),
        }
    if selected_profile == "dual_sma_trend":
        return {
            "indicator_keys": ("dual_sma_trend", "trend_risk_exit"),
            "title": "다중 이동평균 추세 전략",
            "summary": (
                f"약 {int(lookback or 200)}거래일 범위에서 단기·중기·장기 평균이 "
                "차례로 상승 정렬된 종목을 사고, 정렬이나 장기 추세가 깨지면 나옵니다."
            ),
            "why_selected": selection_reason,
            "rebalance": "매일 신호를 확인하되 추세 정렬이 바뀔 때만 매매합니다.",
        }
    if selected_profile == "low_vol_momentum":
        threshold_pct = float(threshold if threshold is not None else 0.03) * 100.0
        return {
            "indicator_keys": (
                "medium_momentum_126d",
                "price_range_volatility",
                "trend_risk_exit",
            ),
            "title": "저변동 모멘텀 전략",
            "summary": (
                f"약 {int(lookback or 126)}거래일 수익 추세가 {threshold_pct:g}% 이상이고 "
                "중기 수익도 양수인 종목을 고르되, 가격 범위가 과도하게 흔들리는 "
                "종목은 제외합니다."
            ),
            "why_selected": selection_reason,
            "rebalance": "매일 위험 조건을 점검하고 중기 추세가 훼손되면 보유를 끝냅니다.",
        }
    return {
        "indicator_keys": (
            "strategy_tournament",
            "momentum_12_1",
            "dual_sma_trend",
            "price_range_volatility",
        ),
        "title": "연구 기반 3계열 퀀트 전략 자동선택",
        "summary": (
            "12-1 모멘텀·장기 추세, 다중 이동평균 추세, 저변동 모멘텀을 "
            "고정 후보로 만들고 동일한 과거 데이터와 비용 가정으로 비교합니다."
        ),
        "why_selected": (
            "요청이 짧거나 조건이 없어서 임의의 RSI 하나를 가정하지 않고, 서로 다른 "
            "시장 원리를 쓰는 세 전략 중 위험조정 결과가 나은 전략을 자동 선택합니다."
        ),
        "rebalance": "선택된 후보 자체의 정기 점검 또는 추세 훼손 규칙을 적용합니다.",
    }


def _parameter_value(parameters: Mapping[str, Any] | Any | None, key: str) -> Any:
    if parameters is None:
        return None
    if isinstance(parameters, Mapping):
        return parameters.get(key)
    return getattr(parameters, key, None)


def _rolling_mean(
    values: np.ndarray,
    valid: np.ndarray,
    window: int,
) -> np.ndarray:
    output = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) < window:
        return output
    safe_values = np.where(valid, values, 0.0)
    value_prefix = np.concatenate(([0.0], np.cumsum(safe_values)))
    count_prefix = np.concatenate(([0], np.cumsum(valid.astype(np.int64))))
    indices = np.arange(window - 1, len(values))
    starts = indices - window + 1
    counts = count_prefix[indices + 1] - count_prefix[starts]
    complete = counts == window
    selected = indices[complete]
    output[selected] = (value_prefix[selected + 1] - value_prefix[starts[complete]]) / window
    return output


def _indicator_key(indicator: str) -> str:
    lowered = indicator.casefold().replace(" ", "_")
    if "rsi" in lowered:
        return "rsi"
    if "sma" in lowered or "이동평균" in lowered:
        return "sma_50_200"
    if "vol" in lowered or "변동성" in lowered:
        return "realized_volatility_21d"
    if "momentum" in lowered or "모멘텀" in lowered:
        return "momentum_12_1"
    if "volume" in lowered or "거래량" in lowered:
        return "volume"
    return lowered or "custom_indicator"


def _indicator_explanation(key: str) -> dict[str, Any]:
    catalog: Mapping[str, dict[str, Any]] = {
        "momentum_12_1": {
            "label": "12-1 모멘텀",
            "plain_explanation": (
                "252거래일 전 가격과 21거래일 전 가격을 비교합니다. "
                "최근 한 달은 단기 반전 영향을 줄이기 위해 제외합니다."
            ),
            "why_used": "중기 추세가 이어지는 종목을 같은 시점의 다른 종목과 비교하기 위해 사용합니다.",
            "caution": "추세가 갑자기 뒤집히면 신호가 늦을 수 있습니다.",
            "source_refs": [JEGADEESH_TITMAN_SOURCE, KEN_FRENCH_MOMENTUM_SOURCE],
        },
        "sma_50_200": {
            "label": "50일·200일 이동평균",
            "plain_explanation": "최근 50일 평균 가격과 200일 평균 가격으로 단기·장기 추세 방향을 봅니다.",
            "why_used": "약한 하락 추세의 종목을 모멘텀 순위만으로 사는 일을 줄이기 위해 사용합니다.",
            "caution": "횡보장에서는 신호가 자주 엇갈리고 진입이 늦을 수 있습니다.",
            "source_refs": [AQR_TREND_SOURCE, FABER_TACTICAL_SOURCE],
        },
        "realized_volatility_21d": {
            "label": "21일 실현변동성",
            "plain_explanation": "최근 21개 일간 수익률이 얼마나 크게 흔들렸는지를 연 단위로 환산한 값입니다.",
            "why_used": "같은 모멘텀이라도 급격히 흔들리는 종목의 위험을 낮게 평가하기 위해 사용합니다.",
            "caution": "과거 21일의 안정성이 다음 달에도 이어진다는 보장은 없습니다.",
            "source_refs": [NBER_VOLATILITY_SOURCE],
        },
        "rebalance_21d": {
            "label": "21거래일 리밸런싱",
            "plain_explanation": "약 한 달에 한 번만 새 종목을 고르고 비중을 점검합니다.",
            "why_used": "매일 순위가 조금 바뀔 때마다 매매하는 비용과 잡음을 줄이기 위해 사용합니다.",
            "caution": "월중 급변은 다음 정기 점검 전에 반영되지 않을 수 있어 손절 규칙을 함께 사용합니다.",
            "source_refs": [FABER_TACTICAL_SOURCE],
        },
        "strategy_tournament": {
            "label": "고정 3계열 전략 비교",
            "plain_explanation": (
                "한 가지 공식의 숫자만 계속 바꾸지 않고, 원리가 다른 세 전략을 "
                "미리 정한 뒤 같은 조건에서 비교합니다."
            ),
            "why_used": (
                "많은 조합을 시험한 뒤 가장 좋아 보이는 것만 고르는 과최적화를 줄이고, "
                "애매한 요청에도 한 전략을 임의로 단정하지 않기 위해 사용합니다."
            ),
            "caution": "후보를 세 개로 제한해도 과거의 승자가 미래에도 이긴다는 보장은 없습니다.",
            "source_refs": [BACKTEST_OVERFITTING_SOURCE],
        },
        "dual_sma_trend": {
            "label": "단기·중기·장기 이동평균 정렬",
            "plain_explanation": (
                "최근 가격 평균을 짧은 구간, 중간 구간, 긴 구간으로 나눠 계산하고 "
                "짧은 평균이 더 위에 있는 상승 정렬인지 확인합니다."
            ),
            "why_used": "일시적인 하루 급등보다 여러 시간대에서 이어지는 추세를 확인하기 위해 사용합니다.",
            "caution": "방향 없이 오르내리는 장에서는 매수와 매도가 자주 엇갈릴 수 있습니다.",
            "source_refs": [AQR_TREND_SOURCE, FABER_TACTICAL_SOURCE],
        },
        "medium_momentum_126d": {
            "label": "약 6개월 모멘텀",
            "plain_explanation": "현재 가격을 약 126거래일 전 가격과 비교해 중기 상승 힘을 봅니다.",
            "why_used": "너무 짧은 뉴스성 급등보다 몇 달간 이어진 가격 방향을 포착하기 위해 사용합니다.",
            "caution": "시장이 급반전하면 과거 상승세를 뒤늦게 따라갈 수 있습니다.",
            "source_refs": [JEGADEESH_TITMAN_SOURCE, KEN_FRENCH_MOMENTUM_SOURCE],
        },
        "price_range_volatility": {
            "label": "가격 범위 변동성 필터",
            "plain_explanation": (
                "관찰 기간의 최고가와 최저가 차이를 평균 가격으로 나눠, "
                "가격이 얼마나 크게 흔들렸는지 비교합니다."
            ),
            "why_used": "상승률이 비슷해도 지나치게 불안정한 종목의 비중을 줄이기 위해 사용합니다.",
            "caution": "과거 가격 범위가 좁았던 종목도 새로운 사건 뒤에는 급격히 흔들릴 수 있습니다.",
            "source_refs": [NBER_VOLATILITY_SOURCE],
        },
        "trend_risk_exit": {
            "label": "추세 훼손·손실 제한 청산",
            "plain_explanation": (
                "중기 또는 장기 평균선 아래로 내려가거나 정해 둔 손실 한도를 넘으면 "
                "더 큰 손실을 기다리지 않고 보유를 끝냅니다."
            ),
            "why_used": "좋은 종목을 찾는 규칙과 별개로 하락 국면의 손실 크기를 통제하기 위해 사용합니다.",
            "caution": "급락 뒤 바로 반등하면 낮은 가격에 팔고 재진입이 늦어질 수 있습니다.",
            "source_refs": [AQR_TREND_SOURCE, FABER_TACTICAL_SOURCE],
        },
        "rsi": {
            "label": "RSI",
            "plain_explanation": "최근 상승폭과 하락폭의 균형을 0~100 범위로 나타냅니다.",
            "why_used": "사용자가 과열·눌림 구간을 숫자로 지정할 때 그 조건을 재현하기 위해 사용합니다.",
            "caution": "강한 추세에서는 과매수·과매도 상태가 오래 지속될 수 있습니다.",
            "source_refs": [],
        },
        "volume": {
            "label": "거래량",
            "plain_explanation": "해당 기간에 실제로 거래된 주식 수입니다.",
            "why_used": "가격 움직임에 시장 참여가 동반됐는지 확인하기 위해 사용합니다.",
            "caution": "일회성 뉴스로 거래량이 급증할 수 있습니다.",
            "source_refs": [],
        },
    }
    item = catalog.get(
        key,
        {
            "label": key.replace("_", " "),
            "plain_explanation": "전략 조건에 포함된 사용자 지정 지표입니다.",
            "why_used": "사용자가 이 지표를 매매 조건으로 지정했기 때문에 그대로 검증합니다.",
            "caution": "정의와 데이터 단위를 확인한 뒤 다른 위험 지표와 함께 해석해야 합니다.",
            "source_refs": [],
        },
    )
    return {"key": key, **item}
