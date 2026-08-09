"""Versioned catalog of independently executable quant strategies.

Catalog v1 counted five parameter presets for each of twenty formulas as one hundred
strategies.  V2 has one row per distinct execution signature.  User controls still
customize bounded risk and cadence parameters, but never inflate the strategy count.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.schemas import Condition, StructuredProfile
from ai_graph.strategy_blueprint_rules import (
    INDICATORS,
    SOURCE_REGISTRY,
    STRATEGY_RULES,
    InvestmentHorizon,
    RiskStyle,
    StrategyRuleDefinition,
)


CATALOG_VERSION = "quant-blueprints.v2"
CATALOG_STORAGE = "versioned_python_catalog"


class BlueprintParameters(BaseModel):
    """Executable defaults; explicit user controls may change only bounded values."""

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


class BlueprintIndicatorExplanation(BaseModel):
    """Why one quant indicator exists and how its number is produced."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    plain_explanation: str = Field(min_length=1)
    formula: str = Field(min_length=1)
    derivation: str = Field(min_length=1)
    why_used: str = Field(min_length=1)
    caution: str = (
        "단일 지표만으로 매매하지 않으며 거래비용·시장 국면과 다른 위험조건을 함께 봐야 합니다."
    )
    source_refs: list[str] = Field(min_length=1)


