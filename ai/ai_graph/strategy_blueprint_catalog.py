from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.schemas import StructuredProfile


CATALOG_VERSION = "quant-blueprints.v1"
CATALOG_STORAGE = "versioned_python_catalog"

RiskStyle = Literal["aggressive", "balanced", "defensive"]
InvestmentHorizon = Literal["short", "medium", "long"]


SOURCE_REGISTRY: dict[str, str] = {
    "aqr_time_series_momentum": (
        "https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum"
    ),
    "aqr_trend_following": (
        "https://www.aqr.com/Insights/Research/Journal-Article/"
        "A-Century-of-Evidence-on-Trend-Following-Investing"
    ),
    "faber_tactical": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461",
    "french_momentum": (
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
        "Data_Library/det_mom_factor_daily.html"
    ),
    "french_short_reversal": (
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
        "data_library/det_st_rev_factor_daily.html"
    ),
    "george_hwang_52_week_high": (
        "https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2004.00695.x"
    ),
    "lee_swaminathan_volume": ("https://papers.ssrn.com/sol3/papers.cfm?abstract_id=92589"),
    "moreira_muir_volatility": "https://www.nber.org/papers/w22208",
    "msci_momentum": (
        "https://www.msci.com/indexes/documents/methodology/"
        "2_MSCI_Momentum_Indexes_Methodology_20250417.pdf"
    ),
    "momentum_crashes": "https://www.nber.org/papers/w20439",
    "quality_minus_junk": (
        "https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk"
    ),
    "betting_against_beta": (
        "https://www.aqr.com/Insights/Research/Journal-Article/Betting-Against-Beta"
    ),
    "sharpe_ratio": "https://web.stanford.edu/~wfsharpe/art/sr/SR.htm",
    "wilder_rsi": (
        "https://windsorpublishing.com/product/new-concepts-in-technical-trading-systems/"
    ),
    "backtest_overfitting": ("https://academic.oup.com/jrssig/article/18/6/22/7038278"),
}


class BlueprintParameters(BaseModel):
    """Executable defaults; user intent may change only these bounded values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lookback: int = Field(ge=3, le=252)
    threshold: float = Field(ge=-1.0, le=100.0)
    max_positions: int = Field(gt=0, le=1000)
    rebalance_interval_days: int = Field(ge=5, le=63)
    stop_loss_pct: float = Field(gt=0.0, le=1.0)
    take_profit_pct: float = Field(gt=0.0, le=10.0)
    trailing_stop_pct: float = Field(gt=0.0, le=0.75)


class BlueprintParameterRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum: float
    maximum: float
    unit: str = Field(min_length=1)
    derivation: str = Field(min_length=1)
    user_overridable: bool = True


class StrategyBlueprintTemplate(BaseModel):
    """Research provenance plus an executable profile and bounded parameters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: str = Field(pattern=r"^qb-v1-[a-z0-9-]+$")
    catalog_version: str = CATALOG_VERSION
    archetype_id: str = Field(min_length=1)
    preset_id: str = Field(min_length=1)
    family: str = Field(min_length=1)
    profile: StructuredProfile
    title: str = Field(min_length=1)
    plain_explanation: str = Field(min_length=1)
    formula: str = Field(min_length=1)
    derivation: str = Field(min_length=1)
    why_used: str = Field(min_length=1)
    risk_style: RiskStyle
    investment_horizon: InvestmentHorizon
    default_parameters: BlueprintParameters
    parameter_schema: dict[str, BlueprintParameterRule] = Field(min_length=7)
    tags: list[str] = Field(min_length=1)
    required_data: list[str] = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    caveats: list[str] = Field(min_length=1)
    implementation_notes: str = Field(min_length=1)
    native_execution: bool = True


@dataclass(frozen=True)
class _Archetype:
    archetype_id: str
    family: str
    profile: StructuredProfile
    title: str
    plain_explanation: str
    formula: str
    derivation: str
    why_used: str
    base_lookback: int
    lookback_range: tuple[int, int]
    base_threshold: float
    threshold_range: tuple[float, float]
    tags: tuple[str, ...]
    source_keys: tuple[str, ...]
    caveats: tuple[str, ...]
    implementation_notes: str
    required_data: tuple[str, ...] = ("adjusted_ohlcv_daily",)


@dataclass(frozen=True)
class _Preset:
    preset_id: str
    label: str
    risk_style: RiskStyle
    horizon: InvestmentHorizon
    lookback_multiplier: float
    threshold_multiplier: float
    max_positions: int
    rebalance_days: int
    stop_loss_pct: float
    trailing_stop_pct: float


