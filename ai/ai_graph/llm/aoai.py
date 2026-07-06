from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ai_graph.llm.base import LLMClientError, LLMJsonRequest, LLMResponseParseError


RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
DEFAULT_TIMEOUT_SECONDS = 30.0
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
        response = self._post_with_retries(request)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise LLMResponseParseError("AOAI response body is not valid JSON") from exc
        return extract_json_object(payload)

    def _post_with_retries(self, request: LLMJsonRequest) -> httpx.Response:
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
        headers = {"Content-Type": "application/json", "api-key": self.api_key}
        attempts = self.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                client = self._http_client or httpx.Client(timeout=self.timeout_seconds)
                if self._http_client is None:
                    with client:
                        response = client.post(self.responses_url, headers=headers, json=body)
                else:
                    response = client.post(self.responses_url, headers=headers, json=body)
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < attempts - 1:
                    _sleep_before_retry(self.retry_backoff_seconds, attempt)
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if not _should_retry(exc) or attempt >= attempts - 1:
                    break
                _sleep_before_retry(self.retry_backoff_seconds, attempt)

        raise LLMClientError("AOAI Responses request failed") from last_error


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
        content = item.get("content")
        if isinstance(content, str):
            text_parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    if not text_parts:
        return None
    return "\n".join(text_parts)


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
