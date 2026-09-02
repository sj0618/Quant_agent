"""The walk-forward geometry has to follow the window the data node loaded.

A one-year window (`AI_BACKTEST_LOOKBACK_YEARS`, default 1) cannot fill a 17-month
fold, so the fixed five-year policy produced zero folds and masked every out-of-sample
metric. These tests pin the tier boundaries, the five-year contract that
`graph.run_analysis` validates the sealed V2 policy against, and the fact that a
one-year input now reaches READY with real numbers.
"""

from __future__ import annotations

from datetime import date, timedelta

from ai_graph.nodes import backtest as backtest_node
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.schemas import Condition, ConditionOperator, StrategySpec


def _strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="window-policy-rsi",
        name="RSI 30/70",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator=ConditionOperator.LTE, right=30.0)],
        exit_conditions=[Condition(left="rsi", operator=ConditionOperator.GTE, right=70.0)],
        indicators=["rsi"],
        risk_constraints={
            "max_position_pct": 0.2,
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.3,
        },
        confidence=0.9,
    )


def _months(count: int, sessions_per_month: int = 20) -> list[dict[str, str]]:
    return [
        {"date": date(2020 + index // 12, index % 12 + 1, day).isoformat()}
        for index in range(count)
        for day in range(1, sessions_per_month + 1)
    ]


def _sessions(count: int) -> list[str]:
    out: list[str] = []
    day = date(2024, 1, 2)
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def _price_rows(
    *,
    sessions: int = 250,
    tickers: int = 8,
    last_session_by_ticker: dict[int, int] | None = None,
    constant_rsi: dict[int, float] | None = None,
) -> list[dict[str, object]]:
    """Deterministic sawtooth prices with an RSI column the compiled rule can trade."""

    last_session_by_ticker = last_session_by_ticker or {}
    constant_rsi = constant_rsi or {}
    rows: list[dict[str, object]] = []
    for day_index, row_date in enumerate(_sessions(sessions)):
        for ticker_index in range(tickers):
            if day_index > last_session_by_ticker.get(ticker_index, sessions):
                continue
            close = (
                50.0
                + ticker_index * 3.0
                + day_index * 0.05
                + ((day_index + ticker_index * 7) % 21 - 10) * 0.4
            )
            volume = 500_000.0 + ticker_index * 2_000.0 + day_index * 100.0
            rows.append(
                {
                    "date": row_date,
                    "ticker": f"{ticker_index + 1:06d}",
                    "open": close * 0.998,
                    "high": close * 1.012,
                    "low": close * 0.988,
                    "close": close,
                    "volume": volume,
                    "raw_notional": volume * close,
                    "rsi": constant_rsi.get(
                        ticker_index, 25.0 + float((day_index + ticker_index * 3) % 60)
                    ),
                }
            )
    return rows


def _candidates(strategy: StrategySpec):
    return generate_loop3_candidates(
        Loop3Request(
            strategy=strategy,
            variant="A",
            trace_id="window-policy",
            max_positions=4,
            server_only=True,
        )
    ).candidates


def test_short_window_tier_reaches_ready_on_a_one_year_sample() -> None:
    sample = backtest_node._walk_forward_sample(_months(12))

    assert sample.policy.tier == "short_window"
    assert (sample.policy.train_months, sample.policy.validation_months) == (6, 1)
    assert sample.valid_fold_count >= 3
    assert sample.status == backtest_node.READY_WALK_FORWARD


def test_medium_window_tier_scales_its_minimums_to_a_three_year_sample() -> None:
    sample = backtest_node._walk_forward_sample(_months(36))

    assert sample.policy.tier == "medium_window"
    assert (sample.policy.train_months, sample.policy.validation_months) == (12, 3)
    assert sample.policy.min_valid_folds == 36 - 17
    assert sample.policy.min_unique_evaluation_sessions == 20 * (36 - 17)
    assert sample.status == backtest_node.READY_WALK_FORWARD


def test_full_window_tier_keeps_the_five_year_contract() -> None:
    sample = backtest_node._walk_forward_sample(_months(60))

    assert sample.policy == backtest_node.FIVE_YEAR_WALK_FORWARD_POLICY
    assert sample.policy.min_valid_folds == backtest_node.WALK_FORWARD_MIN_VALID_FOLDS
    assert (
        sample.policy.min_unique_evaluation_sessions
        == backtest_node.WALK_FORWARD_MIN_UNIQUE_EVALUATION_SESSIONS
    )
    assert sample.status == backtest_node.READY_WALK_FORWARD


def test_exported_constants_still_describe_the_sealed_v2_policy() -> None:
    """`graph.run_analysis` compares the sealed V2 exploration policy to these names.

    Scaling them per window would make every sealed policy look stale, so the module
    constants stay on the five-year contract and only `walk_forward_policy_for` moves.
    """

    assert (
        backtest_node.WALK_FORWARD_TRAIN_MONTHS,
        backtest_node.WALK_FORWARD_VALIDATION_MONTHS,
        backtest_node.WALK_FORWARD_EVALUATION_MONTHS,
        backtest_node.WALK_FORWARD_ROLL_MONTHS,
        backtest_node.WALK_FORWARD_MIN_UNIQUE_EVALUATION_SESSIONS,
    ) == (12, 3, 1, 1, 480)


def test_one_year_input_produces_a_ready_unmasked_walk_forward_result(
    monkeypatch, tmp_path
) -> None:
    strategy = _strategy()
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "one-year"))
    rows = _price_rows()

    with backtest_node._CandidateBacktestSession(strategy, rows) as session:
        result = backtest_node.run_candidate_backtest(
            strategy, _candidates(strategy), _session=session
        )

    artifact = result.engine_summary["walk_forward_sample"]
    assert result.walk_forward is not None
    assert result.walk_forward.status == "ready"
    assert result.walk_forward.aggregate_metrics is not None
    assert artifact["walk_forward_policy"]["tier"] == "short_window"
    assert artifact["aggregate_oos_available"] is True
    assert artifact["aggregate_oos_result"]["availability"] == "available"
    assert isinstance(artifact["aggregate_oos_result"]["sharpe_ratio"], float)


