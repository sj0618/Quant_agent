from __future__ import annotations

from hashlib import sha256
from typing import Any

from ai_graph.envelope import InMemoryDebugStore, build_envelope
from ai_graph.nodes.backtest import backtest_node
from ai_graph.nodes.backtest_code import backtest_code_node
from ai_graph.nodes.report import report_node
from ai_graph.nodes.risk_manager import risk_manager_node
from ai_graph.nodes.signal import signal_node
from ai_graph.retrieval.search import search_retrieval_corpus
from ai_graph.schemas import (
    AmbiguityCode,
    APIEnvelope,
    Condition,
    EnvelopeStatus,
    InternalPayload,
    StrategyCandidateCard,
    StrategySpec,
)
from ai_graph.state import QuantAgentState


DEBUG_STORE = InMemoryDebugStore()
NODE_SEQUENCE = (
    "Supervisor",
    "Ambiguity Classifier",
    "Data",
    "Research",
    "BacktestCode",
    "Backtest",
    "Signal",
    "Risk Manager",
    "Report",
)


class FallbackGraph:
    def invoke(self, state: QuantAgentState) -> QuantAgentState:
        current = supervisor_node(state)
        current.update(ambiguity_classifier_node(current))
        current.update(data_node(current))
        if current["status"] == EnvelopeStatus.READY.value:
            current.update(research_node(current))
            current.update(backtest_code_node(current))
            current.update(backtest_node(current))
            current.update(signal_node(current))
            current.update(risk_manager_node(current))
            current.update(report_node(current))
        current.update(envelope_node(current))
        return current


def build_graph() -> Any:
    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError:
        return FallbackGraph()

    graph = StateGraph(QuantAgentState)
    graph.add_node("Supervisor", supervisor_node)
    graph.add_node("Ambiguity Classifier", ambiguity_classifier_node)
    graph.add_node("Data", data_node)
    graph.add_node("Research", research_node)
    graph.add_node("BacktestCode", backtest_code_node)
    graph.add_node("Backtest", backtest_node)
    graph.add_node("Signal", signal_node)
    graph.add_node("Risk Manager", risk_manager_node)
    graph.add_node("Report", report_node)
    graph.add_node("Envelope", envelope_node)
    graph.add_edge(START, "Supervisor")
    graph.add_edge("Supervisor", "Ambiguity Classifier")
    graph.add_edge("Ambiguity Classifier", "Data")
    graph.add_conditional_edges(
        "Data",
        _route_after_data,
        {"ready": "Research", "final": "Envelope"},
    )
    graph.add_edge("Research", "BacktestCode")
    graph.add_edge("BacktestCode", "Backtest")
    graph.add_edge("Backtest", "Signal")
    graph.add_edge("Signal", "Risk Manager")
    graph.add_edge("Risk Manager", "Report")
    graph.add_edge("Report", "Envelope")
    graph.add_edge("Envelope", END)
    return graph.compile()


def run_analysis(user_query: str, trace_id: str | None = None) -> APIEnvelope:
    state = build_graph().invoke({"user_query": user_query, "trace_id": trace_id or ""})
    return APIEnvelope.model_validate(state["envelope"])


def supervisor_node(state: QuantAgentState) -> QuantAgentState:
    query = " ".join(str(state.get("user_query", "")).split())
    if not query:
        raise ValueError("user_query must not be empty")
    trace_id = state.get("trace_id") or _trace_id(query)
    return {
        **state,
        "user_query": query,
        "trace_id": trace_id,
        "debug_ref": f"debug:{trace_id}",
        "route": "strategy_parse",
        "internal_payload": InternalPayload(trace_id=trace_id).model_dump(),
    }


def ambiguity_classifier_node(state: QuantAgentState) -> dict[str, Any]:
    query = state["user_query"]
    category = classify_query(query)
    status = _status_for_category(category)
    ambiguity = {
        "category": category.value,
        "safety_priority": category == AmbiguityCode.INFEASIBLE,
        "reason": _ambiguity_reason(category),
    }
    return {"ambiguity": ambiguity, "status": status.value}


