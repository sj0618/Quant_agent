from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.staticfiles import StaticFiles

from app.api.routes import pages
from app.core.errors import register_exception_handlers
from app.services.session_store import AuthSessionStore
from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis


def make_client():
    settings = valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN="https://api.example.co.kr")
    app = FastAPI()
    register_exception_handlers(app)
    app.mount("/static", StaticFiles(directory=Path("app/static")), name="static")
    app.include_router(pages.router)
    app.state.settings = settings
    app.state.redis_client = FakeRedis()
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    return TestClient(app, base_url="https://api.example.co.kr"), app


def test_login_page_serves_google_only_backend_hosted_ui():
    client, _app = make_client()
    response = client.get("/login")
    assert response.status_code == 200
    body = response.text
    assert "Continue with Google" in body
    assert "/static/auth/auth.js" in body
    disallowed = ["localStorage", "sessionStorage", "accessToken", "fake user", "test login", "테스트 로그인"]
    assert not any(term in body for term in disallowed)


def test_app_page_requires_valid_session_then_serves_shell():
    client, app = make_client()
    missing = client.get("/app", follow_redirects=False)
    assert missing.status_code == 303
    assert missing.headers["location"] == "/login"
    session_id, _csrf = asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id="user-1"))
    response = client.get("/app", cookies={"qa_session": session_id})
    assert response.status_code == 200
    assert "내 계정" in response.text
    assert "/static/auth/auth.js" in response.text


def test_static_auth_js_uses_same_origin_auth_urls_and_no_browser_storage():
    js = Path("app/static/auth/auth.js").read_text(encoding="utf-8")
    assert "fetch('/auth/me'" in js
    assert "fetch('/auth/logout'" in js
    assert "fetch('/auth/csrf'" in js
    assert "/auth/google/start" in js
    assert "http://" not in js
    assert "https://" not in js
    disallowed = ["localStorage", "sessionStorage", "accessToken", "refreshToken", "provider: 'test'", 'provider: "test"', "fake user"]
    assert not any(term in js for term in disallowed)


def test_logout_button_is_backend_logout_not_client_clear_only():
    html = Path("app/static/auth/app.html").read_text(encoding="utf-8")
    js = Path("app/static/auth/auth.js").read_text(encoding="utf-8")
    assert 'id="logout"' in html
    assert "'/auth/logout'" in js
    assert "method: 'POST'" in js
