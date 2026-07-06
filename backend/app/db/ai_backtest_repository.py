from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import redact_secrets
from app.core.errors import AppError
from app.schemas.ai_backtest import (
    AIBacktestReportCreate,
    AICodeGenerationCreate,
    AICodeValidationResultCreate,
    AIErrorLogCreate,
    AIStrategyParseCreate,
    AITraceCreate,
    AgentExecutionLogCreate,
    AgentExecutionLogUpdate,
    BacktestResultPayload,
    CodeExecutionRunCreate,
    CodeExecutionRunUpdate,
    ModelCallLogBundle,
)


class AIBacktestRepository(Protocol):
    async def create_trace(self, record: AITraceCreate) -> UUID: ...

    async def finish_trace(
        self,
        trace_id: UUID,
        *,
        status: str,
        metadata_jsonb: Mapping[str, Any] | None = None,
        ended_at: datetime | None = None,
    ) -> None: ...

    async def create_strategy_parse(self, record: AIStrategyParseCreate) -> UUID: ...

    async def create_code_generation(self, record: AICodeGenerationCreate) -> UUID: ...

    async def update_code_generation_status(self, code_id: UUID, status: str) -> None: ...

    async def create_code_validation_result(self, record: AICodeValidationResultCreate) -> UUID: ...

    async def create_code_execution_run(self, record: CodeExecutionRunCreate) -> UUID: ...

    async def update_code_execution_run(self, execution_run_id: UUID, update: CodeExecutionRunUpdate) -> None: ...

    async def persist_backtest_result(self, payload: BacktestResultPayload) -> UUID: ...

    async def create_ai_backtest_report(self, record: AIBacktestReportCreate) -> UUID: ...

    async def create_model_call_log(
        self,
        *,
        trace_id: UUID | None,
        user_id: int | None,
        session_id: UUID | None,
        message_id: UUID | None,
        code_id: UUID | None,
        bundle: ModelCallLogBundle,
    ) -> UUID: ...

    async def create_agent_execution_log(self, record: AgentExecutionLogCreate) -> UUID: ...

    async def update_agent_execution_log(self, execution_id: UUID, update: AgentExecutionLogUpdate) -> None: ...

    async def create_error_log(self, record: AIErrorLogCreate) -> UUID: ...