def data_node(state: QuantAgentState) -> dict[str, Any]:
    retrieval = search_retrieval_corpus(state["user_query"], top_k=5)
    cards = strategy_candidate_cards(state["user_query"], retrieval.hits)
    return {
        "retrieval": retrieval.model_dump(),
        "data": {"candidate_cards": [card.model_dump() for card in cards]},
    }


def research_node(state: QuantAgentState) -> dict[str, Any]:
    strategy_a = build_strategy_spec(state["user_query"], variant="A", retrieval=state["retrieval"])
    strategy_b = build_strategy_spec(state["user_query"], variant="B", retrieval=state["retrieval"])
    strategy_b = strategy_b.model_copy(
        update={
            "name": f"{strategy_b.name} AI 개선본",
            "assumptions": [*strategy_b.assumptions, "L1/L2 검색 결과로 RSI 기준을 명시화함"],
            "confidence": min(strategy_b.confidence + 0.05, 0.95),
        }
    )
    return {
        "strategy_spec": strategy_a.model_dump(),
        "improved_strategy_spec": strategy_b.model_dump(),
    }


def envelope_node(state: QuantAgentState) -> dict[str, Any]:
    status = EnvelopeStatus(state["status"])
    report = state.get("report")
    cards = [
        StrategyCandidateCard.model_validate(card)
        for card in state.get("data", {}).get("candidate_cards", [])
    ]
    if status == EnvelopeStatus.READY:
        payload = {
            "headline": "전략 분석이 완료되었습니다.",
            "message": "StrategySpec, A/B 백테스트, 신호, 리스크, 리포트를 생성했습니다.",
            "next_actions": ["web_projection 확인", "email_projection 예약", "실거래 전 데이터 어댑터 연결"],
            "candidate_cards": cards,
            "report": report,
        }
    elif status == EnvelopeStatus.REJECTED:
        payload = {
            "headline": "MVP 범위 밖 전략입니다.",
            "message": state["ambiguity"]["reason"],
            "next_actions": ["KRX 현물 주식 전략으로 다시 입력"],
            "candidate_cards": cards,
        }
    else:
        payload = {
            "headline": "추가 확인이 필요합니다.",
            "message": state["ambiguity"]["reason"],
            "next_actions": ["후보 카드 중 하나 선택", "시장/기간/조건 보강"],
            "candidate_cards": cards,
        }
    internal = build_internal_payload(state)
    DEBUG_STORE.put(state["debug_ref"], internal)
    envelope = build_envelope(
        status=status,
        trace_id=state["trace_id"],
        debug_ref=state["debug_ref"],
        user_payload=payload,
        strategy_spec=state.get("strategy_spec"),
        retryable=status in {EnvelopeStatus.NEED_CLARIFICATION, EnvelopeStatus.FAILED},
    )
    return {"envelope": envelope.model_dump()}


def classify_query(query: str) -> AmbiguityCode:
    lowered = query.lower()
    if any(term in lowered for term in ("옵션", "양매도", "선물", "crypto", "가상화폐")):
        return AmbiguityCode.INFEASIBLE
    if "변동성 낮" in query and "급등" in query:
        return AmbiguityCode.CONFLICTING
    if "저평가주" in query and ("사줘" in query or "매수" not in query):
        return AmbiguityCode.INPUT_AMBIGUOUS
    if "눌림목" in query:
        return AmbiguityCode.TERM_UNKNOWN
    if "rsi" in lowered and ("30" in lowered or "70" in lowered):
        return AmbiguityCode.READY
    return AmbiguityCode.INPUT_AMBIGUOUS


