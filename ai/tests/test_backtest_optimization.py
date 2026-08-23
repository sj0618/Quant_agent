from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
import json
import os
import time
from types import SimpleNamespace

import pytest

from ai_graph.nodes import backtest as backtest_node
from ai_graph.nodes.backtest_code import (
    Loop3Request,
    _render_adaptive_signal_code,
    build_code_generation_plan,
    generate_loop3_candidates,
    generate_self_improvement_candidates,
    map_strategy_features,
)
from ai_graph.nodes.backtest_features import PreparedFeatureStore
from ai_graph.schemas import (
    BacktestMetrics,
    CandidateParameters,
    CodeCandidate,
    Condition,
    ConditionOperator,
    StrategyIR,
    StrategySpec,
)


def _strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="optimized-rsi",
        name="Optimized RSI",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator=ConditionOperator.LTE, right=40.0)],
        exit_conditions=[Condition(left="rsi", operator=ConditionOperator.GTE, right=70.0)],
        indicators=["rsi"],
        risk_constraints={
            "max_position_pct": 0.2,
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.3,
        },
        confidence=0.9,
    )


def _rows(days: int = 80, tickers: int = 6) -> list[dict[str, object]]:
    start = date(2024, 1, 1)
    rows: list[dict[str, object]] = []
    for day_index in range(days):
        row_date = (start + timedelta(days=day_index)).isoformat()
        for ticker_index in range(tickers):
            close = (
                100.0
                + ticker_index * 7.0
                + day_index * (ticker_index + 1) * 0.04
                + ((day_index % 9) - 4) * 0.25
            )
            rows.append(
                {
                    "date": row_date,
                    "ticker": f"{ticker_index + 1:06d}",
                    "open": close * 0.997,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": 1_000_000.0
                    + day_index * 1_000.0
                    + (250_000.0 if day_index % 13 == 0 else 0.0),
                    "rsi": 30.0 + float(day_index % 50),
                }
            )
    return rows


def _canonical_hash(result) -> str:
    payload = {
        "selected_candidate": result.selected_candidate.model_dump(mode="json"),
        "equity_curve": [point.model_dump(mode="json") for point in result.equity_curve],
        "engine_summary": result.engine_summary,
        "objective_scores": result.objective_scores_by_candidate,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def test_structured_features_do_not_read_future_rows() -> None:
    strategy = _strategy()
    generated = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="no-lookahead")
    )
    parameters = generated.candidates[1].parameters
    strategy_ir = generated.strategy_ir
    assert parameters is not None
    full_rows = _rows(days=60)
    prefix_length = 6 * 35

    full_actions = PreparedFeatureStore(full_rows).build_actions(strategy_ir, parameters)
    prefix_actions = PreparedFeatureStore(full_rows[:prefix_length]).build_actions(
        strategy_ir, parameters
    )

    assert list(full_actions[:prefix_length]) == list(prefix_actions)


def test_generic_rolling_features_are_prior_only_and_ignore_missing_values() -> None:
    rows = _rows(days=4, tickers=1)
    rows[0]["factor"] = 1.0
    rows[1]["factor"] = None
    rows[2]["factor"] = 3.0
    rows[3]["factor"] = 4.0
    store = PreparedFeatureStore(rows)

    average = store._rolling_metric("factor", 2, "avg")
    maximum = store._rolling_metric("factor", 2, "max")
    last = store._rolling_metric("factor", 2, "last")

    assert list(average[1:]) == [1.0, 1.0, 3.0]
    assert list(maximum[1:]) == [1.0, 1.0, 3.0]
    assert list(last[1:]) == [1.0, 1.0, 3.0]


