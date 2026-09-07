"""Local synthetic checks of execution deadlines; these are not strategy results."""
from __future__ import annotations

import multiprocessing
import time

import pytest

from ai_graph.nodes import backtest as backtest_node
from ai_graph.progress import AnalysisDeadlineExceeded, analysis_deadline
from ai_graph.schemas import CandidateParameters, CodeCandidate, Condition, StrategyIR, StrategySpec


def _slow_candidate(_task):
    time.sleep(5)
    raise AssertionError("the worker should have been terminated")


def _case(representation="structured"):
    strategy = StrategySpec(
        strategy_id="deadline-unit", name="Deadline unit check", market="KRX", timeframe="daily",
        entry_conditions=[Condition(left="close", operator="gt", right=0)],
        risk_constraints={"max_position_pct": 1.0, "stop_loss_pct": 0.1}, confidence=1.0,
    )
    candidate = CodeCandidate(
        candidate_id="deadline-unit", variant="A", validation_ok=True,
        code="def build_signals(prices):\n    return []", representation=representation,
        strategy_ir=StrategyIR(
            strategy_id=strategy.strategy_id, entry_feature="close", exit_feature="close",
            proxy_feature="close", entry_conditions=strategy.entry_conditions,
        ),
        parameters=CandidateParameters(
            profile="compiled_conditions", lookback=3, threshold=0,
            max_positions=1, stop_loss_pct=0.1, take_profit_pct=0.2,
        ),
    )
    rows = [
        {"date": f"2024-01-{day:02d}", "ticker": "000001", "open": 100.0,
         "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000000.0}
        for day in range(1, 5)
    ]
    return strategy, candidate, rows


@pytest.mark.parametrize("representation", ("structured", "python_fallback"))
@pytest.mark.parametrize("candidate_count", (1, 3))
def test_request_deadline_terminates_all_candidate_workers(monkeypatch, tmp_path, representation, candidate_count):
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("test substitutes a worker function through fork")
    strategy, candidate, rows = _case(representation)
    candidates = [candidate.model_copy(update={"candidate_id": f"deadline-unit-{index}"}) for index in range(candidate_count)]
    monkeypatch.setenv(backtest_node.BACKTEST_CACHE_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(backtest_node, "_evaluate_candidate_worker", _slow_candidate)
    # This assertion makes a regression fail immediately instead of computing inline.
    monkeypatch.setattr(backtest_node, "_evaluate_candidate_task", lambda *args, **kwargs: pytest.fail("bounded work ran inline"))
    original_children = {child.pid for child in multiprocessing.active_children()}
    with backtest_node._CandidateBacktestSession(strategy, rows) as session:
        started = time.monotonic()
        with analysis_deadline(0.05), pytest.raises(AnalysisDeadlineExceeded):
            session.evaluate(candidates)
        assert time.monotonic() - started < 2.0
        assert session._executor is None
    assert {child.pid for child in multiprocessing.active_children()} <= original_children


def test_expired_walk_forward_does_not_start_another_engine():
    with analysis_deadline(0.001):
        time.sleep(0.01)
        with pytest.raises(AnalysisDeadlineExceeded):
            backtest_node._CandidateBacktestSession.run_fold_engines(None, [])


def _slow_walk_forward(*_args, **_kwargs):
    time.sleep(5)
    raise AssertionError("walk-forward should have been terminated")


def _ignores_termination_walk_forward(*args, **kwargs):
    import signal

    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    return _slow_walk_forward(*args, **kwargs)


@pytest.mark.parametrize("worker", (_slow_walk_forward, _ignores_termination_walk_forward))
def test_request_deadline_terminates_walk_forward(monkeypatch, worker):
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("test substitutes a worker function through fork")
    from types import SimpleNamespace

    strategy, candidate, rows = _case()
    monkeypatch.setattr(backtest_node, "_walk_forward_sample", lambda _rows: SimpleNamespace(status=backtest_node.READY_WALK_FORWARD))
    monkeypatch.setattr(backtest_node, "_fold_engine_worker", worker)
    fold = SimpleNamespace(fold_index=0, warmup_sessions=("2024-01-01",), train_sessions=("2024-01-02",), validation_sessions=("2024-01-03",), evaluation_sessions=("2024-01-04",))
    monkeypatch.setattr(backtest_node, "_walk_forward_split_policy", lambda _rows: SimpleNamespace(folds=[fold]))
    original_children = {child.pid for child in multiprocessing.active_children()}
    started = time.monotonic()
    with analysis_deadline(0.05), pytest.raises(AnalysisDeadlineExceeded):
        backtest_node.run_candidate_backtest(strategy, [candidate], price_rows=rows)
    assert time.monotonic() - started < 2.0
    assert {child.pid for child in multiprocessing.active_children()} <= original_children


def test_worker_error_survives_cleanup_that_outlives_the_deadline(monkeypatch):
    from concurrent.futures import Future
    from types import SimpleNamespace

    completed = Future()
    completed.set_exception(ValueError("worker calculation failed"))
    executor = SimpleNamespace(submit=lambda *args, **kwargs: completed)
    session = object.__new__(backtest_node._CandidateBacktestSession)
    monkeypatch.setattr(session, "_ensure_executor", lambda _workers: executor)
    monkeypatch.setattr(session, "_terminate_executor", lambda: time.sleep(0.03))
    with analysis_deadline(0.01), pytest.raises(ValueError, match="worker calculation failed"):
        session._map_fold_tasks([None], 1)


def test_fold_futures_share_one_remaining_budget(monkeypatch):
    from types import SimpleNamespace

    observed = []
    def result(timeout):
        observed.append(timeout)
        time.sleep(0.03)
        return None

    executor = SimpleNamespace(submit=lambda *args, **kwargs: SimpleNamespace(result=result))
    session = object.__new__(backtest_node._CandidateBacktestSession)
    monkeypatch.setattr(session, "_ensure_executor", lambda _workers: executor)
    with analysis_deadline(0.15):
        assert session._map_fold_tasks([None, None], 1) == [None, None]
    assert 0 < observed[1] < observed[0] - 0.02
    assert observed[0] <= 0.15


def test_walk_forward_display_deadline_propagates_to_direct_caller(monkeypatch):
    from types import SimpleNamespace

    strategy, candidate, rows = _case()
    metrics = backtest_node._walk_forward_aggregate_metrics([0.0])
    fold = SimpleNamespace(
        fold_index=0, warmup_sessions=("2024-01-01",),
        train_sessions=("2024-01-02",), validation_sessions=("2024-01-03",),
        evaluation_sessions=("2024-01-04",),
    )
    policy = SimpleNamespace(
        folds=[fold],
        walk_forward=SimpleNamespace(
            min_valid_folds=1, min_unique_evaluation_months=1,
            min_unique_evaluation_sessions=1,
        ),
    )
    monkeypatch.setattr(backtest_node, "_walk_forward_sample", lambda _rows: SimpleNamespace(status=backtest_node.READY_WALK_FORWARD))
    monkeypatch.setattr(backtest_node, "_walk_forward_split_policy", lambda _rows: policy)

    def run_folds(tasks):
        return [
            backtest_node._FoldEngineOutcome(returns={target: 0.0 for target in task.targets})
            if task.targets else backtest_node._FoldEngineOutcome(metrics=metrics)
            for _key, task in tasks
        ]

    def display_evaluation(_candidates):
        raise AnalysisDeadlineExceeded("display evaluation exceeded the request deadline")

    def aggregate_after_display(_returns):
        pytest.fail("the display deadline was swallowed and result construction continued")

    monkeypatch.setattr(backtest_node, "_walk_forward_aggregate_metrics", aggregate_after_display)
    session = SimpleNamespace(
        price_rows=rows, run_fold_engines=run_folds, evaluate=display_evaluation,
    )
    with pytest.raises(AnalysisDeadlineExceeded, match="display evaluation"):
        backtest_node.run_candidate_backtest(strategy, [candidate], _session=session)
