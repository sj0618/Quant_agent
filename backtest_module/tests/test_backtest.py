from datetime import date, datetime, timedelta

import pandas as pd
import pytest
import quantstats.stats as qs_stats

from backtest_module import (
    Condition,
    ConditionOperator,
    CostModel,
    PositionSizing,
    RiskControls,
    StrategySpec,
)
from backtest_module.models import CorporateActionEvent
from backtest_module.backtest import (
    BacktestRunConfig,
    EquityPoint,
    OhlcvBar,
    TalibIndicatorConfig,
    build_sample_spec,
    build_sample_talib_spec,
    required_metric_names,
    run_backtest,
    talib_function_catalog,
)
from backtest_module.performance import QUANTSTATS_REQUIRED_MESSAGE, calculate_quantstats_metrics


def bars(ticker="005930"):
    return [
        OhlcvBar(date=date(2026, 1, 2), ticker=ticker, open=100, high=105, low=95, close=104, volume=1000),
        OhlcvBar(date=date(2026, 1, 5), ticker=ticker, open=110, high=116, low=108, close=115, volume=1000),
        OhlcvBar(date=date(2026, 1, 6), ticker=ticker, open=116, high=118, low=112, close=114, volume=1000),
        OhlcvBar(date=date(2026, 1, 7), ticker=ticker, open=120, high=121, low=117, close=118, volume=1000),
    ]


def rsi_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="rsi_fixture",
        strategy_name="RSI Fixture",
        entry_rules=[Condition(left="rsi_14", operator=ConditionOperator.LTE, right=30, description="RSI <= 30")],
        exit_rules=[Condition(left="rsi_14", operator=ConditionOperator.GTE, right=70, description="RSI >= 70")],
        position_sizing=PositionSizing(max_positions=1),
        risk_controls=RiskControls(
            max_single_position_pct=1.0,
            stop_loss_pct=0.5,
            take_profit_pct=None,
        ),
        backtest={
            "cost_model": CostModel(commission_pct=0, tax_pct=0, slippage_pct=0).model_dump(),
            "execution_capacity": {"enabled": False},
        },
    )


def rsi_metrics(ticker="005930"):
    return [
        {"date": "2026-01-02", "ticker": ticker, "rsi_14": 25},
        {"date": "2026-01-05", "ticker": ticker, "rsi_14": 50},
        {"date": "2026-01-06", "ticker": ticker, "rsi_14": 80},
        {"date": "2026-01-07", "ticker": ticker, "rsi_14": 80},
    ]


def test_required_metric_names_extracts_string_operands():
    spec = StrategySpec(
        strategy_id="metric_to_metric",
        strategy_name="Metric To Metric",
        entry_rules=[Condition(left="macd", operator=ConditionOperator.CROSS_ABOVE, right="macd_signal")],
    )

    assert required_metric_names(spec) == {"macd", "macd_signal"}


def test_conservative_daily_engine_fills_next_open_and_records_trade():
    result = run_backtest(
        rsi_spec(),
        ohlcv_rows=bars(),
        metric_rows=rsi_metrics(),
        config=BacktestRunConfig(initial_capital=1000, write_outputs=False),
    )

    assert result.summary["trade_count"] == 1
    trade = result.trades[0]
    assert trade.entry_date == "2026-01-05"
    assert trade.entry_price == 110
    assert trade.exit_date == "2026-01-07"
    assert trade.exit_price == 120
    assert trade.quantity == 9
    assert result.summary["final_equity"] == 1090
    assert result.summary["period_return"] == 0.09
    assert [event.status for event in result.order_audit] == [
        "submitted",
        "executed",
        "submitted",
        "executed",
    ]
    assert [event.side for event in result.order_audit] == ["buy", "buy", "sell", "sell"]


