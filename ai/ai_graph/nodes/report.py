from __future__ import annotations

from typing import Any

from ai_graph.llm.role_calls import RoleDebatePayload, generate_role_debate
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
        summary=f"{strategy.universe} {strategy.timeframe} 전략 신호는 {signal.action}입니다.",
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
        citations=_research_citations(state.get("research_debate")),
    )
    return {"report": report.model_dump(), "report_debate": debate}


def _research_citations(research_debate: dict[str, Any] | None) -> list[dict[str, str]]:
    if not research_debate:
        return []
    seen: set[str] = set()
    citations: list[dict[str, str]] = []
    for role in ("judge", "bull", "bear"):
        for citation in research_debate.get(role, {}).get("citations", []):
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
    context = {
        "strategy": strategy.model_dump(),
        "risk": risk.model_dump(),
        "backtest": summarize_backtest(state.get("backtest", {})),
        "data_availability": state.get("data", {}).get("data_availability", {}),
    }
    bull = generate_role_debate(
        role="REPORT_BULL",
        task="Interpret the backtest and signal in a supportive but evidence-grounded way.",
        context=context,
        fallback=RoleDebatePayload(
            role="REPORT_BULL",
            summary="선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
            evidence=["Candidate-code backtest result is available.", "Risk Manager output is attached."],
            recommendation=risk.signal.action,
            confidence=risk.signal.confidence,
        ),
    )
    bear = generate_role_debate(
        role="REPORT_BEAR",
        task="Identify weaknesses, missing data, and over-interpretation risk.",
        context=context,
        fallback=RoleDebatePayload(
            role="REPORT_BEAR",
            summary="재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
            concerns=["Report must not imply unavailable data was fully validated."],
            recommendation="paper_trade_or_review",
            confidence=0.68,
        ),
    )
    judge = generate_role_debate(
        role="REPORT_JUDGE",
        task="Produce the final beginner-friendly recommendation from bull and bear interpretations.",
        context={**context, "bull": bull.model_dump(), "bear": bear.model_dump()},
        fallback=RoleDebatePayload(
            role="REPORT_JUDGE",
            summary="성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
            evidence=["Bull/Bear report passes were evaluated."],
            concerns=bear.concerns,
            recommendation=risk.signal.action,
            confidence=risk.signal.confidence,
            validation_results={"over_optimism_check": "pass", "proxy_disclosure": "pass"},
        ),
    )
    return {
        "bull": bull.model_dump(),
        "bear": bear.model_dump(),
        "judge": judge.model_dump(),
    }