_PRESETS: tuple[_Preset, ...] = (
    _Preset("fast", "빠른 공격형", "aggressive", "short", 0.50, 0.80, 8, 5, 0.25, 0.30),
    _Preset("tactical", "단기 전술형", "balanced", "short", 0.75, 0.90, 10, 10, 0.20, 0.25),
    _Preset("core", "중기 기본형", "balanced", "medium", 1.00, 1.00, 10, 21, 0.20, 0.25),
    _Preset("patient", "장기 완만형", "balanced", "long", 1.50, 1.10, 12, 42, 0.18, 0.22),
    _Preset("shield", "장기 방어형", "defensive", "long", 1.25, 1.25, 15, 21, 0.12, 0.15),
)


_ARCHETYPES: tuple[_Archetype, ...] = (
    _Archetype(
        "academic-12-1-trend",
        "momentum",
        "academic_momentum_trend",
        "12-1 모멘텀·200일 추세",
        "최근 한 달을 제외한 1년 상승세와 장기 이동평균을 함께 확인합니다.",
        "score=4*M12-1+2*(SMA50/SMA200-1)-sigma21; buy=M12-1>q and P>=SMA200",
        "학술 2~12개월 모멘텀에 50·200일 추세와 21일 변동성 제한을 결합했습니다.",
        "단기 반전 노이즈를 줄이면서 장기 하락 추세 종목을 피하기 위해 사용합니다.",
        252,
        (200, 252),
        0.0,
        (0.0, 0.20),
        ("모멘텀", "momentum", "12-1", "200일선", "학술"),
        ("french_momentum", "aqr_trend_following", "momentum_crashes"),
        ("최소 252거래일 워밍업이 필요합니다.",),
        "현재 OHLCV 엔진의 academic_momentum_trend 프로필과 동일한 산식입니다.",
    ),
    _Archetype(
        "relative-12-1-rotation",
        "momentum",
        "relative_momentum_rotation",
        "12-1 상대강도 순환",
        "종목들의 12-1 수익률 순위를 비교해 상위 종목만 보유합니다.",
        "score=percentile_rank(P[t-21]/P[t-252]-1); eligible=M12-1>q and P>=SMA200",
        "절대 수익률보다 같은 시점의 종목 간 상대 순위를 사용합니다.",
        "시장 전체가 움직일 때에도 가장 강한 주도주를 구분하기 위해 사용합니다.",
        252,
        (252, 252),
        0.0,
        (0.0, 0.30),
        ("모멘텀", "momentum", "상대강도", "relative strength", "주도주"),
        ("french_momentum", "momentum_crashes"),
        ("횡단면 종목 수가 적으면 순위의 신뢰도가 낮아집니다.",),
        "현재 OHLCV 회전 엔진의 relative_momentum_rotation 프로필을 사용합니다.",
    ),
    _Archetype(
        "risk-adjusted-dual-momentum",
        "momentum",
        "risk_adjusted_momentum_rotation",
        "장·중기 위험조정 모멘텀",
        "장기와 중기 상승률을 각각 변동성으로 나눈 뒤 두 순위를 결합합니다.",
        "score=0.5*rank(M12-1/max(sigma21,.05))+0.5*rank(M[L/2]/max(sigma21,.05))",
        "MSCI의 두 기간 위험조정 모멘텀 결합을 일간 OHLCV용으로 단순화했습니다.",
        "같은 수익이라면 덜 흔들린 종목을 우선해 위험 대비 수익을 높이기 위해 사용합니다.",
        252,
        (126, 252),
        0.0,
        (0.0, 0.25),
        ("모멘텀", "momentum", "위험조정", "risk adjusted", "저변동"),
        ("msci_momentum", "moreira_muir_volatility", "momentum_crashes"),
        ("MSCI 원형의 3년 주간 변동성·z점수와는 다른 제품 단순화입니다.",),
        "현재 OHLCV 회전 엔진의 risk_adjusted_momentum_rotation 프로필을 사용합니다.",
    ),
    _Archetype(
        "trend-leader-blend",
        "momentum",
        "trend_leader_rotation",
        "중·장기 추세 주도주",
        "중기 순위와 12-1 순위를 투자기간에 맞춰 결합합니다.",
        "score=w*rank(P[t]/P[t-L/2]-1)+(1-w)*rank(M12-1); eligible=P>=SMA200",
        "짧은 투자기간일수록 중기 비중을 높이는 사전 규칙을 사용합니다.",
        "최근 주도주 변화와 오래 지속된 추세를 동시에 반영하기 위해 사용합니다.",
        126,
        (63, 252),
        0.0,
        (0.0, 0.25),
        ("모멘텀", "momentum", "추세", "trend", "주도주", "단기"),
        ("aqr_time_series_momentum", "french_momentum"),
        ("현재 구현의 중기 길이는 L/2이므로 표시 기간과 혼동하면 안 됩니다.",),
        "현재 OHLCV 회전 엔진의 trend_leader_rotation 프로필을 사용합니다.",
    ),
    _Archetype(
        "time-series-regime",
        "trend",
        "long_regime_momentum",
        "시계열 모멘텀·장기 국면",
        "자기 자신의 과거 수익이 양수이고 가격이 장기 평균 위일 때 보유합니다.",
        "buy=P>=SMA_L and SMA_L/2>=0.98*SMA_L and R_L>0; sell=P<0.97*SMA_L",
        "시계열 모멘텀의 양의 자기예측성과 장기 추세 필터를 결합했습니다.",
        "시장 하락 국면의 무조건 보유를 줄이기 위해 사용합니다.",
        252,
        (126, 252),
        0.0,
        (0.0, 0.20),
        ("추세", "trend", "시계열", "time series", "장기"),
        ("aqr_time_series_momentum", "aqr_trend_following"),
        ("횡보장에서는 반복 매매가 발생할 수 있습니다.",),
        "현재 OHLCV 엔진의 long_regime_momentum 프로필을 사용합니다.",
    ),
    _Archetype(
        "quality-trend-proxy",
        "defensive",
        "quality_trend_hold",
        "퀄리티·추세 대용지표",
        "회계 퀄리티 데이터가 없을 때 안정적 추세와 낮은 변동성을 대용지표로 씁니다.",
        "score=3*R_L/2+2*R_L+0.5*Sharpe_L-0.5*volatility; volatility<=0.28",
        "QMJ의 수익성·성장·안전성 개념 중 안전성을 가격 안정성으로만 근사합니다.",
        "기초 재무 데이터가 없는 환경에서도 방어적 후보를 만들기 위해 사용합니다.",
        126,
        (63, 252),
        0.0,
        (0.0, 0.10),
        ("퀄리티", "quality", "안정", "방어", "저변동"),
        ("quality_minus_junk", "aqr_trend_following"),
        ("ROE·수익성·재무안전성을 계산한 진짜 퀄리티 전략이 아니라 OHLCV proxy입니다.",),
        "quality_trend_hold 네이티브 프로필이지만 이름에 proxy를 명시합니다.",
    ),
    _Archetype(
        "volatility-breakout",
        "breakout",
        "volatility_breakout_hold",
        "변동성 제한 신고가 돌파",
        "장기 고점 부근에 있으면서 거래량과 변동성 조건을 통과한 종목을 보유합니다.",
        "buy=P>=0.96*High_L and Volume/AvgVolume>=0.85 and volatility<=0.32 and R_L/2>=0",
        "가격 채널 돌파에 과도한 변동성과 약한 거래량을 거르는 조건을 추가했습니다.",
        "거짓 돌파를 줄이고 상승 추세의 지속 가능성을 확인하기 위해 사용합니다.",
        126,
        (63, 252),
        0.0,
        (0.0, 0.20),
        ("돌파", "breakout", "신고가", "변동성", "volatility"),
        ("aqr_trend_following", "moreira_muir_volatility"),
        ("급등 직후 갭 하락과 체결 슬리피지에 취약합니다.",),
        "현재 OHLCV 엔진의 volatility_breakout_hold 프로필을 사용합니다.",
    ),
    _Archetype(
        "rolling-sharpe-momentum",
        "risk_adjusted",
        "rolling_sharpe_momentum",
        "롤링 Sharpe 모멘텀",
        "최근 평균수익을 변동성으로 나눈 위험 대비 추세가 양수인 종목을 고릅니다.",
        "Sharpe_L=mean(r_L)/std(r_L); buy=Sharpe_L>=q/10 and P>=SMA_L/2 and R_L>0",
        "Sharpe 비율을 횡단면 점수와 진입 필터로 사용하도록 단순화했습니다.",
        "수익률만 높은 고변동 종목보다 위험 효율이 좋은 종목을 찾기 위해 사용합니다.",
        126,
        (21, 252),
        0.50,
        (0.0, 3.0),
        ("샤프", "sharpe", "위험조정", "risk adjusted", "모멘텀"),
        ("sharpe_ratio", "moreira_muir_volatility"),
        ("짧은 표본의 Sharpe는 추정오차가 큽니다.",),
        "현재 OHLCV 엔진의 rolling_sharpe_momentum 프로필을 사용합니다.",
    ),
    _Archetype(
        "dual-sma-trend",
        "trend",
        "dual_sma_trend",
        "단·중·장기 이동평균 정렬",
        "짧은 평균이 중간 평균보다 높고 가격도 짧은 평균 위일 때 상승 정렬로 봅니다.",
        "buy=SMA_L/4>SMA_L/2>0.98*SMA_L and P>=SMA_L/4; sell=SMA_L/4<SMA_L/2",
        "하나의 기준기간 L에서 1/4·1/2·전체 창을 사전 계산합니다.",
        "일시적 하루 급등보다 여러 시간축에서 이어진 추세를 확인하기 위해 사용합니다.",
        200,
        (60, 252),
        0.0,
        (0.0, 0.10),
        ("이동평균", "sma", "추세", "trend", "정배열"),
        ("faber_tactical", "aqr_trend_following"),
        ("방향 없는 횡보장에서는 신호가 자주 뒤집힐 수 있습니다.",),
        "현재 OHLCV 엔진의 dual_sma_trend 프로필을 사용합니다.",
    ),
    _Archetype(
        "low-vol-momentum",
        "defensive",
        "low_vol_momentum",
        "저변동 모멘텀",
        "상승 추세 종목 중 가격 범위 변동성이 낮은 종목을 우선합니다.",
        "score=3*R_L+2*R_L/2-1.5*volatility; buy=R_L>=q and volatility<=0.28",
        "모멘텀과 저위험 효과를 한 점수 안에서 결합한 장기 전용 근사입니다.",
        "방어 성향 사용자가 큰 흔들림을 줄이면서 추세에 참여하도록 사용합니다.",
        126,
        (63, 252),
        0.05,
        (0.0, 0.30),
        ("저변동", "low vol", "방어", "모멘텀", "low risk"),
        ("betting_against_beta", "moreira_muir_volatility", "french_momentum"),
        ("낮은 가격 범위 변동성은 낮은 시장 beta와 동일하지 않습니다.",),
        "현재 OHLCV 엔진의 low_vol_momentum 프로필을 사용합니다.",
    ),
    _Archetype(
        "breakout-volume",
        "breakout",
        "breakout_volume",
        "거래량 확인 가격 돌파",
        "직전 고점 돌파가 평균보다 많은 거래량을 동반할 때 진입합니다.",
        "buy=P>=0.995*High_L and Volume/AvgVolume_L>=q and R_L>=0; sell=P<SMA_L/4",
        "가격 모멘텀을 거래량 상태와 함께 분류한 연구를 실행 가능한 규칙으로 옮겼습니다.",
        "거래 참여가 약한 일시적 돌파를 걸러내기 위해 사용합니다.",
        63,
        (20, 252),
        1.20,
        (0.80, 3.00),
        ("거래량", "volume", "돌파", "breakout", "신고가"),
        ("lee_swaminathan_volume", "aqr_trend_following"),
        ("거래량 데이터의 수정·장외거래 포함 범위에 민감합니다.",),
        "현재 OHLCV 엔진의 breakout_volume 프로필을 사용합니다.",
    ),
    _Archetype(
        "rsi-trend-rebound",
        "mean_reversion",
        "rsi_trend_rebound",
        "RSI 추세 눌림 반등",
        "상승 추세 안에서 RSI가 과열되지 않은 눌림 뒤 가격 반등을 찾습니다.",
        "buy=P>=SMA_L/2 and R_L>=0 and 35<=RSI14<=62 and P>=P[t-1]; sell=RSI14>=72",
        "Wilder RSI를 단독 역추세 신호가 아니라 추세 확인 뒤 진입 타이밍으로 사용합니다.",
        "강한 하락 추세의 값싼 착시를 줄인 눌림목 후보를 찾기 위해 사용합니다.",
        63,
        (20, 200),
        0.0,
        (0.0, 1.0),
        ("rsi", "눌림목", "pullback", "반등", "rebound"),
        ("wilder_rsi", "aqr_trend_following"),
        ("RSI 경계 35·62·72는 제품 사전값이며 보편적 최적값이 아닙니다.",),
        "현재 OHLCV 엔진의 rsi_trend_rebound 프로필을 사용합니다.",
    ),
    _Archetype(
        "mean-reversion-band",
        "mean_reversion",
        "mean_reversion_band",
        "이동평균 이격 평균회귀",
        "가격이 이동평균에서 일정 비율 아래로 벗어나고 RSI도 낮을 때 되돌림을 노립니다.",
        "buy=P<=SMA_L*(1-q) and RSI14<=45; sell=P>=SMA_L/2 or RSI14>=60",
        "가격 이격률과 단기 오실레이터를 결합해 단순 하락 매수보다 조건을 엄격히 했습니다.",
        "짧은 기간의 과도한 매도 압력 뒤 평균 복귀를 포착하기 위해 사용합니다.",
        20,
        (5, 126),
        0.05,
        (0.01, 0.20),
        ("평균회귀", "mean reversion", "과매도", "역추세", "밴드"),
        ("french_short_reversal", "wilder_rsi"),
        ("구조적 하락 종목에서는 평균으로 돌아오지 않을 수 있습니다.",),
        "현재 OHLCV 엔진의 mean_reversion_band 프로필을 사용합니다.",
    ),
    _Archetype(
        "return-to-volatility",
        "risk_adjusted",
        "return_to_volatility",
        "수익률·변동폭 비율",
        "관찰기간 수익률을 같은 기간 고저 범위 변동성으로 나눠 효율을 비교합니다.",
        "efficiency=R_L/((High_L-Low_L)/SMA_L); buy=efficiency>=4*q and P>=SMA_L/2",
        "수익 크기를 위험 척도로 나누는 Sharpe·위험조정 모멘텀의 직관을 단순화했습니다.",
        "상승폭은 크지만 가격 경로가 지나치게 불안정한 종목을 낮게 평가하기 위해 사용합니다.",
        126,
        (21, 252),
        0.10,
        (0.0, 1.0),
        ("수익위험비", "return to volatility", "효율", "위험조정", "샤프"),
        ("sharpe_ratio", "moreira_muir_volatility", "msci_momentum"),
        ("고저 범위는 수익률 표준편차와 다른 위험 척도입니다.",),
        "현재 OHLCV 엔진의 return_to_volatility 프로필을 사용합니다.",
    ),
    _Archetype(
        "cash-preserving-trend",
        "defensive",
        "cash_preserving_trend",
        "현금 보존 추세",
        "추세·롤링 Sharpe·변동성 조건을 모두 통과할 때만 주식을 보유합니다.",
        "buy=R_L>=q and Sharpe_L>0.05 and volatility<=0.30; sell=R_L<0.01 or Sharpe_L<0",
        "추세가 불명확할 때 억지로 종목 수를 채우지 않고 현금을 허용합니다.",
        "손실 회피가 중요한 사용자에게 시장 노출을 줄이는 선택지를 제공하기 위해 사용합니다.",
        126,
        (63, 252),
        0.05,
        (0.0, 0.30),
        ("현금", "cash", "방어", "손실최소", "추세"),
        ("faber_tactical", "moreira_muir_volatility"),
        ("강한 V자 반등 초기에 재진입이 늦을 수 있습니다.",),
        "현재 OHLCV 엔진의 cash_preserving_trend 프로필을 사용합니다.",
    ),
    _Archetype(
        "fast-momentum-rotation",
        "momentum",
        "trend_leader_rotation",
        "빠른 중기 모멘텀 순환",
        "12-1 장기 순위보다 최근 중기 순위의 비중을 높여 주도주 변화를 빠르게 반영합니다.",
        "score=w_short*rank(P[t]/P[t-L/2]-1)+(1-w_short)*rank(M12-1), w_short>=0.7",
        "시계열 모멘텀의 여러 관찰기간 중 짧은 구간을 강조한 사전등록 변형입니다.",
        "짧은 투자기간을 명시한 사용자의 주도주 교체 속도를 맞추기 위해 사용합니다.",
        126,
        (63, 126),
        0.0,
        (0.0, 0.20),
        ("단기", "빠른", "fast", "모멘텀", "주도주", "회전"),
        ("aqr_time_series_momentum", "french_momentum"),
        ("빠른 교체는 거래비용과 회전율을 높입니다.",),
        "trend_leader_rotation 프로필을 단기 파라미터 범위로 제한합니다.",
    ),
    _Archetype(
        "defensive-momentum-rotation",
        "defensive",
        "risk_adjusted_momentum_rotation",
        "방어형 위험조정 모멘텀",
        "양의 모멘텀과 낮은 변동성을 모두 요구하는 보수적 주도주 순환입니다.",
        "score=dual_risk_adjusted_rank; eligible=M12-1>q and M_L/2>0 and sigma21<=0.65",
        "위험조정 모멘텀에 더 높은 양의 수익 문턱과 넓은 분산을 사전 지정합니다.",
        "하락 종목과 극단적 변동 종목을 동시에 피하려는 사용자에게 사용합니다.",
        252,
        (126, 252),
        0.05,
        (0.0, 0.30),
        ("방어", "저변동", "위험조정", "모멘텀", "손실최소"),
        ("msci_momentum", "moreira_muir_volatility", "momentum_crashes"),
        ("65% 변동성 상한은 제품 휴리스틱이며 별도 검증이 필요합니다.",),
        "risk_adjusted_momentum_rotation 프로필을 방어적 파라미터로 사용합니다.",
    ),
    _Archetype(
        "52-week-high-continuation",
        "breakout",
        "volatility_breakout_hold",
        "52주 신고가 근접 모멘텀",
        "현재 가격이 최근 1년 최고가에 가까운 종목을 상승 지속 후보로 봅니다.",
        "nearness=P/High_252; buy=nearness>=0.96 and volume_ratio>=0.85 and volatility<=0.32",
        "52주 최고가 근접도가 과거수익 모멘텀의 설명력을 보완한다는 연구를 반영했습니다.",
        "투자자가 과거 고점에 앵커링하며 가격 반영이 늦어질 가능성을 포착하기 위해 사용합니다.",
        252,
        (200, 252),
        0.0,
        (0.0, 0.10),
        ("52주", "52-week", "신고가", "high", "돌파"),
        ("george_hwang_52_week_high", "aqr_trend_following"),
        ("현재 엔진은 정확한 52주 달력 대신 최대 252거래일 창을 사용합니다.",),
        "volatility_breakout_hold 프로필의 장기 고점 조건으로 구현합니다.",
    ),
    _Archetype(
        "short-term-reversal",
        "mean_reversion",
        "mean_reversion_band",
        "1개월 단기반전",
        "최근 약 한 달의 과도한 하락 종목 중 평균에서 멀어진 종목의 반전을 노립니다.",
        "buy=P<=SMA_21*(1-q) and RSI14<=45; sell=P>=SMA_10 or RSI14>=60",
        "Kenneth French의 prior 1-1 단기반전 분류를 롱 전용 가격 밴드로 단순화했습니다.",
        "단기 유동성 충격이나 과잉반응 뒤 되돌림을 찾기 위해 사용합니다.",
        21,
        (10, 42),
        0.04,
        (0.01, 0.15),
        ("단기반전", "short reversal", "평균회귀", "1개월", "과매도"),
        ("french_short_reversal", "wilder_rsi"),
        ("공매도 없는 롱 전용 구현이므로 원 연구의 롱숏 팩터와 동일하지 않습니다.",),
        "mean_reversion_band 프로필을 1개월 범위로 제한합니다.",
    ),
    _Archetype(
        "volatility-managed-momentum",
        "risk_adjusted",
        "low_vol_momentum",
        "변동성 관리 모멘텀",
        "모멘텀 노출을 유지하되 변동성이 커지면 후보를 줄이거나 현금을 남깁니다.",
        "score=3*R_L+2*R_L/2-1.5*volatility; exposure only if volatility<=0.28",
        "고변동 시 팩터 노출을 줄인 Moreira-Muir의 직관을 롱 전용 선별로 옮겼습니다.",
        "위기 시 기대수익 증가보다 변동성 증가가 더 클 수 있어 위험 예산을 줄이기 위해 사용합니다.",
        126,
        (63, 252),
        0.03,
        (0.0, 0.25),
        ("변동성관리", "volatility managed", "위험예산", "저변동", "모멘텀"),
        ("moreira_muir_volatility", "french_momentum"),
        ("원 논문은 포트폴리오 노출 스케일링이며 현재 구현은 종목 필터 근사입니다.",),
        "low_vol_momentum 프로필로 구현하되 원 연구와의 차이를 명시합니다.",
    ),
)