def test_multi_ticker_buys_respect_single_and_gross_exposure_limits():
    tickers = ("000001", "000002", "000003")
    trade_dates = (date(2026, 1, 2), date(2026, 1, 5))
    result = run_backtest(
        StrategySpec(
            strategy_id="multi_ticker_risk_limits",
            strategy_name="Multi Ticker Risk Limits",
            entry_rules=[Condition(left="rsi_14", operator=ConditionOperator.LTE, right=30)],
            exit_rules=[Condition(left="rsi_14", operator=ConditionOperator.GTE, right=70)],
            position_sizing=PositionSizing(max_positions=3),
            risk_controls=RiskControls(
                max_gross_exposure_pct=0.5,
                max_single_position_pct=0.2,
                stop_loss_pct=0.5,
            ),
            backtest={
                "cost_model": CostModel(commission_pct=0, tax_pct=0, slippage_pct=0).model_dump(),
                "execution_capacity": {"enabled": False},
            },
        ),
        ohlcv_rows=[
            OhlcvBar(date=day, ticker=ticker, open=10, high=10, low=10, close=10, volume=1000)
            for day in trade_dates
            for ticker in tickers
        ],
        metric_rows=[
            {
                "date": day.isoformat(),
                "ticker": ticker,
                "rsi_14": 20 if day == trade_dates[0] else 50,
            }
            for day in trade_dates
            for ticker in tickers
        ],
        config=BacktestRunConfig(
            initial_capital=1000,
            write_outputs=False,
            talib=TalibIndicatorConfig(enabled=False, mode="none"),
        ),
    )

    buys = [event for event in result.order_audit if event.status == "executed" and event.side == "buy"]

    assert len(buys) == 3
    assert all(event.price * event.quantity <= 200 for event in buys)
    assert result.equity_curve[-1].positions_value <= 500


def test_all_2000_krx_tickers_run_without_score_filtering():
    tickers = tuple(f"{index:06d}" for index in range(1, 2001))
    trade_dates = (date(2026, 1, 2), date(2026, 1, 5))
    initial_capital = 100_000_000
    result = run_backtest(
        StrategySpec(
            strategy_id="all_krx_matches",
            strategy_name="All KRX Matches",
            entry_rules=[Condition(left="rsi_14", operator=ConditionOperator.LTE, right=30)],
            exit_rules=[Condition(left="rsi_14", operator=ConditionOperator.GTE, right=70)],
            position_sizing=PositionSizing(max_positions=len(tickers)),
            risk_controls=RiskControls(
                max_gross_exposure_pct=1.0,
                max_single_position_pct=1 / len(tickers),
                stop_loss_pct=0.5,
            ),
            backtest={
                "cost_model": CostModel(commission_pct=0, tax_pct=0, slippage_pct=0).model_dump(),
                "execution_capacity": {"enabled": False},
            },
        ),
        ohlcv_rows=[
            OhlcvBar(date=day, ticker=ticker, open=100, high=100, low=100, close=100, volume=1000)
            for day in trade_dates
            for ticker in tickers
        ],
        metric_rows=[
            {
                "date": day.isoformat(),
                "ticker": ticker,
                "rsi_14": 20 if day == trade_dates[0] else 50,
            }
            for day in trade_dates
            for ticker in tickers
        ],
        config=BacktestRunConfig(
            initial_capital=initial_capital,
            write_outputs=False,
            talib=TalibIndicatorConfig(enabled=False, mode="none"),
        ),
    )

    buys = [event for event in result.order_audit if event.status == "executed" and event.side == "buy"]

    assert len(buys) == len(tickers)
    assert result.summary["open_positions"] == len(tickers)
    assert result.summary["final_equity"] == initial_capital


def test_missing_required_metric_excludes_ticker_from_run():
    two_ticker_bars = bars("005930") + bars("000660")
    result = run_backtest(
        rsi_spec(),
        ohlcv_rows=two_ticker_bars,
        metric_rows=rsi_metrics("005930"),
        config=BacktestRunConfig(
            initial_capital=1000,
            write_outputs=False,
            talib=TalibIndicatorConfig(mode="none"),
        ),
    )

    assert result.summary["excluded_ticker_count"] == 1
    excluded = result.summary["excluded_tickers"][0]
    assert excluded["ticker"] == "000660"
    assert excluded["missing_metrics"] == ["rsi_14"]
    assert {signal.ticker for signal in result.signals} == {"005930"}


def test_outputs_are_written(tmp_path):
    result = run_backtest(
        rsi_spec(),
        ohlcv_rows=bars(),
        metric_rows=rsi_metrics(),
        config=BacktestRunConfig(initial_capital=1000, output_dir=tmp_path),
    )

    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "equity_curve.csv").exists()
    assert (tmp_path / "trades.csv").exists()
    assert (tmp_path / "signals.csv").exists()
    assert result.output_paths["summary_json"].endswith("summary.json")
    assert result.output_paths["order_audit_csv"].endswith("order_audit.csv")


