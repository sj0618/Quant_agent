from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings, redact_secrets
from app.core.errors import AppError
from app.core.security import generate_token_urlsafe


class AuthSessionStore:
    """Redis-backed OAuth state, session, and CSRF storage.

    This class intentionally has no in-memory fallback. Redis failures become
    AppError responses so production auth fails closed.
    """

    def __init__(self, redis_client: Any, settings: Settings):
        if redis_client is None:
            raise AppError(
                status_code=503,
                component="redis",
                code="redis_client_unavailable",
                message="Redis client is required for authentication",
            )
        self.redis = redis_client
        self.settings = settings
        self.prefix = "qa:auth"

    def state_key(self, state: str) -> str:
        return f"{self.prefix}:state:{state}"

    def session_key(self, session_id: str) -> str:
        return f"{self.prefix}:session:{session_id}"

    def csrf_key(self, session_id: str) -> str:
        return f"{self.prefix}:csrf:{session_id}"

    async def store_oauth_state(self, *, state: str, nonce: str, return_to: str) -> None:
        payload = {"nonce": nonce, "return_to": return_to}
        await self._set_json(self.state_key(state), payload, ttl_seconds=self.settings.auth_state_ttl_seconds)

    async def consume_oauth_state(self, state: str) -> dict[str, Any]:
        key = self.state_key(state)
        payload = await self._get_json(key)
        if payload is None:
            raise AppError(status_code=401, component="auth", code="oauth_state_invalid", message="OAuth state is invalid or expired")
        await self._delete(key)
        return payload

    async def create_session(self, *, user_id: str) -> tuple[str, str]:
        session_id = generate_token_urlsafe(32)
        csrf_token = generate_token_urlsafe(32)
        await self._set_json(
            self.session_key(session_id),
            {"user_id": str(user_id)},
            ttl_seconds=self.settings.auth_session_ttl_seconds,
        )
        await self._set_json(
            self.csrf_key(session_id),
            {"csrf_token": csrf_token},
            ttl_seconds=self.settings.auth_csrf_ttl_seconds,
        )
        return session_id, csrf_token

    async def get_session_user_id(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        payload = await self._get_json(self.session_key(session_id))
        if not payload:
            return None
        user_id = payload.get("user_id")
        return str(user_id) if user_id else None

    async def get_csrf_token(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        payload = await self._get_json(self.csrf_key(session_id))
        if not payload:
            return None
        token = payload.get("csrf_token")
        return str(token) if token else None

    async def revoke_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        await self._delete(self.session_key(session_id), self.csrf_key(session_id))

    async def _get_json(self, key: str) -> Any | None:
        try:
            raw = await self.redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="redis",
                code="redis_read_failed",
                message="Redis read failed",
                details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
            ) from exc

    async def _set_json(self, key: str, payload: Any, *, ttl_seconds: int) -> None:
        try:
            await self.redis.set(key, json.dumps(payload, ensure_ascii=False, default=str), ex=ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="redis",
                code="redis_write_failed",
                message="Redis write failed",
                details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
            ) from exc

    async def _delete(self, *keys: str) -> None:
        if not keys:
            return
        try:
            await self.redis.delete(*keys)
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="redis",
                code="redis_delete_failed",
                message="Redis delete failed",
                details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
            ) from exc