def _bounded_int(value: float, limits: tuple[int, int]) -> int:
    return max(limits[0], min(limits[1], int(round(value))))


def _bounded_float(value: float, limits: tuple[float, float]) -> float:
    return round(max(limits[0], min(limits[1], float(value))), 6)


def _parameter_schema(archetype: _Archetype) -> dict[str, BlueprintParameterRule]:
    return {
        "lookback": BlueprintParameterRule(
            minimum=archetype.lookback_range[0],
            maximum=archetype.lookback_range[1],
            unit="trading_days",
            derivation="신호 산식이 요구하는 최소 이력과 사용자 투자기간 사이에서 결정합니다.",
        ),
        "threshold": BlueprintParameterRule(
            minimum=archetype.threshold_range[0],
            maximum=archetype.threshold_range[1],
            unit="profile_specific",
            derivation="원형 산식의 진입 문턱이며 수익률을 본 뒤 범위를 확장하지 않습니다.",
        ),
        "max_positions": BlueprintParameterRule(
            minimum=1,
            maximum=1000,
            unit="stocks",
            derivation="사용자가 말한 종목 수를 우선하고 없으면 위험성향 기본값을 사용합니다.",
        ),
        "rebalance_interval_days": BlueprintParameterRule(
            minimum=5,
            maximum=63,
            unit="trading_days",
            derivation="단기 10일·중기 21일·장기 42일 규칙에서 사용자 표현으로 결정합니다.",
        ),
        "stop_loss_pct": BlueprintParameterRule(
            minimum=0.01,
            maximum=1.0,
            unit="fraction",
            derivation="공격형 25%·균형형 20%·방어형 12% 사전 위험예산을 사용합니다.",
        ),
        "take_profit_pct": BlueprintParameterRule(
            minimum=0.01,
            maximum=10.0,
            unit="fraction",
            derivation="추세 전략은 큰 승자를 자르지 않도록 10.0을 사실상 비활성값으로 씁니다.",
        ),
        "trailing_stop_pct": BlueprintParameterRule(
            minimum=0.01,
            maximum=0.75,
            unit="fraction",
            derivation="공격형 30%·균형형 25%·방어형 15% 사전 위험예산을 사용합니다.",
        ),
    }


