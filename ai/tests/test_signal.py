from datetime import datetime

import pytest
from pydantic import ValidationError

from ai_graph.nodes.research import MockResearchLLM, build_research_summary, research_node
from ai_graph.nodes.signal import SignalCondition, generate_signal, signal_node


def make_strategy():
    return {
        "strategy_id": "rsi_rebound",
        "entry_rules": [{"left": "rsi", "operator": "lte", "right": 30, "description": "RSI <= 30"}],
        "exit_rules": [{"left": "rsi", "operator": "gte", "right": 70, "description": "RSI >= 70"}],
        "use_candidate_filter": True,
    }


def make_market(ticker="005930", rsi=28):
    return {"ticker": ticker, "timestamp": datetime(2026, 5, 19, 9, 5), "metrics": {"rsi": rsi}}


def make_candidate():
    return {"snapshot_id": "snap-1", "top_k_stocks": ["005930"], "reason_trace": {"035420": ["not in top-k"]}}


def test_generate_buy_signal_after_candidate_filter():
    result = generate_signal(make_strategy(), make_market(), candidate_snapshot=make_candidate())

    assert result.action == "BUY"
    assert result.matching_entry_rules == ["RSI <= 30"]
    assert result.candidate_snapshot_id == "snap-1"
    assert result.debug_ref.startswith("signal:")
    assert "internal_payload" not in result.model_dump()


def test_generate_filtered_out_for_non_candidate_before_rules():
    result = generate_signal(make_strategy(), make_market(ticker="035420", rsi=10), candidate_snapshot=make_candidate())

    assert result.action == "FILTERED_OUT"
    assert result.reasons == ["not in top-k"]


def test_generate_sell_signal_for_existing_position():
    result = generate_signal(make_strategy(), make_market(rsi=75), candidate_snapshot=make_candidate(), has_position=True)

    assert result.action == "SELL"
    assert result.matching_exit_rules == ["RSI >= 70"]


def test_signal_node_public_contract_excludes_raw_internal_payload():
    output = signal_node(
        {
            "trace_id": "trace-2",
            "strategy_spec": make_strategy(),
            "market_snapshot": make_market(),
            "candidate_snapshot": make_candidate(),
            "internal_payload": {"raw": "must stay internal"},
        }
    )

    assert output["trace_id"] == "trace-2"
    assert output["signal"]["debug_ref"] == "signal:trace-2"
    assert "internal_payload" not in output["signal"]


def test_signal_condition_validates_between_shape():
    with pytest.raises(ValidationError):
        SignalCondition(left="rsi", operator="between", right=[70])


def test_research_summary_uses_mock_llm_and_local_evidence():
    summary = build_research_summary("KRX 삼성전자 RSI 리서치", trace_id="trace-3", llm_client=MockResearchLLM())

    assert summary.trace_id == "trace-3"
    assert summary.debug_ref == "research:trace-3"
    assert summary.evidence
    assert "005930" in summary.candidate_tickers


def test_research_node_preserves_trace_id():
    output = research_node({"trace_id": "trace-4", "user_query": "KRX SK하이닉스 리서치 후보"})

    assert output["trace_id"] == "trace-4"
    assert output["research"]["debug_ref"] == "research:trace-4"
