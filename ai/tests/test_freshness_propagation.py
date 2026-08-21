from __future__ import annotations

from ai_graph.freshness import build_freshness_evidence
from ai_graph.graph import _recommendation_gate, _ticker_actions
from ai_graph.nodes.report import build_report_bundle
from ai_graph.schemas import (
    Condition,
    RiskDecision,
    SignalDecision,
    StrategySpec,
)


def make_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="freshness",
        name="Freshness",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator="lte", right=30)],
        exit_conditions=[Condition(left="rsi", operator="gte", right=70)],
        indicators=["RSI"],
        confidence=0.8,
    )


def _pipeline_metadata(status: str = "stale") -> dict[str, object]:
    return {
        "source": "postgres",
        "freshness_reason": "price source exceeded the configured freshness window",
        "source_manifest": {
            "source": "postgres",
            "as_of": "2026-08-20",
            "freshness": status,
            "lineage_hash": "0" * 64,
            "lineage_refs": ["mart.common_stock_universe_asof"],
        },
    }


def test_stale_evidence_contains_as_of_reason_and_no_recommendation_gate() -> None:
    evidence = build_freshness_evidence(_pipeline_metadata())

    assert evidence.status == "stale"
    assert evidence.as_of.isoformat() == "2026-08-20"
    assert evidence.reason == "price source exceeded the configured freshness window"
    assert evidence.no_recommendation is True

    state = {"freshness_evidence": evidence.model_dump()}
    gate = _recommendation_gate(state)
    assert gate is not None
    assert gate.validated is False
    assert gate.reason == evidence.reason
    assert _ticker_actions(state, []) == []


def test_report_projection_carries_the_same_freshness_evidence() -> None:
    strategy = make_strategy()
    risk = RiskDecision(
        signal=SignalDecision(
            action="HOLD",
            confidence=0.5,
            bull_case=["stale data test"],
            bear_case=["stale data test"],
            judge_reason="stale data test",
        )
    )
    report = build_report_bundle(
        strategy,
        risk,
        data={"pipeline_data_source": _pipeline_metadata()},
    )

    web = next(section for section in report.web_projection.sections if section["id"] == "freshness")
    email = next(section for section in report.email_projection.sections if section["id"] == "freshness")
    assert web["items"] == email["items"]
    assert web["items"]["status"] == "stale"
    assert web["items"]["as_of"] == "2026-08-20"
    assert web["items"]["no_recommendation"] is True
