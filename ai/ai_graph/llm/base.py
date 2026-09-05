from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMClientError(RuntimeError):
    """Base error for LLM provider failures."""

    def __init__(self, message: str, *, retry_count: int = 0) -> None:
        super().__init__(message)
        self.retry_count = retry_count


class LLMTimeoutError(LLMClientError):
    """The provider did not respond within the configured client budget."""


class LLMConnectionError(LLMClientError):
    """The client could not establish or maintain a provider transport connection."""


class LLMHTTPStatusError(LLMClientError):
    """The provider returned a non-success HTTP status without exposing its body."""

    def __init__(self, status_code: int, *, retry_count: int = 0) -> None:
        if status_code < 100 or status_code > 599:
            raise ValueError("status_code must be an HTTP status code")
        super().__init__("AOAI Responses request failed with an HTTP error", retry_count=retry_count)
        self.status_code = status_code


class LLMProviderConfigError(LLMClientError):
    """Raised when the selected LLM provider is not configured safely."""


class LLMResponseParseError(LLMClientError):
    """Raised when an LLM response cannot be parsed as the requested JSON payload."""


class LLMJsonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_name: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    enable_web_search: bool = False
    require_web_search: bool = False
    # The strategy-research lane intentionally pays for a broader evidence search;
    # routine terminology lookups keep the provider default instead.
    web_search_context_size: Literal["low", "medium", "high"] | None = None
    # Streaming is useful when the client can surface token/search progress.  Some
    # Azure web-search deployments, however, buffer those events until the research
    # tool has finished.  A request that needs a bounded structured research contract
    # can opt into one ordinary Responses completion instead of mistaking that quiet
    # but healthy provider work for a dead stream.
    stream_response: bool = True
    # Reasoning tokens share max_output_tokens with visible structured output.  Nodes
    # that have a latency budget can set an explicit, model-supported effort instead
    # of relying on a deployment default that may consume the whole result budget.
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = None
    max_tool_calls: int | None = Field(default=None, ge=1)
    task_type: str | None = None
    prompt_template_name: str | None = None
    prompt_version: str | None = None
    variables_jsonb: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] | None = None


class LLMClient(Protocol):
    def generate_json(self, request: LLMJsonRequest) -> dict[str, Any]:
        """Generate a JSON object for a validated prompt/schema request."""