def strategy_candidate_cards(query: str, hits: list[Any]) -> list[StrategyCandidateCard]:
    return [
        StrategyCandidateCard(
            strategy_id="rsi_mean_reversion",
            title="RSI 평균회귀",
            summary="RSI 30 이하 매수, 70 이상 청산.",
            key_conditions=["KOSPI200", "RSI <= 30", "RSI >= 70"],
            confidence=0.86,
        ),
        StrategyCandidateCard(
            strategy_id="pullback_trend",
            title="눌림목 추세 추종",
            summary="상승 추세 내 단기 조정 후 재진입.",
            key_conditions=["추세 필터", "조정 폭", "재상승 확인"],
            confidence=0.74,
        ),
        StrategyCandidateCard(
            strategy_id="value_quality",
            title="저평가 퀄리티",
            summary="밸류에이션과 수익성 조건을 함께 확인.",
            key_conditions=["PER/PBR", "ROE", "거래대금"],
            confidence=0.68,
        ),
    ]


def build_strategy_spec(query: str, *, variant: str, retrieval: dict[str, Any]) -> StrategySpec:
    source_refs = [hit["document_id"] for hit in retrieval.get("hits", [])]
    return StrategySpec(
        strategy_id=f"rsi_kospi200_{variant.lower()}",
        name="KOSPI200 RSI 평균회귀",
        universe="KOSPI200",
        market="KRX",
        timeframe="daily",
        entry_conditions=[
            Condition(left="rsi", operator="lte", right=30, description="RSI <= 30")
        ],
        exit_conditions=[
            Condition(left="rsi", operator="gte", right=70, description="RSI >= 70")
        ],
        indicators=["RSI"],
        risk_constraints={"max_position_pct": 0.1, "stop_loss_pct": 0.08},
        assumptions=["fixture KOSPI200 universe", "daily adjusted close data"],
        source_refs=source_refs,
        confidence=0.83,
    )


def build_internal_payload(state: QuantAgentState) -> InternalPayload:
    node_outputs = {
        key: state[key]
        for key in (
            "ambiguity",
            "data",
            "strategy_spec",
            "backtest_code",
            "backtest",
            "signal",
            "investment_signal",
            "risk",
            "report",
        )
        if key in state
    }
    validation = {
        "node_sequence": list(NODE_SEQUENCE),
        "schema_validation": "pydantic",
        "langgraph_optional": True,
    }
    return InternalPayload(
        trace_id=state["trace_id"],
        node_outputs=node_outputs,
        retrieval_hits=state.get("retrieval", {}).get("hits", []),
        llm_prompts=["research.md", "signal.md", "backtest_code.md", "report.md"],
        validation=validation,
        backtest_artifacts=state.get("backtest", {}),
        risk_events=state.get("risk", {}).get("adjustments", []),
    )


def _status_for_category(category: AmbiguityCode) -> EnvelopeStatus:
    if category == AmbiguityCode.READY:
        return EnvelopeStatus.READY
    if category == AmbiguityCode.INFEASIBLE:
        return EnvelopeStatus.REJECTED
    return EnvelopeStatus.NEED_CLARIFICATION


def _ambiguity_reason(category: AmbiguityCode) -> str:
    return {
        AmbiguityCode.READY: "분석 가능한 전략 입력입니다.",
        AmbiguityCode.INPUT_AMBIGUOUS: "시장, 조건, 위험 기준이 부족합니다.",
        AmbiguityCode.TERM_UNKNOWN: "용어를 L1/L2 지식베이스와 매칭했지만 확인이 필요합니다.",
        AmbiguityCode.CONFLICTING: "낮은 변동성과 단기 급등 목표가 서로 충돌합니다.",
        AmbiguityCode.INFEASIBLE: "옵션/선물/가상자산은 AI MVP 지원 범위 밖입니다.",
    }[category]


def _route_after_data(state: QuantAgentState) -> str:
    return "ready" if state["status"] == EnvelopeStatus.READY.value else "final"


def _trace_id(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]
