from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol
from uuid import uuid4

from .schemas import (
    BacktestMetric,
    BacktestPoint,
    BacktestResult,
    CandidateSnapshot,
    CandidateStock,
    Condition,
    ConflictExplanation,
    InfeasibleExplanation,
    InternalPayload,
    L4Evidence,
    MarketSnapshot,
    NodeName,
    PublicRunPayload,
    ReportSection,
    RiskSeverity,
    RiskWarning,
    ScenarioCode,
    ScenarioOption,
    ScenarioPayload,
    SignalAction,
    SignalDecision,
    StrategySpec,
    TermDefinition,
    WorkspacePayload,
)
from .state import QuantAgentState, append_internal_trace


DEFAULT_TICKERS = ("005930", "000660", "035420")
DEFAULT_EFFECTIVE_FROM = datetime(2026, 5, 19, 9, 0, tzinfo=UTC)
READY_MESSAGE = (
    "StrategySpec으로 변환했습니다. CandidateSnapshot → Signal Judge → Risk Manager → Report 순서로 결과를 생성했습니다."
)


class LLMClient(Protocol):
    provider_name: str

    def complete_json(self, *, prompt: str, schema_name: str) -> dict[str, Any]:
        """Return JSON-like content that callers validate with Pydantic."""


class MockLLMClient:
    provider_name = "mock"

    def complete_json(self, *, prompt: str, schema_name: str) -> dict[str, Any]:
        digest = sha256(f"{schema_name}:{prompt}".encode("utf-8")).hexdigest()[:12]
        return {
            "provider": self.provider_name,
            "schema_name": schema_name,
            "mock_digest": digest,
        }


class MarketDataAdapter(Protocol):
    def candidate_stocks(self, strategy: StrategySpec) -> list[CandidateStock]:
        """Return market/candidate data without exposing vendor-specific payloads."""


class FixtureMarketDataAdapter:
    def candidate_stocks(self, strategy: StrategySpec) -> list[CandidateStock]:
        return _candidate_stocks(strategy)


class SequentialCompiledGraph:
    def __init__(self, nodes: list[tuple[str, Any]]):
        self._nodes = nodes

    def invoke(self, initial_state: dict[str, Any]) -> QuantAgentState:
        state: QuantAgentState = dict(initial_state)
        for _name, node in self._nodes:
            state.update(node(state))
        return state


def build_quantagent_graph(
    llm_client: LLMClient | None = None,
    data_adapter: MarketDataAdapter | None = None,
) -> Any:
    nodes = _node_sequence(llm_client or MockLLMClient(), data_adapter or FixtureMarketDataAdapter())

    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError:
        return SequentialCompiledGraph(nodes)

    workflow = StateGraph(QuantAgentState)
    for name, node in nodes:
        workflow.add_node(name, node)

    workflow.add_edge(START, NodeName.SUPERVISOR.value)
    workflow.add_edge(NodeName.SUPERVISOR.value, NodeName.AMBIGUITY.value)
    workflow.add_edge(NodeName.AMBIGUITY.value, NodeName.DATA.value)
    workflow.add_edge(NodeName.DATA.value, NodeName.RESEARCH.value)
    workflow.add_edge(NodeName.RESEARCH.value, NodeName.BACKTEST_CODE.value)
    workflow.add_edge(NodeName.BACKTEST_CODE.value, NodeName.BACKTEST.value)
    workflow.add_edge(NodeName.BACKTEST.value, NodeName.SIGNAL.value)
    workflow.add_edge(NodeName.SIGNAL.value, NodeName.RISK_MANAGER.value)
    workflow.add_edge(NodeName.RISK_MANAGER.value, NodeName.REPORT.value)
    workflow.add_edge(NodeName.REPORT.value, END)
    return workflow.compile()


def run_quantagent(
    user_input: str,
    llm_client: LLMClient | None = None,
    data_adapter: MarketDataAdapter | None = None,
) -> QuantAgentState:
    trace_id = f"trc_{uuid4().hex}"
    debug_ref = f"dbg_{trace_id[-12:]}"
    graph = build_quantagent_graph(llm_client, data_adapter)
    return graph.invoke(
        {
            "user_input": user_input,
            "trace_id": trace_id,
            "debug_ref": debug_ref,
        }
    )


def public_response(state: QuantAgentState) -> PublicRunPayload:
    payload = state["public_payload"]
    return PublicRunPayload.model_validate(payload)


