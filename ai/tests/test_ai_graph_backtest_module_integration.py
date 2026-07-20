from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from ai_graph.nodes import backtest as backtest_node
from ai_graph.nodes.backtest import run_candidate_backtest
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.schemas import CodeCandidate, Condition, ConditionOperator, StrategySpec
from backtest_module.performance import QUANTSTATS_REQUIRED_MESSAGE


def make_strategy(strategy_id: str, name: str) -> StrategySpec:
    return StrategySpec(
        strategy_id=strategy_id,
        name=name,
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator=ConditionOperator.LTE, right=30)],
        exit_conditions=[Condition(left="rsi", operator=ConditionOperator.GTE, right=70)],
        indicators=["RSI"],
        risk_constraints={"max_position_pct": 0.1, "stop_loss_pct": 0.08},
        confidence=0.83,
    )


def make_breakout_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="breakout_volume_momentum",
        name="KOSPI200 거래량 돌파 모멘텀",
        market="KRX",
        timeframe="daily",
        entry_conditions=[
            Condition(left="breakout_high", operator=ConditionOperator.EQ, right=1),
            Condition(left="volume_ratio_20", operator=ConditionOperator.GTE, right=1.5),
            Condition(left="close_above_sma_20", operator=ConditionOperator.EQ, right=1),
            Condition(left="relative_strength_20d", operator=ConditionOperator.GTE, right=0),
        ],
        exit_conditions=[Condition(left="close_below_sma_20", operator=ConditionOperator.EQ, right=1)],
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
    execution_audit = result.engine_summary["execution_audit"]
    assert execution_audit["has_real_fills"] is True
    assert execution_audit["executed_buy_count"] >= 1
    assert execution_audit["recent_events"]
    context = result.engine_summary["ai_backtest_context"]
    assert context["available_ticker_count"] == 1
    assert context["requested_max_positions"] == 10
    assert context["applied_max_positions"] == 1
    assert context["exposure_normalized"] is True
    assert result.engine_summary["position_sizing"]["max_positions"] == 1


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
    assert result.engine_summary["effective_trade_count"] >= 1
    assert result.engine_summary["ai_backtest_context"]["available_ticker_count"] == 6
    assert result.engine_summary["ai_backtest_context"]["applied_max_positions"] == 6
    assert result.engine_summary["execution_audit"]["executed_buy_count"] >= 1
    assert result.selected_candidate.metrics is not None


def test_generated_backtest_preserves_requested_position_limit_with_fewer_tickers() -> None:
    strategy = make_strategy("multi-ticker-risk-limit", "Multi Ticker Risk Limit")
    candidate = CodeCandidate(
        candidate_id="multi-ticker-risk-a",
        variant="A",
        code="""def build_signals(prices):
    return [
        {
            "date": row["date"],
            "ticker": row["ticker"],
            "action": "BUY" if row["date"] == "2026-01-02" else "HOLD",
            "price": float(row["close"]),
        }
        for row in prices
    ]
""",
        validation_ok=True,
    )
    price_rows = [
        {
            "date": row_date,
            "ticker": ticker,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1_000_000,
            "rsi": 20 if row_date == "2026-01-02" else 50,
        }
        for row_date in ("2026-01-02", "2026-01-05")
        for ticker, price in (("000001", 10), ("000002", 20), ("000003", 30))
    ]

    result = run_candidate_backtest(strategy, [candidate], price_rows=price_rows)
    audit = result.engine_summary["execution_audit"]
    buys = [
        event
        for event in audit["recent_events"]
        if event["status"] == "executed" and event["side"] == "buy"
    ]

    assert result.engine_summary["ai_backtest_context"]["requested_max_positions"] == 10
    assert result.engine_summary["ai_backtest_context"]["applied_max_positions"] == 3
    assert len(buys) == 3
    assert all(event["price"] * event["quantity"] <= 100_000 for event in buys)


