"""What a walk-forward fold hands the engine, and what the report says about it.

Every fold starts the engine in cash on its own evaluation month, but the action
generator used to be built on that fold's context window alone. Two things followed:

  * it entered the month believing it still held whatever it had bought during
    train/validation, so it issued no entry - measured on the deployed five-year rule,
    506 of 896 evaluation sessions (56.5%) were spent 100% in cash;
  * ``date_number`` restarted at the fold's first bar, so the 21-day rotation grid
    landed on different absolute dates in every fold, and long-window derived metrics
    (sma200, 12-1 momentum) never warmed up inside a one-year window.

Actions are now built on the whole-window store, with the fold's first tradable session
marked as the point where the book restarts from cash. These tests pin that, the slot
release that follows a stop, and the reporting definitions that go out with it.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from ai_graph.nodes import backtest as backtest_node
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.nodes.backtest_features import PreparedFeatureStore
from ai_graph.quant_performance import build_public_backtest_performance
from ai_graph.schemas import (
    CandidateParameters,
    CodeCandidate,
    Condition,
    ConditionOperator,
    StrategyIR,
    StrategySpec,
)

REBALANCE = 7


def _sessions(count: int) -> list[str]:
    out: list[str] = []
    day = date(2024, 1, 2)
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def _bar(session: str, ticker: str, close: float) -> dict[str, object]:
    return {
        "date": session,
        "ticker": ticker,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1_000_000.0,
        "raw_notional": 1_000_000.0 * close,
    }


def _leadership_rows(sessions: list[str], swap_at: int) -> list[dict[str, object]]:
    """Two names, always eligible, whose ranking order swaps once at `swap_at`.

    With one slot, the only way to see a rotation day is a replacement: the leader
    changes mid-grid and the portfolio may only act on it when the grid comes round.
    """

    rows: list[dict[str, object]] = []
    for index, session in enumerate(sessions):
        leader_is_b = index >= swap_at
        rows.append(_bar(session, "000001", 102.0 if not leader_is_b else 101.0))
        rows.append(_bar(session, "000002", 101.0 if not leader_is_b else 102.0))
    return rows


def _rotation_ir(**overrides: object) -> StrategyIR:
    base: dict[str, object] = {
        "strategy_id": "fold-boundary",
        "entry_feature": "compiled",
        "exit_feature": "compiled",
        "proxy_feature": "past_only_adjusted_ohlcv",
        "entry_conditions": [
            Condition(left="close", operator=ConditionOperator.GTE, right=100.0)
        ],
        "exit_conditions": [],
        "ranking_metric": "close",
        "ranking_direction": "desc",
        "execution_mode": "scheduled_rotation",
    }
    base.update(overrides)
    return StrategyIR.model_validate(base)


def _parameters(**overrides: object) -> CandidateParameters:
    base: dict[str, object] = {
        "profile": "compiled_conditions",
        "lookback": 20,
        "threshold": 0.0,
        # Wide enough that the mirrored fixed stop/target never fires in these fixtures;
        # the tests that want it say so.
        "stop_loss_pct": 0.5,
        "take_profit_pct": 10.0,
        "max_positions": 1,
        "rebalance_interval_days": REBALANCE,
        "trailing_stop_pct": 0.75,
    }
    base.update(overrides)
    return CandidateParameters.model_validate(base)


def _decisions(
    rows: list[dict[str, object]], actions: object
) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    """Session index -> tickers bought / sold, read back off the row-aligned array."""

    order = sorted({str(row["date"]) for row in rows})
    index_of = {session: number for number, session in enumerate(order)}
    buys: dict[int, list[str]] = {}
    sells: dict[int, list[str]] = {}
    for row, action in zip(rows, actions, strict=True):
        if action == 0:
            continue
        bucket = buys if action == 1 else sells
        bucket.setdefault(index_of[str(row["date"])], []).append(str(row["ticker"]))
    return buys, sells


# --- fold alignment and seeding ---------------------------------------------


def _executed_orders(rows, strategy_ir, parameters, *, start_index=0):
    from ai_graph.schemas import StrategySpec, CodeCandidate

    sessions = sorted({str(row["date"]) for row in rows})
    strategy = StrategySpec(
        strategy_id=strategy_ir.strategy_id, name="Synthetic fold execution", market="KRX", timeframe="daily",
        entry_conditions=strategy_ir.entry_conditions, exit_conditions=strategy_ir.exit_conditions,
        risk_constraints={"max_position_pct": 1.0 / parameters.max_positions, "stop_loss_pct": parameters.stop_loss_pct}, confidence=1.0,
    )
    candidate = CodeCandidate(
        candidate_id="fold-execution-unit", variant="A", validation_ok=True,
        code="def build_signals(prices):\n    return []", representation="structured",
        strategy_ir=strategy_ir, parameters=parameters,
    )
    tradable = set(sessions[start_index:])
    engine_rows = [row for row in rows if str(row["date"]) in tradable]
    result = backtest_node._fold_engine(strategy, candidate, rows, engine_rows, tradable, store=PreparedFeatureStore(rows))
    buys, sells = {}, {}
    for event in result.order_audit:
        if event.status == "executed":
            target = buys if event.side == "buy" else sells
            target.setdefault(sessions.index(event.date), []).append(event.ticker)
    return buys, sells


def test_the_rotation_grid_is_the_same_absolute_calendar_in_every_fold() -> None:
    sessions = _sessions(24)
    rows = _leadership_rows(sessions, swap_at=10)
    early_buys, early_sells = _executed_orders(rows, _rotation_ir(), _parameters(), start_index=5)
    late_buys, late_sells = _executed_orders(rows, _rotation_ir(), _parameters(), start_index=8)
    # Both folds replace the leader after the same global rotation close (14).
    assert early_sells == late_sells == {15: ["000001"]}
    assert early_buys == {6: ["000001"], 15: ["000002"]}
    assert late_buys == {9: ["000001"], 15: ["000002"]}

def test_a_fold_first_close_signal_fills_at_the_next_open() -> None:
    sessions = _sessions(24)
    rows = _leadership_rows(sessions, swap_at=10)
    buys, sells = _executed_orders(rows, _rotation_ir(), _parameters(), start_index=5)
    assert buys[6] == ["000001"]
    assert 5 not in buys
    assert 5 not in sells and 6 not in sells

def test_rows_after_the_fold_are_never_read() -> None:
    sessions = _sessions(24)
    rows = _leadership_rows(sessions, swap_at=10)
    store = PreparedFeatureStore(rows)

    stopped = store.build_actions(
        _rotation_ir(), _parameters(), reset_session=sessions[5], stop_after_session=sessions[9]
    )

    buys, _ = _decisions(rows, stopped)
    assert max(buys) <= 9


def test_no_future_bar_can_change_a_decision_already_made() -> None:
    """Perturb every close after session 12 and the decisions up to it must not move."""

    sessions = _sessions(24)
    rows = _leadership_rows(sessions, swap_at=10)
    cutoff = sessions[12]
    # Only one of the two names moves, so the ranking after the cutoff really does
    # change - a symmetric shift would leave the order intact and prove nothing.
    perturbed = [
        dict(row)
        if str(row["date"]) <= cutoff or str(row["ticker"]) != "000001"
        else {**row, **{key: float(row[key]) * 3.0 for key in ("open", "high", "low", "close")}}
        for row in rows
    ]

    ir, parameters = _rotation_ir(), _parameters()
    baseline = PreparedFeatureStore(rows).build_actions(ir, parameters, reset_session=sessions[5])
    shifted = PreparedFeatureStore(perturbed).build_actions(
        ir, parameters, reset_session=sessions[5]
    )

    kept = [index for index, row in enumerate(rows) if str(row["date"]) <= cutoff]
    assert [baseline[index] for index in kept] == [shifted[index] for index in kept]
    # The fixture is only meaningful if the perturbation actually changed something.
    assert list(baseline) != list(shifted)


# --- the engine's fixed stop, mirrored --------------------------------------


def test_a_stopped_out_name_releases_its_slot_and_the_next_session_refills_it() -> None:
    sessions = _sessions(12)
    rows = []
    for index, session in enumerate(sessions):
        rows.append(_bar(session, "000001", 120.0 if index < 5 else 96.0))
        rows.append(_bar(session, "000002", 110.0))
    buys, sells = _executed_orders(rows, _rotation_ir(), _parameters(stop_loss_pct=0.08))
    assert buys[1] == ["000001"]
    assert sells[6] == ["000001"]
    # The same next open sells first, then fills the waiting eligible replacement.
    assert buys[6] == ["000002"]

def test_a_take_profit_of_ten_means_no_target_at_all() -> None:
    """Catalogue rows ship `take_profit_pct=10.0` to say "no target"; +1000% is not one."""

    sessions = _sessions(8)
    rows = [_bar(session, "000001", 100.0 + index * 40.0) for index, session in enumerate(sessions)]
    store = PreparedFeatureStore(rows)

    actions = store.build_actions(
        _rotation_ir(), _parameters(take_profit_pct=10.0), reset_session=sessions[0]
    )

    _, sells = _decisions(rows, actions)
    assert sells == {}


# --- reporting definitions --------------------------------------------------


def test_the_win_rate_counts_closed_trades_not_days_spent_in_cash() -> None:
    """A flat day is not a losing trade.

    The aggregate published "share of sessions with a positive return" as `win_rate`.
    Every session the fold sat in cash returns exactly 0.0 and counted against it, so
    the deployed run reported 19.8% - which reads as "loses eight trades in ten" and
    was really "was in cash more than half the time".
    """

    returns = [0.0] * 6 + [0.02, -0.01]
    trade_pnl = [12_000.0, -4_000.0, 900.0]

    assert backtest_node._positive_day_rate(returns) == pytest.approx(1 / 8)
    assert backtest_node._walk_forward_win_rate(trade_pnl) == pytest.approx(2 / 3)
    assert backtest_node._walk_forward_win_rate([]) is None

    metrics = backtest_node._walk_forward_aggregate_metrics(returns, trade_pnl)
    assert metrics.win_rate == pytest.approx(2 / 3)


# --- metric coverage disclosure ---------------------------------------------


def _coverage_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="coverage-probe",
        name="ROE 상위",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="roe", operator=ConditionOperator.GT, right=0.0)],
        exit_conditions=[Condition(left="close", operator=ConditionOperator.LT, right=1.0)],
        indicators=["roe"],
        risk_constraints={"max_position_pct": 0.5, "stop_loss_pct": 0.5},
        confidence=0.9,
    )


def test_a_metric_the_data_barely_carries_is_disclosed_not_silently_flat(
    monkeypatch, tmp_path
) -> None:
    """A rule cannot fire on a bar whose operand is missing, and the user must be told.

    A missing operand makes the comparison a non-match, so a metric the warehouse only
    carries for part of the window switches the rule off for the rest of it - and the
    report showed a flat curve with nothing saying why. The numbers are still published;
    this only adds the sentence beside them.
    """

    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "coverage"))
    sessions = _sessions(40)
    rows: list[dict[str, object]] = []
    for index, session in enumerate(sessions):
        for ticker in ("000001", "000002"):
            bar = _bar(session, ticker, 100.0 + index)
            if index < 4:  # 10% of the window carries the operand at all.
                bar["roe"] = 12.0
            rows.append(bar)

    strategy = _coverage_strategy()
    candidate = CodeCandidate(
        candidate_id="COV01",
        variant="A",
        code="def build_signals(prices):\n    return []\n",
        validation_ok=True,
        representation="structured",
        strategy_ir=_rotation_ir(
            entry_conditions=[
                Condition(left="roe", operator=ConditionOperator.GT, right=0.0)
            ],
            exit_conditions=[
                Condition(left="close", operator=ConditionOperator.LT, right=1.0)
            ],
            ranking_metric=None,
            execution_mode="event_driven",
        ),
        parameters=_parameters(max_positions=2),
    )

    result = backtest_node.run_candidate_backtest(
        strategy, [candidate], price_rows=rows, _walk_forward_enabled=False
    )

    coverage = result.feature_coverage["rule_metric_coverage"]
    assert coverage["roe"] == pytest.approx(0.10)
    assert coverage["close"] == pytest.approx(1.0)
    assert any("roe" in reason and "10%" in reason for reason in result.fallback_reasons)
    # Disclosure never blanks the result.
    assert result.selected_candidate.metrics is not None


# --- the walk-forward report, end to end ------------------------------------


def _walk_forward_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="fold-boundary-rsi",
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


def _walk_forward_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for day_index, session in enumerate(_sessions(250)):
        for ticker_index in range(8):
            close = (
                50.0
                + ticker_index * 3.0
                + day_index * 0.05
                + ((day_index + ticker_index * 7) % 21 - 10) * 0.4
            )
            volume = 500_000.0 + ticker_index * 2_000.0 + day_index * 100.0
            rows.append(
                {
                    "date": session,
                    "ticker": f"{ticker_index + 1:06d}",
                    "open": close * 0.998,
                    "high": close * 1.012,
                    "low": close * 0.988,
                    "close": close,
                    "volume": volume,
                    "raw_notional": volume * close,
                    # Dense enough that the rule has something to hold in every month:
                    # a fold that sits flat because nothing was ever eligible would say
                    # nothing about the fold boundary this file is pinning.
                    "rsi": 20.0 + float((day_index + ticker_index * 3) % 30),
                }
            )
    return rows


@pytest.fixture(scope="module")
def walk_forward_result(tmp_path_factory):
    import os

    strategy = _walk_forward_strategy()
    rows = _walk_forward_rows()
    candidates = generate_loop3_candidates(
        Loop3Request(
            strategy=strategy,
            variant="A",
            trace_id="fold-boundary",
            max_positions=4,
            server_only=True,
        )
    ).candidates
    previous = os.environ.get(backtest_node.BACKTEST_CACHE_DIR_ENV)
    os.environ[backtest_node.BACKTEST_CACHE_DIR_ENV] = str(
        tmp_path_factory.mktemp("fold-boundary-cache")
    )
    try:
        with backtest_node._CandidateBacktestSession(strategy, rows) as session:
            yield backtest_node.run_candidate_backtest(strategy, candidates, _session=session)
    finally:
        if previous is None:
            os.environ.pop(backtest_node.BACKTEST_CACHE_DIR_ENV, None)
        else:
            os.environ[backtest_node.BACKTEST_CACHE_DIR_ENV] = previous


def test_effective_trade_count_means_positions_opened_on_both_paths(
    walk_forward_result,
) -> None:
    """One label, one unit.

    Walk-forward counted both order legs (445) while the single-pass path counted
    positions opened (371), so the same run answered "how many trades?" two ways and the
    minimum-trades gate judged two different quantities.
    """

    walk_forward = walk_forward_result.walk_forward
    assert walk_forward.status == "ready"
    summary = walk_forward_result.engine_summary
    opened = sum(1 for fill in walk_forward.fills if str(fill.get("side")) == "buy")

    assert summary["effective_trade_count"] == opened
    assert summary["filled_order_legs"] == len(walk_forward.fills)
    assert summary["executed_sell_count"] == len(walk_forward.fills) - opened


def test_folds_no_longer_spend_most_of_the_evaluation_month_in_cash(
    walk_forward_result,
) -> None:
    """A fold invests from its first tradable session, not from whenever the grid lands.

    Deployed, 506 of 896 evaluation sessions returned exactly 0.0 - a portfolio in
    100% cash - because the fold's rotation grid restarted at its own context window.
    """

    walk_forward = walk_forward_result.walk_forward
    daily = walk_forward.daily_returns
    flat_share = sum(1 for value in daily.values() if value == 0.0) / len(daily)
    assert flat_share < 0.20, f"평가일의 {flat_share:.0%}가 현금 상태 — 폴드 위상 드리프트"

    # The sharper form of the same claim: a fold may be flat for the one session its
    # first fills take to reach the next open, and no longer than that.
    for selection in walk_forward.fold_selections:
        sessions = [item for item in selection.evaluation_sessions if item in daily]
        leading_flat = 0
        for item in sessions:
            if daily[item] != 0.0:
                break
            leading_flat += 1
        assert leading_flat <= 2, (
            f"폴드 {selection.fold_index}가 평가 시작 후 {leading_flat}세션 동안 현금 상태"
        )


def test_the_reported_win_rate_is_a_trade_statistic_on_a_real_run(
    walk_forward_result,
) -> None:
    summary = walk_forward_result.engine_summary
    aggregate = walk_forward_result.walk_forward.aggregate_metrics

    assert summary["closed_trade_count"] > 0
    # The two are different measurements and the report must not print one as the other.
    assert aggregate.win_rate != pytest.approx(summary["positive_day_rate"])
    # A trade win rate over N closed trades can only be a multiple of 1/N.
    assert aggregate.win_rate * summary["closed_trade_count"] == pytest.approx(
        round(aggregate.win_rate * summary["closed_trade_count"])
    )


def test_the_aggregate_measures_the_benchmark_over_its_own_evaluation_sessions(
    walk_forward_result,
) -> None:
    """Excess return used to be absent on every five-year run.

    The aggregate covers the folds' evaluation sessions, not the whole window, so it had
    no benchmark to subtract and the acceptance floor fell back to the candidate's own
    fitted window. It now compounds the proxy over exactly those sessions.
    """

    walk_forward = walk_forward_result.walk_forward
    aggregate = walk_forward.aggregate_metrics
    expected = backtest_node.benchmark_return_for_sessions(
        backtest_node._build_benchmark_context(_walk_forward_rows(), None),
        sorted(walk_forward.daily_returns),
    )

    assert aggregate.out_sample_benchmark_return == pytest.approx(
        expected, abs=10 ** -backtest_node.METRIC_ROUND_DIGITS
    )
    assert aggregate.out_sample_excess_return == pytest.approx(
        aggregate.out_sample_return - aggregate.out_sample_benchmark_return,
        abs=10 ** -backtest_node.METRIC_ROUND_DIGITS,
    )
    # Fixed quarter blocks over the same sessions, so the automatic gate has something
    # to judge under walk-forward instead of reading a blank.
    assert aggregate.benchmark_period_count is not None


def test_the_headline_and_the_metric_cards_report_the_same_run(walk_forward_result) -> None:
    """One report, one set of numbers.

    The headline came from the rolling aggregate and the cards from the last fold's
    selection window, so a single report published total return as both -49.4% and
    -13.5%, and Sharpe as both -1.20 and -0.64.
    """

    performance = build_public_backtest_performance(walk_forward_result.model_dump())
    assert performance is not None
    details = {detail.key: detail for detail in performance.metric_details}

    assert details["total_return"].value == pytest.approx(performance.metrics.total_return)
    assert details["sharpe_ratio"].value == pytest.approx(performance.metrics.sharpe_ratio)
    assert details["max_drawdown"].value == pytest.approx(performance.metrics.max_drawdown)


def test_walk_forward_publishes_no_in_sample_block_instead_of_a_zero(
    walk_forward_result,
) -> None:
    """`degradation = 0.0` read as "no overfitting decay", which nothing measured."""

    performance = build_public_backtest_performance(walk_forward_result.model_dump())
    assert performance is not None
    details = {detail.key: detail for detail in performance.metric_details}

    for key in ("in_sample_sharpe", "degradation"):
        assert details[key].value is None
        assert (
            details[key].unavailable_reason
            == backtest_node.WALK_FORWARD_HAS_NO_IN_SAMPLE_BLOCK
        )