def test_a_ticker_whose_rows_end_mid_window_does_not_break_the_run(
    monkeypatch, tmp_path
) -> None:
    """PIT rows stop at a delisting date, so a name simply disappears mid-window.

    Held through the gap, that position used to sit at its last close for the rest of
    the run. `delisting_grace_days` closes it instead - the run completes, and a name
    that stops trading while held is realised rather than carried.
    """

    strategy = _strategy()
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "delisted"))
    # rsi 25 never clears the 70 exit, so ticker 000001 is bought and still held when
    # its rows stop at session 120.
    rows = _price_rows(last_session_by_ticker={0: 120}, constant_rsi={0: 25.0})
    delisted_sessions = {str(row["date"]) for row in rows if row["ticker"] == "000001"}

    assert len(delisted_sessions) == 121
    assert backtest_node._available_ticker_count(rows) == 8

    held = backtest_node.run_candidate_backtest(
        strategy, _candidates(strategy), price_rows=rows, _walk_forward_enabled=False
    )
    assert held.engine_summary["delisting"]["forced_exits"] >= 1
    assert held.engine_summary["delisting"]["unrealizable_equity"] == 0

    with backtest_node._CandidateBacktestSession(strategy, rows) as session:
        result = backtest_node.run_candidate_backtest(
            strategy, _candidates(strategy), _session=session
        )

    assert result.walk_forward is not None
    assert result.walk_forward.status == "ready"
    assert result.selected_candidate.metrics is not None


def _backtest_state(strategy: StrategySpec, rows: list[dict[str, object]]) -> dict[str, object]:
    generated = generate_loop3_candidates(
        Loop3Request(
            strategy=strategy,
            variant="A",
            trace_id="window-policy",
            max_positions=4,
            server_only=True,
        )
    )
    return {
        "strategy_spec": strategy.model_dump(),
        "backtest_code": generated.model_dump(),
        "price_rows": rows,
    }


