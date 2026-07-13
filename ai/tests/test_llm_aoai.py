import json
from hashlib import sha256
from uuid import uuid4

import httpx
import pytest

from ai_graph.audit import RecordingAuditSink, bind_audit_context, create_audit_correlation
from ai_graph.llm.aoai import AOAIResponsesClient
from ai_graph.llm.base import (
    LLMClientError,
    LLMJsonRequest,
    LLMProviderConfigError,
    LLMResponseParseError,
)
from ai_graph.llm.factory import create_llm_client
from ai_graph.llm.mock import MockLLMClient


def make_request() -> LLMJsonRequest:
    return LLMJsonRequest(
        schema_name="unit-test.v1",
        system_prompt="Return JSON only.",
        user_prompt="Return candidates.",
        task_type="unit_test",
        prompt_template_name="unit_test_prompt",
        prompt_version="v1",
        variables_jsonb={"language": "ko", "limit": 3},
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


def make_session():
    sink = RecordingAuditSink()
    session = sink.open_session(
        create_audit_correlation(
            db_trace_id=uuid4(),
            trace_id="trace-llm-unit",
            debug_ref="debug-llm-unit",
            entrypoint="test",
            feature="llm",
        )
    )
    return session


def assert_exact_text(actual: str | None, expected: str) -> None:
    assert actual == expected
    assert len(actual.encode("utf-8")) == len(expected.encode("utf-8"))
    assert sha256(actual.encode("utf-8")).digest() == sha256(expected.encode("utf-8")).digest()


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


def test_aoai_audit_preserves_output_text_and_provider_metadata() -> None:
    raw_output = '{"message":"안녕하세요","value":3}'
    client = make_client(
        {
            "id": "resp_123",
            "model": "deployed-model",
            "output_text": raw_output,
            "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
        }
    )
    session = make_session()
    request = make_request().model_copy(update={"enable_web_search": True})

    with bind_audit_context(session):
        assert client.generate_json(request) == {"message": "안녕하세요", "value": 3}

    assert len(session.model_calls) == len(session.prompt_logs) == 1
    model = session.model_calls[0]
    prompt = session.prompt_logs[0]
    assert model.call_id == prompt.call_id
    assert model.status == "succeeded"
    assert model.provider == "aoai"
    assert model.provider_request_id == "resp_123"
    assert model.model_name == "deployed-model"
    assert (model.prompt_tokens, model.completion_tokens, model.total_tokens) == (11, 7, 18)
    assert model.retry_count == 0
    assert model.latency_ms is not None
    assert model.task_type == "unit_test"
    assert model.response_schema_name == "unit-test.v1"
    assert model.web_search_used is True
    assert prompt.system_prompt == "Return JSON only."
    assert prompt.user_prompt == "Return candidates."
    assert prompt.variables_jsonb == {"language": "ko", "limit": 3}
    assert prompt.prompt_template_name == "unit_test_prompt"
    assert prompt.prompt_version == "v1"
    assert_exact_text(prompt.assistant_response, raw_output)


def test_aoai_audit_joins_nested_text_parts_with_one_newline() -> None:
    parts = ['{"message":"first",', '"value":2}']
    client = make_client(
        {
            "output": [
                {"content": [{"type": "output_text", "text": parts[0]}]},
                {"content": [{"type": "output_text", "text": parts[1]}]},
            ]
        }
    )
    session = make_session()

    with bind_audit_context(session):
        assert client.generate_json(make_request()) == {"message": "first", "value": 2}

    assert_exact_text(session.prompt_logs[0].assistant_response, "\n".join(parts))


def test_aoai_audit_ignores_reasoning_items_and_keeps_visible_output_only() -> None:
    hidden = "hidden-chain-of-thought-must-not-persist"
    visible = '{"ok":true}'
    client = make_client(
        {
            "output": [
                {
                    "type": "reasoning",
                    "content": [{"type": "reasoning_text", "text": hidden}],
                },
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": visible}],
                },
            ]
        }
    )
    session = make_session()

    with bind_audit_context(session):
        assert client.generate_json(make_request()) == {"ok": True}

    assert_exact_text(session.prompt_logs[0].assistant_response, visible)
    assert hidden not in repr((session.model_calls, session.prompt_logs, session.buffered_events))


@pytest.mark.parametrize("typed_item", [True, False])
def test_aoai_audit_never_persists_reasoning_only_output(typed_item: bool) -> None:
    hidden = "reasoning-only-secret-chain-of-thought"
    reasoning_item = {
        "content": [{"type": "reasoning_text", "text": hidden}],
    }
    if typed_item:
        reasoning_item["type"] = "reasoning"
    client = make_client(
        {
            "output": [reasoning_item]
        }
    )
    session = make_session()

    with bind_audit_context(session), pytest.raises(
        LLMResponseParseError, match="did not contain a JSON object"
    ):
        client.generate_json(make_request())

    assert session.prompt_logs[0].assistant_response == ""
    assert hidden not in repr((session.model_calls, session.prompt_logs, session.buffered_events))