def _node_sequence(llm_client: LLMClient, data_adapter: MarketDataAdapter) -> list[tuple[str, Any]]:
    return [
        (NodeName.SUPERVISOR.value, lambda state: supervisor_node(state, llm_client)),
        (NodeName.AMBIGUITY.value, ambiguity_node),
        (NodeName.DATA.value, lambda state: data_node(state, data_adapter)),
        (NodeName.RESEARCH.value, lambda state: research_node(state, llm_client)),
        (NodeName.BACKTEST_CODE.value, backtest_code_node),
        (NodeName.BACKTEST.value, backtest_node),
        (NodeName.SIGNAL.value, signal_node),
        (NodeName.RISK_MANAGER.value, risk_manager_node),
        (NodeName.REPORT.value, report_node),
    ]


def supervisor_node(state: QuantAgentState, llm_client: LLMClient) -> dict[str, Any]:
    internal_payload = InternalPayload(llm_provider=llm_client.provider_name)
    update = {"internal_payload": internal_payload}
    update["internal_payload"] = append_internal_trace(
        {**state, **update},
        node=NodeName.SUPERVISOR.value,
        status="ok",
        detail="run initialized with swappable LLM client",
    )
    return update


def ambiguity_node(state: QuantAgentState) -> dict[str, Any]:
    normalized = state["user_input"].strip().lower()
    scenario = _scenario_for_input(normalized)
    update: dict[str, Any] = {"scenario": scenario}
    update["internal_payload"] = append_internal_trace(
        {**state, **update},
        node=NodeName.AMBIGUITY.value,
        status="ok",
        detail=f"scenario={scenario.scenario.value}",
    )
    return update


def data_node(state: QuantAgentState, data_adapter: MarketDataAdapter) -> dict[str, Any]:
    strategy = _strategy_for_input(state["user_input"])
    candidates = data_adapter.candidate_stocks(strategy)
    update = {"strategy": strategy, "candidates": candidates}
    update["internal_payload"] = append_internal_trace(
        {**state, **update},
        node=NodeName.DATA.value,
        status="ok",
        detail=f"{len(candidates)} mock KRX candidates loaded",
    )
    return update


def research_node(state: QuantAgentState, llm_client: LLMClient) -> dict[str, Any]:
    llm_payload = llm_client.complete_json(prompt=state["user_input"], schema_name="L4Evidence")
    evidence = [
        L4Evidence(
            source="fixture:broker-consensus",
            title="반도체 업황 개선과 외국인 순매수 강도",
            summary="메모리 가격 반등과 수급 개선을 전략 후보군 근거로 사용합니다.",
            confidence=0.82,
        )
    ]
    internal_payload = append_internal_trace(
        state,
        node=NodeName.RESEARCH.value,
        status="ok",
        detail="fixture L4 evidence validated",
    )
    raw = internal_payload.model_dump()
    raw["evidence"] = [item.model_dump() for item in evidence]
    raw["raw_llm"] = llm_payload
    return {"internal_payload": InternalPayload.model_validate(raw)}


def backtest_code_node(state: QuantAgentState) -> dict[str, Any]:
    internal_payload = append_internal_trace(
        state,
        node=NodeName.BACKTEST_CODE.value,
        status="ok",
        detail="safe fixture code reference selected",
    )
    raw = internal_payload.model_dump()
    raw["backtest_code_ref"] = "fixture://backtest/rsi-volume-rebound.py"
    return {"internal_payload": InternalPayload.model_validate(raw)}


def backtest_node(state: QuantAgentState) -> dict[str, Any]:
    backtest = BacktestResult(
        metrics=[
            BacktestMetric(label="Total Return", value="+18.4%", detail="fixture 12M", tone="positive"),
            BacktestMetric(label="Sharpe", value="1.21", detail="cost-adjusted", tone="positive"),
            BacktestMetric(label="MDD", value="-8.7%", detail="max drawdown", tone="warning"),
            BacktestMetric(label="Win Rate", value="58%", detail="sample trades", tone="neutral"),
        ],
        series=[
            BacktestPoint(date="2026-01", strategy=100.0, benchmark=100.0),
            BacktestPoint(date="2026-02", strategy=104.2, benchmark=101.1),
            BacktestPoint(date="2026-03", strategy=112.5, benchmark=105.6),
            BacktestPoint(date="2026-04", strategy=118.4, benchmark=108.2),
        ],
    )
    update = {"backtest": backtest}
    update["internal_payload"] = append_internal_trace(
        {**state, **update},
        node=NodeName.BACKTEST.value,
        status="ok",
        detail="fixture backtest metrics validated",
    )
    return update


