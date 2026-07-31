from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import AppError
from app.db.session import execute_one, fetch_one

DEFAULT_NOTIFICATION_DELIVERY_HOUR = "08:00"
USER_PREFERENCES_COMPONENT = "user_preferences"


def _coerce_user_id(user_id: str | int) -> int:
    try:
        return int(user_id)
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=422,
            component=USER_PREFERENCES_COMPONENT,
            code="request_validation_failed",
            message="User id must be a positive integer",
            details={"user_id": user_id},
        ) from exc


def _normalize_email(email: str | None) -> str:
    value = (email or "").strip()
    if not value:
        raise AppError(
            status_code=422,
            component=USER_PREFERENCES_COMPONENT,
            code="request_validation_failed",
            message="Email is required",
            details={"email": email},
        )
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise AppError(
            status_code=422,
            component=USER_PREFERENCES_COMPONENT,
            code="request_validation_failed",
            message="Email format is invalid",
            details={"field": "email"},
        )
    return value


def _normalize_delivery_hour(delivery_hour: str | None) -> str | None:
    if delivery_hour is None:
        return None
    value = delivery_hour.strip()
    return value or None


def _default_notification_settings(email: str) -> dict[str, Any]:
    return {
        "dailyReportEmail": True,
        "actionEmails": True,
        "marketingEmail": False,
        "deliveryHour": DEFAULT_NOTIFICATION_DELIVERY_HOUR,
        "email": email,
    }


def _row_to_notification_settings(row: dict[str, Any], *, email: str) -> dict[str, Any]:
    resolved_email = str(row.get("email") or email).strip() or email
    delivery_hour = row.get("delivery_hour")
    return {
        "dailyReportEmail": bool(row.get("daily_report_email")),
        "actionEmails": bool(row.get("action_emails")),
        "marketingEmail": bool(row.get("marketing_email")),
        "deliveryHour": str(delivery_hour or DEFAULT_NOTIFICATION_DELIVERY_HOUR),
        "email": resolved_email,
    }


async def get_notification_settings(engine: AsyncEngine, *, user_id: str | int, email: str) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    row = await fetch_one(
        engine,
        """
        SELECT email, daily_report_email, action_emails, marketing_email, delivery_hour
        FROM app.users
        WHERE user_id = :user_id
        """,
        {"user_id": _coerce_user_id(user_id)},
    )
    if row is None:
        return _default_notification_settings(normalized_email)
    return _row_to_notification_settings(row, email=normalized_email)


async def save_notification_settings(
    engine: AsyncEngine,
    *,
    user_id: str | int,
    email: str,
    daily_report_email: bool | None = None,
    action_emails: bool | None = None,
    marketing_email: bool | None = None,
    delivery_hour: str | None = None,
) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    normalized_delivery_hour = _normalize_delivery_hour(delivery_hour)
    row = await execute_one(
        engine,
        """
        UPDATE app.users
        SET
            email = COALESCE(:email, app.users.email),
            daily_report_email = COALESCE(:daily_report_email, app.users.daily_report_email),
            action_emails = COALESCE(:action_emails, app.users.action_emails),
            marketing_email = COALESCE(:marketing_email, app.users.marketing_email),
            delivery_hour = COALESCE(:delivery_hour, app.users.delivery_hour),
            updated_at = now()
        WHERE user_id = :user_id
        RETURNING email, daily_report_email, action_emails, marketing_email, delivery_hour, created_at, updated_at
        """,
        {
            "user_id": _coerce_user_id(user_id),
            "email": normalized_email,
            "daily_report_email": daily_report_email,
            "action_emails": action_emails,
            "marketing_email": marketing_email,
            "delivery_hour": normalized_delivery_hour,
        },
    )
    if row is None:
        raise AppError(
            status_code=503,
            component=USER_PREFERENCES_COMPONENT,
            code="notification_settings_upsert_failed",
            message="Notification settings upsert returned no row",
        )
    return _row_to_notification_settings(row, email=normalized_email)
