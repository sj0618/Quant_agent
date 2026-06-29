from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import fe_contract
from app.core.errors import register_exception_handlers
from app.services.session_store import AuthSessionStore
from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis

API_ORIGIN = "https://api.example.co.kr"
FE_ORIGIN = "https://fe.example.co.kr"


def make_client(settings=None):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(fe_contract.router)
    app.state.settings = settings or valid_settings(AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN, AUTH_ALLOWED_ORIGINS=FE_ORIGIN)
    app.state.redis_client = FakeRedis()
    app.state.db_engine = object()
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    return TestClient(app, base_url=API_ORIGIN), app


def test_fe_contract_read_endpoints_return_frontend_shapes():
    client, _app = make_client()

    landing = client.get("/landing-sample")
    template = client.get("/workspace/template")
    overview = client.get("/app/overview")
    candidates = client.get("/trading-candidates")
    performance = client.get("/performance/summary")
    reports = client.get("/reports")
    detail = client.get("/reports/2026-04-18")
    missing = client.get("/reports/missing")

    assert landing.status_code == 200
    assert {"heroStats", "steps", "reportPreview", "comparisonRows", "principles", "faqs"} <= set(landing.json())
    assert template.status_code == 200
    assert template.json()["chatMessages"] == []
    assert template.json()["recentReports"] == []
    assert overview.status_code == 200
    assert len(overview.json()["recentReports"]) == 4
    assert candidates.status_code == 200
    assert candidates.json()[0]["ticker"]
    assert performance.status_code == 200
    assert performance.json()["metrics"][0]["key"] == "sharpe"
    assert reports.status_code == 200
    assert reports.json()[0]["id"] == "2026-04-18"
    assert detail.status_code == 200
    assert detail.json()["id"] == "2026-04-18"
    assert missing.status_code == 200
    assert missing.json() is None


def test_report_resend_accepts_frontend_action_path():
    client, _app = make_client()

    response = client.post("/reports/2026-04-18/resend")

    assert response.status_code == 204
    assert response.content == b""


def test_analysis_job_adapter_supports_frontend_create_poll_and_status():
    client, _app = make_client()

    created = client.post("/analysis-jobs", json={"query": "RSI 30 이하 종목 찾아줘"})

    assert created.status_code == 201
    job = created.json()
    assert job["job_id"]
    assert job["query"] == "RSI 30 이하 종목 찾아줘"
    assert job["result"]["status"] == "ready"
    assert job["result"]["strategy_spec"]["risk_constraints"]
    assert job["result"]["user_payload"]["report"]["web_projection"]["title"]

    fetched = client.get(f"/analysis-jobs/{job['job_id']}")
    status_response = client.get("/analysis-jobs/latest/status")

    assert fetched.status_code == 200
    assert fetched.json()["job_id"] == job["job_id"]
    assert status_response.status_code == 200
    assert status_response.json()["trace_id"] == job["trace_id"]
    assert status_response.json()["status"] == "ready"


def test_spec_compatibility_routes_are_available():
    client, _app = make_client()

    parsed = client.post("/api/strategies/parse", json={"natural_language": "반도체 모멘텀"})
    api_status = client.get("/api-status")
    backtest = client.get("/api/backtests/example-strategy")
    report = client.get("/api/reports/example-report")

    assert parsed.status_code == 201
    assert parsed.json()["result"]["strategy_spec"]["name"]
    assert api_status.status_code == 200
    assert api_status.json()["service"] == "QuantAgent Backend FE Contract API"
    assert backtest.status_code == 200
    assert backtest.json()["status"] == "ready"
    assert report.status_code == 200
    assert report.json()["user_payload"]["report"]["web_projection"]["summary"]


def test_notification_settings_round_trip_with_authenticated_session(monkeypatch):
    client, app = make_client()
    session_id, _csrf = asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id="user-1"))

    async def fake_load_user(_engine, user_id):
        assert user_id == "user-1"
        return {"id": "user-1", "email": "user@example.co.kr", "name": "User", "avatar_url": None}

    monkeypatch.setattr(fe_contract, "load_user_by_id", fake_load_user)

    initial = client.get("/me/notifications", cookies={"qa_session": session_id})
    saved = client.patch(
        "/me/notifications",
        cookies={"qa_session": session_id},
        headers={"Origin": API_ORIGIN},
        json={
            "dailyReportEmail": False,
            "actionEmails": True,
            "marketingEmail": False,
            "deliveryHour": "09:00",
            "email": "user@example.co.kr",
        },
    )
    after = client.get("/me/notifications", cookies={"qa_session": session_id})

    assert initial.status_code == 200
    assert initial.json()["dailyReportEmail"] is True
    assert saved.status_code == 200
    assert saved.json()["dailyReportEmail"] is False
    assert saved.json()["deliveryHour"] == "09:00"
    assert after.json()["dailyReportEmail"] is False


def test_unsubscribe_disables_daily_report_without_auth():
    client, _app = make_client()

    response = client.post("/unsubscribe", json={"email": "reader@example.co.kr"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "email": "reader@example.co.kr", "dailyReportEmail": False}
