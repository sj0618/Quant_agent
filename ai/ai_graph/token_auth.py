"""API tokens that identify an account and cap how fast it can consume AOAI capacity.

The browser session cookie was the only way in, which left no way to tell a person
clicking through the workspace apart from a script looping over the same endpoint. Both
arrive as the same authenticated user, so one automation could exhaust the shared Azure
deployment and every other user's analysis would fail behind it.

A token makes that distinguishable and boundable. It is issued per account by the general
backend, presented as `Authorization: Bearer ...`, and carries its own request allowance,
so an automation can be given a small budget without touching interactive use. The quota
attaches to the token rather than the account precisely so those two can differ.

Session-cookie requests keep working untouched and are not quota-checked: throttling the
interactive path would degrade the product for the exact users this is meant to protect.
That leaves scripting against a copied session cookie unbounded - a deliberate gap, since
closing it means rate-limiting real people, and `concurrency_gate` already stops any
caller from actually overwhelming the provider.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from os import environ
from typing import Any, Protocol

from fastapi import HTTPException, Request, status

from ai_graph.auth import REDIS_URL_ENV, RequireAuthenticatedUser, auth_enabled

_logger = logging.getLogger(__name__)


AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "bearer "

# Namespaced like the auth session keys the backend already writes, so both services'
# Redis keys stay recognisably one scheme.
TOKEN_CACHE_KEY_PREFIX = "qa:ai:account_token"
QUOTA_KEY_PREFIX = "qa:ai:account_token_quota"

# Long enough to keep a busy token off the database, short enough that a revocation whose
# cache delete failed still stops working quickly. Revocation does not wait for this: the
# issuing endpoint deletes the cache entry as part of revoking.
TOKEN_CACHE_TTL_SECONDS = 60
# Unknown tokens are cached briefly too, so a caller retrying a bad token in a loop cannot
# turn every attempt into a database round trip.
TOKEN_NEGATIVE_CACHE_TTL_SECONDS = 30
_NEGATIVE_CACHE_SENTINEL = "\x00unknown"


@dataclass(frozen=True)
class ResolvedAccountToken:
    token_id: str
    user_id: str
    quota_limit: int
    quota_window_seconds: int


class AccountTokenResolver(Protocol):
    async def resolve(self, raw_token: str) -> ResolvedAccountToken | None: ...


def hash_account_token(raw_token: str) -> str:
    """Digest a raw token the same way the issuing backend stores it.

    Both services have to agree on this byte-for-byte or no token would ever validate;
    `backend/app/api/routes/ai_account_tokens.py` computes the identical digest.
    """

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def bearer_token_from_request(request: Request) -> str | None:
    raw = request.headers.get(AUTHORIZATION_HEADER)
    if not raw or not raw.lower().startswith(BEARER_PREFIX):
        return None
    token = raw[len(BEARER_PREFIX):].strip()
    return token or None


class PostgresAccountTokenResolver:
    """Looks a token up by digest, rejecting anything not currently active."""

    def __init__(self, dsn: str, *, record_usage: bool = True) -> None:
        self._dsn = dsn
        self._record_usage = record_usage

    async def resolve(self, raw_token: str) -> ResolvedAccountToken | None:
        import psycopg
        from psycopg.rows import dict_row

        token_hash = hash_account_token(raw_token)
        async with await psycopg.AsyncConnection.connect(
            self._dsn, row_factory=dict_row
        ) as conn:
            row = await (
                await conn.execute(
                    """
                    SELECT token_id, user_id, quota_limit, quota_window_seconds
                    FROM app.ai_account_token
                    WHERE token_hash = %s AND status = 'active'
                    """,
                    (token_hash,),
                )
            ).fetchone()
            if row is None:
                return None
            if self._record_usage:
                # Only written on a cache miss, so a hot token costs one write per cache
                # TTL rather than one per request. The read-only identity resolver
                # below disables this bookkeeping until an analysis job is accepted.
                try:
                    await conn.execute(
                        "UPDATE app.ai_account_token SET last_used_at = now() WHERE token_id = %s",
                        (row["token_id"],),
                    )
                except Exception:
                    _logger.warning("failed to record account token usage", exc_info=True)
        return ResolvedAccountToken(
            token_id=str(row["token_id"]),
            user_id=str(row["user_id"]),
            quota_limit=int(row["quota_limit"]),
            quota_window_seconds=int(row["quota_window_seconds"]),
        )


class CachedAccountTokenResolver:
    """Redis read-through cache in front of another resolver.

    Every authenticated request would otherwise open a database connection just to check a
    digest. Cache failures fall through to the wrapped resolver rather than rejecting the
    request: Redis being unavailable is not evidence that a token is invalid.
    """

    def __init__(
        self,
        inner: AccountTokenResolver,
        redis_client: Any,
        *,
        ttl_seconds: int = TOKEN_CACHE_TTL_SECONDS,
        negative_ttl_seconds: int = TOKEN_NEGATIVE_CACHE_TTL_SECONDS,
    ) -> None:
        self._inner = inner
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds
        self._negative_ttl_seconds = negative_ttl_seconds

    async def resolve(self, raw_token: str) -> ResolvedAccountToken | None:
        key = f"{TOKEN_CACHE_KEY_PREFIX}:{hash_account_token(raw_token)}"
        cached = await self._read_cache(key)
        if cached is _NEGATIVE_CACHE_SENTINEL:
            return None
        if isinstance(cached, ResolvedAccountToken):
            return cached
        resolved = await self._inner.resolve(raw_token)
        await self._write_cache(key, resolved)
        return resolved

    async def _read_cache(self, key: str) -> ResolvedAccountToken | str | None:
        try:
            raw = await self._redis.get(key)
        except Exception:
            _logger.warning("account token cache read failed", exc_info=True)
            return None
        if not raw:
            return None
        if raw == _NEGATIVE_CACHE_SENTINEL:
            return _NEGATIVE_CACHE_SENTINEL
        try:
            payload = json.loads(raw)
            return ResolvedAccountToken(
                token_id=str(payload["token_id"]),
                user_id=str(payload["user_id"]),
                quota_limit=int(payload["quota_limit"]),
                quota_window_seconds=int(payload["quota_window_seconds"]),
            )
        except (TypeError, ValueError, KeyError):
            return None

    async def _write_cache(self, key: str, resolved: ResolvedAccountToken | None) -> None:
        if resolved is None:
            value: str = _NEGATIVE_CACHE_SENTINEL
            ttl = self._negative_ttl_seconds
        else:
            value = json.dumps(
                {
                    "token_id": resolved.token_id,
                    "user_id": resolved.user_id,
                    "quota_limit": resolved.quota_limit,
                    "quota_window_seconds": resolved.quota_window_seconds,
                }
            )
            ttl = self._ttl_seconds
        try:
            await self._redis.set(key, value, ex=ttl)
        except Exception:
            _logger.warning("account token cache write failed", exc_info=True)


class AccountTokenQuota:
    """Fixed-window request counter per token, held in Redis.

    A fixed window can let a caller spend two windows' worth across a boundary. That is
    accepted: this exists to stop a runaway loop, not to meter billing, and a fixed window
    costs one INCR where a sliding one costs a sorted set per token.
    """

    def __init__(self, redis_client: Any, *, key_prefix: str = QUOTA_KEY_PREFIX) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix

    async def check_and_consume(
        self,
        token: ResolvedAccountToken,
        *,
        idempotency_key: str | None = None,
    ) -> None:
        window = max(token.quota_window_seconds, 1)
        bucket = int(time.time() // window)
        quota_key = f"{self._key_prefix}:{token.token_id}:{bucket}"
        try:
            if idempotency_key:
                used = await self._consume_once_per_idempotency_key(
                    token=token,
                    idempotency_key=idempotency_key,
                    quota_key=quota_key,
                    window=window,
                )
            else:
                used = await self._redis.incr(quota_key)
                if used == 1:
                    await self._redis.expire(quota_key, window)
        except Exception:
            # Redis is unavailable, so the counter is unknown. Letting the request through
            # keeps an infrastructure blip from looking like a quota rejection; the
            # concurrency gate still bounds what reaches the provider.
            _logger.warning("account token quota check failed; allowing request", exc_info=True)
            return
        if used > token.quota_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "account_token_quota_exceeded",
                    "message": (
                        "이 토큰의 요청 한도를 초과했습니다. "
                        f"{window}초당 {token.quota_limit}회까지 요청할 수 있습니다."
                    ),
                    "quota_limit": token.quota_limit,
                    "quota_window_seconds": window,
                },
                headers={"Retry-After": str(window)},
            )

    async def _consume_once_per_idempotency_key(
        self,
        *,
        token: ResolvedAccountToken,
        idempotency_key: str,
        quota_key: str,
        window: int,
    ) -> int:
        """Atomically reserve one bearer-token quota unit for an admitted retry key.

        The durable job admission owns the definitive idempotency ledger, but quota is
        intentionally checked before a new Job may reach a provider.  A plain GET/SET
        check would race across two API processes: both could see no job and increment
        the counter.  Redis executes this small Lua transaction serially, so one client
        idempotency key consumes at most one unit in its fixed window without storing
        the raw key in Redis.
        """

        fingerprint = hashlib.sha256(
            f"{token.token_id}\x00{token.user_id}\x00{idempotency_key}".encode("utf-8")
        ).hexdigest()
        reservation_key = f"{self._key_prefix}:admission:{fingerprint}"
        result = await self._redis.eval(
            """
            if redis.call('GET', KEYS[2]) then
                return {0, 0}
            end
            local used = redis.call('INCR', KEYS[1])
            if used == 1 then
                redis.call('EXPIRE', KEYS[1], ARGV[1])
            end
            if used > tonumber(ARGV[2]) then
                return {2, used}
            end
            redis.call('SET', KEYS[2], '1', 'EX', ARGV[1], 'NX')
            return {1, used}
            """,
            2,
            quota_key,
            reservation_key,
            window,
            token.quota_limit,
        )
        decision, used = (int(value) for value in result)
        if decision == 0:
            # A concurrent process has already reserved this exact request.  It may
            # now return the durable job without recharging quota.
            return 0
        return used


class RequireUserIdentity:
    """Resolves the caller to a user id from either a bearer token or the session cookie.

    Tried in that order so a request that bothered to present a token is judged as that
    token - including its quota - even when a session cookie happens to ride along.
    Returns the same `user_id` string shape as the session-only dependency it replaces, so
    route bodies are unaffected.
    """

    def __init__(
        self,
        *,
        session_requirement: RequireAuthenticatedUser,
        token_resolver: AccountTokenResolver | None = None,
    ) -> None:
        self._session_requirement = session_requirement
        self._token_resolver = token_resolver

    async def __call__(self, request: Request) -> str:
        token = await self.resolve_token(request)
        if token is not None:
            return token.user_id
        return await self._session_requirement(request)

    async def resolve_token(self, request: Request) -> ResolvedAccountToken | None:
        """Resolve and stash the bearer token, or 401 when one was presented but is invalid."""

        raw_token = bearer_token_from_request(request)
        if raw_token is None:
            return None
        resolver = self._resolve_resolver(request)
        resolved = None if resolver is None else await resolver.resolve(raw_token)
        if resolved is None:
            # A presented-but-unusable token is an explicit failure rather than a silent
            # fallback to the cookie: quietly downgrading would let a revoked token keep
            # working for anyone who still had a live browser session.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API token",
            )
        request.state.resolved_account_token = resolved
        return resolved

    def _resolve_resolver(self, request: Request) -> AccountTokenResolver | None:
        if self._token_resolver is not None:
            return self._token_resolver
        cached = getattr(request.app.state, "account_token_resolver", None)
        if cached is None:
            cached = build_account_token_resolver_from_env()
            request.app.state.account_token_resolver = cached
        return cached


class RequireUserIdentityWithinQuota:
    """Identity plus quota, as one dependency so the two cannot run out of order.

    Splitting these into sibling `Depends(...)` entries would leave the quota check
    reading a `request.state` field that FastAPI does not promise to have populated yet.
    """

    def __init__(
        self,
        identity: RequireUserIdentity,
        *,
        quota: AccountTokenQuota | None = None,
    ) -> None:
        self._identity = identity
        self._quota = quota

    async def __call__(self, request: Request) -> str:
        token = await self._identity.resolve_token(request)
        if token is None:
            return await self._identity(request)
        quota = self._resolve_quota(request)
        if quota is not None:
            await quota.check_and_consume(token)
        return token.user_id

    def _resolve_quota(self, request: Request) -> AccountTokenQuota | None:
        if self._quota is not None:
            return self._quota
        cached = getattr(request.app.state, "account_token_quota", None)
        if cached is None:
            cached = build_account_token_quota_from_env()
            request.app.state.account_token_quota = cached
        return cached


class RequireAuthenticatedIdentityReadOnly:
    """Authenticate a request without token-usage, cache, or quota mutation.

    The protected analysis routes call :meth:`consume_quota_after_admission` only after
    they create or find a durable job. A malformed or unavailable request therefore
    cannot spend an account token allowance or trigger normal resolver bookkeeping.
    """

    def __init__(
        self,
        *,
        session_requirement: RequireAuthenticatedUser,
        token_resolver: AccountTokenResolver | None = None,
        quota: AccountTokenQuota | None = None,
    ) -> None:
        self._session_requirement = session_requirement
        self._token_resolver = token_resolver
        self._quota = quota

    async def __call__(self, request: Request) -> str:
        raw_token = bearer_token_from_request(request)
        if raw_token is None:
            return await self._session_requirement(request)
        resolver = self._resolve_resolver(request)
        resolved = None if resolver is None else await resolver.resolve(raw_token)
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API token",
            )
        # Request-local state is not persisted and lets the route charge only accepted
        # bearer requests after durable admission.
        request.state.authenticated_account_token = resolved
        return resolved.user_id

    async def consume_quota_after_admission(
        self,
        request: Request,
        *,
        idempotency_key: str | None = None,
    ) -> None:
        token = getattr(request.state, "authenticated_account_token", None)
        if not isinstance(token, ResolvedAccountToken):
            return
        quota = self._resolve_quota(request)
        if quota is not None:
            await quota.check_and_consume(token, idempotency_key=idempotency_key)

    def _resolve_resolver(self, request: Request) -> AccountTokenResolver | None:
        if self._token_resolver is not None:
            return self._token_resolver
        cached = getattr(request.app.state, "read_only_account_token_resolver", None)
        if cached is None:
            cached = build_read_only_account_token_resolver_from_env()
            request.app.state.read_only_account_token_resolver = cached
        return cached

    def _resolve_quota(self, request: Request) -> AccountTokenQuota | None:
        if self._quota is not None:
            return self._quota
        cached = getattr(request.app.state, "account_token_quota", None)
        if cached is None:
            cached = build_account_token_quota_from_env()
            request.app.state.account_token_quota = cached
        return cached


def _redis_client_from_env(env: Mapping[str, str] | None = None) -> Any | None:
    source = environ if env is None else env
    redis_url = (source.get(REDIS_URL_ENV) or "").strip()
    if not redis_url:
        return None
    from redis import asyncio as redis_asyncio

    return redis_asyncio.from_url(redis_url, decode_responses=True)


def build_account_token_resolver_from_env(
    env: Mapping[str, str] | None = None,
) -> AccountTokenResolver | None:
    """Build the token resolver, or None when tokens cannot be validated here.

    Returning None makes `RequireUserIdentity` reject any presented token rather than
    accept one it could not check - the safe direction when the database or auth backend
    is missing, as it is in local development with `AUTH_ENABLED=0`.
    """

    source = environ if env is None else env
    if not auth_enabled(source):
        return None
    from ai_graph.data_sources.db import resolve_database_dsn_from_env

    dsn, _ = resolve_database_dsn_from_env(source)
    if not dsn:
        return None
    resolver: AccountTokenResolver = PostgresAccountTokenResolver(dsn)
    redis_client = _redis_client_from_env(source)
    if redis_client is not None:
        resolver = CachedAccountTokenResolver(resolver, redis_client)
    return resolver


def build_read_only_account_token_resolver_from_env(
    env: Mapping[str, str] | None = None,
) -> AccountTokenResolver | None:
    """Build the read-only token resolver without cache or token-usage writes."""

    source = environ if env is None else env
    if not auth_enabled(source):
        return None
    from ai_graph.data_sources.db import resolve_database_dsn_from_env

    dsn, _ = resolve_database_dsn_from_env(source)
    if not dsn:
        return None
    return PostgresAccountTokenResolver(dsn, record_usage=False)


def build_account_token_quota_from_env(
    env: Mapping[str, str] | None = None,
) -> AccountTokenQuota | None:
    redis_client = _redis_client_from_env(env)
    if redis_client is None:
        return None
    return AccountTokenQuota(redis_client)