def _build_catalog() -> tuple[StrategyBlueprintTemplate, ...]:
    templates: list[StrategyBlueprintTemplate] = []
    for archetype in _ARCHETYPES:
        for preset in _PRESETS:
            lookback = _bounded_int(
                archetype.base_lookback * preset.lookback_multiplier,
                archetype.lookback_range,
            )
            threshold = _bounded_float(
                archetype.base_threshold * preset.threshold_multiplier,
                archetype.threshold_range,
            )
            parameters = BlueprintParameters(
                lookback=lookback,
                threshold=threshold,
                max_positions=preset.max_positions,
                rebalance_interval_days=preset.rebalance_days,
                stop_loss_pct=preset.stop_loss_pct,
                take_profit_pct=10.0,
                trailing_stop_pct=preset.trailing_stop_pct,
            )
            templates.append(
                StrategyBlueprintTemplate(
                    catalog_id=f"qb-v1-{archetype.archetype_id}-{preset.preset_id}",
                    archetype_id=archetype.archetype_id,
                    preset_id=preset.preset_id,
                    family=archetype.family,
                    profile=archetype.profile,
                    title=f"{archetype.title} · {preset.label}",
                    plain_explanation=archetype.plain_explanation,
                    formula=archetype.formula,
                    derivation=archetype.derivation,
                    why_used=archetype.why_used,
                    risk_style=preset.risk_style,
                    investment_horizon=preset.horizon,
                    default_parameters=parameters,
                    parameter_schema=_parameter_schema(archetype),
                    tags=list(archetype.tags),
                    required_data=list(archetype.required_data),
                    source_refs=[SOURCE_REGISTRY[key] for key in archetype.source_keys],
                    caveats=[
                        *archetype.caveats,
                        "연구 근거와 과거 백테스트는 미래 수익을 보장하지 않습니다.",
                    ],
                    implementation_notes=archetype.implementation_notes,
                )
            )
    return tuple(templates)


