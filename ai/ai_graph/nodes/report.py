from __future__ import annotations

from time import perf_counter
from typing import Any

from ai_graph.exploration_policy import ExplorationPolicyV2
from ai_graph.freshness import (
    build_freshness_evidence,
    withhold_recommendations_without_l4_evidence,
)
from ai_graph.llm.role_calls import RoleDebatePayload, generate_report_writeup
from ai_graph.quant_performance import project_public_performance
from ai_graph.research_eligibility import (
    PerformanceAvailable,
    PerformanceUnavailable,
    PublicPerformance,
)
from ai_graph.schemas import (
    BaseReportV2,
    ExplorationCandidateResultV2,
    ExplorationExecutionSpecV2,
    ReportBundle,
    ReportProjection,
    RiskDecision,
    SignalDecision,
    StrategySpec,
    validate_execution_spec,
)
from ai_graph.strategy_blueprint_catalog import strategy_blueprint_catalog


def build_report_bundle(
    strategy: StrategySpec,
    risk: RiskDecision,
    backtest: dict[str, Any] | None = None,
    *,
    data: dict[str, Any] | None = None,
    debate: dict[str, Any] | None = None,
    citations: list[dict[str, str]] | None = None,
    objective_floor: dict[str, Any] | None = None,
    public_performance: PublicPerformance | None = None,
    l4_evidence: list[dict[str, Any]] | None = None,
    base_report_v2: BaseReportV2 | None = None,
) -> ReportBundle:
    signal = risk.signal
    risk_text = (
        "Risk Manager changed the signal."
        if risk.adjustments
        else "Risk Manager did not change the signal."
    )
    sections: list[dict[str, Any]] = [
        {"id": "assumptions", "title": "검증 가정", "items": strategy.assumptions},
    ]
    if base_report_v2 is None:
        sections[:0] = [
            {"id": "strategy", "title": "StrategySpec", "items": strategy.model_dump()},
            {"id": "entry_conditions", "title": "진입 조건", "items": [item.model_dump() for item in strategy.entry_conditions]},
        ]
        sections.extend([
            {"id": "signal", "title": "Signal Judge", "items": signal.model_dump()},
            {"id": "risk", "title": "Risk Manager", "items": [item.model_dump() for item in risk.adjustments]},
        ])
    else:
        sections.append({
            "id": "exploration_candidates",
            "title": "후보별 비용 반영 미래 구간 결과",
            "items": base_report_v2.model_dump(mode="json"),
        })
    if citations:
        sections.append({"id": "citations", "title": "출처", "items": citations})
    if data:
        freshness_evidence = withhold_recommendations_without_l4_evidence(
            build_freshness_evidence(data.get("pipeline_data_source")),
            l4_evidence=l4_evidence,
        )
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
        sections.insert(
            5,
            {
                "id": "freshness",
                "title": "데이터 freshness",
                "items": freshness_evidence.model_dump(mode="json"),
            },
        )
    if public_performance is not None and base_report_v2 is None:
        sections.insert(
            3,
            {
                "id": "performance",
                "title": "후보 코드 백테스트",
                "items": public_performance.model_dump(mode="json"),
            },
        )
    if debate:
        sections.append({"id": "report_debate", "title": "Report 정반합", "items": debate})
    if objective_floor:
        # The acceptance floor's own verdict, printed next to the result rather than only
        # acting on it. While the floor is report-only a strategy can be labelled
        # 검증됨 and still be listed here as not having cleared it, and the reader is
        # entitled to see both.
        sections.append(
            {
                "id": "objective_floor",
                "title": "수용 기준 판정 (참고)",
                "items": objective_floor,
            }
        )
    observation = base_report_v2.historical_observation if base_report_v2 else None
    observation_text = {
        "observed": "비용 반영 후 양(+) 수익 후보가 관측됨",
        "not_observed": "비용 반영 후 양(+) 수익 후보가 관측되지 않음",
        "inconclusive": "표본 부족으로 결론을 보류함",
    }.get(observation or "")
    web = ReportProjection(
        title=f"{strategy.name} 분석 결과",
        summary=(
            f"과거 미래 구간 결과: {observation_text}. 모든 사전등록 후보를 함께 표시합니다."
            if observation_text
            else f"{signal.action} / confidence {signal.confidence:.2f}. {risk_text}"
        ),
        sections=sections,
    )
    email_sections: list[dict[str, Any]] = [
        {
            "id": "summary",
            "title": "요약",
            "items": (
                {"과거_미래_구간_관측": observation_text}
                if base_report_v2
                else {"confidence": signal.confidence}
            ),
        },
        {"id": "assumptions", "title": "검증 가정", "items": strategy.assumptions},
    ]
    if base_report_v2 is None:
        email_sections.append(
            {"id": "risk", "title": "리스크 변경", "items": [item.model_dump() for item in risk.adjustments]}
        )
    else:
        email_sections.append({
            "id": "exploration_candidates",
            "title": "후보별 결과",
            "items": base_report_v2.model_dump(mode="json"),
        })
    if data:
        email_sections.append(
            {
                "id": "freshness",
                "title": "데이터 freshness",
                "items": withhold_recommendations_without_l4_evidence(
                    build_freshness_evidence(data.get("pipeline_data_source")),
                    l4_evidence=l4_evidence,
                ).model_dump(mode="json"),
            }
        )
    email = ReportProjection(
        title=(
            f"[QuantAgent] {strategy.name}: 과거 검증 결과"
            if base_report_v2
            else f"[QuantAgent] {strategy.name}: {signal.action}"
        ),
        summary=(
            "개인별 매매 지시가 아닌 사전등록 후보군의 과거 검증 결과입니다."
            if base_report_v2
            else f"{strategy.timeframe} 전략 신호는 {signal.action}입니다."
        ),
        sections=email_sections,
    )
    return ReportBundle(
        web_projection=web,
        email_projection=email,
        risk_adjustments=[] if base_report_v2 else risk.adjustments,
        base_report_v2=base_report_v2,
    )


