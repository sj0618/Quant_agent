from __future__ import annotations

import math
import os
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.schemas.ai_backtest import (
    AICodeBacktestFlowRequest,
    BacktestEquityPointRecord,
    BacktestMetricDetailRecord,
    BacktestResultPayload,
    BacktestRunCreate,
    BacktestSignalRecord,
    BacktestSummaryRecord,
    BacktestTradeRecord,
    CodeExecutionResult,
    GeneratedCodeResult,
)

_RELEASE_BYTE = b"\x01"
_RELEASE_FAILURE_EXIT_CODE = 2


def _await_release(release_spec: str) -> bool:
    if release_spec.startswith("path:"):
        release_path = Path(release_spec.removeprefix("path:"))
        while not release_path.exists():
            time.sleep(0.01)
        try:
            return release_path.read_bytes() == _RELEASE_BYTE
        finally:
            release_path.unlink(missing_ok=True)
    fd_spec = release_spec.removeprefix("fd:")
    try:
        # Keep accepting the legacy raw descriptor form for direct runner callers;
        # the executor uses the explicit ``fd:``/``path:`` forms.
        release_fd = int(fd_spec)
    except ValueError:
        return False
    try:
        if os.read(release_fd, 1) != _RELEASE_BYTE:
            return False
        return os.read(release_fd, 1) == b""
    finally:
        os.close(release_fd)

def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 5:
        raise SystemExit(
            "usage: python -m app.services.ai_backtest_subprocess_runner "
            "<request.json> <generated_code.py> <result.json> <trace_id> <release_fd>"
        )
    request_path = Path(args[0])
    code_path = Path(args[1])
    result_path = Path(args[2])
    trace_id = UUID(args[3])
    if not _await_release(args[4]):
        return _RELEASE_FAILURE_EXIT_CODE

    request = AICodeBacktestFlowRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    generated = GeneratedCodeResult(
        target_runtime=request.target_runtime,
        code_purpose=request.code_purpose,
        generated_code=code_path.read_text(encoding="utf-8"),
    )
    result = _execute_generated_backtest(request, generated, trace_id=trace_id)
    result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return 0


