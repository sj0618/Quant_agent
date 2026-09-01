from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.role_calls import research_screening_terms
from ai_graph.nodes.report import report_node
from ai_graph.schemas import (
    Condition,
    ConditionOperator,
    RiskDecision,
    SignalDecision,
    StrategySpec,
)


class RecordingWebSearchLLMClient:
    """Fake LLMClient that records enable_web_search and returns fixed citations."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.requests.append(request)
        return {
            "strategy_reading": f"{self.role} summary grounded via web search.",
            "metrics": [],
            "citations": [
                {"title": "Example source", "url": "https://example.com/a"}
            ],
        }


def make_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="rsi_rebound_test",
        name="RSI Rebound Test",
        market="KRX",
        timeframe="daily",
        entry_conditions=[
            Condition(
                left="rsi",
                operator=ConditionOperator.LTE,
                right=30,
                description="RSI <= 30",
            )
        ],
        confidence=0.8,
    )


def test_screening_research_enables_web_search(monkeypatch) -> None:
    created_roles: list[str] = []
    clients: dict[str, RecordingWebSearchLLMClient] = {}

    def fake_create_llm_client(environ=None, *, role=None):
        del environ
        created_roles.append(role)
        client = RecordingWebSearchLLMClient(role)
        clients[role] = client
        return client

    monkeypatch.setattr(
        "ai_graph.llm.role_calls.create_llm_client",
        fake_create_llm_client,
    )
    monkeypatch.setattr(
        "ai_graph.llm.role_calls.is_live_llm_provider",
        lambda: True,
    )

    research = research_screening_terms(query="RSI 30 이하 KOSPI200")

    assert created_roles == ["SCREENING_RESEARCH"]
    assert clients["SCREENING_RESEARCH"].requests[0].enable_web_search is True
    assert research is not None
    assert research["citations"] == [
        {"title": "Example source", "url": "https://example.com/a"}
    ]


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
        "ai_graph.llm.role_calls.create_llm_client",
        lambda *args, **kwargs: CapturingClient(),
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
    sealed_source = {"title": "Sealed source", "url": "https://example.com/sealed"}
    state = {
        "strategy_spec": strategy.model_dump(),
        "risk": risk.model_dump(),
        "data": {
            "pipeline_data_source": {
                "screening_relaxation": {
                    "research": {
                        "citations": [
                            duplicate,
                            {"title": "Bear source", "url": "https://example.com/bear"},
                            duplicate,
                        ]
                    }
                }
            }
        },
        "research_sources": [sealed_source, duplicate],
    }

    output = report_node(state)

    citation_section = next(
        section
        for section in output["report"]["web_projection"]["sections"]
        if section["id"] == "citations"
    )
    urls = {item["url"] for item in citation_section["items"]}
    assert urls == {
        "https://example.com/sealed",
        "https://example.com/dup",
        "https://example.com/bear",
    }
    assert len(citation_section["items"]) == 3
    email_citations = next(
        section
        for section in output["report"]["email_projection"]["sections"]
        if section["id"] == "citations"
    )
    assert {item["url"] for item in email_citations["items"]} == urls
