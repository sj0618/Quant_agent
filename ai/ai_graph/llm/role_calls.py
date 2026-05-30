from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_graph.llm import LLMClientError, LLMJsonRequest, create_llm_client


ROLE_DEBATE_SCHEMA_NAME = "quantagent.role_debate.v1"


class RoleDebatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommendation: str = Field(default="HOLD", min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    validation_results: dict[str, Any] = Field(default_factory=dict)
    fallback_reasons: list[str] = Field(default_factory=list)


def generate_role_debate(
    *,
    role: str,
    task: str,
    context: dict[str, Any],
    fallback: RoleDebatePayload,
) -> RoleDebatePayload:
    """Run a role-specific LLM call, falling back to deterministic MVP notes.

    The fallback keeps local tests and mock mode stable, while AOAI deployments can
    be split by role through create_llm_client(role=...).
    """

    request = LLMJsonRequest(
        schema_name=ROLE_DEBATE_SCHEMA_NAME,
        system_prompt=_system_prompt(role, task),
        user_prompt=_user_prompt(context),
        temperature=0.0,
    )
    try:
        payload = create_llm_client(role=role).generate_json(request)
        return RoleDebatePayload.model_validate(
            {
                "role": role,
                **payload,
            }
        )
    except (LLMClientError, ValidationError, ValueError, TypeError) as exc:
        reasons = [*fallback.fallback_reasons, f"{type(exc).__name__}: {exc}"]
        return fallback.model_copy(update={"fallback_reasons": reasons})


def _system_prompt(role: str, task: str) -> str:
    return (
        "You are a QuantAgent role-specific analyst. Return JSON only with "
        "summary, evidence, concerns, recommendation, confidence, and "
        f"validation_results. Role={role}. Task={task}."
    )


def _user_prompt(context: dict[str, Any]) -> str:
    return (
        "Analyze this QuantAgent state snapshot. Keep the output concise and "
        f"machine-readable.\nCONTEXT_JSON={context}"
    )
