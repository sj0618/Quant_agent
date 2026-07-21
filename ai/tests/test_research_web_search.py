from ai_graph.graph import build_research_debate
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.nodes.report import report_node
from ai_graph.schemas import Condition, ConditionOperator, RiskDecision, SignalDecision, StrategySpec


class RecordingWebSearchLLMClient:
    """Fake LLMClient that records enable_web_search and returns fixed citations."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.requests.append(request)
        return {
            "summary": f"{self.role} summary grounded via web search.",
            "evidence": ["web search finding"],
            "concerns": [],
            "recommendation": "proceed",
            "confidence": 0.8,
            "citations": (
                [{"title": "Example source", "url": "https://example.com/a"}]
                if request.enable_web_search
                else []
            ),
        }


def make_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="rsi_rebound_test",
        name="RSI Rebound Test",
        market="KRX",
        timeframe="daily",
        entry_conditions=[
            Condition(left="rsi", operator=ConditionOperator.LTE, right=30, description="RSI <= 30")
        ],
        confidence=0.8,
    )


def test_build_research_debate_enables_web_search_for_all_three_roles(monkeypatch) -> None:
    created_roles: list[str] = []
    clients: dict[str, RecordingWebSearchLLMClient] = {}

    def fake_create_llm_client(environ=None, *, role=None):
        created_roles.append(role)
        client = RecordingWebSearchLLMClient(role)
        clients[role] = client
        return client

    monkeypatch.setattr("ai_graph.llm.role_calls.create_llm_client", fake_create_llm_client)

    strategy = make_strategy()
    debate = build_research_debate(
        {"user_query": "RSI 30 이하 KOSPI200", "data": {}}, strategy
    )

    assert created_roles == ["RESEARCH_BULL", "RESEARCH_BEAR", "RESEARCH_JUDGE"]
    for role in ("RESEARCH_BULL", "RESEARCH_BEAR", "RESEARCH_JUDGE"):
        assert clients[role].requests[0].enable_web_search is True

    assert debate["bull"]["citations"] == [{"title": "Example source", "url": "https://example.com/a"}]
    assert debate["judge"]["citations"] == [{"title": "Example source", "url": "https://example.com/a"}]


def test_non_research_role_debate_does_not_enable_web_search(monkeypatch) -> None:
    from ai_graph.llm.role_calls import generate_daily_digest_overall_comment
    from ai_graph.schemas import DailyDigestComparisonRow

    captured: list[LLMJsonRequest] = []

    class CapturingClient:
        def generate_json(self, request: LLMJsonRequest) -> dict:
            captured.append(request)
            return {
                "summary": "digest summary",
                "recommendation": "HOLD",
                "confidence": 0.5,
            }

    monkeypatch.setattr(
        "ai_graph.llm.role_calls.create_llm_client", lambda *a, **k: CapturingClient()
    )

    generate_daily_digest_overall_comment(
        [],
        [
            DailyDigestComparisonRow(
                strategy_id="s1",
                name="전략1",
                today_signal="HOLD",
                total_return=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                status="유지",
            )
        ],
    )

    assert captured[0].enable_web_search is False


def test_report_node_surfaces_deduplicated_research_citations(monkeypatch) -> None:
    # The report stage now writes its interpretation in one call instead of running a
    # third bull/bear/judge debate; this test only needs that call stubbed out.
    monkeypatch.setattr(
        "ai_graph.nodes.report.generate_report_writeup",
        lambda **kwargs: kwargs["fallback"],
    )

    strategy = make_strategy()
    risk = RiskDecision(
        signal=SignalDecision(action="BUY", confidence=0.7, judge_reason="test"),
        adjustments=[],
    )
    duplicate = {"title": "Same source", "url": "https://example.com/dup"}
    state = {
        "strategy_spec": strategy.model_dump(),
        "risk": risk.model_dump(),
        "research_debate": {
            "bull": {"citations": [duplicate]},
            "bear": {"citations": [{"title": "Bear source", "url": "https://example.com/bear"}]},
            "judge": {"citations": [duplicate]},
        },
    }

    output = report_node(state)

    citation_section = next(
        section
        for section in output["report"]["web_projection"]["sections"]
        if section["id"] == "citations"
    )
    urls = {item["url"] for item in citation_section["items"]}
    assert urls == {"https://example.com/dup", "https://example.com/bear"}
    assert len(citation_section["items"]) == 2
