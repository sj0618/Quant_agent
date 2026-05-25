from datetime import date

from backtest_module import (
    Condition,
    ConditionOperator,
    CostModel,
    PositionSizing,
    RiskControls,
    StrategySpec,
)
from backtest_module.backtest import (
    BacktestRunConfig,
    OhlcvBar,
    TalibIndicatorConfig,
    build_sample_spec,
    build_sample_talib_spec,
    compute_talib_metrics_for_bars,
    required_metric_names,
    run_backtest,
    talib_function_catalog,
)


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
        risk_controls=RiskControls(stop_loss_pct=0.5, take_profit_pct=None),
        backtest={"cost_model": CostModel(commission_pct=0, tax_pct=0, slippage_pct=0).model_dump()},
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
