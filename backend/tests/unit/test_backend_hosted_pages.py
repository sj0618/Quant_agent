from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from app.api.routes import pages
from app.core.errors import register_exception_handlers
from app.services.session_store import AuthSessionStore
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis


@pytest.fixture
def frontend_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "fe" / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><body>FE SPA</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('FE SPA asset');", encoding="utf-8")
    return dist


def make_client(frontend_dist: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pages, "FE_DIST_DIR", frontend_dist)
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


def test_login_page_serves_frontend_shell(frontend_dist: Path, monkeypatch: pytest.MonkeyPatch):
    client, _app = make_client(frontend_dist, monkeypatch)
    response = client.get("/login")
    assert response.status_code == 200
    assert response.text == "<!doctype html><html><body>FE SPA</body></html>"


def test_app_page_requires_valid_session_then_serves_shell(frontend_dist: Path, monkeypatch: pytest.MonkeyPatch):
    client, app = make_client(frontend_dist, monkeypatch)
    missing = client.get("/app", follow_redirects=False)
    assert missing.status_code == 303
    assert missing.headers["location"] == "/login"
    session_id, _csrf = asyncio.run(
        AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id="user-1")
    )
    response = client.get("/app", cookies={"qa_session": session_id})
    assert response.status_code == 200
    assert response.text == "<!doctype html><html><body>FE SPA</body></html>"


def test_known_frontend_routes_use_spa_fallback(frontend_dist: Path, monkeypatch: pytest.MonkeyPatch):
    client, _app = make_client(frontend_dist, monkeypatch)
    static_routes = [
        "/",
        "/login",
        "/app",
        "/reports",
        "/me",
        "/me/notifications",
        "/search",
        "/terms",
        "/privacy",
        "/disclaimer",
        "/trust",
        "/unsubscribe",
    ]
    frontend_routes_source = (Path(__file__).resolve().parents[3] / "fe" / "src" / "config" / "routes.ts").read_text(
        encoding="utf-8"
    )
    configured_static_routes = set(re.findall(r'^  \w+: "([^"]+)",$', frontend_routes_source, flags=re.MULTILINE))
    # The OAuth callback is owned by the backend auth router. Every other static
    # frontend URL must be served by the same HTTP policy as this test.
    assert set(static_routes) == configured_static_routes - {"/auth/google/callback"}
    responses = {route: client.get(route, follow_redirects=False) for route in static_routes}
    report_detail = client.get("/reports/report-123")
    asset = client.get("/assets/app.js")

    # /login and /app deliberately have authentication-specific routes; every other
    # public React route must remain in lockstep with FRONTEND_EXACT_ROUTES.
    assert responses["/login"].status_code == 200
    assert responses["/app"].status_code == 303
    assert all(response.status_code == 200 for route, response in responses.items() if route != "/app")
    assert report_detail.status_code == 200
    assert asset.status_code == 200
    assert responses["/search"].text == "<!doctype html><html><body>FE SPA</body></html>"
    assert report_detail.text == "<!doctype html><html><body>FE SPA</body></html>"
    assert responses["/"].text == "<!doctype html><html><body>FE SPA</body></html>"
    assert asset.text == "console.log('FE SPA asset');"


def test_unknown_frontend_routes_keep_the_not_found_shell_but_return_http_404(
    frontend_dist: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    client, _app = make_client(frontend_dist, monkeypatch)

    response = client.get("/dev/email-template")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == "<!doctype html><html><body>FE SPA</body></html>"


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