def test_rank_only_and_consecutive_conditions_emit_compiled_actions() -> None:
    rows = _rows(days=4, tickers=2)
    rank_ir = StrategyIR(
        strategy_id="rank-only",
        entry_feature="close",
        exit_feature="close",
        proxy_feature="close",
        entry_conditions=[
            Condition(
                left="close",
                operator=ConditionOperator.GTE,
                right=0.0,
                universe_rank_pct=0.5,
            )
        ],
    )
    parameters = CandidateParameters(
        profile="compiled_conditions",
        lookback=3,
        threshold=0.0,
        stop_loss_pct=0.5,
        take_profit_pct=5.0,
        max_positions=1,
    )
    rank_actions = PreparedFeatureStore(rows).build_actions(rank_ir, parameters)
    assert rank_actions[1] == 1
    assert sum(action == 1 for action in rank_actions) == 1

    consecutive_ir = rank_ir.model_copy(
        update={
            "strategy_id": "consecutive",
            "entry_conditions": [
                Condition(
                    left="close",
                    operator=ConditionOperator.GTE,
                    right=0.0,
                    consecutive=2,
                )
            ],
        }
    )
    consecutive_actions = PreparedFeatureStore(rows).build_actions(consecutive_ir, parameters)
    assert sum(action == 1 for action in consecutive_actions) == 1
    assert consecutive_actions[2] == 1


def test_structured_profile_actions_match_legacy_reference() -> None:
    strategy = _strategy()
    plan = build_code_generation_plan(strategy, map_strategy_features(strategy))
    rows = _rows(days=80, tickers=3)
    profiles = [
        "long_regime_momentum",
        "quality_trend_hold",
        "volatility_breakout_hold",
        "rolling_sharpe_momentum",
        "dual_sma_trend",
        "low_vol_momentum",
        "breakout_volume",
        "rsi_trend_rebound",
        "mean_reversion_band",
        "return_to_volatility",
        "cash_preserving_trend",
    ]
    action_values = {"BUY": 1, "SELL": -1, "HOLD": 0}
    store = PreparedFeatureStore(rows)
    strategy_ir = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="legacy-equivalence")
    ).strategy_ir

    for profile in profiles:
        parameters = CandidateParameters(
            profile=profile,  # type: ignore[arg-type]
            lookback=20,
            threshold=0.05,
            stop_loss_pct=0.08,
            take_profit_pct=0.3,
            max_positions=2,
        )
        namespace: dict[str, object] = {}
        exec(
            _render_adaptive_signal_code(
                strategy_id=strategy.strategy_id,
                plan=plan,
                profile=profile,
                lookback=parameters.lookback,
                threshold=parameters.threshold,
                stop_loss=parameters.stop_loss_pct,
                take_profit=parameters.take_profit_pct,
                max_positions=parameters.max_positions,
            ),
            namespace,
        )
        legacy_signals = namespace["build_signals"](rows)  # type: ignore[operator]
        legacy_actions = [action_values[str(signal["action"])] for signal in legacy_signals]

        assert list(store.build_actions(strategy_ir, parameters)) == legacy_actions


def test_worker_count_and_disk_cache_are_deterministic(monkeypatch, tmp_path) -> None:
    strategy = _strategy()
    rows = _rows(days=45)
    candidates = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="deterministic")
    ).candidates
    monkeypatch.setattr(backtest_node, "SERIAL_EVALUATION_WORK_ITEMS", 0)

    cache_one = tmp_path / "worker-one"
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(cache_one))
    monkeypatch.setenv(backtest_node.AI_BACKTEST_WORKERS_ENV, "1")
    result_one = backtest_node.run_candidate_backtest(strategy, candidates, price_rows=rows)

    cache_two = tmp_path / "worker-two"
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(cache_two))
    monkeypatch.setenv(backtest_node.AI_BACKTEST_WORKERS_ENV, "2")
    result_two = backtest_node.run_candidate_backtest(strategy, candidates, price_rows=rows)

    assert _canonical_hash(result_one) == _canonical_hash(result_two)


@pytest.mark.skipif(
    "fork" not in backtest_node.get_all_start_methods(),
    reason="structured action workers share prepared arrays through fork",
)
def test_structured_actions_run_in_workers_and_are_reused_for_full(
    monkeypatch, tmp_path
) -> None:
    strategy = _strategy()
    rows = _rows(days=45)
    candidates = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="parallel-actions")
    ).candidates
    original_build_actions = PreparedFeatureStore.build_actions

    def delayed_build_actions(self, strategy_ir, parameters):
        time.sleep(0.05)
        return original_build_actions(self, strategy_ir, parameters)

    monkeypatch.setattr(PreparedFeatureStore, "build_actions", delayed_build_actions)
    monkeypatch.setattr(backtest_node, "SERIAL_EVALUATION_WORK_ITEMS", 0)
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "parallel-actions"))
    monkeypatch.setenv(backtest_node.AI_BACKTEST_WORKERS_ENV, "2")

    with backtest_node._CandidateBacktestSession(strategy, rows) as session:
        selection = session.evaluate(candidates)
        full = session.evaluate([selection[0].candidate], metrics_mode="full")
        rounds = session.execution_stats()["rounds"]

    selection_pids = {item.diagnostics["worker_pid"] for item in selection}
    assert len(selection_pids) == 2
    assert os.getpid() not in selection_pids
    assert set(rounds[0]["action_worker_pids"]) == selection_pids
    assert rounds[0]["action_cache_hits"] == 0
    assert full[0].diagnostics["action_cache_hit"] is True
    assert full[0].diagnostics["action_build_seconds"] == 0.0
    assert rounds[1]["action_cache_hits"] == 1
    assert rounds[1]["action_worker_pids"] == []


