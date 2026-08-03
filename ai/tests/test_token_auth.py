import pytest
from fastapi.testclient import TestClient

from ai_graph.api import ANALYSIS_JOBS_PATH, create_app
from ai_graph.jobs import InMemoryAnalysisJobStore
from ai_graph.schemas import APIEnvelope, EnvelopeStatus, UserPayload
from ai_graph.token_auth import (
    AccountTokenQuota,
    CachedAccountTokenResolver,
    ResolvedAccountToken,
    build_account_token_resolver_from_env,
    hash_account_token,
)


class StubSessionResolver:
    def __init__(self, sessions: dict[str, str]) -> None:
        self._sessions = sessions

    async def resolve_user_id(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        return self._sessions.get(session_id)


class StubAccountTokenResolver:
    def __init__(self, tokens: dict[str, ResolvedAccountToken]) -> None:
        self._tokens = tokens
        self.calls = 0

    async def resolve(self, raw_token: str) -> ResolvedAccountToken | None:
        self.calls += 1
        return self._tokens.get(raw_token)


class FakeRedis:
    """Just the operations the quota counter and token cache use."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.counters: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds


class BrokenRedis:
    async def incr(self, key: str) -> int:
        raise RuntimeError("redis is down")

    async def expire(self, key: str, seconds: int) -> None:  # pragma: no cover
        raise RuntimeError("redis is down")

    async def get(self, key: str) -> str | None:
        raise RuntimeError("redis is down")

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        raise RuntimeError("redis is down")


def _ready_envelope(trace_id: str) -> APIEnvelope:
    return APIEnvelope(
        status=EnvelopeStatus.READY,
        trace_id=trace_id,
        user_payload=UserPayload(headline="ready", message="done", next_actions=[]),
        strategy_spec=None,
        debug_ref=f"debug:{trace_id}",
        retryable=False,
    )


def _token(**overrides) -> ResolvedAccountToken:
    defaults = {
        "token_id": "token-1",
        "user_id": "42",
        "quota_limit": 2,
        "quota_window_seconds": 60,
    }
    defaults.update(overrides)
    return ResolvedAccountToken(**defaults)


def _client(
    *,
    sessions: dict[str, str] | None = None,
    tokens: dict[str, ResolvedAccountToken] | None = None,
    redis_client=None,
) -> TestClient:
    quota = AccountTokenQuota(redis_client) if redis_client is not None else None
    return TestClient(
        create_app(
            InMemoryAnalysisJobStore(),
            analysis_runner=lambda query, trace_id: _ready_envelope(trace_id),
            session_resolver=StubSessionResolver(sessions or {}),
            account_token_resolver=StubAccountTokenResolver(tokens or {}),
            account_token_quota=quota,
        )
    )


def _create_job(client: TestClient, **kwargs):
    return client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI 30 이하 종목"}, **kwargs)


def test_a_bearer_token_authenticates_without_a_session_cookie() -> None:
    client = _client(tokens={"secret-token": _token()}, redis_client=FakeRedis())

    response = _create_job(client, headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 201


def test_a_job_created_with_a_token_belongs_to_that_token_s_account() -> None:
    # Attribution is not visible on the response, so it is checked the way it actually
    # matters: the owning account sees the job and another account does not.
    client = _client(
        sessions={"owner-session": "42", "stranger-session": "99"},
        tokens={"secret-token": _token(user_id="42")},
        redis_client=FakeRedis(),
    )
    created = _create_job(
        client, headers={"Authorization": "Bearer secret-token"}
    ).json()

    client.cookies.set("qa_session", "owner-session")
    owner_jobs = client.get(ANALYSIS_JOBS_PATH).json()
    client.cookies.set("qa_session", "stranger-session")
    stranger_jobs = client.get(ANALYSIS_JOBS_PATH).json()

    assert [job["job_id"] for job in owner_jobs] == [created["job_id"]]
    assert stranger_jobs == []


def test_an_unknown_token_is_rejected_rather_than_falling_back_to_the_cookie() -> None:
    # The cookie alone would authenticate, so this proves a revoked token cannot ride a
    # still-live browser session back in.
    client = _client(
        sessions={"session-1": "42"},
        tokens={},
        redis_client=FakeRedis(),
    )
    client.cookies.set("qa_session", "session-1")

    response = _create_job(client, headers={"Authorization": "Bearer revoked-token"})

    assert response.status_code == 401


def test_requests_over_the_token_quota_are_rejected_with_429() -> None:
    redis_client = FakeRedis()
    client = _client(
        tokens={"secret-token": _token(quota_limit=2)}, redis_client=redis_client
    )
    headers = {"Authorization": "Bearer secret-token"}

    assert _create_job(client, headers=headers).status_code == 201
    assert _create_job(client, headers=headers).status_code == 201

    third = _create_job(client, headers=headers)

    assert third.status_code == 429
    assert third.json()["detail"]["code"] == "account_token_quota_exceeded"
    assert third.headers["Retry-After"] == "60"


def test_the_quota_window_is_given_an_expiry_so_the_counter_resets() -> None:
    redis_client = FakeRedis()
    client = _client(
        tokens={"secret-token": _token(quota_window_seconds=30)},
        redis_client=redis_client,
    )

    _create_job(client, headers={"Authorization": "Bearer secret-token"})

    assert list(redis_client.expirations.values()) == [30]


def test_session_cookie_requests_are_not_charged_against_any_quota() -> None:
    redis_client = FakeRedis()
    client = _client(
        sessions={"session-1": "42"},
        tokens={"secret-token": _token(quota_limit=1)},
        redis_client=redis_client,
    )
    client.cookies.set("qa_session", "session-1")

    for _ in range(5):
        assert _create_job(client).status_code == 201

    assert redis_client.counters == {}


def test_reads_do_not_consume_quota_because_they_spend_no_provider_capacity() -> None:
    redis_client = FakeRedis()
    client = _client(
        tokens={"secret-token": _token(quota_limit=1)}, redis_client=redis_client
    )
    headers = {"Authorization": "Bearer secret-token"}
    created = _create_job(client, headers=headers).json()

    for _ in range(5):
        listed = client.get(ANALYSIS_JOBS_PATH, headers=headers)
        assert listed.status_code == 200
        assert client.get(f"{ANALYSIS_JOBS_PATH}/{created['job_id']}", headers=headers).status_code == 200

    assert sum(redis_client.counters.values()) == 1


def test_an_unavailable_quota_counter_does_not_reject_the_request() -> None:
    # Redis being down says nothing about whether the caller is over quota, and the
    # concurrency gate still bounds what reaches the provider.
    client = _client(tokens={"secret-token": _token()}, redis_client=BrokenRedis())

    response = _create_job(client, headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 201


def test_a_malformed_authorization_header_is_treated_as_no_token() -> None:
    client = _client(sessions={"session-1": "42"}, tokens={}, redis_client=FakeRedis())
    client.cookies.set("qa_session", "session-1")

    response = _create_job(client, headers={"Authorization": "Basic abc123"})

    assert response.status_code == 201


@pytest.mark.anyio
async def test_the_cache_keeps_a_hot_token_off_the_database() -> None:
    inner = StubAccountTokenResolver({"secret-token": _token()})
    resolver = CachedAccountTokenResolver(inner, FakeRedis())

    for _ in range(4):
        assert await resolver.resolve("secret-token") is not None

    assert inner.calls == 1


@pytest.mark.anyio
async def test_the_cache_is_keyed_by_digest_so_the_raw_token_is_never_stored() -> None:
    redis_client = FakeRedis()
    resolver = CachedAccountTokenResolver(
        StubAccountTokenResolver({"secret-token": _token()}), redis_client
    )

    await resolver.resolve("secret-token")

    assert f"qa:ai:account_token:{hash_account_token('secret-token')}" in redis_client.values
    assert all("secret-token" not in key for key in redis_client.values)
    assert all("secret-token" not in value for value in redis_client.values.values())


@pytest.mark.anyio
async def test_an_unknown_token_is_negatively_cached_so_a_retry_loop_cannot_hammer_the_db() -> None:
    inner = StubAccountTokenResolver({})
    resolver = CachedAccountTokenResolver(inner, FakeRedis())

    for _ in range(4):
        assert await resolver.resolve("bad-token") is None

    assert inner.calls == 1


@pytest.mark.anyio
async def test_a_broken_cache_falls_through_instead_of_rejecting_a_valid_token() -> None:
    inner = StubAccountTokenResolver({"secret-token": _token()})
    resolver = CachedAccountTokenResolver(inner, BrokenRedis())

    assert await resolver.resolve("secret-token") is not None


def test_the_ai_service_and_backend_agree_on_the_token_digest() -> None:
    from hashlib import sha256

    raw = "qaai_example-token-value"

    assert hash_account_token(raw) == sha256(raw.encode("utf-8")).hexdigest()


def test_tokens_are_unusable_when_the_auth_backend_is_disabled() -> None:
    # AUTH_ENABLED=0 is the local-development shortcut. Accepting tokens there would mean
    # accepting ones nothing had validated.
    assert build_account_token_resolver_from_env({"AUTH_ENABLED": "0"}) is None


def test_tokens_are_unusable_without_a_database_to_validate_them_against() -> None:
    assert build_account_token_resolver_from_env({"AUTH_ENABLED": "1"}) is None
