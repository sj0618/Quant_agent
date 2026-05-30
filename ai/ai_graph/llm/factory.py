from __future__ import annotations

import os
from collections.abc import Mapping

from ai_graph.llm.aoai import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    AOAIResponsesClient,
)
from ai_graph.llm.base import LLMClient, LLMProviderConfigError
from ai_graph.llm.mock import MockLLMClient


AI_LLM_PROVIDER_ENV = "AI_LLM_PROVIDER"
AI_AOAI_RESPONSES_URL_ENV = "AI_AOAI_RESPONSES_URL"
AI_AOAI_API_KEY_ENV = "AI_AOAI_API_KEY"
AI_AOAI_MODEL_ENV = "AI_AOAI_MODEL"
AI_AOAI_TIMEOUT_SECONDS_ENV = "AI_AOAI_TIMEOUT_SECONDS"
AI_AOAI_MAX_RETRIES_ENV = "AI_AOAI_MAX_RETRIES"
AI_AOAI_RETRY_BACKOFF_SECONDS_ENV = "AI_AOAI_RETRY_BACKOFF_SECONDS"

LLM_PROVIDER_MOCK = "mock"
LLM_PROVIDER_AOAI = "aoai"


def create_llm_client(
    environ: Mapping[str, str] | None = None,
    *,
    role: str | None = None,
) -> LLMClient:
    env = environ or os.environ
    provider = env.get(AI_LLM_PROVIDER_ENV, LLM_PROVIDER_MOCK).strip().lower()
    if provider in ("", LLM_PROVIDER_MOCK):
        return MockLLMClient()
    if provider == LLM_PROVIDER_AOAI:
        return _create_aoai_client(env, role=role)
    raise LLMProviderConfigError(f"unsupported {AI_LLM_PROVIDER_ENV}: {provider}")


def _create_aoai_client(
    env: Mapping[str, str],
    *,
    role: str | None = None,
) -> AOAIResponsesClient:
    responses_url = _role_or_global_env(env, role, "RESPONSES_URL", AI_AOAI_RESPONSES_URL_ENV)
    api_key = _role_or_global_env(env, role, "API_KEY", AI_AOAI_API_KEY_ENV)
    model = _role_or_global_env(env, role, "MODEL", AI_AOAI_MODEL_ENV)
    return AOAIResponsesClient(
        responses_url=responses_url,
        api_key=api_key,
        model=model,
        timeout_seconds=_float_env(
            env,
            _role_env_name(role, "TIMEOUT_SECONDS"),
            _float_env(env, AI_AOAI_TIMEOUT_SECONDS_ENV, DEFAULT_TIMEOUT_SECONDS),
        ),
        max_retries=_int_env(
            env,
            _role_env_name(role, "MAX_RETRIES"),
            _int_env(env, AI_AOAI_MAX_RETRIES_ENV, DEFAULT_MAX_RETRIES),
        ),
        retry_backoff_seconds=_float_env(
            env,
            _role_env_name(role, "RETRY_BACKOFF_SECONDS"),
            _float_env(env, AI_AOAI_RETRY_BACKOFF_SECONDS_ENV, 0.25),
        ),
    )


def _role_or_global_env(
    env: Mapping[str, str],
    role: str | None,
    suffix: str,
    global_key: str,
) -> str:
    role_key = _role_env_name(role, suffix)
    if role_key:
        value = env.get(role_key)
        if value is not None and value.strip():
            return value
    return _required_env(env, global_key)


def _role_env_name(role: str | None, suffix: str) -> str:
    if role is None or not role.strip():
        return ""
    normalized = role.strip().upper().replace("-", "_").replace(" ", "_")
    return f"AI_LLM_{normalized}_{suffix}"


def _required_env(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if value is None or not value.strip():
        raise LLMProviderConfigError(f"{key} is required when {AI_LLM_PROVIDER_ENV}=aoai")
    return value


def _float_env(env: Mapping[str, str], key: str, default: float) -> float:
    value = env.get(key)
    if value is None or not value.strip():
        return default
    return float(value)


def _int_env(env: Mapping[str, str], key: str, default: int) -> int:
    value = env.get(key)
    if value is None or not value.strip():
        return default
    return int(value)
