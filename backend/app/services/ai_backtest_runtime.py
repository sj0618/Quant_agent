from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.schemas.ai_backtest import (
    AIBacktestReportDraft,
    AICodeBacktestFlowRequest,
    BacktestEquityPointRecord,
    BacktestMetricDetailRecord,
    BacktestResultPayload,
    BacktestRunCreate,
    BacktestSignalRecord,
    BacktestSummaryRecord,
    BacktestTradeRecord,
    CodeExecutionResult,
    CodeValidationOutcome,
    GeneratedCodeResult,
)


def _ensure_project_python_paths() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    for relative in ("ai", "backtest_module"):
        candidate = repo_root / relative
        if candidate.is_dir():
            resolved = str(candidate)
            if resolved not in sys.path:
                sys.path.insert(0, resolved)


class AOAICodeGenerator:
    async def generate(self, request: AICodeBacktestFlowRequest, *, trace_id: UUID) -> GeneratedCodeResult:
        _ensure_project_python_paths()
        from ai_graph.graph import build_strategy_spec
        from ai_graph.llm.factory import AI_AOAI_MODEL_ENV, create_llm_client
        from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
        from ai_graph.schemas import StrategySpec

        strategy = (
            StrategySpec.model_validate(request.parsed_strategy_jsonb)
            if request.parsed_strategy_jsonb
            else build_strategy_spec(request.natural_language_prompt, variant="A", retrieval={"hits": []})
        )
        result = generate_loop3_candidates(
            Loop3Request(strategy=strategy, variant="A", trace_id=str(trace_id)),
            llm_client=create_llm_client(role="BACKTEST_CODE"),
        )
        selected = next((candidate for candidate in result.candidates if candidate.validation_ok), result.selected_candidate)
        model_name = os.environ.get("AI_LLM_BACKTEST_CODE_MODEL") or os.environ.get(AI_AOAI_MODEL_ENV)
        return GeneratedCodeResult(
            target_runtime=request.target_runtime,
            code_purpose=request.code_purpose,
            generated_code=selected.code,
            model_name=model_name,
        )


class ASTCodeValidator:
    def validate(self, generated: GeneratedCodeResult, *, trace_id: UUID) -> CodeValidationOutcome:
        _ensure_project_python_paths()
        from ai_graph.security.ast_validator import validate_backtest_code

        result = validate_backtest_code(generated.generated_code)
        violation_codes = {violation.code for violation in result.violations}
        messages = [violation.message for violation in result.violations]
        return CodeValidationOutcome(
            is_safe=result.ok,
            syntax_valid="syntax.error" not in violation_codes,
            uses_allowed_imports=not any(code.startswith("import") for code in violation_codes),
            blocks_network_access=not any("network" in message.lower() or "socket" in message.lower() for message in messages),
            blocks_file_write=not any("open" in message.lower() or "file" in message.lower() for message in messages),
            warnings_jsonb=[],
            errors_jsonb=[{"code": violation.code, "message": violation.message, "line": violation.line} for violation in result.violations],
        )


