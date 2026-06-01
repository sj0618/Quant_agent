from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import auth
from app.core.errors import register_exception_handlers
from app.core.security import OAUTH_TRANSACTION_COOKIE_NAME, hash_oauth_transaction_token
from app.main import _install_credentialed_cors_middleware
from app.services.google_oauth import GoogleIdentity
from app.services.session_store import AuthSessionStore
from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis

FE_CALLBACK = "https://fe.example.co.kr/auth/google/callback"
FE_ORIGIN = "https://fe.example.co.kr"
API_ORIGIN = "https://api.example.co.kr"


def make_client(settings=None, redis=None, *, install_cors: bool = False):
    settings = settings or valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN)
    app = FastAPI()
    register_exception_handlers(app)
    if install_cors:
        _install_credentialed_cors_middleware(app)
    app.include_router(auth.router)
    app.state.settings = settings
    app.state.redis_client = redis or FakeRedis()
    app.state.db_engine = object()
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    return TestClient(app, base_url=API_ORIGIN), app


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


def test_google_start_json_returns_authorization_url_and_binds_transaction_cookie():
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN, AUTH_ALLOWED_ORIGINS=FE_ORIGIN, AUTH_STATE_TTL_SECONDS=600)
    client, app = make_client(settings)

    response = client.get(
        "/auth/google/start",
        params={"return_to": "/app", "response_mode": "json", "redirect_uri": FE_CALLBACK},
    )

    assert response.status_code == 200
    assert response.cookies.get("qa_session") is None
    cookie_header = response.headers["set-cookie"]
    assert f"{OAUTH_TRANSACTION_COOKIE_NAME}=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Path=/auth/google" in cookie_header
    assert "Max-Age=600" in cookie_header

    body = response.json()
    params = parse_qs(urlsplit(body["authorizationUrl"]).query)
    assert params["redirect_uri"] == [FE_CALLBACK]
    state_key = AuthSessionStore(app.state.redis_client, settings).state_key(params["state"][0])
    payload = json.loads(app.state.redis_client.values[state_key])
    assert payload["nonce"] == params["nonce"][0]
    assert payload["return_to"] == "/app"
    assert payload["redirect_uri"] == FE_CALLBACK
    assert payload["flow_mode"] == "json"
    assert payload["transaction_token_hash"] != response.cookies.get(OAUTH_TRANSACTION_COOKIE_NAME)


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://evil.example/auth/google/callback",
        "https://fe.example.co.kr/wrong/callback",
        "//fe.example.co.kr/auth/google/callback",
    ],
)
def test_google_start_json_rejects_invalid_redirect_uri(redirect_uri: str):
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN, AUTH_ALLOWED_ORIGINS=FE_ORIGIN)
    client, _app = make_client(settings)

    response = client.get(
        "/auth/google/start",
        params={"return_to": "/app", "response_mode": "json", "redirect_uri": redirect_uri},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_redirect_uri"
    assert "qa_session=" not in response.headers.get("set-cookie", "")


def test_google_callback_sets_cookie_and_redirects(monkeypatch):
    client, app = make_client()
    store = AuthSessionStore(app.state.redis_client, app.state.settings)

    async def seed_state():
        await store.store_oauth_state(state="state-1", nonce="nonce-1", return_to="/app")

    asyncio.run(seed_state())

    async def fake_exchange(settings, *, code, redirect_uri=None):
        assert redirect_uri is None
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

    async def fake_exchange(settings, *, code, redirect_uri=None):
        assert redirect_uri is None
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


def test_google_json_callback_returns_session_sets_cookie_and_clears_transaction(monkeypatch):
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN, AUTH_ALLOWED_ORIGINS=FE_ORIGIN)
    client, app = make_client(settings)
    users = {}

    start = client.get(
        "/auth/google/start",
        params={"return_to": "/app", "response_mode": "json", "redirect_uri": FE_CALLBACK},
    )
    state = parse_qs(urlsplit(start.json()["authorizationUrl"]).query)["state"][0]

    async def fake_exchange(settings, *, code, redirect_uri):
        assert code == "code-1"
        assert redirect_uri == FE_CALLBACK
        return {"id_token": "id-token"}

    async def fake_validate(settings, *, id_token, expected_nonce):
        assert expected_nonce
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

    response = client.post(
        "/auth/google/callback",
        headers={"Origin": FE_ORIGIN},
        json={"code": "code-1", "state": state, "redirectUri": FE_CALLBACK},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session": {"user": {"id": "user-1", "name": "User", "email": "user@example.co.kr", "provider": "google", "avatarUrl": None}},
        "returnTo": "/app",
    }
    set_cookie = response.headers["set-cookie"]
    assert "qa_session=" in set_cookie
    assert f"{OAUTH_TRANSACTION_COOKIE_NAME}=" in set_cookie
    assert "Max-Age=0" in set_cookie

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "user@example.co.kr"


