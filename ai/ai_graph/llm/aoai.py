from __future__ import annotations

import json
import logging
from threading import Lock
import time
from typing import Any

import httpx

from ai_graph.audit import begin_model_call, finish_model_call
from ai_graph.llm.base import (
    LLMClientError,
    LLMConnectionError,
    LLMHTTPStatusError,
    LLMJsonRequest,
    LLMResponseParseError,
    LLMTimeoutError,
)
from ai_graph.llm.concurrency_gate import AOAIConcurrencyGate, get_shared_gate
from ai_graph.progress import report_activity


RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_RESPONSE_START_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25
DEFAULT_SERVICE_TIER = "priority"
# Used when a 429 arrives without a Retry-After header, and as the cap when it has one.
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 5.0
MAX_RETRY_AFTER_SECONDS = 60.0
DEFAULT_WEB_SEARCH_TOOL_TYPE = "web_search_preview"
MAX_COMPATIBILITY_ADJUSTMENTS = 3
UNSUPPORTED_STRICT_SCHEMA_KEYWORDS = frozenset(
    {
        "$id",
        "$schema",
        "default",
        "deprecated",
        "examples",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "format",
        "maxItems",
        "maxLength",
        "maxProperties",
        "maximum",
        "minContains",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "multipleOf",
        "pattern",
        "patternProperties",
        "propertyNames",
        "readOnly",
        "title",
        "unevaluatedItems",
        "unevaluatedProperties",
        "uniqueItems",
        "writeOnly",
    }
)
# Stream events that carry the finished response object.
TERMINAL_STREAM_EVENTS = frozenset(
    {"response.completed", "response.incomplete", "response.failed"}
)

_logger = logging.getLogger(__name__)
_compatibility_lock = Lock()
_compatibility_cache: dict[str, dict[str, bool]] = {}


def _compatibility_snapshot(cache_key: str | None) -> dict[str, bool]:
    defaults = {
        "temperature": True,
        "service_tier": True,
        "structured_outputs": True,
    }
    if cache_key is None:
        return defaults
    with _compatibility_lock:
        return {**defaults, **_compatibility_cache.get(cache_key, {})}


def _uses_fixed_sampling_temperature(model: str) -> bool:
    """Return whether the deployed model rejects explicit sampling temperature."""

    return model.strip().lower().startswith("gpt-5")


def _remember_unsupported(cache_key: str | None, feature: str) -> None:
    if cache_key is None:
        return
    with _compatibility_lock:
        state = _compatibility_cache.setdefault(cache_key, {})
        state[feature] = False


