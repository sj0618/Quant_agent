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

LLM_PROVIDER_MOCK = "mock"
LLM_PROVIDER_AOAI = "aoai"


def create_llm_client(environ: Mapping[str, str] | None = None) -> LLMClient:
    env = environ or os.environ
    provider = env.get(AI_LLM_PROVIDER_ENV, LLM_PROVIDER_MOCK).strip().lower()
    if provider in ("", LLM_PROVIDER_MOCK):
        return MockLLMClient()
    if provider == LLM_PROVIDER_AOAI:
        return _create_aoai_client(env)
    raise LLMProviderConfigError(f"unsupported {AI_LLM_PROVIDER_ENV}: {provider}")


def _create_aoai_client(env: Mapping[str, str]) -> AOAIResponsesClient:
    responses_url = _required_env(env, AI_AOAI_RESPONSES_URL_ENV)
    api_key = _required_env(env, AI_AOAI_API_KEY_ENV)
    model = _required_env(env, AI_AOAI_MODEL_ENV)
    return AOAIResponsesClient(
        responses_url=responses_url,
        api_key=api_key,
        model=model,
        timeout_seconds=_float_env(env, AI_AOAI_TIMEOUT_SECONDS_ENV, DEFAULT_TIMEOUT_SECONDS),
        max_retries=_int_env(env, AI_AOAI_MAX_RETRIES_ENV, DEFAULT_MAX_RETRIES),
    )


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
