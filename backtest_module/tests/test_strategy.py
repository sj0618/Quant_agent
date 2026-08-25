from datetime import datetime

from backtest_module import (
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


def test_generate_buy_signal_for_matching_ticker():
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
    )

    assert result.action == SignalAction.SELL
    assert "RSI >= 70" in result.matching_exit_rules


def test_compile_backtest_plan_disables_network():
    strategy = QuantStrategy(make_spec())
    plan = strategy.compile_backtest_plan()

    assert plan.network_access_allowed is False
    assert plan.execution_timing.value == "next_open"


def test_metric_to_metric_scalar_condition_evaluates():
    spec = StrategySpec(
        strategy_id="trend_v1",
        strategy_name="Trend V1",
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