def test_google_json_callback_rejects_missing_transaction_cookie_before_exchange(monkeypatch):
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN, AUTH_ALLOWED_ORIGINS=FE_ORIGIN)
    client, app = make_client(settings)
    store = AuthSessionStore(app.state.redis_client, settings)
    called = False

    async def seed_state():
        await store.store_oauth_state(
            state="state-1",
            nonce="nonce-1",
            return_to="/app",
            redirect_uri=FE_CALLBACK,
            flow_mode="json",
            transaction_token_hash=hash_oauth_transaction_token("transaction-token"),
        )

    asyncio.run(seed_state())

    async def fake_exchange(*args, **kwargs):
        nonlocal called
        called = True
        return {"id_token": "id-token"}

    monkeypatch.setattr(auth, "exchange_authorization_code", fake_exchange)
    response = client.post(
        "/auth/google/callback",
        headers={"Origin": FE_ORIGIN},
        json={"code": "code-1", "state": "state-1", "redirectUri": FE_CALLBACK},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "oauth_transaction_invalid"
    assert "qa_session=" not in response.headers.get("set-cookie", "")
    assert called is False


def test_google_json_callback_rejects_transaction_cookie_mismatch_before_exchange(monkeypatch):
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN, AUTH_ALLOWED_ORIGINS=FE_ORIGIN)
    client, app = make_client(settings)
    store = AuthSessionStore(app.state.redis_client, settings)
    called = False

    async def seed_state():
        await store.store_oauth_state(
            state="state-1",
            nonce="nonce-1",
            return_to="/app",
            redirect_uri=FE_CALLBACK,
            flow_mode="json",
            transaction_token_hash=hash_oauth_transaction_token("transaction-token"),
        )

    asyncio.run(seed_state())

    async def fake_exchange(*args, **kwargs):
        nonlocal called
        called = True
        return {"id_token": "id-token"}

    monkeypatch.setattr(auth, "exchange_authorization_code", fake_exchange)
    response = client.post(
        "/auth/google/callback",
        headers={"Origin": FE_ORIGIN},
        cookies={OAUTH_TRANSACTION_COOKIE_NAME: "wrong-token"},
        json={"code": "code-1", "state": "state-1", "redirectUri": FE_CALLBACK},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "oauth_transaction_invalid"
    assert "qa_session=" not in response.headers.get("set-cookie", "")
    assert called is False


def test_google_json_callback_rejects_redirect_uri_mismatch_before_exchange(monkeypatch):
    other_callback = "https://other.example.co.kr/auth/google/callback"
    settings = valid_settings(
        AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN,
        AUTH_ALLOWED_ORIGINS=f"{FE_ORIGIN},https://other.example.co.kr",
    )
    client, app = make_client(settings)
    store = AuthSessionStore(app.state.redis_client, settings)
    called = False

    async def seed_state():
        await store.store_oauth_state(
            state="state-1",
            nonce="nonce-1",
            return_to="/app",
            redirect_uri=FE_CALLBACK,
            flow_mode="json",
            transaction_token_hash=hash_oauth_transaction_token("transaction-token"),
        )

    asyncio.run(seed_state())

    async def fake_exchange(*args, **kwargs):
        nonlocal called
        called = True
        return {"id_token": "id-token"}

    monkeypatch.setattr(auth, "exchange_authorization_code", fake_exchange)
    response = client.post(
        "/auth/google/callback",
        headers={"Origin": FE_ORIGIN},
        cookies={OAUTH_TRANSACTION_COOKIE_NAME: "transaction-token"},
        json={"code": "code-1", "state": "state-1", "redirectUri": other_callback},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "redirect_uri_mismatch"
    assert "qa_session=" not in response.headers.get("set-cookie", "")
    assert called is False


def test_google_json_callback_rejects_disallowed_origin_before_exchange(monkeypatch):
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN, AUTH_ALLOWED_ORIGINS=FE_ORIGIN)
    client, _app = make_client(settings)
    called = False

    async def fake_exchange(*args, **kwargs):
        nonlocal called
        called = True
        return {"id_token": "id-token"}

    monkeypatch.setattr(auth, "exchange_authorization_code", fake_exchange)
    response = client.post(
        "/auth/google/callback",
        headers={"Origin": "https://evil.example"},
        cookies={OAUTH_TRANSACTION_COOKIE_NAME: "transaction-token"},
        json={"code": "code-1", "state": "state-1", "redirectUri": FE_CALLBACK},
    )

    assert response.status_code == 403
    assert called is False


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
    response = client.post("/auth/logout", cookies={"qa_session": session_id}, headers={"Origin": API_ORIGIN})
    assert response.status_code == 204
    assert asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).get_session_user_id(session_id)) is None


def test_logout_requires_csrf_token_when_configured():
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN, AUTH_CSRF_REQUIRED=True)
    client, app = make_client(settings)
    session_id, csrf = asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id="user-1"))

    missing = client.post("/auth/logout", cookies={"qa_session": session_id}, headers={"Origin": API_ORIGIN})
    assert missing.status_code == 403

    ok = client.post(
        "/auth/logout",
        cookies={"qa_session": session_id},
        headers={"Origin": API_ORIGIN, "X-CSRF-Token": csrf},
    )
    assert ok.status_code == 204


def test_csrf_route_returns_token_for_existing_session():
    client, app = make_client()
    session_id, csrf = asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id="user-1"))
    response = client.get("/auth/csrf", cookies={"qa_session": session_id})
    assert response.status_code == 200
    assert response.json() == {"csrfToken": csrf}


def test_auth_cors_preflight_reflects_configured_origin_only():
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN, AUTH_ALLOWED_ORIGINS=FE_ORIGIN)
    client, _app = make_client(settings, install_cors=True)

    allowed = client.options(
        "/auth/google/callback",
        headers={"Origin": FE_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert allowed.status_code == 204
    assert allowed.headers["Access-Control-Allow-Origin"] == FE_ORIGIN
    assert allowed.headers["Access-Control-Allow-Credentials"] == "true"

    disallowed = client.options(
        "/auth/google/callback",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert disallowed.status_code == 204
    assert "Access-Control-Allow-Origin" not in disallowed.headers
