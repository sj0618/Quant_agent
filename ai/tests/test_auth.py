import asyncio

import pytest
from fastapi.testclient import TestClient

from ai_graph.api import ANALYSIS_JOBS_PATH, create_app
from ai_graph.auth import (
    AuthConfigurationError,
    DisabledSessionResolver,
    RedisSessionResolver,
    build_session_resolver_from_env,
    session_cookie_name,
)
from ai_graph.jobs import InMemoryAnalysisJobStore
from ai_graph.schemas import APIEnvelope, EnvelopeStatus, UserPayload


class StubSessionResolver:
    def __init__(self, sessions: dict[str, str]) -> None:
        self._sessions = sessions

    async def resolve_user_id(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        return self._sessions.get(session_id)


def _ready_envelope(trace_id: str) -> APIEnvelope:
    return APIEnvelope(
        status=EnvelopeStatus.READY,
        trace_id=trace_id,
        user_payload=UserPayload(headline="ready", message="analysis completed", next_actions=[]),
        strategy_spec=None,
        debug_ref=f"debug:{trace_id}",
        retryable=False,
    )


def _client(resolver: StubSessionResolver) -> TestClient:
    return TestClient(
        create_app(
            InMemoryAnalysisJobStore(),
            analysis_runner=lambda query, trace_id: _ready_envelope(trace_id),
            session_resolver=resolver,
        )
    )


def test_create_analysis_job_requires_authentication() -> None:
    client = _client(StubSessionResolver({}))

    response = client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI strategy"})

    assert response.status_code == 401


def test_create_analysis_job_succeeds_with_valid_session_cookie() -> None:
    client = _client(StubSessionResolver({"alice-token": "alice"}))
    client.cookies.set(session_cookie_name(), "alice-token")

    response = client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI strategy"})

    assert response.status_code == 201


def test_analysis_job_detail_is_isolated_per_user() -> None:
    client = _client(StubSessionResolver({"alice-token": "alice", "bob-token": "bob"}))

    client.cookies.set(session_cookie_name(), "alice-token")
    created = client.post(ANALYSIS_JOBS_PATH, json={"query": "RSI strategy"}).json()
    job_id = created["job_id"]

    owner_response = client.get(f"{ANALYSIS_JOBS_PATH}/{job_id}")
    assert owner_response.status_code == 200

    client.cookies.set(session_cookie_name(), "bob-token")
    other_user_response = client.get(f"{ANALYSIS_JOBS_PATH}/{job_id}")
    assert other_user_response.status_code == 404

    client.cookies.delete(session_cookie_name())
    unauthenticated_response = client.get(f"{ANALYSIS_JOBS_PATH}/{job_id}")
    assert unauthenticated_response.status_code == 401


def test_build_session_resolver_from_env_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "0")

    resolver = build_session_resolver_from_env()

    assert isinstance(resolver, DisabledSessionResolver)


def test_build_session_resolver_from_env_requires_redis_url_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(AuthConfigurationError):
        build_session_resolver_from_env()


def test_build_session_resolver_from_env_builds_redis_resolver_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    resolver = build_session_resolver_from_env()

    assert isinstance(resolver, RedisSessionResolver)


def test_redis_session_resolver_reads_backend_session_payload() -> None:
    class FakeRedis:
        async def get(self, key: str) -> str | None:
            assert key == "qa:auth:session:abc123"
            return '{"user_id": "42"}'

    resolver = RedisSessionResolver(FakeRedis())

    assert asyncio.run(resolver.resolve_user_id("abc123")) == "42"


def test_redis_session_resolver_returns_none_for_missing_session() -> None:
    class FakeRedis:
        async def get(self, key: str) -> str | None:
            return None

    resolver = RedisSessionResolver(FakeRedis())

    assert asyncio.run(resolver.resolve_user_id("missing")) is None
