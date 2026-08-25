from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.api.routes.auth import get_session_cookie, get_session_store
from app.core.errors import AppError
from app.core.security import csrf_token_required, require_csrf_token, validate_unsafe_request_origin
from app.db import email_delivery_history as email_delivery_history_db
from app.db import user_preferences
from app.db.user_queries import load_user_by_id
from app.dependencies import get_db_engine, get_runtime_settings
from app.schemas.email_delivery_history import EmailDeliveryHistoryResponse
from app.schemas.email_unsubscribe import UnsubscribeInspectionResponse, UnsubscribeMutationResponse
from app.services import email_delivery, email_unsubscribe

router = APIRouter(tags=["email-reports"])


class NotificationSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dailyReportEmail: StrictBool | None = None
    email: str | None = Field(default=None, min_length=3)
    actionEmails: StrictBool | None = None
    marketingEmail: StrictBool | None = None
    deliveryHour: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class UnsubscribeTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)


async def _require_current_user_id(request: Request) -> str:
    store = get_session_store(request)
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


async def _require_csrf(request: Request) -> None:
    settings = get_runtime_settings(request)
    validate_unsafe_request_origin(request, settings)
    if not csrf_token_required(settings):
        return
    session_id = get_session_cookie(request)
    provided_token = request.headers.get("X-CSRF-Token")
    store = get_session_store(request)
    stored_token = await store.get_csrf_token(session_id)
    require_csrf_token(provided_token, stored_token)


async def _current_user(request: Request) -> dict[str, Any]:
    user_id = await _require_current_user_id(request)
    user = await load_user_by_id(get_db_engine(request), user_id)
    if user is None:
        raise AppError(
            status_code=401,
            component="auth",
            code="user_session_invalid",
            message="Session user is unavailable",
        )
    return user


@router.get("/me/notifications")
async def get_my_notification_settings(request: Request) -> dict[str, Any]:
    user = await _current_user(request)
    return await user_preferences.get_notification_settings(
        get_db_engine(request),
        user_id=str(user["id"]),
        email=str(user["email"]),
    )


@router.patch("/me/notifications")
async def patch_my_notification_settings(request: Request, payload: NotificationSettingsRequest) -> dict[str, Any]:
    await _require_csrf(request)
    user = await _current_user(request)
    return await user_preferences.save_notification_settings(
        get_db_engine(request),
        user_id=str(user["id"]),
        email=payload.email or str(user["email"]),
        daily_report_email=payload.dailyReportEmail,
        action_emails=payload.actionEmails,
        marketing_email=payload.marketingEmail,
        delivery_hour=payload.deliveryHour,
    )


def _retired_subscription_route() -> None:
    raise AppError(
        status_code=410,
        component="email_reports",
        code="daily_digest_subscriptions_retired",
        message="정기 다이제스트 구독은 현재 제공하지 않습니다.",
    )


@router.api_route(
    "/me/email-strategy-subscriptions",
    methods=["GET", "POST"],
    response_model=None,
)
async def retired_email_strategy_subscriptions() -> None:
    _retired_subscription_route()


@router.delete("/me/email-strategy-subscriptions/{strategy_id}", response_model=None)
async def retired_email_strategy_subscription(strategy_id: str) -> None:
    _retired_subscription_route()


@router.get("/me/email-deliveries", response_model=EmailDeliveryHistoryResponse)
async def get_my_email_deliveries(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> EmailDeliveryHistoryResponse:
    user_id = await _require_current_user_id(request)
    return await email_delivery_history_db.list_email_deliveries(
        get_db_engine(request), user_id=user_id, limit=limit, cursor=cursor, status=status
    )


@router.post("/reports/{report_id}/resend")
async def resend_report_email(request: Request, report_id: str) -> Response:
    await _require_csrf(request)
    user = await _current_user(request)
    result = await email_delivery.create_report_completed_delivery(
        get_db_engine(request),
        settings=get_runtime_settings(request),
        user_id=str(user["id"]),
        report_id=report_id,
    )
    if result["delivery"] is None:
        raise AppError(
            status_code=409,
            component="email_reports",
            code="email_resend_unavailable",
            message="Report resend delivery is unavailable",
            details={"reportId": report_id},
        )
    return Response(status_code=204)


@router.get("/unsubscribe", response_model=UnsubscribeInspectionResponse)
async def inspect_unsubscribe(request: Request, token: str | None = Query(default=None)) -> dict[str, Any]:
    return await email_unsubscribe.inspect_unsubscribe_token(
        get_db_engine(request), get_runtime_settings(request), token=token
    )


@router.post("/unsubscribe", response_model=UnsubscribeMutationResponse)
async def confirm_unsubscribe(request: Request, payload: UnsubscribeTokenRequest) -> dict[str, Any]:
    return await email_unsubscribe.confirm_unsubscribe(
        get_db_engine(request), get_runtime_settings(request), token=payload.token
    )
