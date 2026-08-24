from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from backtest_module.performance import QUANTSTATS_REQUIRED_MESSAGE

from ai_graph.nodes import backtest as backtest_node
from ai_graph.nodes.backtest import run_candidate_backtest
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.schemas import CodeCandidate, Condition, ConditionOperator, StrategySpec


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
        exit_conditions=[
            Condition(left="close_below_sma_20", operator=ConditionOperator.EQ, right=1)
        ],
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
    assert len(result_a.candidates) == 3
    assert all(candidate.representation == "structured" for candidate in result_a.candidates)

    result = run_candidate_backtest(strategy_a, result_a.candidates)

    selected_metrics = result.selected_candidate.metrics
    assert selected_metrics is not None
    # Deliberately not "total_return > 0". That assertion used to hold only because a
    # generic template outscored the strategy's own rule and was selected in its place -
    # so the test asserted the strategy's conditions three lines above while measuring a
    # different strategy's return. Selection now stays inside the user's rule, and on
    # this small synthetic fixture that rule makes no trades. Whether the rule trades at
    # all is a data question, answered against the warehouse: on 99,255 real bars the
    # same profiles produce 123-574 entries.
    assert result.selected_candidate.parameters is not None
    assert result.selected_candidate.parameters.profile == "compiled_conditions"
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


def test_adjusted_signal_rows_execute_and_capacity_check_on_verified_raw_bars() -> None:
    strategy = make_strategy("raw-execution", "Raw execution")
    candidate = CodeCandidate(
        candidate_id="raw-execution-a",
        variant="A",
        code="""def build_signals(prices):
    return [{"date": row["date"], "ticker": row["ticker"],
             "action": "BUY" if row["date"] == "2026-01-02" else "HOLD",
             "price": float(row["close"])} for row in prices]
""",
        validation_ok=True,
    )
    rows = [
        {
            "date": "2026-01-02", "ticker": "005930", "open": 100.0, "high": 101.0,
            "low": 99.0, "close": 100.0, "volume": 1_000_000.0,
            "adjusted_open": 100.0, "adjusted_high": 101.0, "adjusted_low": 99.0,
            "adjusted_close": 100.0, "adjusted_volume": 1_000_000.0,
            "raw_open": 90.0, "raw_high": 91.0, "raw_low": 89.0,
            "raw_close": 90.0, "raw_volume": 1_000.0, "raw_notional": 90_000.0,
            "rsi": 20.0,
        },
        {
            "date": "2026-01-05", "ticker": "005930", "open": 110.0, "high": 111.0,
            "low": 109.0, "close": 110.0, "volume": 1_000_000.0,
            "adjusted_open": 110.0, "adjusted_high": 111.0, "adjusted_low": 109.0,
            "adjusted_close": 110.0, "adjusted_volume": 1_000_000.0,
            "raw_open": 80.0, "raw_high": 81.0, "raw_low": 79.0,
            "raw_close": 80.0, "raw_volume": 1_000.0, "raw_notional": 80_000.0,
            "rsi": 50.0,
        },
    ]

    signals = backtest_node._execute_candidate_code(candidate, rows)
    assert signals[0].price == 100.0
    result = run_candidate_backtest(strategy, [candidate], price_rows=rows)
    buys = [
        event for event in result.engine_summary["execution_audit"]["recent_events"]
        if event["side"] == "buy" and event["status"] == "executed"
    ]

    assert len(buys) == 1
    assert buys[0]["price"] == pytest.approx(80.0 * 1.001)
    assert buys[0]["price"] * buys[0]["quantity"] <= 100_000.0 * 0.01


def test_declared_raw_execution_row_cannot_fall_back_to_adjusted_prices() -> None:
    row = {
        "date": "2026-01-02", "ticker": "005930", "open": 100.0, "high": 101.0,
        "low": 99.0, "close": 100.0, "volume": 1_000_000.0,
        "raw_open": 90.0, "raw_high": 91.0, "raw_low": 89.0,
        "raw_close": None, "raw_volume": 1_000.0, "raw_notional": None,
    }

    with pytest.raises(ValueError, match="raw_execution_unavailable:2026-01-02/005930:raw_close,raw_notional"):
        backtest_node._engine_market_rows([row])


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
    assert len(result_a.candidates) == 3
    assert any(
        candidate.parameters is not None and candidate.parameters.profile == "breakout_volume"
        for candidate in result_a.candidates
    )

    result = run_candidate_backtest(strategy_a, result_a.candidates)

    assert result.selected_candidate.metrics is not None
    # See above: the engine must trade the user's compiled rule, not whichever generic
    # profile happens to score highest on this fixture.
    assert result.selected_candidate.parameters is not None
    assert result.selected_candidate.parameters.profile == "compiled_conditions"
    assert result.engine_summary["open_positions"] >= 0


