from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.contract_policy import CONTRACT_POLICY
from app.api.routes import fe_contract
from app.core.errors import register_exception_handlers
from app.core.runtime_perf import install_runtime_performance_middleware
from app.services.session_store import AuthSessionStore
from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis

API_ORIGIN = "https://api.example.co.kr"
FE_ORIGIN = "https://fe.example.co.kr"


def make_client(settings=None):
    app = FastAPI()
    register_exception_handlers(app)
    install_runtime_performance_middleware(app)
    app.include_router(fe_contract.router)
    app.state.settings = settings or valid_settings(
        AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN,
        AUTH_ALLOWED_ORIGINS=FE_ORIGIN,
        AUTH_CSRF_REQUIRED=True,
    )
    app.state.redis_client = FakeRedis()
    app.state.db_engine = object()
    app.state.trading_data_db_engine = object()
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    return TestClient(app, base_url=API_ORIGIN), app


def _create_session(app, user_id: str = "user-1") -> tuple[str, str]:
    return asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id=user_id))


def test_track_c_api_status_exposes_only_track_c_contract_endpoints():
    client, _app = make_client()

    response = client.get("/api/v1/api-status")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "QuantAgent Track C API"
    assert body["schemaVersion"] == "qa.track_c.v1"
    assert body["tradingDataEngine"]["configured"] is True
    assert {(entry["method"], entry["path"]) for entry in body["endpoints"]} == {
        (item.method, item.path) for item in CONTRACT_POLICY
    }
    assert {(entry["method"], entry["path"]) for entry in body["feLiveAllowlist"]} == {
        (item.method, item.path) for item in CONTRACT_POLICY
    }


def test_track_c_create_run_requires_csrf_and_uses_trading_data_engine(monkeypatch):
    client, app = make_client()
    session_id, csrf_token = _create_session(app, user_id="user-1")
    observed: dict[str, object] = {}

    async def fake_create(engine, *, user_id: str, payload: dict[str, object], identity_source_engine=None):
        observed["engine"] = engine
        observed["user_id"] = user_id
        observed["payload"] = payload
        observed["identity_source_engine"] = identity_source_engine
        return {"id": "run-1", "status": "queued", "createdAt": "2026-07-20T00:00:00Z"}

    monkeypatch.setattr(fe_contract.fe_contract_store, "create_analysis_run_from_db", fake_create)

    response = client.post(
        "/api/v1/runs",
        cookies={app.state.settings.auth_session_cookie_name: session_id},
        headers={"Origin": API_ORIGIN, "X-CSRF-Token": csrf_token},
        json={"query": "RSI 30", "strategyId": "strategy-1", "requestPayload": {"seed": "alpha"}},
    )

    assert response.status_code == 201
    assert response.json()["id"] == "run-1"
    assert observed["engine"] is app.state.trading_data_db_engine
    assert observed["identity_source_engine"] is app.state.db_engine
    assert observed["user_id"] == "user-1"
    assert observed["payload"]["query"] == "RSI 30"
    assert observed["payload"]["strategyId"] == "strategy-1"
    assert observed["payload"]["requestPayload"] == {"seed": "alpha"}


