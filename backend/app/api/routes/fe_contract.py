from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.routes.auth import get_session_cookie, get_session_store
from app.core.errors import AppError
from app.core.security import (
    csrf_token_required,
    public_user_payload,
    require_csrf_token,
    validate_unsafe_request_origin,
)
from app.db.user_queries import load_user_by_id
from app.dependencies import get_db_engine, get_runtime_settings
from app.services import fe_contract_store

router = APIRouter(tags=["fe-contract"])


class CreateAnalysisJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)


class ParseStrategyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    natural_language: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    strategy_id: str | None = None
    client_request_id: str | None = None


class NotificationSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dailyReportEmail: bool
    actionEmails: bool
    marketingEmail: bool
    deliveryHour: str = Field(min_length=1)
    email: str = Field(min_length=1)


class UnsubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    token: str | None = None


@router.get("/landing-sample")
async def get_landing_sample() -> dict[str, Any]:
    return fe_contract_store.landing_sample()


@router.get("/workspace/template")
async def get_workspace_template() -> dict[str, Any]:
    return fe_contract_store.workspace_template()


@router.get("/app/overview")
async def get_app_overview() -> dict[str, Any]:
    return fe_contract_store.app_overview()


@router.get("/trading-candidates")
async def get_trading_candidates() -> list[dict[str, Any]]:
    return fe_contract_store.trading_candidates()


@router.get("/performance/summary")
async def get_performance_summary() -> dict[str, Any]:
    return fe_contract_store.performance_summary()


@router.get("/reports")
async def get_reports() -> list[dict[str, Any]]:
    return fe_contract_store.report_summaries()


@router.get("/reports/{report_id}")
async def get_report_by_id(report_id: str) -> JSONResponse:
    return JSONResponse(fe_contract_store.report_detail_or_none(report_id))


@router.post("/reports/{report_id}/resend", status_code=status.HTTP_204_NO_CONTENT)
async def resend_report_email(report_id: str) -> Response:
    if not report_id.strip():
        raise AppError(status_code=400, component="reports", code="invalid_report_id", message="Report id is required")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/notifications")
async def get_my_notification_settings(request: Request) -> dict[str, Any]:
    user = await _require_current_user(request)
    return fe_contract_store.get_notification_settings(request, str(user["email"]))


@router.patch("/me/notifications")
async def patch_my_notification_settings(request: Request, payload: NotificationSettingsRequest) -> dict[str, Any]:
    settings = get_runtime_settings(request)
    validate_unsafe_request_origin(request, settings)
    store = get_session_store(request)
    if csrf_token_required(settings):
        require_csrf_token(request.headers.get("X-CSRF-Token"), await store.get_csrf_token(get_session_cookie(request)))
    user = await _require_current_user(request)
    next_settings = payload.model_dump()
    next_settings["email"] = next_settings.get("email") or user["email"]
    return fe_contract_store.save_notification_settings(request, next_settings)


@router.post("/unsubscribe")
async def unsubscribe_daily_report(request: Request, payload: UnsubscribeRequest) -> dict[str, Any]:
    current = fe_contract_store.get_notification_settings(request, payload.email)
    next_settings = {**current, "email": payload.email, "dailyReportEmail": False}
    saved = fe_contract_store.save_notification_settings(request, next_settings)
    return {"ok": True, "email": saved["email"], "dailyReportEmail": False}