class StrategyBlueprintTemplate(BaseModel):
    """One source-backed formula and the exact IR fragments the engine executes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: str = Field(pattern=r"^qb-v2-[a-z0-9-]+$")
    catalog_version: str = CATALOG_VERSION
    archetype_id: str = Field(min_length=1)
    # Retained for API compatibility.  It is always canonical and is not counted as a
    # strategy or materialized into additional rows.
    preset_id: Literal["canonical"] = "canonical"
    family: str = Field(min_length=1)
    profile: StructuredProfile = "compiled_conditions"
    title: str = Field(min_length=1)
    plain_explanation: str = Field(min_length=1)
    formula: str = Field(min_length=1)
    derivation: str = Field(min_length=1)
    why_used: str = Field(min_length=1)
    entry_conditions: list[Condition] = Field(min_length=1)
    exit_conditions: list[Condition] = Field(min_length=1)
    ranking_metric: str = Field(min_length=1)
    ranking_direction: Literal["desc", "asc"] = "desc"
    execution_mode: Literal["event_driven", "scheduled_rotation"] = "event_driven"
    execution_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    default_priority: int = Field(ge=0, le=100)
    risk_style: RiskStyle
    investment_horizon: InvestmentHorizon
    default_parameters: BlueprintParameters
    parameter_schema: dict[str, BlueprintParameterRule] = Field(min_length=7)
    tags: list[str] = Field(min_length=1)
    required_data: list[str] = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    indicator_explanations: list[BlueprintIndicatorExplanation] = Field(min_length=1)
    caveats: list[str] = Field(min_length=1)
    implementation_notes: str = Field(min_length=1)
    native_execution: bool = True
    independent_strategy: bool = True


def _execution_signature(rule: StrategyRuleDefinition) -> str:
    payload = {
        "entry": [item.model_dump(mode="json") for item in rule.entry_conditions],
        "exit": [item.model_dump(mode="json") for item in rule.exit_conditions],
        "ranking_metric": rule.ranking_metric,
        "ranking_direction": rule.ranking_direction,
        "execution_mode": rule.execution_mode,
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _parameter_schema(rule: StrategyRuleDefinition) -> dict[str, BlueprintParameterRule]:
    # Formula windows are fixed in V2.  That makes a SMA(20/50) crossover one strategy,
    # not dozens of lookback clones.  Risk controls remain explicitly customizable.
    return {
        "lookback": BlueprintParameterRule(
            minimum=rule.lookback,
            maximum=rule.lookback,
            unit="trading_days",
            derivation="전략 산식의 가장 긴 지표 창과 평활 준비기간에서 고정했습니다.",
            user_overridable=False,
        ),
        "threshold": BlueprintParameterRule(
            minimum=rule.threshold,
            maximum=rule.threshold,
            unit="formula_specific",
            derivation="전략 정의 안의 사전등록 문턱이며 성과를 본 뒤 조정하지 않습니다.",
            user_overridable=False,
        ),
        "max_positions": BlueprintParameterRule(
            minimum=1,
            maximum=1000,
            unit="stocks",
            derivation="사용자가 말한 종목 수를 우선하고 입력이 없으면 위험성향 기본값을 씁니다.",
        ),
        "rebalance_interval_days": BlueprintParameterRule(
            minimum=5,
            maximum=63,
            unit="trading_days",
            derivation="단기 10일·중기 21일·장기 42일을 기본으로 사용자 기간 표현에 맞춥니다.",
        ),
        "stop_loss_pct": BlueprintParameterRule(
            minimum=0.01,
            maximum=1.0,
            unit="fraction",
            derivation="공격형 25%·균형형 20%·방어형 12%의 사전 위험예산에서 시작합니다.",
        ),
        "take_profit_pct": BlueprintParameterRule(
            minimum=0.01,
            maximum=10.0,
            unit="fraction",
            derivation="추세의 큰 승자를 자르지 않도록 기본 10.0을 사실상 비활성 상한으로 씁니다.",
        ),
        "trailing_stop_pct": BlueprintParameterRule(
            minimum=0.01,
            maximum=0.75,
            unit="fraction",
            derivation="공격형 30%·균형형 25%·방어형 15%의 사전 추적 위험예산에서 시작합니다.",
        ),
    }


def _default_parameters(rule: StrategyRuleDefinition) -> BlueprintParameters:
    by_style = {
        "aggressive": (8, 10, .25, .30),
        "balanced": (10, 21, .20, .25),
        "defensive": (15, 21, .12, .15),
    }
    positions, rebalance, stop, trailing = by_style[rule.risk_style]
    return BlueprintParameters(
        lookback=rule.lookback,
        threshold=rule.threshold,
        max_positions=positions,
        rebalance_interval_days=rebalance,
        stop_loss_pct=stop,
        take_profit_pct=10.0,
        trailing_stop_pct=trailing,
    )


def _indicator_explanations(rule: StrategyRuleDefinition) -> list[BlueprintIndicatorExplanation]:
    output: list[BlueprintIndicatorExplanation] = []
    for key in rule.indicator_keys:
        item = INDICATORS[key]
        output.append(
            BlueprintIndicatorExplanation(
                key=item.key,
                label=item.label,
                plain_explanation=item.plain_explanation,
                formula=item.formula,
                derivation=item.derivation,
                why_used=item.why_used,
                source_refs=[SOURCE_REGISTRY[source] for source in item.source_keys],
            )
        )
    return output


def _build_catalog() -> tuple[StrategyBlueprintTemplate, ...]:
    templates = tuple(
        StrategyBlueprintTemplate(
            catalog_id=f"qb-v2-{rule.strategy_id}",
            archetype_id=rule.strategy_id,
            family=rule.family,
            title=rule.title,
            plain_explanation=rule.plain_explanation,
            formula=rule.formula,
            derivation=rule.derivation,
            why_used=rule.why_used,
            entry_conditions=list(rule.entry_conditions),
            exit_conditions=list(rule.exit_conditions),
            ranking_metric=rule.ranking_metric,
            ranking_direction=rule.ranking_direction,
            execution_mode=rule.execution_mode,
            execution_signature=_execution_signature(rule),
            default_priority=rule.default_priority,
            risk_style=rule.risk_style,
            investment_horizon=rule.horizon,
            default_parameters=_default_parameters(rule),
            parameter_schema=_parameter_schema(rule),
            tags=list(rule.tags),
            required_data=["adjusted_ohlcv_daily"],
            source_refs=[SOURCE_REGISTRY[key] for key in rule.source_keys],
            indicator_explanations=_indicator_explanations(rule),
            caveats=[
                rule.caveat,
                "논문·공식 지표 정의와 과거 백테스트는 미래 수익을 보장하지 않습니다.",
            ],
            implementation_notes=(
                "조정 OHLCV의 당일 종가까지로 신호를 계산하고 주문은 다음 거래 가능 시가에 "
                "체결합니다. 이 정의의 entry/exit/ranking 조건이 StrategyIR로 그대로 전달됩니다."
            ),
        )
        for rule in STRATEGY_RULES
    )
    signatures = {item.execution_signature for item in templates}
    if len(signatures) != len(templates):
        raise RuntimeError("catalog contains duplicate execution formulas")
    if len(templates) < 50:
        raise RuntimeError("catalog must contain at least 50 independent strategies")
    return templates


STRATEGY_BLUEPRINT_CATALOG = _build_catalog()


def strategy_blueprint_catalog() -> tuple[StrategyBlueprintTemplate, ...]:
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
        "independent_strategy_count": len(STRATEGY_BLUEPRINT_CATALOG),
        "archetype_count": len(STRATEGY_BLUEPRINT_CATALOG),
        "preset_count": 1,
        "parameter_presets_counted_as_strategies": False,
        "families": sorted({item.family for item in STRATEGY_BLUEPRINT_CATALOG}),
        "profiles": sorted({item.profile for item in STRATEGY_BLUEPRINT_CATALOG}),
        "fingerprint": strategy_blueprint_catalog_fingerprint(),
    }


_GENERIC_MATCH_TERMS = {
    "모멘텀", "momentum", "추세", "trend", "변동성", "volatility", "단기", "중기",
    "장기", "빠른", "fast", "전략", "strategy", "퀀트", "자동", "추천", "수익",
}


def _normalized_text(text: str) -> str:
    return " ".join(str(text).casefold().replace("_", " ").split())


def _term_matches(text: str, tags: Sequence[str]) -> tuple[int, int]:
    generic = specialized = 0
    for raw_tag in tags:
        tag = _normalized_text(raw_tag)
        if tag and tag in text:
            if tag in _GENERIC_MATCH_TERMS:
                generic += 1
            else:
                specialized += 1
    return generic, specialized


def _intent_fit(
    item: StrategyBlueprintTemplate,
    *,
    risk_style: RiskStyle,
    horizon: InvestmentHorizon,
) -> int:
    return (4 if item.risk_style == risk_style else 0) + (
        6 if item.investment_horizon == horizon else 0
    )


def select_strategy_blueprints(
    text: str,
    *,
    risk_style: RiskStyle,
    horizon: InvestmentHorizon,
    profile_priority: Sequence[StructuredProfile] = (),
    limit: int = 3,
) -> list[StrategyBlueprintTemplate]:
    """Select distinct formulas from intent only, before any return is inspected."""

    del profile_priority  # V1 profile menus must not collapse V2's compiled formulas.
    if limit <= 0:
        return []
    normalized = _normalized_text(text)
    matches = {
        item.catalog_id: _term_matches(normalized, item.tags)
        for item in STRATEGY_BLUEPRINT_CATALOG
    }
    specialized_request = any(specialized for _, specialized in matches.values())

    def rank(item: StrategyBlueprintTemplate) -> tuple[int, int, int, int, str]:
        generic, specialized = matches[item.catalog_id]
        fit = _intent_fit(item, risk_style=risk_style, horizon=horizon)
        if specialized_request:
            intent = specialized * 10_000 + fit * 100 + generic * 5
            prior = item.default_priority
        else:
            intent = fit * 1_000 + item.default_priority * 10
            prior = generic
        return (
            intent,
            fit,
            prior,
            -len(item.caveats),
            item.catalog_id,
        )

    return sorted(STRATEGY_BLUEPRINT_CATALOG, key=rank, reverse=True)[:limit]


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
    """Apply user risk controls without mutating or duplicating the formula itself."""

    def bounded(name: str, value: float) -> float:
        rule = template.parameter_schema[name]
        return max(rule.minimum, min(rule.maximum, float(value)))

    lookback = template.default_parameters.lookback
    if preferred_lookback is not None and template.parameter_schema["lookback"].user_overridable:
        lookback = int(preferred_lookback)
    return BlueprintParameters(
        lookback=int(bounded("lookback", lookback)),
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