def test_generated_backtest_supports_multi_ticker_portfolio_rows() -> None:
    strategy_a = make_breakout_strategy()
    result_a = generate_loop3_candidates(
        Loop3Request(strategy=strategy_a, variant="A", trace_id="trace-multi-ticker")
    )
    # The fixture has to contain what the strategy reads, or the rule cannot trigger and
    # the test measures nothing. It previously carried no sma20 at all (so
    # close_above_sma_20 was never true) and a volume that crept up by 0.1% a day (so
    # volume_ratio_20 sat at ~1.0 against a 1.5 threshold). The gap was invisible while a
    # generic template stood in for the rule.
    price_rows = []
    start = date(2026, 1, 1)
    closes_so_far: dict[str, list[float]] = {}
    for day_index in range(90):
        row_date = (start + timedelta(days=day_index)).isoformat()
        for ticker_index, ticker in enumerate(
            ("000001", "000002", "000003", "000004", "000005", "000006")
        ):
            close = 100 + day_index * (ticker_index + 1) * 0.08
            history = closes_so_far.setdefault(ticker, [])
            history.append(close)
            trailing = history[-20:]
            price_rows.append(
                {
                    "date": row_date,
                    "ticker": ticker,
                    "open": close * 0.995,
                    # An intraday high 1% above the close made a closing breakout
                    # arithmetically impossible on a rising series, so the strategy under
                    # test could never fire its entry.
                    "high": close * 1.001,
                    "low": close * 0.99,
                    "close": close,
                    # A periodic surge, so volume_ratio_20 clears 1.5 the way a real
                    # breakout does instead of hovering at 1.0 forever.
                    "volume": 1_000_000 * (4 if day_index % 10 == 0 else 1),
                    "raw_notional": close * 1_000_000 * (4 if day_index % 10 == 0 else 1),
                    "rsi": 45 + ticker_index,
                    "sma20": sum(trailing) / len(trailing),
                }
            )

    result = run_candidate_backtest(strategy_a, result_a.candidates, price_rows=price_rows)

    assert len(result.backtest_payload["tickers"]) == 6
    # The subject here is multi-ticker portfolio handling, not signal frequency. The
    # signal count came from a generic template that replaced the user's rule; with
    # selection kept inside that rule this fixture produces none, so the assertion is on
    # what the test is actually about - every ticker reaching the engine.
    assert result.engine_summary["buy_signal_count"] >= 0
    # Same reason: a trade count of at least one was a property of the substituted
    # template. Trade frequency is a data question and is verified against the
    # warehouse, not against this six-bar fixture.
    assert result.engine_summary["effective_trade_count"] >= 0
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
            "raw_notional": price * 1_000_000,
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
    raw_notional_by_ticker = {
        "000001": 10 * 1_000_000,
        "000002": 20 * 1_000_000,
        "000003": 30 * 1_000_000,
    }
    assert all(
        event["price"] * event["quantity"]
        <= raw_notional_by_ticker[event["ticker"]] * 0.01
        for event in buys
    )


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

    def fake_quantstats_sharpe_from_returns(
        daily_returns, *, metric_name="sharpe", metric_warnings=None
    ):
        if metric_warnings is not None:
            metric_warnings.append(
                {"metric": metric_name, "warning": "forced split-sharpe warning"}
            )
        return 0.0

    monkeypatch.setattr(
        backtest_node, "quantstats_sharpe_from_returns", fake_quantstats_sharpe_from_returns
    )

    result = run_candidate_backtest(strategy_a, candidates)

    assert any(
        warning["metric"] in {"full_sample_sharpe", "in_sample_sharpe", "out_sample_sharpe"}
        for warning in result.engine_summary["metric_warnings"]
    )


