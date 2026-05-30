from datetime import date, timedelta

from ai_graph.nodes.backtest import run_candidate_backtest
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.schemas import CodeCandidate, Condition, StrategySpec


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


def make_breakout_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="breakout_volume_momentum",
        name="KOSPI200 거래량 돌파 모멘텀",
        universe="KOSPI200",
        market="KRX",
        timeframe="daily",
        entry_conditions=[
            Condition(left="breakout_high", operator="eq", right=1),
            Condition(left="volume_ratio_20", operator="gte", right=1.5),
            Condition(left="close_above_sma_20", operator="eq", right=1),
            Condition(left="relative_strength_20d", operator="gte", right=0),
        ],
        exit_conditions=[Condition(left="close_below_sma_20", operator="eq", right=1)],
        indicators=["rolling_high", "volume_ratio_20", "SMA20", "relative_strength_20d"],
        risk_constraints={"max_position_pct": 0.1, "stop_loss_pct": 0.08},
        confidence=0.8,
    )


def test_backtest_node_metrics_are_computed_by_backtest_module_engine() -> None:
    strategy_a = make_strategy("rsi_a", "RSI A")
    result_a = generate_loop3_candidates(
        Loop3Request(strategy=strategy_a, variant="A", trace_id="trace-module")
    )

    assert all(candidate.metrics is None for candidate in result_a.candidates)
    assert len(result_a.candidates) >= 6

    result = run_candidate_backtest(strategy_a, result_a.candidates)

    selected_metrics = result.selected_candidate.metrics
    assert selected_metrics is not None
    assert selected_metrics.total_return > 0
    assert result.equity_curve[-1].cumulative_return > 0
    assert result.engine_summary
    assert result.backtest_payload["payload_hash"]


def test_generated_backtest_code_can_use_sorted_builtin() -> None:
    strategy_a = make_strategy("rsi_a", "RSI A")
    code = """def build_signals(prices):
    signals = []
    ordered = sorted(prices, key=lambda item: item["date"])
    for previous, row in zip([None] + ordered[:-1], ordered):
        rsi = float(row.get("rsi", 50)) if isinstance(row, dict) else 50
        previous_rsi = float(previous.get("rsi", rsi)) if isinstance(previous, dict) else rsi
        action = "buy" if rsi <= 30 else "sell" if rsi >= 70 else "hold"
        if previous_rsi <= 30 and rsi > 30:
            action = "hold"
        signals.append({"date": row["date"], "action": action, "price": float(row["close"])})
    return signals
"""
    candidates = [
        CodeCandidate(candidate_id="sorted-a", variant="A", code=code, validation_ok=True),
    ]

    result = run_candidate_backtest(strategy_a, candidates)

    assert result.selected_candidate.candidate_id == "sorted-a"


def test_generated_backtest_code_can_use_any_builtin() -> None:
    strategy_a = make_strategy("rsi_a", "RSI A")
    code = """def build_signals(prices):
    has_oversold = any(float(row.get("rsi", 50)) <= 30 for row in prices)
    action = "BUY" if has_oversold else "HOLD"
    return [{"date": row["date"], "action": action, "price": float(row["close"])} for row in prices]
"""
    candidates = [
        CodeCandidate(candidate_id="any-a", variant="A", code=code, validation_ok=True),
    ]

    result = run_candidate_backtest(strategy_a, candidates)

    assert result.selected_candidate.candidate_id == "any-a"


def test_breakout_volume_strategy_uses_strategy_specific_candidates() -> None:
    strategy_a = make_breakout_strategy()
    result_a = generate_loop3_candidates(
        Loop3Request(strategy=strategy_a, variant="A", trace_id="trace-breakout")
    )

    assert all(candidate.validation_ok for candidate in result_a.candidates)
    assert len(result_a.candidates) >= 6
    assert any("volume_ratio" in candidate.code for candidate in result_a.candidates)

    result = run_candidate_backtest(strategy_a, result_a.candidates)

    assert result.selected_candidate.metrics is not None
    assert result.selected_candidate.metrics.total_return > 0
    assert result.engine_summary["open_positions"] >= 0


def test_generated_backtest_supports_multi_ticker_portfolio_rows() -> None:
    strategy_a = make_breakout_strategy()
    result_a = generate_loop3_candidates(
        Loop3Request(strategy=strategy_a, variant="A", trace_id="trace-multi-ticker")
    )
    price_rows = []
    start = date(2026, 1, 1)
    for day_index in range(90):
        row_date = (start + timedelta(days=day_index)).isoformat()
        for ticker_index, ticker in enumerate(("000001", "000002", "000003", "000004", "000005", "000006")):
            close = 100 + day_index * (ticker_index + 1) * 0.08
            price_rows.append(
                {
                    "date": row_date,
                    "ticker": ticker,
                    "open": close * 0.995,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": 1_000_000 + day_index * 1_000,
                    "rsi": 45 + ticker_index,
                }
            )

    result = run_candidate_backtest(strategy_a, result_a.candidates, price_rows=price_rows)

    assert len(result.backtest_payload["tickers"]) == 6
    assert result.engine_summary["buy_signal_count"] > 1
    assert result.engine_summary["effective_trade_count"] >= result.engine_summary["buy_signal_count"]
    assert result.selected_candidate.metrics is not None
