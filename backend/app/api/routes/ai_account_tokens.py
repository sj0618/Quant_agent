"""Self-serve issuance of the per-account API tokens the AI service authenticates with.

Minting a token proves nothing about the caller beyond their browser session, which is
exactly the intent: a signed-in user may create credentials for their own account and no
other. The raw secret is returned once and never stored, so this endpoint is the only
moment it exists outside the caller's hands.

The AI service validates these independently by digest (`ai/ai_graph/token_auth.py`);
neither service calls the other, they only agree on the table and the hash.
"""

from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.errors import AppError
from app.core.security import generate_token_urlsafe
from app.db.ai_account_token_queries import (
    create_account_token,
    list_account_tokens,
    revoke_account_token,
)
from app.dependencies import get_db_engine, get_redis_client, get_runtime_settings
from app.schemas.ai_account_token import (
    AccountTokenSummary,
    IssueAccountTokenRequest,
    IssueAccountTokenResponse,
    ListAccountTokensResponse,
)
from app.services.session_store import AuthSessionStore

# Reachable only under /api/v1: the FE dev server and the deployed reverse proxy forward
# that prefix and /ai-api, so a router mounted anywhere else would be unroutable from a
# browser even though the app registers it.
router = APIRouter(prefix="/api/v1/ai/account-tokens", tags=["ai-account-tokens"])

# Identifies a QuantAgent AI token at a glance in logs and config files, the way provider
# API keys are conventionally prefixed.
TOKEN_VALUE_PREFIX = "qaai_"
# Enough to tell two tokens apart in a list without materially narrowing the secret.
TOKEN_DISPLAY_PREFIX_LENGTH = 12

# Must match `hash_account_token` in ai/ai_graph/token_auth.py. A plain digest is right
# here: the secret is 32 random bytes, so it is not guessable at any hash speed, and this
# runs on every authenticated AI request where a slow KDF would cost real latency.
def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def _authenticated_user_id(request: Request) -> int:
    settings = get_runtime_settings(request)
    store = AuthSessionStore(get_redis_client(request), settings)
    session_id = request.cookies.get(settings.auth_session_cookie_name)
    user_id = await store.get_session_user_id(session_id)
    if not user_id:
        raise AppError(
            status_code=401,
            component="ai_account_token",
            code="not_authenticated",
            message="Authentication required",
        )
    try:
        return int(user_id)
    except ValueError as exc:
        raise AppError(
            status_code=401,
            component="ai_account_token",
            code="invalid_session_user_id",
            message="Session user id is invalid",
        ) from exc


@router.post("", response_model=IssueAccountTokenResponse, status_code=status.HTTP_201_CREATED)
async def issue_account_token(
    request: Request,
    payload: IssueAccountTokenRequest,
    user_id: int = Depends(_authenticated_user_id),
) -> IssueAccountTokenResponse:
    settings = get_runtime_settings(request)
    raw_token = f"{TOKEN_VALUE_PREFIX}{generate_token_urlsafe(32)}"
    row = await create_account_token(
        get_db_engine(request),
        token_id=str(uuid4()),
        user_id=user_id,
        label=payload.label,
        token_prefix=raw_token[:TOKEN_DISPLAY_PREFIX_LENGTH],
        token_hash=_hash_token(raw_token),
        quota_limit=settings.ai_account_token_default_quota_limit,
        quota_window_seconds=settings.ai_account_token_default_quota_window_seconds,
    )
    return IssueAccountTokenResponse(
        token_id=str(row["token_id"]),
        raw_token=raw_token,
        token_prefix=row["token_prefix"],
        label=row["label"],
        quota_limit=row["quota_limit"],
        quota_window_seconds=row["quota_window_seconds"],
        created_at=row["created_at"],
    )


@router.get("", response_model=ListAccountTokensResponse)
async def list_my_account_tokens(
    request: Request,
    user_id: int = Depends(_authenticated_user_id),
) -> ListAccountTokensResponse:
    rows = await list_account_tokens(get_db_engine(request), user_id=user_id)
    return ListAccountTokensResponse(
        tokens=[
            AccountTokenSummary(
                token_id=str(row["token_id"]),
                label=row["label"],
                token_prefix=row["token_prefix"],
                quota_limit=row["quota_limit"],
                quota_window_seconds=row["quota_window_seconds"],
                status=row["status"],
                created_at=row["created_at"],
                revoked_at=row["revoked_at"],
                last_used_at=row["last_used_at"],
            )
            for row in rows
        ]
    )


@router.post("/{token_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_account_token(
    request: Request,
    token_id: str,
    user_id: int = Depends(_authenticated_user_id),
) -> Response:
    row = await revoke_account_token(
        get_db_engine(request), user_id=user_id, token_id=token_id
    )
    if row is None:
        raise AppError(
            status_code=404,
            component="ai_account_token",
            code="account_token_not_found",
            message="Active API token not found",
        )
    # The AI service caches token lookups, so the database row alone does not stop it.
    # Dropping the cache entry here is what makes revocation take effect immediately
    # rather than whenever the entry happened to expire.
    try:
        await get_redis_client(request).delete(
            f"qa:ai:account_token:{row['token_hash']}"
        )
    except Exception as exc:
        # The row is already revoked, so this is reported rather than swallowed: the
        # caller needs to know the token keeps working until the short cache TTL lapses.
        # Retrying the revoke will return 404 (nothing active left to revoke), which is
        # why the message says what actually happened instead of implying it failed.
        raise AppError(
            status_code=503,
            component="ai_account_token",
            code="account_token_cache_evict_failed",
            message="Token was revoked but may remain usable briefly",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
