from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMClientError(RuntimeError):
    """Base error for LLM provider failures."""

    def __init__(self, message: str, *, retry_count: int = 0) -> None:
        super().__init__(message)
        self.retry_count = retry_count


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
    enable_web_search: bool = False
    task_type: str | None = None
    prompt_template_name: str | None = None
    prompt_version: str | None = None
    variables_jsonb: dict[str, Any] = Field(default_factory=dict)


class LLMClient(Protocol):
    def generate_json(self, request: LLMJsonRequest) -> dict[str, Any]:
        """Generate a JSON object for a validated prompt/schema request."""
