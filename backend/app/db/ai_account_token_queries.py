"""Queries for the per-account API tokens defined in migration 020.

The raw token never reaches this module: callers hash it first and only the digest is
persisted, so a database dump cannot be replayed as credentials.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import execute_one, fetch_all


async def create_account_token(
    engine: AsyncEngine,
    *,
    token_id: str,
    user_id: int,
    label: str | None,
    token_prefix: str,
    token_hash: str,
    quota_limit: int,
    quota_window_seconds: int,
) -> dict[str, Any]:
    row = await execute_one(
        engine,
        """
        INSERT INTO app.ai_account_token (
            token_id, user_id, label, token_prefix, token_hash,
            quota_limit, quota_window_seconds
        )
        VALUES (
            CAST(:token_id AS uuid), :user_id, :label, :token_prefix, :token_hash,
            :quota_limit, :quota_window_seconds
        )
        RETURNING token_id, label, token_prefix, quota_limit, quota_window_seconds,
                  status, created_at, last_used_at
        """,
        {
            "token_id": token_id,
            "user_id": user_id,
            "label": label,
            "token_prefix": token_prefix,
            "token_hash": token_hash,
            "quota_limit": quota_limit,
            "quota_window_seconds": quota_window_seconds,
        },
    )
    if row is None:  # pragma: no cover - RETURNING always yields a row on success
        raise RuntimeError("account token insert returned no row")
    return row


async def list_account_tokens(engine: AsyncEngine, *, user_id: int) -> list[dict[str, Any]]:
    """List a user's tokens. Deliberately never selects token_hash."""

    return await fetch_all(
        engine,
        """
        SELECT token_id, label, token_prefix, quota_limit, quota_window_seconds,
               status, created_at, revoked_at, last_used_at
        FROM app.ai_account_token
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        """,
        {"user_id": user_id},
    )


async def revoke_account_token(
    engine: AsyncEngine, *, user_id: int, token_id: str
) -> dict[str, Any] | None:
    """Revoke one of the caller's own tokens, returning its digest.

    Ownership is part of the WHERE clause rather than a separate check, so one user
    cannot revoke another's token even if they guess a token_id. The returned digest is
    what the caller needs to evict the AI service's Redis cache entry - without that,
    a revoked token would keep authenticating until the cache TTL expired.

    Returns None when no active token matched, which covers both "not yours" and
    "already revoked"; the route reports the same 404 for either so a caller cannot use
    the response to discover whether someone else's token_id exists.
    """

    return await execute_one(
        engine,
        """
        UPDATE app.ai_account_token
        SET status = 'revoked', revoked_at = now()
        WHERE token_id = CAST(:token_id AS uuid)
          AND user_id = :user_id
          AND status = 'active'
        RETURNING token_id, token_hash
        """,
        {"token_id": token_id, "user_id": user_id},
    )
