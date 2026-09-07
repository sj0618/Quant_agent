"""Synthetic unit regressions for benchmark source and OOS interval alignment.

These prices are deliberately constructed; they are not market-performance evidence.
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ai_graph.nodes import backtest as b
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.schemas import BacktestMetrics
from test_fold_execution_boundary import _walk_forward_rows, _walk_forward_strategy
from test_official_benchmark_contract import _official_benchmark, _price_rows, _sessions


def _small_context():
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    levels = dict(zip(days, [100.0, 110.0, 120.0, 130.0], strict=True))
    official = {
        "available": True, "kospi_tr": levels, "kosdaq_tr": levels,
        "monthly_weights": {"2023-12": [0.5, 0.5]},
    }
    return days, b._build_benchmark_context(_price_rows(days), official)


def _metrics(**updates):
    values = dict(
        sharpe_ratio=1.0, max_drawdown=-0.1, win_rate=0.5, total_return=-0.5,
        in_sample_sharpe=1.0, out_sample_sharpe=1.0, degradation=0.0,
        out_sample_return=-0.2, in_sample_benchmark_return=0.4,
        out_sample_benchmark_return=0.2, out_sample_excess_return=0.3,
        benchmark_period_count=3, benchmark_period_win_rate=1.0,
        benchmark_period_loss_rate=0.0, out_sample_benchmark_period_count=3,
        out_sample_benchmark_period_win_rate=1.0, out_sample_benchmark_period_loss_rate=0.0,
    )
    values.update(updates)
    return BacktestMetrics(**values)


def _rolling_result(aggregate, *, primary=True):
    return SimpleNamespace(
        strategy_a=SimpleNamespace(selection_mode="automatic"),
        selected_candidate=SimpleNamespace(metrics=_metrics()),
        walk_forward=SimpleNamespace(status="ready", aggregate_metrics=aggregate),
        engine_summary={"effective_trade_count": 20},
        # The full window intentionally loses while OOS wins.
        backtest_payload={"benchmark": {
            "primary": {"available": primary, "return": 2.0},
            "auxiliary": {"return": 2.0},
        }},
    )


def test_official_daily_returns_and_provenance_use_the_same_source():
    days, context = _small_context()
    aligned = b.benchmark_daily_returns_for_sessions(context, days[1:])
    assert aligned == pytest.approx([0.1, 120 / 110 - 1, 130 / 120 - 1])
    assert context.selection_return == pytest.approx(0.1)
    aggregate = b._walk_forward_aggregate_metrics([0.1] * 3, benchmark_returns=aligned)
    assert aggregate.out_sample_benchmark_return == pytest.approx(0.3)
    provenance = b._benchmark_provenance(context, days[1:])
    assert provenance["primary"]["return"] == pytest.approx(0.3)
    assert provenance["primary"]["used_for_acceptance"] is True
    assert provenance["auxiliary"]["return"] == 0.0
    assert provenance["auxiliary"]["used_for_acceptance"] is False
    assert provenance["comparison"]["source"] == "primary"
    assert provenance["comparison"]["period"] == "walk_forward_evaluation"
    assert provenance["comparison"]["return"] == pytest.approx(0.3)


def test_lookup_preserves_requested_order_and_does_not_add_skipped_days():
    days, context = _small_context()
    assert b.benchmark_daily_returns_for_sessions(context, [days[3], days[1]]) == pytest.approx(
        [130 / 120 - 1, 0.1]
    )
    assert b.benchmark_return_for_sessions(context, [days[1], days[3]]) == pytest.approx(
        1.1 * 130 / 120 - 1
    )


@pytest.mark.parametrize("case", ["missing", "duplicate", "first_session", "length", "previous"])
def test_incomplete_or_ambiguous_daily_intervals_are_unavailable(case):
    days, context = _small_context()
    wanted = days[1:3]
    kwargs = {}
    if case == "missing":
        wanted = [days[1], "2099-01-01"]
    elif case == "duplicate":
        wanted = [days[1], days[1]]
    elif case == "first_session":
        wanted = days[:2]
    elif case == "length":
        context = replace(context, daily_returns=context.daily_returns[:-1])
    else:
        kwargs = {"previous_sessions": [days[0], days[0]]}
    assert b.benchmark_daily_returns_for_sessions(context, wanted, **kwargs) == []
    provenance = b._benchmark_provenance(context, wanted, **kwargs)
    assert provenance["comparison"]["available"] is False
    assert provenance["comparison"]["return"] is None
    assert provenance["primary"]["used_for_acceptance"] is False
    assert provenance["auxiliary"]["used_for_acceptance"] is False


def test_high_full_window_coverage_does_not_allow_missing_oos_or_bridge_levels():
    days = _sessions()
    supplied = _official_benchmark(days)
    missing = days[10]
    supplied["kospi_tr"].pop(missing)
    context = b._build_benchmark_context(_price_rows(days), supplied)
    assert context.primary_available is True
    assert context.primary_coverage["coverage_ratio"] > 0.99
    assert b.benchmark_daily_returns_for_sessions(context, [missing]) == []
    # The next day's value exists, but its immediate prior price session does not.
    assert b.benchmark_daily_returns_for_sessions(context, [days[11]]) == []
    assert b.benchmark_return_for_sessions(context, [days[12]]) == pytest.approx(0.001, abs=1e-6)
    assert b._benchmark_provenance(context, [days[11]])["comparison"]["source"] == "primary"


@pytest.mark.parametrize("primary", [True, False])
def test_floor_compares_strategy_and_benchmark_on_the_same_oos_window(primary):
    aggregate = _metrics(total_return=0.331, out_sample_return=0.331,
                         out_sample_benchmark_return=0.2, out_sample_excess_return=0.131)
    result = _rolling_result(aggregate, primary=primary)
    assert b._floor_metrics(result).total_return == pytest.approx(0.331)
    assert b.objective_floor_reasons(result) == []


def test_missing_oos_benchmark_never_inherits_training_comparisons():
    aggregate = b._walk_forward_aggregate_metrics([0.1] * 3, benchmark_returns=[0.0])
    result = _rolling_result(aggregate)
    floor = b._floor_metrics(result)
    assert floor.total_return == pytest.approx(0.331)
    assert floor.in_sample_benchmark_return is None
    for name in b._BENCHMARK_AGGREGATE_FIELDS:
        assert getattr(floor, name) is None
    reasons = b.objective_floor_reasons(result)
    assert any("unavailable" in reason for reason in reasons)
    assert not any("-50.00%" in reason or "200.00%" in reason for reason in reasons)


def test_proxy_policy_is_preserved_and_labelled_for_oos():
    days, _ = _small_context()
    context = b._build_benchmark_context(_price_rows(days))
    provenance = b._benchmark_provenance(context, days[1:])
    assert provenance["primary"]["available"] is False
    assert provenance["auxiliary"]["used_for_acceptance"] is True
    assert provenance["comparison"]["source"] == "auxiliary"
    assert provenance["comparison"]["return"] == 0.0


def test_same_official_endpoints_with_different_daily_paths_do_not_share_cache(tmp_path, monkeypatch):
    from test_official_benchmark_contract import _session_rows, _session_strategy
    from ai_graph.schemas import CodeCandidate

    monkeypatch.setenv(b.BACKTEST_CACHE_DIR_ENV, str(tmp_path))
    rows = _session_rows()
    days = sorted({str(row["date"]) for row in rows})
    first = _official_benchmark(days)
    changed = _official_benchmark(days)
    changed["kospi_tr"][days[5]] *= 1.03
    candidate = CodeCandidate(
        candidate_id="path-check", variant="A",
        code="def build_signals(prices):\n    return []\n", validation_ok=True,
    )
    with b._CandidateBacktestSession(_session_strategy(), rows, official_benchmark=first) as left:
        left_key = left._disk_cache_key(candidate, "selection")
        left_return = left.benchmark_context.total_return
    with b._CandidateBacktestSession(_session_strategy(), rows, official_benchmark=changed) as right:
        assert right.benchmark_context.total_return == left_return
        assert right._disk_cache_key(candidate, "selection") != left_key


@pytest.mark.parametrize("gap", [None, "evaluation", "bridge"])
def test_full_walk_forward_keeps_official_oos_source_in_payload_and_each_candidate(tmp_path, monkeypatch, gap):
    rows, strategy = _walk_forward_rows(), _walk_forward_strategy()
    days = sorted({str(row["date"]) for row in rows})
    levels = {day: 100 * 1.001**index for index, day in enumerate(days)}
    official = {
        "available": True, "kospi_tr": levels, "kosdaq_tr": levels,
        "monthly_weights": {b._previous_month(day[:7]): [0.5, 0.5] for day in days},
    }
    if gap:
        fold = b._walk_forward_split_policy(rows).folds[0]
        missing = fold.evaluation_sessions[0] if gap == "evaluation" else fold.validation_sessions[-1]
        official["kospi_tr"].pop(missing)
    candidates = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="official-oos-unit",
                     max_positions=4, server_only=True)
    ).candidates[:2]
    monkeypatch.setenv(b.BACKTEST_CACHE_DIR_ENV, str(tmp_path))
    with b._CandidateBacktestSession(strategy, rows, official_benchmark=official) as session:
        result = b.run_candidate_backtest(strategy, candidates, _session=session)
    wf = result.walk_forward
    assert wf.status == "ready"
    comparison = result.backtest_payload["benchmark"]["comparison"]
    if gap:
        assert wf.aggregate_metrics.out_sample_benchmark_return is None
        assert wf.aggregate_metrics.out_sample_excess_return is None
        assert comparison["source"] == "primary"
        assert comparison["available"] is False
        assert comparison["return"] is None
        for summary in result.engine_summaries_by_candidate.values():
            provenance = summary["benchmark_provenance"]
            assert provenance["primary"]["available"] is True
            assert provenance["primary"]["used_for_acceptance"] is False
            assert provenance["auxiliary"]["used_for_acceptance"] is False
            assert provenance["comparison"]["available"] is False
        return
    expected = 1.001 ** len(wf.daily_returns) - 1
    assert wf.aggregate_metrics.out_sample_benchmark_return == pytest.approx(expected, abs=2e-6)
    assert comparison["return"] == pytest.approx(expected, abs=2e-6)
    assert comparison["source"] == "primary"
    assert comparison["session_count"] == len(wf.daily_returns)
    assert result.engine_summary["benchmark_provenance"]["comparison"] == comparison
    for summary in result.engine_summaries_by_candidate.values():
        provenance = summary["benchmark_provenance"]
        assert provenance["comparison"]["source"] == "primary"
        assert provenance["comparison"]["return"] == pytest.approx(expected, abs=2e-6)
        assert provenance["auxiliary"]["used_for_acceptance"] is False


def test_single_engine_partial_benchmark_does_not_report_neutral_or_truncated_returns():
    curve = [SimpleNamespace(date=f"2024-01-0{index + 2}", total_equity=100 * 1.1**index)
             for index in range(4)]
    engine = SimpleNamespace(
        summary={"metrics_mode": "selection", "max_drawdown": -0.1, "win_rate": 0.5},
        equity_curve=curve,
    )
    metrics = b._metrics_from_engine_result(engine, benchmark_returns=[0.01])
    assert metrics.out_sample_benchmark_return is None
    assert metrics.in_sample_benchmark_return is None
    assert metrics.out_sample_excess_return is None
    assert metrics.benchmark_period_count is None
