from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrategyLifecycle(str, Enum):
    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    REJECTED = "rejected"


class Market(str, Enum):
    KRX = "KRX"


class AssetType(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    SECTOR = "sector"
    INDEX = "index"


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


class PositionSizingMethod(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    FIXED_PERCENT = "fixed_percent"
    FIXED_RISK = "fixed_risk"


class ExecutionTiming(str, Enum):
    NEXT_OPEN = "next_open"
    NEXT_CLOSE = "next_close"


class ReportSummaryMode(str, Enum):
    BEGINNER = "beginner"
    PRACTITIONER = "practitioner"
    BOTH = "both"


class UserIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: Market = Market.KRX
    asset_type: AssetType = AssetType.EQUITY
    strategy_goal: str
    strategy_family_hint: str | None = None
    indicator_preferences: list[str] = Field(default_factory=list)
    use_report_filter: bool = True
    risk_profile: Literal["conservative", "moderate", "aggressive"] = "moderate"


class UserIntentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lifecycle: StrategyLifecycle = StrategyLifecycle.PROVISIONAL
    fit_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    missing_fields: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    user_intent: UserIntent


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: str = Field(..., description="좌변 metric 이름. 예: rsi, close, macd")
    operator: ConditionOperator
    right: float | str | list[float] = Field(
        ..., description="우변 값. scalar 비교면 숫자, cross 계열이면 metric 이름, between이면 [low, high]"
    )
    description: str | None = None

    @model_validator(mode="after")
    def validate_condition(self) -> "Condition":
        if self.operator in {
            ConditionOperator.LT,
            ConditionOperator.LTE,
            ConditionOperator.GT,
            ConditionOperator.GTE,
            ConditionOperator.EQ,
            ConditionOperator.NE,
        }:
            if not isinstance(self.right, (int, float)):
                raise ValueError("scalar 비교 연산자는 right가 숫자여야 합니다.")

        if self.operator in {ConditionOperator.CROSS_ABOVE, ConditionOperator.CROSS_BELOW}:
            if not isinstance(self.right, str):
                raise ValueError("cross_above/cross_below는 right가 metric 이름 문자열이어야 합니다.")

        if self.operator == ConditionOperator.BETWEEN:
            if not isinstance(self.right, list) or len(self.right) != 2:
                raise ValueError("between 연산자는 right가 [low, high] 형태여야 합니다.")
            if self.right[0] > self.right[1]:
                raise ValueError("between 연산자는 [low, high] 순서여야 합니다.")

        return self


class PositionSizing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: PositionSizingMethod = PositionSizingMethod.EQUAL_WEIGHT
    max_positions: int = Field(default=10, ge=1)
    fixed_percent: float | None = Field(default=None, gt=0.0, le=1.0)
    risk_per_position: float | None = Field(default=None, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_position_sizing(self) -> "PositionSizing":
        if self.method == PositionSizingMethod.FIXED_PERCENT and self.fixed_percent is None:
            raise ValueError("fixed_percent 방식은 fixed_percent 값이 필요합니다.")
        if self.method == PositionSizingMethod.FIXED_RISK and self.risk_per_position is None:
            raise ValueError("fixed_risk 방식은 risk_per_position 값이 필요합니다.")
        return self


class RiskControls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_gross_exposure_pct: float = Field(default=1.0, gt=0.0, le=1.0)
    stop_loss_pct: float = Field(default=0.08, gt=0.0, le=1.0)
    take_profit_pct: float | None = Field(default=None, gt=0.0)
    max_single_position_pct: float = Field(default=0.2, gt=0.0, le=1.0)
    max_sector_weight_pct: float = Field(default=0.4, gt=0.0, le=1.0)
    exclude_listing_risk: bool = True


class WalkForwardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    in_sample_months: int = Field(default=12, ge=1)
    out_of_sample_months: int = Field(default=3, ge=1)
    roll_months: int = Field(default=1, ge=1)


class CostModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commission_pct: float = Field(default=0.00015, ge=0.0)
    tax_pct: float = Field(default=0.0023, ge=0.0)
    slippage_pct: float = Field(default=0.001, ge=0.0)


class BacktestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_timing: ExecutionTiming = ExecutionTiming.NEXT_OPEN
    use_adjusted_price: bool = True
    walk_forward: WalkForwardConfig = Field(default_factory=WalkForwardConfig)
    cost_model: CostModel = Field(default_factory=CostModel)


class ReportingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_email_time: time = time(8, 0)
    summary_mode: ReportSummaryMode = ReportSummaryMode.BOTH
    include_wts_archive: bool = True
    include_ab_comparison_in_user_report: bool = False
    include_ab_comparison_in_analyst_mode: bool = True
    include_candidate_reason_trace: bool = True


class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    strategy_id: str
    strategy_name: str
    description: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    market: Market = Market.KRX
    asset_type: AssetType = AssetType.EQUITY
    user_intent: UserIntentSpec | None = None
    entry_rules: list[Condition]
    entry_logic: LogicMode = LogicMode.ALL
    exit_rules: list[Condition] = Field(default_factory=list)
    exit_logic: LogicMode = LogicMode.ANY
    position_sizing: PositionSizing = Field(default_factory=PositionSizing)
    risk_controls: RiskControls = Field(default_factory=RiskControls)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)

    @field_validator("strategy_id")
    @classmethod
    def normalize_strategy_id(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")

    @model_validator(mode="after")
    def validate_strategy_spec(self) -> "StrategySpec":
        if not self.entry_rules:
            raise ValueError("entry_rules는 최소 1개 이상 필요합니다.")
        return self


class ParsedReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    ticker: str
    sector: str | None = None
    source_published_at: datetime | None = None
    source_discovered_at: datetime | None = None
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    available_at: datetime | None = None
    report_date: date | None = None
    target_price: float | None = None
    rating: str | None = None
    coverage_status: str | None = None
    target_price_change: Literal["UP", "DOWN", "UNCHANGED", "UNKNOWN"] = "UNKNOWN"
    llm_sentiment: float = Field(default=0.0, ge=-1.0, le=1.0)
    extraction_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: str | None = None


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    timestamp: datetime
    metrics: dict[str, float]
    previous_metrics: dict[str, float] = Field(default_factory=dict)


class SignalAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WATCH = "watch"


class SignalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    ticker: str
    action: SignalAction
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    matching_entry_rules: list[str] = Field(default_factory=list)
    matching_exit_rules: list[str] = Field(default_factory=list)


class BacktestPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    strategy_name: str
    market: Market
    asset_type: AssetType
    allowed_modules: list[str]
    network_access_allowed: bool = False
    execution_timing: ExecutionTiming
    use_adjusted_price: bool
    walk_forward: WalkForwardConfig
    cost_model: CostModel
    notes: list[str] = Field(default_factory=list)