STRATEGY_BLUEPRINT_CATALOG = _build_catalog()


def strategy_blueprint_catalog() -> tuple[StrategyBlueprintTemplate, ...]:
    """Return the immutable, reviewable catalog rather than mutable database rows."""

    return STRATEGY_BLUEPRINT_CATALOG


def strategy_blueprint_catalog_fingerprint() -> str:
    payload = [item.model_dump(mode="json") for item in STRATEGY_BLUEPRINT_CATALOG]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def strategy_blueprint_catalog_summary() -> dict[str, object]:
    return {
        "version": CATALOG_VERSION,
        "storage": CATALOG_STORAGE,
        "count": len(STRATEGY_BLUEPRINT_CATALOG),
        "archetype_count": len({item.archetype_id for item in STRATEGY_BLUEPRINT_CATALOG}),
        "preset_count": len({item.preset_id for item in STRATEGY_BLUEPRINT_CATALOG}),
        "families": sorted({item.family for item in STRATEGY_BLUEPRINT_CATALOG}),
        "profiles": sorted({item.profile for item in STRATEGY_BLUEPRINT_CATALOG}),
        "fingerprint": strategy_blueprint_catalog_fingerprint(),
    }


_GENERIC_MATCH_TERMS = {
    "모멘텀",
    "momentum",
    "추세",
    "trend",
    "변동성",
    "volatility",
    "위험조정",
    "risk adjusted",
    "단기",
    "중기",
    "장기",
    "빠른",
    "fast",
    "전략",
    "strategy",
    "퀀트",
    "자동",
    "추천",
}