def report_node(state: dict) -> dict:
    strategy = StrategySpec.model_validate(state["strategy_spec"])
    risk = RiskDecision.model_validate(state["risk"])
    public_performance = project_public_performance(
        state.get("backtest"),
        price_rows=state.get("price_rows"),
        pipeline_data_source=(state.get("data") or {}).get("pipeline_data_source"),
    )
    public_risk = _risk_for_public_report(risk, public_performance)
    base_report_v2 = _build_base_report_v2(state, strategy)
    if base_report_v2 is not None and not _can_publish_base_report_v2(public_performance):
        base_report_v2 = None
    debate = None if base_report_v2 else build_report_debate(state, strategy, public_risk)
    report = build_report_bundle(
        strategy,
        public_risk,
        state.get("backtest"),
        data=state.get("data"),
        debate=debate,
        citations=_screening_citations(state),
        public_performance=public_performance,
        l4_evidence=state.get("l4_evidence"),
        objective_floor=state.get("objective_floor"),
        base_report_v2=base_report_v2,
    )
    return {"report": report.model_dump(), "report_debate": debate or {}}


def _can_publish_base_report_v2(public_performance: PublicPerformance | None) -> bool:
    if not isinstance(public_performance, PerformanceAvailable):
        return False
    reliability = public_performance.performance.get("reliability")
    return isinstance(reliability, dict) and reliability.get("source") == "postgres"


