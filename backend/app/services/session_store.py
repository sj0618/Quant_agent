from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from app.core.config import Settings, redact_secrets
from app.core.errors import AppError
from app.core.runtime_perf import measure_span
from app.core.security import generate_token_urlsafe


@dataclass(frozen=True, slots=True)
class AuthenticatedSessionContext:
    user_id: int
    redis_session_id: str
    scope_family_id: UUID


class AuthSessionStore:
    """Redis-backed OAuth state, session, and CSRF storage.

    Redis failures fail closed.

    Session expiration policy:
    - idle timeout: expires when no authenticated request occurs for a configured period
    - absolute timeout: expires after a fixed period from login regardless of activity
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

    async def store_oauth_state(
        self,
        *,
        state: str,
        nonce: str,
        return_to: str,
        redirect_uri: str | None = None,
        flow_mode: str | None = None,
        transaction_token_hash: str | None = None,
    ) -> None:
        payload = {
            "nonce": nonce,
            "return_to": return_to,
        }

        if redirect_uri is not None:
            payload["redirect_uri"] = redirect_uri

        if flow_mode is not None:
            payload["flow_mode"] = flow_mode

        if transaction_token_hash is not None:
            payload["transaction_token_hash"] = transaction_token_hash

        await self._set_json(
            self.state_key(state),
            payload,
            ttl_seconds=self.settings.auth_state_ttl_seconds,
        )

    async def consume_oauth_state(self, state: str) -> dict[str, Any]:
        key = self.state_key(state)
        payload = await self._get_json(key)

        if payload is None:
            raise AppError(
                status_code=401,
                component="auth",
                code="oauth_state_invalid",
                message="OAuth state is invalid or expired",
            )

        await self._delete(key)
        return payload

    async def create_session(self, *, user_id: str) -> tuple[str, str]:
        session_id = generate_token_urlsafe(32)
        csrf_token = generate_token_urlsafe(32)

        now = int(time.time())
        absolute_expires_at = (
            now + self.settings.auth_session_absolute_ttl_seconds
        )

        initial_session_ttl = min(
            self.settings.auth_session_idle_ttl_seconds,
            self.settings.auth_session_absolute_ttl_seconds,
        )

        initial_csrf_ttl = min(
            self.settings.auth_csrf_ttl_seconds,
            initial_session_ttl,
        )

        session_payload = {
            "user_id": str(user_id),
            "scope_family_id": str(uuid4()),
            "created_at": now,
            "last_seen_at": now,
            "absolute_expires_at": absolute_expires_at,
        }

        await self._set_json(
            self.session_key(session_id),
            session_payload,
            ttl_seconds=initial_session_ttl,
        )

        await self._set_json(
            self.csrf_key(session_id),
            {"csrf_token": csrf_token},
            ttl_seconds=initial_csrf_ttl,
        )

        return session_id, csrf_token

    async def get_session_user_id(
        self,
        session_id: str | None,
    ) -> str | None:
        if not session_id:
            return None

        key = self.session_key(session_id)
        payload = await self._get_json(key)

        if not isinstance(payload, dict):
            return None

        user_id = payload.get("user_id")

        if not user_id:
            await self.revoke_session(session_id)
            return None

        try:
            created_at = int(payload["created_at"])
            last_seen_at = int(payload["last_seen_at"])
            absolute_expires_at = int(payload["absolute_expires_at"])
        except (KeyError, TypeError, ValueError):
            # 기존 단일 TTL 형식의 세션이나 손상된 세션은 안전하게 무효화
            await self.revoke_session(session_id)
            return None

        if (
            created_at <= 0
            or last_seen_at < created_at
            or absolute_expires_at <= created_at
        ):
            await self.revoke_session(session_id)
            return None

        now = int(time.time())

        # 절대 만료: 계속 사용하더라도 로그인 후 최대 시간이 지나면 종료
        if now >= absolute_expires_at:
            await self.revoke_session(session_id)
            return None

        idle_elapsed = max(0, now - last_seen_at)

        # 유휴 만료: 일정 시간 동안 인증 요청이 없었으면 종료
        if idle_elapsed >= self.settings.auth_session_idle_ttl_seconds:
            await self.revoke_session(session_id)
            return None

        # 매 요청마다 Redis를 쓰지 않고 touch interval마다 갱신
        if idle_elapsed >= self.settings.auth_session_touch_interval_seconds:
            absolute_remaining = absolute_expires_at - now

            next_session_ttl = min(
                self.settings.auth_session_idle_ttl_seconds,
                absolute_remaining,
            )

            if next_session_ttl <= 0:
                await self.revoke_session(session_id)
                return None

            payload["last_seen_at"] = now

            await self._set_json(
                key,
                payload,
                ttl_seconds=next_session_ttl,
            )

            # 로그인 세션이 살아 있는데 CSRF key만 먼저 사라지지 않도록
            # CSRF TTL도 함께 갱신한다.
            next_csrf_ttl = min(
                self.settings.auth_csrf_ttl_seconds,
                next_session_ttl,
            )

            await self._expire(
                self.csrf_key(session_id),
                ttl_seconds=next_csrf_ttl,
            )

        return str(user_id)

    async def get_authenticated_session_context(
        self,
        session_id: str | None,
    ) -> AuthenticatedSessionContext | None:
        user_id = await self.get_session_user_id(session_id)
        if user_id is None or session_id is None:
            return None

        payload = await self._get_json(self.session_key(session_id))
        if not isinstance(payload, dict):
            return None

        try:
            parsed_user_id = int(user_id)
            scope_family_id = UUID(str(payload["scope_family_id"]))
        except (KeyError, TypeError, ValueError):
            await self.revoke_session(session_id)
            return None

        return AuthenticatedSessionContext(
            user_id=parsed_user_id,
            redis_session_id=session_id,
            scope_family_id=scope_family_id,
        )

    async def get_csrf_token(
        self,
        session_id: str | None,
    ) -> str | None:
        if not session_id:
            return None

        payload = await self._get_json(self.csrf_key(session_id))

        if not isinstance(payload, dict):
            return None

        token = payload.get("csrf_token")
        return str(token) if token else None

    async def revoke_session(
        self,
        session_id: str | None,
    ) -> None:
        if not session_id:
            return

        await self._delete(
            self.session_key(session_id),
            self.csrf_key(session_id),
        )

    async def _get_json(self, key: str) -> Any | None:
        try:
            with measure_span("redis"):
                raw = await self.redis.get(key)

            if raw is None:
                return None

            with measure_span("session_decode"):
                return json.loads(raw)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="redis",
                code="redis_read_failed",
                message="Redis read failed",
                details={
                    "error": redact_secrets(
                        f"{type(exc).__name__}: {exc}"
                    )
                },
            ) from exc

    async def _set_json(
        self,
        key: str,
        payload: Any,
        *,
        ttl_seconds: int,
    ) -> None:
        try:
            with measure_span("redis"):
                await self.redis.set(
                    key,
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        default=str,
                    ),
                    ex=ttl_seconds,
                )
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="redis",
                code="redis_write_failed",
                message="Redis write failed",
                details={
                    "error": redact_secrets(
                        f"{type(exc).__name__}: {exc}"
                    )
                },
            ) from exc

    async def _expire(
        self,
        key: str,
        *,
        ttl_seconds: int,
    ) -> None:
        try:
            with measure_span("redis"):
                await self.redis.expire(
                    key,
                    max(1, ttl_seconds),
                )
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="redis",
                code="redis_write_failed",
                message="Redis write failed",
                details={
                    "error": redact_secrets(
                        f"{type(exc).__name__}: {exc}"
                    )
                },
            ) from exc

    async def _delete(self, *keys: str) -> None:
        if not keys:
            return

        try:
            with measure_span("redis"):
                await self.redis.delete(*keys)
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="redis",
                code="redis_delete_failed",
                message="Redis delete failed",
                details={
                    "error": redact_secrets(
                        f"{type(exc).__name__}: {exc}"
                    )
                },
            ) from exc