def _normalized_text(text: str) -> str:
    return " ".join(str(text).casefold().replace("_", " ").split())


def _term_matches(text: str, tags: Sequence[str]) -> tuple[int, int]:
    generic = 0
    specialized = 0
    for raw_tag in tags:
        tag = _normalized_text(raw_tag)
        if tag and tag in text:
            if tag in _GENERIC_MATCH_TERMS:
                generic += 1
            else:
                specialized += 1
    return generic, specialized


def _preset_fit(
    item: StrategyBlueprintTemplate,
    *,
    risk_style: RiskStyle,
    horizon: InvestmentHorizon,
) -> int:
    style_score = 4 if item.risk_style == risk_style else 0
    horizon_score = 6 if item.investment_horizon == horizon else 0
    return style_score + horizon_score


def select_strategy_blueprints(
    text: str,
    *,
    risk_style: RiskStyle,
    horizon: InvestmentHorizon,
    profile_priority: Sequence[StructuredProfile] = (),
    limit: int = 3,
) -> list[StrategyBlueprintTemplate]:
    """Select before backtest using intent only, with one best preset per archetype."""

    if limit <= 0:
        return []
    normalized = _normalized_text(text)
    best_by_archetype: dict[str, StrategyBlueprintTemplate] = {}
    for item in STRATEGY_BLUEPRINT_CATALOG:
        current = best_by_archetype.get(item.archetype_id)
        if current is None or (
            _preset_fit(item, risk_style=risk_style, horizon=horizon),
            item.catalog_id,
        ) > (
            _preset_fit(current, risk_style=risk_style, horizon=horizon),
            current.catalog_id,
        ):
            best_by_archetype[item.archetype_id] = item

    candidates = list(best_by_archetype.values())
    match_counts = {item.catalog_id: _term_matches(normalized, item.tags) for item in candidates}
    has_specialized_request = any(specialized > 0 for _, specialized in match_counts.values())
    priority_index = {profile: index for index, profile in enumerate(profile_priority)}

    def rank(item: StrategyBlueprintTemplate) -> tuple[int, int, int, int, str]:
        generic, specialized = match_counts[item.catalog_id]
        priority = len(profile_priority) - priority_index.get(item.profile, len(profile_priority))
        if has_specialized_request:
            primary = specialized * 100 + generic * 5
            secondary = priority
        else:
            primary = priority * 100
            secondary = generic
        return (
            primary,
            secondary,
            _preset_fit(item, risk_style=risk_style, horizon=horizon),
            -len(item.caveats),
            item.catalog_id,
        )

    ranked = sorted(candidates, key=rank, reverse=True)
    selected: list[StrategyBlueprintTemplate] = []
    used_profiles: set[StructuredProfile] = set()
    for item in ranked:
        if item.profile in used_profiles:
            continue
        selected.append(item)
        used_profiles.add(item.profile)
        if len(selected) >= limit:
            break
    return selected


