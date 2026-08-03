from ai_graph.graph import build_public_backtest_performance
from ai_graph.nodes.report import build_report_bundle
from ai_graph.nodes.risk_manager import MacroSnapshot, apply_risk_rules
from ai_graph.schemas import BacktestMetrics, CodeCandidate, Condition, SignalDecision, StrategySpec


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


def test_report_builds_web_and_email_projection_from_same_decision() -> None:
    risk = apply_risk_rules(make_signal(), MacroSnapshot())
    report = build_report_bundle(make_strategy(), risk)

    assert report.web_projection.title
    assert report.email_projection.title
    assert report.web_projection.summary != report.email_projection.summary


def test_public_performance_excludes_oversized_engine_arrays() -> None:
    metrics = BacktestMetrics(
        sharpe_ratio=0.28,
        max_drawdown=-0.0776,
        win_rate=0.3364,
        total_return=0.0898,
        in_sample_sharpe=0.3,
        out_sample_sharpe=0.1,
        degradation=0.0,
    )
    candidate = CodeCandidate(
        candidate_id="A2",
        variant="A",
        code="pass",
        validation_ok=True,
        metrics=metrics,
    )
    performance = build_public_backtest_performance(
        {
            "strategy_a": make_strategy().model_dump(),
            "candidates": [candidate.model_dump()],
            "selected_candidate": candidate.model_dump(),
            "equity_curve": [],
            "engine_summary": {
                "effective_trade_count": 110,
                "montecarlo": ["large internal-only payload"],
                "rolling_sharpe": [0.1, 0.2],
            },
        }
    )

    assert performance is not None
    assert performance.engine_summary == {"effective_trade_count": 110}
