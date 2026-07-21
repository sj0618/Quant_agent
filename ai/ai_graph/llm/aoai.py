from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ai_graph.audit import begin_model_call, finish_model_call
from ai_graph.llm.base import LLMClientError, LLMJsonRequest, LLMResponseParseError
from ai_graph.progress import activity_listener_installed, report_activity


RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25
DEFAULT_WEB_SEARCH_TOOL_TYPE = "web_search_preview"


class AOAIResponsesClient:
    def __init__(
        self,
        *,
        responses_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        web_search_tool_type: str = DEFAULT_WEB_SEARCH_TOOL_TYPE,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.responses_url = responses_url
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.web_search_tool_type = web_search_tool_type
        self._http_client = http_client

    def generate_json(self, request: LLMJsonRequest) -> dict[str, Any]:
        call_id = begin_model_call(
            task_type=request.task_type or request.schema_name,
            provider="aoai",
            model_name=self.model,
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            variables_jsonb=request.variables_jsonb,
            prompt_template_name=request.prompt_template_name,
            prompt_version=request.prompt_version,
            temperature=request.temperature,
            response_schema_name=request.schema_name,
            web_search_used=request.enable_web_search,
        )
        started_at = time.perf_counter()
        assistant_response: str | None = None
        retry_count = 0
        provider_request_id: str | None = None
        response_model = self.model
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        total_tokens: int | None = None
        try:
            if activity_listener_installed():
                # Streaming exists purely so the live view has something to show; the
                # terminal response.completed event carries the same response object the
                # non-streaming call returns, so everything below is identical either way.
                payload, retry_count = self._stream_with_retries(request)
                response = None
                provider_request_id = _provider_request_id(payload, None)
            else:
                response, retry_count = self._post_with_retries(request)
                provider_request_id = _provider_request_id(None, response)
                try:
                    payload = response.json()
                except json.JSONDecodeError as exc:
                    assistant_response = response.text
                    raise LLMResponseParseError("AOAI response body is not valid JSON") from exc
                provider_request_id = _provider_request_id(payload, response)

            response_model = _response_model(payload) or self.model
            prompt_tokens, completion_tokens, total_tokens = _usage(payload)
            raw_output = _raw_assistant_output(payload, response.text if response else "")
            try:
                result = extract_json_object(payload)
            except LLMResponseParseError:
                assistant_response = raw_output
                raise
            assistant_response = raw_output
        except Exception as exc:
            retry_count = max(retry_count, getattr(exc, "retry_count", 0))
            finish_model_call(
                call_id,
                status="failed",
                assistant_response=assistant_response,
                provider_request_id=provider_request_id,
                model_name=response_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=(time.perf_counter() - started_at) * 1000,
                retry_count=retry_count,
                error_type=type(exc).__name__,
                error_message=_safe_model_failure_message(exc),
            )
            raise

        finish_model_call(
            call_id,
            status="succeeded",
            assistant_response=assistant_response,
            provider_request_id=provider_request_id,
            model_name=response_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            retry_count=retry_count,
        )
        return result

    def _stream_with_retries(self, request: LLMJsonRequest) -> tuple[dict[str, Any], int]:
        """Stream the response, publishing provider activity, and return its final payload.

        Only the terminal `response.completed` event is used as the result: it repeats
        the whole response object, so the caller parses exactly what the non-streaming
        path would have received. Everything emitted along the way is passed through
        untouched - search queries, text deltas and citations are the provider's own.
        """

        body = self._request_body(request)
        body["stream"] = True
        headers = {"Content-Type": "application/json", "api-key": self.api_key}
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        last_attempt = 0

        for attempt in range(attempts):
            last_attempt = attempt
            client = self._http_client or httpx.Client(timeout=self.timeout_seconds)
            owns_client = self._http_client is None
            try:
                try:
                    with client.stream(
                        "POST", self.responses_url, headers=headers, json=body
                    ) as response:
                        if response.status_code >= 400:
                            response.read()
                            if _unsupported_parameter(response, "temperature"):
                                body.pop("temperature", None)
                                continue
                            if (
                                response.status_code in RETRYABLE_STATUS_CODES
                                and attempt < attempts - 1
                            ):
                                _sleep_before_retry(self.retry_backoff_seconds, attempt)
                                continue
                            response.raise_for_status()
                        payload = self._consume_stream(response)
                        if payload is None:
                            raise LLMResponseParseError(
                                "AOAI stream ended without a response.completed event"
                            )
                        return payload, attempt
                finally:
                    if owns_client:
                        client.close()
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if not _should_retry(exc) or attempt >= attempts - 1:
                    break
                _sleep_before_retry(self.retry_backoff_seconds, attempt)

        raise LLMClientError(
            "AOAI Responses stream failed", retry_count=last_attempt
        ) from last_error

    def _consume_stream(self, response: httpx.Response) -> dict[str, Any] | None:
        final_payload: dict[str, Any] | None = None
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            if event_type == "response.completed":
                completed = event.get("response")
                if isinstance(completed, dict):
                    final_payload = completed
            else:
                _publish_stream_activity(event_type, event)
        return final_payload

    def _request_body(self, request: LLMJsonRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
        }
        if request.enable_web_search:
            body["tools"] = [{"type": self.web_search_tool_type}]
        if request.response_schema is not None:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": _schema_format_name(request.schema_name),
                    "strict": True,
                    "schema": request.response_schema,
                }
            }
        return body

    def _post_with_retries(self, request: LLMJsonRequest) -> tuple[httpx.Response, int]:
        body = self._request_body(request)
        headers = {"Content-Type": "application/json", "api-key": self.api_key}
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        last_attempt = 0

        for attempt in range(attempts):
            last_attempt = attempt
            try:
                client = self._http_client or httpx.Client(timeout=self.timeout_seconds)
                if self._http_client is None:
                    with client:
                        response = client.post(self.responses_url, headers=headers, json=body)
                        if _unsupported_parameter(response, "temperature"):
                            body.pop("temperature", None)
                            response = client.post(self.responses_url, headers=headers, json=body)
                else:
                    response = client.post(self.responses_url, headers=headers, json=body)
                    if _unsupported_parameter(response, "temperature"):
                        body.pop("temperature", None)
                        response = client.post(self.responses_url, headers=headers, json=body)
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < attempts - 1:
                    _sleep_before_retry(self.retry_backoff_seconds, attempt)
                    continue
                response.raise_for_status()
                return response, attempt
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if not _should_retry(exc) or attempt >= attempts - 1:
                    break
                _sleep_before_retry(self.retry_backoff_seconds, attempt)

        raise LLMClientError(
            "AOAI Responses request failed", retry_count=last_attempt
        ) from last_error