def test_market_benchmark_is_prepared_once_per_session(monkeypatch, tmp_path) -> None:
    strategy = _strategy()
    rows = _rows(days=45)
    candidates = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="benchmark-context")
    ).candidates
    original = backtest_node._equal_weight_benchmark_curve
    calls = 0

    def counted(price_rows):
        nonlocal calls
        calls += 1
        return original(price_rows)

    monkeypatch.setattr(backtest_node, "_equal_weight_benchmark_curve", counted)
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "benchmark-context"))
    monkeypatch.setenv(backtest_node.AI_BACKTEST_WORKERS_ENV, "1")

    backtest_node.run_candidate_backtest(strategy, candidates, price_rows=rows)

    assert calls == 1


def test_fresh_and_disk_cache_results_are_identical(monkeypatch, tmp_path) -> None:
    strategy = _strategy()
    rows = _rows(days=35)
    candidate = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="disk-cache")
    ).candidates[0]
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "cache"))
    monkeypatch.setenv(backtest_node.AI_BACKTEST_WORKERS_ENV, "1")

    with backtest_node._CandidateBacktestSession(strategy, rows) as first:
        fresh = first.evaluate([candidate])[0]
        assert not fresh.diagnostics["cache_hit"]
    with backtest_node._CandidateBacktestSession(strategy, rows) as second:
        cached = second.evaluate([candidate])[0]
        assert cached.diagnostics["cache_hit"]
        assert cached.diagnostics["cache_level"] == "disk"

    fresh_payload = {
        "candidate": fresh.candidate.model_dump(mode="json"),
        "summary": fresh.engine_summary,
        "equity": [item.model_dump(mode="json") for item in fresh.equity_curve or []],
        "score": fresh.objective_score,
    }
    cached_payload = {
        "candidate": cached.candidate.model_dump(mode="json"),
        "summary": cached.engine_summary,
        "equity": [item.model_dump(mode="json") for item in cached.equity_curve or []],
        "score": cached.objective_score,
    }
    assert fresh_payload == cached_payload


def test_disk_cache_discards_stale_dependency_failures(monkeypatch, tmp_path) -> None:
    """A cache made without quantstats must not poison a repaired worker process."""
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "cache"))
    cache = backtest_node._DiskEvaluationCache()
    candidate = CodeCandidate(
        candidate_id="stale-quantstats-failure",
        variant="A",
        code="def build_signals(prices):\n    return []\n",
        validation_ok=True,
    )
    key = "stale-quantstats-failure"
    path = cache.root / f"{key}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": backtest_node.BACKTEST_CACHE_SCHEMA_VERSION,
                "candidate": candidate.model_dump(mode="json"),
                "engine_summary": None,
                "equity_curve": [],
                "objective_score": None,
                "quantstats_dependency_error": True,
                "diagnostics": {"error_type": "ModuleNotFoundError"},
                "ticker_actions": [],
            }
        ),
        encoding="utf-8",
    )

    assert cache.load(key, candidate) is None
    assert not path.exists()


def test_prepared_market_cache_skips_repeated_engine_conversion(monkeypatch) -> None:
    strategy = _strategy()
    rows = _rows(days=12, tickers=3)
    original = backtest_node._engine_market_rows
    calls = 0

    def counted(price_rows):
        nonlocal calls
        calls += 1
        return original(price_rows)

    backtest_node._clear_prepared_market_cache()
    monkeypatch.setattr(backtest_node, "_engine_market_rows", counted)
    try:
        with backtest_node._CandidateBacktestSession(strategy, rows) as first:
            assert not first.prepared_market_cache_hit
        with backtest_node._CandidateBacktestSession(strategy, rows) as second:
            assert second.prepared_market_cache_hit
            assert second.preparation_phases["engine_row_conversion_seconds"] == 0.0
            assert second.preparation_phases["engine_market_index_seconds"] == 0.0
    finally:
        backtest_node._clear_prepared_market_cache()

    assert calls == 1


