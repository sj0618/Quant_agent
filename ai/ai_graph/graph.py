from __future__ import annotations

from hashlib import sha256
from collections.abc import Mapping
from typing import Any

from ai_graph.data_sources import load_pipeline_data_from_env
from ai_graph.envelope import InMemoryDebugStore, build_envelope
from ai_graph.nodes.backtest import backtest_node
from ai_graph.nodes.backtest_code import backtest_code_node
from ai_graph.nodes.report import report_node
from ai_graph.nodes.risk_manager import risk_manager_node
from ai_graph.nodes.signal import signal_node
from ai_graph.retrieval.search import search_retrieval_corpus
from ai_graph.schemas import (
    AmbiguityCode,
    ABBacktestResult,
    APIEnvelope,
    BacktestPerformance,
    ClarificationOption,
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
    retrieval = search_retrieval_corpus(query, top_k=3)
    clarification = build_clarification_prompt(category, query)
    ambiguity = {
        "category": category.value,
        "ambiguity_category": category.value,
        "safety_priority": category == AmbiguityCode.INFEASIBLE,
        "reason": _ambiguity_reason(category),
        "ambiguity_reasons": _ambiguity_reasons(category, query),
        "retrieved_definitions": [hit.model_dump() for hit in retrieval.hits],
        "clarification_question": clarification["question"],
        "question_reason": clarification["question_reason"],
        "options": [option.model_dump() for option in clarification["options"]],
        "recommended_option": clarification["recommended"],
        "recommendation_confidence": clarification["confidence"],
        "recommendation_confidence_reason": clarification["confidence_reason"],
    }
    return {"ambiguity": ambiguity, "status": status.value}


def data_node(state: QuantAgentState) -> dict[str, Any]:
    retrieval = search_retrieval_corpus(state["user_query"], top_k=5)
    cards = strategy_candidate_cards(state["user_query"], retrieval.hits)
    pipeline_data = load_pipeline_data_from_env(state["user_query"], state["trace_id"])
    output: dict[str, Any] = {
        "retrieval": retrieval.model_dump(),
        "data": {
            "candidate_cards": [card.model_dump() for card in cards],
            "pipeline_data_source": pipeline_data.metadata,
        },
    }
    if pipeline_data.price_rows:
        output["price_rows"] = pipeline_data.price_rows
    if pipeline_data.metadata.get("source") == "postgres" or pipeline_data.l4_evidence:
        output["l4_evidence"] = pipeline_data.l4_evidence
    if pipeline_data.macro_snapshot:
        output["macro_snapshot"] = pipeline_data.macro_snapshot
    return output


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
            "performance": build_public_backtest_performance(state.get("backtest")),
        }
    elif status == EnvelopeStatus.REJECTED:
        clarification = _clarification_from_ambiguity(state["ambiguity"])
        payload = {
            "headline": "MVP 범위 밖 전략입니다.",
            "message": state["ambiguity"]["reason"],
            "next_actions": ["KRX 현물 주식 전략으로 다시 입력"],
            "candidate_cards": cards,
            **clarification,
        }
    else:
        clarification = _clarification_from_ambiguity(state["ambiguity"])
        payload = {
            "headline": "추가 확인이 필요합니다.",
            "message": state["ambiguity"]["reason"],
            "next_actions": ["후보 카드 중 하나 선택", "시장/기간/조건 보강"],
            "candidate_cards": cards,
            **clarification,
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
    if any(term in lowered for term in ("옵션", "양매도", "선물", "crypto", "가상화폐", "비트코인")):
        return AmbiguityCode.INFEASIBLE
    if _has_conflicting_targets(query):
        return AmbiguityCode.CONFLICTING
    if _is_candidate_selection_query(query):
        return AmbiguityCode.READY
    if _needs_query_smoothing(query):
        return AmbiguityCode.INPUT_AMBIGUOUS
    if _is_supported_technical_query(query):
        return AmbiguityCode.READY
    if _has_known_strategy_term(query):
        return AmbiguityCode.READY
    if _has_unknown_term_risk(query):
        return AmbiguityCode.TERM_UNKNOWN
    return AmbiguityCode.READY


def strategy_candidate_cards(query: str, hits: list[Any]) -> list[StrategyCandidateCard]:
    lowered = query.lower()
    if any(term in lowered or term in query for term in ("per", "pbr", "roe", "저평가", "가치", "부채", "순현금", "배당", "fcf")):
        return [
            StrategyCandidateCard(
                strategy_id="value_quality",
                title="저평가 퀄리티",
                summary="PER/PBR/ROE 같은 재무 조건을 먼저 두고, 기술적 상대강도로 최종 확인합니다.",
                key_conditions=["PER/PBR", "ROE", "부채비율", "상대강도"],
                confidence=0.72,
                reason="재무 데이터가 없는 구간은 L1 정의와 기술적 proxy로 query smooth가 필요합니다.",
            ),
            StrategyCandidateCard(
                strategy_id="dividend_defensive",
                title="배당 방어주",
                summary="배당수익률·재무 안정성을 우선하고 200일선 회복 여부로 진입 타이밍을 봅니다.",
                key_conditions=["배당수익률", "부채비율", "200일선", "저변동성"],
                confidence=0.66,
                reason="배당/부채 조건은 공개 재무 데이터 연결 전까지 별도 확인이 필요합니다.",
            ),
            StrategyCandidateCard(
                strategy_id="reasonable_growth",
                title="합리적 성장주",
                summary="ROE·매출 성장률·PER 업종 비교를 결합한 GARP 후보입니다.",
                key_conditions=["ROE", "매출 성장률", "PER 업종 이하", "50일선"],
                confidence=0.64,
                reason="성장성과 밸류에이션을 함께 요구하는 입력에 가장 가까운 후보입니다.",
            ),
        ]
    if any(term in query for term in ("신고가", "거래량", "모멘텀", "돌파", "상대강도", "주도주", "숏커버링", "갭")):
        return [
            StrategyCandidateCard(
                strategy_id="breakout_volume_momentum",
                title="거래량 돌파 모멘텀",
                summary="신고가 또는 박스권 상단 돌파와 20일 평균 대비 거래량 증가를 결합합니다.",
                key_conditions=["신고가", "거래량 150%", "20일선 위", "상대강도"],
                confidence=0.82,
                reason="OHLCV와 TA 지표로 가장 즉시 검증 가능한 모멘텀 유형입니다.",
            ),
            StrategyCandidateCard(
                strategy_id="relative_strength_leader",
                title="상대강도 주도주",
                summary="1개월·3개월 수익률이 시장보다 강한 종목을 추세 후보로 봅니다.",
                key_conditions=["1개월 RS", "3개월 RS", "50일선", "거래대금"],
                confidence=0.77,
                reason="섹터/시장 대비 강도 조건을 기술 지표로 매핑할 수 있습니다.",
            ),
            StrategyCandidateCard(
                strategy_id="short_covering_proxy",
                title="숏커버링 proxy",
                summary="공매도 잔고 데이터가 없으면 거래량 증가와 양봉 돌파를 proxy로 사용합니다.",
                key_conditions=["거래량 증가", "양봉 돌파", "신고가 근처", "변동성 확대"],
                confidence=0.58,
                reason="공매도 잔고는 C5가 아니라 데이터 보강 전 proxy 후보로 처리합니다.",
            ),
        ]
    if any(term in query for term in ("눌림목", "200일", "20일선", "20일 이동평균", "120일")):
        return [
            StrategyCandidateCard(
                strategy_id="pullback_trend",
                title="상승추세 눌림목",
                summary="200일선 위 상승추세에서 20일선까지 조정받은 뒤 재상승하는 후보입니다.",
                key_conditions=["200일선 위", "20일선 조정", "재돌파", "손절선"],
                confidence=0.82,
                reason="L1 눌림목 정의와 이동평균 기반 L2 조건이 직접 매칭됩니다.",
            ),
            StrategyCandidateCard(
                strategy_id="rsi_rebound",
                title="RSI 과매도 반등",
                summary="RSI(14)가 30 이하로 내려간 뒤 30을 회복하는 단기 반등 후보입니다.",
                key_conditions=["RSI <= 30", "RSI 30 상향", "거래량 확인"],
                confidence=0.78,
                reason="눌림목 뒤 반등 확인을 보조하는 기술 후보입니다.",
            ),
            StrategyCandidateCard(
                strategy_id="bollinger_squeeze_breakout",
                title="볼린저 스퀴즈 돌파",
                summary="밴드 폭 축소 후 상단 돌파, 또는 하단 이탈 후 밴드 재진입을 봅니다.",
                key_conditions=["밴드폭 축소", "상단 돌파", "재진입", "저변동성"],
                confidence=0.72,
                reason="조정 뒤 변동성 회복을 확인하는 대체 후보입니다.",
            ),
        ]
    if any(term in query for term in ("눌림목", "200일", "20일선", "120일", "볼린저", "변동성", "반등")) or "rsi" in lowered:
        return [
            StrategyCandidateCard(
                strategy_id="rsi_rebound",
                title="RSI 과매도 반등",
                summary="RSI(14)가 30 이하로 내려간 뒤 30을 회복하는 단기 반등 후보입니다.",
                key_conditions=["RSI <= 30", "RSI 30 상향", "거래량 확인"],
                confidence=0.86,
                reason="현재 백테스트 엔진이 가장 안정적으로 검증하는 기술 반등 유형입니다.",
            ),
            StrategyCandidateCard(
                strategy_id="pullback_trend",
                title="상승추세 눌림목",
                summary="200일선 위 상승추세에서 20일선까지 조정받은 뒤 재상승하는 후보입니다.",
                key_conditions=["200일선 위", "20일선 조정", "재돌파", "손절선"],
                confidence=0.78,
                reason="L1 눌림목 정의와 이동평균 기반 L2 조건이 매칭됩니다.",
            ),
            StrategyCandidateCard(
                strategy_id="bollinger_squeeze_breakout",
                title="볼린저 스퀴즈 돌파",
                summary="밴드 폭 축소 후 상단 돌파, 또는 하단 이탈 후 밴드 재진입을 봅니다.",
                key_conditions=["밴드폭 축소", "상단 돌파", "재진입", "저변동성"],
                confidence=0.74,
                reason="변동성 축소와 돌파 조건을 명확히 분리할 수 있습니다.",
            ),
        ]
    return [
        StrategyCandidateCard(
            strategy_id="rsi_mean_reversion",
            title="RSI 평균회귀",
            summary="RSI 30 이하 매수, 70 이상 청산.",
            key_conditions=["KOSPI200", "RSI <= 30", "RSI >= 70"],
            confidence=0.86,
            reason="과매도/과매수 기준이 명확한 기본 후보입니다.",
        ),
        StrategyCandidateCard(
            strategy_id="pullback_trend",
            title="눌림목 추세 추종",
            summary="상승 추세 내 단기 조정 후 재진입.",
            key_conditions=["추세 필터", "조정 폭", "재상승 확인"],
            confidence=0.74,
            reason="모호한 추세 추종 입력을 이동평균 조건으로 구체화합니다.",
        ),
        StrategyCandidateCard(
            strategy_id="value_quality",
            title="저평가 퀄리티",
            summary="밸류에이션과 수익성 조건을 함께 확인.",
            key_conditions=["PER/PBR", "ROE", "거래대금"],
            confidence=0.68,
            reason="재무 조건이 포함된 입력에 대한 query smooth 후보입니다.",
        ),
    ]


def build_clarification_prompt(category: AmbiguityCode, query: str) -> dict[str, Any]:
    if category == AmbiguityCode.CONFLICTING:
        options = [
            ClarificationOption(label="저변동성 우선", reason="급등 기대보다 낙폭과 손실 변동성을 낮추는 쪽입니다."),
            ClarificationOption(label="돌파 모멘텀 우선", reason="단기 급등 가능성을 보되 변동성 상승을 허용합니다."),
            ClarificationOption(label="균형형 후보", reason="저변동성 필터 뒤 거래량 돌파만 통과시킵니다."),
        ]
        return _clarification(
            question="둘 중 어떤 목표를 먼저 볼까요?",
            question_reason="낮은 변동성과 단기 급등은 같은 스크리닝 안에서 충돌할 수 있습니다.",
            options=options,
            recommended=2,
            confidence=0.74,
            confidence_reason="MVP에서는 목표를 하나로 고정하는 것보다 균형형 query smooth가 재시도 비용을 줄입니다.",
        )
    if category == AmbiguityCode.INFEASIBLE:
        options = [
            ClarificationOption(label="KRX 현물로 대체", reason="현재 실행 가능한 데이터/백테스트 범위입니다."),
            ClarificationOption(label="기술 신호만 분석", reason="파생상품 노출 대신 현물 proxy 신호를 확인합니다."),
            ClarificationOption(label="지원 범위 확인", reason="지원하지 않는 자산군을 명확히 분리합니다."),
        ]
        return _clarification(
            question="KRX 현물 주식 전략으로 바꿔서 볼까요?",
            question_reason="옵션·선물·가상자산은 현재 데이터 인프라 범위 밖입니다.",
            options=options,
            recommended=0,
            confidence=0.9,
            confidence_reason="현재 API/백테스트는 KRX 현물 주식 중심으로 검증됩니다.",
        )
    if category == AmbiguityCode.TERM_UNKNOWN:
        options = [
            ClarificationOption(label="L1/L2 정의 적용", reason="로컬 지식베이스 정의로 조건을 보정합니다."),
            ClarificationOption(label="기술적 proxy 사용", reason="OHLCV/TA 지표로 먼저 후보를 좁힙니다."),
            ClarificationOption(label="질문으로 확정", reason="용어 정의가 투자 판단에 직접 영향을 줍니다."),
        ]
        return _clarification(
            question="이 용어는 어떤 방식으로 해석할까요?",
            question_reason="용어의 시장 관행 정의와 사용자의 의도가 다를 수 있습니다.",
            options=options,
            recommended=0,
            confidence=0.78,
            confidence_reason="L1/L2 문서에 정의가 있으면 질문 없이 우선 적용하는 정책입니다.",
        )

    cards = strategy_candidate_cards(query, [])
    options = [
        ClarificationOption(
            label=card.title,
            reason=card.reason or card.summary,
        )
        for card in cards[:3]
    ]
    return _clarification(
        question="먼저 어떤 후보 전략으로 구체화할까요?",
        question_reason="입력 조건 일부가 재무·컨센서스·공시 데이터에 걸쳐 있어 실행 가능한 후보로 나눕니다.",
        options=options,
        recommended=0,
        confidence=0.7,
        confidence_reason="첫 후보가 입력의 핵심 조건과 현재 검증 가능한 데이터 범위의 교집합이 가장 큽니다.",
    )


def _clarification(
    *,
    question: str,
    question_reason: str,
    options: list[ClarificationOption],
    recommended: int,
    confidence: float,
    confidence_reason: str,
) -> dict[str, Any]:
    return {
        "question": question,
        "question_reason": question_reason,
        "options": options[:3],
        "recommended": recommended,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
    }


def _clarification_from_ambiguity(ambiguity: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": ambiguity.get("clarification_question"),
        "options": [
            ClarificationOption.model_validate(option)
            for option in ambiguity.get("options", [])
        ],
        "recommended": ambiguity.get("recommended_option"),
    }


def _has_conflicting_targets(query: str) -> bool:
    return any(term in query for term in ("변동성 낮", "저변동성")) and "급등" in query


def _is_candidate_selection_query(query: str) -> bool:
    lowered = query.lower()
    return "후보 확정" in query or "strategy_id=" in lowered or "candidate_id=" in lowered


def _is_supported_technical_query(query: str) -> bool:
    lowered = query.lower()
    technical_terms = (
        "rsi",
        "신고가",
        "거래량",
        "200일",
        "20일선",
        "20일 이동평균",
        "120일",
        "52주",
        "볼린저",
        "상대강도",
        "갭",
        "양봉",
        "변동성",
        "돌파",
        "반등",
        "눌림목",
    )
    return any(term in lowered or term in query for term in technical_terms)


def _has_known_strategy_term(query: str) -> bool:
    known_terms = ("눌림목", "숏커버링", "방어주", "주도주", "스퀴즈", "과매도")
    return any(term in query for term in known_terms)


def _needs_query_smoothing(query: str) -> bool:
    lowered = query.lower()
    smoothing_terms = (
        "per",
        "pbr",
        "roe",
        "eps",
        "fcf",
        "저평가",
        "가치",
        "컨센서스",
        "배당",
        "부채",
        "순현금",
        "자사주",
        "공시",
        "기관",
        "외국인",
        "공매도",
        "어닝",
        "가이던스",
        "매출",
        "영업이익",
        "재고",
        "업종 평균",
        "원달러",
        "환율",
        "원자재",
        "리츠",
        "유틸리티",
    )
    return any(term in lowered or term in query for term in smoothing_terms)


def _has_unknown_term_risk(query: str) -> bool:
    return any(term in query for term in ("알아서", "좋은 종목", "괜찮은 종목"))


def _ambiguity_reasons(category: AmbiguityCode, query: str) -> list[str]:
    if category == AmbiguityCode.READY:
        return ["L1/L2 또는 기술 지표 조건으로 해석 가능한 KRX 현물 전략입니다."]
    if category == AmbiguityCode.INPUT_AMBIGUOUS:
        return ["재무·컨센서스·공시·수급 데이터 조건이 섞여 있어 실행 후보 선택이 필요합니다."]
    if category == AmbiguityCode.TERM_UNKNOWN:
        return ["용어 정의가 전략 조건으로 직접 변환되기 전 확인이 필요합니다."]
    if category == AmbiguityCode.CONFLICTING:
        return ["입력 안에 동시에 최적화하기 어려운 목표가 포함되어 있습니다."]
    return [f"{query[:40]} 입력은 현재 KRX 현물 데이터 범위를 벗어난 자산군을 포함합니다."]


def build_strategy_spec(query: str, *, variant: str, retrieval: dict[str, Any]) -> StrategySpec:
    source_refs = [hit["document_id"] for hit in retrieval.get("hits", [])]
    profile = _strategy_profile(query)
    return StrategySpec(
        strategy_id=f"{profile['strategy_id']}_{variant.lower()}",
        name=str(profile["name"]),
        universe="KOSPI200",
        market="KRX",
        timeframe="daily",
        entry_conditions=profile["entry_conditions"],
        exit_conditions=profile["exit_conditions"],
        indicators=profile["indicators"],
        risk_constraints={"max_position_pct": 0.1, "stop_loss_pct": 0.08},
        assumptions=[
            "fixture KOSPI200 universe",
            "daily adjusted close data",
            *profile["assumptions"],
        ],
        source_refs=source_refs,
        confidence=float(profile["confidence"]),
    )


def _strategy_profile(query: str) -> dict[str, Any]:
    lowered = query.lower()
    if "dividend_defensive" in lowered or "배당 방어주" in query:
        return {
            "strategy_id": "dividend_defensive",
            "name": "KOSPI200 배당 방어주",
            "entry_conditions": [
                Condition(left="dividend_yield", operator="gte", right=0.04, description="배당수익률 4% 이상"),
                Condition(left="debt_ratio", operator="lte", right=100, description="부채비율 100% 이하"),
                Condition(left="dividend_cut_5y", operator="eq", right=0, description="최근 5년 배당 삭감 없음"),
                Condition(left="close_above_sma_200", operator="eq", right=1, description="200일선 위 기술 확인"),
            ],
            "exit_conditions": [
                Condition(left="close_below_sma_200", operator="eq", right=1, description="200일선 이탈")
            ],
            "indicators": ["dividend_yield", "debt_ratio", "dividend_cut_5y", "SMA200"],
            "assumptions": [
                "배당수익률과 부채비율은 L1/L2에서 재무 안정성 필터로 해석",
                "배당 삭감 이력 데이터가 없으면 후보 확정 후 기술 proxy 백테스트로 검증",
            ],
            "confidence": 0.73,
        }
    if "value_quality" in lowered or "저평가 퀄리티" in query:
        return {
            "strategy_id": "value_quality",
            "name": "KOSPI200 저평가 퀄리티",
            "entry_conditions": [
                Condition(left="per_percentile", operator="lte", right=0.4, description="PER 업종/시장 하위권"),
                Condition(left="roe", operator="gte", right=0.15, description="ROE 15% 이상"),
                Condition(left="debt_ratio", operator="lte", right=100, description="부채비율 100% 이하"),
                Condition(left="relative_strength_20d", operator="gte", right=0, description="20일 상대강도 양호"),
            ],
            "exit_conditions": [
                Condition(left="relative_strength_20d", operator="lt", right=0, description="단기 상대강도 약화")
            ],
            "indicators": ["PER", "ROE", "debt_ratio", "relative_strength_20d"],
            "assumptions": ["재무 조건은 후보 필터, OHLCV 기반 상대강도는 검증 proxy로 사용"],
            "confidence": 0.75,
        }
    if "reasonable_growth" in lowered or "합리적 성장주" in query:
        return {
            "strategy_id": "reasonable_growth",
            "name": "KOSPI200 합리적 성장주",
            "entry_conditions": [
                Condition(left="roe", operator="gte", right=0.15, description="ROE 15% 이상"),
                Condition(left="sales_growth", operator="gte", right=0.1, description="매출 성장률 10% 이상"),
                Condition(left="per_vs_industry", operator="lte", right=1, description="PER 업종 평균 이하"),
                Condition(left="close_above_sma_50", operator="eq", right=1, description="50일선 위"),
            ],
            "exit_conditions": [
                Condition(left="close_below_sma_50", operator="eq", right=1, description="50일선 이탈")
            ],
            "indicators": ["ROE", "sales_growth", "PER", "SMA50"],
            "assumptions": ["성장성과 밸류에이션을 결합한 GARP 후보로 확정"],
            "confidence": 0.72,
        }
    if "rsi" in lowered or "과매도" in query or "반등" in query:
        return {
            "strategy_id": "rsi_rebound",
            "name": "KOSPI200 RSI 과매도 반등",
            "entry_conditions": [
                Condition(left="rsi", operator="lte", right=30, description="RSI <= 30 또는 30 상향 회복")
            ],
            "exit_conditions": [
                Condition(left="rsi", operator="gte", right=70, description="RSI >= 70")
            ],
            "indicators": ["RSI"],
            "assumptions": ["RSI 30 회복 조건은 L2에서 과매도 반등 proxy로 해석"],
            "confidence": 0.84,
        }
    if any(term in query for term in ("52주", "120일", "신고가", "거래량", "돌파", "갭")):
        return {
            "strategy_id": "breakout_volume_momentum",
            "name": "KOSPI200 거래량 돌파 모멘텀",
            "entry_conditions": [
                Condition(left="breakout_high", operator="eq", right=1, description="신고가 또는 상단 돌파"),
                Condition(left="volume_ratio_20", operator="gte", right=1.5, description="20일 평균 대비 거래량 150% 이상"),
            ],
            "exit_conditions": [
                Condition(left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈")
            ],
            "indicators": ["rolling_high", "volume_ratio_20", "SMA20"],
            "assumptions": ["신고가 기간은 입력의 52주/120일/20일 표현에 맞춰 L2에서 선택"],
            "confidence": 0.8,
        }
    if any(term in query for term in ("눌림목", "200일", "20일선", "20일 이동평균")):
        return {
            "strategy_id": "pullback_trend",
            "name": "KOSPI200 상승추세 눌림목",
            "entry_conditions": [
                Condition(left="close_above_sma_200", operator="eq", right=1, description="주가가 200일선 위"),
                Condition(left="pullback_to_sma_20", operator="eq", right=1, description="20일선 근처 조정"),
            ],
            "exit_conditions": [
                Condition(left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈")
            ],
            "indicators": ["SMA20", "SMA200"],
            "assumptions": ["눌림목은 L1 정의에 따라 장기 상승추세 안의 단기 조정으로 해석"],
            "confidence": 0.78,
        }
    if "볼린저" in query or "변동성" in query:
        return {
            "strategy_id": "bollinger_squeeze_breakout",
            "name": "KOSPI200 볼린저 스퀴즈 돌파",
            "entry_conditions": [
                Condition(left="bb_width_percentile", operator="lte", right=0.25, description="밴드 폭 축소"),
                Condition(left="bollinger_breakout", operator="eq", right=1, description="상단 돌파 또는 밴드 재진입"),
            ],
            "exit_conditions": [
                Condition(left="close_below_middle_band", operator="eq", right=1, description="중심선 이탈")
            ],
            "indicators": ["Bollinger Bands", "realized_volatility"],
            "assumptions": ["상단 돌파와 하단 재진입은 입력 문맥에 따라 L2에서 분기"],
            "confidence": 0.74,
        }
    if any(term in query for term in ("상대강도", "주도주", "시장보다", "섹터")):
        return {
            "strategy_id": "relative_strength_leader",
            "name": "KOSPI200 상대강도 주도주",
            "entry_conditions": [
                Condition(left="relative_strength_20d", operator="gte", right=0, description="20일 시장 대비 초과수익"),
                Condition(left="relative_strength_60d", operator="gte", right=0, description="60일 시장 대비 초과수익"),
            ],
            "exit_conditions": [
                Condition(left="relative_strength_20d", operator="lt", right=0, description="단기 상대강도 약화")
            ],
            "indicators": ["relative_strength_20d", "relative_strength_60d"],
            "assumptions": ["시장 벤치마크는 KOSPI200 proxy로 해석"],
            "confidence": 0.76,
        }
    return {
        "strategy_id": "rsi_rebound",
        "name": "KOSPI200 RSI 과매도 반등",
        "entry_conditions": [
            Condition(left="rsi", operator="lte", right=30, description="RSI <= 30")
        ],
        "exit_conditions": [
            Condition(left="rsi", operator="gte", right=70, description="RSI >= 70")
        ],
        "indicators": ["RSI"],
        "assumptions": ["명확한 기술 조건이 없으면 RSI 평균회귀 후보를 기본 제안"],
        "confidence": 0.68,
    }


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
        "pipeline_data_source": state.get("data", {}).get("pipeline_data_source", {}),
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


def build_public_backtest_performance(
    backtest: Mapping[str, Any] | None,
) -> BacktestPerformance | None:
    if not backtest:
        return None

    result = ABBacktestResult.model_validate(backtest)
    return BacktestPerformance(
        selected_variant=result.selected_candidate.variant,
        selected_candidate_id=result.selected_candidate.candidate_id,
        metrics_by_variant=result.metrics_by_variant,
        equity_curve_by_variant=result.equity_curve_by_variant,
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
