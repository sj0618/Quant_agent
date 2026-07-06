from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.errors import AppError
from app.schemas.ai_backtest import (
    AIBacktestReportCreate,
    AIBacktestReportDraft,
    AICodeBacktestFlowRequest,
    AIErrorLogCreate,
    AIStrategyParseCreate,
    AITraceCreate,
    BacktestMetricDetailRecord,
    BacktestResultPayload,
    BacktestRunCreate,
    BacktestSummaryRecord,
    CodeExecutionResult,
    CodeValidationOutcome,
    GeneratedCodeResult,
)
from app.services.ai_backtest_flow import AICodeBacktestService


@dataclass(slots=True)
class FakeRepository:
    traces: list[AITraceCreate] = field(default_factory=list)
    strategy_parses: list[AIStrategyParseCreate] = field(default_factory=list)
    code_generations: list[Any] = field(default_factory=list)
    code_status_updates: list[tuple[UUID, str]] = field(default_factory=list)
    code_validation_results: list[Any] = field(default_factory=list)
    execution_runs: list[Any] = field(default_factory=list)
    execution_updates: list[Any] = field(default_factory=list)
    backtest_results: list[BacktestResultPayload] = field(default_factory=list)
    reports: list[AIBacktestReportCreate] = field(default_factory=list)
    model_calls: list[Any] = field(default_factory=list)
    agent_logs: list[Any] = field(default_factory=list)
    agent_log_updates: list[Any] = field(default_factory=list)
    error_logs: list[AIErrorLogCreate] = field(default_factory=list)
    finished_traces: list[dict[str, Any]] = field(default_factory=list)

    async def create_trace(self, record: AITraceCreate):
        self.traces.append(record)
        return record.trace_id

    async def finish_trace(self, trace_id, *, status, metadata_jsonb=None, ended_at=None):
        self.finished_traces.append({"trace_id": trace_id, "status": status, "metadata_jsonb": metadata_jsonb})

    async def create_strategy_parse(self, record: AIStrategyParseCreate):
        self.strategy_parses.append(record)
        return record.parse_id

    async def create_code_generation(self, record):
        self.code_generations.append(record)
        return record.code_id

    async def update_code_generation_status(self, code_id, status):
        self.code_status_updates.append((code_id, status))

    async def create_code_validation_result(self, record):
        self.code_validation_results.append(record)
        return record.validation_id

    async def create_code_execution_run(self, record):
        self.execution_runs.append(record)
        return record.execution_run_id

    async def update_code_execution_run(self, execution_run_id, update):
        self.execution_updates.append((execution_run_id, update))

    async def persist_backtest_result(self, payload: BacktestResultPayload):
        self.backtest_results.append(payload)
        return payload.run.run_id

    async def create_ai_backtest_report(self, record: AIBacktestReportCreate):
        self.reports.append(record)
        return record.report_id

    async def create_model_call_log(self, **kwargs):
        self.model_calls.append(kwargs)
        return uuid4()

    async def create_agent_execution_log(self, record):
        self.agent_logs.append(record)
        return record.execution_id

    async def update_agent_execution_log(self, execution_id, update):
        self.agent_log_updates.append((execution_id, update))

    async def create_error_log(self, record: AIErrorLogCreate):
        self.error_logs.append(record)
        return record.error_id


class FakeGenerator:
    def __init__(self):
        self.called = False

    async def generate(self, request: AICodeBacktestFlowRequest, *, trace_id: UUID) -> GeneratedCodeResult:
        self.called = True
        return GeneratedCodeResult(
            target_runtime=request.target_runtime,
            code_purpose=request.code_purpose,
            generated_code="def build_signals(prices):\n    return []\n",
            model_name="gpt-code",
        )


class SafeValidator:
    def __init__(self):
        self.called = False

    def validate(self, generated: GeneratedCodeResult, *, trace_id: UUID) -> CodeValidationOutcome:
        self.called = True
        assert generated.generated_code
        return CodeValidationOutcome(
            is_safe=True,
            syntax_valid=True,
            uses_allowed_imports=True,
            blocks_network_access=True,
            blocks_file_write=True,
        )


class UnsafeValidator:
    def validate(self, generated: GeneratedCodeResult, *, trace_id: UUID) -> CodeValidationOutcome:
        return CodeValidationOutcome(
            is_safe=False,
            syntax_valid=True,
            uses_allowed_imports=False,
            blocks_network_access=True,
            blocks_file_write=True,
            errors_jsonb=[{"rule": "import", "message": "os import not allowed"}],
        )