def _execute_generated_backtest(
    request: AICodeBacktestFlowRequest,
    generated: GeneratedCodeResult,
    *,
    trace_id: UUID,
) -> CodeExecutionResult:
    from ai_graph.data_sources import load_pipeline_data_from_env
    from ai_graph.nodes import backtest as ai_backtest
    from ai_graph.schemas import CodeCandidate, StrategySpec

    if not request.parsed_strategy_jsonb:
        raise ValueError("generated backtest requires a sealed strategy with a backtest period")
    strategy = StrategySpec.model_validate(request.parsed_strategy_jsonb)
    if strategy.backtest_years is None:
        raise ValueError("generated backtest requires a sealed strategy with a backtest period")
    pipeline = load_pipeline_data_from_env(
        request.natural_language_prompt,
        str(trace_id),
        backtest_lookback_years=strategy.backtest_years,
        period_locked=True,
    )
    rows = pipeline.price_rows or list(ai_backtest.DEFAULT_BACKTEST_PRICE_ROWS)
    candidate = CodeCandidate(
        candidate_id="A1",
        variant="A",
        code=generated.generated_code,
        validation_ok=True,
        violations=[],
    )
    started_at = datetime.now(UTC)
    generated_signals = ai_backtest._execute_candidate_code(candidate, rows)
    ohlcv_rows, metric_rows = ai_backtest._engine_market_rows(rows)
    metric_rows = ai_backtest._merge_generated_signals(metric_rows, generated_signals)
    engine_spec = ai_backtest._engine_strategy_spec(
        strategy,
        candidate,
        available_ticker_count=ai_backtest._available_ticker_count(rows),
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
    cost_totals = _realized_cost_totals(
        trades=engine_result.trades,
        ohlcv_rows=ohlcv_rows,
        cost_model=summary.get("cost_model"),
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
            candidate_snapshot_jsonb={"tickers": tickers, "metadata": pipeline.metadata},
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
            benchmark_return=ai_backtest._benchmark_return(rows),
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
            total_commission=cost_totals[0],
            total_tax=cost_totals[1],
            total_slippage=cost_totals[2],
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
        timeout_seconds=request.timeout_seconds,
        memory_limit_mb=request.memory_limit_mb,
        sandbox_id="subprocess-sandbox",
        latency_ms=round((ended_at - started_at).total_seconds() * 1000, 6),
        stdout="generated code executed successfully",
        stderr="",
        output_artifacts_jsonb={"source": pipeline.metadata.get("source") if pipeline.metadata else request.data_source},
        started_at=started_at,
        ended_at=ended_at,
        backtest_result=payload,
    )


def _realized_cost_totals(*, trades: list[object], ohlcv_rows: list[object], cost_model: object) -> tuple[float | None, float | None, float | None]:
    if not isinstance(cost_model, dict):
        return None, None, None

    commission_pct = _nonnegative_finite_float(cost_model.get("commission_pct"))
    tax_pct = _nonnegative_finite_float(cost_model.get("tax_pct"))
    slippage_pct = _nonnegative_finite_float(cost_model.get("slippage_pct"))
    if commission_pct is None or tax_pct is None or slippage_pct is None:
        return None, None, None

    commission_total = 0.0
    tax_total = 0.0
    slippage_total = 0.0
    slippage_complete = True
    open_prices = _open_prices_by_trade_key(ohlcv_rows)
    exit_cost_rate = commission_pct + tax_pct

    for trade in trades:
        entry_cost = _nonnegative_finite_float(getattr(trade, "entry_cost", None))
        exit_cost = _nonnegative_finite_float(getattr(trade, "exit_cost", None))
        if entry_cost is None or exit_cost is None:
            return None, None, None

        commission_total += entry_cost
        if exit_cost_rate:
            commission_total += exit_cost * commission_pct / exit_cost_rate
            tax_total += exit_cost * tax_pct / exit_cost_rate
        elif exit_cost:
            return None, None, None

        quantity = _nonnegative_finite_float(getattr(trade, "quantity", None))
        entry_price = _nonnegative_finite_float(getattr(trade, "entry_price", None))
        exit_price = _nonnegative_finite_float(getattr(trade, "exit_price", None))
        try:
            entry_key = (_coerce_date(getattr(trade, "entry_date")), str(getattr(trade, "ticker")))
            exit_key = (_coerce_date(getattr(trade, "exit_date")), str(getattr(trade, "ticker")))
        except (TypeError, ValueError):
            slippage_complete = False
            continue
        entry_open = open_prices.get(entry_key)
        exit_open = open_prices.get(exit_key)
        if None in (quantity, entry_price, exit_price, entry_open, exit_open):
            slippage_complete = False
            continue
        slippage_total += quantity * (abs(entry_price - entry_open) + abs(exit_price - exit_open))

    return commission_total, tax_total, slippage_total if slippage_complete else None


def _open_prices_by_trade_key(ohlcv_rows: list[object]) -> dict[tuple[date, str], float]:
    prices: dict[tuple[date, str], float] = {}
    for row in ohlcv_rows:
        try:
            open_price = _nonnegative_finite_float(getattr(row, "open"))
            row_date = _coerce_date(getattr(row, "date"))
            ticker = str(getattr(row, "ticker"))
        except (AttributeError, TypeError, ValueError):
            continue
        if open_price is not None:
            prices[(row_date, ticker)] = open_price
    return prices


def _nonnegative_finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None

def _coerce_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _split_reason(value: str) -> list[str]:
    if not value:
        return []
    return [part for part in str(value).split(";") if part]


if __name__ == "__main__":
    raise SystemExit(main())