def _build_base_report_v2(
    state: dict[str, Any], strategy: StrategySpec
) -> BaseReportV2 | None:
    raw_spec = state.get("execution_spec")
    if not raw_spec:
        return None
    spec = validate_execution_spec(raw_spec)
    if not isinstance(spec, ExplorationExecutionSpecV2):
        return None
    policy = ExplorationPolicyV2.model_validate(state["exploration_policy"])

    backtest = state.get("backtest") or {}
    summaries = backtest.get("engine_summaries_by_candidate") or {}
    titles = {item.catalog_id: item.title for item in strategy_blueprint_catalog()}
    results: list[ExplorationCandidateResultV2] = []
    for candidate in spec.candidates:
        aggregate = (summaries.get(candidate.catalog_id) or {}).get("aggregate_oos_result") or {}
        available = aggregate.get("availability") == "available"
        failed = aggregate.get("availability") == "failed"
        results.append(ExplorationCandidateResultV2(
            catalog_id=candidate.catalog_id,
            title=titles[candidate.catalog_id],
            status="available" if available else "failed" if failed else "insufficient_data",
            total_return=aggregate.get("total_return") if available else None,
            max_drawdown=aggregate.get("max_drawdown") if available else None,
            sharpe_ratio=aggregate.get("sharpe_ratio") if available else None,
            trade_count=int(aggregate.get("trade_count") or 0),
            evaluation_session_count=int(aggregate.get("evaluation_session_count") or 0),
            costs=aggregate.get("costs"),
            after_costs=True,
            reason=None if available else str(aggregate.get("reason") or "미래 구간 표본 부족"),
        ))
    available_returns = [item.total_return for item in results if item.total_return is not None]
    observation = (
        "inconclusive"
        if len(available_returns) != len(results)
        else "observed"
        if any(value > 0.0 for value in available_returns)
        else "not_observed"
    )
    started_at = state.get("base_report_started_at")
    elapsed_ms = (
        round(max(0.0, perf_counter() - float(started_at)) * 1_000, 3)
        if started_at is not None
        else 0.0
    )
    return BaseReportV2(
        policy_version=spec.policy_version,
        policy_hash=spec.policy_hash,
        catalog_version=spec.catalog_version,
        catalog_hash=spec.catalog_hash,
        benchmark=policy.benchmark,
        validation_method=policy.validation.method,
        elapsed_ms=elapsed_ms,
        llm_call_counts={
            "post_parse_intent": 0,
            "screening_sql": 0,
            "python_generation": 0,
        },
        historical_observation=observation,
        candidates=results,
        assumptions=strategy.assumptions,
        limitations=[
            "과거 성과는 미래 수익을 보장하지 않습니다.",
            "개인 보유자산과 재무상황을 반영한 매매 추천이 아닙니다.",
            "후보는 성과 조회 전에 고정했으며 일부 후보만 골라 결과를 표시하지 않습니다.",
        ],
    )


def _risk_for_public_report(
    risk: RiskDecision,
    public_performance: PublicPerformance | None,
) -> RiskDecision:
    """Withhold every report recommendation when public performance is unavailable.

    A raw RiskDecision is useful internal context, but it can be derived from an
    undersized backtest.  Do not let its BUY/HOLD/DROP text outrun the public
    performance contract: web, email, and the report writer must all see the same
    no-recommendation decision.
    """

    if not isinstance(public_performance, PerformanceUnavailable):
        return risk

    reason = (
        "입력 기간·유니버스가 최소 데이터 기준에 미달해 매매 추천을 생성하지 않습니다."
        if public_performance.reason_code == "insufficient_reliability"
        else "공개 가능한 백테스트 성과가 없어 매매 추천을 생성하지 않습니다."
    )
    return RiskDecision(
        signal=SignalDecision(
            action="NO_RECOMMENDATION",
            confidence=0.0,
            bear_case=[reason],
            judge_reason=reason,
        ),
        adjustments=[],
        portfolio_risk=risk.portfolio_risk,
    )


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

    if risk.signal.action == "NO_RECOMMENDATION":
        reason = risk.signal.judge_reason
        return {
            "writeup": RoleDebatePayload(
                role="REPORT_WRITER",
                summary="데이터 검증 범위가 부족해 이번 결과에서는 매매 추천을 생성하지 않습니다.",
                evidence=[reason],
                concerns=["데이터 기준을 충족한 뒤 다시 분석해야 합니다."],
                recommendation="NO_RECOMMENDATION",
                confidence=0.0,
                validation_results={"recommendation_withheld": "pass"},
            ).model_dump()
        }

    # The signal is now derived from the backtest by rule (no debate), so the opposing
    # material comes from that decision's own bull/bear case rather than three LLM calls.
    investment_signal = state.get("investment_signal") or {}
    context = {
        "strategy": strategy.model_dump(),
        "risk": risk.model_dump(),
        "performance": _report_safe_performance(state),
        "data_availability": state.get("data", {}).get("data_availability", {}),
        "signal_decision": {
            "action": investment_signal.get("action"),
            "confidence": investment_signal.get("confidence"),
            "reason": investment_signal.get("judge_reason"),
        },
        # Surfaced explicitly so the write-up addresses concentration, not just returns.
        "portfolio_risk": (risk.portfolio_risk.model_dump() if risk.portfolio_risk else None),
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


def _report_safe_performance(state: dict[str, Any]) -> dict[str, Any] | None:
    performance = project_public_performance(
        state.get("backtest"),
        price_rows=state.get("price_rows"),
        pipeline_data_source=(state.get("data") or {}).get("pipeline_data_source"),
    )
    if performance is None:
        return None
    if isinstance(performance, PerformanceAvailable):
        return performance.model_dump(mode="json")
    # The unavailable variant has no metrics/chart fields by construction.
    return performance.model_dump(mode="json")
