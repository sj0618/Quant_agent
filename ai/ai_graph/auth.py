from __future__ import annotations

import json
from collections.abc import Mapping
from os import environ
from typing import Protocol

from fastapi import HTTPException, Request, status

AUTH_ENABLED_ENV = "AUTH_ENABLED"
REDIS_URL_ENV = "REDIS_URL"
AUTH_SESSION_COOKIE_NAME_ENV = "AUTH_SESSION_COOKIE_NAME"
DEFAULT_SESSION_COOKIE_NAME = "qa_session"

# Must match AuthSessionStore.session_key in backend/app/services/session_store.py so
# both services validate the same Google-login session written by the backend auth API.
SESSION_KEY_PREFIX = "qa:auth:session"


def session_cookie_name(env: Mapping[str, str] | None = None) -> str:
    source = environ if env is None else env
    raw = (source.get(AUTH_SESSION_COOKIE_NAME_ENV) or "").strip()
    return raw or DEFAULT_SESSION_COOKIE_NAME


def auth_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Fail closed by default: any value other than an explicit disable keeps auth required."""

    source = environ if env is None else env
    raw = (source.get(AUTH_ENABLED_ENV) or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


class AuthConfigurationError(RuntimeError):
    """Raised when auth is enabled but required runtime config (REDIS_URL) is missing."""


class SessionResolver(Protocol):
    async def resolve_user_id(self, session_id: str | None) -> str | None: ...


class DisabledSessionResolver:
    """Only used when AUTH_ENABLED=0, for local development without the shared auth backend."""

    async def resolve_user_id(self, session_id: str | None) -> str | None:
        return "local-dev-user"


class RedisSessionResolver:
    """Validates the shared qa_session cookie against the Redis session store the backend auth service writes to."""

    def __init__(self, redis_client: object) -> None:
        self._redis = redis_client

    async def resolve_user_id(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        raw = await self._redis.get(f"{SESSION_KEY_PREFIX}:{session_id}")
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return None
        user_id = payload.get("user_id") if isinstance(payload, dict) else None
        return str(user_id) if user_id else None


def build_session_resolver_from_env(env: Mapping[str, str] | None = None) -> SessionResolver:
    source = environ if env is None else env
    if not auth_enabled(source):
        return DisabledSessionResolver()
    redis_url = (source.get(REDIS_URL_ENV) or "").strip()
    if not redis_url:
        raise AuthConfigurationError(
            "REDIS_URL is required when AUTH_ENABLED is not disabled. "
            "Set AUTH_ENABLED=0 only for local development without the shared auth backend."
        )
    from redis import asyncio as redis_asyncio

    client = redis_asyncio.from_url(redis_url, decode_responses=True)
    return RedisSessionResolver(client)


class RequireAuthenticatedUser:
    """FastAPI dependency: resolves the qa_session cookie to a user id, or raises 401.

    Resolver construction is deferred to the first request so importing this module (and
    the module-level `app = create_app()` FastAPI apps build at import time) never touches
    Redis or fails on missing config; only actually calling a protected endpoint does.
    """

    def __init__(self, resolver: SessionResolver | None = None, *, cookie_name: str | None = None) -> None:
        self._resolver = resolver
        self._cookie_name = cookie_name or session_cookie_name()

    def _resolve_resolver(self, request: Request) -> SessionResolver:
        if self._resolver is not None:
            return self._resolver
        cached = getattr(request.app.state, "session_resolver", None)
        if cached is None:
            cached = build_session_resolver_from_env()
            request.app.state.session_resolver = cached
        return cached

    async def __call__(self, request: Request) -> str:
        resolver = self._resolve_resolver(request)
        session_id = request.cookies.get(self._cookie_name)
        user_id = await resolver.resolve_user_id(session_id)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        return user_id
