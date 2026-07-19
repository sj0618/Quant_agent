from ai_graph.llm import role_calls
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.role_calls import RoleDebatePayload
from ai_graph.schemas import MarketBrief


class CapturingClient:
    def __init__(self, response: dict | None = None) -> None:
        self.request: LLMJsonRequest | None = None
        self.response = response or {
            "summary": "summary",
            "evidence": [],
            "concerns": [],
            "recommendation": "HOLD",
            "confidence": 0.5,
        }

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.request = request
        return self.response


def test_role_call_keeps_role_task_context_and_prompt_identity(monkeypatch) -> None:
    client = CapturingClient()
    monkeypatch.setattr(role_calls, "create_llm_client", lambda *, role: client)
    context = {"query": "삼성전자", "scores": [1, 2, 3]}

    role_calls.generate_role_debate(
        role="RESEARCH_BULL",
        task="Find supporting evidence.",
        context=context,
        fallback=RoleDebatePayload(role="RESEARCH_BULL", summary="fallback"),
    )

    assert client.request is not None
    assert client.request.task_type == "research_bull"
    assert client.request.prompt_template_name == "role_debate"
    assert client.request.prompt_version == "v2"
    assert client.request.variables_jsonb["role"] == "RESEARCH_BULL"
    assert client.request.variables_jsonb["task"] == "Find supporting evidence."
    assert client.request.variables_jsonb["context"] == context

    schema = client.request.variables_jsonb["expected_json_schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["summary"]["type"] == "string"
    assert schema["properties"]["recommendation"]["type"] == "string"
    assert schema["properties"]["evidence"]["type"] == "array"
    assert schema["properties"]["evidence"]["items"]["type"] == "string"
    assert schema["properties"]["concerns"]["items"]["type"] == "string"
    assert "minLength" not in schema["properties"]["summary"]
    assert "minLength" not in schema["properties"]["recommendation"]
    assert "minimum" not in schema["properties"]["confidence"]
    assert "maximum" not in schema["properties"]["confidence"]
    assert client.request.response_schema == schema
    assert "EXPECTED_JSON_SCHEMA=" in client.request.user_prompt
    assert '"summary": {' in client.request.user_prompt
    assert '"minLength"' not in client.request.user_prompt


def test_market_brief_keeps_full_prompt_variables_and_identity(monkeypatch) -> None:
    client = CapturingClient({"headline": "market summary", "items": []})
    monkeypatch.setattr(role_calls, "create_llm_client", lambda *, role: client)

    role_calls.generate_market_brief(
        strategy_names=["KOSPI200 RSI"],
        report_date="2026-07-13",
        fallback=MarketBrief(headline="fallback"),
    )

    assert client.request is not None
    assert client.request.task_type == "digest_market_brief"
    assert client.request.prompt_template_name == "daily_market_brief"
    assert client.request.prompt_version == "v1"
    assert client.request.enable_web_search is True
    assert client.request.variables_jsonb["report_date"] == "2026-07-13"
    assert client.request.variables_jsonb["strategy_universes"] == ["KOSPI200 RSI"]
    assert "expected_json_schema" in client.request.variables_jsonb
