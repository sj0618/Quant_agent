from __future__ import annotations

import asyncio
import math
import re

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core import runtime_perf
from app.core.runtime_perf import (
    install_runtime_performance_middleware,
    measure_span,
    report_database_phase,
    set_report_metadata,
)
from app.db.session import fetch_all
from tests.unit.test_auth_config import valid_settings


_ALLOWED_SERVER_TIMING = {
    "total",
    "auth",
    "redis",
    "userdb",
    "dbacquire",
    "query",
    "fetch",
    "mapping",
    "response",
}


def _app(*, enabled: bool) -> FastAPI:
    app = FastAPI()
    install_runtime_performance_middleware(app)
    app.state.settings = valid_settings(PERF_DIAGNOSTICS_ENABLED=enabled)

    @app.get("/api/v1/auth/me")
    async def auth_me():
        with measure_span("auth"):
            with measure_span("redis"):
                await asyncio.sleep(0)
            with measure_span("userdb"):
                await asyncio.sleep(0)
        return {"user": {"id": "public-user"}}

    @app.get("/api/v1/reports/{report_id}")
    async def report_detail(report_id: str):
        del report_id
        with measure_span("auth"):
            await asyncio.sleep(0)
        set_report_metadata(row_count=1)
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def _parse_server_timing(value: str) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for item in value.split(","):
        name, duration = item.strip().split(";dur=", maxsplit=1)
        parsed[name] = float(duration)
    return parsed


def test_diagnostics_are_disabled_by_default_and_ignore_non_target_routes(caplog, monkeypatch):
    disabled = TestClient(_app(enabled=False))
    enabled = TestClient(_app(enabled=True))
    caplog.set_level("INFO", logger="uvicorn.error.runtime_perf")
    timer_calls = 0

    def diagnostic_timer():
        nonlocal timer_calls
        timer_calls += 1
        return 0.0

    monkeypatch.setattr(runtime_perf, "_now", diagnostic_timer)

    disabled_response = disabled.get("/api/v1/auth/me")
    non_target_response = enabled.get("/health")

    assert "X-Request-ID" not in disabled_response.headers
    assert "Server-Timing" not in disabled_response.headers
    assert "X-Request-ID" not in non_target_response.headers
    assert "Server-Timing" not in non_target_response.headers
    assert "event=runtime_perf" not in caplog.text
    assert timer_calls == 0


def test_enabled_diagnostics_reuse_only_safe_request_ids_and_emit_numeric_allowlisted_metrics():
    client = TestClient(_app(enabled=True))

    safe = client.get("/api/v1/auth/me", headers={"X-Request-ID": "safe.request-1:abc"})
    unsafe = client.get("/api/v1/auth/me", headers={"X-Request-ID": "unsafe request/id"})
    oversized = client.get("/api/v1/auth/me", headers={"X-Request-ID": "x" * 65})

    assert safe.headers["X-Request-ID"] == "safe.request-1:abc"
    assert unsafe.headers["X-Request-ID"] != "unsafe request/id"
    assert re.fullmatch(r"[a-f0-9]{32}", unsafe.headers["X-Request-ID"])
    assert oversized.headers["X-Request-ID"] != "x" * 65
    assert re.fullmatch(r"[a-f0-9]{32}", oversized.headers["X-Request-ID"])
    timings = _parse_server_timing(safe.headers["Server-Timing"])
    assert timings.keys() <= _ALLOWED_SERVER_TIMING
    assert {"total", "auth", "redis", "userdb"} <= timings.keys()
    assert all(math.isfinite(value) and value >= 0 for value in timings.values())


def test_logs_use_route_templates_and_do_not_expose_path_query_cookie_or_body_values(caplog):
    client = TestClient(_app(enabled=True))
    caplog.set_level("INFO", logger="uvicorn.error.runtime_perf")

    response = client.get(
        "/api/v1/reports/private-report-id?token=private-query-token",
        headers={"Cookie": "qa_session=private-session-value", "X-Request-ID": "redaction-check-1"},
    )

    assert response.status_code == 200
    assert "route=/api/v1/reports/{report_id}" in caplog.text
    assert "private-report-id" not in caplog.text
    assert "private-query-token" not in caplog.text
    assert "private-session-value" not in caplog.text


def test_instrumentation_failure_does_not_change_business_response(monkeypatch):
    app = _app(enabled=True)
    client = TestClient(app)
    monkeypatch.setattr(runtime_perf, "_server_timing_value", lambda _collector: (_ for _ in ()).throw(RuntimeError("boom")))

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["id"] == "public-user"


def test_existing_http_exception_contract_is_unchanged():
    app = FastAPI()
    install_runtime_performance_middleware(app)
    app.state.settings = valid_settings(PERF_DIAGNOSTICS_ENABLED=True)

    @app.get("/api/v1/auth/me")
    async def auth_me_error():
        raise HTTPException(status_code=418, detail="contract-detail")

    response = TestClient(app).get("/api/v1/auth/me", headers={"X-Request-ID": "error-contract-1"})

    assert response.status_code == 418
    assert response.json() == {"detail": "contract-detail"}
    assert response.headers["X-Request-ID"] == "error-contract-1"


class _FakeMappings:
    def all(self):
        return [{"id": "row-1"}, {"id": "row-2"}]


class _FakeResult:
    def mappings(self):
        return _FakeMappings()


class _FakeConnection:
    async def execute(self, _statement, _params):
        await asyncio.sleep(0)
        return _FakeResult()


class _FakeConnectionContext:
    async def __aenter__(self):
        await asyncio.sleep(0)
        return _FakeConnection()

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


class _FakeEngine:
    def connect(self):
        return _FakeConnectionContext()


def test_report_database_spans_are_separated():
    app = FastAPI()
    install_runtime_performance_middleware(app)
    app.state.settings = valid_settings(PERF_DIAGNOSTICS_ENABLED=True)

    @app.get("/api/v1/reports")
    async def reports():
        with report_database_phase():
            rows = await fetch_all(_FakeEngine(), "SELECT id FROM reports")
        with measure_span("mapping"):
            result = {"items": rows, "meta": {"hasMore": False}}
        set_report_metadata(row_count=len(rows), has_more=False)
        return result

    response = TestClient(app).get("/api/v1/reports")
    timings = _parse_server_timing(response.headers["Server-Timing"])

    assert response.status_code == 200
    assert {"dbacquire", "query", "fetch", "mapping"} <= timings.keys()
    assert all(timings[name] >= 0 for name in ("dbacquire", "query", "fetch", "mapping"))


def test_concurrent_requests_keep_request_ids_isolated():
    app = _app(enabled=True)

    async def run_requests():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://api.example.co.kr") as client:
            return await asyncio.gather(
                client.get("/api/v1/auth/me", headers={"X-Request-ID": "concurrent-a"}),
                client.get("/api/v1/auth/me", headers={"X-Request-ID": "concurrent-b"}),
            )

    first, second = asyncio.run(run_requests())

    assert first.headers["X-Request-ID"] == "concurrent-a"
    assert second.headers["X-Request-ID"] == "concurrent-b"
