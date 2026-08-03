from ai_graph.nodes.report import build_report_bundle
from ai_graph.nodes.risk_manager import (
    MacroSnapshot,
    _average_pairwise_correlation,
    apply_risk_rules,
)
from ai_graph.schemas import Condition, SignalDecision, StrategySpec


def make_signal() -> SignalDecision:
    return SignalDecision(
        action="BUY",
        confidence=0.95,
        bull_case=["fixture"],
        bear_case=["fixture"],
        judge_reason="fixture judge",
    )


def make_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="rsi",
        name="RSI",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator="lte", right=30)],
        exit_conditions=[Condition(left="rsi", operator="gte", right=70)],
        indicators=["RSI"],
        confidence=0.8,
    )


def test_risk_manager_overrides_buy_to_hold_on_kospi_drop() -> None:
    decision = apply_risk_rules(
        make_signal(),
        MacroSnapshot(kospi_close_change_pct=-0.051, fx_daily_change_pct=0.0, vkospi=20),
    )

    assert decision.signal.action == "HOLD"
    assert decision.adjustments[0].rule == "KOSPI_CLOSE_DROP_5PCT"


def test_risk_manager_caps_buy_confidence_for_fx_and_vkospi() -> None:
    decision = apply_risk_rules(
        make_signal(),
        MacroSnapshot(kospi_close_change_pct=0.0, fx_daily_change_pct=0.021, vkospi=31),
    )

    assert decision.signal.action == "BUY"
    assert decision.signal.confidence == 0.6
    assert {adjustment.rule for adjustment in decision.adjustments} == {
        "FX_DAILY_MOVE_2PCT_CAP",
        "VKOSPI_30_CAP",
    }


def test_portfolio_correlation_keeps_pairwise_missing_date_semantics() -> None:
    rows = [
        {"ticker": "000001", "date": "2026-01-01", "close": 100},
        {"ticker": "000001", "date": "2026-01-02", "close": 110},
        {"ticker": "000001", "date": "2026-01-03", "close": 99},
        {"ticker": "000001", "date": "2026-01-04", "close": 118.8},
        {"ticker": "000002", "date": "2026-01-01", "close": 100},
        {"ticker": "000002", "date": "2026-01-02", "close": 80},
        {"ticker": "000002", "date": "2026-01-04", "close": 88},
        {"ticker": "000003", "date": "2026-01-01", "close": 100},
        {"ticker": "000003", "date": "2026-01-03", "close": 120},
        {"ticker": "000003", "date": "2026-01-04", "close": 108},
    ]

    correlation = _average_pairwise_correlation({"000001", "000002", "000003"}, rows)

    assert correlation is not None
    assert abs(correlation) < 1e-12


def test_report_builds_web_and_email_projection_from_same_decision() -> None:
    risk = apply_risk_rules(make_signal(), MacroSnapshot())
    report = build_report_bundle(make_strategy(), risk)

    assert report.web_projection.title
    assert report.email_projection.title
    assert report.web_projection.summary != report.email_projection.summary