def test_sample_spec_runs_without_external_metrics():
    result = run_backtest(
        build_sample_spec(),
        ohlcv_rows=bars(),
        config=BacktestRunConfig(initial_capital=1000, write_outputs=False),
    )

    assert result.summary["excluded_ticker_count"] == 0
    assert result.signals


def test_talib_catalog_marks_all_ohlcv_calculable_functions():
    catalog = talib_function_catalog()

    assert catalog["function_count"] >= 150
    assert catalog["calculable_from_ohlcv_count"] >= 150
    assert catalog["skipped"] == {"MAVP": ["periods"]}


def test_talib_required_mode_computes_rsi_metric_and_aliases():
    result = run_backtest(
        build_sample_talib_spec(),
        ohlcv_rows=bars(),
        config=BacktestRunConfig(initial_capital=1000, write_outputs=False),
    )

    indicator_report = result.summary["indicator_report"]
    assert "RSI" in indicator_report["computed_functions"]
    assert "rsi_14" in indicator_report["computed_metric_names"]
    assert result.summary["excluded_ticker_count"] == 0


def test_talib_required_mode_keeps_multiple_sma_periods():
    spec = StrategySpec(
        strategy_id="ma_cross_fixture",
        strategy_name="MA Cross Fixture",
        entry_rules=[Condition(left="ma_5", operator=ConditionOperator.CROSS_ABOVE, right="ma_20")],
        exit_rules=[Condition(left="ma_5", operator=ConditionOperator.CROSS_BELOW, right="ma_20")],
    )

    result = run_backtest(
        spec,
        ohlcv_rows=bars(),
        config=BacktestRunConfig(initial_capital=1000, write_outputs=False),
    )

    computed = set(result.summary["indicator_report"]["computed_metric_names"])
    assert {"ma_5", "ma_20"}.issubset(computed)
    assert result.summary["excluded_ticker_count"] == 0


def test_required_mode_computes_bmt_derived_metrics():
    spec = StrategySpec(
        strategy_id="derived_fixture",
        strategy_name="Derived Fixture",
        entry_rules=[
            Condition(left="volume_ratio_20", operator=ConditionOperator.GTE, right=1.0),
            Condition(left="rolling_high_60", operator=ConditionOperator.GTE, right=100.0),
            Condition(left="days_since_breakout", operator=ConditionOperator.LTE, right=10.0),
            Condition(left="close", operator=ConditionOperator.CROSS_ABOVE, right="bollinger_lower_20_2"),
        ],
        exit_rules=[Condition(left="close", operator=ConditionOperator.LT, right="ma_20")],
    )

    result = run_backtest(
        spec,
        ohlcv_rows=bars(),
        config=BacktestRunConfig(initial_capital=1000, write_outputs=False),
    )

    computed = set(result.summary["indicator_report"]["computed_metric_names"])
    assert {"volume_ratio_20", "rolling_high_60", "days_since_breakout", "bollinger_lower_20_2"}.issubset(
        computed
    )
    assert result.summary["excluded_ticker_count"] == 0


def test_talib_all_mode_computes_many_functions_from_ohlcv():
    result = run_backtest(
        build_sample_spec(),
        ohlcv_rows=bars(),
        config=BacktestRunConfig(
            initial_capital=1000,
            write_outputs=False,
            talib=TalibIndicatorConfig(mode="all"),
        ),
    )

    assert result.summary["indicator_report"]["talib_calculable_from_ohlcv_count"] >= 150
    assert result.summary["indicator_report"]["computed_function_count"] >= 150


def test_precomputed_metric_overrides_talib_value():
    spec = rsi_spec()
    result = run_backtest(
        spec,
        ohlcv_rows=bars(),
        metric_rows=[
            {"date": "2026-01-02", "ticker": "005930", "rsi_14": 10},
            {"date": "2026-01-05", "ticker": "005930", "rsi_14": 80},
            {"date": "2026-01-06", "ticker": "005930", "rsi_14": 80},
            {"date": "2026-01-07", "ticker": "005930", "rsi_14": 80},
        ],
        config=BacktestRunConfig(initial_capital=1000, write_outputs=False),
    )

    assert result.trades[0].entry_date == "2026-01-05"
    assert result.trades[0].exit_date == "2026-01-06"