class FakeExecutor:
    def __init__(self):
        self.called = False

    async def execute(
        self,
        request: AICodeBacktestFlowRequest,
        generated: GeneratedCodeResult,
        *,
        trace_id: UUID,
        execution_run_id: UUID,
    ) -> CodeExecutionResult:
        self.called = True
        now = datetime.now(UTC)
        run_id = uuid4()
        payload = BacktestResultPayload(
            run=BacktestRunCreate(
                run_id=run_id,
                initial_capital=1_000_000.0,
                status="succeeded",
                started_at=now,
                ended_at=now,
                output_paths_jsonb={"summary_json": "outputs/summary.json"},
            ),
            summary=BacktestSummaryRecord(
                final_equity=1_120_000.0,
                final_cash=120_000.0,
                open_positions=1,
                period_return=0.12,
                sharpe_ratio=1.4,
                trade_count=2,
                signal_count=3,
            ),
            metric_detail=BacktestMetricDetailRecord(
                compare_json={"benchmark": 0.08},
                monthly_return_json=[{"month": "2026-01", "value": 0.12}],
            ),
            equity_points=[],
            signals=[],
            trades=[],
        )
        return CodeExecutionResult(
            runtime_env=generated.target_runtime,
            status="succeeded",
            timeout_seconds=300,
            memory_limit_mb=512,
            sandbox_id="sandbox-1",
            latency_ms=42.5,
            stdout="ok",
            stderr="",
            output_artifacts_jsonb={"artifacts": ["summary.json"]},
            started_at=now,
            ended_at=now,
            backtest_result=payload,
        )


class FakeReporter:
    def __init__(self):
        self.called = False

    async def build_report(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        run_id: UUID,
        execution: CodeExecutionResult,
    ) -> AIBacktestReportDraft:
        self.called = True
        return AIBacktestReportDraft(
            period_return=0.12,
            cagr=0.12,
            max_drawdown=-0.05,
            sharpe_ratio=1.4,
            sortino_ratio=1.7,
            calmar_ratio=2.4,
            win_rate=0.5,
            profit_factor=1.8,
            volatility=0.2,
            benchmark_return=0.08,
            overall_rating="good",
            summary="AI generated code outperformed benchmark.",
            report_jsonb={"run_id": str(run_id), "status": execution.status},
            model_name=request.report_model_name,
        )


def test_ai_backtest_flow_persists_generated_code_validation_execution_and_report():
    repository = FakeRepository()
    generator = FakeGenerator()
    validator = SafeValidator()
    executor = FakeExecutor()
    reporter = FakeReporter()
    service = AICodeBacktestService(repository, generator, validator, executor, reporter)

    request = AICodeBacktestFlowRequest(
        user_id=7,
        natural_language_prompt="RSI 반등 전략을 코드로 생성해서 백테스트해줘",
        parsed_strategy_jsonb={"strategy_id": "rsi_rebound", "entry": "rsi <= 30"},
        parse_confidence=0.91,
        parse_model_name="gpt-parse",
        strategy_id="rsi_rebound",
        target_runtime="python-sandbox",
        code_purpose="backtest",
        benchmark_ticker="KOSPI200",
        data_source="fixture",
        report_model_name="gpt-report",
    )

    result = asyncio.run(service.run_generated_backtest(request))

    assert generator.called is True
    assert validator.called is True
    assert executor.called is True
    assert reporter.called is True
    assert result.code_status == "executed"
    assert result.execution_status == "succeeded"
    assert repository.traces[0].trace_id == result.trace_id
    assert repository.strategy_parses[0].trace_id == result.trace_id
    assert repository.code_generations[0].parse_id == result.parse_id
    assert [status for _code_id, status in repository.code_status_updates] == ["validated", "executed"]
    assert repository.execution_runs[0].status == "running"
    assert repository.backtest_results[0].run.execution_run_id == result.execution_run_id
    assert repository.backtest_results[0].run.execution_mode == "ai_generated_code"
    assert repository.backtest_results[0].run.code_id == result.code_id
    assert repository.reports[0].run_id == result.run_id
    assert repository.finished_traces[-1]["status"] == "succeeded"
    assert repository.error_logs == []


def test_ai_backtest_flow_rejects_unsafe_code_before_execution():
    repository = FakeRepository()
    generator = FakeGenerator()
    executor = FakeExecutor()
    service = AICodeBacktestService(repository, generator, UnsafeValidator(), executor, FakeReporter())

    request = AICodeBacktestFlowRequest(
        user_id=8,
        natural_language_prompt="위험한 import가 들어간 전략도 생성해줘",
        parsed_strategy_jsonb={"strategy_id": "unsafe_demo"},
        strategy_id="unsafe_demo",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )

    with pytest.raises(AppError) as exc_info:
        asyncio.run(service.run_generated_backtest(request))

    assert exc_info.value.code == "generated_code_rejected"
    assert repository.code_status_updates[-1][1] == "rejected"
    assert repository.execution_runs == []
    assert repository.backtest_results == []
    assert repository.error_logs
    assert repository.finished_traces[-1]["status"] == "rejected"
