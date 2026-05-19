from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "ai-mvp.v1"


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


class CodeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    variant: Literal["A", "B"]
    code: str = Field(min_length=1)
    validation_ok: bool
    violations: list[str] = Field(default_factory=list)
    metrics: BacktestMetrics | None = None


class ABBacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_a: StrategySpec
    strategy_b: StrategySpec
    candidates: list[CodeCandidate] = Field(min_length=1)
    selected_candidate: CodeCandidate
    metrics_by_variant: dict[str, BacktestMetrics]


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


class APIEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EnvelopeStatus
    trace_id: str = Field(min_length=1)
    schema_version: str = SCHEMA_VERSION
    user_payload: UserPayload
    strategy_spec: StrategySpec | None = None
    debug_ref: str = Field(min_length=1)
    retryable: bool