def test_summary_includes_quantstats_metrics():
    result = run_backtest(
        rsi_spec(),
        ohlcv_rows=bars(),
        metric_rows=rsi_metrics(),
        config=BacktestRunConfig(initial_capital=1000, write_outputs=False),
    )

    metrics = result.summary["metrics"]

    for key in [
        "cagr",
        "sharpe",
        "max_drawdown",
        "total_return",
        "monthly_returns",
        "drawdown_details",
        "drawdown_series",
        "omega",
        "common_sense_ratio",
        "value_at_risk",
        "ulcer_index",
        "rolling_volatility",
        "rolling_sharpe",
        "rolling_sortino",
        "montecarlo",
        "montecarlo_cagr",
        "outliers",
    ]:
        assert key in metrics
    for key in [
        "cagr",
        "total_return",
        "monthly_returns",
        "drawdown_details",
        "drawdown_series",
        "omega",
        "common_sense_ratio",
        "value_at_risk",
        "ulcer_index",
        "rolling_volatility",
        "rolling_sharpe",
        "rolling_sortino",
        "montecarlo",
        "montecarlo_cagr",
        "outliers",
        "final_cash",
        "avg_holding_days",
        "sharpe_ratio",
        "conditional_value_at_risk",
        "annualized_volatility",
    ]:
        assert key in result.summary

    assert result.summary["period_return"] == metrics["total_return"]
    assert result.summary["daily_sharpe_like"] == metrics["sharpe"]
    assert result.summary["sharpe_ratio"] == metrics["sharpe_ratio"]
    assert result.summary["annualized_volatility"] == metrics["annualized_volatility"]
    assert result.summary["conditional_value_at_risk"] == metrics["conditional_value_at_risk"]
    assert result.summary["final_cash"] == result.summary["cash"]
    assert result.summary["monthly_returns"] == metrics["monthly_returns"]
    assert result.summary["drawdown_details"] == metrics["drawdown_details"]
    assert result.summary["drawdown_series"] == metrics["drawdown_series"]
    assert result.summary["montecarlo_cagr"] == metrics["montecarlo_cagr"]
    assert result.summary["win_rate"] == result.summary["trade_win_rate"]
    assert result.summary["return_win_rate"] == metrics["win_rate"]
    assert result.summary["avg_holding_days"] == 2.0
    assert isinstance(metrics["monthly_returns"], list)
    assert isinstance(metrics["drawdown_details"], list)
    assert isinstance(metrics["drawdown_series"], list)
    assert isinstance(metrics["rolling_volatility"], list)
    assert isinstance(metrics["rolling_sharpe"], list)
    assert isinstance(metrics["rolling_sortino"], list)
    assert isinstance(metrics["montecarlo"], dict)
    assert isinstance(metrics["montecarlo_mean"], list)
    assert isinstance(metrics["montecarlo_cagr"], dict)
    assert isinstance(metrics["outliers"], dict)
    assert metrics["montecarlo"]["simulations"] > 0
    assert metrics["information_ratio"] is None
    assert metrics["r_squared"] is None
    assert metrics["greeks"] is None
    assert result.summary["trade_win_rate"] == 1.0


def test_missing_quantstats_raises_clear_error(monkeypatch):
    real_import = __import__

    def raising_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "quantstats" or name.startswith("quantstats."):
            raise ImportError("quantstats unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", raising_import)

    with pytest.raises(ModuleNotFoundError, match=QUANTSTATS_REQUIRED_MESSAGE):
        calculate_quantstats_metrics(
            [
                {"date": "2026-01-02", "total_equity": 1000.0},
                {"date": "2026-01-03", "total_equity": 1010.0},
            ]
        )