@router.post("/strategies", status_code=status.HTTP_201_CREATED)
async def create_strategy(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    return fe_contract_store.create_strategy(request, payload)


@router.patch("/strategies/{strategy_id}")
async def patch_strategy(request: Request, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return fe_contract_store.update_strategy(request, strategy_id, payload)


@router.put("/strategies/{strategy_id}")
async def put_strategy(request: Request, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return fe_contract_store.update_strategy(request, strategy_id, payload)


@router.post("/strategies/{strategy_id}/analysis-runs", status_code=status.HTTP_201_CREATED)
async def run_strategy_analysis(request: Request, strategy_id: str) -> dict[str, Any]:
    strategy = fe_contract_store.strategy_store(request).get(strategy_id)
    query = str((strategy or {}).get("natural_language_strategy") or f"Run strategy {strategy_id}")
    return fe_contract_store.create_analysis_job(request, query, strategy_id=strategy_id)


@router.post("/analysis-jobs", status_code=status.HTTP_201_CREATED)
async def create_analysis_job(request: Request, payload: CreateAnalysisJobRequest) -> dict[str, Any]:
    return fe_contract_store.create_analysis_job(request, payload.query.strip())


@router.get("/analysis-jobs/latest/status")
async def get_latest_analysis_job_status(request: Request) -> dict[str, Any]:
    return fe_contract_store.latest_analysis_job_status(request)


@router.get("/analysis-jobs/{job_id}")
async def get_analysis_job(request: Request, job_id: str) -> dict[str, Any]:
    return fe_contract_store.require_analysis_job(fe_contract_store.get_analysis_job(request, job_id))


@router.post("/api/strategies/parse", status_code=status.HTTP_201_CREATED)
async def parse_strategy(request: Request, payload: ParseStrategyRequest) -> dict[str, Any]:
    query = (payload.natural_language or payload.query or "").strip()
    if not query:
        raise AppError(status_code=422, component="analysis_jobs", code="query_required", message="natural_language or query is required")
    return fe_contract_store.create_analysis_job(request, query, strategy_id=payload.strategy_id)


@router.get("/api/analysis-jobs/{job_id}")
async def get_compat_analysis_job(request: Request, job_id: str) -> dict[str, Any]:
    return await get_analysis_job(request, job_id)


@router.get("/api/backtests/{strategy_id}")
async def get_compat_backtest(strategy_id: str) -> dict[str, Any]:
    envelope = fe_contract_store.contract_value("readyEnvelope")
    envelope["debug_ref"] = f"backend_fe_contract:backtest:{strategy_id}"
    return envelope


@router.get("/api/reports/{report_id}")
async def get_compat_report(report_id: str) -> dict[str, Any]:
    job = fe_contract_store.build_analysis_job(job_id=f"compat-{report_id}", query=f"Report {report_id}")
    return job["result"]


@router.get("/api-status")
async def get_api_status() -> dict[str, Any]:
    return {
        "service": "QuantAgent Backend FE Contract API",
        "schema_version": "qa.fe_contract.v1",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
        "data_source": {
            "configured": True,
            "dsn_env": "BACKEND_STATIC_FE_CONTRACT",
            "price_source": "backend/app/data/fe_mock_contract.json",
            "universe_source": "backend/app/data/fe_mock_contract.json",
            "l4_evidence_source": "backend/app/data/fe_mock_contract.json",
            "macro_source": "backend/app/data/fe_mock_contract.json",
            "macro_usable": True,
            "fallback_when_unset": "static_contract",
        },
        "job_store": {
            "requested_mode": "backend_memory",
            "active_mode": "backend_memory",
            "mode_env": "BACKEND_FE_CONTRACT_JOB_STORE",
            "dsn_env": "DATABASE_URL",
            "dsn_configured": False,
            "fallback": True,
            "fallback_reason": "FE contract adapter uses in-memory jobs until app.analysis_runs is introduced.",
        },
        "endpoints": [
            {"method": "GET", "path": "/landing-sample", "state": "available", "summary": "Landing mock contract."},
            {"method": "GET", "path": "/app/overview", "state": "available", "summary": "Workspace overview contract."},
            {"method": "GET", "path": "/reports", "state": "available", "summary": "Report summary contract."},
            {"method": "POST", "path": "/analysis-jobs", "state": "available", "summary": "FE-compatible analysis job adapter."},
        ],
    }


async def _require_current_user(request: Request) -> dict[str, Any]:
    store = get_session_store(request)
    user_id = await store.get_session_user_id(get_session_cookie(request))
    if not user_id:
        raise AppError(status_code=401, component="auth", code="not_authenticated", message="Authentication required")
    user = await load_user_by_id(get_db_engine(request), user_id)
    if not user:
        raise AppError(status_code=401, component="auth", code="user_session_invalid", message="Session user is unavailable")
    return public_user_payload(user)
