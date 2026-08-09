from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any, Literal

import numpy as np


StrategyRequestMode = Literal["standard", "automatic", "user_defined"]
AutomaticRiskStyle = Literal["aggressive", "balanced", "defensive"]
AutomaticHorizon = Literal["short", "medium", "long"]

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
NBER_MOMENTUM_CRASH_SOURCE = "https://www.nber.org/papers/w20439"
AQR_TIME_SERIES_MOMENTUM_SOURCE = (
    "https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum"
)
MSCI_MOMENTUM_METHODOLOGY_SOURCE = (
    "https://www.msci.com/indexes/documents/methodology/"
    "2_MSCI_Momentum_Indexes_Methodology_20250417.pdf"
)
NBER_BENCHMARKING_SOURCE = "https://www.nber.org/papers/w12461"
BACKTEST_OVERFITTING_SOURCE = "https://academic.oup.com/jrssig/article/18/6/22/7038278"

# These are the default automatic priorities and the compatibility fallback for
# results created before the blueprint catalog. An explicit user preference may pick
# other pre-registered profiles, but selection still happens before returns are read.
AUTOMATIC_TOURNAMENT_PROFILES = (
    "relative_momentum_rotation",
    "risk_adjusted_momentum_rotation",
    "trend_leader_rotation",
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
    "검증된",
    "알아서",
    "권장",
    "인기",
    "많이 쓰는",
    "사람들이 쓰는",
    "사람들이 사용하는",
    "대중적인",
    "검증된 퀀트",
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
_AUTOMATIC_COMPATIBLE_NAMED_TERMS = (
    "momentum",
    "모멘텀",
    "relative strength",
    "상대강도",
    "주도주",
    "trend",
    "추세",
    "volatility",
    "변동성",
    "low vol",
    "저변동",
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


@dataclass(frozen=True)
class AutomaticStrategyPreferences:
    """Deterministic user-intent controls for the automatic strategy.

    These controls are inferred before a backtest.  They change the candidate menu and
    risk budget, but never inspect returns, which keeps customization separate from
    post-hoc curve fitting.
    """

    risk_style: AutomaticRiskStyle
    horizon: AutomaticHorizon
    max_positions: int
    rebalance_interval_days: int
    stop_loss_pct: float
    trailing_stop_pct: float


_AGGRESSIVE_PREFERENCE_TERMS = (
    "공격적",
    "고수익",
    "수익 극대화",
    "초과수익",
    "알파",
    "집중",
    "강하게",
    "aggressive",
    "high return",
    "outperform",
    "alpha",
    "concentrated",
)
_DEFENSIVE_PREFERENCE_TERMS = (
    "안정적",
    "안전",
    "보수적",
    "저위험",
    "저변동",
    "낙폭",
    "손실 최소",
    "방어",
    "연금",
    "defensive",
    "conservative",
    "low risk",
    "low volatility",
    "drawdown",
)
_SHORT_HORIZON_TERMS = (
    "단기",
    "스윙",
    "주간",
    "빠르게",
    "1개월",
    "3개월",
    "short term",
    "swing",
    "weekly",
)
_LONG_HORIZON_TERMS = (
    "장기",
    "오래",
    "저회전",
    "거래 적게",
    "1년 이상",
    "3년",
    "5년",
    "연금",
    "long term",
    "low turnover",
)
_POSITION_COUNT_RE = re.compile(
    r"(?<!\d)([3-9]|[12]\d|30)\s*(?:개(?:\s*종목)?|종목|names?|stocks?)(?!\d)",
    re.IGNORECASE,
)


def infer_automatic_strategy_preferences(query: str) -> AutomaticStrategyPreferences:
    """Turn loose risk/horizon language into bounded, auditable controls."""

    normalized = " ".join((query or "").casefold().split())
    aggressive_score = _term_score(normalized, _AGGRESSIVE_PREFERENCE_TERMS)
    defensive_score = _term_score(normalized, _DEFENSIVE_PREFERENCE_TERMS)
    position_match = _POSITION_COUNT_RE.search(normalized)
    requested_positions = int(position_match.group(1)) if position_match else None

    if requested_positions is not None and requested_positions <= 7:
        aggressive_score += 1
    elif requested_positions is not None and requested_positions >= 15:
        defensive_score += 1

    if aggressive_score > defensive_score:
        risk_style: AutomaticRiskStyle = "aggressive"
    elif defensive_score > aggressive_score:
        risk_style = "defensive"
    else:
        risk_style = "balanced"

    short_score = _term_score(normalized, _SHORT_HORIZON_TERMS)
    long_score = _term_score(normalized, _LONG_HORIZON_TERMS)
    if short_score > long_score:
        horizon: AutomaticHorizon = "short"
    elif long_score > short_score:
        horizon = "long"
    else:
        horizon = "medium"

    default_positions = {"aggressive": 8, "balanced": 10, "defensive": 15}[risk_style]
    max_positions = requested_positions or default_positions
    rebalance_interval_days = {"short": 10, "medium": 21, "long": 42}[horizon]
    if any(term in normalized for term in ("매주", "weekly")):
        rebalance_interval_days = 5
    elif any(term in normalized for term in ("격주", "biweekly")):
        rebalance_interval_days = 10
    elif any(term in normalized for term in ("매월", "월간", "monthly")):
        rebalance_interval_days = 21
    elif any(term in normalized for term in ("분기", "quarterly")):
        rebalance_interval_days = 63

    stop_loss_pct, trailing_stop_pct = {
        "aggressive": (0.25, 0.30),
        "balanced": (0.20, 0.25),
        "defensive": (0.12, 0.15),
    }[risk_style]
    return AutomaticStrategyPreferences(
        risk_style=risk_style,
        horizon=horizon,
        max_positions=max_positions,
        rebalance_interval_days=rebalance_interval_days,
        stop_loss_pct=stop_loss_pct,
        trailing_stop_pct=trailing_stop_pct,
    )


def automatic_candidate_profiles(
    risk_style: AutomaticRiskStyle,
    horizon: AutomaticHorizon,
) -> tuple[str, str, str]:
    """Return only the three configurations compatible with the stated intent."""

    if risk_style == "defensive":
        return (
            "risk_adjusted_momentum_rotation",
            "relative_momentum_rotation",
            "trend_leader_rotation",
        )
    if horizon == "short":
        return (
            "trend_leader_rotation",
            "risk_adjusted_momentum_rotation",
            "relative_momentum_rotation",
        )
    if risk_style == "aggressive":
        return (
            "relative_momentum_rotation",
            "trend_leader_rotation",
            "risk_adjusted_momentum_rotation",
        )
    return AUTOMATIC_TOURNAMENT_PROFILES


def automatic_candidate_lookbacks(
    profiles: Sequence[str],
    *,
    risk_style: AutomaticRiskStyle,
    horizon: AutomaticHorizon,
) -> list[int]:
    """Choose medium-term windows without searching them after seeing returns."""

    if risk_style == "defensive":
        return [252 for _ in profiles]
    if horizon == "short":
        return [252 if profile == "relative_momentum_rotation" else 126 for profile in profiles]
    return [252 for _ in profiles]


def _term_score(text: str, terms: Sequence[str]) -> int:
    return sum(1 for term in terms if term in text)


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
    has_creation_intent = any(term in lowered for term in _STRATEGY_CREATION_TERMS)
    is_information_only = any(term in lowered for term in _INFORMATIONAL_TERMS) and not (
        has_creation_intent
    )
    if is_information_only:
        return "standard"
    if any(term in lowered for term in _AUTOMATIC_TERMS):
        return "automatic"
    if any(term in lowered for term in _NAMED_STRATEGY_TERMS):
        if has_creation_intent and any(
            term in lowered for term in _AUTOMATIC_COMPATIBLE_NAMED_TERMS
        ):
            return "automatic"
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
    generated_strategies: Sequence[Mapping[str, Any] | Any] | None = None,
) -> dict[str, Any]:
    mode: StrategyRequestMode = getattr(strategy, "selection_mode", "standard")
    indicators = [str(item) for item in getattr(strategy, "indicators", [])]
    generated_strategy_payloads = _generated_strategy_payloads(generated_strategies)
    selected_blueprint_id = str(
        _parameter_value(selected_parameters, "blueprint_id") or ""
    )
    selected_blueprint = next(
        (
            item
            for item in generated_strategy_payloads
            if str(item.get("blueprint_id") or "") == selected_blueprint_id
        ),
        None,
    )
    if mode == "automatic" and selected_blueprint is not None:
        indicator_keys: tuple[str, ...] = ()
        title = str(selected_blueprint.get("title") or "자동 퀀트 전략")
        summary = str(
            selected_blueprint.get("plain_explanation")
            or selected_blueprint.get("formula")
            or "사전등록 산식을 실행한 자동 전략입니다."
        )
        why_selected = " ".join(
            str(value)
            for value in (
                selected_blueprint.get("why_generated"),
                selected_blueprint.get("why_used"),
            )
            if value
        )
        if selected_blueprint.get("execution_mode") == "scheduled_rotation":
            days = int(
                _parameter_value(selected_parameters, "rebalance_interval_days") or 21
            )
            rebalance = f"{days}거래일마다 조건과 순위를 다시 계산해 목표 종목을 교체합니다."
        else:
            rebalance = "고정 교체일까지 기다리지 않고 전략 고유의 진입·청산 신호가 발생할 때 매매합니다."
        explanations = [
            dict(item)
            for item in selected_blueprint.get("indicator_explanations", [])
            if isinstance(item, Mapping)
        ]
    elif mode == "automatic":
        automatic = _automatic_profile_explanation(
            strategy,
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
    if not (mode == "automatic" and selected_blueprint is not None):
        explanations = [
            _indicator_explanation(
                key,
                strategy=strategy,
                selected_parameters=selected_parameters,
            )
            for key in dict.fromkeys(indicator_keys)
        ]
    source_refs = list(
        dict.fromkeys(
            [
                *(str(source) for item in explanations for source in item.get("source_refs", [])),
                *(
                    str(source)
                    for item in generated_strategy_payloads
                    for source in item.get("source_refs", [])
                ),
                *(
                    str(source)
                    for item in generated_strategy_payloads
                    for indicator in item.get("indicator_explanations", [])
                    if isinstance(indicator, Mapping)
                    for source in indicator.get("source_refs", [])
                ),
            ]
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
        "generated_strategies": generated_strategy_payloads,
        "source_refs": source_refs,
    }


def _generated_strategy_payloads(
    items: Sequence[Mapping[str, Any] | Any] | None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for item in items or ():
        if isinstance(item, Mapping):
            payloads.append(dict(item))
            continue
        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            payloads.append(dict(model_dump(mode="json")))
    return payloads


def academic_strategy_source_refs() -> list[str]:
    return [
        AQR_TREND_SOURCE,
        FABER_TACTICAL_SOURCE,
        JEGADEESH_TITMAN_SOURCE,
        KEN_FRENCH_MOMENTUM_SOURCE,
        NBER_VOLATILITY_SOURCE,
    ]


def robust_strategy_source_refs() -> list[str]:
    return [
        *academic_strategy_source_refs(),
        AQR_TIME_SERIES_MOMENTUM_SOURCE,
        MSCI_MOMENTUM_METHODOLOGY_SOURCE,
        NBER_MOMENTUM_CRASH_SOURCE,
        NBER_BENCHMARKING_SOURCE,
        BACKTEST_OVERFITTING_SOURCE,
    ]


def _automatic_profile_explanation(
    strategy: Any,
    selected_profile: str | None,
    *,
    selected_parameters: Mapping[str, Any] | Any | None,
) -> dict[str, Any]:
    lookback = _parameter_value(selected_parameters, "lookback")
    threshold = _parameter_value(selected_parameters, "threshold")
    constraints = getattr(strategy, "risk_constraints", {}) or {}
    style = str(constraints.get("strategy_style", "balanced"))
    horizon = str(constraints.get("investment_horizon", "medium"))
    style_label = {
        "aggressive": "공격형",
        "balanced": "균형형",
        "defensive": "방어형",
    }.get(style, "균형형")
    horizon_label = {"short": "단기", "medium": "중기", "long": "장기"}.get(horizon, "중기")
    rebalance_days = int(
        _parameter_value(selected_parameters, "rebalance_interval_days")
        or constraints.get("rebalance_interval_days", 21)
    )
    max_positions = int(
        _parameter_value(selected_parameters, "max_positions")
        or round(1.0 / float(constraints.get("max_position_pct", 0.1)))
    )
    medium_weight = float(
        _parameter_value(selected_parameters, "medium_momentum_weight")
        or constraints.get("medium_momentum_weight", 0.60)
    )
    selection_reason = (
        f"입력을 {style_label}·{horizon_label}으로 해석해 최대 {max_positions}종목, "
        f"{rebalance_days}거래일 교체 조건에 맞는 후보 3개만 비교했습니다. "
        "앞 70%에서는 벤치마크 초과수익을 가장 크게 반영해 선택하고, 마지막 30%는 "
        "선택에 쓰지 않습니다. 63거래일 단위 패배 구간이 50% 이상이거나 최종 "
        "누적 초과수익이 음수이면 검증 실패입니다."
    )
    if selected_profile == "relative_momentum_rotation":
        return {
            "indicator_keys": (
                "cross_sectional_rank",
                "momentum_12_1",
                "sma_200_regime",
                "winner_hold",
                "crash_risk_guard",
                "portfolio_customization",
                "benchmark_period_gate",
            ),
            "title": "12-1 상대강도 승자 순환 전략",
            "summary": (
                "한 달 전까지의 약 1년 수익률로 모든 종목의 순위를 매기고, "
                "200일선 위이면서 모멘텀이 양수인 상위 종목을 매달 교체합니다."
            ),
            "why_selected": selection_reason,
            "rebalance": (
                f"{rebalance_days}거래일마다 상위 종목을 다시 선정하고, 순위에서 밀린 종목은 팔되 "
                "계속 강한 승자는 45% 같은 조기 고정 익절 없이 보유합니다."
            ),
        }
    if selected_profile == "risk_adjusted_momentum_rotation":
        return {
            "indicator_keys": (
                "cross_sectional_rank",
                "momentum_blend",
                "realized_volatility_21d",
                "sma_200_regime",
                "winner_hold",
                "crash_risk_guard",
                "portfolio_customization",
                "benchmark_period_gate",
            ),
            "title": "변동성 조절 복합 모멘텀 순환 전략",
            "summary": (
                "12-1 모멘텀과 약 6개월 모멘텀을 각각 최근 변동성으로 나눈 뒤 "
                "순위를 50%씩 합쳐, 상승 힘 대비 위험이 나은 종목을 고릅니다."
            ),
            "why_selected": selection_reason,
            "rebalance": f"{rebalance_days}거래일마다 순위를 갱신하고 고변동 종목과 추세 이탈 종목을 교체합니다.",
        }
    if selected_profile == "trend_leader_rotation":
        return {
            "indicator_keys": (
                "cross_sectional_rank",
                "momentum_blend",
                "sma_200_regime",
                "winner_hold",
                "crash_risk_guard",
                "portfolio_customization",
                "benchmark_period_gate",
            ),
            "title": "6개월·12-1 추세 주도주 순환 전략",
            "summary": (
                f"중기 상승률에 {medium_weight:.0%}, 12-1 모멘텀에 "
                f"{1.0 - medium_weight:.0%}를 두어, "
                "최근과 중장기 구간에서 동시에 강한 200일선 위 종목을 보유합니다."
            ),
            "why_selected": selection_reason,
            "rebalance": f"{rebalance_days}거래일마다 주도주 순위를 다시 계산해 강한 승자는 유지하고 약해진 종목만 바꿉니다.",
        }
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
            "cross_sectional_rank",
            "momentum_12_1",
            "momentum_blend",
            "winner_hold",
            "crash_risk_guard",
            "portfolio_customization",
            "benchmark_period_gate",
        ),
        "title": f"{style_label}·{horizon_label} 벤치마크 초과수익 맞춤 전략군",
        "summary": (
            "생성 단계에서 12-1 상대강도, 변동성 조절 복합 모멘텀, 사용자기간 맞춤 "
            "주도주 순환을 각각 독립 전략으로 미리 만듭니다. 백테스트는 이후 별도 단계에서 비교합니다."
        ),
        "why_selected": (
            f"사용자의 {style_label}·{horizon_label} 입력에 맞지 않는 후보는 제외하고, "
            "학습구간 초과수익과 고정 63거래일 승패를 자동으로 비교합니다. 마지막 30%에서도 "
            "패배 구간이 절반 미만이고 누적 초과수익이 양수여야 추천으로 인정합니다."
        ),
        "rebalance": f"{rebalance_days}거래일마다 순위를 갱신하되 매일 사고팔지 않아 비용을 제한합니다.",
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


def _indicator_explanation(
    key: str,
    *,
    strategy: Any | None = None,
    selected_parameters: Mapping[str, Any] | Any | None = None,
) -> dict[str, Any]:
    catalog: Mapping[str, dict[str, Any]] = {
        "momentum_12_1": {
            "label": "12-1 모멘텀",
            "plain_explanation": (
                "252거래일 전 가격과 21거래일 전 가격을 비교합니다. "
                "최근 한 달은 단기 반전 영향을 줄이기 위해 제외합니다."
            ),
            "why_used": "중기 추세가 이어지는 종목을 같은 시점의 다른 종목과 비교하기 위해 사용합니다.",
            "formula": "M12-1(t) = P(t-21) / P(t-252) - 1",
            "derivation": (
                "252거래일은 약 1년, 21거래일은 약 1개월입니다. Ken French의 "
                "모멘텀 정의처럼 직전 한 달을 제외해 단기 반전 영향을 줄였습니다."
            ),
            "caution": "추세가 갑자기 뒤집히면 신호가 늦을 수 있습니다.",
            "source_refs": [JEGADEESH_TITMAN_SOURCE, KEN_FRENCH_MOMENTUM_SOURCE],
        },
        "sma_50_200": {
            "label": "50일·200일 이동평균",
            "plain_explanation": "최근 50일 평균 가격과 200일 평균 가격으로 단기·장기 추세 방향을 봅니다.",
            "why_used": "약한 하락 추세의 종목을 모멘텀 순위만으로 사는 일을 줄이기 위해 사용합니다.",
            "formula": "SMA_n(t) = (P(t)+P(t-1)+...+P(t-n+1)) / n; n∈{50, 200}",
            "derivation": "50일은 약 한 분기, 200일은 약 한 거래연도를 대표해 서로 다른 추세 길이를 비교합니다.",
            "caution": "횡보장에서는 신호가 자주 엇갈리고 진입이 늦을 수 있습니다.",
            "source_refs": [AQR_TREND_SOURCE, FABER_TACTICAL_SOURCE],
        },
        "realized_volatility_21d": {
            "label": "21일 실현변동성",
            "plain_explanation": "최근 21개 일간 수익률이 얼마나 크게 흔들렸는지를 연 단위로 환산한 값입니다.",
            "why_used": "같은 모멘텀이라도 급격히 흔들리는 종목의 위험을 낮게 평가하기 위해 사용합니다.",
            "formula": "σ21(t) = 표준편차(최근 21개 일간수익률) × √252",
            "derivation": "21거래일은 약 한 달이며, √252를 곱해 서로 다른 기간과 비교 가능한 연율 값으로 바꿉니다.",
            "caution": "과거 21일의 안정성이 다음 달에도 이어진다는 보장은 없습니다.",
            "source_refs": [NBER_VOLATILITY_SOURCE],
        },
        "rebalance_21d": {
            "label": "21거래일 리밸런싱",
            "plain_explanation": "약 한 달에 한 번만 새 종목을 고르고 비중을 점검합니다.",
            "why_used": "매일 순위가 조금 바뀔 때마다 매매하는 비용과 잡음을 줄이기 위해 사용합니다.",
            "formula": "교체일 = 최초 신호 가능일 + 21×k 거래일 (k=0,1,2,...)",
            "derivation": "21거래일을 평균적인 한 달로 보고, 월중 가격 잡음보다 지속된 순위 변화만 반영합니다.",
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
            "formula": (
                "선택점수 = 1.00×연환산초과수익 + 0.35×샤프 + 0.15×칼마 + "
                "0.10×연환산수익 + 0.20×구간승패일관성 - 0.05×회전율벌점"
            ),
            "derivation": (
                "1.00은 사용자의 지수 초과수익 목표를 가장 크게 반영합니다. 0.35 샤프와 0.15 칼마는 "
                "변동성과 낙폭을 보정하고, 0.10 절대수익은 지수만 덜 하락해 이기는 후보를 제한하며, "
                "0.20 구간일관성은 반복성을 보상합니다. 0.05 회전율은 비용 벌점입니다. 모두 결과를 "
                "보기 전에 정한 제품 가중치이며 학술 상수는 아닙니다."
            ),
            "caution": "후보를 세 개로 제한해도 과거의 승자가 미래에도 이긴다는 보장은 없습니다.",
            "source_refs": [BACKTEST_OVERFITTING_SOURCE],
        },
        "cross_sectional_rank": {
            "label": "종목 간 상대강도 순위",
            "plain_explanation": (
                "각 종목의 상승률을 따로 합격·불합격 처리하지 않고 같은 날 모든 종목과 "
                "비교해 가장 강한 종목부터 순위를 매깁니다."
            ),
            "why_used": "시장 전체가 오를 때도 그중 자금이 더 강하게 몰리는 주도주를 고르기 위해 사용합니다.",
            "formula": "백분위순위 = (동률 평균순위 - 1) / (비교종목수 - 1)",
            "derivation": "가격 단위가 다른 종목을 같은 0~1 척도로 비교하고, 같은 값에는 같은 순위를 주기 위한 변환입니다.",
            "caution": "현재 유니버스가 너무 작거나 생존 종목만 포함하면 순위 결과가 왜곡될 수 있습니다.",
            "source_refs": [JEGADEESH_TITMAN_SOURCE, KEN_FRENCH_MOMENTUM_SOURCE],
        },
        "momentum_blend": {
            "label": "6개월·12-1 복합 모멘텀",
            "plain_explanation": (
                "약 6개월 상승률과 최근 한 달을 뺀 약 1년 상승률을 함께 순위화합니다. "
                "한 기간에만 우연히 급등한 종목보다 여러 기간에서 강한 종목이 위로 갑니다."
            ),
            "why_used": "중기와 장기 추세가 동시에 이어지는 주도주를 찾기 위해 사용합니다.",
            "formula": "선택된 프로필과 사용자 투자기간에 따라 6개월·12-1 모멘텀 순위를 가중 결합",
            "derivation": (
                "위험조정 프로필은 MSCI의 두 기간 위험조정·50:50 결합 원리를 참고합니다. "
                "다만 데이터 범위에 맞춰 3년 주간 변동성·z점수 대신 21일 일간변동성·"
                "백분위순위를 쓰는 단순화입니다. 추세 주도주 프로필은 사용자 투자기간이 "
                "짧을수록 중기 비중을 높입니다."
            ),
            "caution": "급격한 시장 반등에서는 과거의 패자가 갑자기 올라 순위 전략이 뒤처질 수 있습니다.",
            "source_refs": [
                AQR_TIME_SERIES_MOMENTUM_SOURCE,
                KEN_FRENCH_MOMENTUM_SOURCE,
                MSCI_MOMENTUM_METHODOLOGY_SOURCE,
                NBER_MOMENTUM_CRASH_SOURCE,
            ],
        },
        "sma_200_regime": {
            "label": "200일 추세 필터",
            "plain_explanation": "현재 가격이 약 1년 평균 가격인 200일선 위에 있는지 확인합니다.",
            "why_used": "상대 순위가 높아도 장기 하락 추세인 종목을 사는 일을 줄이기 위해 사용합니다.",
            "formula": "SMA200(t) = 최근 200개 종가의 산술평균; 진입조건 P(t) ≥ SMA200(t)",
            "derivation": "약 한 거래연도의 평균 원가 위에 있는 종목만 남겨 장기 하락 국면의 역추세 매수를 줄입니다.",
            "caution": "급반등 초반에는 200일선을 아직 회복하지 못해 진입이 늦을 수 있습니다.",
            "source_refs": [AQR_TREND_SOURCE, FABER_TACTICAL_SOURCE],
        },
        "winner_hold": {
            "label": "승자 장기보유·월간 교체",
            "plain_explanation": (
                "일반적인 단기 익절 목표에 도달했다고 바로 팔지 않고, 상대 순위와 "
                "장기 추세가 유지되는 동안 계속 보유합니다."
            ),
            "why_used": "소수의 큰 상승 종목이 포트폴리오 전체 수익을 끌어올리는 효과를 잘라내지 않기 위해 사용합니다.",
            "formula": "정기 교체일에 상위 N 안에 남아 있으면 보유, 순위 이탈 또는 위험조건 충족 시 매도",
            "derivation": "고정 익절폭을 두지 않고 모멘텀이 유지되는 동안 큰 승자의 오른쪽 꼬리 수익을 보존합니다.",
            "caution": "승자를 오래 보유하는 만큼 고점 이후 되돌림이 커질 수 있어 손실 제한과 분산이 필요합니다.",
            "source_refs": [AQR_TIME_SERIES_MOMENTUM_SOURCE, NBER_MOMENTUM_CRASH_SOURCE],
        },
        "crash_risk_guard": {
            "label": "모멘텀 급락 안전장치",
            "plain_explanation": (
                "매수가보다 20% 이상 하락하거나 보유 중 최고가에서 25% 이상 밀리면 "
                "다음 월간 교체일까지 기다리지 않고 빠져나옵니다."
            ),
            "why_used": "모멘텀 전략이 시장 급반등 국면에서 드물지만 크게 손실 나는 위험을 제한하기 위해 사용합니다.",
            "formula": "매도 = 수익률 ≤ -손절폭 또는 P(t) ≤ 보유중최고가×(1-추적손절폭)",
            "derivation": "손절폭은 사용자의 공격·균형·방어 성향에서 정하며, 모멘텀 급락 연구를 반영한 위험예산이지 수익을 맞추기 위한 값이 아닙니다.",
            "caution": "급락 직후 바로 반등하면 손실을 확정하고 재진입이 늦어질 수 있습니다.",
            "source_refs": [NBER_MOMENTUM_CRASH_SOURCE],
        },
        "portfolio_customization": {
            "label": "사용자 맞춤 포트폴리오 제어",
            "plain_explanation": "입력한 위험성향과 투자기간에 맞춰 보유 종목 수, 교체 주기와 손실 제한을 정합니다.",
            "why_used": "같은 지표라도 단기 집중 투자와 장기 방어 투자는 서로 다른 비용·낙폭 허용치가 필요합니다.",
            "formula": "종목당 목표비중 = 1 / 최대보유종목수; 교체주기·손절폭은 입력 성향표에서 사전 결정",
            "derivation": (
                "공격형 8종목(종목당 약 12.5%), 균형형 10종목(10%), 방어형 15종목(약 6.7%)의 "
                "사전 프리셋으로 집중도를 단계적으로 낮춥니다. 손절·추적손절은 각각 공격형 25%·30%, "
                "균형형 20%·25%, 방어형 12%·15%로 위험 허용도를 좁힙니다. 학술 상수가 아니라 "
                "설명 가능한 제품 기본값이며 사용자가 종목 수나 주기를 말하면 그 값을 우선합니다."
            ),
            "caution": "입력 해석은 백테스트 수익을 보지 않고 수행되며, 집중도가 높을수록 종목 고유위험이 커집니다.",
            "source_refs": [MSCI_MOMENTUM_METHODOLOGY_SOURCE, BACKTEST_OVERFITTING_SOURCE],
        },
        "benchmark_period_gate": {
            "label": "고정구간 벤치마크 승패 판정",
            "plain_explanation": (
                "전 기간을 약 3개월인 63거래일씩 고정 분할해 각 구간의 전략 수익률과 "
                "벤치마크 수익률을 비교합니다."
            ),
            "why_used": "몇 번의 큰 초과수익은 허용하되 대부분의 시장 구간에서 지는 전략을 성공으로 포장하지 않기 위해 사용합니다.",
            "formula": (
                "패배율 = 벤치마크보다 수익률이 낮은 63일 구간 수 / 유효 구간 수; "
                "패배율 ≥ 50%이면 실패"
            ),
            "derivation": (
                "63일은 단기 시장 국면을 분리하면서 월간 순환을 세 번가량 관찰하는 한 분기입니다. "
                "구간 길이와 50% 문턱은 "
                "사용자 기준으로 사전에 고정하며 결과에 맞춰 이동시키지 않습니다."
            ),
            "caution": "실제 KOSPI 지수열이 없는 환경에서는 분석 유니버스의 고정 동일가중 매수·보유 프록시와 비교합니다.",
            "source_refs": [NBER_BENCHMARKING_SOURCE, BACKTEST_OVERFITTING_SOURCE],
        },
        "dual_sma_trend": {
            "label": "단기·중기·장기 이동평균 정렬",
            "plain_explanation": (
                "최근 가격 평균을 짧은 구간, 중간 구간, 긴 구간으로 나눠 계산하고 "
                "짧은 평균이 더 위에 있는 상승 정렬인지 확인합니다."
            ),
            "why_used": "일시적인 하루 급등보다 여러 시간대에서 이어지는 추세를 확인하기 위해 사용합니다.",
            "formula": "진입 = SMA단기 > SMA중기 > 0.98×SMA장기 이고 P(t) ≥ SMA단기",
            "derivation": "후보의 기준 lookback을 장기로 두고 그 1/2·1/4을 중기·단기로 나눠 동일한 비율로 추세를 비교합니다.",
            "caution": "방향 없이 오르내리는 장에서는 매수와 매도가 자주 엇갈릴 수 있습니다.",
            "source_refs": [AQR_TREND_SOURCE, FABER_TACTICAL_SOURCE],
        },
        "medium_momentum_126d": {
            "label": "약 6개월 모멘텀",
            "plain_explanation": "현재 가격을 약 126거래일 전 가격과 비교해 중기 상승 힘을 봅니다.",
            "why_used": "너무 짧은 뉴스성 급등보다 몇 달간 이어진 가격 방향을 포착하기 위해 사용합니다.",
            "formula": "M126(t) = P(t) / P(t-126) - 1",
            "derivation": "126거래일은 약 6개월이라 1년 모멘텀보다 최근 추세 변화에 빠르게 반응합니다.",
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
            "formula": "범위변동성 = (관찰기간 최고가 - 관찰기간 최저가) / 관찰기간 평균가",
            "derivation": "가격 단위가 다른 종목도 비교할 수 있도록 고저 차이를 평균 가격으로 나눈 무차원 비율입니다.",
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
            "formula": "청산 = 추세선 이탈 또는 보유수익률 ≤ -손절폭 또는 최고가대비하락률 ≥ 추적손절폭",
            "derivation": "느린 추세 신호와 빠른 가격 손실 제한을 함께 써 급락 때 정기 교체일까지 기다리지 않게 합니다.",
            "caution": "급락 뒤 바로 반등하면 낮은 가격에 팔고 재진입이 늦어질 수 있습니다.",
            "source_refs": [AQR_TREND_SOURCE, FABER_TACTICAL_SOURCE],
        },
        "rsi": {
            "label": "RSI",
            "plain_explanation": "최근 상승폭과 하락폭의 균형을 0~100 범위로 나타냅니다.",
            "why_used": "사용자가 과열·눌림 구간을 숫자로 지정할 때 그 조건을 재현하기 위해 사용합니다.",
            "formula": "RSI = 100 - 100/(1 + 최근 평균상승폭/최근 평균하락폭)",
            "derivation": "상승폭과 하락폭의 상대 크기를 0~100으로 정규화한 Wilder 계열 지표이며, 기간·문턱은 사용자 조건을 우선합니다.",
            "caution": "강한 추세에서는 과매수·과매도 상태가 오래 지속될 수 있습니다.",
            "source_refs": [],
        },
        "volume": {
            "label": "거래량",
            "plain_explanation": "해당 기간에 실제로 거래된 주식 수입니다.",
            "why_used": "가격 움직임에 시장 참여가 동반됐는지 확인하기 위해 사용합니다.",
            "formula": "거래량비(t) = V(t) / 과거 N일 평균거래량",
            "derivation": "종목마다 평소 거래 규모가 달라 절대 거래량 대신 자기 과거 평균 대비 배수로 비교합니다.",
            "caution": "일회성 뉴스로 거래량이 급증할 수 있습니다.",
            "source_refs": [],
        },
    }
    item = dict(
        catalog.get(
            key,
            {
                "label": key.replace("_", " "),
                "plain_explanation": "전략 조건에 포함된 사용자 지정 지표입니다.",
                "why_used": "사용자가 이 지표를 매매 조건으로 지정했기 때문에 그대로 검증합니다.",
                "formula": f"사용자 전략식에 지정된 {key} 값과 임계값을 그대로 적용",
                "derivation": "자동으로 새 수치나 공식을 만든 것이 아니라 사용자의 원래 조건을 보존한 값입니다.",
                "caution": "정의와 데이터 단위를 확인한 뒤 다른 위험 지표와 함께 해석해야 합니다.",
                "source_refs": [],
            },
        )
    )
    constraints = getattr(strategy, "risk_constraints", {}) or {}
    selected_profile = str(_parameter_value(selected_parameters, "profile") or "")
    rebalance_days = int(
        _parameter_value(selected_parameters, "rebalance_interval_days")
        or constraints.get("rebalance_interval_days", 21)
    )
    max_positions = int(
        _parameter_value(selected_parameters, "max_positions")
        or round(1.0 / float(constraints.get("max_position_pct", 0.1)))
    )
    stop_loss_pct = float(
        _parameter_value(selected_parameters, "stop_loss_pct")
        or constraints.get("stop_loss_pct", 0.20)
    )
    trailing_stop_pct = float(
        _parameter_value(selected_parameters, "trailing_stop_pct")
        or constraints.get("trailing_stop_pct", 0.25)
    )
    medium_weight = float(
        _parameter_value(selected_parameters, "medium_momentum_weight")
        or constraints.get("medium_momentum_weight", 0.60)
    )
    style = str(constraints.get("strategy_style", "balanced"))
    horizon = str(constraints.get("investment_horizon", "medium"))
    if key == "momentum_blend":
        if selected_profile == "risk_adjusted_momentum_rotation":
            item["formula"] = "점수 = 0.50×백분위순위(M12-1/σ21) + 0.50×백분위순위(M중기/σ21)"
            item["customization"] = (
                "위험조정형 후보라 두 기간을 사전고정 50:50으로 결합했습니다. MSCI 방법론의 "
                "핵심 구조를 참고했지만 변동성 기간과 표준화 방식은 제품용으로 단순화했습니다."
            )
        else:
            item["formula"] = (
                f"점수 = {medium_weight:.0%}×중기모멘텀순위 + "
                f"{1.0 - medium_weight:.0%}×12-1모멘텀순위"
            )
            item["customization"] = (
                f"입력 투자기간을 {horizon}으로 해석해 중기 비중을 {medium_weight:.0%}로 정했습니다."
            )
    elif key == "winner_hold":
        item["label"] = f"승자 보유·{rebalance_days}거래일 교체"
        item["customization"] = (
            f"입력 투자기간에 맞춰 교체 주기를 {rebalance_days}거래일로 고정했습니다."
        )
    elif key == "crash_risk_guard":
        item["plain_explanation"] = (
            f"매수가보다 {stop_loss_pct:.0%} 이상 하락하거나 보유 중 최고가에서 "
            f"{trailing_stop_pct:.0%} 이상 밀리면 다음 정기 교체일까지 기다리지 않고 나옵니다."
        )
        item["customization"] = (
            f"입력 위험성향을 {style}으로 해석해 손절 {stop_loss_pct:.0%}, "
            f"추적손절 {trailing_stop_pct:.0%}를 적용했습니다."
        )
    elif key == "portfolio_customization":
        item["plain_explanation"] = (
            f"최대 {max_positions}종목을 동일비중에 가깝게 보유하고 "
            f"{rebalance_days}거래일마다 후보를 교체합니다."
        )
        item["customization"] = (
            f"입력을 위험성향 {style}, 투자기간 {horizon}으로 해석한 결과입니다."
        )
    elif key == "benchmark_period_gate":
        item["caution"] = (
            "63거래일을 채우지 못한 마지막 미완료 구간은 승패 계산에서 제외합니다. "
            "실제 KOSPI 지수열이 없는 환경에서는 고정 동일가중 매수·보유 프록시를 사용합니다."
        )
        item["customization"] = (
            "사용자가 지정한 판정 기준대로 패배 구간이 정확히 50%인 경우도 실패로 처리합니다."
        )
    return {"key": key, **item}
