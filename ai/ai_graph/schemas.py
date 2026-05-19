from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "1.0.0"
DEFAULT_CANDIDATE_SNAPSHOT_ID = "mock-candidate-snapshot-krx-001"


class ScenarioCode(str, Enum):
    READY = "READY"
    C1_INPUT_AMBIGUOUS = "C1_INPUT_AMBIGUOUS"
    C2_TERM_UNKNOWN = "C2_TERM_UNKNOWN"
    C4_CONFLICTING = "C4_CONFLICTING"
    C5_INFEASIBLE = "C5_INFEASIBLE"


class NodeName(str, Enum):
    SUPERVISOR = "supervisor"
    AMBIGUITY = "ambiguity"
    DATA = "data"
    RESEARCH = "research"
    BACKTEST_CODE = "backtest_code"
    BACKTEST = "backtest"
    SIGNAL = "signal"
    RISK_MANAGER = "risk_manager"
    REPORT = "report"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WATCH = "WATCH"
    FILTERED_OUT = "FILTERED_OUT"


class RiskSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class L4Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    title: str
    published_at: datetime | None = None
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    metric: str
    operator: Literal["<", "<=", ">", ">=", "=", "increasing", "decreasing"]
    value: str
    unit: str | None = None


class CandidateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = DEFAULT_CANDIDATE_SNAPSHOT_ID
    tickers: list[str] = Field(min_length=1)
    effective_from: datetime


class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    name: str
    summary: str
    universe: str = "KRX equities"
    entry_rules: list[Condition] = Field(min_length=1)
    exit_rules: list[Condition] = Field(default_factory=list)
    entry_logic: Literal["ALL", "ANY"] = "ALL"
    exit_logic: Literal["ALL", "ANY"] = "ANY"
    candidate_snapshot: CandidateSnapshot

    @model_validator(mode="after")
    def normalize_strategy_id(self) -> "StrategySpec":
        self.strategy_id = self.strategy_id.strip().lower().replace(" ", "_")
        return self


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    timestamp: datetime
    metrics: dict[str, float]
    previous_metrics: dict[str, float] = Field(default_factory=dict)


class CandidateStock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str
    sector: str
    lastPrice: float
    dayChangeRate: float
    hasPosition: bool = False
    inCandidateSnapshot: bool = True
    marketSnapshot: MarketSnapshot


class BacktestMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Literal["Total Return", "Sharpe", "MDD", "Win Rate"]
    value: str
    detail: str
    tone: Literal["positive", "neutral", "warning"]


class BacktestPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    strategy: float
    benchmark: float


class BacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[BacktestMetric] = Field(min_length=1)
    series: list[BacktestPoint] = Field(min_length=1)


class SignalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    ticker: str
    action: SignalAction
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    generatedBy: Literal["Signal Judge"] = "Signal Judge"


class RiskWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    ticker: str
    severity: RiskSeverity
    reason: str
    source: str
    evidence: list[str] = Field(default_factory=list)
    report_note: str


class ReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    summary: str
    signalJudgeNote: str | None = None
    riskManagerNote: str | None = None


class ScenarioOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    title: str
    description: str
    keyConditions: list[str]


class TermDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    definition: str
    confidence: float = Field(ge=0.0, le=1.0)
    matchedSources: list[str]
    requiresConfirmation: bool
    mappedStrategyId: str


class ConflictExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    conflictPoints: list[str]
    alternatives: list[ScenarioOption]


class InfeasibleExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    reason: str
    supportedScope: str
    examples: list[str]


class ScenarioPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: ScenarioCode
    assistantMessage: str
    strategy_id: str | None = None
    options: list[ScenarioOption] | None = None
    termDefinition: TermDefinition | None = None
    conflict: ConflictExplanation | None = None
    infeasible: InfeasibleExplanation | None = None


class WorkspacePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activeStrategy: StrategySpec
    candidates: list[CandidateStock]
    signalDecisions: list[SignalDecision]
    riskWarnings: list[RiskWarning]
    reportPreview: list[ReportSection]
    backtestMetrics: list[BacktestMetric]
    backtestSeries: list[BacktestPoint]


class PublicRunPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: ScenarioPayload
    workspace: WorkspacePayload | None = None


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    trace_id: str
    debug_ref: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    result: PublicRunPayload | None = None
    error: str | None = None


class NodeTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: NodeName
    status: Literal["ok", "skipped"]
    detail: str


class InternalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_provider: str
    node_trace: list[NodeTrace] = Field(default_factory=list)
    evidence: list[L4Evidence] = Field(default_factory=list)
    backtest_code_ref: str | None = None
    raw_llm: dict[str, Any] = Field(default_factory=dict)