def signal_node(state: QuantAgentState) -> dict[str, Any]:
    strategy = state["strategy"]
    decisions = []
    for candidate in state["candidates"]:
        action = SignalAction.BUY if candidate.ticker in DEFAULT_TICKERS[:2] else SignalAction.WATCH
        decisions.append(
            SignalDecision(
                strategy_id=strategy.strategy_id,
                ticker=candidate.ticker,
                action=action,
                confidence=0.86 if action == SignalAction.BUY else 0.61,
                reasons=[
                    "candidate snapshot included",
                    "RSI rebound and volume confirmation" if action == SignalAction.BUY else "watchlist only",
                ],
            )
        )
    update = {"signal_decisions": decisions}
    update["internal_payload"] = append_internal_trace(
        {**state, **update},
        node=NodeName.SIGNAL.value,
        status="ok",
        detail=f"{len(decisions)} Signal Judge decisions generated",
    )
    return update


def risk_manager_node(state: QuantAgentState) -> dict[str, Any]:
    warnings = [
        RiskWarning(
            id="risk_001",
            ticker="005930",
            severity=RiskSeverity.MEDIUM,
            reason="단기 급등 후 변동성 확대 가능성",
            source="Risk Manager",
            evidence=["MDD fixture -8.7%", "candidate concentration in semiconductors"],
            report_note="BUY action은 유지하되 진입 비중을 분할합니다.",
        )
    ]
    update = {"risk_warnings": warnings}
    update["internal_payload"] = append_internal_trace(
        {**state, **update},
        node=NodeName.RISK_MANAGER.value,
        status="ok",
        detail="risk warnings generated without mutating signal actions",
    )
    return update


def report_node(state: QuantAgentState) -> dict[str, Any]:
    report = [
        ReportSection(
            id="report_001",
            title="전략 요약",
            summary="거래량 증가와 RSI 반등 조건으로 KRX 대형주 후보를 선별했습니다.",
            signalJudgeNote="Signal Judge는 BUY/WATCH와 confidence만 산출했습니다.",
            riskManagerNote="Risk Manager는 경고와 리포트 주석만 추가했습니다.",
        ),
        ReportSection(
            id="report_002",
            title="검증 결과",
            summary="Fixture 백테스트 기준 총수익률 +18.4%, MDD -8.7%입니다.",
        ),
    ]
    workspace = WorkspacePayload(
        activeStrategy=state["strategy"],
        candidates=state["candidates"],
        signalDecisions=state["signal_decisions"],
        riskWarnings=state["risk_warnings"],
        reportPreview=report,
        backtestMetrics=state["backtest"].metrics,
        backtestSeries=state["backtest"].series,
    )
    scenario = state["scenario"]
    if scenario.scenario == ScenarioCode.READY:
        scenario.strategy_id = state["strategy"].strategy_id
    public_payload = PublicRunPayload(
        scenario=scenario,
        workspace=workspace if scenario.scenario == ScenarioCode.READY else None,
    )
    update = {
        "report_preview": report,
        "workspace": workspace,
        "public_payload": public_payload,
    }
    update["internal_payload"] = append_internal_trace(
        {**state, **update},
        node=NodeName.REPORT.value,
        status="ok",
        detail="public payload assembled without internal_payload exposure",
    )
    return update