def test_walk_forward_deflation_reads_the_out_of_sample_aggregate(
    monkeypatch, tmp_path
) -> None:
    """Walk-forward has no in-sample Sharpe, so deflating one was a structural failure.

    `_walk_forward_aggregate_metrics` pins in_sample_sharpe at 0.0 because selection ran
    per fold on train/validation. Subtracting the expected best-of-N from that zero
    produced a large negative number - measured at -2.84 on a one-year live run - and the
    acceptance floor then failed on search width no matter what the strategy did.
    """

    strategy = _strategy()
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "deflation"))
    rows = _price_rows()
    candidates = _candidates(strategy)

    with backtest_node._CandidateBacktestSession(strategy, rows) as session:
        result = backtest_node.run_candidate_backtest(strategy, candidates, _session=session)
    corrected = backtest_node._apply_selection_correction(result, len(candidates))

    walk_forward = corrected.walk_forward
    aggregate = walk_forward.aggregate_metrics
    assert walk_forward.status == "ready"
    assert aggregate.in_sample_sharpe == 0.0
    expected = round(
        aggregate.out_sample_sharpe
        - backtest_node._expected_max_sharpe(
            len(candidates), walk_forward.unique_evaluation_session_count
        ),
        backtest_node.METRIC_ROUND_DIGITS,
    )
    assert aggregate.selection_adjusted_sharpe == expected
    assert corrected.selected_candidate.metrics.selection_adjusted_sharpe == expected
    # The search width now reaches the published document instead of reading as 1.
    assert aggregate.candidates_evaluated == len(candidates)
    # The floor judges the rolling evaluation, not the fold split selection was run on.
    assert backtest_node._floor_metrics(corrected).out_sample_sharpe == (
        aggregate.out_sample_sharpe
    )


def test_self_improvement_runs_when_the_floor_is_not_cleared_under_walk_forward(
    monkeypatch, tmp_path
) -> None:
    """A missed floor now keeps searching instead of stopping at the first pass."""

    strategy = _strategy()
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "rounds"))
    output = backtest_node.backtest_node(_backtest_state(strategy, _price_rows()))

    floor = output["objective_floor"]
    assert floor["cleared"] is False
    assert 1 <= floor["rounds_run"] <= backtest_node.MAX_SELF_IMPROVEMENT_ROUNDS
    assert floor["candidates_tried"] > 3
    assert output["backtest"]["execution_stats"]["self_improvement_rounds_run"] == (
        floor["rounds_run"]
    )
    # A miss reports numbers, never a blank.
    assert "목표 미달" in floor["conclusion"]
    assert "미사용 구간 Sharpe" in floor["conclusion"]
    assert floor["metrics"]["evaluation_session_count"] > 0
    assert floor["metrics"]["evaluation_period"]["start"] < (
        floor["metrics"]["evaluation_period"]["end"]
    )
    # The equity curve survives the miss, so the reader still gets the run.
    assert output["backtest"]["walk_forward"]["equity_curve"]


def test_self_improvement_stops_at_the_wall_budget_and_still_concludes(
    monkeypatch, tmp_path
) -> None:
    strategy = _strategy()
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "budget"))
    # 0 means "unset" to the reader, so use the smallest budget it accepts.
    monkeypatch.setenv(backtest_node.AI_BACKTEST_WALL_BUDGET_ENV, "0.001")

    output = backtest_node.backtest_node(_backtest_state(strategy, _price_rows()))

    floor = output["objective_floor"]
    assert floor["rounds_run"] == 0
    assert floor["conclusion"]
    assert any(
        "wall budget" in reason for reason in output["backtest"]["fallback_reasons"]
    )


def test_a_cleared_floor_names_the_candidate_and_its_numbers(monkeypatch, tmp_path) -> None:
    strategy = _strategy()
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "cleared"))
    monkeypatch.setattr(backtest_node, "MIN_OBJECTIVE_TRADES", 0)
    monkeypatch.setattr(backtest_node, "MIN_OBJECTIVE_SHARPE", -10.0)
    monkeypatch.setattr(backtest_node, "MIN_SELECTION_ADJUSTED_SHARPE", -10.0)

    output = backtest_node.backtest_node(_backtest_state(strategy, _price_rows()))

    floor = output["objective_floor"]
    assert floor["cleared"] is True
    assert floor["reasons"] == []
    # Clearing on the first pass must not spend the refinement budget.
    assert floor["rounds_run"] == 0
    assert floor["conclusion"].startswith("목표 달성: 후보 ")
    assert "미사용 구간 Sharpe" in floor["conclusion"]
