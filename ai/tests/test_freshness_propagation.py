from __future__ import annotations

from datetime import date

import pytest

from ai_graph.data_sources import PipelineDataBundle
from ai_graph.freshness import (
    build_freshness_evidence,
    classify_source_freshness,
    withhold_recommendations_without_l4_evidence,
)
from ai_graph.graph import _recommendation_gate, _ticker_actions, data_node
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


def _pipeline_metadata(
    status: str = "stale",
    *,
    reason: str = "price source exceeded the configured freshness window",
    freshness_as_of: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": "postgres",
        "freshness_reason": reason,
        "source_manifest": {
            "source": "postgres",
            "as_of": "2026-08-20",
            "freshness": status,
            "lineage_hash": "0" * 64,
            "lineage_refs": ["mart.common_stock_universe_asof"],
        },
    }
    if freshness_as_of is not None:
        metadata["freshness_as_of"] = freshness_as_of
    return metadata


def _ticker_action(ticker: str = "005930") -> dict[str, object]:
    return {
        "ticker": ticker,
        "name": "SAMSUNG",
        "action": "BUY",
        "reason": "entry condition met on the last session",
        "as_of_date": "2026-08-21",
        "close": 70000.0,
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


def test_data_reaching_the_last_closed_session_is_fresh() -> None:
    status, reason = classify_source_freshness(
        data_as_of=date(2026, 8, 21), settled_session=date(2026, 8, 21)
    )

    assert status == "fresh"
    assert "2026-08-21" in reason


def test_data_carrying_todays_bar_is_still_fresh() -> None:
    """An intraday load that already has today's row is ahead of the reference, not behind."""

    status, _ = classify_source_freshness(
        data_as_of=date(2026, 8, 24), settled_session=date(2026, 8, 21)
    )

    assert status == "fresh"


def test_data_behind_the_last_closed_session_is_stale_with_its_lag() -> None:
    status, reason = classify_source_freshness(
        data_as_of=date(2026, 8, 18), settled_session=date(2026, 8, 21)
    )

    assert status == "stale"
    assert "2026-08-18" in reason
    assert "2026-08-21" in reason
    assert "3일" in reason


def test_missing_dates_are_unknown_rather_than_assumed_fresh() -> None:
    assert classify_source_freshness(data_as_of=None, settled_session=date(2026, 8, 21))[0] == "unknown"
    assert classify_source_freshness(data_as_of=date(2026, 8, 21), settled_session=None)[0] == "unknown"


def test_fresh_postgres_load_still_produces_recommendations() -> None:
    """The gate must not be the reason a healthy load returns nothing.

    Every production manifest used to be built with freshness="unknown", which this
    gate treats as no-recommendation, so a fully current Postgres load silently
    returned no ticker actions and a failed recommendation gate.
    """

    evidence = build_freshness_evidence(
        _pipeline_metadata("fresh", reason="가격 데이터가 직전 개장일까지 적재돼 있습니다.")
    )

    assert evidence.status == "fresh"
    assert evidence.no_recommendation is False

    state = {
        "freshness_evidence": evidence.model_dump(),
        "backtest": {"ticker_actions": [_ticker_action()]},
    }
    assert [action.ticker for action in _ticker_actions(state, [])] == ["005930"]
    # No backtest payload to gate against means the gate abstains; what matters is that
    # freshness is not the thing forcing validated=False.
    assert _recommendation_gate({"freshness_evidence": evidence.model_dump()}) is None


def test_stale_load_still_withholds_recommendations() -> None:
    evidence = build_freshness_evidence(_pipeline_metadata("stale"))
    state = {
        "freshness_evidence": evidence.model_dump(),
        "backtest": {"ticker_actions": [_ticker_action()]},
    }

    assert _ticker_actions(state, []) == []


@pytest.mark.parametrize("l4_evidence", [None, []])
def test_missing_l4_evidence_withholds_recommendations_even_when_price_data_is_fresh(
    l4_evidence: list[dict[str, object]] | None,
) -> None:
    evidence = withhold_recommendations_without_l4_evidence(
        build_freshness_evidence(
            _pipeline_metadata("fresh", reason="가격 데이터가 직전 개장일까지 적재돼 있습니다.")
        ),
        l4_evidence=l4_evidence,
    )

    assert evidence.status == "fresh"
    assert evidence.no_recommendation is True
    assert "L4" in evidence.reason
    gate = _recommendation_gate({"freshness_evidence": evidence.model_dump()})
    assert gate is not None
    assert gate.validated is False
    assert gate.reason == evidence.reason
    assert _ticker_actions(
        {
            "freshness_evidence": evidence.model_dump(),
            "backtest": {"ticker_actions": [_ticker_action()]},
        },
        [],
    ) == []

    report = build_report_bundle(
        make_strategy(),
        RiskDecision(
            signal=SignalDecision(
                action="NO_RECOMMENDATION",
                confidence=0.0,
                judge_reason=evidence.reason,
            )
        ),
        data={"pipeline_data_source": _pipeline_metadata("fresh")},
        l4_evidence=l4_evidence,
    )
    assert "NO_RECOMMENDATION" in report.web_projection.summary
    assert "NO_RECOMMENDATION" in report.email_projection.summary


@pytest.mark.parametrize("l4_evidence", [None, []])
def test_data_node_withholds_recommendations_when_fresh_postgres_has_no_l4_evidence(
    monkeypatch,
    l4_evidence: list[dict[str, object]] | None,
) -> None:
    bundle = PipelineDataBundle(
        l4_evidence=[] if l4_evidence is None else l4_evidence,
        data_availability={},
        metadata=_pipeline_metadata("fresh", reason="가격 데이터가 직전 개장일까지 적재돼 있습니다."),
    )
    monkeypatch.setattr("ai_graph.graph.load_pipeline_data_from_env", lambda *_: bundle)

    data = data_node({"user_query": "RSI가 30 이하인 KOSPI200", "trace_id": "l4-absent"})

    assert data["freshness_evidence"]["status"] == "fresh"
    assert data["freshness_evidence"]["no_recommendation"] is True
    assert "L4" in data["freshness_evidence"]["reason"]
    assert "l4_evidence" in data
    assert data["l4_evidence"] == []


def test_evidence_reports_the_date_the_data_actually_reaches() -> None:
    """The manifest as_of is the window that was targeted, not the coverage that landed."""

    evidence = build_freshness_evidence(
        _pipeline_metadata("stale", freshness_as_of="2026-08-18")
    )

    assert evidence.as_of == date(2026, 8, 18)
