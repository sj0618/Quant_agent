"""The acceptance floor is report-only for now, and switching it back is one variable."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_graph.nodes import backtest as backtest_node
from ai_graph.schemas import BacktestMetrics
from ai_graph.validation_gates import (
    AI_VALIDATION_GATES_ENV,
    DEFAULT_MODE,
    ENFORCED,
    RELEASE_DEFAULT_MODE,
    REPORT_ONLY,
    objective_floor_is_enforced,
    validation_gate_mode,
)


def _failing_result() -> SimpleNamespace:
    """Below every floor: too few trades, negative hold-out Sharpe, drawdown past the cap."""

    metrics = BacktestMetrics(
        sharpe_ratio=-0.4,
        max_drawdown=-0.80,
        win_rate=0.2,
        total_return=-0.3,
        in_sample_sharpe=-0.4,
        out_sample_sharpe=-0.4,
        degradation=0.0,
    )
    return SimpleNamespace(
        selected_candidate=SimpleNamespace(candidate_id="below-floor", metrics=metrics),
        engine_summary={"effective_trade_count": 1},
    )


def test_the_dev_default_is_report_only() -> None:
    assert DEFAULT_MODE == REPORT_ONLY
    assert validation_gate_mode({}) == REPORT_ONLY
    assert objective_floor_is_enforced({}) is False


def test_a_release_profile_enforces_the_floor_by_default() -> None:
    # D-1: production never silently ships the report-only floor. Either release
    # signal defaults to enforced; an explicit AI_VALIDATION_GATES still wins.
    assert RELEASE_DEFAULT_MODE == ENFORCED
    assert validation_gate_mode({"APP_ENV": "production"}) == ENFORCED
    assert validation_gate_mode({"AI_RELEASE_PROFILE": "release"}) == ENFORCED
    assert objective_floor_is_enforced({"APP_ENV": "production"}) is True
    assert (
        validation_gate_mode(
            {"APP_ENV": "production", AI_VALIDATION_GATES_ENV: REPORT_ONLY}
        )
        == REPORT_ONLY
    )


def test_one_variable_puts_the_floor_back_in_the_path() -> None:
    assert objective_floor_is_enforced({AI_VALIDATION_GATES_ENV: ENFORCED}) is True


@pytest.mark.parametrize("value", ("", "  ", "yes", "on", "enforce"))
def test_an_unrecognised_mode_does_not_silently_enforce(value: str) -> None:
    """A typo must not flip a product decision; it falls back to the documented default."""

    assert validation_gate_mode({AI_VALIDATION_GATES_ENV: value}) == REPORT_ONLY


def test_report_only_publishes_a_failing_strategy_as_validated() -> None:
    assert backtest_node._passes_objective_floor(_failing_result()) is True


def test_enforced_withholds_the_same_strategy(enforced_objective_floor: None) -> None:
    assert backtest_node._passes_objective_floor(_failing_result()) is False


def test_the_reasons_are_computed_either_way() -> None:
    """The check is never skipped, only stopped from blocking.

    A gate deleted while 'temporarily off' has to be rewritten from memory later, and by
    then nobody can say whether the thresholds still mean what they meant.
    """

    reasons = backtest_node.objective_floor_reasons(_failing_result())

    assert reasons
    assert any("거래 수" in reason for reason in reasons)
    assert any("Sharpe" in reason for reason in reasons)
    assert any("낙폭" in reason for reason in reasons)


def test_a_clearing_strategy_has_no_reasons() -> None:
    metrics = BacktestMetrics(
        sharpe_ratio=0.9,
        max_drawdown=-0.10,
        win_rate=0.6,
        total_return=0.2,
        in_sample_sharpe=0.9,
        out_sample_sharpe=0.8,
        degradation=0.1,
    )
    result = SimpleNamespace(
        selected_candidate=SimpleNamespace(candidate_id="clears", metrics=metrics),
        engine_summary={"effective_trade_count": 30},
    )

    assert backtest_node.objective_floor_reasons(result) == []
    assert backtest_node._passes_objective_floor(result) is True


def test_the_report_prints_the_floor_verdict_beside_the_result() -> None:
    """#12: the 검증됨 label stays, and the floor's own verdict is shown next to it."""

    from ai_graph.nodes.report import build_report_bundle
    from ai_graph.schemas import Condition, RiskDecision, SignalDecision, StrategySpec

    strategy = StrategySpec(
        strategy_id="floor-report",
        name="Floor Report",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator="lte", right=30)],
        confidence=0.8,
    )
    risk = RiskDecision(
        signal=SignalDecision(
            action="HOLD",
            confidence=0.5,
            bull_case=["floor"],
            bear_case=["floor"],
            judge_reason="floor",
        )
    )
    floor = {"mode": REPORT_ONLY, "cleared": False, "reasons": ["거래 수 1건이 최소 5건에 미달합니다"]}

    bundle = build_report_bundle(strategy, risk, objective_floor=floor)

    section = next(
        item for item in bundle.web_projection.sections if item["id"] == "objective_floor"
    )
    assert section["items"] == floor