def test_data_fingerprint_tracks_content_and_input_order() -> None:
    rows = _rows(days=3, tickers=2)
    same_rows = [dict(row) for row in rows]
    changed_rows = [dict(row) for row in rows]
    changed_rows[-1]["rsi"] = float(changed_rows[-1]["rsi"]) + 1.0

    fingerprint, descriptor = backtest_node._data_fingerprint(rows)
    same_fingerprint, _ = backtest_node._data_fingerprint(same_rows)
    changed_fingerprint, _ = backtest_node._data_fingerprint(changed_rows)
    _, reversed_descriptor = backtest_node._data_fingerprint(list(reversed(rows)))

    assert fingerprint == same_fingerprint
    assert fingerprint != changed_fingerprint
    assert descriptor["rows_are_sorted"] is True
    assert reversed_descriptor["rows_are_sorted"] is False


def test_improvement_candidates_are_bounded_and_normalized() -> None:
    strategy = _strategy()
    generated = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="bounded")
    )
    improved = generate_self_improvement_candidates(
        strategy,
        generated.code_plan.model_dump(mode="python"),
        start_index=4,
        iteration=1,
        max_positions=5,
    )
    identities = {backtest_node._candidate_identity(candidate) for candidate in improved}

    assert 1 <= len(improved) <= 6
    assert len(identities) == len(improved)
    assert (
        sum(
            item.parameters.profile == "compiled_conditions" for item in improved if item.parameters
        )
        >= 2
    )


def test_candidate_profiles_are_schema_profiles_only() -> None:
    plan = build_code_generation_plan(_strategy(), map_strategy_features(_strategy()))
    profiles = backtest_node.generate_self_improvement_candidates(
        _strategy(), plan.model_dump(mode="python"), start_index=4, iteration=1
    )
    assert all(item.parameters is not None for item in profiles)
    # CandidateParameters validation makes this assertion a regression test for any
    # profile returned by the generator that is outside StructuredProfile.
    assert all(item.parameters.profile for item in profiles if item.parameters)


def test_selection_score_does_not_peek_at_holdout_sharpe() -> None:
    rows = _rows(days=20)
    common = dict(
        sharpe_ratio=1.0,
        max_drawdown=-0.1,
        win_rate=0.6,
        total_return=0.1,
        in_sample_sharpe=1.0,
        degradation=0.0,
    )
    weak_holdout = BacktestMetrics(**common, out_sample_sharpe=-5.0)
    strong_holdout = BacktestMetrics(**common, out_sample_sharpe=5.0)
    summary = {"effective_trade_count": 8, "trade_win_rate": 0.6}

    assert backtest_node._objective_score(
        weak_holdout, summary, rows
    ) == backtest_node._objective_score(strong_holdout, summary, rows)


def test_selection_score_rewards_training_return_when_risk_is_equal() -> None:
    rows = _rows(days=300)
    common = dict(
        sharpe_ratio=0.8,
        max_drawdown=-0.15,
        win_rate=0.55,
        total_return=0.4,
        in_sample_sharpe=0.8,
        out_sample_sharpe=0.7,
        degradation=0.1,
        in_sample_max_drawdown=-0.15,
    )
    lower_return = BacktestMetrics(**common, in_sample_return=0.10)
    higher_return = BacktestMetrics(**common, in_sample_return=0.30)
    summary = {"selection_buy_count": 12}

    assert backtest_node._objective_score(
        higher_return,
        summary,
        rows,
    ) > backtest_node._objective_score(lower_return, summary, rows)


