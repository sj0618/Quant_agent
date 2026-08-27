"""Disposable Redis proof for concurrent bearer quota idempotency.

Set ``AI_QUOTA_REDIS_TEST_URL`` only to an isolated Redis DB.  The test uses a unique
prefix and deletes only the keys it created; it never flushes a shared database.
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from ai_graph.token_auth import AccountTokenQuota, ResolvedAccountToken


REDIS_TEST_URL_ENV = "AI_QUOTA_REDIS_TEST_URL"
_REDIS_URL = os.getenv(REDIS_TEST_URL_ENV)

pytestmark = pytest.mark.skipif(
    not _REDIS_URL,
    reason=f"{REDIS_TEST_URL_ENV} is required for disposable Redis integration tests",
)


def test_redis_lua_reservation_charges_concurrent_idempotent_requests_once() -> None:
    assert _REDIS_URL is not None
    prefix = f"quantagent:quota-integration:{uuid4().hex}"
    token = ResolvedAccountToken(
        token_id="integration-token",
        user_id="integration-user",
        quota_limit=1,
        quota_window_seconds=60,
    )

    async def scenario() -> list[tuple[bytes, bytes | None]]:
        redis = Redis.from_url(_REDIS_URL, decode_responses=False)
        quota = AccountTokenQuota(redis, key_prefix=prefix)
        try:
            await asyncio.gather(
                quota.check_and_consume(token, idempotency_key="same-client-request"),
                quota.check_and_consume(token, idempotency_key="same-client-request"),
            )
            counter_keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
            return [(key, await redis.get(key)) for key in counter_keys]
        finally:
            keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
            if keys:
                await redis.delete(*keys)
            await redis.aclose()

    created_records = asyncio.run(scenario())
    created_keys = [key for key, _value in created_records]
    counter_values = [
        int(value)
        for key, value in created_records
        if b":admission:" not in key and value is not None
    ]

    # Two keys exist (window counter + hashed reservation), but the quota counter is
    # one; no key contains the raw client idempotency string.
    assert counter_values == [1]
    assert all(b"same-client-request" not in key for key in created_keys)