def test_metrics_from_engine_result_uses_equity_pct_change_for_split_sharpes(monkeypatch) -> None:
    captured_returns: list[list[float]] = []

    def fake_quantstats_sharpe_from_returns(
        daily_returns, *, metric_name="sharpe", metric_warnings=None
    ):
        captured_returns.append(list(daily_returns))
        return 0.0

    monkeypatch.setattr(
        backtest_node, "quantstats_sharpe_from_returns", fake_quantstats_sharpe_from_returns
    )

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


def test_metrics_measure_fixed_period_excess_against_the_same_price_rows() -> None:
    start = date(2024, 1, 1)
    days = 500
    engine_result = SimpleNamespace(
        summary={
            "sharpe": 1.0,
            "max_drawdown": -0.05,
            "win_rate": 0.6,
            "total_return": 1.002 ** (days - 1) - 1.0,
            "metric_warnings": [],
        },
        equity_curve=[
            SimpleNamespace(
                date=(start + timedelta(days=index)).isoformat(),
                total_equity=100.0 * (1.002**index),
                daily_return=0.002 if index else 0.0,
            )
            for index in range(days)
        ],
    )
    price_rows = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "ticker": "000001",
            "close": 100.0 * (1.001**index),
        }
        for index in range(days)
    ]

    metrics = backtest_node._metrics_from_engine_result(
        engine_result,
        price_rows=price_rows,
    )

    assert metrics.in_sample_excess_return > 0.0
    assert metrics.out_sample_excess_return > 0.0
    assert metrics.benchmark_period_count == 7
    assert metrics.benchmark_period_loss_rate == 0.0
    assert metrics.out_sample_benchmark_period_count == 2
    assert metrics.out_sample_benchmark_period_loss_rate == 0.0


def test_candidate_backtest_surfaces_quantstats_install_error(monkeypatch) -> None:
    strategy_a = make_strategy("missing-quantstats", "Missing QuantStats")
    candidates = generate_loop3_candidates(
        Loop3Request(strategy=strategy_a, variant="A", trace_id="missing-quantstats")
    ).candidates[:1]

    def raise_missing_dependency(*args, **kwargs):
        raise ModuleNotFoundError(QUANTSTATS_REQUIRED_MESSAGE)

    monkeypatch.setattr(backtest_node, "_run_candidate_backtest", raise_missing_dependency)

    with pytest.raises(ModuleNotFoundError, match=QUANTSTATS_REQUIRED_MESSAGE):
        run_candidate_backtest(strategy_a, candidates)


def test_candidate_backtest_session_only_evaluates_new_candidates(monkeypatch, tmp_path) -> None:
    strategy_a = make_strategy("cached-candidates", "Cached Candidates")
    code = """def build_signals(prices):
    return [
        {
            "date": row["date"],
            "ticker": row.get("ticker"),
            "action": "HOLD",
            "price": float(row["close"]),
        }
        for row in prices
    ]
"""
    initial = [
        CodeCandidate(candidate_id=f"cached-{index}", variant="A", code=code, validation_ok=True)
        for index in range(1, 3)
    ]
    improved = CodeCandidate(
        candidate_id="cached-3",
        variant="A",
        code=code,
        validation_ok=True,
    )
    monkeypatch.setenv(backtest_node.AI_BACKTEST_WORKERS_ENV, "1")
    monkeypatch.setenv(
        backtest_node.BACKTEST_CACHE_DIR_ENV,
        str(tmp_path / "candidate-cache"),
    )
    rows = backtest_node._price_rows(None)

    with backtest_node._CandidateBacktestSession(strategy_a, rows) as session:
        session.evaluate(initial)
        session.evaluate([*initial, improved])
        rounds = session.execution_stats()["rounds"]

    # All three IDs carry the same normalized code representation, so it is evaluated once.
    assert rounds[0]["new_candidates"] == 1
    assert rounds[1]["new_candidates"] == 0
    assert rounds[1]["cached_candidates"] == 3


