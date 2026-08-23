from __future__ import annotations

import atexit
import os
from collections.abc import Mapping
from threading import Lock
from urllib.parse import urlsplit

import httpx

from ai_graph.llm.aoai import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_WEB_SEARCH_TOOL_TYPE,
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
AI_AOAI_WEB_SEARCH_TOOL_TYPE_ENV = "AI_AOAI_WEB_SEARCH_TOOL_TYPE"

LLM_PROVIDER_MOCK = "mock"
LLM_PROVIDER_AOAI = "aoai"
_AOAI_ROLE_OVERRIDE_SUFFIXES = (
    "RESPONSES_URL",
    "API_KEY",
    "MODEL",
    "TIMEOUT_SECONDS",
    "MAX_RETRIES",
    "RETRY_BACKOFF_SECONDS",
    "WEB_SEARCH_TOOL_TYPE",
)
_shared_http_client_lock = Lock()
_shared_http_client: httpx.Client | None = None


def _get_shared_http_client() -> httpx.Client:
    global _shared_http_client
    with _shared_http_client_lock:
        if _shared_http_client is None:
            _shared_http_client = httpx.Client()
        return _shared_http_client


def _close_shared_http_client() -> None:
    global _shared_http_client
    with _shared_http_client_lock:
        client = _shared_http_client
        _shared_http_client = None
    if client is not None:
        client.close()


atexit.register(_close_shared_http_client)


def create_llm_client(
    environ: Mapping[str, str] | None = None,
    *,
    role: str | None = None,
) -> LLMClient:
    env = os.environ if environ is None else environ
    provider = env.get(AI_LLM_PROVIDER_ENV, LLM_PROVIDER_MOCK).strip().lower()
    if provider in ("", LLM_PROVIDER_MOCK):
        return MockLLMClient()
    if provider == LLM_PROVIDER_AOAI:
        return _create_aoai_client(env, role=role)
    raise LLMProviderConfigError(f"unsupported {AI_LLM_PROVIDER_ENV}: {provider}")


def is_live_llm_provider(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get(AI_LLM_PROVIDER_ENV, LLM_PROVIDER_MOCK).strip().lower() == LLM_PROVIDER_AOAI


def live_provider_configuration_ready(
    environ: Mapping[str, str] | None = None,
    *,
    role: str | None = None,
) -> tuple[bool, str | None]:
    """Check whether live AOAI provider config is usable without issuing requests.

    When *role* is omitted, validate both the global AOAI configuration and any
    role-scoped AOAI overrides present in the environment so a broken override cannot
    make readiness report a misleading green state.
    """

    env = os.environ if environ is None else environ
    provider = env.get(AI_LLM_PROVIDER_ENV, LLM_PROVIDER_MOCK).strip().lower()
    if provider != LLM_PROVIDER_AOAI:
        return False, "live_provider_required"

    if not _live_provider_configuration_ready_for_role(env, role=None):
        return False, "provider_config_invalid"
    if role is not None:
        role_ready = _live_provider_configuration_ready_for_role(env, role)
        return role_ready, None if role_ready else "provider_config_invalid"

    for configured_role in _configured_aoai_roles(env):
        if not _live_provider_configuration_ready_for_role(env, configured_role):
            return False, "provider_config_invalid"
    return True, None


def _live_provider_configuration_ready_for_role(
    env: Mapping[str, str],
    role: str | None,
) -> bool:
    try:
        responses_url = _role_or_global_env(env, role, "RESPONSES_URL", AI_AOAI_RESPONSES_URL_ENV)
        parsed = urlsplit(responses_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False

        _role_or_global_env(env, role, "API_KEY", AI_AOAI_API_KEY_ENV)
        _role_or_global_env(env, role, "MODEL", AI_AOAI_MODEL_ENV)
        _float_env(
            env,
            _role_env_name(role, "TIMEOUT_SECONDS"),
            _float_env(env, AI_AOAI_TIMEOUT_SECONDS_ENV, DEFAULT_TIMEOUT_SECONDS),
        )
        _int_env(
            env,
            _role_env_name(role, "MAX_RETRIES"),
            _int_env(env, AI_AOAI_MAX_RETRIES_ENV, DEFAULT_MAX_RETRIES),
        )
        _float_env(
            env,
            _role_env_name(role, "RETRY_BACKOFF_SECONDS"),
            _float_env(env, AI_AOAI_RETRY_BACKOFF_SECONDS_ENV, 0.25),
        )
        _str_env(
            env,
            _role_env_name(role, "WEB_SEARCH_TOOL_TYPE"),
            _str_env(env, AI_AOAI_WEB_SEARCH_TOOL_TYPE_ENV, DEFAULT_WEB_SEARCH_TOOL_TYPE),
        )
    except (LLMProviderConfigError, TypeError, ValueError):
        return False
    return True


def _configured_aoai_roles(env: Mapping[str, str]) -> list[str]:
    roles: set[str] = set()
    for key in env:
        if not key.startswith("AI_LLM_"):
            continue
        for suffix in _AOAI_ROLE_OVERRIDE_SUFFIXES:
            marker = f"_{suffix}"
            if key.endswith(marker):
                role = key[len("AI_LLM_") : -len(marker)]
                if role:
                    roles.add(role)
                break
    return sorted(roles)


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
        web_search_tool_type=_str_env(
            env,
            _role_env_name(role, "WEB_SEARCH_TOOL_TYPE"),
            _str_env(env, AI_AOAI_WEB_SEARCH_TOOL_TYPE_ENV, DEFAULT_WEB_SEARCH_TOOL_TYPE),
        ),
        http_client=_get_shared_http_client(),
        compatibility_cache_key=f"{responses_url}\0{model}",
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


def _str_env(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(key)
    if value is None or not value.strip():
        return default
    return value.strip()
