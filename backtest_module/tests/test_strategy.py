from datetime import date, datetime

from backtest_module import (
    BacktestConfig,
    CandidateSnapshot,
    Condition,
    ConditionOperator,
    MarketSnapshot,
    QuantStrategy,
    SignalAction,
    StrategySpec,
)


def make_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="mean_reversion_v1",
        strategy_name="Mean Reversion V1",
        entry_rules=[
            Condition(
                left="rsi",
                operator=ConditionOperator.LTE,
                right=30,
                description="RSI <= 30",
            )
        ],
        exit_rules=[
            Condition(
                left="rsi",
                operator=ConditionOperator.GTE,
                right=70,
                description="RSI >= 70",
            )
        ],
    )


def make_snapshot() -> CandidateSnapshot:
    return CandidateSnapshot(
        snapshot_id="snap-2026-04-08",
        trade_date=date(2026, 4, 8),
        effective_from=datetime(2026, 4, 8, 9, 0),
        top_k_stocks=["005930", "000660"],
        score_list={"005930": 82.4, "000660": 80.1},
        reason_trace={"005930": ["candidate score top-k"]},
    )


def test_generate_buy_signal_without_candidate_filter():
    strategy = QuantStrategy(make_spec())
    market = MarketSnapshot(
        ticker="005930",
        timestamp=datetime(2026, 4, 8, 9, 5),
        metrics={"rsi": 28},
    )

    result = strategy.generate_signal(
        market=market,
        has_position=False,
    )

    assert result.action == SignalAction.BUY
    assert "RSI <= 30" in result.matching_entry_rules


def test_candidate_snapshot_is_ignored_while_filter_is_disabled():
    strategy = QuantStrategy(make_spec())
    market = MarketSnapshot(
        ticker="035420",
        timestamp=datetime(2026, 4, 8, 9, 5),
        metrics={"rsi": 28},
    )

    result = strategy.generate_signal(
        market=market,
        has_position=False,
        candidate_snapshot=make_snapshot(),
    )

    assert result.action == SignalAction.BUY
    assert "RSI <= 30" in result.matching_entry_rules


def test_generate_sell_signal_when_exit_matches():
    strategy = QuantStrategy(make_spec())
    market = MarketSnapshot(
        ticker="005930",
        timestamp=datetime(2026, 4, 8, 9, 5),
        metrics={"rsi": 71},
    )

    result = strategy.generate_signal(
        market=market,
        has_position=True,
        candidate_snapshot=make_snapshot(),
    )

    assert result.action == SignalAction.SELL
    assert "RSI >= 70" in result.matching_exit_rules


def test_compile_backtest_plan_disables_network_and_keeps_compare_flag():
    strategy = QuantStrategy(make_spec())
    plan = strategy.compile_backtest_plan()

    assert plan.network_access_allowed is False
    assert plan.use_candidate_filter is False
    assert plan.compare_filtered_vs_unfiltered is False
    assert plan.execution_timing.value == "next_open"


def test_compile_backtest_plan_ignores_candidate_filter_even_if_requested():
    spec = make_spec()
    spec.research_overlay.enabled = True
    spec.backtest = BacktestConfig(use_candidate_filter=True, compare_filtered_vs_unfiltered=True)
    strategy = QuantStrategy(spec)

    plan = strategy.compile_backtest_plan()

    assert plan.use_candidate_filter is False
    assert plan.compare_filtered_vs_unfiltered is False


def test_metric_to_metric_scalar_condition_evaluates():
    spec = StrategySpec(
        strategy_id="trend_v1",
        strategy_name="Trend V1",
        research_overlay={"enabled": False},
        entry_rules=[
            Condition(
                left="close",
                operator=ConditionOperator.GT,
                right="ma_20",
                description="close > ma_20",
            )
        ],
        exit_rules=[
            Condition(
                left="rsi_14",
                operator=ConditionOperator.GTE,
                right=70,
                description="RSI >= 70",
            )
        ],
    )
    strategy = QuantStrategy(spec)
    market = MarketSnapshot(
        ticker="005930",
        timestamp=datetime(2026, 4, 8, 9, 5),
        metrics={"close": 101, "ma_20": 100, "rsi_14": 50},
    )

    result = strategy.generate_signal(market=market, has_position=False)

    assert result.action == SignalAction.BUY


def test_cross_above_numeric_threshold_evaluates():
    spec = StrategySpec(
        strategy_id="rsi_cross_v1",
        strategy_name="RSI Cross V1",
        research_overlay={"enabled": False},
        entry_rules=[
            Condition(
                left="rsi_14",
                operator=ConditionOperator.CROSS_ABOVE,
                right=30,
                description="RSI crosses above 30",
            )
        ],
        exit_rules=[
            Condition(
                left="rsi_14",
                operator=ConditionOperator.GTE,
                right=70,
                description="RSI >= 70",
            )
        ],
    )
    strategy = QuantStrategy(spec)
    market = MarketSnapshot(
        ticker="005930",
        timestamp=datetime(2026, 4, 8, 9, 5),
        metrics={"rsi_14": 31},
        previous_metrics={"rsi_14": 29},
    )

    result = strategy.generate_signal(market=market, has_position=False)

    assert result.action == SignalAction.BUY


def test_cross_condition_returns_false_without_previous_metrics():
    spec = StrategySpec(
        strategy_id="rsi_cross_v1",
        strategy_name="RSI Cross V1",
        research_overlay={"enabled": False},
        entry_rules=[
            Condition(
                left="rsi_14",
                operator=ConditionOperator.CROSS_ABOVE,
                right=30,
                description="RSI crosses above 30",
            )
        ],
        exit_rules=[],
    )
    strategy = QuantStrategy(spec)
    market = MarketSnapshot(
        ticker="005930",
        timestamp=datetime(2026, 4, 8, 9, 5),
        metrics={"rsi_14": 31},
    )

    result = strategy.generate_signal(market=market, has_position=False)

    assert result.action == SignalAction.WATCH
