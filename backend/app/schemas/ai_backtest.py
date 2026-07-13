from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ExecutionMode = Literal["engine", "ai_generated_code"]
AICodeStatus = Literal["generated", "validated", "rejected", "executed", "failed"]
CodeExecutionStatus = Literal["queued", "running", "succeeded", "failed", "timeout"]


class AITraceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    user_id: int | None = None
    session_id: UUID | None = None
    trace_kind: str = Field(default="ai_generated_backtest", min_length=1)
    status: str = Field(default="running", min_length=1)
    metadata_jsonb: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class AIStrategyParseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parse_id: UUID
    session_id: UUID | None = None
    user_id: int | None = None
    trace_id: UUID | None = None
    raw_prompt: str = Field(min_length=1)
    parsed_strategy_jsonb: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    model_name: str | None = None
    parse_status: str = Field(default="parsed", min_length=1)


class AICodeGenerationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_id: UUID
    parse_id: UUID | None = None
    user_id: int | None = None
    session_id: UUID | None = None
    trace_id: UUID | None = None
    source_message_id: UUID | None = None
    target_runtime: str = Field(min_length=1)
    code_purpose: str = Field(min_length=1)
    generated_code: str = Field(min_length=1)
    code_hash: str = Field(min_length=1)
    model_name: str | None = None
    code_status: AICodeStatus = "generated"


class CodeValidationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_safe: bool
    syntax_valid: bool
    uses_allowed_imports: bool
    blocks_network_access: bool
    blocks_file_write: bool
    warnings_jsonb: list[Any] = Field(default_factory=list)
    errors_jsonb: list[Any] = Field(default_factory=list)

    @property
    def allows_execution(self) -> bool:
        return (
            self.is_safe
            and self.syntax_valid
            and self.uses_allowed_imports
            and self.blocks_network_access
            and self.blocks_file_write
        )


class AICodeValidationResultCreate(CodeValidationOutcome):
    validation_id: UUID
    code_id: UUID


class CodeExecutionRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_run_id: UUID
    code_id: UUID
    user_id: int | None = None
    session_id: UUID | None = None
    trace_id: UUID | None = None
    runtime_env: str = Field(min_length=1)
    sandbox_id: str | None = None
    status: CodeExecutionStatus = "queued"
    timeout_seconds: int = Field(gt=0)
    memory_limit_mb: int = Field(gt=0)
    latency_ms: float | None = None
    stdout: str | None = None
    stderr: str | None = None
    output_artifacts_jsonb: dict[str, Any] | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class CodeExecutionRunUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CodeExecutionStatus
    latency_ms: float | None = None
    stdout: str | None = None
    stderr: str | None = None
    output_artifacts_jsonb: dict[str, Any] | None = None
    sandbox_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class BacktestEquityPointRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_date: date
    cash: float | None = None
    positions_value: float | None = None
    total_equity: float | None = None
    daily_return: float | None = None


class BacktestSignalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_date: date
    scheduled_execution_date: date | None = None
    execution_timing: str | None = None
    sequence_no: int = Field(ge=1)
    ticker: str = Field(min_length=1)
    action: str = Field(min_length=1)
    reasons: list[Any] = Field(default_factory=list)
    matching_entry_rules: list[Any] = Field(default_factory=list)
    matching_exit_rules: list[Any] = Field(default_factory=list)


class BacktestTradeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_signal_id: int | None = None
    exit_signal_id: int | None = None
    ticker: str = Field(min_length=1)
    entry_date: date
    exit_date: date | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    quantity: int | None = None
    entry_cost: float | None = None
    exit_cost: float | None = None
    gross_pnl: float | None = None
    net_pnl: float | None = None
    return_pct: float | None = None
    reason: str | None = None


class BacktestSummaryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_equity: float | None = None
    final_cash: float | None = None
    open_positions: int | None = None
    period_return: float | None = None
    cagr: float | None = None
    benchmark_return: float | None = None
    alpha: float | None = None
    beta: float | None = None
    max_drawdown: float | None = None
    volatility: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    payoff_ratio: float | None = None
    avg_win: float | None = None
    avg_loss: float | None = None
    max_consecutive_wins: int | None = None
    max_consecutive_losses: int | None = None
    trade_count: int | None = None
    signal_count: int | None = None
    avg_holding_days: float | None = None
    turnover: float | None = None
    total_commission: float | None = None
    total_tax: float | None = None
    total_slippage: float | None = None
    excluded_ticker_count: int | None = None
    excluded_tickers_jsonb: list[Any] = Field(default_factory=list)
    indicator_report_jsonb: dict[str, Any] = Field(default_factory=dict)
    cost_model_jsonb: dict[str, Any] = Field(default_factory=dict)
    position_sizing_jsonb: dict[str, Any] = Field(default_factory=dict)
    metrics_version: str | None = None


class BacktestMetricDetailRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compare_json: dict[str, Any] = Field(default_factory=dict)
    composition_json: dict[str, Any] = Field(default_factory=dict)
    drawdown_detail_json: list[Any] = Field(default_factory=list)
    drawdown_series_json: list[Any] = Field(default_factory=list)
    greeks_json: dict[str, Any] = Field(default_factory=dict)
    rolling_returns_json: dict[str, Any] = Field(default_factory=dict)
    monthly_return_json: list[Any] = Field(default_factory=list)
    montecarlo_json: dict[str, Any] = Field(default_factory=dict)
    montecarlo_cagr_json: dict[str, Any] = Field(default_factory=dict)
    montecarlo_drawdown_json: dict[str, Any] = Field(default_factory=dict)
    montecarlo_sharpe_json: dict[str, Any] = Field(default_factory=dict)
    outliers_json: dict[str, Any] = Field(default_factory=dict)


class BacktestRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    strategy_id: str | None = None
    user_id: int | None = None
    session_id: UUID | None = None
    source_parse_id: UUID | None = None
    code_id: UUID | None = None
    execution_run_id: UUID | None = None
    trace_id: UUID | None = None
    initial_capital: float
    max_tickers: int | None = None
    talib_mode: str | None = None
    config_jsonb: dict[str, Any] = Field(default_factory=dict)
    backtest_start_date: date | None = None
    backtest_end_date: date | None = None
    benchmark_ticker: str | None = None
    data_source: str | None = None
    strategy_snapshot_jsonb: dict[str, Any] = Field(default_factory=dict)
    universe_snapshot_jsonb: dict[str, Any] = Field(default_factory=dict)
    as_of_at: datetime | None = None
    status: str = Field(default="succeeded", min_length=1)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_message: str | None = None
    output_paths_jsonb: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode = "ai_generated_code"


class BacktestResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: BacktestRunCreate
    summary: BacktestSummaryRecord
    metric_detail: BacktestMetricDetailRecord
    equity_points: list[BacktestEquityPointRecord] = Field(default_factory=list)
    signals: list[BacktestSignalRecord] = Field(default_factory=list)
    trades: list[BacktestTradeRecord] = Field(default_factory=list)


class PromptLogBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_template_name: str | None = None
    system_prompt: str | None = None
    user_prompt: str | None = None
    assistant_response: str | None = None
    variables_jsonb: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str | None = None
    contains_pii: bool = False
    masked: bool = False


class ModelCallLogBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: str = Field(min_length=1)
    provider: str | None = None
    provider_request_id: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    response_schema_name: str | None = None
    web_search_used: bool = False
    top_p: float | None = None
    seed: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None
    cost: float | None = None
    retry_count: int = 0
    cache_hit: bool = False
    tool_calls_jsonb: list[Any] = Field(default_factory=list)
    status: str = Field(default="succeeded", min_length=1)
    error_type: str | None = None
    error_message: str | None = None
    prompt_log: PromptLogBundle


class AIBacktestReportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_return: float | None = None
    cagr: float | None = None
    max_drawdown: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    volatility: float | None = None
    benchmark_return: float | None = None
    overall_rating: str | None = None
    summary: str | None = None
    return_analysis: str | None = None
    risk_analysis: str | None = None
    trade_analysis: str | None = None
    benchmark_analysis: str | None = None
    improvement_suggestions: str | None = None
    report_jsonb: dict[str, Any] = Field(default_factory=dict)
    model_name: str | None = None
    model_call: ModelCallLogBundle | None = None


class AIBacktestReportCreate(AIBacktestReportDraft):
    report_id: UUID
    run_id: UUID
    user_id: int | None = None
    trace_id: UUID | None = None


class AgentExecutionLogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: UUID
    trace_id: UUID | None = None
    user_id: int | None = None
    session_id: UUID | None = None
    run_id: UUID | None = None
    execution_run_id: UUID | None = None
    agent_name: str = Field(min_length=1)
    step_name: str = Field(min_length=1)
    status: str = Field(default="running", min_length=1)
    input_jsonb: dict[str, Any] = Field(default_factory=dict)
    output_jsonb: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    latency_ms: float | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class AgentExecutionLogUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1)
    output_jsonb: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    latency_ms: float | None = None
    ended_at: datetime | None = None


class AIErrorLogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_id: UUID
    trace_id: UUID | None = None
    user_id: int | None = None
    session_id: UUID | None = None
    call_id: UUID | None = None
    execution_id: UUID | None = None
    execution_run_id: UUID | None = None
    error_type: str = Field(min_length=1)
    error_message: str = Field(min_length=1)
    stack_trace: str | None = None
    context_jsonb: dict[str, Any] = Field(default_factory=dict)
    severity: str = Field(default="error", min_length=1)


class GeneratedCodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_runtime: str = Field(min_length=1)
    code_purpose: str = Field(min_length=1)
    generated_code: str = Field(min_length=1)
    model_name: str | None = None
    model_call: ModelCallLogBundle | None = None


class CodeExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_env: str = Field(min_length=1)
    status: CodeExecutionStatus
    timeout_seconds: int = Field(gt=0)
    memory_limit_mb: int = Field(gt=0)
    sandbox_id: str | None = None
    latency_ms: float | None = None
    stdout: str | None = None
    stderr: str | None = None
    output_artifacts_jsonb: dict[str, Any] | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    backtest_result: BacktestResultPayload | None = None


class AICodeBacktestFlowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int | None = None
    session_id: UUID | None = None
    source_message_id: UUID | None = None
    trace_id: UUID | None = None
    natural_language_prompt: str = Field(min_length=1)
    parsed_strategy_jsonb: dict[str, Any] = Field(default_factory=dict)
    parse_confidence: float | None = None
    parse_model_name: str | None = None
    strategy_id: str | None = None
    target_runtime: str = Field(min_length=1)
    code_purpose: str = Field(min_length=1)
    benchmark_ticker: str | None = None
    data_source: str | None = None
    report_model_name: str | None = None
    timeout_seconds: int = Field(default=300, gt=0)
    memory_limit_mb: int = Field(default=512, gt=0)


class AICodeBacktestFlowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    parse_id: UUID
    code_id: UUID
    validation_id: UUID
    execution_run_id: UUID | None = None
    run_id: UUID | None = None
    report_id: UUID | None = None
    code_status: AICodeStatus
    execution_status: CodeExecutionStatus | None = None
