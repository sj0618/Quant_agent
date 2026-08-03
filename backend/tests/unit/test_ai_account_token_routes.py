from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256

from app.api.routes import ai_account_tokens
from app.core.errors import register_exception_handlers
from app.services.session_store import AuthSessionStore
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis

API_ORIGIN = "https://api.example.co.kr"
TOKENS_PATH = "/api/v1/ai/account-tokens"


class FakeTokenStore:
    """Stands in for app.ai_account_token, recording exactly what the routes persist."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def create(self, **kwargs) -> dict:
        row = {
            **kwargs,
            "status": "active",
            "created_at": datetime.now(UTC),
            "revoked_at": None,
            "last_used_at": None,
        }
        self.rows.append(row)
        return row

    def for_user(self, user_id: int) -> list[dict]:
        return [row for row in self.rows if row["user_id"] == user_id]

    def revoke(self, user_id: int, token_id: str) -> dict | None:
        for row in self.rows:
            if (
                row["token_id"] == token_id
                and row["user_id"] == user_id
                and row["status"] == "active"
            ):
                row["status"] = "revoked"
                row["revoked_at"] = datetime.now(UTC)
                return {"token_id": row["token_id"], "token_hash": row["token_hash"]}
        return None


def make_client(monkeypatch, *, redis=None):
    store = FakeTokenStore()
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN)

    async def fake_create(engine, **kwargs):
        return store.create(**kwargs)

    async def fake_list(engine, *, user_id):
        return store.for_user(user_id)

    async def fake_revoke(engine, *, user_id, token_id):
        return store.revoke(user_id, token_id)

    monkeypatch.setattr(ai_account_tokens, "create_account_token", fake_create)
    monkeypatch.setattr(ai_account_tokens, "list_account_tokens", fake_list)
    monkeypatch.setattr(ai_account_tokens, "revoke_account_token", fake_revoke)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(ai_account_tokens.router)
    app.state.settings = settings
    app.state.redis_client = redis or FakeRedis()
    app.state.db_engine = object()
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    return TestClient(app, base_url=API_ORIGIN), app, store, settings


def sign_in(client, app, settings, user_id: str = "42") -> None:
    """Put a live session cookie on the client, replacing whoever was signed in."""

    session_id, _csrf = asyncio.run(
        AuthSessionStore(app.state.redis_client, settings).create_session(user_id=user_id)
    )
    client.cookies.set(settings.auth_session_cookie_name, session_id)


def test_issue_returns_the_raw_token_exactly_once_and_stores_only_its_digest(monkeypatch):
    client, app, store, settings = make_client(monkeypatch)
    sign_in(client, app, settings)

    response = client.post(TOKENS_PATH, json={"label": "my automation"})

    assert response.status_code == 201
    raw_token = response.json()["raw_token"]
    assert raw_token.startswith("qaai_")
    # The stored row must never let anyone reconstruct the credential.
    stored = store.rows[0]
    assert stored["token_hash"] == sha256(raw_token.encode("utf-8")).hexdigest()
    assert raw_token not in stored.values()
    assert stored["token_prefix"] == raw_token[:12]

    listed = client.get(TOKENS_PATH).json()["tokens"]
    assert len(listed) == 1
    assert "raw_token" not in listed[0]
    assert "token_hash" not in listed[0]


def test_unauthenticated_issuance_is_rejected(monkeypatch):
    client, _app, store, _settings = make_client(monkeypatch)

    response = client.post(TOKENS_PATH, json={})

    assert response.status_code == 401
    assert store.rows == []


def test_the_caller_cannot_choose_its_own_quota(monkeypatch):
    client, app, store, settings = make_client(monkeypatch)
    sign_in(client, app, settings)

    response = client.post(TOKENS_PATH, json={"label": "x", "quota_limit": 1_000_000})

    # A self-chosen allowance would defeat the point of having one, so the field is not
    # part of the request contract at all.
    assert response.status_code == 422
    assert store.rows == []


def test_issued_quota_comes_from_configuration(monkeypatch):
    client, app, _store, settings = make_client(monkeypatch)
    sign_in(client, app, settings)

    body = client.post(TOKENS_PATH, json={}).json()

    assert body["quota_limit"] == settings.ai_account_token_default_quota_limit
    assert (
        body["quota_window_seconds"]
        == settings.ai_account_token_default_quota_window_seconds
    )


def test_two_tokens_for_one_account_are_independent_rows(monkeypatch):
    client, app, store, settings = make_client(monkeypatch)
    sign_in(client, app, settings)

    first = client.post(TOKENS_PATH, json={}).json()
    second = client.post(TOKENS_PATH, json={}).json()

    assert first["token_id"] != second["token_id"]
    assert first["raw_token"] != second["raw_token"]
    assert len(store.rows) == 2


def test_revoking_evicts_the_ai_service_cache_so_it_stops_working_immediately(monkeypatch):
    redis = FakeRedis()
    client, app, store, settings = make_client(monkeypatch, redis=redis)
    sign_in(client, app, settings)
    issued = client.post(TOKENS_PATH, json={}).json()
    token_hash = store.rows[0]["token_hash"]
    # Simulate the AI service having cached this token as valid.
    asyncio.run(redis.set(f"qa:ai:account_token:{token_hash}", "cached", ex=60))

    response = client.post(f"{TOKENS_PATH}/{issued['token_id']}/revoke")

    assert response.status_code == 204
    assert store.rows[0]["status"] == "revoked"
    assert f"qa:ai:account_token:{token_hash}" not in redis.values


def test_one_account_cannot_revoke_another_accounts_token(monkeypatch):
    client, app, store, settings = make_client(monkeypatch)
    sign_in(client, app, settings, "42")
    issued = client.post(TOKENS_PATH, json={}).json()

    sign_in(client, app, settings, "99")
    response = client.post(f"{TOKENS_PATH}/{issued['token_id']}/revoke")

    assert response.status_code == 404
    assert store.rows[0]["status"] == "active"


def test_revoking_an_already_revoked_token_reports_not_found(monkeypatch):
    client, app, _store, settings = make_client(monkeypatch)
    sign_in(client, app, settings)
    issued = client.post(TOKENS_PATH, json={}).json()
    path = f"{TOKENS_PATH}/{issued['token_id']}/revoke"

    assert client.post(path).status_code == 204
    assert client.post(path).status_code == 404


def test_listing_only_shows_the_callers_own_tokens(monkeypatch):
    client, app, store, settings = make_client(monkeypatch)
    sign_in(client, app, settings, "42")
    client.post(TOKENS_PATH, json={})
    sign_in(client, app, settings, "99")
    client.post(TOKENS_PATH, json={})

    listed = client.get(TOKENS_PATH).json()["tokens"]

    assert len(store.rows) == 2
    assert len(listed) == 1


def test_routes_live_under_the_prefix_the_frontend_proxy_forwards():
    # Only /api/v1 and /ai-api are proxied to the backend, so a router mounted elsewhere
    # would be registered but unreachable from a browser.
    for route in ai_account_tokens.router.routes:
        assert route.path.startswith("/api/v1/")
