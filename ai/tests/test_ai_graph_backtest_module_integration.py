from ai_graph.nodes.backtest import run_ab_backtest
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.schemas import Condition, StrategySpec


def make_strategy(strategy_id: str, name: str) -> StrategySpec:
    return StrategySpec(
        strategy_id=strategy_id,
        name=name,
        universe="KOSPI200",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator="lte", right=30)],
        exit_conditions=[Condition(left="rsi", operator="gte", right=70)],
        indicators=["RSI"],
        risk_constraints={"max_position_pct": 0.1, "stop_loss_pct": 0.08},
        confidence=0.83,
    )


def test_backtest_node_metrics_are_computed_by_backtest_module_engine() -> None:
    strategy_a = make_strategy("rsi_a", "RSI A")
    strategy_b = make_strategy("rsi_b", "RSI B")
    result_a = generate_loop3_candidates(
        Loop3Request(strategy=strategy_a, variant="A", trace_id="trace-module")
    )
    result_b = generate_loop3_candidates(
        Loop3Request(strategy=strategy_b, variant="B", trace_id="trace-module")
    )

    assert all(candidate.metrics is None for candidate in result_a.candidates + result_b.candidates)

    result = run_ab_backtest(strategy_a, strategy_b, result_a.candidates + result_b.candidates)

    selected_metrics = result.selected_candidate.metrics
    assert selected_metrics is not None
    assert selected_metrics.total_return > 0
    assert result.metrics_by_variant["A"].total_return > 0
    assert result.metrics_by_variant["B"].total_return > 0
    assert result.engine_summaries_by_candidate[result.selected_candidate.candidate_id]["trade_count"] == 1
