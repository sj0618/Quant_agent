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
FABER_TACTICAL_SOURCE = (
    "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461"
)
JEGADEESH_TITMAN_SOURCE = (
    "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=299107"
)
KEN_FRENCH_MOMENTUM_SOURCE = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
    "Data_Library/det_mom_factor_daily.html"
)
NBER_VOLATILITY_SOURCE = "https://www.nber.org/papers/w22208"

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
    """Classify strategy selection without replacing a concrete user rule."""

    lowered = (query or "").casefold()
    has_entry_or_exit_clause = any(term in lowered for term in _ENTRY_EXIT_TERMS)
    has_action = any(term in lowered for term in _ACTION_TERMS)
    has_indicator = any(term in lowered for term in _INDICATOR_TERMS)
    has_price = any(term in lowered for term in _PRICE_TERMS)
    has_operator = any(term in lowered for term in _OPERATOR_TERMS)
    has_number = bool(_NUMBER_RE.search(lowered))
    has_concrete_rule = has_entry_or_exit_clause or (
        has_number
        and has_operator
        and (has_indicator or has_action or has_price)
    )
    if has_concrete_rule:
        return "user_defined"
    if any(term in lowered for term in _AUTOMATIC_TERMS):
        return "automatic"
    return "standard"


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
            values[numerator_indices[usable]]
            / values[denominator_indices[usable]]
            - 1.0
        )
        rebalance[MOMENTUM_LONG_LOOKBACK::REBALANCE_INTERVAL_DAYS] = True

    if size > REALIZED_VOLATILITY_LOOKBACK:
        daily_returns = np.full(size, np.nan, dtype=np.float64)
        valid_pairs = valid[1:] & valid[:-1]
        daily_returns[1:][valid_pairs] = (
            values[1:][valid_pairs] / values[:-1][valid_pairs] - 1.0
        )
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
            square_totals = (
                square_prefix[selected + 1] - square_prefix[selected_starts]
            )
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


def build_strategy_explanation(strategy: Any) -> dict[str, Any]:
    mode: StrategyRequestMode = getattr(strategy, "selection_mode", "standard")
    indicators = [str(item) for item in getattr(strategy, "indicators", [])]
    if mode == "automatic":
        indicator_keys = (
            "momentum_12_1",
            "sma_50_200",
            "realized_volatility_21d",
            "rebalance_21d",
        )
        title = "검증 근거 기반 월간 모멘텀·추세 전략"
        summary = (
            "최근 한 달을 제외한 12-1 모멘텀으로 종목을 비교하고, "
            "50일·200일 이동평균과 최근 변동성으로 위험한 구간을 거릅니다."
        )
        why_selected = (
            "사용자가 자동·추천 전략을 요청했기 때문에 널리 연구된 모멘텀, "
            "추세, 변동성 관리 요소를 재현 가능한 규칙으로 조합했습니다."
        )
        rebalance = (
            "21거래일마다 새 종목을 고르도록 제한해 매일 순위를 바꾸며 생기는 "
            "과도한 매매와 거래비용을 줄입니다."
        )
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
            str(source)
            for item in explanations
            for source in item.get("source_refs", [])
        )
    )
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
    output[selected] = (
        value_prefix[selected + 1] - value_prefix[starts[complete]]
    ) / window
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