def test_benchmark_metrics_use_benchmark_returns_not_raw_equity():
    equity_curve = [
        {"date": "2026-01-02", "total_equity": 100.0},
        {"date": "2026-01-03", "total_equity": 105.0},
        {"date": "2026-01-04", "total_equity": 95.0},
        {"date": "2026-01-05", "total_equity": 110.0},
    ]
    benchmark_curve = [
        {"date": "2026-01-02", "total_equity": 200.0},
        {"date": "2026-01-03", "total_equity": 202.0},
        {"date": "2026-01-04", "total_equity": 201.0},
        {"date": "2026-01-05", "total_equity": 205.0},
    ]

    metrics = calculate_quantstats_metrics(equity_curve, benchmark_returns=benchmark_curve)
    returns = pd.Series(
        [100.0, 105.0, 95.0, 110.0],
        index=pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]),
    ).pct_change().dropna()
    benchmark_returns = pd.Series(
        [200.0, 202.0, 201.0, 205.0],
        index=pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]),
    ).pct_change().dropna()

    assert metrics["information_ratio"] is not None
    assert metrics["r_squared"] is not None
    assert metrics["greeks"] is not None
    assert metrics["r_squared"] == pytest.approx(float(qs_stats.r_squared(returns, benchmark_returns)), rel=1e-6)
    assert metrics["compare"]
    assert isinstance(metrics["compare"]["cumulative"], list)
    assert isinstance(metrics["rolling_greeks"], list)


def test_single_point_equity_defaults_core_metrics_and_surfaces_warnings():
    metrics = calculate_quantstats_metrics(
        [
            {"date": "2026-01-02", "total_equity": 1000.0},
        ]
    )

    assert metrics["total_return"] == 0.0
    assert metrics["cagr"] == 0.0
    assert metrics["sharpe"] == 0.0
    assert metrics["adjusted_sortino"] == 0.0
    assert metrics["max_drawdown"] == 0.0
    assert metrics["win_rate"] == 0.0
    assert metrics["omega"] == 0.0
    assert metrics["monthly_returns"] == []
    assert metrics["drawdown_details"] == []
    assert metrics["drawdown_series"] == []
    assert metrics["rolling_volatility"] == []
    assert metrics["rolling_sharpe"] == []
    assert metrics["rolling_sortino"] == []
    assert metrics["information_ratio"] is None
    assert metrics["r_squared"] is None
    assert metrics["greeks"] is None
    assert metrics["compare"] == {}
    assert metrics["montecarlo"] == {}
    assert metrics["montecarlo_mean"] == []
    assert metrics["montecarlo_cagr"] == {}
    assert metrics["montecarlo_drawdown"] == {}
    assert metrics["montecarlo_sharpe"] == {}
    assert metrics["outliers"] == {}
    assert metrics["metric_warnings"]


def _delisting_scenario(*, grace_days, recovery_rate, survivor_days=40, doomed_days=3):
    """One name that keeps trading and one that stops after `doomed_days`."""

    days = [date(2026, 1, 1) + timedelta(days=n) for n in range(survivor_days)]
    rows = []
    for index, day in enumerate(days):
        rows.append(
            OhlcvBar(date=day, ticker="000001", open=100, high=100, low=100, close=100, volume=1000)
        )
        if index < doomed_days:
            rows.append(
                OhlcvBar(date=day, ticker="000002", open=100, high=100, low=100, close=100, volume=1000)
            )
    metrics = [
        {"date": row.date.isoformat(), "ticker": row.ticker, "rsi_14": 20 if row.date == days[0] else 50}
        for row in rows
    ]
    return run_backtest(
        StrategySpec(
            strategy_id="delisting",
            strategy_name="Delisting",
            entry_rules=[Condition(left="rsi_14", operator=ConditionOperator.LTE, right=30)],
            exit_rules=[Condition(left="rsi_14", operator=ConditionOperator.GTE, right=70)],
            position_sizing=PositionSizing(max_positions=2),
            risk_controls=RiskControls(
                max_gross_exposure_pct=1.0, max_single_position_pct=0.5, stop_loss_pct=0.9
            ),
            backtest={
                "cost_model": CostModel(
                    commission_pct=0, tax_pct=0, slippage_pct=0
                ).model_dump(),
                "execution_capacity": {"enabled": False},
            },
        ),
        ohlcv_rows=rows,
        metric_rows=metrics,
        config=BacktestRunConfig(
            initial_capital=1000,
            write_outputs=False,
            talib=TalibIndicatorConfig(enabled=False, mode="none"),
            delisting_grace_days=grace_days,
            delisting_recovery_rate=recovery_rate,
        ),
    )