class InProcessBacktestExecutor:
    async def execute(
        self,
        request: AICodeBacktestFlowRequest,
        generated: GeneratedCodeResult,
        *,
        trace_id: UUID,
        execution_run_id: UUID,
    ) -> CodeExecutionResult:
        _ensure_project_python_paths()
        from ai_graph.data_sources.db import load_pipeline_data_from_env
        from ai_graph.graph import build_strategy_spec
        from ai_graph.nodes import backtest as ai_backtest
        from ai_graph.schemas import CodeCandidate, StrategySpec

        strategy = (
            StrategySpec.model_validate(request.parsed_strategy_jsonb)
            if request.parsed_strategy_jsonb
            else build_strategy_spec(request.natural_language_prompt, variant="A", retrieval={"hits": []})
        )
        pipeline = load_pipeline_data_from_env(request.natural_language_prompt, str(trace_id))
        price_rows = pipeline.price_rows or None
        candidate = CodeCandidate(
            candidate_id="A1",
            variant="A",
            code=generated.generated_code,
            validation_ok=True,
            violations=[],
        )
        started_at = datetime.now(UTC)
        generated_signals = ai_backtest._execute_candidate_code(candidate, price_rows or ai_backtest.DEFAULT_BACKTEST_PRICE_ROWS)
        ohlcv_rows, metric_rows = ai_backtest._engine_market_rows(price_rows or ai_backtest.DEFAULT_BACKTEST_PRICE_ROWS)
        metric_rows = ai_backtest._merge_generated_signals(metric_rows, generated_signals)
        engine_spec = ai_backtest._engine_strategy_spec(
            strategy,
            candidate,
            available_ticker_count=ai_backtest._available_ticker_count(price_rows or ai_backtest.DEFAULT_BACKTEST_PRICE_ROWS),
        )
        engine_result = ai_backtest.run_engine_backtest(
            engine_spec,
            ohlcv_rows=ohlcv_rows,
            metric_rows=metric_rows,
            config=ai_backtest.EngineBacktestRunConfig(
                initial_capital=ai_backtest.DEFAULT_INITIAL_CAPITAL,
                write_outputs=False,
                talib=ai_backtest.EngineTalibIndicatorConfig(enabled=False, mode="none"),
            ),
        )
        ended_at = datetime.now(UTC)
        summary = dict(engine_result.summary)
        tickers = sorted({signal.ticker for signal in engine_result.signals})
        metric_detail = BacktestMetricDetailRecord(
            compare_json=summary.get("compare") or {},
            composition_json={
                "strategy_id": strategy.strategy_id,
                "tickers": tickers,
                "execution_audit": [event.as_dict() for event in getattr(engine_result, "order_audit", [])],
            },
            drawdown_detail_json=summary.get("drawdown_details") or [],
            drawdown_series_json=summary.get("drawdown_series") or [],
            greeks_json=summary.get("greeks") or {},
            rolling_returns_json={
                "rolling_volatility": summary.get("rolling_volatility") or [],
                "rolling_sharpe": summary.get("rolling_sharpe") or [],
                "rolling_sortino": summary.get("rolling_sortino") or [],
                "rolling_greeks": summary.get("rolling_greeks") or [],
            },
            monthly_return_json=summary.get("monthly_returns") or [],
            montecarlo_json=summary.get("montecarlo") or {},
            montecarlo_cagr_json=summary.get("montecarlo_cagr") or {},
            montecarlo_drawdown_json=summary.get("montecarlo_drawdown") or {},
            montecarlo_sharpe_json=summary.get("montecarlo_sharpe") or {},
            outliers_json=summary.get("outliers") or {},
        )
        payload = BacktestResultPayload(
            run=BacktestRunCreate(
                run_id=uuid4(),
                initial_capital=float(summary.get("initial_capital") or ai_backtest.DEFAULT_INITIAL_CAPITAL),
                max_tickers=len(tickers) or None,
                talib_mode="none",
                config_jsonb={"target_runtime": generated.target_runtime},
                backtest_start_date=_coerce_date(engine_result.equity_curve[0].date) if engine_result.equity_curve else None,
                backtest_end_date=_coerce_date(engine_result.equity_curve[-1].date) if engine_result.equity_curve else None,
                benchmark_ticker=request.benchmark_ticker,
                data_source=(pipeline.metadata.get("source") if pipeline.metadata else request.data_source),
                strategy_snapshot_jsonb=strategy.model_dump(mode="json"),
                universe_snapshot_jsonb={"tickers": tickers, "metadata": pipeline.metadata},
                as_of_at=ended_at,
                status="succeeded",
                started_at=started_at,
                ended_at=ended_at,
                output_paths_jsonb=getattr(engine_result, "output_paths", {}),
                execution_mode="ai_generated_code",
            ),
            summary=BacktestSummaryRecord(
                final_equity=summary.get("final_equity"),
                final_cash=summary.get("cash"),
                open_positions=summary.get("open_positions"),
                period_return=summary.get("period_return"),
                cagr=summary.get("cagr"),
                benchmark_return=ai_backtest._benchmark_return(price_rows or ai_backtest.DEFAULT_BACKTEST_PRICE_ROWS),
                alpha=(summary.get("compare") or {}).get("active_return") if isinstance(summary.get("compare"), dict) else None,
                beta=(summary.get("greeks") or {}).get("beta") if isinstance(summary.get("greeks"), dict) else None,
                max_drawdown=summary.get("max_drawdown"),
                volatility=summary.get("annualized_volatility") or summary.get("volatility"),
                sharpe_ratio=summary.get("sharpe_ratio") or summary.get("sharpe"),
                sortino_ratio=summary.get("sortino_ratio") or summary.get("sortino"),
                calmar_ratio=summary.get("calmar_ratio") or summary.get("calmar"),
                win_rate=summary.get("return_win_rate") or summary.get("win_rate"),
                profit_factor=summary.get("profit_factor"),
                payoff_ratio=summary.get("payoff_ratio"),
                avg_win=summary.get("avg_win"),
                avg_loss=summary.get("avg_loss"),
                max_consecutive_wins=summary.get("consecutive_positive_periods"),
                max_consecutive_losses=summary.get("consecutive_negative_periods"),
                trade_count=summary.get("trade_count"),
                signal_count=summary.get("signal_count"),
                avg_holding_days=summary.get("avg_holding_days"),
                turnover=summary.get("turnover"),
                total_commission=(summary.get("cost_model") or {}).get("commission_pct") if isinstance(summary.get("cost_model"), dict) else None,
                total_tax=(summary.get("cost_model") or {}).get("tax_pct") if isinstance(summary.get("cost_model"), dict) else None,
                total_slippage=(summary.get("cost_model") or {}).get("slippage_pct") if isinstance(summary.get("cost_model"), dict) else None,
                excluded_ticker_count=summary.get("excluded_ticker_count"),
                excluded_tickers_jsonb=summary.get("excluded_tickers") or [],
                indicator_report_jsonb=summary.get("indicator_report") or {},
                cost_model_jsonb=summary.get("cost_model") or {},
                position_sizing_jsonb=summary.get("position_sizing") or {},
                metrics_version="ai_graph_backtest_module_v1",
            ),
            metric_detail=metric_detail,
            equity_points=[
                BacktestEquityPointRecord(
                    trade_date=_coerce_date(point.date),
                    cash=point.cash,
                    positions_value=point.positions_value,
                    total_equity=point.total_equity,
                    daily_return=point.daily_return,
                )
                for point in engine_result.equity_curve
            ],
            signals=[
                BacktestSignalRecord(
                    signal_date=_coerce_date(signal.date),
                    scheduled_execution_date=None,
                    execution_timing=summary.get("execution_timing"),
                    sequence_no=index,
                    ticker=signal.ticker,
                    action=signal.action,
                    reasons=_split_reason(signal.reasons),
                    matching_entry_rules=_split_reason(signal.matching_entry_rules),
                    matching_exit_rules=_split_reason(signal.matching_exit_rules),
                )
                for index, signal in enumerate(engine_result.signals, start=1)
            ],
            trades=[
                BacktestTradeRecord(
                    ticker=trade.ticker,
                    entry_date=_coerce_date(trade.entry_date),
                    exit_date=_coerce_date(trade.exit_date) if trade.exit_date else None,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    quantity=trade.quantity,
                    entry_cost=trade.entry_cost,
                    exit_cost=trade.exit_cost,
                    gross_pnl=trade.gross_pnl,
                    net_pnl=trade.net_pnl,
                    return_pct=trade.return_pct,
                    reason=trade.reason,
                )
                for trade in engine_result.trades
            ],
        )
        return CodeExecutionResult(
            runtime_env=generated.target_runtime,
            status="succeeded",
            timeout_seconds=300,
            memory_limit_mb=512,
            sandbox_id="inprocess-mvp",
            latency_ms=round((ended_at - started_at).total_seconds() * 1000, 6),
            stdout="generated code executed successfully",
            stderr="",
            output_artifacts_jsonb={"source": pipeline.metadata.get("source") if pipeline.metadata else request.data_source},
            started_at=started_at,
            ended_at=ended_at,
            backtest_result=payload,
        )


