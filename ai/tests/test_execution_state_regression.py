"""Synthetic unit checks only; never a strategy-performance result.

Run: PYTHONPATH=ai:backtest_module python ai/tests/test_execution_state_regression.py
"""
from datetime import date, timedelta
import unittest
import math
import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_graph.nodes import backtest as node
from ai_graph.nodes.backtest_features import PreparedFeatureStore
from ai_graph.schemas import CandidateParameters, CodeCandidate, Condition, ConditionOperator, StrategyIR, StrategySpec


def make_rows(closes, *, ticker="000001"):
    return [dict(date=(date(2026, 1, 1) + timedelta(days=i)).isoformat(), ticker=ticker,
                 open=float(close), high=float(close), low=float(close), close=float(close),
                 volume=1_000_000_000., raw_notional=float(close) * 1_000_000_000.)
            for i, close in enumerate(closes)]


def make_rule(*, rotation=True, stop=.08, trailing=.75, overlap=False, holding_days=None):
    entry = [Condition(left="close", operator=ConditionOperator.GT, right=0)]
    exit_rule = [Condition(left="close", operator=ConditionOperator.GT if overlap else ConditionOperator.LT, right=0 if overlap else 1)]
    strategy = StrategySpec(strategy_id="synthetic-execution-state", name="Synthetic unit rule", market="KRX", timeframe="daily", entry_conditions=entry, exit_conditions=exit_rule,
                            risk_constraints={"max_position_pct": 1., "stop_loss_pct": stop}, confidence=1.)
    ir = StrategyIR(strategy_id=strategy.strategy_id, entry_feature="close", exit_feature="close", proxy_feature="close", entry_conditions=entry, exit_conditions=exit_rule,
                    execution_mode="scheduled_rotation" if rotation else "event_driven", ranking_metric="rank", holding_days=holding_days)
    params = CandidateParameters(profile="compiled_conditions", lookback=3, threshold=0, stop_loss_pct=stop, take_profit_pct=10, max_positions=1, rebalance_interval_days=5, trailing_stop_pct=trailing)
    candidate = CodeCandidate(candidate_id="synthetic-unit", variant="A", code="def build_signals(prices):\n    return []", validation_ok=True, representation="structured", strategy_ir=ir, parameters=params)
    return strategy, candidate


def run_fold(rows, *, engine_rows=None, sessions=None, **kwargs):
    for row in rows:
        row.setdefault("rank", 1.)
    strategy, candidate = make_rule(**kwargs)
    engine_rows = rows if engine_rows is None else engine_rows
    sessions = {row["date"] for row in engine_rows} if sessions is None else sessions
    return node._fold_engine(strategy, candidate, rows, engine_rows, sessions)


def fills(result, side):
    return [event for event in result.order_audit if event.side == side and event.status == "executed"]