class SqlAIBacktestRepository:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def create_trace(self, record: AITraceCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_trace (
                trace_id, user_id, session_id, trace_kind, status,
                metadata_jsonb, started_at, ended_at
            ) VALUES (
                :trace_id, :user_id, :session_id, :trace_kind, :status,
                :metadata_jsonb::jsonb, :started_at, :ended_at
            )
            """,
            {
                "trace_id": str(record.trace_id),
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "trace_kind": record.trace_kind,
                "status": record.status,
                "metadata_jsonb": _json_dumps(record.metadata_jsonb),
                "started_at": record.started_at or _utcnow(),
                "ended_at": record.ended_at,
            },
        )
        return record.trace_id

    async def finish_trace(
        self,
        trace_id: UUID,
        *,
        status: str,
        metadata_jsonb: Mapping[str, Any] | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        await self._execute(
            """
            UPDATE app.ai_trace
            SET status = :status,
                metadata_jsonb = COALESCE(:metadata_jsonb::jsonb, metadata_jsonb),
                ended_at = :ended_at
            WHERE trace_id = :trace_id
            """,
            {
                "trace_id": str(trace_id),
                "status": status,
                "metadata_jsonb": _json_dumps(metadata_jsonb) if metadata_jsonb is not None else None,
                "ended_at": ended_at or _utcnow(),
            },
        )

    async def create_strategy_parse(self, record: AIStrategyParseCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_strategy_parse (
                parse_id, session_id, user_id, trace_id, raw_prompt,
                parsed_strategy_jsonb, confidence, model_name, parse_status
            ) VALUES (
                :parse_id, :session_id, :user_id, :trace_id, :raw_prompt,
                :parsed_strategy_jsonb::jsonb, :confidence, :model_name, :parse_status
            )
            """,
            {
                "parse_id": str(record.parse_id),
                "session_id": str(record.session_id) if record.session_id else None,
                "user_id": record.user_id,
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "raw_prompt": record.raw_prompt,
                "parsed_strategy_jsonb": _json_dumps(record.parsed_strategy_jsonb),
                "confidence": record.confidence,
                "model_name": record.model_name,
                "parse_status": record.parse_status,
            },
        )
        return record.parse_id

    async def create_code_generation(self, record: AICodeGenerationCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_code_generation (
                code_id, parse_id, user_id, session_id, trace_id,
                source_message_id, target_runtime, code_purpose,
                generated_code, code_hash, model_name, code_status
            ) VALUES (
                :code_id, :parse_id, :user_id, :session_id, :trace_id,
                :source_message_id, :target_runtime, :code_purpose,
                :generated_code, :code_hash, :model_name, :code_status
            )
            """,
            {
                "code_id": str(record.code_id),
                "parse_id": str(record.parse_id) if record.parse_id else None,
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "source_message_id": str(record.source_message_id) if record.source_message_id else None,
                "target_runtime": record.target_runtime,
                "code_purpose": record.code_purpose,
                "generated_code": record.generated_code,
                "code_hash": record.code_hash,
                "model_name": record.model_name,
                "code_status": record.code_status,
            },
        )
        return record.code_id

    async def update_code_generation_status(self, code_id: UUID, status: str) -> None:
        await self._execute(
            """
            UPDATE app.ai_code_generation
            SET code_status = :status,
                updated_at = :updated_at
            WHERE code_id = :code_id
            """,
            {
                "code_id": str(code_id),
                "status": status,
                "updated_at": _utcnow(),
            },
        )

    async def create_code_validation_result(self, record: AICodeValidationResultCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_code_validation_result (
                validation_id, code_id, is_safe, syntax_valid,
                uses_allowed_imports, blocks_network_access,
                blocks_file_write, warnings_jsonb, errors_jsonb
            ) VALUES (
                :validation_id, :code_id, :is_safe, :syntax_valid,
                :uses_allowed_imports, :blocks_network_access,
                :blocks_file_write, :warnings_jsonb::jsonb, :errors_jsonb::jsonb
            )
            """,
            {
                "validation_id": str(record.validation_id),
                "code_id": str(record.code_id),
                "is_safe": record.is_safe,
                "syntax_valid": record.syntax_valid,
                "uses_allowed_imports": record.uses_allowed_imports,
                "blocks_network_access": record.blocks_network_access,
                "blocks_file_write": record.blocks_file_write,
                "warnings_jsonb": _json_dumps(record.warnings_jsonb),
                "errors_jsonb": _json_dumps(record.errors_jsonb),
            },
        )
        return record.validation_id

    async def create_code_execution_run(self, record: CodeExecutionRunCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.code_execution_run (
                execution_run_id, code_id, user_id, session_id, trace_id,
                runtime_env, sandbox_id, status, timeout_seconds,
                memory_limit_mb, latency_ms, stdout, stderr,
                output_artifacts_jsonb, started_at, ended_at
            ) VALUES (
                :execution_run_id, :code_id, :user_id, :session_id, :trace_id,
                :runtime_env, :sandbox_id, :status, :timeout_seconds,
                :memory_limit_mb, :latency_ms, :stdout, :stderr,
                :output_artifacts_jsonb::jsonb, :started_at, :ended_at
            )
            """,
            {
                "execution_run_id": str(record.execution_run_id),
                "code_id": str(record.code_id),
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "runtime_env": record.runtime_env,
                "sandbox_id": record.sandbox_id,
                "status": record.status,
                "timeout_seconds": record.timeout_seconds,
                "memory_limit_mb": record.memory_limit_mb,
                "latency_ms": record.latency_ms,
                "stdout": record.stdout,
                "stderr": record.stderr,
                "output_artifacts_jsonb": _json_dumps(record.output_artifacts_jsonb) if record.output_artifacts_jsonb is not None else None,
                "started_at": record.started_at,
                "ended_at": record.ended_at,
            },
        )
        return record.execution_run_id

    async def update_code_execution_run(self, execution_run_id: UUID, update: CodeExecutionRunUpdate) -> None:
        await self._execute(
            """
            UPDATE app.code_execution_run
            SET status = :status,
                latency_ms = :latency_ms,
                stdout = :stdout,
                stderr = :stderr,
                output_artifacts_jsonb = :output_artifacts_jsonb::jsonb,
                sandbox_id = :sandbox_id,
                started_at = COALESCE(:started_at, started_at),
                ended_at = :ended_at
            WHERE execution_run_id = :execution_run_id
            """,
            {
                "execution_run_id": str(execution_run_id),
                "status": update.status,
                "latency_ms": update.latency_ms,
                "stdout": update.stdout,
                "stderr": update.stderr,
                "output_artifacts_jsonb": _json_dumps(update.output_artifacts_jsonb) if update.output_artifacts_jsonb is not None else None,
                "sandbox_id": update.sandbox_id,
                "started_at": update.started_at,
                "ended_at": update.ended_at,
            },
        )

    async def persist_backtest_result(self, payload: BacktestResultPayload) -> UUID:
        async with self.engine.begin() as conn:
            try:
                run = payload.run
                await conn.execute(
                    text(
                        """
                        INSERT INTO app.backtest_run (
                            run_id, strategy_id, user_id, session_id, source_parse_id,
                            code_id, execution_run_id, trace_id, initial_capital, max_tickers,
                            talib_mode, config_jsonb, backtest_start_date, backtest_end_date,
                            benchmark_ticker, data_source, strategy_snapshot_jsonb,
                            universe_snapshot_jsonb, as_of_at, status, started_at,
                            ended_at, error_message, output_paths_jsonb, execution_mode
                        ) VALUES (
                            :run_id, :strategy_id, :user_id, :session_id, :source_parse_id,
                            :code_id, :execution_run_id, :trace_id, :initial_capital, :max_tickers,
                            :talib_mode, :config_jsonb::jsonb, :backtest_start_date, :backtest_end_date,
                            :benchmark_ticker, :data_source, :strategy_snapshot_jsonb::jsonb,
                            :universe_snapshot_jsonb::jsonb, :as_of_at, :status, :started_at,
                            :ended_at, :error_message, :output_paths_jsonb::jsonb, :execution_mode
                        )
                        """
                    ),
                    {
                        "run_id": str(run.run_id),
                        "strategy_id": run.strategy_id,
                        "user_id": run.user_id,
                        "session_id": str(run.session_id) if run.session_id else None,
                        "source_parse_id": str(run.source_parse_id) if run.source_parse_id else None,
                        "code_id": str(run.code_id) if run.code_id else None,
                        "execution_run_id": str(run.execution_run_id) if run.execution_run_id else None,
                        "trace_id": str(run.trace_id) if run.trace_id else None,
                        "initial_capital": run.initial_capital,
                        "max_tickers": run.max_tickers,
                        "talib_mode": run.talib_mode,
                        "config_jsonb": _json_dumps(run.config_jsonb),
                        "backtest_start_date": run.backtest_start_date,
                        "backtest_end_date": run.backtest_end_date,
                        "benchmark_ticker": run.benchmark_ticker,
                        "data_source": run.data_source,
                        "strategy_snapshot_jsonb": _json_dumps(run.strategy_snapshot_jsonb),
                        "universe_snapshot_jsonb": _json_dumps(run.universe_snapshot_jsonb),
                        "as_of_at": run.as_of_at,
                        "status": run.status,
                        "started_at": run.started_at,
                        "ended_at": run.ended_at,
                        "error_message": run.error_message,
                        "output_paths_jsonb": _json_dumps(run.output_paths_jsonb),
                        "execution_mode": run.execution_mode,
                    },
                )

                summary = payload.summary
                await conn.execute(
                    text(
                        """
                        INSERT INTO app.backtest_summary (
                            summary_id, run_id, final_equity, final_cash, open_positions,
                            period_return, cagr, benchmark_return, alpha, beta,
                            max_drawdown, volatility, sharpe_ratio, sortino_ratio,
                            calmar_ratio, win_rate, profit_factor, payoff_ratio,
                            avg_win, avg_loss, max_consecutive_wins, max_consecutive_losses,
                            trade_count, signal_count, avg_holding_days, turnover,
                            total_commission, total_tax, total_slippage,
                            excluded_ticker_count, excluded_tickers_jsonb,
                            indicator_report_jsonb, cost_model_jsonb,
                            position_sizing_jsonb, metrics_version
                        ) VALUES (
                            gen_random_uuid(), :run_id, :final_equity, :final_cash, :open_positions,
                            :period_return, :cagr, :benchmark_return, :alpha, :beta,
                            :max_drawdown, :volatility, :sharpe_ratio, :sortino_ratio,
                            :calmar_ratio, :win_rate, :profit_factor, :payoff_ratio,
                            :avg_win, :avg_loss, :max_consecutive_wins, :max_consecutive_losses,
                            :trade_count, :signal_count, :avg_holding_days, :turnover,
                            :total_commission, :total_tax, :total_slippage,
                            :excluded_ticker_count, :excluded_tickers_jsonb::jsonb,
                            :indicator_report_jsonb::jsonb, :cost_model_jsonb::jsonb,
                            :position_sizing_jsonb::jsonb, :metrics_version
                        )
                        """
                    ),
                    {"run_id": str(run.run_id), **_summary_params(summary)},
                )

                detail = payload.metric_detail
                await conn.execute(
                    text(
                        """
                        INSERT INTO app.backtest_metric_detail (
                            run_id, compare_json, composition_json, drawdown_detail_json,
                            drawdown_series_json, greeks_json, rolling_returns_json,
                            monthly_return_json, montecarlo_json, montecarlo_cagr_json,
                            montecarlo_drawdown_json, montecarlo_sharpe_json, outliers_json
                        ) VALUES (
                            :run_id, :compare_json::jsonb, :composition_json::jsonb, :drawdown_detail_json::jsonb,
                            :drawdown_series_json::jsonb, :greeks_json::jsonb, :rolling_returns_json::jsonb,
                            :monthly_return_json::jsonb, :montecarlo_json::jsonb, :montecarlo_cagr_json::jsonb,
                            :montecarlo_drawdown_json::jsonb, :montecarlo_sharpe_json::jsonb, :outliers_json::jsonb
                        )
                        """
                    ),
                    {"run_id": str(run.run_id), **_metric_detail_params(detail)},
                )

                if payload.equity_points:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO app.backtest_equity_point (
                                point_id, run_id, trade_date, cash,
                                positions_value, total_equity, daily_return
                            ) VALUES (
                                gen_random_uuid(), :run_id, :trade_date, :cash,
                                :positions_value, :total_equity, :daily_return
                            )
                            """
                        ),
                        [
                            {
                                "run_id": str(run.run_id),
                                "trade_date": point.trade_date,
                                "cash": point.cash,
                                "positions_value": point.positions_value,
                                "total_equity": point.total_equity,
                                "daily_return": point.daily_return,
                            }
                            for point in payload.equity_points
                        ],
                    )

                if payload.signals:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO app.backtest_signal (
                                run_id, signal_date, scheduled_execution_date,
                                execution_timing, sequence_no, ticker, action,
                                reasons, matching_entry_rules, matching_exit_rules
                            ) VALUES (
                                :run_id, :signal_date, :scheduled_execution_date,
                                :execution_timing, :sequence_no, :ticker, :action,
                                :reasons::jsonb, :matching_entry_rules::jsonb, :matching_exit_rules::jsonb
                            )
                            """
                        ),
                        [
                            {
                                "run_id": str(run.run_id),
                                "signal_date": signal.signal_date,
                                "scheduled_execution_date": signal.scheduled_execution_date,
                                "execution_timing": signal.execution_timing,
                                "sequence_no": signal.sequence_no,
                                "ticker": signal.ticker,
                                "action": signal.action,
                                "reasons": _json_dumps(signal.reasons),
                                "matching_entry_rules": _json_dumps(signal.matching_entry_rules),
                                "matching_exit_rules": _json_dumps(signal.matching_exit_rules),
                            }
                            for signal in payload.signals
                        ],
                    )

                if payload.trades:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO app.backtest_trade (
                                run_id, entry_signal_id, exit_signal_id, ticker,
                                entry_date, exit_date, entry_price, exit_price,
                                quantity, entry_cost, exit_cost, gross_pnl,
                                net_pnl, return_pct, reason
                            ) VALUES (
                                :run_id, :entry_signal_id, :exit_signal_id, :ticker,
                                :entry_date, :exit_date, :entry_price, :exit_price,
                                :quantity, :entry_cost, :exit_cost, :gross_pnl,
                                :net_pnl, :return_pct, :reason
                            )
                            """
                        ),
                        [
                            {
                                "run_id": str(run.run_id),
                                "entry_signal_id": trade.entry_signal_id,
                                "exit_signal_id": trade.exit_signal_id,
                                "ticker": trade.ticker,
                                "entry_date": trade.entry_date,
                                "exit_date": trade.exit_date,
                                "entry_price": trade.entry_price,
                                "exit_price": trade.exit_price,
                                "quantity": trade.quantity,
                                "entry_cost": trade.entry_cost,
                                "exit_cost": trade.exit_cost,
                                "gross_pnl": trade.gross_pnl,
                                "net_pnl": trade.net_pnl,
                                "return_pct": trade.return_pct,
                                "reason": trade.reason,
                            }
                            for trade in payload.trades
                        ],
                    )
            except AppError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise self._db_error(exc) from exc
        return payload.run.run_id

    async def create_ai_backtest_report(self, record: AIBacktestReportCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_backtest_report (
                report_id, run_id, user_id, trace_id, period_return, cagr,
                max_drawdown, sharpe_ratio, sortino_ratio, calmar_ratio,
                win_rate, profit_factor, volatility, benchmark_return,
                overall_rating, summary, return_analysis, risk_analysis,
                trade_analysis, benchmark_analysis, improvement_suggestions,
                report_jsonb, model_name
            ) VALUES (
                :report_id, :run_id, :user_id, :trace_id, :period_return, :cagr,
                :max_drawdown, :sharpe_ratio, :sortino_ratio, :calmar_ratio,
                :win_rate, :profit_factor, :volatility, :benchmark_return,
                :overall_rating, :summary, :return_analysis, :risk_analysis,
                :trade_analysis, :benchmark_analysis, :improvement_suggestions,
                :report_jsonb::jsonb, :model_name
            )
            """,
            {
                "report_id": str(record.report_id),
                "run_id": str(record.run_id),
                "user_id": record.user_id,
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "period_return": record.period_return,
                "cagr": record.cagr,
                "max_drawdown": record.max_drawdown,
                "sharpe_ratio": record.sharpe_ratio,
                "sortino_ratio": record.sortino_ratio,
                "calmar_ratio": record.calmar_ratio,
                "win_rate": record.win_rate,
                "profit_factor": record.profit_factor,
                "volatility": record.volatility,
                "benchmark_return": record.benchmark_return,
                "overall_rating": record.overall_rating,
                "summary": record.summary,
                "return_analysis": record.return_analysis,
                "risk_analysis": record.risk_analysis,
                "trade_analysis": record.trade_analysis,
                "benchmark_analysis": record.benchmark_analysis,
                "improvement_suggestions": record.improvement_suggestions,
                "report_jsonb": _json_dumps(record.report_jsonb),
                "model_name": record.model_name,
            },
        )
        return record.report_id

    async def create_model_call_log(
        self,
        *,
        trace_id: UUID | None,
        user_id: int | None,
        session_id: UUID | None,
        message_id: UUID | None,
        code_id: UUID | None,
        bundle: ModelCallLogBundle,
    ) -> UUID:
        call_id = uuid4()
        await self._execute(
            """
            INSERT INTO app.ai_model_call_log (
                call_id, trace_id, user_id, session_id, message_id, code_id,
                task_type, provider, provider_request_id, model_name,
                temperature, top_p, seed, prompt_tokens, completion_tokens,
                total_tokens, latency_ms, cost, retry_count, cache_hit,
                tool_calls_jsonb, status, error_message
            ) VALUES (
                :call_id, :trace_id, :user_id, :session_id, :message_id, :code_id,
                :task_type, :provider, :provider_request_id, :model_name,
                :temperature, :top_p, :seed, :prompt_tokens, :completion_tokens,
                :total_tokens, :latency_ms, :cost, :retry_count, :cache_hit,
                :tool_calls_jsonb::jsonb, :status, :error_message
            )
            """,
            {
                "call_id": str(call_id),
                "trace_id": str(trace_id) if trace_id else None,
                "user_id": user_id,
                "session_id": str(session_id) if session_id else None,
                "message_id": str(message_id) if message_id else None,
                "code_id": str(code_id) if code_id else None,
                "task_type": bundle.task_type,
                "provider": bundle.provider,
                "provider_request_id": bundle.provider_request_id,
                "model_name": bundle.model_name,
                "temperature": bundle.temperature,
                "top_p": bundle.top_p,
                "seed": bundle.seed,
                "prompt_tokens": bundle.prompt_tokens,
                "completion_tokens": bundle.completion_tokens,
                "total_tokens": bundle.total_tokens,
                "latency_ms": bundle.latency_ms,
                "cost": bundle.cost,
                "retry_count": bundle.retry_count,
                "cache_hit": bundle.cache_hit,
                "tool_calls_jsonb": _json_dumps(bundle.tool_calls_jsonb),
                "status": bundle.status,
                "error_message": bundle.error_message,
            },
        )
        if bundle.prompt_log is not None:
            await self._execute(
                """
                INSERT INTO app.ai_prompt_log (
                    prompt_log_id, call_id, user_id, session_id,
                    prompt_template_name, system_prompt, user_prompt,
                    assistant_response, variables_jsonb, prompt_version,
                    contains_pii, masked
                ) VALUES (
                    gen_random_uuid(), :call_id, :user_id, :session_id,
                    :prompt_template_name, :system_prompt, :user_prompt,
                    :assistant_response, :variables_jsonb::jsonb, :prompt_version,
                    :contains_pii, :masked
                )
                """,
                {
                    "call_id": str(call_id),
                    "user_id": user_id,
                    "session_id": str(session_id) if session_id else None,
                    "prompt_template_name": bundle.prompt_log.prompt_template_name,
                    "system_prompt": bundle.prompt_log.system_prompt,
                    "user_prompt": bundle.prompt_log.user_prompt,
                    "assistant_response": bundle.prompt_log.assistant_response,
                    "variables_jsonb": _json_dumps(bundle.prompt_log.variables_jsonb),
                    "prompt_version": bundle.prompt_log.prompt_version,
                    "contains_pii": bundle.prompt_log.contains_pii,
                    "masked": bundle.prompt_log.masked,
                },
            )
        return call_id

    async def create_agent_execution_log(self, record: AgentExecutionLogCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_agent_execution_log (
                execution_id, trace_id, user_id, session_id, run_id,
                execution_run_id, agent_name, step_name, status,
                input_jsonb, output_jsonb, error_message, latency_ms,
                started_at, ended_at
            ) VALUES (
                :execution_id, :trace_id, :user_id, :session_id, :run_id,
                :execution_run_id, :agent_name, :step_name, :status,
                :input_jsonb::jsonb, :output_jsonb::jsonb, :error_message, :latency_ms,
                :started_at, :ended_at
            )
            """,
            {
                "execution_id": str(record.execution_id),
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "run_id": str(record.run_id) if record.run_id else None,
                "execution_run_id": str(record.execution_run_id) if record.execution_run_id else None,
                "agent_name": record.agent_name,
                "step_name": record.step_name,
                "status": record.status,
                "input_jsonb": _json_dumps(record.input_jsonb),
                "output_jsonb": _json_dumps(record.output_jsonb),
                "error_message": record.error_message,
                "latency_ms": record.latency_ms,
                "started_at": record.started_at or _utcnow(),
                "ended_at": record.ended_at,
            },
        )
        return record.execution_id

    async def update_agent_execution_log(self, execution_id: UUID, update: AgentExecutionLogUpdate) -> None:
        await self._execute(
            """
            UPDATE app.ai_agent_execution_log
            SET status = :status,
                output_jsonb = :output_jsonb::jsonb,
                error_message = :error_message,
                latency_ms = :latency_ms,
                ended_at = :ended_at
            WHERE execution_id = :execution_id
            """,
            {
                "execution_id": str(execution_id),
                "status": update.status,
                "output_jsonb": _json_dumps(update.output_jsonb),
                "error_message": update.error_message,
                "latency_ms": update.latency_ms,
                "ended_at": update.ended_at or _utcnow(),
            },
        )

    async def create_error_log(self, record: AIErrorLogCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_error_log (
                error_id, trace_id, user_id, session_id, call_id,
                execution_id, execution_run_id, error_type, error_message,
                stack_trace, context_jsonb, severity
            ) VALUES (
                :error_id, :trace_id, :user_id, :session_id, :call_id,
                :execution_id, :execution_run_id, :error_type, :error_message,
                :stack_trace, :context_jsonb::jsonb, :severity
            )
            """,
            {
                "error_id": str(record.error_id),
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "call_id": str(record.call_id) if record.call_id else None,
                "execution_id": str(record.execution_id) if record.execution_id else None,
                "execution_run_id": str(record.execution_run_id) if record.execution_run_id else None,
                "error_type": record.error_type,
                "error_message": record.error_message,
                "stack_trace": record.stack_trace,
                "context_jsonb": _json_dumps(record.context_jsonb),
                "severity": record.severity,
            },
        )
        return record.error_id

    async def _execute(self, sql: str, params: Mapping[str, Any]) -> None:
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text(sql), params)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc

    def _db_error(self, exc: Exception) -> AppError:
        return AppError(
            status_code=503,
            component="db",
            code="db_query_failed",
            message="Database query failed",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        )


def _summary_params(summary) -> dict[str, Any]:
    payload = summary.model_dump(mode="python")
    payload["excluded_tickers_jsonb"] = _json_dumps(payload["excluded_tickers_jsonb"])
    payload["indicator_report_jsonb"] = _json_dumps(payload["indicator_report_jsonb"])
    payload["cost_model_jsonb"] = _json_dumps(payload["cost_model_jsonb"])
    payload["position_sizing_jsonb"] = _json_dumps(payload["position_sizing_jsonb"])
    return payload


def _metric_detail_params(detail) -> dict[str, Any]:
    payload = detail.model_dump(mode="python")
    return {key: _json_dumps(value) for key, value in payload.items()}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _json_default(value: Any):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC)

