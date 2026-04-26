from datetime import date, datetime

from quantagent_strategy import (
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


def test_generate_buy_signal_with_candidate_filter():
    strategy = QuantStrategy(make_spec())
    market = MarketSnapshot(
        ticker="005930",
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


def test_generate_filtered_out_for_non_candidate():
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

    assert result.action == SignalAction.FILTERED_OUT


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
    assert plan.compare_filtered_vs_unfiltered is True
    assert plan.execution_timing.value == "next_open"