def _scenario_for_input(normalized: str) -> ScenarioPayload:
    options = [
        ScenarioOption(
            strategy_id="strategy_rsi_volume_rebound",
            title="RSI 거래량 반등",
            description="과매도 이후 거래량 회복을 확인합니다.",
            keyConditions=["RSI <= 35", "거래량 증가"],
        ),
        ScenarioOption(
            strategy_id="strategy_defensive_quality",
            title="방어적 퀄리티",
            description="재무 안정성과 낮은 변동성을 우선합니다.",
            keyConditions=["낮은 변동성", "이익 안정성"],
        ),
    ]
    if not normalized or "저평가주 사줘" in normalized:
        return ScenarioPayload(
            scenario=ScenarioCode.C1_INPUT_AMBIGUOUS,
            assistantMessage="입력이 넓게 해석될 수 있어 의도에 가까운 전략 후보를 골라주세요.",
            options=options,
        )
    if "눌림목" in normalized:
        return ScenarioPayload(
            scenario=ScenarioCode.C2_TERM_UNKNOWN,
            assistantMessage="입력한 용어를 L1/L2 우선 검색으로 매핑했습니다.",
            termDefinition=TermDefinition(
                term="눌림목",
                definition="상승 추세 중 단기 조정 뒤 재상승을 기대하는 구간입니다.",
                confidence=0.79,
                matchedSources=["fixture:l1-glossary", "fixture:l2-strategy-map"],
                requiresConfirmation=True,
                mappedStrategyId="strategy_rsi_volume_rebound",
            ),
        )
    if "변동성 낮" in normalized and "급등" in normalized:
        return ScenarioPayload(
            scenario=ScenarioCode.C4_CONFLICTING,
            assistantMessage="전략 조건 사이에 논리 충돌이 있어 조건 완화가 필요합니다.",
            conflict=ConflictExplanation(
                title="낮은 변동성과 급등 추구 조건 충돌",
                conflictPoints=["급등주는 일반적으로 단기 변동성이 높습니다.", "동시 최적화 대신 대안 전략 선택이 필요합니다."],
                alternatives=options,
            ),
        )
    if any(term in normalized for term in ("옵션", "선물", "레버리지", "주문")):
        return ScenarioPayload(
            scenario=ScenarioCode.C5_INFEASIBLE,
            assistantMessage="요청 범위가 현재 AI MVP 지원 범위를 벗어났습니다.",
            infeasible=InfeasibleExplanation(
                title="지원하지 않는 실행/파생상품 요청",
                reason="현재 MVP는 KRX 현물 주식 전략 분석과 모의 백테스트만 지원합니다.",
                supportedScope="자연어 주식 전략 → 후보군 → 신호 → 리스크 → 리포트",
                examples=["RSI가 낮고 거래량이 늘어난 대형주", "방어적인 고배당주"],
            ),
        )
    return ScenarioPayload(
        scenario=ScenarioCode.READY,
        assistantMessage=READY_MESSAGE,
    )


def _strategy_for_input(user_input: str) -> StrategySpec:
    defensive = "방어" in user_input
    snapshot = CandidateSnapshot(tickers=list(DEFAULT_TICKERS), effective_from=DEFAULT_EFFECTIVE_FROM)
    if defensive:
        return StrategySpec(
            strategy_id="strategy_defensive_quality",
            name="방어적 퀄리티 전략",
            summary="낮은 변동성과 안정적 이익을 가진 KRX 종목을 선별합니다.",
            entry_rules=[
                Condition(id="entry_001", label="변동성 하위권", metric="volatility", operator="<=", value="0.18"),
                Condition(id="entry_002", label="ROE 양호", metric="roe", operator=">=", value="8%"),
            ],
            exit_rules=[Condition(id="exit_001", label="변동성 확대", metric="volatility", operator=">", value="0.25")],
            candidate_snapshot=snapshot,
        )
    return StrategySpec(
        strategy_id="strategy_rsi_volume_rebound",
        name="RSI 거래량 반등 전략",
        summary="RSI 과매도와 거래량 증가가 동시에 나타나는 KRX 대형주 후보를 선별합니다.",
        entry_rules=[
            Condition(id="entry_001", label="RSI 과매도", metric="rsi", operator="<=", value="35"),
            Condition(id="entry_002", label="거래량 증가", metric="volume_ratio", operator=">=", value="1.5x"),
        ],
        exit_rules=[Condition(id="exit_001", label="RSI 과열", metric="rsi", operator=">=", value="70")],
        candidate_snapshot=snapshot,
    )


def _candidate_stocks(strategy: StrategySpec) -> list[CandidateStock]:
    now = DEFAULT_EFFECTIVE_FROM
    rows = [
        ("005930", "삼성전자", "반도체", 78400.0, 1.2, {"rsi": 32.0, "volume_ratio": 1.8, "volatility": 0.16, "roe": 9.4}),
        ("000660", "SK하이닉스", "반도체", 172000.0, 2.1, {"rsi": 34.0, "volume_ratio": 1.6, "volatility": 0.19, "roe": 8.9}),
        ("035420", "NAVER", "인터넷", 188500.0, -0.4, {"rsi": 44.0, "volume_ratio": 1.1, "volatility": 0.21, "roe": 7.2}),
    ]
    return [
        CandidateStock(
            ticker=ticker,
            name=name,
            sector=sector,
            lastPrice=price,
            dayChangeRate=change,
            inCandidateSnapshot=ticker in strategy.candidate_snapshot.tickers,
            marketSnapshot=MarketSnapshot(ticker=ticker, timestamp=now, metrics=metrics),
        )
        for ticker, name, sector, price, change, metrics in rows
    ]
