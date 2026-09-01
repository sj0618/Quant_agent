from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from ai_graph.research_eligibility import PublicPerformance

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
    # The run stopped because someone or something stopped it, not because it broke:
    # a user cancellation, or a request that used up its total time budget.
    "cancelled",
    "unknown_failure",
]

class Stage(str, Enum):
    INTERPRETING = "interpreting"
    CODE_GENERATION = "code_generation"
    BACKTEST = "backtest"
    DEBATE = "debate"
    FINALIZING = "finalizing"


FailureSubcause = Literal[
    "db_connection_unavailable",
    "db_connect_timeout",
    "db_statement_timeout",
    # The warehouse ran out of lock-table slots ("out of shared memory"), which a query
    # touching many hypertable chunks can do on its own. Distinct from the timeouts
    # above: nothing was slow, the statement was refused before it read a row.
    "db_lock_capacity_exhausted",
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
    # The provider took the request and then did not answer within the client's budget,
    # as opposed to refusing it for capacity (aoai_capacity_exhausted above).
    "aoai_response_timeout",
    # Provider failures are kept separate from warehouse connection failures so the
    # operator can distinguish an AOAI incident from a database incident without
    # exposing provider response bodies to API consumers.
    "aoai_connection_error",
    "aoai_http_4xx",
    "aoai_http_5xx",
    "aoai_http_error",
    "parser_low_confidence",
    "source_conflict",
    "data_required",
    "exploration_policy_unavailable",
    "exploration_policy_stale",
    # A release deployment must never substitute local fixture rows for an absent
    # operational data source. This is a stable configuration-safety diagnosis, not
    # an arbitrary exception string carried into the public contract.
    "fixture_mode_forbidden_in_release",
    # The screen ran and matched nothing, or the matched names have no price history.
    # Separate from the generic gaps above so the user is told the condition was too
    # tight rather than that something broke.
    "no_screening_matches",
    "no_price_rows",
    "empty_analysis_result",
    # Emitted when the user cancels a running analysis.
    "user_cancelled",
    # The request as a whole outlived `AI_JOB_DEADLINE_SECONDS`. Distinct from the
    # provider and statement timeouts above: nothing individually timed out, the sum did.
    "job_deadline_exceeded",
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
    availability: Literal[
        "available", "derivable", "partial", "unavailable", "outside_owner", "not_required"
    ]
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


class FreshnessEvidence(BaseModel):
    """The bounded freshness decision carried by a public envelope."""

    model_config = ConfigDict(extra="forbid")

    status: FreshnessStatus
    as_of: date | None = None
    reason: str = Field(min_length=1)
    source: str = Field(min_length=1)
    no_recommendation: bool


class FailureDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: FailureCategory
    subcause: FailureSubcause
    # This is a public routing field, not arbitrary provider text.  Keeping it
    # closed prevents an internal exception message from becoming a UI stage and
    # makes the API/job/FE contract testable across a rolling deploy.
    failure_stage: Stage
    owner: Literal[
        "ai_graph",
        "data_source_config",
        "fe_state",
        "outside_owner",
        "product_data_gap",
        # Nobody's defect: the run stopped because the user asked it to. Reporting this
        # as "unknown" would send an operator looking for a fault that is not there.
        "user",
        "unknown",
    ]
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
        elif not isinstance(self.right, (int, float, str)):
            # Metric-to-metric comparisons are first-class rules (close > SMA, +DI >
            # -DI).  Requiring a fake one-period window changed "current versus
            # current" into "current versus yesterday" in the executable evaluator.
            raise ValueError("scalar operators require a number or metric name")
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
    selection_mode: Literal["standard", "automatic", "user_defined"] = "standard"
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("strategy_id")
    @classmethod
    def normalize_strategy_id(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


STRATEGY_EXECUTION_SPEC_VERSION_V1 = "strategy-execution-spec.v1"
EXPLORATION_EXECUTION_SPEC_VERSION_V2 = "exploration-execution-spec.v2"
RESEARCH_CANDIDATE_EXECUTION_SPEC_VERSION_V3 = "research-candidate-execution-spec.v3"


class StrategyExecutionConditionV1(BaseModel):
    """A bounded, non-order condition in the parse-bound execution contract."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(min_length=1, max_length=64)
    comparator: Literal["lt", "lte", "gt", "gte", "eq", "ne"]
    value: float
    lookback: int = Field(default=14, ge=1, le=2000)
    role: Literal["entry", "exit"]

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not math.isfinite(value) or abs(value) > 1_000_000_000:
            raise ValueError("condition value is outside the supported range")
        return value

    @model_validator(mode="after")
    def metric_value_range(self) -> "StrategyExecutionConditionV1":
        metric = self.metric.strip().lower().replace("-", "_")
        if metric in {"rsi", "rsi_14", "mfi", "stoch_k", "stoch_d"} and not 0 <= self.value <= 100:
            raise ValueError("bounded oscillator value is outside the supported range")
        if metric == "willr" and not -100 <= self.value <= 0:
            raise ValueError("willr value is outside the supported range")
        return self


class StrategyExecutionSpecV1(BaseModel):
    """The public V1 rule shape that may be admitted to a durable analysis job.

    Entry and exit describe a historical research rule only.  They never express an
    order, position, account, quantity, or personalized recommendation.
    """

    model_config = ConfigDict(extra="forbid")

    market: Literal["KRX"] = "KRX"
    timeframe: Literal["daily"] = "daily"
    entry_conditions: list[StrategyExecutionConditionV1] = Field(min_length=1, max_length=3)
    exit_conditions: list[StrategyExecutionConditionV1] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def separate_condition_roles(self) -> "StrategyExecutionSpecV1":
        if any(condition.role != "entry" for condition in self.entry_conditions):
            raise ValueError("entry_conditions must use the entry role")
        if any(condition.role != "exit" for condition in self.exit_conditions):
            raise ValueError("exit_conditions must use the exit role")
        return self


class ExplorationCandidateRefV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: str = Field(pattern=r"^qb-v2-[a-z0-9-]+$")
    execution_signature: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExplorationExecutionSpecV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: Literal["exploratory_return_seeking"] = "exploratory_return_seeking"
    market: Literal["KRX"] = "KRX"
    timeframe: Literal["daily"] = "daily"
    policy_version: str = Field(min_length=1, max_length=100)
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_version: str = Field(min_length=1)
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: list[ExplorationCandidateRefV2] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def candidate_ids_are_unique(self) -> "ExplorationExecutionSpecV2":
        ids = [candidate.catalog_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("exploration candidates must be unique")
        return self

    @property
    def is_executable(self) -> bool:
        return True


class ResearchSourceRefV3(BaseModel):
    """A cited research fact used to resolve an unfamiliar strategy term.

    The source is evidence for *what a term means*, never a source of return or
    recommendation numbers.  ``excerpt_digest`` deliberately identifies the exact
    captured assertion without treating a mutable web page as an executable input.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(pattern=r"^source-[1-8]$")
    title: str = Field(min_length=1, max_length=240)
    url: str = Field(pattern=r"^https://")
    claim: str = Field(min_length=1, max_length=600)
    excerpt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ResearchCandidateV3(BaseModel):
    """One AOAI-researched, compiler-verifiable candidate before performance exists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(pattern=r"^research-[a-z0-9][a-z0-9-]{0,62}$")
    title: str = Field(min_length=1, max_length=160)
    hypothesis: str = Field(min_length=1, max_length=800)
    counter_hypothesis: str = Field(min_length=1, max_length=800)
    entry_conditions: list[Condition] = Field(min_length=1, max_length=6)
    exit_conditions: list[Condition] = Field(min_length=1, max_length=6)
    required_metrics: list[str] = Field(min_length=1, max_length=20)
    assumptions: list[str] = Field(min_length=1, max_length=10)
    source_ids: list[str] = Field(min_length=1, max_length=8)


class ResearchCandidateExecutionSpecV3(BaseModel):
    """Sealed execution contract for an AI-researched unfamiliar strategy.

    V3 is intentionally declarative: AOAI may research terminology and formulate
    candidates, but it cannot inject Python, SQL, a data-source choice, or performance
    figures.  The deterministic compiler and PostgreSQL/PIT loader remain the only
    authorities for execution and results.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: Literal["research_required"] = "research_required"
    market: Literal["KRX"] = "KRX"
    timeframe: Literal["daily"] = "daily"
    research_schema_version: Literal["strategy-research-draft.v3"] = "strategy-research-draft.v3"
    research_prompt_version: str = Field(min_length=1, max_length=100)
    query_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolution_summary: str = Field(min_length=1, max_length=800)
    research_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sources: list[ResearchSourceRefV3] = Field(min_length=1, max_length=8)
    # V3.0 executes one faithful researched rule. A later multi-candidate engine must
    # not silently drop sealed rules before it can execute and report every one.
    candidates: list[ResearchCandidateV3] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def source_and_candidate_references_are_complete(self) -> "ResearchCandidateExecutionSpecV3":
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("research sources must be unique")
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("research candidate ids must be unique")
        known_sources = set(source_ids)
        if any(not set(candidate.source_ids) <= known_sources for candidate in self.candidates):
            raise ValueError("research candidates must reference sealed research sources")
        return self

    @property
    def is_executable(self) -> bool:
        return True


ExecutionSpecV1OrV2 = (
    StrategyExecutionSpecV1 | ExplorationExecutionSpecV2 | ResearchCandidateExecutionSpecV3
)
_EXECUTION_SPEC_ADAPTER = TypeAdapter(ExecutionSpecV1OrV2)


def validate_execution_spec(raw: Any) -> ExecutionSpecV1OrV2:
    """Decode either admitted contract at one shared boundary."""

    return _EXECUTION_SPEC_ADAPTER.validate_python(raw)


def canonical_execution_spec_digest(spec: ExecutionSpecV1OrV2) -> str:
    """Return the stable, public digest for a validated execution specification.

    The parse boundary signs the same canonical JSON shape.  Keeping the serializer
    here lets the envelope validate its own contract without importing the
    higher-level research/parse module (and creating a dependency cycle).
    """

    encoded = json.dumps(
        spec.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    out_sample_sharpe: float | None
    degradation: float
    # Selection-only statistics. Defaults preserve compatibility with historical
    # result payloads that predate the real hold-out split.
    in_sample_return: float = 0.0
    in_sample_max_drawdown: float = 0.0
    # Hold-out statistics. `sharpe_ratio`/`total_return`/`max_drawdown` above span the
    # whole period, including the selection history, so they are not an out-of-sample
    # claim. Nullable values explicitly represent an unavailable walk-forward aggregate.
    out_sample_return: float | None = None
    out_sample_max_drawdown: float | None = None
    # Daily returns behind the in-sample statistics. Needed to deflate a Sharpe for the
    # width of the search: the public equity curve is downsampled to a dozen points, so
    # it cannot stand in for the sample size.
    in_sample_observations: int = 0
    # How many candidates the winner was chosen from. Reporting the best of N without
    # saying what N was makes an argmax look like a discovery.
    candidates_evaluated: int = 1
    # Sharpe after deflating for the width of the search.
    selection_adjusted_sharpe: float = 0.0
    in_sample_benchmark_return: float | None = None
    out_sample_benchmark_return: float | None = None
    in_sample_excess_return: float | None = None
    out_sample_excess_return: float | None = None
    benchmark_period_count: int | None = Field(default=None, ge=0)
    benchmark_period_win_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    benchmark_period_loss_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    in_sample_benchmark_period_count: int | None = Field(default=None, ge=0)
    in_sample_benchmark_period_win_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    in_sample_benchmark_period_loss_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    out_sample_benchmark_period_count: int | None = Field(default=None, ge=0)
    out_sample_benchmark_period_win_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    out_sample_benchmark_period_loss_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class WalkForwardFoldSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fold_index: int = Field(ge=0)
    selection_hash: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    evaluation_sessions: list[str] = Field(default_factory=list)


class WalkForwardPolicyResult(BaseModel):
    """Performance belongs to the rolling selection policy, never one final candidate."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "insufficient", "unsafe_candidate"]
    unavailable_reason: str | None = None
    fold_selections: list[WalkForwardFoldSelection] = Field(default_factory=list)
    unique_evaluation_session_count: int = Field(default=0, ge=0)
    daily_returns: dict[str, float] = Field(default_factory=dict)
    aggregate_metrics: BacktestMetrics | None = None
    equity_curve: list[BacktestEquityPoint] = Field(default_factory=list)
    fills: list[dict[str, Any]] = Field(default_factory=list)
    costs: float = 0.0
    deduped_session_count: int = Field(default=0, ge=0)


class PublicMetricProvenance(BaseModel):
    """Immutable registry reference for one public metric definition."""

    model_config = ConfigDict(extra="forbid")

    implementation_path: str = Field(min_length=1)
    implementation_ref: str = Field(min_length=1)
    implementation_hash: str = Field(min_length=64, max_length=64)


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
    source_refs: list[str] = Field(default_factory=list)
    registry_version: str = Field(min_length=1)
    provenance: PublicMetricProvenance


class PublicIndicatorExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    plain_explanation: str = Field(min_length=1)
    why_used: str = Field(min_length=1)
    formula: str | None = None
    derivation: str | None = None
    customization: str | None = None
    caution: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)


class PublicStrategyExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_mode: Literal["standard", "automatic", "user_defined"]
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    why_selected: str = Field(min_length=1)
    rebalance_explanation: str | None = None
    caution: str = Field(min_length=1)
    indicators: list[PublicIndicatorExplanation] = Field(default_factory=list)
    generated_strategies: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


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
    "academic_momentum_trend",
    "relative_momentum_rotation",
    "risk_adjusted_momentum_rotation",
    "trend_leader_rotation",
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
    # Catalog strategies carry their own ranking formula.  This is deliberately part
    # of the executable IR (rather than display-only blueprint metadata), so the rule
    # described to the user is the rule that decides which names receive scarce slots.
    ranking_metric: str | None = None
    ranking_direction: Literal["desc", "asc"] = "desc"
    execution_mode: Literal["event_driven", "scheduled_rotation"] = "event_driven"


class CandidateParameters(BaseModel):
    """Small bounded search surface executed by the verified signal engine."""

    model_config = ConfigDict(extra="forbid")

    profile: StructuredProfile
    # Stable provenance for an independently defined catalog strategy.  Parameter
    # variants may share a profile, but two catalog rules never share this identity.
    blueprint_id: str | None = None
    lookback: int = Field(ge=3, le=252)
    threshold: float = Field(ge=-1.0, le=100.0)
    stop_loss_pct: float = Field(gt=0.0, le=1.0)
    take_profit_pct: float = Field(gt=0.0, le=10.0)
    max_positions: int = Field(gt=0, le=1000)
    rebalance_interval_days: int = Field(default=21, ge=5, le=63)
    trailing_stop_pct: float = Field(default=0.25, gt=0.0, le=0.75)
    medium_momentum_weight: float = Field(default=0.60, ge=0.0, le=1.0)


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


TickerActionType = Literal["BUY", "SELL", "HOLD", "WATCH"]


class TickerAction(BaseModel):
    """What to do with one stock today, according to the strategy that was validated.

    The backtest ends on the most recent bar, so it already knows both halves of this:
    what the rule signals now, and what the book is holding now. Emitting the verdict
    from that same run is the only way the recommendation and the performance figure can
    be guaranteed to describe the same strategy.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    name: str = Field(min_length=1)
    action: TickerActionType
    reason: str = Field(min_length=1)
    as_of_date: str = Field(min_length=1)
    close: float | None = None
    # Which candidate produced it, so a recommendation can be traced to the run that
    # was measured rather than to "the strategy" in general.
    source_candidate_id: str | None = None


class CandidateBacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_a: StrategySpec
    candidates: list[CodeCandidate] = Field(min_length=1)
    selected_candidate: CodeCandidate
    equity_curve: list[BacktestEquityPoint]
    # Per-stock BUY/SELL/HOLD for the final bar of the selected candidate's run.
    ticker_actions: list[TickerAction] = Field(default_factory=list)
    engine_summary: dict[str, Any] = Field(default_factory=dict)
    engine_summaries_by_candidate: dict[str, dict[str, Any]] = Field(default_factory=dict)
    objective_scores_by_candidate: dict[str, float] = Field(default_factory=dict)
    backtest_payload: dict[str, Any] = Field(default_factory=dict)
    feature_coverage: dict[str, Any] = Field(default_factory=dict)
    fallback_reasons: list[str] = Field(default_factory=list)
    execution_stats: dict[str, Any] = Field(default_factory=dict)
    generated_strategy_blueprints: list[dict[str, Any]] = Field(default_factory=list)
    walk_forward: WalkForwardPolicyResult | None = None


def _normalize_legacy_signal_action(value: Any) -> Any:
    """Keep historical report reads compatible while emitting the standard SELL term."""

    return "SELL" if value == "DROP" else value


SignalAction = Annotated[
    Literal["BUY", "HOLD", "SELL", "NO_RECOMMENDATION"],
    BeforeValidator(_normalize_legacy_signal_action),
]


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


class ExplorationCandidateResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: Literal["available", "insufficient_data", "failed"]
    total_return: float | None = None
    max_drawdown: float | None = None
    sharpe_ratio: float | None = None
    trade_count: int = Field(default=0, ge=0)
    evaluation_session_count: int = Field(default=0, ge=0)
    costs: float | None = Field(default=None, ge=0.0)
    after_costs: bool = True
    reason: str | None = None


class BaseReportV2(BaseModel):
    """Fixed, server-numbered exploration report returned by the primary job."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["base-report.v2"] = "base-report.v2"
    classification: Literal["exploratory_return_seeking"] = "exploratory_return_seeking"
    policy_version: str = Field(min_length=1)
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_version: str = Field(min_length=1)
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark: str = Field(min_length=1)
    validation_method: str = Field(min_length=1)
    elapsed_ms: float = Field(ge=0.0)
    llm_call_counts: dict[str, int]
    historical_observation: Literal["observed", "not_observed", "inconclusive"]
    candidates: list[ExplorationCandidateResultV2] = Field(min_length=2, max_length=10)
    comparison_candidate_id: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    deep_research_status: Literal["pending", "ready", "unavailable"] = "pending"


class ReportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_projection: ReportProjection
    email_projection: ReportProjection
    risk_adjustments: list[RiskAdjustment] = Field(default_factory=list)
    base_report_v2: BaseReportV2 | None = None


class BacktestEvaluationBasis(BaseModel):
    """Reader-facing statement of the historical slice used for performance."""

    model_config = ConfigDict(extra="forbid")

    basis: Literal["hold_out", "walk_forward_policy"]
    caption: str = Field(min_length=1)
    hold_out_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    window_start: str | None = None
    window_end: str | None = None
    window_policy_id: str | None = None
    evaluation_session_count: int | None = Field(default=None, ge=0)
    fold_count: int | None = Field(default=None, ge=0)
    cost_model_applied: bool = False


class BacktestUniversePolicy(BaseModel):
    """Reader-facing distinction between a PIT backtest universe and today's screen."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    policy_id: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    traded_ticker_count: int | None = Field(default=None, ge=0)
    excluded_screening_candidate_count: int = Field(default=0, ge=0)
    excluded_notice: str | None = None


class BacktestPerformance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_candidate_id: str = Field(min_length=1)
    # ``None`` is unavailable data, never a measured zero return.
    metrics: BacktestMetrics | None = None
    equity_curve: list[BacktestEquityPoint] = Field(default_factory=list)
    engine_summary: dict[str, Any] = Field(default_factory=dict)
    reliability: BacktestReliability | None = None
    data_quality: list[str] = Field(default_factory=list)
    benchmark: BacktestBenchmark | None = None
    metric_details: list[PublicMetricDetail] = Field(default_factory=list)
    strategy_explanation: PublicStrategyExplanation | None = None
    is_available: bool = True
    unavailable_reason: str | None = None
    evaluation_basis: BacktestEvaluationBasis | None = None
    universe_policy: BacktestUniversePolicy | None = None


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
    # A measured threshold miss and an acceptance rule that could not be evaluated are
    # distinct outcomes. Keep them separate so unavailable inputs are never presented
    # as strategy underperformance.
    verification_complete: bool = True
    unmet_objective_criteria: list[str] = Field(default_factory=list)
    unmet_data_requirements: list[str] = Field(default_factory=list)


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
    # Internal backtest objects retain their richer audit fields.  The HTTP/job
    # envelope deliberately exposes only the discriminated projection so consumers
    # cannot mistake a partial calculation for a publishable performance result.
    performance: PublicPerformance | None = None
    recommendation_gate: RecommendationGate | None = None
    ticker_actions: list[TickerAction] = Field(default_factory=list)
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
    status: Literal["주목", "유지", "매도", "근거 부족"]


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
    # The legacy ``strategy_spec`` remains readable while callers migrate.  A
    # parse-bound analysis carries this separately versioned and hash-addressed
    # execution contract; all three fields are present or absent together.
    execution_spec: ExecutionSpecV1OrV2 | None = None
    execution_spec_version: Literal[
        "strategy-execution-spec.v1",
        "exploration-execution-spec.v2",
        "research-candidate-execution-spec.v3",
    ] | None = None
    execution_spec_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    debug_ref: str = Field(min_length=1)
    retryable: bool
    semantic_slots: SemanticSlots | None = None
    data_requirements: list[DataRequirement] = Field(default_factory=list)
    source_usage: list[SourceUsage] = Field(default_factory=list)
    freshness_status: FreshnessStatus | None = None
    freshness_evidence: FreshnessEvidence | None = None
    proxy_disclosure: dict[str, str] | None = None
    failure_cause: FailureDiagnostic | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    rule_provenance: RuleProvenance | None = None

    @model_validator(mode="after")
    def validate_public_terminal_contract(self) -> "APIEnvelope":
        execution_values = (
            self.execution_spec,
            self.execution_spec_version,
            self.execution_spec_hash,
        )
        if any(value is None for value in execution_values) and any(
            value is not None for value in execution_values
        ):
            raise ValueError("execution spec, version, and hash must be present together")
        if self.execution_spec is not None:
            expected_version = (
                EXPLORATION_EXECUTION_SPEC_VERSION_V2
                if isinstance(self.execution_spec, ExplorationExecutionSpecV2)
                else RESEARCH_CANDIDATE_EXECUTION_SPEC_VERSION_V3
                if isinstance(self.execution_spec, ResearchCandidateExecutionSpecV3)
                else STRATEGY_EXECUTION_SPEC_VERSION_V1
            )
            if self.execution_spec_version != expected_version:
                raise ValueError("execution spec version must match the execution spec shape")
            expected_hash = canonical_execution_spec_digest(self.execution_spec)
            if self.execution_spec_hash != expected_hash:
                raise ValueError("execution spec hash must match the canonical execution spec")
        if self.failure_cause is not None and self.status != EnvelopeStatus.FAILED:
            raise ValueError("only failed envelopes may expose a failure cause")
        if self.status == EnvelopeStatus.FAILED and self.failure_cause is None:
            raise ValueError("failed envelopes require a typed failure cause")
        return self