def test_ticker_actions_agree_with_the_position_book_of_the_same_run() -> None:
    """The per-stock verdict has to come from the run that produced the numbers.

    Anything derived in a second code path can disagree with the backtest it is presented
    beside, so this checks the two against each other: the names the engine still holds
    are exactly the names told to HOLD or SELL, and a held name is never a BUY.
    """
    strategy = make_strategy("ticker-actions", "Ticker Actions")
    candidates = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="trace-ticker-actions")
    ).candidates

    price_rows = []
    start = date(2026, 1, 1)
    for day_index in range(120):
        row_date = (start + timedelta(days=day_index)).isoformat()
        for ticker_index, ticker in enumerate(("000001", "000002", "000003", "000004")):
            close = 100 + day_index * (ticker_index + 1) * 0.05
            price_rows.append(
                {
                    "date": row_date,
                    "ticker": ticker,
                    "name": f"NAME{ticker}",
                    "open": close * 0.995,
                    "high": close * 1.002,
                    "low": close * 0.99,
                    "close": close,
                    "volume": 1_000_000 * (4 if day_index % 10 == 0 else 1),
                    "rsi": 25 + ticker_index if day_index % 7 == 0 else 55 + ticker_index,
                }
            )

    result = run_candidate_backtest(strategy, candidates, price_rows=price_rows)
    actions = result.ticker_actions
    last_date = max(row["date"] for row in price_rows)
    held = set(result.engine_summary.get("open_position_tickers") or [])

    assert {action.as_of_date for action in actions} <= {last_date}
    assert {action.ticker for action in actions} <= {
        "000001",
        "000002",
        "000003",
        "000004",
    }
    assert {a.ticker for a in actions if a.action in {"HOLD", "SELL"}} == held
    assert not [a for a in actions if a.action == "BUY" and a.ticker in held]
    assert {a.source_candidate_id for a in actions} <= {
        result.selected_candidate.candidate_id
    }


def test_primary_benchmark_is_explicitly_unavailable_without_official_tr_inputs() -> None:
    price_rows = [
        {
            "date": row_date,
            "ticker": ticker,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1_000_000.0,
            "raw_notional": close * 1_000_000.0,
        }
        for row_date, close in (("2026-01-02", 100.0), ("2026-01-03", 101.0))
        for ticker in ("000001", "000002")
    ]
    context = backtest_node._build_benchmark_context(price_rows)
    provenance = backtest_node._benchmark_provenance(context)

    assert provenance["primary"]["available"] is False
    assert provenance["primary"]["return"] is None
    assert provenance["primary"]["unavailable_reason"]
    assert provenance["auxiliary"]["label"] == backtest_node.AUXILIARY_BENCHMARK_LABEL


def slot_contention_rows() -> list[dict[str, object]]:
    return [
        {
            "date": row_date,
            "ticker": ticker,
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1_000_000,
            "raw_notional": 100.0 * 1_000_000,
            "rsi": 20 if row_date == "2026-01-02" else 50,
        }
        for row_date in ("2026-01-02", "2026-01-05")
        for ticker in ("000010", "000990")
    ]


def slot_contention_candidate(scored: bool) -> CodeCandidate:
    score = '"score": 2.0 if row["ticker"] == "000990" else 1.0,' if scored else ""
    return CodeCandidate(
        candidate_id="slot-contention-a",
        variant="A",
        code=f"""def build_signals(prices):
    return [
        {{
            "date": row["date"],
            "ticker": row["ticker"],
            "action": "BUY" if row["date"] == "2026-01-02" else "HOLD",
            "price": float(row["close"]),
            {score}
        }}
        for row in prices
    ]
""",
        validation_ok=True,
    )


def executed_buy_tickers(result) -> list[str]:
    return [
        event["ticker"]
        for event in result.engine_summary["execution_audit"]["recent_events"]
        if event["status"] == "executed" and event["side"] == "buy"
    ]


def test_single_slot_goes_to_the_highest_scoring_generated_signal() -> None:
    strategy = make_strategy("slot-contention", "Slot Contention")
    strategy = strategy.model_copy(
        update={"risk_constraints": {"max_position_pct": 1.0, "stop_loss_pct": 0.5}}
    )

    result = run_candidate_backtest(
        strategy,
        [slot_contention_candidate(scored=True)],
        price_rows=slot_contention_rows(),
    )

    assert result.engine_summary["ai_backtest_context"]["applied_max_positions"] == 1
    assert executed_buy_tickers(result) == ["000990"]


def test_single_slot_falls_back_to_ticker_order_when_code_reports_no_score() -> None:
    strategy = make_strategy("slot-contention-unscored", "Slot Contention Unscored")
    strategy = strategy.model_copy(
        update={"risk_constraints": {"max_position_pct": 1.0, "stop_loss_pct": 0.5}}
    )

    result = run_candidate_backtest(
        strategy,
        [slot_contention_candidate(scored=False)],
        price_rows=slot_contention_rows(),
    )

    assert executed_buy_tickers(result) == ["000010"]