def test_temporary_relaxed_objective_floor_boundaries() -> None:
    metrics = BacktestMetrics(
        sharpe_ratio=0.0,
        max_drawdown=-0.50,
        win_rate=0.5,
        total_return=0.0,
        in_sample_sharpe=0.0,
        out_sample_sharpe=0.0,
        degradation=0.0,
    )
    result = SimpleNamespace(
        selected_candidate=SimpleNamespace(candidate_id="temporary-floor", metrics=metrics),
        engine_summary={"effective_trade_count": 5},
    )

    assert backtest_node._passes_objective_floor(result)
    result.selected_candidate.metrics = metrics.model_copy(update={"out_sample_sharpe": -0.01})
    assert not backtest_node._passes_objective_floor(result)
    result.selected_candidate.metrics = metrics.model_copy(update={"max_drawdown": -0.501})
    assert not backtest_node._passes_objective_floor(result)


def test_fixed_period_benchmark_rule_allows_large_regime_wins() -> None:
    period = backtest_node.BENCHMARK_EVALUATION_PERIOD_DAYS
    benchmark_returns = [0.0] * (period * 4)
    strategy_returns = [
        *([0.002] * period),
        *([-0.001] * period),
        *([0.004] * period),
        *([0.0] * period),
    ]

    stats = backtest_node._benchmark_period_stats(strategy_returns, benchmark_returns)

    assert stats.count == 4
    assert stats.win_rate == 0.5
    assert stats.loss_rate == 0.25


def test_automatic_benchmark_gate_treats_exactly_half_losing_periods_as_defeat() -> None:
    metrics = BacktestMetrics(
        sharpe_ratio=0.9,
        max_drawdown=-0.25,
        win_rate=0.55,
        total_return=0.60,
        in_sample_sharpe=0.8,
        out_sample_sharpe=0.7,
        degradation=0.1,
        in_sample_return=0.30,
        out_sample_return=0.23,
        in_sample_benchmark_return=0.20,
        out_sample_benchmark_return=0.10,
        in_sample_excess_return=0.10,
        out_sample_excess_return=0.13,
        benchmark_period_count=8,
        benchmark_period_win_rate=0.50,
        benchmark_period_loss_rate=0.375,
        in_sample_benchmark_period_count=5,
        in_sample_benchmark_period_win_rate=0.60,
        in_sample_benchmark_period_loss_rate=0.40,
        out_sample_benchmark_period_count=3,
        out_sample_benchmark_period_win_rate=2 / 3,
        out_sample_benchmark_period_loss_rate=1 / 3,
    )
    result = SimpleNamespace(
        strategy_a=SimpleNamespace(selection_mode="automatic"),
        selected_candidate=SimpleNamespace(candidate_id="benchmark-winner", metrics=metrics),
        engine_summary={"effective_trade_count": 20},
        backtest_payload={
            "benchmark": {"primary": {"available": True, "return": 0.32}}
        },
    )

    assert backtest_node._passes_objective_floor(result)

    # Exactly half is a defeat, not a draw: the rate is compared with >=.
    result.selected_candidate.metrics = metrics.model_copy(
        update={"out_sample_benchmark_period_loss_rate": 0.50}
    )
    assert not backtest_node._passes_objective_floor(result)

    # The whole-history loss rate is deliberately not a gate any more. It spans the
    # selection split, so it judged the winner partly on the sample it was chosen from,
    # and it could not fail without the hold-out rate above failing too. A candidate that
    # clears the hold-out passes even when its full-history rate is at the old boundary.
    result.selected_candidate.metrics = metrics.model_copy(
        update={"benchmark_period_loss_rate": 0.50}
    )
    assert backtest_node._passes_objective_floor(result)


def test_repeated_round_submits_no_completed_candidate(monkeypatch, tmp_path) -> None:
    strategy = _strategy()
    rows = _rows(days=25)
    candidates = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="round-cache")
    ).candidates
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "round-cache"))
    monkeypatch.setenv(backtest_node.AI_BACKTEST_WORKERS_ENV, "1")

    with backtest_node._CandidateBacktestSession(strategy, rows) as session:
        session.evaluate(candidates)
        cached = session.evaluate(candidates)
        rounds = session.execution_stats()["rounds"]

    assert rounds[0]["new_candidates"] == 3
    assert rounds[1]["new_candidates"] == 0
    assert rounds[1]["cached_candidates"] == 3
    assert cached[0].diagnostics["cache_hit"]
    assert cached[0].diagnostics["cache_level"] == "memory"


