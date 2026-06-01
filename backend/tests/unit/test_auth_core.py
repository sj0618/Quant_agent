from __future__ import annotations

import json
from time import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import Response

from app.core.errors import AppError, register_exception_handlers
from app.core.security import (
    OAUTH_TRANSACTION_COOKIE_NAME,
    clear_session_cookie,
    clear_oauth_transaction_cookie,
    csrf_token_required,
    hash_oauth_transaction_token,
    oauth_transaction_token_matches,
    sanitize_return_to,
    set_session_cookie,
    set_oauth_transaction_cookie,
    validate_oauth_redirect_uri,
    validate_unsafe_request_origin,
)
from app.services.google_oauth import build_google_authorization_url, validate_google_claims
from app.services.session_store import AuthSessionStore
from tests.unit.test_auth_config import valid_settings


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.ttls[key] = ex

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.ttls.pop(key, None)


class FailingRedis(FakeRedis):
    async def get(self, key):
        raise RuntimeError("redis password=super-secret failed")


@pytest.mark.parametrize(
    "value",
    ["https://evil.example/app", "//evil.example/app", "%2F%2Fevil.example/app", "/../admin", "/app\\evil"],
)
def test_sanitize_return_to_rejects_external_and_traversal(value: str):
    with pytest.raises(AppError):
        sanitize_return_to(value)


def test_sanitize_return_to_allows_local_path_and_default():
    assert sanitize_return_to(None) == "/app"
    assert sanitize_return_to("/app?tab=profile") == "/app?tab=profile"


def test_validate_oauth_redirect_uri_accepts_configured_backend_and_fe_origin():
    settings = valid_settings(AUTH_ALLOWED_ORIGINS="https://fe.example.co.kr")
    assert validate_oauth_redirect_uri(settings.google_redirect_uri, settings) == settings.google_redirect_uri
    assert (
        validate_oauth_redirect_uri("https://fe.example.co.kr/auth/google/callback", settings)
        == "https://fe.example.co.kr/auth/google/callback"
    )


def test_validate_oauth_redirect_uri_accepts_localhost_http_in_local_env():
    settings = valid_settings(
        APP_ENV="local",
        GOOGLE_REDIRECT_URI="http://localhost:8000/auth/google/callback",
        AUTH_ALLOWED_ORIGINS="http://localhost:5173",
    )
    assert (
        validate_oauth_redirect_uri("http://localhost:5173/auth/google/callback", settings)
        == "http://localhost:5173/auth/google/callback"
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example/auth/google/callback",
        "https://fe.example.co.kr/wrong/callback",
        "https://fe.example.co.kr/auth/google/callback?next=/app",
        "https://fe.example.co.kr/auth/google/callback#fragment",
        "https://user:pass@fe.example.co.kr/auth/google/callback",
        "javascript:alert(1)",
        "//fe.example.co.kr/auth/google/callback",
    ],
)
def test_validate_oauth_redirect_uri_rejects_untrusted_or_malformed_values(value: str):
    settings = valid_settings(AUTH_ALLOWED_ORIGINS="https://fe.example.co.kr")
    with pytest.raises(AppError) as exc:
        validate_oauth_redirect_uri(value, settings)
    assert exc.value.code == "invalid_redirect_uri"


def test_cookie_helpers_set_and_clear_secure_httponly_cookie():
    settings = valid_settings(AUTH_SESSION_COOKIE_NAME="qa_session", AUTH_COOKIE_SAMESITE="lax")
    response = Response()
    set_session_cookie(response, settings, "session-id")
    header = response.headers["set-cookie"]
    assert "qa_session=session-id" in header
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header

    response = Response()
    clear_session_cookie(response, settings)
    clear_header = response.headers["set-cookie"]
    assert "qa_session=" in clear_header
    assert "Max-Age=0" in clear_header


def test_oauth_transaction_cookie_helpers_set_short_lived_httponly_cookie():
    settings = valid_settings(AUTH_STATE_TTL_SECONDS=300)
    response = Response()
    set_oauth_transaction_cookie(response, settings, "transaction-token")
    header = response.headers["set-cookie"]
    assert f"{OAUTH_TRANSACTION_COOKIE_NAME}=transaction-token" in header
    assert "HttpOnly" in header
    assert "Path=/auth/google" in header
    assert "Max-Age=300" in header

    response = Response()
    clear_oauth_transaction_cookie(response, settings)
    clear_header = response.headers["set-cookie"]
    assert f"{OAUTH_TRANSACTION_COOKIE_NAME}=" in clear_header
    assert "Max-Age=0" in clear_header
    assert "Path=/auth/google" in clear_header


def test_oauth_transaction_hash_compares_without_storing_plain_token():
    digest = hash_oauth_transaction_token("transaction-token")
    assert digest != "transaction-token"
    assert oauth_transaction_token_matches("transaction-token", digest) is True
    assert oauth_transaction_token_matches("wrong-token", digest) is False


def test_validate_unsafe_request_origin_requires_allowed_origin():
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN="https://api.example.co.kr")
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/unsafe")
    async def unsafe(request: Request):
        validate_unsafe_request_origin(request, settings)
        return {"ok": True}

    client = TestClient(app, base_url="https://api.example.co.kr")
    assert client.post("/unsafe", headers={"Origin": "https://api.example.co.kr"}).status_code == 200
    assert client.post("/unsafe").status_code == 403
    assert client.post("/unsafe", headers={"Origin": "https://evil.example"}).status_code == 403