def _publish_stream_activity(event_type: Any, event: dict[str, Any]) -> None:
    """Forward one provider stream event to the live view, verbatim.

    Only events that carry something a reader can act on are forwarded; the values
    (queries, deltas, citation titles/urls) are exactly what the provider sent.
    """

    if event_type == "response.web_search_call.searching":
        report_activity("search_started")
        return
    if event_type == "response.output_text.delta":
        delta = event.get("delta")
        if isinstance(delta, str) and delta:
            report_activity("text_delta", text=delta)
        return
    if event_type == "response.output_text.annotation.added":
        annotation = event.get("annotation")
        if isinstance(annotation, dict) and annotation.get("type") == "url_citation":
            report_activity(
                "citation",
                title=annotation.get("title"),
                url=annotation.get("url"),
            )
        return
    if event_type == "response.output_item.done":
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "web_search_call":
            return
        action = item.get("action")
        if not isinstance(action, dict):
            return
        # The provider only reveals what it searched for once the search finishes, so
        # this necessarily lands after the matching search_started.
        queries = [query for query in action.get("queries") or [] if isinstance(query, str)]
        if not queries and isinstance(action.get("query"), str):
            queries = [action["query"]]
        if queries:
            report_activity("search_queries", queries=queries)


def _unsupported_parameter(response: httpx.Response, parameter: str) -> bool:
    if response.status_code != 400:
        return False
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    return isinstance(error, dict) and error.get("param") == parameter


def _schema_format_name(schema_name: str) -> str:
    normalized = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in schema_name
    )
    return normalized[:64] or "response"


def extract_json_object(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        direct_text = payload.get("output_text")
        if isinstance(direct_text, str):
            return parse_json_object(direct_text)

        nested_text = _extract_nested_output_text(payload)
        if nested_text is not None:
            return parse_json_object(nested_text)

        if _looks_like_direct_json_payload(payload):
            return payload

    if isinstance(payload, str):
        return parse_json_object(payload)

    raise LLMResponseParseError("AOAI response did not contain a JSON object payload")


def parse_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = _strip_code_fence(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMResponseParseError("AOAI output_text is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMResponseParseError("AOAI JSON response must be an object")
    return parsed


def _extract_nested_output_text(payload: dict[str, Any]) -> str | None:
    output = payload.get("output")
    if not isinstance(output, list):
        return None
    text_parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in (None, "message"):
            continue
        content = item.get("content")
        if isinstance(content, str):
            text_parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            if content_item.get("type") not in (None, "output_text"):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    if not text_parts:
        return None
    return "\n".join(text_parts)


def _raw_assistant_output(payload: Any, response_text: str) -> str:
    if isinstance(payload, dict):
        output_text = payload.get("output_text")
        if isinstance(output_text, str):
            return output_text
        nested_text = _extract_nested_output_text(payload)
        if nested_text is not None:
            return nested_text
        if isinstance(payload.get("output"), list):
            return ""
        return response_text
    if isinstance(payload, str):
        return payload
    return response_text


def _provider_request_id(payload: Any, response: httpx.Response | None) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("id"), str):
        return payload["id"]
    if response is None:
        return None
    return response.headers.get("x-request-id") or response.headers.get("apim-request-id")


def _response_model(payload: Any) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("model"), str):
        return payload["model"]
    return None


def _usage(payload: Any) -> tuple[int | None, int | None, int | None]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return None, None, None
    prompt = _optional_int(usage.get("input_tokens", usage.get("prompt_tokens")))
    completion = _optional_int(usage.get("output_tokens", usage.get("completion_tokens")))
    total = _optional_int(usage.get("total_tokens"))
    return prompt, completion, total


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _safe_model_failure_message(exc: Exception) -> str:
    if isinstance(exc, LLMResponseParseError):
        return "Model response could not be parsed as the required JSON object."
    cause = exc.__cause__
    if isinstance(cause, httpx.TimeoutException):
        return "Model request timed out after retry attempts."
    if isinstance(cause, httpx.HTTPStatusError):
        return f"Model provider returned HTTP {cause.response.status_code} after retry attempts."
    if isinstance(cause, httpx.TransportError):
        return "Model provider transport failed after retry attempts."
    if isinstance(exc, LLMClientError):
        return "Model request failed after retry attempts."
    return f"{type(exc).__name__} during model call."


def _looks_like_direct_json_payload(payload: dict[str, Any]) -> bool:
    response_metadata_fields = {
        "id",
        "object",
        "created_at",
        "status",
        "model",
        "output",
        "output_text",
        "usage",
        "error",
    }
    return not response_metadata_fields.intersection(payload.keys())


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _sleep_before_retry(backoff_seconds: float, attempt: int) -> None:
    if backoff_seconds <= 0:
        return
    time.sleep(backoff_seconds * (attempt + 1))