def test_candidate_backtest_handles_single_price_row_without_metric_crash() -> None:
    strategy_a = make_strategy("single-row", "Single Row")
    candidates = [
        CodeCandidate(
            candidate_id="single-row-a",
            variant="A",
            code="""def build_signals(prices):
    return [{"date": row["date"], "action": "HOLD", "price": float(row["close"])} for row in prices]
""",
            validation_ok=True,
        )
    ]
    price_rows = [
        {
            "date": "2026-01-02",
            "ticker": "005930",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000.0,
            "rsi": 50.0,
        }
    ]

    result = run_candidate_backtest(strategy_a, candidates, price_rows=price_rows)

    assert result.selected_candidate.metrics is not None
    assert result.selected_candidate.metrics.total_return == 0.0
    assert result.selected_candidate.metrics.max_drawdown == 0.0
    assert result.selected_candidate.metrics.sharpe_ratio == 0.0
    assert result.engine_summary["metric_warnings"]


def test_candidate_backtest_surfaces_split_sharpe_warnings(monkeypatch) -> None:
    strategy_a = make_strategy("warning-row", "Warning Row")
    candidates = [
        CodeCandidate(
            candidate_id="warning-row-a",
            variant="A",
            code="""def build_signals(prices):
    return [{"date": row["date"], "action": "HOLD", "price": float(row["close"])} for row in prices]
""",
            validation_ok=True,
        )
    ]

    def fake_quantstats_sharpe_from_returns(daily_returns, *, metric_name="sharpe", metric_warnings=None):
        if metric_warnings is not None:
            metric_warnings.append({"metric": metric_name, "warning": "forced split-sharpe warning"})
        return 0.0

    monkeypatch.setattr(backtest_node, "quantstats_sharpe_from_returns", fake_quantstats_sharpe_from_returns)

    result = run_candidate_backtest(strategy_a, candidates)

    assert any(
        warning["metric"] in {"full_sample_sharpe", "in_sample_sharpe", "out_sample_sharpe"}
        for warning in result.engine_summary["metric_warnings"]
    )


def test_metrics_from_engine_result_uses_equity_pct_change_for_split_sharpes(monkeypatch) -> None:
    captured_returns: list[list[float]] = []

    def fake_quantstats_sharpe_from_returns(daily_returns, *, metric_name="sharpe", metric_warnings=None):
        captured_returns.append(list(daily_returns))
        return 0.0

    monkeypatch.setattr(backtest_node, "quantstats_sharpe_from_returns", fake_quantstats_sharpe_from_returns)

    engine_result = SimpleNamespace(
        summary={
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "total_return": 0.0,
            "metric_warnings": [],
        },
        equity_curve=[
            SimpleNamespace(date="2026-01-01", total_equity=100.0, daily_return=0.9),
            SimpleNamespace(date="2026-01-02", total_equity=110.0, daily_return=0.8),
            SimpleNamespace(date="2026-01-03", total_equity=121.0, daily_return=0.7),
            SimpleNamespace(date="2026-01-04", total_equity=108.9, daily_return=0.6),
            SimpleNamespace(date="2026-01-05", total_equity=119.79, daily_return=0.5),
        ],
    )

    backtest_node._metrics_from_engine_result(engine_result)

    assert len(captured_returns) == 2
    assert captured_returns[0] == pytest.approx([0.1, 0.1])
    assert captured_returns[1] == pytest.approx([-0.1, 0.1])


def test_candidate_backtest_surfaces_quantstats_install_error(monkeypatch) -> None:
    strategy_a = make_strategy("missing-quantstats", "Missing QuantStats")
    candidates = [
        CodeCandidate(
            candidate_id="missing-quantstats-a",
            variant="A",
            code="""def build_signals(prices):
    return [{"date": row["date"], "action": "HOLD", "price": float(row["close"])} for row in prices]
""",
            validation_ok=True,
        )
    ]

    def raise_missing_dependency(*args, **kwargs):
        raise ModuleNotFoundError(QUANTSTATS_REQUIRED_MESSAGE)

    monkeypatch.setattr(backtest_node, "_run_candidate_backtest", raise_missing_dependency)

    with pytest.raises(ModuleNotFoundError, match=QUANTSTATS_REQUIRED_MESSAGE):
        run_candidate_backtest(strategy_a, candidates)
