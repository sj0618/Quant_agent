from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import combined_main


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
def patched_general_startup(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    settings = DummySettings()
    redis_client = DummyRedis()
    db_engine = object()
    trading_engine = object()

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

    monkeypatch.setattr("app.main.load_settings", fake_load_settings)
    monkeypatch.setattr("app.main.create_db_engine", fake_create_db_engine)
    monkeypatch.setattr("app.main.create_trading_data_db_engine", fake_create_trading_data_db_engine)
    monkeypatch.setattr("app.main.create_redis_client", fake_create_redis_client)
    monkeypatch.setattr("app.main.dispose_db_engine", fake_dispose_db_engine)
    return {
        "settings": settings,
        "redis_client": redis_client,
        "db_engine": db_engine,
        "trading_engine": trading_engine,
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

    monkeypatch.setattr(combined_main, "general_app", general_app)
    monkeypatch.setattr(combined_main, "ai_app", ai_app)

    application = combined_main.create_app()
    assert [route.path for route in application.routes] == ["/combined-health", "/ai-api", ""]

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

    assert ai_not_found.status_code == 404
    assert ai_not_found.headers["content-type"].startswith("application/json")

    assert general_not_found.status_code == 404
    assert general_not_found.headers["content-type"].startswith("application/json")

    assert bare_analysis_jobs.status_code == 404
    assert general_ai_jobs.status_code == 404

    assert any(route.path == "/static" for route in combined_main.general_app.routes)
    assert not any(route.path.startswith("/ai-api") for route in combined_main.ai_app.routes)
