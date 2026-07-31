from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.contract_policy import api_status_endpoints, fe_live_allowlist
from app.api.routes import email_reports
from app.api.routes.auth import get_session_cookie, get_session_store
from app.core.errors import AppError
from app.core.runtime_perf import measure_span, report_database_phase, set_report_metadata
from app.core.security import csrf_token_required, require_csrf_token, validate_unsafe_request_origin
from app.dependencies import get_db_engine, get_runtime_settings, get_trading_data_engine
from app.services import fe_contract_store

router = APIRouter(prefix="/api/v1", tags=["track-c"])
router.include_router(email_reports.router)


class TrackCRunRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    query: str | None = Field(default=None, min_length=1)
    strategyId: str | None = None
    strategy_id: str | None = None
    instrumentId: str | None = None
    instrument_id: str | None = None
    ticker: str | None = None
    aiJobId: str | None = None
    ai_job_id: str | None = None
    requestPayload: dict[str, Any] | None = None
    request_payload: dict[str, Any] | None = None


class TrackCRunCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str | None = None
    result: dict[str, Any] | None = None
    analysisResult: dict[str, Any] | None = None
    completedAt: str | None = None
    completed_at: str | None = None


async def _require_current_user_id(request: Request) -> str:
    with measure_span("auth"):
        store = get_session_store(request)
        with measure_span("cookie_parse"):
            session_id = get_session_cookie(request)
        user_id = await store.get_session_user_id(session_id)
        if not user_id:
            raise AppError(
                status_code=401,
                component="auth",
                code="not_authenticated",
                message="Authentication required",
            )
        return user_id


async def _require_track_c_csrf(request: Request) -> None:
    settings = get_runtime_settings(request)
    validate_unsafe_request_origin(request, settings)
    if not csrf_token_required(settings):
        return
    store = get_session_store(request)
    session_id = get_session_cookie(request)
    require_csrf_token(request.headers.get("X-CSRF-Token"), await store.get_csrf_token(session_id))


def _payload(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)


def _track_c_api_status() -> dict[str, Any]:
    return {
        "service": "QuantAgent Track C API",
        "schemaVersion": "qa.track_c.v1",
        "contract": "track-c-semantic",
        "endpoints": api_status_endpoints(),
        "feLiveAllowlist": [
            {"method": method, "path": path}
            for method, path in sorted(fe_live_allowlist())
        ],
    }


@router.get("/api-status")
async def get_api_status(request: Request) -> dict[str, Any]:
    return {
        **_track_c_api_status(),
        "tradingDataEngine": {
            "configured": getattr(request.app.state, "trading_data_db_engine", None) is not None,
        },
    }


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_analysis_run(request: Request, payload: TrackCRunRequest) -> dict[str, Any]:
    await _require_track_c_csrf(request)
    user_id = await _require_current_user_id(request)
    engine = get_trading_data_engine(request)
    identity_source_engine = get_db_engine(request)
    return await fe_contract_store.create_analysis_run_from_db(
        engine,
        user_id=user_id,
        payload=_payload(payload),
        identity_source_engine=identity_source_engine,
    )


@router.get("/runs/{run_id}")
async def get_analysis_run(request: Request, run_id: str) -> dict[str, Any]:
    user_id = await _require_current_user_id(request)
    engine = get_trading_data_engine(request)
    run = await fe_contract_store.get_analysis_run_from_db(engine, run_id, user_id=user_id)
    if run is None:
        raise AppError(
            status_code=404,
            component="analysis_runs",
            code="run_not_found",
            message="Analysis run was not found",
            details={"runId": run_id},
        )
    return run


@router.post("/runs/{run_id}/complete")
async def complete_analysis_run(request: Request, run_id: str, payload: TrackCRunCompletionRequest) -> dict[str, Any]:
    await _require_track_c_csrf(request)
    user_id = await _require_current_user_id(request)
    engine = get_trading_data_engine(request)
    identity_source_engine = get_db_engine(request)
    return await fe_contract_store.complete_analysis_run_from_db(
        engine,
        user_id=user_id,
        run_id=run_id,
        payload=_payload(payload),
        identity_source_engine=identity_source_engine,
        email_settings=get_runtime_settings(request),
    )

@router.get("/reports")
async def list_reports(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> dict[str, Any]:
    user_id = await _require_current_user_id(request)
    engine = get_trading_data_engine(request)
    with report_database_phase():
        result = await fe_contract_store.list_reports_from_db(
            engine,
            user_id=user_id,
            limit=limit,
            cursor=cursor,
            status=status,
            q=q,
        )
    items = result.get("items")
    meta = result.get("meta")
    set_report_metadata(
        row_count=len(items) if isinstance(items, list) else None,
        has_more=meta.get("hasMore") if isinstance(meta, dict) else None,
    )
    return result


@router.get("/reports/{report_id}")
async def get_report(request: Request, report_id: str) -> dict[str, Any]:
    user_id = await _require_current_user_id(request)
    engine = get_trading_data_engine(request)
    with report_database_phase():
        report = await fe_contract_store.get_report_from_db(engine, report_id, user_id=user_id)
    if report is None:
        set_report_metadata(row_count=0)
        raise AppError(
            status_code=404,
            component="reports",
            code="report_not_found",
            message="Report was not found",
            details={"reportId": report_id},
        )
    set_report_metadata(row_count=1)
    return report
