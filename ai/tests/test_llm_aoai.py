import json

import httpx
import pytest

from ai_graph.llm.aoai import AOAIResponsesClient
from ai_graph.llm.base import LLMJsonRequest, LLMProviderConfigError, LLMResponseParseError
from ai_graph.llm.factory import create_llm_client
from ai_graph.llm.mock import MockLLMClient


def make_request() -> LLMJsonRequest:
    return LLMJsonRequest(
        schema_name="unit-test.v1",
        system_prompt="Return JSON only.",
        user_prompt="Return candidates.",
    )


def make_client(response_payload: dict) -> AOAIResponsesClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["api-key"] == "test-api-key"
        assert body["model"] == "test-model"
        assert body["temperature"] == 0.0
        assert body["input"][0]["role"] == "system"
        assert body["input"][1]["role"] == "user"
        return httpx.Response(200, json=response_payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return AOAIResponsesClient(
        responses_url="https://example.test/openai/responses?api-version=2025-04-01-preview",
        api_key="test-api-key",
        model="test-model",
        retry_backoff_seconds=0.0,
        http_client=http_client,
    )


def test_aoai_client_parses_direct_json_payload() -> None:
    client = make_client({"candidates": ["a", "b", "c"], "fallback_reasons": []})

    result = client.generate_json(make_request())

    assert result == {"candidates": ["a", "b", "c"], "fallback_reasons": []}


def test_aoai_client_parses_output_text_json_payload() -> None:
    client = make_client(
        {"output_text": json.dumps({"candidates": ["a", "b", "c"], "fallback_reasons": []})}
    )

    result = client.generate_json(make_request())

    assert result["candidates"] == ["a", "b", "c"]


def test_aoai_client_rejects_broken_output_text_json() -> None:
    client = make_client({"output_text": "{broken-json"})

    with pytest.raises(LLMResponseParseError):
        client.generate_json(make_request())


def test_llm_factory_defaults_to_mock_without_env() -> None:
    client = create_llm_client({})

    assert isinstance(client, MockLLMClient)


def test_llm_factory_selects_aoai_when_env_is_configured() -> None:
    client = create_llm_client(
        {
            "AI_LLM_PROVIDER": "aoai",
            "AI_AOAI_RESPONSES_URL": (
                "https://example.test/openai/responses?api-version=2025-04-01-preview"
            ),
            "AI_AOAI_API_KEY": "test-api-key",
            "AI_AOAI_MODEL": "test-model",
        }
    )

    assert isinstance(client, AOAIResponsesClient)


def test_llm_factory_uses_role_model_override_with_global_endpoint_and_key() -> None:
    client = create_llm_client(
        {
            "AI_LLM_PROVIDER": "aoai",
            "AI_AOAI_RESPONSES_URL": (
                "https://example.test/openai/responses?api-version=2025-04-01-preview"
            ),
            "AI_AOAI_API_KEY": "test-api-key",
            "AI_AOAI_MODEL": "fallback-model",
            "AI_LLM_RESEARCH_JUDGE_MODEL": "research-judge-model",
        },
        role="RESEARCH_JUDGE",
    )

    assert isinstance(client, AOAIResponsesClient)
    assert client.model == "research-judge-model"


def test_llm_factory_falls_back_to_global_model_without_role_override() -> None:
    client = create_llm_client(
        {
            "AI_LLM_PROVIDER": "aoai",
            "AI_AOAI_RESPONSES_URL": (
                "https://example.test/openai/responses?api-version=2025-04-01-preview"
            ),
            "AI_AOAI_API_KEY": "test-api-key",
            "AI_AOAI_MODEL": "fallback-model",
        },
        role="REPORT_JUDGE",
    )

    assert isinstance(client, AOAIResponsesClient)
    assert client.model == "fallback-model"


def test_llm_factory_requires_all_aoai_env_values() -> None:
    with pytest.raises(LLMProviderConfigError):
        create_llm_client({"AI_LLM_PROVIDER": "aoai"})