def customize_blueprint_parameters(
    template: StrategyBlueprintTemplate,
    *,
    max_positions: int,
    rebalance_interval_days: int,
    stop_loss_pct: float,
    take_profit_pct: float,
    trailing_stop_pct: float,
    preferred_lookback: int | None = None,
) -> BlueprintParameters:
    """Apply explicit user controls while respecting the blueprint's declared bounds."""

    def bounded(name: str, value: float) -> float:
        rule = template.parameter_schema[name]
        return max(rule.minimum, min(rule.maximum, float(value)))

    lookback = int(preferred_lookback or template.default_parameters.lookback)
    lookback = int(bounded("lookback", lookback))
    return BlueprintParameters(
        lookback=lookback,
        threshold=template.default_parameters.threshold,
        max_positions=int(bounded("max_positions", max_positions)),
        rebalance_interval_days=int(bounded("rebalance_interval_days", rebalance_interval_days)),
        stop_loss_pct=bounded("stop_loss_pct", stop_loss_pct),
        take_profit_pct=bounded("take_profit_pct", take_profit_pct),
        trailing_stop_pct=bounded("trailing_stop_pct", trailing_stop_pct),
    )


def catalog_selection_terms(
    text: str, templates: Sequence[StrategyBlueprintTemplate]
) -> dict[str, list[str]]:
    normalized = _normalized_text(text)
    return {
        item.catalog_id: [tag for tag in item.tags if _normalized_text(tag) in normalized]
        for item in templates
    }