def test_csrf_required_when_samesite_none_or_explicit():
    assert csrf_token_required(valid_settings(AUTH_COOKIE_SAMESITE="none")) is True
    assert csrf_token_required(valid_settings(AUTH_CSRF_REQUIRED=True)) is True
    assert csrf_token_required(valid_settings(AUTH_COOKIE_SAMESITE="lax", AUTH_CSRF_REQUIRED=False)) is False


@pytest.mark.asyncio
async def test_session_store_oauth_state_is_single_use_and_ttl_backed():
    settings = valid_settings(AUTH_STATE_TTL_SECONDS=120)
    redis = FakeRedis()
    store = AuthSessionStore(redis, settings)
    await store.store_oauth_state(state="state-1", nonce="nonce-1", return_to="/app")
    key = store.state_key("state-1")
    assert redis.ttls[key] == 120
    assert await store.consume_oauth_state("state-1") == {"nonce": "nonce-1", "return_to": "/app"}
    with pytest.raises(AppError) as exc:
        await store.consume_oauth_state("state-1")
    assert exc.value.code == "oauth_state_invalid"


@pytest.mark.asyncio
async def test_session_store_oauth_state_round_trips_json_flow_metadata():
    settings = valid_settings(AUTH_STATE_TTL_SECONDS=120)
    redis = FakeRedis()
    store = AuthSessionStore(redis, settings)
    await store.store_oauth_state(
        state="state-1",
        nonce="nonce-1",
        return_to="/app",
        redirect_uri="https://fe.example.co.kr/auth/google/callback",
        flow_mode="json",
        transaction_token_hash="transaction-hash",
    )
    assert await store.consume_oauth_state("state-1") == {
        "nonce": "nonce-1",
        "return_to": "/app",
        "redirect_uri": "https://fe.example.co.kr/auth/google/callback",
        "flow_mode": "json",
        "transaction_token_hash": "transaction-hash",
    }


@pytest.mark.asyncio
async def test_session_store_session_and_csrf_are_redis_backed():
    settings = valid_settings(AUTH_SESSION_TTL_SECONDS=900, AUTH_CSRF_TTL_SECONDS=600)
    redis = FakeRedis()
    store = AuthSessionStore(redis, settings)
    session_id, csrf = await store.create_session(user_id="user-123")
    assert await store.get_session_user_id(session_id) == "user-123"
    assert await store.get_csrf_token(session_id) == csrf
    assert redis.ttls[store.session_key(session_id)] == 900
    await store.revoke_session(session_id)
    assert await store.get_session_user_id(session_id) is None


@pytest.mark.asyncio
async def test_session_store_redis_failure_fails_closed_and_redacts():
    store = AuthSessionStore(FailingRedis(), valid_settings())
    with pytest.raises(AppError) as exc:
        await store.get_session_user_id("session")
    assert exc.value.code == "redis_read_failed"
    assert "super-secret" not in json.dumps(exc.value.payload())


def test_google_authorization_url_contains_oidc_state_and_nonce():
    settings = valid_settings()
    url = build_google_authorization_url(settings, state="state-1", nonce="nonce-1")
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)
    assert parsed.netloc == "accounts.google.com"
    assert params["client_id"] == [settings.google_client_id]
    assert params["redirect_uri"] == [settings.google_redirect_uri]
    assert params["scope"] == ["openid email profile"]
    assert params["state"] == ["state-1"]
    assert params["nonce"] == ["nonce-1"]


def test_google_authorization_url_accepts_validated_redirect_uri_override():
    settings = valid_settings(AUTH_ALLOWED_ORIGINS="https://fe.example.co.kr")
    url = build_google_authorization_url(
        settings,
        state="state-1",
        nonce="nonce-1",
        redirect_uri="https://fe.example.co.kr/auth/google/callback",
    )
    params = parse_qs(urlsplit(url).query)
    assert params["redirect_uri"] == ["https://fe.example.co.kr/auth/google/callback"]


def valid_claims(settings, **overrides):
    claims = {
        "aud": settings.google_client_id,
        "iss": "https://accounts.google.com",
        "exp": str(int(time()) + 3600),
        "nonce": "nonce-1",
        "sub": "google-sub-123",
        "email": "user@example.co.kr",
        "email_verified": "true",
        "name": "User Name",
        "picture": "https://lh3.googleusercontent.com/avatar",
    }
    claims.update(overrides)
    return claims


def test_validate_google_claims_accepts_verified_google_identity():
    settings = valid_settings()
    identity = validate_google_claims(settings, claims=valid_claims(settings), expected_nonce="nonce-1")
    assert identity.sub == "google-sub-123"
    assert identity.email_verified is True


@pytest.mark.parametrize(
    "override,code",
    [
        ({"aud": "other-client"}, "google_audience_invalid"),
        ({"iss": "https://evil.example"}, "google_issuer_invalid"),
        ({"exp": "1"}, "google_token_expired"),
        ({"nonce": "wrong"}, "google_nonce_invalid"),
        ({"sub": ""}, "google_sub_missing"),
        ({"email": ""}, "google_email_missing"),
        ({"email_verified": "false"}, "google_email_unverified"),
    ],
)
def test_validate_google_claims_rejects_invalid_identity(override, code):
    settings = valid_settings()
    with pytest.raises(AppError) as exc:
        validate_google_claims(settings, claims=valid_claims(settings, **override), expected_nonce="nonce-1")
    assert exc.value.code == code
