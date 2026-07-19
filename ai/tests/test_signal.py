from datetime import datetime

import pytest
from pydantic import ValidationError

from ai_graph.nodes.backtest import summarize_backtest
from ai_graph.nodes.signal import SignalCondition, build_investment_signal, generate_signal, signal_node


def make_strategy():
    return {
        "strategy_id": "rsi_rebound",
        "entry_rules": [
            {"left": "rsi", "operator": "lte", "right": 30, "description": "RSI <= 30"}
        ],
        "exit_rules": [
            {"left": "rsi", "operator": "gte", "right": 70, "description": "RSI >= 70"}
        ],
    }


def make_market(ticker="005930", rsi=28):
    return {
        "ticker": ticker,
        "timestamp": datetime(2026, 5, 19, 9, 5),
        "metrics": {"rsi": rsi},
    }


def test_generate_buy_signal_when_entry_rule_matches():
    result = generate_signal(make_strategy(), make_market())

    assert result.action == "BUY"
    assert result.matching_entry_rules == ["RSI <= 30"]
    assert result.debug_ref.startswith("signal:")
    assert "internal_payload" not in result.model_dump()


def test_generate_sell_signal_for_existing_position():
    result = generate_signal(
        make_strategy(),
        make_market(rsi=75),
        has_position=True,
    )

    assert result.action == "SELL"
    assert result.matching_exit_rules == ["RSI >= 70"]


def test_signal_node_public_contract_excludes_raw_internal_payload():
    output = signal_node(
        {
            "trace_id": "trace-2",
            "strategy_spec": make_strategy(),
            "market_snapshot": make_market(),
            "internal_payload": {"raw": "must stay internal"},
        }
    )

    assert output["trace_id"] == "trace-2"
    assert output["signal"]["debug_ref"] == "signal:trace-2"
    assert "internal_payload" not in output["signal"]


def test_empty_l4_evidence_does_not_fall_back_to_fixture_evidence():
    decision = build_investment_signal(
        {"selected_candidate": {"metrics": {"sharpe_ratio": 1.4, "max_drawdown": -0.03}}},
        trace_id="trace-empty-evidence",
        l4_evidence=[],
    )

    assert decision.l4_evidence == []


def test_backtest_summary_excludes_generated_candidate_payloads():
    summary = summarize_backtest(
        {
            "candidates": [{"code": "generated code" * 100_000}],
            "selected_candidate": {
                "candidate_id": "candidate-a",
                "metrics": {"sharpe_ratio": 1.4},
            },
            "engine_summary": {"trades": 7},
            "objective_scores_by_candidate": {"candidate-a": 0.81},
        }
    )

    assert summary == {
        "selected_candidate_id": "candidate-a",
        "metrics": {"sharpe_ratio": 1.4},
        "engine_summary": {"trades": 7},
        "objective_score": 0.81,
    }
    assert "candidates" not in summary


def test_signal_condition_validates_between_shape():
    with pytest.raises(ValidationError):
        SignalCondition(left="rsi", operator="between", right=[70])