def test_position_in_a_name_that_stops_trading_is_written_off_not_held_forever():
    """A delisted name used to keep its last quoted value in equity for the whole run.

    `last_price` is only refreshed on days the ticker has a bar, so the position was
    never sold, never marked down, and still counted toward final equity - and its
    capital never came back to fund another entry.
    """

    result = _delisting_scenario(grace_days=5, recovery_rate=0.0)

    write_offs = [t for t in result.trades if t.reason == "delisted_write_off"]
    assert [t.ticker for t in write_offs] == ["000002"]
    assert write_offs[0].exit_price == 0.0
    assert write_offs[0].net_pnl < 0
    assert result.summary["delisting"]["forced_exits"] == 1
    # The position is gone, so nothing unrealisable is left carrying the headline,
    # and only the surviving name is still held.
    assert result.summary["delisting"]["unrealizable_equity"] == 0.0
    assert result.summary["open_positions"] == 1


def test_write_off_respects_the_grace_period_and_the_recovery_rate():
    """A short suspension must not be treated as a delisting, and the recovery is a knob."""

    # Grace longer than the gap: the name is still held at its last close.
    held = _delisting_scenario(grace_days=100, recovery_rate=0.0)
    assert [t for t in held.trades if t.reason == "delisted_write_off"] == []
    assert held.summary["delisting"]["forced_exits"] == 0
    assert held.summary["delisting"]["unrealizable_equity"] > 0

    # Same scenario, but a holder recovers half of the last close.
    partial = _delisting_scenario(grace_days=5, recovery_rate=0.5)
    write_off = next(t for t in partial.trades if t.reason == "delisted_write_off")
    assert write_off.exit_price == 50.0
    assert partial.summary["delisting"]["recovery_rate"] == 0.5

def test_selection_metrics_vectorized_formula_matches_reference():
    from backtest_module.backtest import _calculate_selection_metrics
    import math

    equity_curve = [
        EquityPoint(date="2026-01-01", cash=100.0, positions_value=0.0, total_equity=100.0, daily_return=0.0),
        EquityPoint(date="2026-01-02", cash=102.0, positions_value=0.0, total_equity=102.0, daily_return=0.02),
        EquityPoint(date="2026-01-03", cash=101.0, positions_value=0.0, total_equity=101.0, daily_return=-0.01),
        EquityPoint(date="2026-01-04", cash=103.0, positions_value=0.0, total_equity=103.0, daily_return=0.02),
    ]
    metrics = _calculate_selection_metrics(equity_curve)

    usable = [0.02, -0.01, 0.02]
    mean_return = sum(usable) / len(usable)
    variance = ((0.02 - mean_return) ** 2 + (-0.01 - mean_return) ** 2 + (0.02 - mean_return) ** 2) / (len(usable) - 1)
    expected_sharpe = mean_return / math.sqrt(variance) * (252.0**0.5)
    expected_max_drawdown = min(
        0.0,
        102.0 / 102.0 - 1.0,
        101.0 / 102.0 - 1.0,
        103.0 / 103.0 - 1.0,
    )

    assert metrics["total_return"] == pytest.approx((103.0 / 100.0) - 1.0, rel=1e-10)
    assert metrics["cagr"] == pytest.approx((103.0 / 100.0) ** (365.0 / 3.0) - 1.0, rel=1e-10)
    assert metrics["sharpe"] == pytest.approx(round(expected_sharpe, 10), rel=1e-10)
    assert metrics["max_drawdown"] == pytest.approx(round(expected_max_drawdown, 10), rel=1e-10)
    assert metrics["win_rate"] == pytest.approx(2.0 / 3.0, rel=1e-10)
    assert metrics["profit_factor"] == pytest.approx(0.04 / 0.01, rel=1e-10)


def test_next_session_expiry_and_raw_capacity_are_fail_transparent():
    spec = rsi_spec()
    spec.backtest.execution_capacity.enabled = True
    result = run_backtest(
        spec,
        ohlcv_rows=[
            OhlcvBar(date=date(2026, 1, 2), ticker="000001", open=10, high=10, low=10, close=10, volume=1, raw_notional=100),
            OhlcvBar(date=date(2026, 1, 5), ticker="000002", open=10, high=10, low=10, close=10, volume=999999),
        ],
        metric_rows=[{"date": "2026-01-02", "ticker": "000001", "rsi_14": 20}, {"date": "2026-01-05", "ticker": "000002", "rsi_14": 50}],
        config=BacktestRunConfig(initial_capital=1000, write_outputs=False, talib=TalibIndicatorConfig(enabled=False, mode="none")),
    )
    expired = [event for event in result.order_audit if event.ticker == "000001" and event.status == "expired_next_session"]
    assert expired and expired[0].reason == "next_session_missing_bar"


