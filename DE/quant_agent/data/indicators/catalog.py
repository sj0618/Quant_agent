"""TA-Lib indicator catalog grouped into the product's five categories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quant_agent.data.config import DEFAULT_TA_TRANSFORM_VERSION


@dataclass(frozen=True)
class IndicatorDefinition:
    category: str
    name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    warmup_days: int = 0
    output_schema: dict[str, Any] = field(default_factory=dict)
    transform_version: str = DEFAULT_TA_TRANSFORM_VERSION

    def to_repository_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "parameters": self.parameters,
            "warmup_days": self.warmup_days,
            "output_schema": self.output_schema,
            "transform_version": self.transform_version,
        }


OVERLAP_STUDIES = [
    "BBANDS",
    "DEMA",
    "EMA",
    "HT_TRENDLINE",
    "KAMA",
    "MA",
    "MAMA",
    "MAVP",
    "MIDPOINT",
    "MIDPRICE",
    "SAR",
    "SAREXT",
    "SMA",
    "T3",
    "TEMA",
    "TRIMA",
    "WMA",
]
PRICE_TRANSFORM = ["AVGPRICE", "MEDPRICE", "TYPPRICE", "WCLPRICE"]
CYCLE_INDICATORS = ["HT_DCPERIOD", "HT_DCPHASE", "HT_PHASOR", "HT_SINE", "HT_TRENDMODE"]
STATISTIC_FUNCTIONS = ["BETA", "CORREL", "LINEARREG", "LINEARREG_ANGLE", "LINEARREG_INTERCEPT", "LINEARREG_SLOPE", "STDDEV", "TSF", "VAR"]
MATH_TRANSFORM = ["ACOS", "ASIN", "ATAN", "CEIL", "COS", "COSH", "EXP", "FLOOR", "LN", "LOG10", "SIN", "SINH", "SQRT", "TAN", "TANH"]
TREND_MATH_OPERATORS = ["MULT", "MAXINDEX", "MININDEX", "MINMAX", "MINMAXINDEX", "SUM"]

MOMENTUM_INDICATORS = [
    "ADX",
    "ADXR",
    "APO",
    "AROON",
    "AROONOSC",
    "BOP",
    "CCI",
    "CMO",
    "DX",
    "MACD",
    "MACDEXT",
    "MACDFIX",
    "MFI",
    "MINUS_DI",
    "MINUS_DM",
    "MOM",
    "PLUS_DI",
    "PLUS_DM",
    "PPO",
    "ROC",
    "ROCP",
    "ROCR",
    "ROCR100",
    "RSI",
    "STOCH",
    "STOCHF",
    "STOCHRSI",
    "TRIX",
    "ULTOSC",
    "WILLR",
]
MOMENTUM_MATH_OPERATORS = ["ADD", "DIV", "MAX", "MIN", "SUB"]

VOLATILITY_INDICATORS = ["ATR", "NATR", "TRANGE"]
VOLUME_INDICATORS = ["AD", "ADOSC", "OBV"]

PATTERN_INDICATORS = [
    "CDL2CROWS",
    "CDL3BLACKCROWS",
    "CDL3INSIDE",
    "CDL3LINESTRIKE",
    "CDL3OUTSIDE",
    "CDL3STARSINSOUTH",
    "CDL3WHITESOLDIERS",
    "CDLABANDONEDBABY",
    "CDLADVANCEBLOCK",
    "CDLBELTHOLD",
    "CDLBREAKAWAY",
    "CDLCLOSINGMARUBOZU",
    "CDLCONCEALBABYSWALL",
    "CDLCOUNTERATTACK",
    "CDLDARKCLOUDCOVER",
    "CDLDOJI",
    "CDLDOJISTAR",
    "CDLDRAGONFLYDOJI",
    "CDLENGULFING",
    "CDLEVENINGDOJISTAR",
    "CDLEVENINGSTAR",
    "CDLGAPSIDESIDEWHITE",
    "CDLGRAVESTONEDOJI",
    "CDLHAMMER",
    "CDLHANGINGMAN",
    "CDLHARAMI",
    "CDLHARAMICROSS",
    "CDLHIGHWAVE",
    "CDLHIKKAKE",
    "CDLHIKKAKEMOD",
    "CDLHOMINGPIGEON",
    "CDLIDENTICAL3CROWS",
    "CDLINNECK",
    "CDLINVERTEDHAMMER",
    "CDLKICKING",
    "CDLKICKINGBYLENGTH",
    "CDLLADDERBOTTOM",
    "CDLLONGLEGGEDDOJI",
    "CDLLONGLINE",
    "CDLMARUBOZU",
    "CDLMATCHINGLOW",
    "CDLMATHOLD",
    "CDLMORNINGDOJISTAR",
    "CDLMORNINGSTAR",
    "CDLONNECK",
    "CDLPIERCING",
    "CDLRICKSHAWMAN",
    "CDLRISEFALL3METHODS",
    "CDLSEPARATINGLINES",
    "CDLSHOOTINGSTAR",
    "CDLSHORTLINE",
    "CDLSPINNINGTOP",
    "CDLSTALLEDPATTERN",
    "CDLSTICKSANDWICH",
    "CDLTAKURI",
    "CDLTASUKIGAP",
    "CDLTHRUSTING",
    "CDLTRISTAR",
    "CDLUNIQUE3RIVER",
    "CDLUPSIDEGAP2CROWS",
    "CDLXSIDEGAP3METHODS",
]


def _build_definitions(category: str, names: list[str], warmup_days: int) -> list[IndicatorDefinition]:
    return [
        IndicatorDefinition(
            category=category,
            name=name,
            warmup_days=warmup_days,
            output_schema={"storage": "values_jsonb", "talib_function": name},
        )
        for name in names
    ]


INDICATOR_CATALOG = (
    _build_definitions(
        "Trend",
        OVERLAP_STUDIES + PRICE_TRANSFORM + CYCLE_INDICATORS + STATISTIC_FUNCTIONS + MATH_TRANSFORM + TREND_MATH_OPERATORS,
        252,
    )
    + _build_definitions("Momentum", MOMENTUM_INDICATORS + MOMENTUM_MATH_OPERATORS, 252)
    + _build_definitions("Volatility", VOLATILITY_INDICATORS, 30)
    + _build_definitions("Volume", VOLUME_INDICATORS, 30)
    + _build_definitions("Pattern", PATTERN_INDICATORS, 5)
)

CATALOG_COUNTS = {
    "Trend": 56,
    "Momentum": 35,
    "Volatility": 3,
    "Volume": 3,
    "Pattern": 61,
}


def validate_catalog_counts() -> None:
    actual = {category: 0 for category in CATALOG_COUNTS}
    for item in INDICATOR_CATALOG:
        actual[item.category] = actual.get(item.category, 0) + 1
    if actual != CATALOG_COUNTS:
        raise ValueError(f"TA catalog count mismatch: expected={CATALOG_COUNTS}, actual={actual}")