class DeterministicBacktestReportGenerator:
    async def build_report(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        run_id: UUID,
        execution: CodeExecutionResult,
    ) -> AIBacktestReportDraft:
        summary = execution.backtest_result.summary if execution.backtest_result else None
        if summary is None:
            return AIBacktestReportDraft(
                overall_rating="failed",
                summary="No backtest result was available for report generation.",
                report_jsonb={"trace_id": str(trace_id), "run_id": str(run_id), "status": execution.status},
                model_name=request.report_model_name,
            )
        return AIBacktestReportDraft(
            period_return=summary.period_return,
            cagr=summary.cagr,
            max_drawdown=summary.max_drawdown,
            sharpe_ratio=summary.sharpe_ratio,
            sortino_ratio=summary.sortino_ratio,
            calmar_ratio=summary.calmar_ratio,
            win_rate=summary.win_rate,
            profit_factor=summary.profit_factor,
            volatility=summary.volatility,
            benchmark_return=summary.benchmark_return,
            overall_rating="pass" if (summary.period_return or 0) >= 0 else "watch",
            summary=(
                f"AI generated backtest for '{request.natural_language_prompt[:80]}' completed with "
                f"return {summary.period_return or 0:.4f} and sharpe {summary.sharpe_ratio or 0:.4f}."
            ),
            return_analysis="Generated code was validated and executed through the AI backtest flow.",
            risk_analysis=f"Max drawdown was {summary.max_drawdown or 0:.4f}.",
            trade_analysis=f"Trade count: {summary.trade_count or 0}, win rate: {summary.win_rate or 0:.4f}.",
            benchmark_analysis=f"Benchmark return: {summary.benchmark_return or 0:.4f}.",
            improvement_suggestions="Review generated assumptions and compare with live market adapters before production trading.",
            report_jsonb={
                "trace_id": str(trace_id),
                "run_id": str(run_id),
                "execution_status": execution.status,
                "strategy_id": request.strategy_id,
            },
            model_name=request.report_model_name,
        )


def _coerce_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _split_reason(value: str) -> list[str]:
    if not value:
        return []
    return [part for part in str(value).split(";") if part]