def test_raw_prior_notional_limits_partial_fill_and_never_uses_fill_day_volume():
    spec = rsi_spec()
    spec.backtest.execution_capacity.enabled = True
    result = run_backtest(
        spec,
        ohlcv_rows=[
            OhlcvBar(date=date(2026, 1, 2), ticker="005930", open=10, high=10, low=10, close=10, volume=1, raw_notional=10_000),
            OhlcvBar(date=date(2026, 1, 5), ticker="005930", open=10, high=10, low=10, close=10, volume=999999, raw_notional=0),
        ],
        metric_rows=[{"date": "2026-01-02", "ticker": "005930", "rsi_14": 20}, {"date": "2026-01-05", "ticker": "005930", "rsi_14": 50}],
        config=BacktestRunConfig(initial_capital=1000, write_outputs=False, talib=TalibIndicatorConfig(enabled=False, mode="none")),
    )
    buy = next(event for event in result.order_audit if event.status == "executed" and event.side == "buy")
    assert (buy.requested_quantity, buy.filled_quantity, buy.fill_rate) == (100, 10, 0.1)


def test_unbounded_positions_and_fixed_risk_validation():
    tickers = [f"{number:06d}" for number in range(11)]
    spec = StrategySpec(
        strategy_id="unbounded", strategy_name="Unbounded",
        entry_rules=[Condition(left="rsi_14", operator=ConditionOperator.LTE, right=30)],
        position_sizing=PositionSizing(max_positions=None),
        risk_controls=RiskControls(max_single_position_pct=0.2),
        backtest={"execution_capacity": {"enabled": False}},
    )
    result = run_backtest(
        spec,
        ohlcv_rows=[OhlcvBar(date=day, ticker=ticker, open=10, high=10, low=10, close=10, volume=1) for day in (date(2026, 1, 2), date(2026, 1, 5)) for ticker in tickers],
        metric_rows=[{"date": day.isoformat(), "ticker": ticker, "rsi_14": 20 if day == date(2026, 1, 2) else 50} for day in (date(2026, 1, 2), date(2026, 1, 5)) for ticker in tickers],
        config=BacktestRunConfig(initial_capital=1_100, write_outputs=False, talib=TalibIndicatorConfig(enabled=False, mode="none")),
    )
    assert result.summary["open_positions"] == 11
    with pytest.raises(ValueError, match="stop_loss_pct"):
        StrategySpec(
            strategy_id="invalid_risk", strategy_name="Invalid Risk",
            entry_rules=[Condition(left="rsi_14", operator=ConditionOperator.LTE, right=30)],
            position_sizing=PositionSizing(method="fixed_risk", risk_per_position=0.01),
            risk_controls=RiskControls(stop_loss_pct=None),
        )



def test_cost_cash_reconciliation_preserves_actual_costs():
    spec = rsi_spec()
    spec.backtest.cost_model = CostModel(commission_pct=0.01, tax_pct=0.02, slippage_pct=0)
    result = run_backtest(
        spec,
        ohlcv_rows=[
            OhlcvBar(date=date(2026, 1, 2), ticker="005930", open=100, high=100, low=100, close=100, volume=1),
            OhlcvBar(date=date(2026, 1, 5), ticker="005930", open=100, high=100, low=100, close=100, volume=1),
            OhlcvBar(date=date(2026, 1, 6), ticker="005930", open=110, high=110, low=110, close=110, volume=1),
            OhlcvBar(date=date(2026, 1, 7), ticker="005930", open=110, high=110, low=110, close=110, volume=1),
        ],
        metric_rows=[{"date": day, "ticker": "005930", "rsi_14": value} for day, value in [("2026-01-02", 20), ("2026-01-05", 50), ("2026-01-06", 80), ("2026-01-07", 80)]],
        config=BacktestRunConfig(initial_capital=1_000, write_outputs=False, talib=TalibIndicatorConfig(enabled=False, mode="none")),
    )
    assert result.summary["final_equity"] == pytest.approx(1_051.3)
    assert result.summary["total_cost"] == pytest.approx(38.7)


