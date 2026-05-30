from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import auth
from app.core.errors import register_exception_handlers
from app.services.google_oauth import GoogleIdentity
from app.services.session_store import AuthSessionStore
from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis


def make_client(settings=None, redis=None):
    settings = settings or valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN="https://api.example.co.kr")
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth.router)
    app.state.settings = settings
    app.state.redis_client = redis or FakeRedis()
    app.state.db_engine = object()
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    return TestClient(app, base_url="https://api.example.co.kr"), app


def test_google_start_redirects_and_stores_state():
    client, app = make_client()
    response = client.get("/auth/google/start?return_to=/app", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert any(key.startswith("qa:auth:state:") for key in app.state.redis_client.values)


def test_google_start_rejects_external_return_to():
    client, _app = make_client()
    response = client.get("/auth/google/start?return_to=https://evil.example", follow_redirects=False)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_return_to"


def test_google_callback_sets_cookie_and_redirects(monkeypatch):
    client, app = make_client()
    store = AuthSessionStore(app.state.redis_client, app.state.settings)

    async def seed_state():
        await store.store_oauth_state(state="state-1", nonce="nonce-1", return_to="/app")

    import asyncio
    asyncio.run(seed_state())

    async def fake_exchange(settings, *, code):
        return {"id_token": "id-token"}

    async def fake_validate(settings, *, id_token, expected_nonce):
        assert expected_nonce == "nonce-1"
        return GoogleIdentity(sub="google-sub", email="user@example.co.kr", email_verified=True, name="User", picture=None)

    async def fake_upsert(engine, identity):
        assert identity.sub == "google-sub"
        return {"id": "user-1", "email": identity.email, "name": identity.name, "auth_provider": "google", "provider_user_id": identity.sub}

    monkeypatch.setattr(auth, "exchange_authorization_code", fake_exchange)
    monkeypatch.setattr(auth, "validate_google_id_token", fake_validate)
    monkeypatch.setattr(auth, "upsert_google_user", fake_upsert)

    response = client.get("/auth/google/callback?code=code-1&state=state-1", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/app"
    assert "qa_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_google_callback_session_supports_follow_up_auth_me(monkeypatch):
    client, app = make_client()
    store = AuthSessionStore(app.state.redis_client, app.state.settings)
    users = {}

    async def seed_state():
        await store.store_oauth_state(state="state-1", nonce="nonce-1", return_to="/app")

    asyncio.run(seed_state())

    async def fake_exchange(settings, *, code):
        return {"id_token": "id-token"}

    async def fake_validate(settings, *, id_token, expected_nonce):
        return GoogleIdentity(sub="google-sub", email="user@example.co.kr", email_verified=True, name="User", picture=None)

    async def fake_upsert(engine, identity):
        users["user-1"] = {"id": "user-1", "email": identity.email, "name": identity.name, "auth_provider": "google", "provider_user_id": identity.sub}
        return users["user-1"]

    async def fake_load(engine, user_id):
        return users.get(user_id)

    monkeypatch.setattr(auth, "exchange_authorization_code", fake_exchange)
    monkeypatch.setattr(auth, "validate_google_id_token", fake_validate)
    monkeypatch.setattr(auth, "upsert_google_user", fake_upsert)
    monkeypatch.setattr(auth, "load_user_by_id", fake_load)

    callback = client.get("/auth/google/callback?code=code-1&state=state-1", follow_redirects=False)
    assert callback.status_code == 303

    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user-1"
    assert response.json()["user"]["email"] == "user@example.co.kr"


def test_auth_me_requires_and_loads_valid_session(monkeypatch):
    client, app = make_client()
    session_id, _csrf = asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id="user-1"))

    async def fake_load(engine, user_id):
        assert user_id == "user-1"
        return {"id": "user-1", "email": "user@example.co.kr", "name": "User", "avatar_url": None}

    monkeypatch.setattr(auth, "load_user_by_id", fake_load)
    missing = client.get("/auth/me")
    assert missing.status_code == 401
    response = client.get("/auth/me", cookies={"qa_session": session_id})
    assert response.status_code == 200
    assert response.json()["user"]["provider"] == "google"
    assert response.json()["user"]["email"] == "user@example.co.kr"


def test_logout_requires_origin_and_revokes_session():
    client, app = make_client()
    session_id, _csrf = asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id="user-1"))
    no_origin = client.post("/auth/logout", cookies={"qa_session": session_id})
    assert no_origin.status_code == 403
    response = client.post("/auth/logout", cookies={"qa_session": session_id}, headers={"Origin": "https://api.example.co.kr"})
    assert response.status_code == 204
    assert asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).get_session_user_id(session_id)) is None


def test_csrf_route_returns_token_for_existing_session():
    client, app = make_client()
    session_id, csrf = asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id="user-1"))
    response = client.get("/auth/csrf", cookies={"qa_session": session_id})
    assert response.status_code == 200
    assert response.json() == {"csrfToken": csrf}