def test_python_fallback_timeout_terminates_worker(monkeypatch, tmp_path) -> None:
    strategy = _strategy()
    candidate = CodeCandidate(
        candidate_id="infinite-fallback",
        variant="A",
        code="""def build_signals(prices):
    total = 0
    for left in range(10000):
        for right in range(10000):
            total += left + right
    return []
""",
        validation_ok=True,
    )
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path / "timeout"))
    monkeypatch.setenv(backtest_node.AI_BACKTEST_CANDIDATE_TIMEOUT_ENV, "0.5")

    with backtest_node._CandidateBacktestSession(strategy, _rows(days=3)) as session:
        evaluation = session.evaluate([candidate])[0]
        assert not evaluation.candidate.validation_ok
        assert any("timeout" in item for item in evaluation.candidate.violations)
        assert session._executor is None


def test_expected_max_sharpe_grows_with_the_number_of_candidates():
    """Picking the best of N noisy estimates is biased upward by construction.

    Measured with candidates whose trades were random on real prices: the average
    candidate returned -3.7% and the best-of-six returned +16.2%, with nine of twelve
    trials producing a "profitable" winner out of pure noise. A headline that does not
    subtract this reports the width of the search as if it were skill.
    """
    observations = 1764  # ~7y of daily bars, the in-sample side of a 10y run

    one = backtest_node._expected_max_sharpe(1, observations)
    six = backtest_node._expected_max_sharpe(6, observations)
    fifteen = backtest_node._expected_max_sharpe(15, observations)

    assert one == 0.0
    assert 0.0 < six < fifteen
    # A shorter sample makes the same search more dangerous, not less.
    assert backtest_node._expected_max_sharpe(6, 252) > six


def test_selection_correction_records_the_search_width_without_changing_the_winner():
    metrics = BacktestMetrics(
        sharpe_ratio=0.9,
        max_drawdown=-0.2,
        win_rate=0.5,
        total_return=0.4,
        in_sample_sharpe=0.9,
        out_sample_sharpe=0.1,
        degradation=0.9,
        in_sample_observations=1764,
    )
    candidate = CodeCandidate(
        candidate_id="A1", variant="A", code="def build_signals(p):\n    return []\n",
        validation_ok=True, metrics=metrics,
    )
    result = SimpleNamespace(
        selected_candidate=candidate,
        model_copy=lambda update: SimpleNamespace(**{**result.__dict__, **update}),
    )

    corrected = backtest_node._apply_selection_correction(result, 15)

    assert corrected.selected_candidate.candidate_id == "A1"
    assert corrected.selected_candidate.metrics.candidates_evaluated == 15
    assert corrected.selected_candidate.metrics.selection_adjusted_sharpe < 0.9
    # The uncorrected figures are untouched - the correction adds context, it does not
    # rewrite what the run measured.
    assert corrected.selected_candidate.metrics.in_sample_sharpe == 0.9


def test_headline_reports_the_hold_out_not_the_period_selection_optimised_against():
    headline = backtest_node._headline_metrics(
        {
            "total_return": 0.42,
            "sharpe_ratio": 0.9,
            "max_drawdown": -0.2,
            "in_sample_return": 0.60,
            "in_sample_sharpe": 1.3,
            "in_sample_max_drawdown": -0.15,
            "out_sample_return": -0.08,
            "out_sample_sharpe": -0.25,
            "out_sample_max_drawdown": -0.3,
            "candidates_evaluated": 15,
            "selection_adjusted_sharpe": -0.1,
        }
    )

    assert headline["basis"] == "hold_out"
    assert headline["total_return"] == -0.08
    assert headline["sharpe_ratio"] == -0.25
    assert headline["candidates_evaluated"] == 15
    # Both other bases stay reachable, explicitly labelled.
    assert headline["in_sample"]["sharpe_ratio"] == 1.3
    assert headline["full_period"]["sharpe_ratio"] == 0.9


def _warmup_store(bars=400, tickers=("000001", "000002")):
    rows = []
    for ticker in tickers:
        price = 10_000.0
        for index in range(bars):
            price *= 1.004 if index % 3 else 0.997
            rows.append(
                {
                    "date": (date(2016, 1, 1) + timedelta(days=index)).isoformat(),
                    "ticker": ticker,
                    "open": price,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "volume": 1_000_000.0,
                    "rsi": 40.0,
                }
            )
    return PreparedFeatureStore(rows), len(tickers)