def test_cost_policy_provenance_interval_components_and_limited_reliability():
    with pytest.raises(ValueError, match="effective_from"):
        CostModel(effective_from=date(2026, 1, 2), effective_to=date(2026, 1, 1))
    spec = rsi_spec()
    spec.backtest.cost_model = CostModel(
        commission_pct=0.01, tax_pct=0.02, slippage_pct=0.01,
        policy_id="krx-retail", policy_version="2026.1", applicable_market="KRX", applicable_account="cash",
        applicable_channel="online", applicable_tier="standard",
        effective_from=date(2026, 1, 1), effective_to=date(2026, 12, 31), source_urls=["https://example.test/fees"],
        document_hash="sha256:fixture", verified_at=datetime(2026, 1, 1), rounding_mode="floor", rounding_decimals=2,
    )
    result = run_backtest(
        spec,
        ohlcv_rows=bars(), metric_rows=rsi_metrics(),
        config=BacktestRunConfig(initial_capital=1_000, write_outputs=False, talib=TalibIndicatorConfig(enabled=False, mode="none")),
    )
    executed = [event for event in result.order_audit if event.status == "executed"]
    assert all(event.cost_policy_id == "krx-retail" for event in executed)
    assert result.summary["commission_cost"] > 0
    assert result.summary["tax_cost"] > 0
    assert result.summary["slippage_cost"] > 0
    assert result.summary["total_cost"] == pytest.approx(
        result.summary["commission_cost"] + result.summary["tax_cost"] + result.summary["slippage_cost"]
    )
    spec.backtest.cost_model.effective_from = date(2026, 1, 6)
    outside_interval = run_backtest(
        spec, ohlcv_rows=bars(), metric_rows=rsi_metrics(),
        config=BacktestRunConfig(initial_capital=1_000, write_outputs=False, talib=TalibIndicatorConfig(enabled=False, mode="none")),
    )
    assert "cost_policy_effective_interval_not_covering_run" in outside_interval.summary["reliability_reasons"]


def test_terminal_open_position_marks_recovery_capability_limited():
    spec = rsi_spec()
    result = run_backtest(
        spec,
        ohlcv_rows=bars()[:2],
        metric_rows=rsi_metrics()[:2],
        config=BacktestRunConfig(initial_capital=1_000, write_outputs=False, talib=TalibIndicatorConfig(enabled=False, mode="none")),
    )
    assert "terminal_open_positions_without_recovery_policy" in result.summary["reliability_reasons"]
    assert result.summary["data_capabilities"]["corporate_actions"] == "unsupported_source_unavailable"
    assert result.summary["cost_policy_production_eligible"] is False


def test_corporate_actions_apply_only_on_effective_session_and_recover_delist():
    spec = rsi_spec()
    spec.backtest.corporate_actions = [
        CorporateActionEvent(event_type="split", ticker="005930", effective_date=date(2026, 1, 6), split_ratio=2),
        CorporateActionEvent(event_type="cash_dividend", ticker="005930", effective_date=date(2026, 1, 6), cash_dividend_per_share=1),
        CorporateActionEvent(event_type="delist", ticker="005930", effective_date=date(2026, 1, 7), recovery_price=5),
    ]
    result = run_backtest(
        spec, ohlcv_rows=bars(), metric_rows=rsi_metrics(),
        config=BacktestRunConfig(initial_capital=1_000, write_outputs=False, talib=TalibIndicatorConfig(enabled=False, mode="none")),
    )
    statuses = [event.status for event in result.order_audit if event.side == "corporate_action"]
    assert statuses == ["applied_split", "applied_cash_dividend", "applied_delist_recovery"]
    assert result.summary["open_positions"] == 0
    assert "corporate_action_provenance_incomplete" in result.summary["reliability_reasons"]


def test_cost_half_up_uses_decimal_at_half_boundary():
    spec = rsi_spec()
    spec.backtest.cost_model = CostModel(commission_pct=0.005, tax_pct=0, slippage_pct=0, rounding_mode="half_up", rounding_decimals=0)
    result = run_backtest(
        spec, ohlcv_rows=bars()[:2], metric_rows=rsi_metrics()[:2],
        config=BacktestRunConfig(initial_capital=1_000, write_outputs=False, talib=TalibIndicatorConfig(enabled=False, mode="none")),
    )
    buy = next(event for event in result.order_audit if event.side == "buy" and event.status == "executed")
    assert buy.commission_cost_text == "5"
    assert result.summary["commission_cost_exact"] == "5"