class AOAIResponsesClient:
    def __init__(
        self,
        *,
        responses_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        response_start_timeout_seconds: float = DEFAULT_RESPONSE_START_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        service_tier: str = DEFAULT_SERVICE_TIER,
        web_search_tool_type: str = DEFAULT_WEB_SEARCH_TOOL_TYPE,
        http_client: httpx.Client | None = None,
        compatibility_cache_key: str | None = None,
        concurrency_gate: AOAIConcurrencyGate | None = None,
    ) -> None:
        self.responses_url = responses_url
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.response_start_timeout_seconds = response_start_timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.service_tier = service_tier
        self.web_search_tool_type = web_search_tool_type
        self._http_client = http_client
        self._compatibility_cache_key = compatibility_cache_key
        # Deferred to the shared process-wide gate unless a test injects its own, so every
        # client instance - one is built per logical call in `role_calls` - contends for
        # the same deployment capacity rather than each keeping a private allowance.
        self._concurrency_gate = concurrency_gate or get_shared_gate()
        # Fixed-sampling model families reject `temperature` outright. Unknown model
        # aliases still learn from the first 400 and share that result process-wide.
        compatibility = _compatibility_snapshot(compatibility_cache_key)
        self._temperature_supported = (
            compatibility["temperature"]
            and not _uses_fixed_sampling_temperature(model)
        )
        self._service_tier_supported = compatibility["service_tier"]
        self._structured_outputs_supported = compatibility["structured_outputs"]
        self.logical_call_count = 0
        self.physical_http_post_count = 0
        self.last_call_timings: dict[str, Any] = {}

    def generate_json(self, request: LLMJsonRequest) -> dict[str, Any]:
        self.logical_call_count += 1
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
        physical_before = self.physical_http_post_count
        try:
            # Always stream, even when no activity listener is installed. A non-streamed
            # Responses request does not expose when generation starts, so it cannot
            # enforce a response-start timeout independently from response completion.
            payload, retry_count, direct_body, provider_request_id = (
                self._stream_with_retries(request)
            )
            if direct_body is not None:
                try:
                    payload = json.loads(direct_body)
                except json.JSONDecodeError as exc:
                    assistant_response = direct_body
                    raise LLMResponseParseError("AOAI response body is not valid JSON") from exc
            provider_request_id = _provider_request_id(payload, None) or provider_request_id

            response_model = _response_model(payload) or self.model
            prompt_tokens, completion_tokens, total_tokens = _usage(payload)
            raw_output = _raw_assistant_output(payload, direct_body or "")
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
            self.last_call_timings = {
                **self.last_call_timings,
                "logical_call_count": self.logical_call_count,
                "physical_http_posts": self.physical_http_post_count - physical_before,
                "completion_seconds": round(time.perf_counter() - started_at, 6),
                "retry_count": retry_count,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
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
        self.last_call_timings = {
            **self.last_call_timings,
            "logical_call_count": self.logical_call_count,
            "physical_http_posts": self.physical_http_post_count - physical_before,
            "completion_seconds": round(time.perf_counter() - started_at, 6),
            "retry_count": retry_count,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        return result

    def _stream_with_retries(
        self, request: LLMJsonRequest
    ) -> tuple[dict[str, Any] | None, int, str | None, str | None]:
        """Stream the response, publishing provider activity, and return its final payload.

        Only the terminal `response.completed` event is used as the result: it repeats
        the whole response object, so the caller parses exactly what the non-streaming
        path would have received. Everything emitted along the way is passed through
        untouched - search queries, text deltas and citations are the provider's own.
        """

        body = self._request_body(request)
        body["stream"] = True
        headers = {"Content-Type": "application/json", "api-key": self.api_key}
        max_posts = self.max_retries + MAX_COMPATIBILITY_ADJUSTMENTS + 1
        last_error: Exception | None = None
        retry_count = 0
        compatibility_adjustments: list[str] = []
        # Backoff is deferred to the top of the next attempt so it happens outside the
        # concurrency gate. Sleeping while holding a slot would be capacity nobody can
        # use, and a Retry-After wait exists precisely to let the deployment recover.
        pending_backoff: tuple[int, httpx.Response | None] | None = None

        for _ in range(max_posts):
            if pending_backoff is not None:
                backoff_attempt, backoff_response = pending_backoff
                pending_backoff = None
                _sleep_before_retry(
                    self.retry_backoff_seconds, backoff_attempt, backoff_response
                )
            attempt_started = time.perf_counter()
            client = self._http_client or httpx.Client(timeout=self.timeout_seconds)
            owns_client = self._http_client is None
            try:
                try:
                    response_start_timeout = httpx.Timeout(
                        self.timeout_seconds,
                        read=self.response_start_timeout_seconds,
                    )
                    # One slot spans the whole exchange, streamed body included: a
                    # completion that is still generating still occupies deployment
                    # capacity, so releasing at the first header would admit far more
                    # concurrent work than Azure is actually serving.
                    with self._concurrency_gate.acquire_slot(), client.stream(
                        "POST",
                        self.responses_url,
                        headers=headers,
                        json=body,
                        timeout=response_start_timeout,
                    ) as response:
                        self.physical_http_post_count += 1
                        self._observe_provider_capacity(response)
                        self.last_call_timings = {
                            "first_header_seconds": round(
                                time.perf_counter() - attempt_started, 6
                            ),
                            "first_meaningful_text_seconds": None,
                            "compatibility_adjustments": list(
                                compatibility_adjustments
                            ),
                        }
                        if response.status_code >= 400:
                            response.read()
                            if _unsupported_parameter(response, "temperature"):
                                compatibility_adjustments.append("temperature")
                                self._temperature_supported = False
                                _remember_unsupported(
                                    self._compatibility_cache_key, "temperature"
                                )
                                body.pop("temperature", None)
                                continue
                            if _unsupported_parameter(response, "service_tier"):
                                compatibility_adjustments.append("service_tier")
                                self._service_tier_supported = False
                                _remember_unsupported(
                                    self._compatibility_cache_key, "service_tier"
                                )
                                body.pop("service_tier", None)
                                continue
                            if "text" in body:
                                # Azure deployments differ in their structured-output
                                # support. Keep the JSON contract in the prompt and let
                                # Pydantic validate it when this deployment rejects the
                                # provider-side schema.
                                compatibility_adjustments.append(
                                    "structured_outputs"
                                )
                                self._structured_outputs_supported = False
                                _remember_unsupported(
                                    self._compatibility_cache_key, "structured_outputs"
                                )
                                body.pop("text", None)
                                continue
                            if (
                                response.status_code in RETRYABLE_STATUS_CODES
                                and retry_count < self.max_retries
                            ):
                                pending_backoff = (retry_count, response)
                                retry_count += 1
                                continue
                            response.raise_for_status()
                        if "text/event-stream" not in response.headers.get(
                            "content-type", ""
                        ).lower():
                            response.read()
                            self.last_call_timings["first_meaningful_text_seconds"] = round(
                                time.perf_counter() - attempt_started, 6
                            )
                            response.request.extensions["timeout"]["read"] = self.timeout_seconds
                            return (
                                None,
                                retry_count,
                                response.text,
                                _provider_request_id(None, response),
                            )
                        payload, terminal, first_text_seconds = self._consume_stream(
                            response,
                            attempt_started=attempt_started,
                        )
                        self.last_call_timings[
                            "first_meaningful_text_seconds"
                        ] = first_text_seconds
                        if terminal == "response.completed" and payload is not None:
                            return (
                                payload,
                                retry_count,
                                None,
                                _provider_request_id(payload, response),
                            )
                        # Either the stream stopped early (transport hiccup) or the run
                        # ended incomplete/failed. Neither yields a parseable answer, so
                        # retry instead of handing the caller a response with no message.
                        last_error = LLMResponseParseError(
                            _stream_failure_reason(terminal, payload)
                        )
                        if retry_count < self.max_retries:
                            pending_backoff = (retry_count, None)
                            retry_count += 1
                            continue
                        break
                finally:
                    if owns_client:
                        client.close()
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if not _should_retry(exc) or retry_count >= self.max_retries:
                    break
                _sleep_before_retry(
                    self.retry_backoff_seconds,
                    retry_count,
                    exc.response if isinstance(exc, httpx.HTTPStatusError) else None,
                )
                retry_count += 1

        raise _typed_provider_failure(last_error, retry_count=retry_count) from last_error

    def _observe_provider_capacity(self, response: httpx.Response) -> None:
        """Report what this response says about remaining deployment capacity.

        Called on every response, not only failures: the gate needs the healthy ones to
        justify growing back after a shrink, and Azure attaches its remaining-quota
        headers to successes too.
        """

        if response.status_code == 429:
            # A 429 is authoritative on its own; deployments do not always attach usable
            # rate-limit headers to it, and waiting for one would miss the clearest signal.
            self._concurrency_gate.observe_rate_limited_response()
            return
        self._concurrency_gate.observe_rate_limit_headers(response.headers)

    def _consume_stream(
        self,
        response: httpx.Response,
        *,
        attempt_started: float,
    ) -> tuple[dict[str, Any] | None, str | None, float | None]:
        """Drain the stream, returning its final response object and terminal event type.

        The terminal type is reported separately because only `response.completed`
        carries a usable answer: an incomplete or failed run still repeats the response
        object, but without the message the caller is trying to parse.

        Headers alone do not satisfy the response-start deadline. Until the response
        actually starts - a `web_search_call.searching` event or the first non-empty
        text delta - both the short socket read timeout and the wall-clock check below
        remain active. The normal timeout applies afterwards.

        The deadline is silence, not elapsed time. It used to run from the start of the
        attempt to the first text delta, which is not a liveness signal at all on a
        reasoning deployment: the model emits `response.created`, `response.in_progress`
        and `web_search_call` events while it thinks and searches, and only then starts
        writing. Anything that thought for longer than the deadline was killed as a dead
        stream and retried into the same wall. Measured over 14 days of production, that
        was every `strategy_intent` call ever made - 13 of 13, each dying at 33-40s after
        its retries - while `backtest_code_generation` calls that began writing early
        went on to succeed at 38.8s. The budget was never the problem; what it timed was.
        """

        final_payload: dict[str, Any] | None = None
        terminal_type: str | None = None
        first_text_seconds: float | None = None
        response_started = False
        last_event_at = attempt_started
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
            # Any well-formed event proves the deployment is still working on this
            # request, which is the only thing the start deadline is entitled to check.
            last_event_at = time.perf_counter()
            event_type = event.get("type")
            if event_type == "response.web_search_call.searching":
                response_started = True
                response.request.extensions["timeout"]["read"] = self.timeout_seconds
            if event_type == "response.output_text.delta":
                delta = event.get("delta")
                if (
                    first_text_seconds is None
                    and isinstance(delta, str)
                    and delta.strip()
                ):
                    first_text_seconds = round(
                        time.perf_counter() - attempt_started, 6
                    )
                    response_started = True
                    response.request.extensions["timeout"][
                        "read"
                    ] = self.timeout_seconds
            if (
                not response_started
                and time.perf_counter() - last_event_at
                > self.response_start_timeout_seconds
            ):
                raise httpx.ReadTimeout(
                    "AOAI stream went silent before the response-start deadline",
                    request=response.request,
                )
            if event_type in TERMINAL_STREAM_EVENTS:
                terminal_type = str(event_type)
                completed = event.get("response")
                if isinstance(completed, dict):
                    final_payload = completed
                    if (
                        first_text_seconds is None
                        and _raw_assistant_output(completed, "").strip()
                    ):
                        first_text_seconds = round(
                            time.perf_counter() - attempt_started, 6
                        )
                        response.request.extensions["timeout"][
                            "read"
                        ] = self.timeout_seconds
            else:
                _publish_stream_activity(event_type, event)
        return final_payload, terminal_type, first_text_seconds

    def _request_body(self, request: LLMJsonRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        if self._temperature_supported:
            body["temperature"] = request.temperature
        if self._service_tier_supported:
            body["service_tier"] = self.service_tier
        if request.max_output_tokens is not None:
            body["max_output_tokens"] = request.max_output_tokens
        if request.enable_web_search:
            body["tools"] = [{"type": self.web_search_tool_type}]
        if request.response_schema is not None and self._structured_outputs_supported:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": _schema_format_name(request.schema_name),
                    "strict": True,
                    "schema": _strict_response_schema(request.response_schema),
                }
            }
        return body


def _strict_response_schema(value: Any) -> Any:
    """Return the Azure/OpenAI strict JSON Schema subset.

    Pydantic intentionally emits validation constraints that remain useful for
    local validation but are rejected by strict structured outputs. Provider-side
    schemas require every object property and reject those type-specific keywords.
    """

    if isinstance(value, list):
        return [_strict_response_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key in UNSUPPORTED_STRICT_SCHEMA_KEYWORDS:
            continue
        if key == "const":
            normalized["enum"] = [_strict_response_schema(item)]
            continue
        normalized[key] = _strict_response_schema(item)

    properties = normalized.get("properties")
    if isinstance(properties, dict):
        normalized["additionalProperties"] = False
        normalized["required"] = list(properties)
    return normalized

def _stream_failure_reason(terminal: str | None, payload: dict[str, Any] | None) -> str:
    if terminal is None:
        return "AOAI stream ended without a terminal response event"
    detail: Any = None
    if isinstance(payload, dict):
        detail = payload.get("incomplete_details") or payload.get("error")
    return f"AOAI stream ended as {terminal}" + (f": {detail}" if detail else "")


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


def _typed_provider_failure(error: Exception | None, *, retry_count: int) -> LLMClientError:
    """Convert a transport failure into a closed, message-independent cause.

    ``LLMClientError`` used to retain only a generic label and leave callers to parse
    the chained httpx exception's string. The typed result carries the only public
    diagnostic we need: timeout, transport, or HTTP status class. HTTP response bodies
    and endpoint details stay attached solely to the private exception cause.
    """

    if isinstance(error, httpx.TimeoutException):
        return LLMTimeoutError("AOAI Responses request failed: timeout", retry_count=retry_count)
    if isinstance(error, httpx.HTTPStatusError):
        return LLMHTTPStatusError(error.response.status_code, retry_count=retry_count)
    if isinstance(error, httpx.TransportError):
        return LLMConnectionError("AOAI Responses request failed: transport", retry_count=retry_count)
    return LLMClientError("AOAI Responses request failed", retry_count=retry_count)


def _sleep_before_retry(
    backoff_seconds: float, attempt: int, response: httpx.Response | None = None
) -> None:
    """Back off before retrying, preferring the provider's own Retry-After.

    A rate-limited deployment needs seconds, not the sub-second linear backoff that
    suits a transient 5xx - retrying too early just burns the remaining attempts and
    fails the whole analysis.
    """

    delay = backoff_seconds * (attempt + 1)
    retry_after = _retry_after_seconds(response)
    rate_limited = retry_after is not None
    if rate_limited:
        delay = max(delay, min(retry_after or 0.0, MAX_RETRY_AFTER_SECONDS))
    if delay <= 0:
        return
    if rate_limited:
        # Honouring Retry-After can mean a full minute of silence per attempt, which
        # reads as a hang. Say so instead of leaving the view frozen.
        _logger.warning("AOAI rate limited; waiting %.0fs before retry", delay)
        report_activity(
            "step",
            label="AOAI 호출 제한 대기",
            detail=f"{delay:.0f}초 후 재시도합니다 (요청 한도 초과)",
        )
    time.sleep(delay)


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None or response.status_code != 429:
        return None
    raw = response.headers.get("retry-after")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    # No usable header: still wait meaningfully rather than hammering the quota.
    return DEFAULT_RATE_LIMIT_BACKOFF_SECONDS