def test_track_c_create_run_rejects_missing_csrf(monkeypatch):
    client, app = make_client()
    session_id, _csrf_token = _create_session(app, user_id="user-1")

    async def fake_create(*_args, **_kwargs):
        raise AssertionError("Track C create run store must not be called when CSRF is missing")

    monkeypatch.setattr(fe_contract.fe_contract_store, "create_analysis_run_from_db", fake_create)

    response = client.post(
        "/api/v1/runs",
        cookies={app.state.settings.auth_session_cookie_name: session_id},
        headers={"Origin": API_ORIGIN},
        json={"query": "RSI 30"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_invalid"


def test_track_c_routes_return_503_when_trading_data_engine_is_missing():
    client, app = make_client()
    session_id, _csrf_token = _create_session(app, user_id="user-1")
    app.state.trading_data_db_engine = None

    response = client.get("/api/v1/reports", cookies={app.state.settings.auth_session_cookie_name: session_id})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "trading_data_not_configured"


def test_email_routes_require_authentication_and_csrf_before_database_access():
    client, app = make_client()

    for path in (
        "/api/v1/me/notifications",
        "/api/v1/me/email-strategy-subscriptions",
        "/api/v1/me/email-deliveries",
    ):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"

    session_id, _csrf_token = _create_session(app, user_id="user-1")
    cookie = {app.state.settings.auth_session_cookie_name: session_id}
    for method, path, payload in (
        ("PATCH", "/api/v1/me/notifications", {"dailyReportEmail": True}),
        ("POST", "/api/v1/me/email-strategy-subscriptions", {"strategyId": "strategy-1"}),
        ("DELETE", "/api/v1/me/email-strategy-subscriptions/strategy-1", None),
        ("POST", "/api/v1/reports/report-1/resend", None),
    ):
        response = client.request(method, path, cookies=cookie, headers={"Origin": API_ORIGIN}, json=payload)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_invalid"


def test_unsubscribe_route_is_public_but_fail_closed_when_disabled():
    client, _app = make_client()

    response = client.get("/api/v1/unsubscribe", params={"token": "opaque"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unsubscribe_disabled"


def test_track_c_run_and_report_routes_enforce_owner_scope(monkeypatch):
    client, app = make_client()
    owner_session_id, _owner_csrf = _create_session(app, user_id="user-1")
    intruder_session_id, _intruder_csrf = _create_session(app, user_id="user-2")

    async def fake_get_run(engine, run_id: str, *, user_id: str):
        if user_id == "user-1":
            return {"id": run_id, "status": "queued", "createdAt": "2026-07-20T00:00:00Z", "strategyId": "strategy-1"}
        return None

    async def fake_list_reports(
        engine,
        *,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ):
        if user_id == "user-1":
            return {
                "items": [{"id": "report-1", "runId": "run-1", "title": "Report", "summary": "Summary", "status": "sent"}],
                "meta": {"limit": limit, "hasMore": False, "nextCursor": None},
            }
        return {"items": [], "meta": {"limit": limit, "hasMore": False, "nextCursor": None}}

    async def fake_get_report(engine, report_id: str, *, user_id: str):
        if user_id == "user-1":
            return {
                "id": report_id,
                "runId": "run-1",
                "title": "Report",
                "summary": "Summary",
                "status": "sent",
                "marketBrief": "Summary",
            }
        return None

    monkeypatch.setattr(fe_contract.fe_contract_store, "get_analysis_run_from_db", fake_get_run)
    monkeypatch.setattr(fe_contract.fe_contract_store, "list_reports_from_db", fake_list_reports)
    monkeypatch.setattr(fe_contract.fe_contract_store, "get_report_from_db", fake_get_report)

    owner_run = client.get("/api/v1/runs/run-1", cookies={app.state.settings.auth_session_cookie_name: owner_session_id})
    intruder_run = client.get("/api/v1/runs/run-1", cookies={app.state.settings.auth_session_cookie_name: intruder_session_id})
    owner_reports = client.get("/api/v1/reports", cookies={app.state.settings.auth_session_cookie_name: owner_session_id})
    intruder_reports = client.get("/api/v1/reports", cookies={app.state.settings.auth_session_cookie_name: intruder_session_id})
    owner_report = client.get("/api/v1/reports/report-1", cookies={app.state.settings.auth_session_cookie_name: owner_session_id})
    intruder_report = client.get("/api/v1/reports/report-1", cookies={app.state.settings.auth_session_cookie_name: intruder_session_id})

    assert owner_run.status_code == 200
    assert owner_run.json()["id"] == "run-1"
    assert intruder_run.status_code == 404
    assert intruder_run.json()["error"]["code"] == "run_not_found"
    assert owner_reports.status_code == 200
    assert owner_reports.json()["items"][0]["id"] == "report-1"
    assert intruder_reports.status_code == 200
    assert intruder_reports.json()["items"] == []
    assert owner_report.status_code == 200
    assert owner_report.json()["id"] == "report-1"
    assert intruder_report.status_code == 404
    assert intruder_report.json()["error"]["code"] == "report_not_found"


def test_track_c_complete_and_report_list_routes_forward_filters(monkeypatch):
    client, app = make_client()
    session_id, csrf_token = _create_session(app, user_id="user-1")
    observed: dict[str, object] = {}

    async def fake_complete(
        engine,
        *,
        user_id: str,
        run_id: str,
        payload: dict[str, object],
        identity_source_engine=None,
        email_settings=None,
    ):
        observed["engine"] = engine
        observed["user_id"] = user_id
        observed["run_id"] = run_id
        observed["payload"] = payload
        observed["identity_source_engine"] = identity_source_engine
        observed["email_settings"] = email_settings
        return {"runId": run_id, "reportId": "report-1", "status": "completed", "created": True}

    async def fake_list_reports(
        engine,
        *,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ):
        observed["list_filters"] = {"user_id": user_id, "limit": limit, "cursor": cursor, "status": status, "q": q}
        return {"items": [], "meta": {"limit": limit, "hasMore": False, "nextCursor": None}}

    monkeypatch.setattr(fe_contract.fe_contract_store, "complete_analysis_run_from_db", fake_complete)
    monkeypatch.setattr(fe_contract.fe_contract_store, "list_reports_from_db", fake_list_reports)

    class StoredResult:
        def model_dump(self, *, mode: str):
            assert mode == "json"
            return {
                "status": "ready",
                "strategy_spec": {"strategy_id": "strategy-1"},
                "user_payload": {
                    "recommendation_gate": {"validated": True},
                    "performance": {"sharpe_ratio": 0.28},
                    "report": {
                        "web_projection": {
                            "title": "Stored report",
                            "summary": "Stored summary",
                            "sections": [{"title": "Section", "summary": "Body"}],
                        }
                    },
                },
            }

    app.state.analysis_job_store = SimpleNamespace(
        get_job=lambda job_id: SimpleNamespace(
            job_id=job_id,
            user_id="user-1",
            status="completed",
            result=StoredResult(),
            completed_at=datetime(2026, 8, 3, tzinfo=UTC),
        )
    )

    completion = client.post(
        "/api/v1/runs/run-1/complete",
        cookies={app.state.settings.auth_session_cookie_name: session_id},
        headers={"Origin": API_ORIGIN, "X-CSRF-Token": csrf_token},
        json={
            "aiJobId": "job-1",
            "result": {"title": "Forged browser report", "summary": "Forged browser summary"},
        },
    )
    reports = client.get(
        "/api/v1/reports",
        cookies={app.state.settings.auth_session_cookie_name: session_id},
        params={"limit": 5, "cursor": "cursor-value", "status": "sent", "q": "삼성전자"},
    )

    assert completion.status_code == 200
    assert completion.json()["runId"] == "run-1"
    assert observed["engine"] is app.state.trading_data_db_engine
    assert observed["identity_source_engine"] is app.state.db_engine
    assert observed["user_id"] == "user-1"
    assert observed["run_id"] == "run-1"
    assert observed["payload"]["status"] == "completed"
    assert observed["payload"]["aiJobId"] == "job-1"
    assert observed["payload"]["result"]["title"] == "Stored report"
    assert observed["payload"]["result"]["summary"] == "Stored summary"
    assert reports.status_code == 200
    assert observed["list_filters"] == {"user_id": "user-1", "limit": 5, "cursor": "cursor-value", "status": "sent", "q": "삼성전자"}


def test_report_diagnostics_preserve_contract_and_record_safe_metadata(monkeypatch, caplog):
    settings = valid_settings(
        AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN,
        AUTH_ALLOWED_ORIGINS=FE_ORIGIN,
        PERF_DIAGNOSTICS_ENABLED=True,
    )
    client, app = make_client(settings)
    session_id, _csrf = _create_session(app, user_id="user-1")

    async def fake_list_reports(_engine, **_kwargs):
        return {
            "items": [{"id": "report-1", "runId": "run-1", "title": "Report", "summary": "Summary", "status": "sent"}],
            "meta": {"limit": 20, "hasMore": False, "nextCursor": None},
        }

    monkeypatch.setattr(fe_contract.fe_contract_store, "list_reports_from_db", fake_list_reports)
    caplog.set_level("INFO", logger="uvicorn.error.runtime_perf")

    response = client.get(
        "/api/v1/reports",
        cookies={settings.auth_session_cookie_name: session_id},
        headers={"X-Request-ID": "reports-contract-1"},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "report-1"
    assert response.headers["X-Request-ID"] == "reports-contract-1"
    assert "row_count=1" in caplog.text
    assert "has_more=false" in caplog.text