def test_aoai_audit_preserves_direct_json_http_body_exactly() -> None:
    raw_response = '{ "message": "direct", "value": 1 }'

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=raw_response)

    client = AOAIResponsesClient(
        responses_url="https://example.test/responses",
        api_key="secret-key",
        model="test-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    session = make_session()

    with bind_audit_context(session):
        assert client.generate_json(make_request()) == {"message": "direct", "value": 1}

    assert_exact_text(session.prompt_logs[0].assistant_response, raw_response)


@pytest.mark.parametrize(
    ("raw_response", "expected_assistant"),
    [
        ("not-json-at-all", "not-json-at-all"),
        ('{"output_text":"{broken-json"}', "{broken-json"),
        ('{"output_text":""}', ""),
    ],
)
def test_aoai_audit_preserves_malformed_2xx_before_raising(
    raw_response: str, expected_assistant: str
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=raw_response)

    client = AOAIResponsesClient(
        responses_url="https://example.test/responses",
        api_key="secret-key",
        model="test-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    session = make_session()

    with bind_audit_context(session), pytest.raises(LLMResponseParseError):
        client.generate_json(make_request())

    assert session.model_calls[0].status == "failed"
    assert session.model_calls[0].error_message == "Model response could not be parsed as the required JSON object."
    assert session.buffered_events[0].call_id == session.model_calls[0].call_id
    assert_exact_text(session.prompt_logs[0].assistant_response, expected_assistant)


def test_aoai_audit_non_2xx_has_null_response_and_keeps_original_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="provider unavailable")

    client = AOAIResponsesClient(
        responses_url="https://example.test/responses?credential=must-not-persist",
        api_key="secret-key-must-not-persist",
        model="test-model",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    session = make_session()

    with bind_audit_context(session), pytest.raises(LLMClientError, match="request failed"):
        client.generate_json(make_request())

    assert session.model_calls[0].status == "failed"
    assert session.model_calls[0].error_message == "Model provider returned HTTP 503 after retry attempts."
    assert session.prompt_logs[0].assistant_response is None
    persisted = repr((session.model_calls, session.prompt_logs, session.buffered_events))
    assert "secret-key-must-not-persist" not in persisted
    assert "credential=must-not-persist" not in persisted
    assert "provider unavailable" not in persisted


def test_aoai_audit_transport_failure_has_null_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = AOAIResponsesClient(
        responses_url="https://example.test/responses",
        api_key="secret-key",
        model="test-model",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    session = make_session()
    execution_id = session.start_agent_execution("Research", step_name="Research")

    with bind_audit_context(session, execution_id), pytest.raises(
        LLMClientError, match="request failed"
    ):
        client.generate_json(make_request())
    session.finish_agent_execution(execution_id, status="succeeded")

    assert session.model_calls[0].status == "failed"
    assert session.model_calls[0].error_message == "Model request timed out after retry attempts."
    assert session.model_calls[0].retry_count == 0
    assert session.prompt_logs[0].assistant_response is None
    assert session.model_calls[0].execution_id == execution_id
    assert session.buffered_events[0].call_id == session.model_calls[0].call_id
    assert session.buffered_events[0].execution_id == execution_id
    assert session.agent_executions[0].status == "succeeded"


def test_aoai_retry_is_one_logical_call() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, text="retry")
        return httpx.Response(200, json={"output_text": '{"ok":true}'})

    client = AOAIResponsesClient(
        responses_url="https://example.test/responses",
        api_key="secret-key",
        model="test-model",
        max_retries=1,
        retry_backoff_seconds=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    session = make_session()

    with bind_audit_context(session):
        assert client.generate_json(make_request()) == {"ok": True}

    assert attempts == 2
    assert len(session.model_calls) == len(session.prompt_logs) == 1
    assert session.model_calls[0].retry_count == 1


def test_aoai_retry_count_survives_parse_failure_after_retry() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, text="retry")
        return httpx.Response(200, json={"output_text": "{broken-json"})

    client = AOAIResponsesClient(
        responses_url="https://example.test/responses",
        api_key="secret-key",
        model="test-model",
        max_retries=1,
        retry_backoff_seconds=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    session = make_session()

    with bind_audit_context(session), pytest.raises(LLMResponseParseError):
        client.generate_json(make_request())

    assert attempts == 2
    assert session.model_calls[0].status == "failed"
    assert session.model_calls[0].retry_count == 1
    assert_exact_text(session.prompt_logs[0].assistant_response, "{broken-json")


def test_mock_audit_uses_deterministic_compact_json() -> None:
    client = create_llm_client({})
    session = make_session()

    with bind_audit_context(session):
        result = client.generate_json(make_request())

    expected = json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    assert session.model_calls[0].provider == "mock"
    assert session.model_calls[0].model_name == "deterministic"
    assert_exact_text(session.prompt_logs[0].assistant_response, expected)


def test_audit_variable_serialization_failure_does_not_change_mock_result(capsys) -> None:
    client = create_llm_client({})
    session = make_session()
    request = make_request().model_copy(update={"variables_jsonb": {"bad": object()}})

    with bind_audit_context(session):
        result = client.generate_json(request)

    assert result == {"fallback_reasons": ["unsupported mock schema: unit-test.v1"]}
    assert session.model_calls == ()
    assert session.prompt_logs == ()
    stderr = capsys.readouterr().err
    assert "ai_audit_failure" in stderr
    assert "object" not in stderr


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
