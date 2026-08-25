from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.errors import AppError
from app.db.session import fetch_all
from app.schemas.email_delivery_history import EmailDeliveryHistoryEntry, EmailDeliveryHistoryMeta, EmailDeliveryHistoryResponse

EMAIL_HISTORY_COMPONENT = "email_delivery_history"
VALID_FILTERS = {"all", "sent", "failed", "draft"}


def _encode_cursor(created_at: datetime, delivery_id: str) -> str:
    value = created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=UTC)
    payload = json.dumps({"created_at": value.astimezone(UTC).isoformat(), "delivery_id": delivery_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
        delivery_id = str(payload["delivery_id"])
        if not delivery_id:
            raise ValueError("empty delivery id")
        UUID(delivery_id)
        return created_at, delivery_id
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=422,
            component=EMAIL_HISTORY_COMPONENT,
            code="email_delivery_history_invalid_cursor",
            message="Email delivery cursor is invalid",
        ) from exc


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_entry(row: dict[str, Any]) -> EmailDeliveryHistoryEntry:
    metadata = _metadata(row.get("metadata_jsonb"))
    submission_status = str(metadata.get("submission_status") or "PENDING").upper()
    provider_submission_status = metadata.get("provider_submission_status")
    provider_delivery_status = metadata.get("provider_delivery_status")
    if provider_delivery_status == "accepted":
        provider_delivery_status = "pending"
    if provider_submission_status is None and submission_status == "SENT":
        provider_submission_status = "accepted"
    database_status = str(row.get("status") or "draft").lower()
    last_event_at = _as_datetime(metadata.get("last_event_at"))
    failed_at = last_event_at if submission_status in {"FAILED", "CANCELLED"} else None
    return EmailDeliveryHistoryEntry(
        deliveryId=str(row["delivery_id"]),
        reportId=str(row["report_id"]) if row.get("report_id") else None,
        reportTitle=row.get("report_title"),
        strategyId=row.get("strategy_id"),
        strategyName=row.get("strategy_name"),
        triggerType=str(metadata.get("trigger_type") or "report_completed"),
        templateName=str(metadata.get("template_name") or "report_completed"),
        submissionStatus=submission_status,
        providerSubmissionStatus=provider_submission_status,
        providerDeliveryStatus=provider_delivery_status,
        providerStatusCheckedAt=_as_datetime(metadata.get("provider_status_checked_at")),
        providerEventAt=_as_datetime(metadata.get("provider_event_at")),
        providerStatusSource=metadata.get("provider_status_source"),
        status=database_status,
        reportDate=str(row["report_date"]) if row.get("report_date") else None,
        createdAt=row["created_at"],
        sentAt=row.get("sent_at"),
        deliveredAt=_as_datetime(metadata.get("delivered_at")),
        failedAt=failed_at,
        lastEventAt=last_event_at,
        attemptCount=int(metadata.get("attempt_count") or 0),
        maxAttempts=int(metadata.get("max_attempts") or 0),
        safeFailureCategory=metadata.get("safe_failure_category"),
    )


async def list_email_deliveries(
    db: Any,
    *,
    user_id: str | int,
    limit: int = 20,
    cursor: str | None = None,
    status: str | None = None,
) -> EmailDeliveryHistoryResponse:
    if limit < 1 or limit > 100:
        raise AppError(
            status_code=422,
            component=EMAIL_HISTORY_COMPONENT,
            code="email_delivery_history_limit_invalid",
            message="Email delivery history limit must be between 1 and 100",
        )
    normalized_filter = (status or "all").strip().lower()
    if normalized_filter not in VALID_FILTERS:
        raise AppError(
            status_code=422,
            component=EMAIL_HISTORY_COMPONENT,
            code="email_delivery_history_invalid_filter",
            message="Email delivery history status filter is invalid",
        )
    decoded = _decode_cursor(cursor)
    filter_sql = {
        "all": "TRUE",
        "sent": "delivery.status IN ('sent', 'resent')",
        "failed": "delivery.status = 'failed'",
        "draft": "delivery.status = 'draft'",
    }[normalized_filter]
    cursor_sql = "TRUE"
    params: dict[str, Any] = {"user_id": int(user_id), "limit": limit + 1}
    if decoded is not None:
        cursor_sql = "(delivery.created_at, delivery.delivery_id) < (:cursor_created_at, CAST(:cursor_delivery_id AS uuid))"
        params.update({"cursor_created_at": decoded[0], "cursor_delivery_id": decoded[1]})
    rows = await fetch_all(
        db,
        f"""
        SELECT
            delivery.delivery_id,
            delivery.report_id,
            delivery.strategy_id,
            delivery.status,
            delivery.sent_at,
            delivery.metadata_jsonb,
            delivery.created_at,
            report.title AS report_title,
            report.report_date,
            profile.name AS strategy_name
        FROM app.email_delivery_history AS delivery
        LEFT JOIN app.strategy_email_report AS report ON report.report_id = delivery.report_id
        LEFT JOIN app.strategy_report_profile AS profile
          ON profile.strategy_id = COALESCE(delivery.strategy_id, report.strategy_id)
        WHERE delivery.user_id = CAST(:user_id AS bigint)
          AND {filter_sql}
          AND {cursor_sql}
        ORDER BY delivery.created_at DESC, delivery.delivery_id DESC
        LIMIT :limit
        """,
        params,
    )
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = None
    if has_more and page_rows:
        next_cursor = _encode_cursor(page_rows[-1]["created_at"], str(page_rows[-1]["delivery_id"]))
    return EmailDeliveryHistoryResponse(
        items=[_to_entry(row) for row in page_rows],
        meta=EmailDeliveryHistoryMeta(limit=limit, hasMore=has_more, nextCursor=next_cursor),
    )
