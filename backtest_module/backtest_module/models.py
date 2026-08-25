from __future__ import annotations

from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Literal, Union

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
    strategy_family_hint: Union[str, None] = None
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
    right: Union[float, str, list[float]] = Field(
        ..., description="우변 값. scalar 비교면 숫자, cross 계열이면 metric 이름, between이면 [low, high]"
    )
    description: Union[str, None] = None

    @model_validator(mode="after")
    def validate_condition(self) -> "Condition":
        if self.operator == ConditionOperator.BETWEEN:
            if not isinstance(self.right, list) or len(self.right) != 2:
                raise ValueError("between 연산자는 right가 [low, high] 형태여야 합니다.")
            if self.right[0] > self.right[1]:
                raise ValueError("between 연산자는 [low, high] 순서여야 합니다.")

        return self


class PositionSizing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: PositionSizingMethod = PositionSizingMethod.EQUAL_WEIGHT
    max_positions: Union[int, None] = Field(default=10, ge=1)
    fixed_percent: Union[float, None] = Field(default=None, gt=0.0, le=1.0)
    risk_per_position: Union[float, None] = Field(default=None, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_position_sizing(self) -> "PositionSizing":
        if self.method == PositionSizingMethod.FIXED_PERCENT and self.fixed_percent is None:
            raise ValueError("fixed_percent 방식은 fixed_percent 값이 필요합니다.")
        if self.method == PositionSizingMethod.FIXED_RISK and self.risk_per_position is None:
            raise ValueError("fixed_risk 방식은 risk_per_position 값이 필요합니다.")
        return self


class ExecutionCapacityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_participation_rate: float = Field(default=0.01, gt=0.0, le=1.0)


class RiskControls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_gross_exposure_pct: float = Field(default=1.0, gt=0.0, le=1.0)
    stop_loss_pct: Union[float, None] = Field(default=0.08, gt=0.0, le=1.0)
    take_profit_pct: Union[float, None] = Field(default=None, gt=0.0)
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
    policy_id: Union[str, None] = None
    policy_version: Union[str, None] = None
    applicable_market: Union[str, None] = None
    applicable_account: Union[str, None] = None
    applicable_channel: Union[str, None] = None
    applicable_tier: Union[str, None] = None
    effective_from: Union[date, None] = None
    effective_to: Union[date, None] = None
    source_urls: list[str] = Field(default_factory=list)
    document_hash: Union[str, None] = None
    verified_at: Union[datetime, None] = None
    rounding_mode: Literal["none", "floor", "half_up"] = "none"
    rounding_decimals: int = Field(default=6, ge=0, le=10)

    @model_validator(mode="after")
    def validate_cost_policy(self) -> "CostModel":
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValueError("cost policy effective_from must not be after effective_to")
        return self

    @property
    def production_eligible(self) -> bool:
        return bool(
            self.policy_id and self.policy_version and self.applicable_market and self.applicable_account
            and self.applicable_channel and self.applicable_tier and self.effective_from and self.effective_to
            and self.source_urls and self.document_hash and self.verified_at
        )


class CorporateActionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["split", "cash_dividend", "delist"]
    ticker: str
    effective_date: date
    split_ratio: Union[float, None] = Field(default=None, gt=0.0)
    cash_dividend_per_share: Union[float, None] = Field(default=None, ge=0.0)
    recovery_price: Union[float, None] = Field(default=None, ge=0.0)
    recovery_verified: bool = False
    source_urls: list[str] = Field(default_factory=list)
    document_hash: Union[str, None] = None
    verified_at: Union[datetime, None] = None

    @model_validator(mode="after")
    def validate_event(self) -> "CorporateActionEvent":
        if self.event_type == "split" and self.split_ratio is None:
            raise ValueError("split event requires split_ratio")
        if self.event_type == "cash_dividend" and self.cash_dividend_per_share is None:
            raise ValueError("cash_dividend event requires cash_dividend_per_share")
        if self.event_type == "delist" and self.recovery_price is None:
            raise ValueError("delist event requires recovery_price; use zero for explicit zero recovery")
        return self

    @property
    def source_verified(self) -> bool:
        return bool(self.source_urls and self.document_hash and self.verified_at)


class BacktestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_timing: ExecutionTiming = ExecutionTiming.NEXT_OPEN
    use_adjusted_price: bool = True
    walk_forward: WalkForwardConfig = Field(default_factory=WalkForwardConfig)
    cost_model: CostModel = Field(default_factory=CostModel)
    execution_capacity: ExecutionCapacityConfig = Field(default_factory=ExecutionCapacityConfig)
    corporate_actions: list[CorporateActionEvent] = Field(default_factory=list)


class ReportingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_email_time: time = time(8, 0)
    summary_mode: ReportSummaryMode = ReportSummaryMode.BOTH
    include_wts_archive: bool = True
    include_ab_comparison_in_user_report: bool = False
    include_ab_comparison_in_analyst_mode: bool = True
    include_candidate_reason_trace: bool = False


class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    strategy_id: str
    strategy_name: str
    description: Union[str, None] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    market: Market = Market.KRX
    asset_type: AssetType = AssetType.EQUITY
    user_intent: Union[UserIntentSpec, None] = None
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
        if self.position_sizing.method == PositionSizingMethod.FIXED_RISK and self.risk_controls.stop_loss_pct is None:
            raise ValueError("fixed_risk 방식은 stop_loss_pct가 필요합니다.")
        return self


class ParsedReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    ticker: str
    sector: Union[str, None] = None
    source_published_at: Union[datetime, None] = None
    source_discovered_at: Union[datetime, None] = None
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    available_at: Union[datetime, None] = None
    report_date: Union[date, None] = None
    target_price: Union[float, None] = None
    rating: Union[str, None] = None
    coverage_status: Union[str, None] = None
    target_price_change: Literal["UP", "DOWN", "UNCHANGED", "UNKNOWN"] = "UNKNOWN"
    llm_sentiment: float = Field(default=0.0, ge=-1.0, le=1.0)
    extraction_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: Union[str, None] = None


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    timestamp: datetime
    metrics: dict[str, float]
    previous_metrics: Union[dict[str, float], None] = None


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
