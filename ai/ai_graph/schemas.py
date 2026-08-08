from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "ai-mvp.v1"




SemanticParseStatus = Literal["ready", "needs_clarification", "failed"]
SourceType = Literal["internal_db", "krx", "dart", "aoai_web_search", "analyst_evidence", "none"]
FreshnessStatus = Literal["fresh", "stale", "unknown", "not_time_sensitive"]
FailureCategory = Literal[
    "infrastructure_failure",
    "semantic_failure",
    "data_gap",
    "clarification_failure",
    "ui_failure",
    "debug_failure",
    "unknown_failure",
]
FailureSubcause = Literal[
    "db_connect_timeout",
    "db_statement_timeout",
    "semantic_drift",
    "missing_data_policy_gap",
    "clarification_quality_gap",
    "ui_state_stale",
    "contract_shape_error",
    "debug_unavailable",
    "krx_api_error",
    "dart_api_error",
    "websearch_unavailable",
    "source_mapping_gap",
    "disclosure_mapping_gap",
    "freshness_gap",
    "external_source_rate_limited",
    "aoai_capacity_exhausted",
    "parser_low_confidence",
    "source_conflict",
    "data_required",
    # The screen ran and matched nothing, or the matched names have no price history.
    # Separate from the generic gaps above so the user is told the condition was too
    # tight rather than that something broke.
    "no_screening_matches",
    "no_price_rows",
    "outside_owner",
    "product_data_gap",
    "unknown",
]


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_id: str = Field(min_length=1)
    source_type: SourceType
    stage: str = Field(min_length=1)
    retrieved_at: datetime
    sanitized_summary: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class SemanticSlots(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicator: list[str] = Field(default_factory=list)
    threshold: list[str] = Field(default_factory=list)
    lookback: list[str] = Field(default_factory=list)
    horizon: list[str] = Field(default_factory=list)
    price_basis: list[str] = Field(default_factory=list)
    event: list[str] = Field(default_factory=list)
    action: list[str] = Field(default_factory=list)
    sector: str | None = None
    slot_evidence_refs: list[str] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    parse_status: SemanticParseStatus
    extraction_method: Literal["deterministic_rules", "json_schema_llm"] = "deterministic_rules"
    schema_validation_status: Literal["valid", "invalid"] = "valid"


class DataRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: Literal[
        "ohlcv_ta",
        "fundamentals",
        "consensus_guidance",
        "ownership_flow",
        "short_interest",
        "macro_fx_rates_commodities",
        "event",
        "disclosure",
        "analyst_evidence",
    ]
    required: bool = True
    availability: Literal["available", "derivable", "partial", "unavailable", "outside_owner", "not_required"]
    owner: Literal["ai_graph", "data_source_config", "product_data_gap", "outside_owner", "unknown"]
    preferred_source: SourceType
    fallback_sources: list[SourceType] = Field(default_factory=list)
    freshness_requirement: Literal[
        "same_trading_day",
        "latest_filing",
        "recent_news",
        "report_period",
        "as_of_date",
        "not_time_sensitive",
    ]
    source_confidence_floor: float = Field(default=0.0, ge=0.0, le=1.0)
    proxy_allowed: bool = False
    proxy_used: bool = False
    proxy_disclosure: dict[str, str] | None = None
    evidence_ref: str = Field(min_length=1)


class SourceUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    query: str = Field(min_length=1)
    retrieved_at: datetime
    source_refs: list[str] = Field(default_factory=list)
    freshness_status: FreshnessStatus
    confidence: float = Field(ge=0.0, le=1.0)
    fallback_used: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class FailureDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: FailureCategory
    subcause: FailureSubcause
    failure_stage: str = Field(min_length=1)
    owner: Literal["ai_graph", "data_source_config", "fe_state", "outside_owner", "product_data_gap", "unknown"]
    retryable: bool
    safe_message: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


class LogicMode(str, Enum):
    ALL = "all"
    ANY = "any"


class ConditionOperator(str, Enum):
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    EQ = "eq"
    NE = "ne"
    BETWEEN = "between"
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: str = Field(min_length=1)
    operator: ConditionOperator
    right: float | str | list[float]
    description: str | None = None

    # --- Optional structure so one condition list can express the strategies that used
    # to be encoded twice (SQL for today's screen, Python for the backtest) and drift
    # apart. All default to None, so a plain comparison is unchanged; a compiler that
    # does not understand a field can fall back to raw SQL for that condition.
    #
    # window: evaluate `left` over a rolling window of this many trading days
    # (e.g. 52-week high -> left="high", window=252, aggregate="max").
    window: int | None = Field(default=None, gt=0)
    # aggregate: how to reduce `left` (and a metric `right`) across the window.
    aggregate: Literal["max", "min", "avg", "sum", "last"] | None = None
    # scale: multiply the right-hand side, so "volume >= 1.5x its 20-day average" is
    # right="volume", window=20, aggregate="avg", scale=1.5 - no separate metric needed.
    scale: float | None = None
    # consecutive: the condition must hold this many periods in a row
    # (e.g. operating income up YoY for 4 quarters -> consecutive=4).
    consecutive: int | None = Field(default=None, gt=0)
    # universe_rank: cross-sectional selection instead of an absolute cut, as a top
    # percentile of the universe on `left` (e.g. revenue growth in the top 20% -> 0.2).
    universe_rank_pct: float | None = Field(default=None, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_right_shape(self) -> "Condition":
        if self.operator == ConditionOperator.BETWEEN:
            if not isinstance(self.right, list) or len(self.right) != 2:
                raise ValueError("between requires [low, high]")
            if float(self.right[0]) > float(self.right[1]):
                raise ValueError("between lower bound must be <= upper bound")
        elif self.operator in {ConditionOperator.CROSS_ABOVE, ConditionOperator.CROSS_BELOW}:
            if not isinstance(self.right, str):
                raise ValueError("cross operators require a metric name")
        elif not isinstance(self.right, (int, float)):
            # A metric name on the right is allowed once the condition compares against a
            # windowed/derived series - "close >= 252-day max of high", "operating_income
            # > its previous quarter". Absolute comparisons still require a number.
            structured = self.window is not None or self.consecutive is not None
            if not (structured and isinstance(self.right, str)):
                raise ValueError("scalar operators require a numeric right side")
        return self


class AmbiguityCode(str, Enum):
    NO_STRATEGY_INTENT = "C0_NO_STRATEGY_INTENT"
    READY = "READY"
    INPUT_AMBIGUOUS = "C1_INPUT_AMBIGUOUS"
    TERM_UNKNOWN = "C2_TERM_UNKNOWN"
    CONFLICTING = "C4_CONFLICTING"
    INFEASIBLE = "C5_INFEASIBLE"


class EnvelopeStatus(str, Enum):
    READY = "ready"
    NEED_CLARIFICATION = "need_clarification"
    REJECTED = "rejected"
    FAILED = "failed"


class Stage(str, Enum):
    INTERPRETING = "interpreting"
    CODE_GENERATION = "code_generation"
    BACKTEST = "backtest"
    DEBATE = "debate"
    FINALIZING = "finalizing"


class StageStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ScreeningMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=6, max_length=6)
    name: str = Field(min_length=1)
    market: str = Field(min_length=1)
    sector: str | None = None
    as_of_date: str = Field(min_length=1)
    close: float | None = None
    matched_rules: list[str] = Field(default_factory=list)


class StrategyCandidateCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    key_conditions: list[str] = Field(min_length=1, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str | None = None
    sector: str | None = None
    matches: list[ScreeningMatch] = Field(default_factory=list)


class ClarificationOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ClarificationPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    options: list[ClarificationOption] = Field(default_factory=list, max_length=3)
    recommended: int | None = Field(default=None, ge=0, le=2)


class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    market: str = Field(min_length=1)
    sector: str | None = None
    timeframe: str = Field(min_length=1)
    entry_conditions: list[Condition] = Field(min_length=1)
    exit_conditions: list[Condition] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    risk_constraints: dict[str, float | int | str | bool] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("strategy_id")
    @classmethod
    def normalize_strategy_id(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


class L4Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publisher: str = Field(min_length=1)
    published_at: datetime
    retrieved_at: datetime
    freshness_days: int = Field(ge=0)
    dedupe_group: str = Field(min_length=1)
    access_status: Literal["available", "fixture", "unavailable"]
    quality_note: str = Field(min_length=1)


class BacktestMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sharpe_ratio: float
    max_drawdown: float
    win_rate: float = Field(ge=0.0, le=1.0)
    total_return: float
    in_sample_sharpe: float
    out_sample_sharpe: float
    degradation: float
    # Selection-only statistics. Defaults preserve compatibility with historical
    # result payloads that predate the real hold-out split.
    in_sample_return: float = 0.0
    in_sample_max_drawdown: float = 0.0


class PublicMetricDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: float | None
    unit: str = Field(min_length=1)
    is_available: bool
    unavailable_reason: str | None = None
    plain_explanation: str = Field(min_length=1)
    why_used: str = Field(min_length=1)
    caution: str = Field(min_length=1)


class BacktestReliability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["fixture", "postgres", "unknown"] = "unknown"
    status: Literal["sufficient", "limited", "insufficient"]
    row_count: int = Field(ge=0)
    ticker_count: int = Field(ge=0)
    trading_days: int = Field(ge=0)
    history_start: str | None = None
    history_end: str | None = None
    trade_count: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BacktestBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    method: str = Field(min_length=1)
    warning: str | None = None
    total_return: float | None
    cumulative_curve: list[BacktestEquityPoint] = Field(default_factory=list)
    is_available: bool = True
    unavailable_reason: str | None = None


class BacktestEquityPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(min_length=1)
    cumulative_return: float


StructuredProfile = Literal[
    "compiled_conditions",
    "long_regime_momentum",
    "quality_trend_hold",
    "volatility_breakout_hold",
    "rolling_sharpe_momentum",
    "dual_sma_trend",
    "low_vol_momentum",
    "breakout_volume",
    "rsi_trend_rebound",
    "mean_reversion_band",
    "return_to_volatility",
    "cash_preserving_trend",
    "adaptive_trend",
]


class StrategyIR(BaseModel):
    """Canonical rule description shared by every parameter candidate."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["strategy-ir.v1"] = "strategy-ir.v1"
    strategy_id: str = Field(min_length=1)
    entry_feature: str = Field(min_length=1)
    exit_feature: str = Field(min_length=1)
    proxy_feature: str = Field(min_length=1)
    entry_conditions: list[Condition] = Field(default_factory=list)
    exit_conditions: list[Condition] = Field(default_factory=list)
    ranking: Literal["score_desc_ticker_desc", "none"] = "score_desc_ticker_desc"


class CandidateParameters(BaseModel):
    """Small bounded search surface executed by the verified signal engine."""

    model_config = ConfigDict(extra="forbid")

    profile: StructuredProfile
    lookback: int = Field(ge=3, le=252)
    threshold: float = Field(ge=-1.0, le=100.0)
    stop_loss_pct: float = Field(gt=0.0, le=1.0)
    take_profit_pct: float = Field(gt=0.0, le=10.0)
    max_positions: int = Field(gt=0, le=1000)


class CodeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    variant: Literal["A", "B"]
    code: str = Field(min_length=1)
    validation_ok: bool
    violations: list[str] = Field(default_factory=list)
    metrics: BacktestMetrics | None = None
    representation: Literal["structured", "python_fallback"] = "python_fallback"
    strategy_ir: StrategyIR | None = None
    parameters: CandidateParameters | None = None

    @model_validator(mode="after")
    def validate_representation(self) -> "CodeCandidate":
        if self.representation == "structured" and (
            self.strategy_ir is None or self.parameters is None
        ):
            raise ValueError("structured candidates require strategy_ir and parameters")
        return self


class CandidateBacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_a: StrategySpec
    candidates: list[CodeCandidate] = Field(min_length=1)
    selected_candidate: CodeCandidate
    equity_curve: list[BacktestEquityPoint]
    engine_summary: dict[str, Any] = Field(default_factory=dict)
    engine_summaries_by_candidate: dict[str, dict[str, Any]] = Field(default_factory=dict)
    objective_scores_by_candidate: dict[str, float] = Field(default_factory=dict)
    backtest_payload: dict[str, Any] = Field(default_factory=dict)
    feature_coverage: dict[str, Any] = Field(default_factory=dict)
    fallback_reasons: list[str] = Field(default_factory=list)
    execution_stats: dict[str, Any] = Field(default_factory=dict)


SignalAction = Literal["BUY", "HOLD", "DROP"]


class SignalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: SignalAction
    confidence: float = Field(ge=0.0, le=1.0)
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    judge_reason: str = Field(min_length=1)
    l4_evidence: list[L4Evidence] = Field(default_factory=list)


class RiskAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: SignalAction
    after: SignalAction
    rule: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class PortfolioRisk(BaseModel):
    """Concentration and correlation of the names the strategy trades.

    All measured from the portfolio itself - sector mix and pairwise return correlation
    - with no fixed thresholds; the fields are continuous so the risk step can scale its
    response rather than trip a hardcoded line.
    """

    model_config = ConfigDict(extra="forbid")

    name_count: int = Field(ge=0)
    sector_count: int = Field(ge=0)
    # Effective number of sectors (1/HHI of sector weights): near 1 = one sector,
    # near sector_count = evenly spread.
    effective_sectors: float = Field(ge=0.0)
    top_sector_weight: float = Field(ge=0.0, le=1.0)
    # Average pairwise correlation of daily returns; high = the names move together, so
    # holding several of them buys little diversification.
    average_correlation: float | None = None
    # 0 (fully concentrated / perfectly correlated) .. 1 (well spread / uncorrelated).
    diversification_score: float = Field(ge=0.0, le=1.0)


class RiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: SignalDecision
    adjustments: list[RiskAdjustment] = Field(default_factory=list)
    portfolio_risk: PortfolioRisk | None = None


class ReportProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    sections: list[dict[str, Any]] = Field(default_factory=list)


class ReportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_projection: ReportProjection
    email_projection: ReportProjection
    risk_adjustments: list[RiskAdjustment] = Field(default_factory=list)


class BacktestPerformance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_candidate_id: str = Field(min_length=1)
    metrics: BacktestMetrics
    equity_curve: list[BacktestEquityPoint]
    engine_summary: dict[str, Any] = Field(default_factory=dict)
    reliability: BacktestReliability | None = None
    data_quality: list[str] = Field(default_factory=list)
    benchmark: BacktestBenchmark | None = None
    metric_details: list[PublicMetricDetail] = Field(default_factory=list)


class InternalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    llm_prompts: list[str] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    backtest_artifacts: dict[str, Any] = Field(default_factory=dict)
    risk_events: list[dict[str, Any]] = Field(default_factory=list)


class RecommendationGate(BaseModel):
    """Whether the backtest validated the strategy that produced today's picks.

    The screen names "the stocks to buy today", but that recommendation is only as
    trustworthy as the strategy behind it. When the backtest of that same rule does not
    clear the objective floor, the picks are still shown - hiding them loses information -
    but flagged not-validated so the UI presents them as reference, not a call to act.
    """

    model_config = ConfigDict(extra="forbid")

    validated: bool
    reason: str = Field(min_length=1)


class RuleProvenance(BaseModel):
    """What the backtest actually evaluated, reported by the backtest itself.

    The strategy spec carries the rule that was *generated*. Nothing carried the rule
    that was *run*, and when the generated conditions could not be compiled the engine
    quietly fell back to a generic template - producing a report whose headline was
    byte-identical to one where the user's own rule had been tested. Two independent
    descriptions of one run always drift; this is the executing stage describing itself,
    so there is only one.
    """

    model_config = ConfigDict(extra="forbid")

    # "user_conditions" when the strategy's own compiled rule was traded, otherwise the
    # template profile that stood in for it.
    evaluated_rule: str = Field(min_length=1)
    substituted: bool
    requested_conditions: list[str] = Field(default_factory=list)
    # Conditions the compiler could not translate; empty when nothing was substituted.
    untranslatable_conditions: list[str] = Field(default_factory=list)
    reason: str | None = None


class UserPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1)
    message: str = Field(min_length=1)
    next_actions: list[str] = Field(default_factory=list)
    candidate_cards: list[StrategyCandidateCard] = Field(default_factory=list)
    report: ReportBundle | None = None
    performance: BacktestPerformance | None = None
    recommendation_gate: RecommendationGate | None = None
    question: str | None = None
    options: list[ClarificationOption] = Field(default_factory=list, max_length=3)
    recommended: int | None = Field(default=None, ge=0, le=2)


NewsTone = Literal["positive", "warning", "negative", "neutral", "info"]


class DailyDigestStrategyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    today_signal: SignalAction
    targets: list[str] = Field(default_factory=list)
    metrics: BacktestMetrics
    win_rate: float = Field(ge=0.0, le=1.0)
    trade_count: int = Field(ge=0)


class DailyDigestComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    today_signal: SignalAction
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    status: Literal["주목", "유지", "관망"]


class DailyDigestStrategyCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    today_signal: SignalAction
    targets: list[str] = Field(default_factory=list)
    metrics: BacktestMetrics
    win_rate: float = Field(ge=0.0, le=1.0)
    trade_count: int = Field(ge=0)
    ai_interpretation: str = Field(min_length=1)
    caution: str = Field(min_length=1)


class MarketBriefItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    url: str | None = None
    published_at: datetime | None = None
    tone: NewsTone = "neutral"
    summary: str = Field(min_length=1)


class MarketBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1)
    items: list[MarketBriefItem] = Field(default_factory=list)
    source_usage: SourceUsage | None = None
    fallback_reasons: list[str] = Field(default_factory=list)


class DailyDigestHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_date: str = Field(min_length=1)
    user_name: str = Field(min_length=1)
    strategy_count: int = Field(ge=1, le=3)


class DailyDigestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: DailyDigestHeader
    overall_summary: list[str] = Field(min_length=1)
    comparison_rows: list[DailyDigestComparisonRow] = Field(min_length=1, max_length=3)
    strategy_cards: list[DailyDigestStrategyCard] = Field(min_length=1, max_length=3)
    ai_overall_comment: str = Field(min_length=1)
    market_brief: MarketBrief
    footer: list[str] = Field(min_length=1)


class APIEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EnvelopeStatus
    trace_id: str = Field(min_length=1)
    schema_version: str = SCHEMA_VERSION
    user_payload: UserPayload
    strategy_spec: StrategySpec | None = None
    debug_ref: str = Field(min_length=1)
    retryable: bool
    semantic_slots: SemanticSlots | None = None
    data_requirements: list[DataRequirement] = Field(default_factory=list)
    source_usage: list[SourceUsage] = Field(default_factory=list)
    freshness_status: FreshnessStatus | None = None
    proxy_disclosure: dict[str, str] | None = None
    failure_cause: FailureDiagnostic | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    rule_provenance: RuleProvenance | None = None
