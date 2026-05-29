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
    "parser_low_confidence",
    "source_conflict",
    "data_required",
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
    universe: str | None = None
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
        "universe",
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
            raise ValueError("scalar operators require a numeric right side")
        return self


class AmbiguityCode(str, Enum):
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


class StrategyCandidateCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    key_conditions: list[str] = Field(min_length=1, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str | None = None


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
    universe: str = Field(min_length=1)
    market: str = Field(min_length=1)
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


class BacktestEquityPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(min_length=1)
    cumulative_return: float


class CodeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    variant: Literal["A", "B"]
    code: str = Field(min_length=1)
    validation_ok: bool
    violations: list[str] = Field(default_factory=list)
    metrics: BacktestMetrics | None = None


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


class RiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: SignalDecision
    adjustments: list[RiskAdjustment] = Field(default_factory=list)


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


class InternalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    retrieval_hits: list[dict[str, Any]] = Field(default_factory=list)
    llm_prompts: list[str] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    backtest_artifacts: dict[str, Any] = Field(default_factory=dict)
    risk_events: list[dict[str, Any]] = Field(default_factory=list)


class UserPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1)
    message: str = Field(min_length=1)
    next_actions: list[str] = Field(default_factory=list)
    candidate_cards: list[StrategyCandidateCard] = Field(default_factory=list)
    report: ReportBundle | None = None
    performance: BacktestPerformance | None = None
    question: str | None = None
    options: list[ClarificationOption] = Field(default_factory=list, max_length=3)
    recommended: int | None = Field(default=None, ge=0, le=2)


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