def test_indicator_windows_wait_for_a_full_lookback():
    """A 20-day average must not be the previous close on the second bar.

    features() computed every window as min(lookback, index), so each indicator reported
    a shorter one under its own name and `high` could be a single prior close - letting a
    breakout fire on bar two. The rows inside the warm-up now stay unready.
    """
    store, ticker_count = _warmup_store()
    lookback = 60

    matrix = store.features(lookback)
    not_ready = int((matrix[:, 0] == 0).sum())

    # Exactly the warm-up rows of each ticker, not just each ticker's first bar.
    assert not_ready == lookback * ticker_count

    closes = store.close[store.indices_by_ticker["000001"]]
    first_ready = store.indices_by_ticker["000001"][lookback]
    # The reported average is the real lookback-bar mean, not a truncated one.
    assert matrix[first_ready][1] == pytest.approx(closes[0:lookback].mean())


def test_no_action_fires_before_its_lookback_has_elapsed():
    store, _ = _warmup_store()
    parameters = CandidateParameters(
        profile="long_regime_momentum",
        lookback=60,
        threshold=0.05,
        stop_loss_pct=0.08,
        take_profit_pct=0.25,
        max_positions=5,
    )
    ir = StrategyIR(
        strategy_id="warmup",
        entry_feature="close",
        exit_feature="close",
        proxy_feature="close",
    )

    actions = list(store.build_actions(ir, parameters))

    ordinal = {}
    for indices in store.indices_by_ticker.values():
        for position, index in enumerate(indices):
            ordinal[index] = position
    fired = [ordinal[i] for i, a in enumerate(actions) if a != 0]
    assert fired, "the fixture should still produce signals after the warm-up"
    assert min(fired) >= parameters.lookback


def test_candidate_stop_and_target_reach_the_engine():
    """The engine is the only place a stop is applied, so the search values must get there.

    Stop-loss used to be evaluated twice: once by the action generator against the
    signal-day close, once by the engine against the price actually paid at the next
    open. Removing the first copy is only correct if the candidate's own stop/target
    still reach the second - otherwise the search over them quietly stops mattering.
    """
    strategy = StrategySpec(
        strategy_id="stops",
        name="Stops",
        market="KOSPI",
        timeframe="1d",
        entry_conditions=[Condition(left="rsi", operator=ConditionOperator.LT, right=30.0)],
        risk_constraints={"stop_loss_pct": 0.08, "take_profit_pct": 0.2},
        confidence=0.5,
    )
    parameters = CandidateParameters(
        profile="long_regime_momentum",
        lookback=60,
        threshold=0.05,
        stop_loss_pct=0.03,
        take_profit_pct=0.45,
        max_positions=5,
    )
    ir = StrategyIR(
        strategy_id="stops", entry_feature="close", exit_feature="close", proxy_feature="close"
    )
    candidate = CodeCandidate(
        candidate_id="A1", variant="A", code="def build_signals(p):\n    return []\n",
        validation_ok=True, representation="structured", strategy_ir=ir, parameters=parameters,
    )

    controls = backtest_node._engine_risk_controls(strategy, candidate=candidate)

    assert controls.stop_loss_pct == 0.03
    assert controls.take_profit_pct == 0.45
    # With no candidate the strategy's own constraints still apply.
    plain = backtest_node._engine_risk_controls(strategy)
    assert plain.stop_loss_pct == 0.08
    assert plain.take_profit_pct == 0.2


def test_action_generator_no_longer_emits_its_own_stop_loss_exits():
    """Only rule exits and the profile's trailing stop come from the generator."""
    import inspect

    from ai_graph.nodes import backtest_features

    source = inspect.getsource(backtest_features.PreparedFeatureStore)
    assert "parameters.stop_loss_pct" not in source
    assert "parameters.take_profit_pct" not in source
    # The trailing stop is the profile's own rule and the engine does not model it.
    assert "trailing_stop" in source


def test_canonical_analysis_contract_seals_one_hundred_million_krw() -> None:
    assert backtest_node.CANONICAL_ANALYSIS_INITIAL_CAPITAL == 100_000_000.0
    assert backtest_node.DEFAULT_INITIAL_CAPITAL == 1_000_000.0


def test_missing_strategy_sizing_is_fail_closed_not_default_ten() -> None:
    strategy = _strategy().model_copy(update={"risk_constraints": {}})

    with pytest.raises(ValueError, match="max_position_pct"):
        backtest_node._requested_max_positions(strategy)


