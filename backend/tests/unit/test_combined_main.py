from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import textwrap
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

import combined_main
from app.api.routes import pages


class DummySettings:
    auth_session_cookie_name = "qa_session"
    auth_state_ttl_seconds = 600
    auth_session_idle_ttl_seconds = 1800
    auth_session_absolute_ttl_seconds = 28800
    auth_session_touch_interval_seconds = 60
    auth_csrf_ttl_seconds = 3600

    def __init__(self) -> None:
        self._redis_url_value = "redis://combined-test"

    @property
    def redis_url_value(self) -> str | None:
        return self._redis_url_value

    @property
    def sqlalchemy_database_url(self) -> str:
        return "postgresql+asyncpg://combined-main/test"

    @property
    def trading_data_sqlalchemy_database_url(self) -> str | None:
        return "postgresql+asyncpg://combined-trading/test"

    @property
    def allowed_origins(self) -> list[str]:
        return []


class DummyRedis:
    async def get(self, key: str) -> None:
        return None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        return None

    async def expire(self, key: str, ttl_seconds: int) -> None:
        return None

    async def delete(self, *keys: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


@asynccontextmanager
async def _general_lifespan(order: list[str]):
    order.append("general:enter")
    yield
    order.append("general:exit")


@asynccontextmanager
async def _ai_lifespan(order: list[str]):
    order.append("ai:enter")
    yield
    order.append("ai:exit")


@asynccontextmanager
async def _failing_ai_lifespan(order: list[str]):
    order.append("ai:enter")
    raise RuntimeError("ai startup failed")
    yield  # pragma: no cover - required by asynccontextmanager semantics


@pytest.fixture
def patched_general_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    settings = DummySettings()
    redis_client = DummyRedis()
    db_engine = object()
    trading_engine = object()
    frontend_dist = tmp_path / "fe" / "dist"
    (frontend_dist / "assets").mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<!doctype html><html><body>Combined FE</body></html>", encoding="utf-8")
    (frontend_dist / "assets" / "app.js").write_text("console.log('Combined FE asset');", encoding="utf-8")
    monkeypatch.setattr(pages, "FE_DIST_DIR", frontend_dist)

    def fake_load_settings():
        return settings

    def fake_create_db_engine(runtime_settings):
        assert runtime_settings is settings
        return db_engine

    def fake_create_trading_data_db_engine(runtime_settings):
        assert runtime_settings is settings
        return trading_engine

    def fake_create_redis_client(redis_url: str | None):
        return redis_client

    async def fake_dispose_db_engine(engine):
        return None

    class FakeMissingSessionResolver:
        async def resolve_user_id(self, session_id: str | None) -> None:
            return None

    monkeypatch.setattr("app.main.load_settings", fake_load_settings)
    monkeypatch.setattr("app.main.create_db_engine", fake_create_db_engine)
    monkeypatch.setattr("app.main.create_trading_data_db_engine", fake_create_trading_data_db_engine)
    monkeypatch.setattr("app.main.create_redis_client", fake_create_redis_client)
    monkeypatch.setattr("app.main.dispose_db_engine", fake_dispose_db_engine)
    monkeypatch.setattr("ai_graph.auth.build_session_resolver_from_env", lambda env=None: FakeMissingSessionResolver())
    return {
        "settings": settings,
        "redis_client": redis_client,
        "db_engine": db_engine,
        "trading_engine": trading_engine,
        "frontend_dist": frontend_dist,
    }


def test_combined_module_import_does_not_start_child_lifespan():
    repo_root = Path(__file__).resolve().parents[3]
    script = textwrap.dedent(
        """
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        import sys
        import types

        order = []

        @asynccontextmanager
        async def lifespan(app):
            order.append(f"{app.title}:enter")
            yield
            order.append(f"{app.title}:exit")

        def register(package_name: str, module_name: str, title: str) -> None:
            package = types.ModuleType(package_name)
            package.__path__ = []
            module = types.ModuleType(module_name)
            module.app = FastAPI(title=title, lifespan=lifespan)
            setattr(package, module_name.split(".")[-1], module)
            sys.modules[package_name] = package
            sys.modules[module_name] = module

        register("app", "app.main", "general")
        register("ai_graph", "ai_graph.api", "ai")

        import combined_main

        print(order)
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == "[]"


def test_combined_app_lifespan_orders_general_then_ai_and_mounts_ai_first(monkeypatch: pytest.MonkeyPatch):
    order: list[str] = []
    general_app = FastAPI(title="general", lifespan=lambda app: _general_lifespan(order))
    ai_app = FastAPI(title="ai", lifespan=lambda app: _ai_lifespan(order))
    ai_app.state.job_store = object()

    monkeypatch.setattr(combined_main, "general_app", general_app)
    monkeypatch.setattr(combined_main, "ai_app", ai_app)

    application = combined_main.create_app()
    assert [route.path for route in application.routes] == ["/combined-health", "/ai-api", ""]
    assert general_app.state.analysis_job_store is ai_app.state.job_store

    with TestClient(application) as client:
        assert client.get("/combined-health").json() == {
            "status": "ok",
            "service": "quantagent-combined-backend",
        }

    assert order == ["general:enter", "ai:enter", "ai:exit", "general:exit"]


def test_combined_app_lifespan_unwinds_general_if_ai_startup_fails(monkeypatch: pytest.MonkeyPatch):
    order: list[str] = []
    general_app = FastAPI(title="general", lifespan=lambda app: _general_lifespan(order))
    ai_app = FastAPI(title="ai", lifespan=lambda app: _failing_ai_lifespan(order))

    monkeypatch.setattr(combined_main, "general_app", general_app)
    monkeypatch.setattr(combined_main, "ai_app", ai_app)

    application = combined_main.create_app()

    with pytest.raises(RuntimeError, match="ai startup failed"):
        with TestClient(application):
            pass

    assert order == ["general:enter", "ai:enter", "general:exit"]


def test_combined_route_surface_routes_general_and_ai_without_cross_shadowing(
    patched_general_startup: dict[str, Any],
):
    with TestClient(combined_main.app, base_url="http://testserver") as client:
        combined_health = client.get("/combined-health")
        general_api_status = client.get("/api/v1/api-status")
        unauthenticated_me = client.get("/api/v1/auth/me")
        ai_health = client.get("/ai-api/health")
        ai_api_status = client.get("/ai-api/api-status")
        frontend_root = client.get("/search")
        frontend_asset = client.get("/assets/app.js")
        ai_not_found = client.get("/ai-api/not-found")
        general_not_found = client.get("/api/v1/not-found")
        bare_analysis_jobs = client.get("/analysis-jobs")
        general_ai_jobs = client.get("/api/v1/analysis-jobs")

    assert combined_health.status_code == 200
    assert combined_health.json() == {"status": "ok", "service": "quantagent-combined-backend"}

    assert general_api_status.status_code == 200
    assert general_api_status.json()["service"] == "QuantAgent Track C API"

    assert unauthenticated_me.status_code == 401
    assert unauthenticated_me.headers["content-type"].startswith("application/json")
    assert unauthenticated_me.json()["error"]["code"] == "not_authenticated"

    assert ai_health.status_code == 200
    assert ai_health.json()["status"] == "ok"

    assert ai_api_status.status_code == 200
    assert ai_api_status.json()["service"] == "QuantAgent AI API"

    assert frontend_root.status_code == 200
    assert "Combined FE" in frontend_root.text

    assert frontend_asset.status_code == 200
    assert frontend_asset.text == "console.log('Combined FE asset');"

    assert ai_not_found.status_code == 404
    assert ai_not_found.headers["content-type"].startswith("application/json")

    assert general_not_found.status_code == 404
    assert general_not_found.headers["content-type"].startswith("application/json")

    # Root /analysis-jobs is now a compatibility alias for the mounted AI app.
    assert bare_analysis_jobs.status_code == 401
    assert general_ai_jobs.status_code == 404

    assert any(route.path == "/static" for route in combined_main.general_app.routes)
    assert not any(route.path.startswith("/ai-api") for route in combined_main.ai_app.routes)


@pytest.fixture
def compat_ai_app() -> FastAPI:
    app = FastAPI(title="ai-compat-stub")
    app.state.calls = []
    app.state.stream_started = False
    app.state.stream_finished = False

    async def capture_request(request: Request, *, route: str, job_id: str | None = None) -> dict[str, Any]:
        body = await request.body()
        body_text = body.decode(encoding="utf-8")
        raw_path = request.scope.get("raw_path")
        query_string = request.scope.get("query_string")
        scope_path = request.scope.get("path")
        root_path = request.scope.get("root_path") or ""
        mounted_path = scope_path.removeprefix(root_path) if isinstance(scope_path, str) else scope_path
        record = {
            "marker": "ai-compat",
            "route": route,
            "job_id": job_id,
            "method": request.method,
            "path": scope_path,
            "root_path": root_path,
            "mounted_path": mounted_path,
            "raw_path": raw_path.decode(encoding="utf-8") if isinstance(raw_path, bytes) else raw_path,
            "query_string": query_string.decode(encoding="utf-8") if isinstance(query_string, bytes) else query_string,
            "content_type": request.headers.get("content-type"),
            "body_text": body_text,
            "body_json": json.loads(body_text) if body_text else None,
        }
        app.state.calls.append(record)
        return record

    @app.post("/analysis-jobs")
    async def create_analysis_job(request: Request):
        return JSONResponse(await capture_request(request, route="create"))

    @app.get("/analysis-jobs")
    async def list_analysis_jobs(request: Request):
        return JSONResponse(await capture_request(request, route="list"))

    @app.get("/analysis-jobs/{job_id}")
    async def get_analysis_job(request: Request, job_id: str):
        return JSONResponse(await capture_request(request, route="detail", job_id=job_id))

    @app.post("/analysis-jobs/{job_id}/cancel")
    async def cancel_analysis_job(request: Request, job_id: str):
        return JSONResponse(await capture_request(request, route="cancel", job_id=job_id))

    @app.get("/analysis-jobs/{job_id}/events")
    async def stream_analysis_job_events(request: Request, job_id: str):
        await capture_request(request, route="events", job_id=job_id)

        async def event_source():
            app.state.stream_started = True
            yield "event: message\ndata: chunk-1\n\n"
            await asyncio.sleep(0)
            yield "event: done\ndata: chunk-2\n\n"
            app.state.stream_finished = True

        return StreamingResponse(event_source(), media_type="text/event-stream")

    return app


@pytest.fixture
def compat_combined_app(
    monkeypatch: pytest.MonkeyPatch,
    patched_general_startup: dict[str, Any],
    compat_ai_app: FastAPI,
) -> FastAPI:
    monkeypatch.setattr(combined_main, "ai_app", compat_ai_app)
    application = combined_main.create_app()
    assert [middleware.cls for middleware in application.user_middleware] == [
        combined_main.LegacyAiPrefixCompatibilityMiddleware,
    ]
    return application


def test_legacy_ai_prefix_compatibility_rewrites_post_create_requests(compat_combined_app: FastAPI, compat_ai_app: FastAPI):
    with TestClient(compat_combined_app, base_url="http://testserver") as client:
        response = client.post(
            "/analysis-jobs",
            json={"query": "Strip legacy prefix"},
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json()["marker"] == "ai-compat"
    assert response.json()["route"] == "create"
    assert response.json()["mounted_path"] == "/analysis-jobs"
    assert response.json()["root_path"] == "/ai-api"
    assert response.json()["raw_path"] == "/ai-api/analysis-jobs"
    assert response.json()["method"] == "POST"
    assert response.json()["content_type"].startswith("application/json")
    assert response.json()["body_json"] == {"query": "Strip legacy prefix"}
    assert compat_ai_app.state.calls[-1]["body_json"] == {"query": "Strip legacy prefix"}


def test_legacy_ai_prefix_compatibility_rewrites_list_requests_and_preserves_query(
    compat_combined_app: FastAPI,
    compat_ai_app: FastAPI,
):
    with TestClient(compat_combined_app, base_url="http://testserver") as client:
        response = client.get("/analysis-jobs?limit=20")

    assert response.status_code == 200
    assert response.json()["route"] == "list"
    assert response.json()["method"] == "GET"
    assert response.json()["mounted_path"] == "/analysis-jobs"
    assert response.json()["root_path"] == "/ai-api"
    assert response.json()["query_string"] == "limit=20"
    assert response.json()["raw_path"] == "/ai-api/analysis-jobs"
    assert compat_ai_app.state.calls[-1]["query_string"] == "limit=20"


@pytest.mark.parametrize(
    ("path", "expected_route", "expected_status"),
    [
        ("/analysis-jobs/job-123", "detail", 200),
        ("/analysis-jobs/job-123/cancel", "cancel", 200),
    ],
)
def test_legacy_ai_prefix_compatibility_rewrites_detail_and_cancel_requests(
    compat_combined_app: FastAPI,
    compat_ai_app: FastAPI,
    path: str,
    expected_route: str,
    expected_status: int,
):
    with TestClient(compat_combined_app, base_url="http://testserver") as client:
        request_kwargs: dict[str, Any] = {}
        if path.endswith("/cancel"):
            request_kwargs["json"] = {"reason": "stop now"}
        response = client.request(
            "POST" if path.endswith("/cancel") else "GET",
            path,
            **request_kwargs,
        )

    assert response.status_code == expected_status
    assert response.json()["route"] == expected_route
    assert response.json()["mounted_path"] == path
    assert response.json()["root_path"] == "/ai-api"
    assert response.json()["method"] == ("POST" if path.endswith("/cancel") else "GET")
    if path.endswith("/cancel"):
        assert response.json()["body_json"] == {"reason": "stop now"}
        assert response.json()["content_type"].startswith("application/json")
    else:
        assert response.json()["body_text"] == ""
    assert response.json()["raw_path"] == f"/ai-api{path}"
    assert compat_ai_app.state.calls[-1]["job_id"] == "job-123"


def test_legacy_ai_prefix_compatibility_streams_events_without_buffering(
    compat_combined_app: FastAPI,
    compat_ai_app: FastAPI,
):
    with TestClient(compat_combined_app, base_url="http://testserver") as client:
        response = client.get("/analysis-jobs/job-123/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "chunk-1" in response.text
    assert "chunk-2" in response.text
    assert compat_ai_app.state.calls[-1]["route"] == "events"
    assert compat_ai_app.state.calls[-1]["mounted_path"] == "/analysis-jobs/job-123/events"
    assert compat_ai_app.state.calls[-1]["root_path"] == "/ai-api"
    assert compat_ai_app.state.stream_started is True
    assert compat_ai_app.state.stream_finished is True


def test_legacy_ai_prefix_compatibility_keeps_prefixed_ai_requests_on_the_same_ai_route(
    compat_combined_app: FastAPI,
    compat_ai_app: FastAPI,
):
    with TestClient(compat_combined_app, base_url="http://testserver") as client:
        response = client.post(
            "/ai-api/analysis-jobs",
            json={"query": "Already prefixed"},
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json()["mounted_path"] == "/analysis-jobs"
    assert response.json()["root_path"] == "/ai-api"
    assert response.json()["raw_path"] == "/ai-api/analysis-jobs"
    assert response.json()["body_json"] == {"query": "Already prefixed"}
    assert len(compat_ai_app.state.calls) == 1


@pytest.mark.parametrize(
    ("path", "expected_status", "expected_body_contains"),
    [
        ("/analysis-jobs-extra", 404, None),
        ("/analysis-job", 200, "Combined FE"),
        ("/api/analysis-jobs", 404, None),
        ("/api/v1/analysis-jobs", 404, None),
        ("/foo/analysis-jobs", 200, "Combined FE"),
    ],
)
def test_legacy_ai_prefix_compatibility_leaves_non_matching_paths_on_general_backend(
    compat_combined_app: FastAPI,
    compat_ai_app: FastAPI,
    path: str,
    expected_status: int,
    expected_body_contains: str | None,
):
    with TestClient(compat_combined_app, base_url="http://testserver") as client:
        response = client.get(path)

    assert response.status_code == expected_status
    if expected_body_contains is not None:
        assert expected_body_contains in response.text
    assert compat_ai_app.state.calls == []