class ExecutionStateChecks(unittest.TestCase):
    def test_stop_loss_reentry_refills_an_empty_slot_between_rotations(self):
        rows = make_rows([100, 100, 90, 90, 100, 105, 110, 110, 110, 110, 110, 110])
        result = run_fold(rows)
        self.assertEqual([item.date for item in fills(result, "buy")], ["2026-01-02", "2026-01-05"])
        self.assertEqual(result.trades[0].reason, "daily_close_stop_loss_0.08")

    def test_warmup_holdings_do_not_suppress_the_first_fold_trade(self):
        rows = make_rows([100] * 12)
        result = run_fold(rows, engine_rows=rows[5:], sessions={row["date"] for row in rows[6:]})
        self.assertEqual([item.date for item in fills(result, "buy")], ["2026-01-08"])
        self.assertGreater(result.equity_curve[-1].positions_value, 0.)

    def test_zero_capacity_does_not_create_a_phantom_position(self):
        rows = make_rows([100] * 5)
        rows[0]["raw_notional"] = 0.
        result = run_fold(rows, rotation=False)
        self.assertEqual([item.date for item in fills(result, "buy")], ["2026-01-03"])
        self.assertTrue(any(item.reason == "zero_raw_notional" for item in result.order_audit))

    def test_rotation_frees_the_slot_before_the_highest_score_buy(self):
        rows = []
        for ticker in ("000001", "000002", "000003"):
            for i, row in enumerate(make_rows([100] * 8, ticker=ticker)):
                row["rank"] = (3. if ticker == "000001" else 0.) if i < 5 else {"000001": 0., "000002": 1., "000003": 4.}[ticker]
                rows.append(row)
        rows.sort(key=lambda row: (row["date"], row["ticker"]))
        result = run_fold(rows)
        self.assertEqual([item.ticker for item in fills(result, "buy")], ["000001", "000003"])
        self.assertEqual([item.ticker for item in fills(result, "sell")], ["000001"])

    def test_trailing_peak_begins_with_an_actual_fill(self):
        rows = make_rows([150, 100, 110, 115, 100, 100])
        result = run_fold(rows, rotation=False, stop=.5, trailing=.1)
        self.assertEqual([item.date for item in fills(result, "sell")], ["2026-01-06"])
        self.assertEqual(result.trades[0].reason, "daily_close_trailing_stop_0.1")

    def test_overlapping_rules_enter_when_flat_and_exit_when_held(self):
        rows = make_rows([100] * 4)
        result = run_fold(rows, rotation=False, overlap=True)
        self.assertEqual([item.date for item in fills(result, "buy")], ["2026-01-02", "2026-01-04"])
        self.assertEqual([item.date for item in fills(result, "sell")], ["2026-01-03"])
        self.assertTrue(all(item.action in {"buy", "sell", "hold"} for item in result.signals))

    def test_score_survives_event_driven_scarce_slot_execution(self):
        rows = []
        for ticker, rank in (("000001", 1.), ("000099", 9.)):
            rows.extend({**row, "rank": rank} for row in make_rows([100] * 3, ticker=ticker))
        rows.sort(key=lambda row: (row["date"], row["ticker"]))
        result = run_fold(rows, rotation=False)
        self.assertEqual([item.ticker for item in fills(result, "buy")], ["000099"])

    def test_catalog_candidates_use_their_own_position_limits(self):
        strategy, candidate = make_rule()
        strategy.risk_constraints["max_position_pct"] = .1
        for count in (3, 7):
            own = candidate.model_copy(update={"parameters": candidate.parameters.model_copy(update={"max_positions": count, "blueprint_id": "unit-catalog"})})
            self.assertEqual(node._engine_position_sizing(strategy, candidate=own, available_ticker_count=100).max_positions, count)
            self.assertAlmostEqual(node._engine_risk_controls(strategy, candidate=own).max_single_position_pct, 1 / count)
        self.assertEqual(node._engine_position_sizing(strategy, candidate=own, available_ticker_count=2).max_positions, 2)

    def test_sealed_candidates_cannot_expand_after_a_failed_evaluation(self):
        rows = make_rows([100] * 8)
        for row in rows:
            row["rank"] = 1.
        strategy, candidate = make_rule(rotation=False)
        strategy.risk_constraints["research_snapshot_hash"] = "unit-sealed"
        state = {"strategy_spec": strategy.model_dump(), "price_rows": rows,
                 "backtest_code": {"candidates": [candidate.model_dump()], "code_plan": {}}}
        with TemporaryDirectory() as cache, patch.dict(os.environ, {"AI_BACKTEST_CACHE_DIR": cache, "AI_BACKTEST_WORKERS": "1"}), patch.object(node, "generate_self_improvement_candidates", side_effect=AssertionError("sealed candidates changed")):
            result = node.backtest_node(state)
        self.assertEqual(len(result["backtest"]["candidates"]), 1)
        self.assertEqual(result["backtest"]["execution_stats"]["self_improvement_rounds_limit"], 0)

    def test_explicitly_disabled_stop_loss_reaches_the_engine(self):
        rows = make_rows([100, 100, 70, 70, 70])
        for row in rows:
            row["rank"] = 1.
        strategy, candidate = make_rule(rotation=False, trailing=.75)
        candidate.parameters = candidate.parameters.model_copy(update={"stop_loss_pct": None})
        self.assertIsNone(node._engine_risk_controls(strategy, candidate=candidate).stop_loss_pct)
        result = node._fold_engine(strategy, candidate, rows, rows, {row["date"] for row in rows})
        self.assertFalse(fills(result, "sell"))
        self.assertGreater(result.equity_curve[-1].positions_value, 0.)

    def test_holding_period_counts_sessions_after_the_actual_fill(self):
        rows = make_rows([100] * 7)
        rows[0]["raw_notional"] = 0.
        result = run_fold(rows, rotation=False, holding_days=2)
        self.assertEqual(fills(result, "buy")[0].date, "2026-01-03")
        self.assertEqual(fills(result, "sell")[0].date, "2026-01-05")
        self.assertEqual(result.trades[0].reason, "holding_period_2_sessions")

    def test_rejected_sell_does_not_hide_a_held_closing_peak(self):
        rows = make_rows([100, 100, 130, 115, 115])
        for index, row in enumerate(rows):
            row.update(rank=1., exit_flag=1. if index == 2 else 0.)
        rows[2]["raw_notional"] = 0.
        strategy, candidate = make_rule(rotation=False, stop=.5, trailing=.1)
        candidate.strategy_ir.exit_conditions = [Condition(left="exit_flag", operator=ConditionOperator.GT, right=0)]
        result = node._fold_engine(strategy, candidate, rows, rows, {row["date"] for row in rows})
        self.assertEqual([item.date for item in fills(result, "sell")], ["2026-01-05"])
        self.assertEqual(result.trades[0].reason, "daily_close_trailing_stop_0.1")

    def test_explicit_position_counts_do_not_round_up_from_percentages(self):
        from ai_graph.nodes.position_sizing import requested_max_positions, applied_max_positions
        for count in (3, 7):
            self.assertEqual(requested_max_positions(round(1 / count, 8), explicit_max_positions=count), count)
            self.assertEqual(applied_max_positions(round(1 / count, 8), 100, explicit_max_positions=count), count)
        for invalid in (True, 0, 3.5, float("nan"), 1001):
            with self.assertRaises(ValueError):
                requested_max_positions(.1, explicit_max_positions=invalid)

    def test_future_rows_do_not_change_eligibility_or_scores(self):
        rows = make_rows([100, 110, 105, 120, 115, 100, 110, 105])
        for row in rows:
            row["rank"] = 1.
        _, candidate = make_rule(rotation=False, overlap=True)
        full = PreparedFeatureStore(rows).build_ranked_actions(candidate.strategy_ir, candidate.parameters)
        prefix = PreparedFeatureStore(rows[:4]).build_ranked_actions(candidate.strategy_ir, candidate.parameters)
        self.assertEqual(list(full.actions[:4]), list(prefix.actions))
        self.assertTrue(all(
            a == b or (math.isnan(a) and math.isnan(b))
            for a, b in zip(full.scores[:4], prefix.scores, strict=True)
        ))


    def test_gap_at_entry_does_not_leave_a_stopped_name_marked_as_held(self):
        rows = make_rows([100, 110, 110, 110, 110, 110])
        rows[1]["open"] = rows[1]["high"] = 120.0
        result = run_fold(rows)
        self.assertEqual([item.date for item in fills(result, "buy")], ["2026-01-02", "2026-01-04"])
        self.assertEqual([item.date for item in fills(result, "sell")], ["2026-01-03"])

    def test_fold_scores_reach_the_engine_when_execution_has_one_slot(self):
        strategy, candidate = make_rule()
        candidate = candidate.model_copy(update={
            "parameters": candidate.parameters.model_copy(update={"max_positions": 2}),
        })
        rows = []
        for ticker, score in (("000001", 1.0), ("000002", 10.0)):
            for row in make_rows([100, 100, 100], ticker=ticker):
                row["rank"] = score
                rows.append(row)
        rows.sort(key=lambda row: (row["date"], row["ticker"]))
        # Apply a tighter execution cap than the rule's two eligible names.
        with patch.object(node, "_engine_position_sizing", return_value=node.EnginePositionSizing(max_positions=1)):
            result = node._fold_engine(strategy, candidate, rows, rows, {row["date"] for row in rows})
        self.assertEqual([item.ticker for item in fills(result, "buy")], ["000002"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