def test_short_history_hides_aggregate_oos_and_benchmark_claims() -> None:
    metadata = backtest_node._walk_forward_metadata(backtest_node._walk_forward_sample(_rows(days=79)))

    assert metadata["status"] == backtest_node.INSUFFICIENT_WALK_FORWARD_SAMPLE
    assert metadata["aggregate_oos_available"] is False
    assert metadata["benchmark_comparison_available"] is False


def test_official_tr_benchmark_keeps_units_fixed_between_monthly_rebalances() -> None:
    curve, total_return = backtest_node._official_krx_tr_benchmark_curve(
        {
            "2024-01-02": 100.0,
            "2024-01-31": 110.0,
            "2024-02-01": 110.0,
            "2024-02-29": 121.0,
        },
        {
            "2024-01-02": 100.0,
            "2024-01-31": 100.0,
            "2024-02-01": 100.0,
            "2024-02-29": 100.0,
        },
        {"2024-01": (0.5, 0.5), "2024-02": (1.0, 0.0)},
    )

    assert [point.cumulative_return for point in curve] == pytest.approx(
        [0.0, 0.05, 0.05, 0.155]
    )
    assert total_return == pytest.approx(0.155)


def test_undefined_metric_is_published_as_null_with_a_reason() -> None:
    availability = backtest_node._undefined_metric_availability(
        [{"metric": "out_sample_sharpe", "reason": "zero return variance"}]
    )

    assert availability["out_sample_sharpe"] == {
        "value": None,
        "unavailable_reason": "zero return variance",
    }


def _monthly_sessions(month_count: int, sessions_per_month: int = 12) -> list[dict[str, str]]:
    return [
        {"date": date(2020 + month_index // 12, month_index % 12 + 1, day).isoformat()}
        for month_index in range(month_count)
        for day in range(1, sessions_per_month + 1)
    ]


def test_walk_forward_policy_uses_disjoint_monthly_evaluation_folds() -> None:
    rows = _monthly_sessions(40, sessions_per_month=20)
    policy = backtest_node._walk_forward_split_policy(rows)
    sample = backtest_node._walk_forward_sample(rows)

    assert len(policy.warmup_sessions) == 20
    assert len(policy.folds) == 24
    assert policy.folds[0].train_sessions[0].startswith("2020-02")
    assert len({session for fold in policy.folds for session in fold.evaluation_sessions}) == 480
    assert sample.valid_fold_count == 24
    assert sample.unique_evaluation_session_count == 480
    assert sample.status == backtest_node.READY_WALK_FORWARD


def test_walk_forward_completeness_uses_full_engine_curve_not_public_sample() -> None:
    targets = {
        date(2024, 1, day).isoformat()
        for day in range(1, 21)
    }
    engine_result = SimpleNamespace(
        equity_curve=[
            SimpleNamespace(date=session, daily_return=index / 10_000)
            for index, session in enumerate(sorted(targets), start=1)
        ]
    )

    returns = backtest_node._complete_target_returns(engine_result, targets)

    assert returns is not None
    assert len(returns) == 20
    assert set(returns) == targets


def test_walk_forward_policy_fails_closed_at_23_folds_and_479_sessions() -> None:
    twenty_three_folds = _monthly_sessions(39, sessions_per_month=20)
    four_seventy_nine_sessions = _monthly_sessions(40, sessions_per_month=20)[:-1]

    assert backtest_node._walk_forward_sample(twenty_three_folds).valid_fold_count == 23
    assert (
        backtest_node._walk_forward_sample(twenty_three_folds).status
        == backtest_node.INSUFFICIENT_WALK_FORWARD_SAMPLE
    )
    assert (
        backtest_node._walk_forward_sample(four_seventy_nine_sessions).status
        == backtest_node.INSUFFICIENT_WALK_FORWARD_SAMPLE
    )


def test_official_tr_benchmark_rejects_missing_monthly_lagged_weight() -> None:
    with pytest.raises(ValueError, match="missing lagged official benchmark weights"):
        backtest_node._official_krx_tr_benchmark_curve(
            {"2024-01-02": 100.0, "2024-02-01": 101.0},
            {"2024-01-02": 100.0, "2024-02-01": 101.0},
            {"2024-01": (0.5, 0.5)},
        )
