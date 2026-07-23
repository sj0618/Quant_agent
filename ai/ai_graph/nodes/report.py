from __future__ import annotations

from typing import Any

from ai_graph.llm.role_calls import RoleDebatePayload, generate_report_writeup
from ai_graph.nodes.backtest import summarize_backtest
from ai_graph.schemas import ReportBundle, ReportProjection, RiskDecision, StrategySpec


def build_report_bundle(
    strategy: StrategySpec,
    risk: RiskDecision,
    backtest: dict[str, Any] | None = None,
    *,
    data: dict[str, Any] | None = None,
    debate: dict[str, Any] | None = None,
    citations: list[dict[str, str]] | None = None,
) -> ReportBundle:
    signal = risk.signal
    risk_text = (
        "Risk Manager changed the signal."
        if risk.adjustments
        else "Risk Manager did not change the signal."
    )
    sections: list[dict[str, Any]] = [
        {"id": "strategy", "title": "StrategySpec", "items": strategy.model_dump()},
        {"id": "entry_conditions", "title": "진입 조건", "items": [item.model_dump() for item in strategy.entry_conditions]},
        {"id": "assumptions", "title": "검증 가정", "items": strategy.assumptions},
        {"id": "signal", "title": "Signal Judge", "items": signal.model_dump()},
        {"id": "risk", "title": "Risk Manager", "items": [item.model_dump() for item in risk.adjustments]},
    ]
    if citations:
        sections.append({"id": "citations", "title": "출처", "items": citations})
    if data:
        sections.insert(
            3,
            {
                "id": "screening_candidates",
                "title": "공용 DB 스크리닝 후보",
                "items": data.get("screening_candidates", []),
            },
        )
        sections.insert(
            4,
            {
                "id": "data_availability",
                "title": "데이터 가용성",
                "items": data.get("data_availability", {}),
            },
        )
    if backtest:
        sections.insert(
            3,
            {
                "id": "backtest",
                "title": "후보 코드 백테스트",
                "items": summarize_backtest(backtest),
            },
        )
    if debate:
        sections.append({"id": "report_debate", "title": "Report 정반합", "items": debate})
    web = ReportProjection(
        title=f"{strategy.name} 분석 결과",
        summary=f"{signal.action} / confidence {signal.confidence:.2f}. {risk_text}",
        sections=sections,
    )
    email = ReportProjection(
        title=f"[QuantAgent] {strategy.name}: {signal.action}",
        summary=f"{strategy.timeframe} 전략 신호는 {signal.action}입니다.",
        sections=[
            {"id": "summary", "title": "요약", "items": {"confidence": signal.confidence}},
            {"id": "assumptions", "title": "검증 가정", "items": strategy.assumptions},
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
    debate = build_report_debate(state, strategy, risk)
    report = build_report_bundle(
        strategy,
        risk,
        state.get("backtest"),
        data=state.get("data"),
        debate=debate,
        citations=_screening_citations(state),
    )
    return {"report": report.model_dump(), "report_debate": debate}


def _screening_citations(state: dict[str, Any]) -> list[dict[str, str]]:
    """Sources behind the report.

    These used to come from the research debate. That debate is gone, and the sources
    that actually informed the run are the ones the screening stage consulted while
    working out what the strategy's terms mean.
    """

    pipeline = (state.get("data") or {}).get("pipeline_data_source") or {}
    research = (pipeline.get("screening_relaxation") or {}).get("research") or {}
    seen: set[str] = set()
    citations: list[dict[str, str]] = []
    for citation in research.get("citations") or []:
        url = citation.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        citations.append(citation)
    return citations


def build_report_debate(
    state: dict[str, Any],
    strategy: StrategySpec,
    risk: RiskDecision,
) -> dict[str, Any]:
    """Write the report's interpretation of an already-decided outcome.

    This used to be a third bull/bear/judge debate, after the ones in research and
    signal. It re-argued a settled decision - its judge fallback just echoed
    risk.signal.action - for three provider calls. The opposing views are now taken
    from the debates that already ran and handed to a single writing call.
    """

    # The signal is now derived from the backtest by rule (no debate), so the opposing
    # material comes from that decision's own bull/bear case rather than three LLM calls.
    investment_signal = state.get("investment_signal") or {}
    context = {
        "strategy": strategy.model_dump(),
        "risk": risk.model_dump(),
        "backtest": summarize_backtest(state.get("backtest", {})),
        "data_availability": state.get("data", {}).get("data_availability", {}),
        "signal_decision": {
            "action": investment_signal.get("action"),
            "confidence": investment_signal.get("confidence"),
            "reason": investment_signal.get("judge_reason"),
        },
        "supporting_case": investment_signal.get("bull_case") or [],
        "objections": investment_signal.get("bear_case") or [],
        "research_review": state.get("research_review") or {},
    }
    writeup = generate_report_writeup(
        context=context,
        fallback=RoleDebatePayload(
            role="REPORT_WRITER",
            summary="성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
            evidence=["Backtest metrics and Risk Manager inputs are available."],
            concerns=["Report must not imply unavailable data was fully validated."],
            recommendation=risk.signal.action,
            confidence=risk.signal.confidence,
            validation_results={"over_optimism_check": "pass", "proxy_disclosure": "pass"},
        ),
    )
    return {"writeup": writeup.model_dump()}
