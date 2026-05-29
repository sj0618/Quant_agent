from __future__ import annotations

from ai_graph.schemas import ReportBundle, ReportProjection, RiskDecision, StrategySpec


def build_report_bundle(strategy: StrategySpec, risk: RiskDecision) -> ReportBundle:
    signal = risk.signal
    risk_text = (
        "Risk Manager changed the signal."
        if risk.adjustments
        else "Risk Manager did not change the signal."
    )
    web = ReportProjection(
        title=f"{strategy.name} 분석 결과",
        summary=f"{signal.action} / confidence {signal.confidence:.2f}. {risk_text}",
        sections=[
            {"id": "strategy", "title": "StrategySpec", "items": strategy.model_dump()},
            {"id": "signal", "title": "Signal Judge", "items": signal.model_dump()},
            {"id": "risk", "title": "Risk Manager", "items": [item.model_dump() for item in risk.adjustments]},
        ],
    )
    email = ReportProjection(
        title=f"[QuantAgent] {strategy.name}: {signal.action}",
        summary=f"{strategy.universe} {strategy.timeframe} 전략 신호는 {signal.action}입니다.",
        sections=[
            {"id": "summary", "title": "요약", "items": {"confidence": signal.confidence}},
            {"id": "risk", "title": "리스크 변경", "items": [item.model_dump() for item in risk.adjustments]},
        ],
    )
    return ReportBundle(
        web_projection=web,
        email_projection=email,
        risk_adjustments=risk.adjustments,
    )


def report_node(state: dict) -> dict:
    strategy = StrategySpec.model_validate(state["strategy_spec"])
    risk = RiskDecision.model_validate(state["risk"])
    report = build_report_bundle(strategy, risk)
    return {"report": report.model_dump()}
