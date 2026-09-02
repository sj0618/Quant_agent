from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.core.config import redact_secrets
from app.core.errors import AppError
from app.db.session import execute_one, fetch_one
from app.schemas.email_delivery import EmailDeliveryCreateRequest

EMAIL_OUTBOX_COMPONENT = "email_delivery_outbox"
EMAIL_OUTBOX_STALE_CLAIM_CODE = "email_delivery_outbox_stale_claim"
EMAIL_ADDRESS_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str:
    effective = value or _now()
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=UTC)
    return effective.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _safe_error(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = EMAIL_ADDRESS_PATTERN.sub("<redacted-email>", str(redact_secrets(value))).strip()
    return normalized[:497] + "..." if len(normalized) > 500 else normalized


def _normalize_error_code(value: str | None) -> str:
    normalized = "".join(character for character in (value or "unknown_error").lower() if character.isalnum() or character in "_-")
    return normalized[:80] or "unknown_error"


def _row_to_delivery(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(row.get("metadata_jsonb"))
    database_status = str(row.get("status") or "draft").lower()
    fallback_status = {"sent": "SENT", "failed": "FAILED", "resent": "SENT"}.get(database_status, "PENDING")
    submission_status = str(metadata.get("submission_status") or fallback_status).upper()
    return {
        **row,
        "delivery_id": str(row.get("delivery_id") or ""),
        "user_id": str(row.get("user_id") or ""),
        "report_id": str(row.get("report_id") or ""),
        "strategy_id": row.get("strategy_id"),
        "status": submission_status,
        "submission_status": submission_status,
        "trigger_type": metadata.get("trigger_type") or "report_completed",
        "template_name": metadata.get("template_name") or "report_completed",
        "template_version": metadata.get("template_version") or "v1",
        "idempotency_key": metadata.get("idempotency_key"),
        "payload_jsonb": _metadata(metadata.get("payload")),
        "attempt_count": int(metadata.get("attempt_count") or 0),
        "max_attempts": int(metadata.get("max_attempts") or 1),
        "available_at": metadata.get("available_at"),
        "claim_token": metadata.get("claim_token"),
        "claim_expires_at": metadata.get("claim_expires_at"),
        "claimed_by": metadata.get("claimed_by"),
        "correlation_id": metadata.get("correlation_id"),
        "provider_submission_status": metadata.get("provider_submission_status"),
        "provider_delivery_status": metadata.get("provider_delivery_status"),
        "provider_status_checked_at": metadata.get("provider_status_checked_at"),
        "provider_event_at": metadata.get("provider_event_at"),
        "provider_status_source": metadata.get("provider_status_source"),
        "safe_failure_category": metadata.get("safe_failure_category"),
        "last_event_at": metadata.get("last_event_at"),
        "metadata_jsonb": metadata,
    }


def build_email_delivery_idempotency_key(
    *, user_id: str | int, report_id: str, trigger_type: str, template_version: str
) -> str:
    return f"report-email:{int(user_id)}:{report_id}:{trigger_type}:{template_version}"


def deterministic_delivery_id(idempotency_key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"quantagent-email:{idempotency_key}"))


async def get_delivery(db: Any, delivery_id: str) -> dict[str, Any] | None:
    row = await fetch_one(
        db,
        "SELECT * FROM app.email_delivery_history WHERE delivery_id = CAST(:delivery_id AS uuid)",
        {"delivery_id": delivery_id},
    )
    return _row_to_delivery(row) if row is not None else None


async def get_queue_readiness_snapshot(db: Any, *, now: datetime | None = None) -> dict[str, Any]:
    effective_now = now or _now()
    counts = await fetch_one(
        db,
        """
        SELECT
            COUNT(*) FILTER (
                WHERE status = 'draft'
                  AND metadata_jsonb ->> 'submission_status' IN ('PENDING', 'RETRY_PENDING')
                  AND CAST(metadata_jsonb ->> 'available_at' AS timestamptz) <= CAST(:now AS timestamptz)
            ) AS due_count,
            COUNT(*) FILTER (
                WHERE status = 'draft'
                  AND metadata_jsonb ->> 'submission_status' = 'PROCESSING'
            ) AS processing_count,
            COUNT(*) FILTER (
                WHERE status = 'draft'
                  AND metadata_jsonb ->> 'submission_status' = 'PROCESSING'
                  AND CAST(metadata_jsonb ->> 'claim_expires_at' AS timestamptz) <= CAST(:now AS timestamptz)
            ) AS stale_claim_count
        FROM app.email_delivery_history
        """,
        {"now": effective_now},
    ) or {}
    latest = await fetch_one(
        db,
        """
        SELECT
            COALESCE(
                NULLIF(metadata_jsonb ->> 'safe_failure_category', ''),
                NULLIF(lower(metadata_jsonb ->> 'submission_status'), ''),
                lower(status),
                'none'
            ) AS outcome_category
        FROM app.email_delivery_history
        ORDER BY COALESCE(
            CAST(metadata_jsonb ->> 'last_event_at' AS timestamptz),
            sent_at,
            created_at
        ) DESC NULLS LAST
        LIMIT 1
        """,
        {},
    )
    return {
        "due_count": int(counts.get("due_count") or 0),
        "processing_count": int(counts.get("processing_count") or 0),
        "stale_claim_count": int(counts.get("stale_claim_count") or 0),
        "last_outcome_category": _normalize_error_code(latest.get("outcome_category")) if latest else "none",
    }


async def create_or_get_delivery(db: Any, request: EmailDeliveryCreateRequest) -> dict[str, Any]:
    delivery_id = deterministic_delivery_id(request.idempotency_key)
    metadata = {
        "submission_status": "PENDING",
        "trigger_type": request.trigger_type,
        "template_name": request.template_name,
        "template_version": request.template_version,
        "idempotency_key": request.idempotency_key,
        "payload": request.payload_json,
        "attempt_count": 0,
        "max_attempts": request.max_attempts,
        "available_at": _iso(request.available_at),
        "correlation_id": request.correlation_id,
        "provider_submission_status": None,
        "provider_delivery_status": None,
        "provider_status_checked_at": None,
        "provider_event_at": None,
        "provider_status_source": None,
        "safe_failure_category": None,
    }
    row = await execute_one(
        db,
        """
        INSERT INTO app.email_delivery_history (
            delivery_id, user_id, report_id, strategy_id, recipient_email,
            status, provider, metadata_jsonb
        )
        VALUES (
            CAST(:delivery_id AS uuid), CAST(:user_id AS bigint), :report_id, :strategy_id, :recipient_email,
            'draft', :provider, CAST(:metadata_json AS jsonb)
        )
        ON CONFLICT (delivery_id) DO NOTHING
        RETURNING *
        """,
        {
            "delivery_id": delivery_id,
            "user_id": request.user_id,
            "report_id": request.report_id,
            "strategy_id": request.payload_json.get("strategyId"),
            "recipient_email": request.recipient_email,
            "provider": request.provider,
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
        },
    )
    created = row is not None
    if row is None:
        row = await fetch_one(
            db,
            "SELECT * FROM app.email_delivery_history WHERE delivery_id = CAST(:delivery_id AS uuid)",
            {"delivery_id": delivery_id},
        )
    if row is None:
        raise AppError(
            status_code=503,
            component=EMAIL_OUTBOX_COMPONENT,
            code="email_delivery_outbox_unavailable",
            message="Email delivery could not be persisted",
        )
    return {**_row_to_delivery(row), "created": created, "reused": not created}


async def requeue_delivery(
    db: Any,
    *,
    delivery_id: str,
    recipient_email: str | None = None,
    payload_json: dict[str, Any] | None = None,
    cooldown_seconds: int = 0,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Re-queue a terminal delivery for an explicit resend.

    Returns None when the row is not terminal or its last event is younger than
    ``cooldown_seconds`` (an unthrottled resend button would otherwise be a send loop).
    The fresh recipient and rendered payload replace the stored ones so a changed
    address or template is what actually goes out.
    """

    effective_now = now or _now()
    row = await execute_one(
        db,
        """
        UPDATE app.email_delivery_history
        SET status = 'draft', error_message = NULL, sent_at = NULL, provider_message_id = NULL,
            recipient_email = COALESCE(CAST(:recipient_email AS text), recipient_email),
            metadata_jsonb = metadata_jsonb || jsonb_build_object(
                'submission_status', 'PENDING',
                'attempt_count', 0,
                'available_at', CAST(:now AS timestamptz),
                'payload', COALESCE(CAST(:payload_json AS jsonb), metadata_jsonb -> 'payload'),
                'claim_token', NULL, 'claim_expires_at', NULL, 'claimed_by', NULL,
                'provider_submission_status', NULL, 'provider_delivery_status', NULL,
                'provider_status_checked_at', NULL, 'provider_event_at', NULL,
                'provider_status_source', NULL, 'safe_failure_category', NULL,
                'last_event_at', CAST(:now AS timestamptz)
            )
        WHERE delivery_id = CAST(:delivery_id AS uuid)
          AND COALESCE(metadata_jsonb ->> 'submission_status', upper(status)) IN ('SENT', 'FAILED', 'CANCELLED')
          AND COALESCE(
                CAST(metadata_jsonb ->> 'last_event_at' AS timestamptz), sent_at, created_at
              ) <= CAST(:now AS timestamptz) - CAST(:cooldown_seconds AS integer) * interval '1 second'
        RETURNING *
        """,
        {
            "delivery_id": delivery_id,
            "recipient_email": recipient_email,
            "payload_json": json.dumps(payload_json, ensure_ascii=False) if payload_json is not None else None,
            "cooldown_seconds": max(0, int(cooldown_seconds)),
            "now": effective_now,
        },
    )
    return _row_to_delivery(row) if row is not None else None


async def release_expired_claims(
    db: Any,
    *,
    now: datetime | None = None,
    delivery_scope_id: str | None = None,
) -> list[dict[str, Any]]:
    effective_now = now or _now()
    rows: list[dict[str, Any]] = []
    while True:
        row = await execute_one(
            db,
            """
            WITH candidate AS (
                SELECT delivery_id
                FROM app.email_delivery_history
                WHERE status = 'draft'
                  AND metadata_jsonb ->> 'submission_status' = 'PROCESSING'
                  AND CAST(metadata_jsonb ->> 'claim_expires_at' AS timestamptz) <= CAST(:now AS timestamptz)
                  AND (
                      CAST(:delivery_scope_id AS uuid) IS NULL
                      OR delivery_id = CAST(:delivery_scope_id AS uuid)
                  )
                ORDER BY created_at, delivery_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE app.email_delivery_history AS delivery
            SET status = CASE
                    WHEN COALESCE((delivery.metadata_jsonb ->> 'attempt_count')::int, 0)
                       >= COALESCE((delivery.metadata_jsonb ->> 'max_attempts')::int, 1)
                    THEN 'failed' ELSE 'draft' END,
                error_message = 'claim_expired',
                metadata_jsonb = delivery.metadata_jsonb || jsonb_build_object(
                    'submission_status', CASE
                        WHEN COALESCE((delivery.metadata_jsonb ->> 'attempt_count')::int, 0)
                           >= COALESCE((delivery.metadata_jsonb ->> 'max_attempts')::int, 1)
                        THEN 'FAILED' ELSE 'RETRY_PENDING' END,
                    'available_at', CAST(:now AS timestamptz),
                    'claim_token', NULL,
                    'claim_expires_at', NULL,
                    'claimed_by', NULL,
                    'safe_failure_category', 'claim_expired',
                    'last_event_at', CAST(:now AS timestamptz)
                )
            FROM candidate
            WHERE delivery.delivery_id = candidate.delivery_id
            RETURNING delivery.*
            """,
            {"now": effective_now, "delivery_scope_id": delivery_scope_id},
        )
        if row is None:
            break
        rows.append(_row_to_delivery(row))
    return rows


async def claim_next_delivery(
    db: Any,
    *,
    claimed_by: str,
    claim_ttl_seconds: int,
    now: datetime | None = None,
    delivery_scope_id: str | None = None,
) -> dict[str, Any] | None:
    effective_now = now or _now()
    claim_expires_at = effective_now + timedelta(seconds=max(1, int(claim_ttl_seconds)))
    claim_token = str(uuid4())
    row = await execute_one(
        db,
        """
        WITH candidate AS (
            SELECT delivery_id
            FROM app.email_delivery_history
            WHERE status = 'draft'
              AND metadata_jsonb ->> 'submission_status' IN ('PENDING', 'RETRY_PENDING')
              AND CAST(metadata_jsonb ->> 'available_at' AS timestamptz) <= CAST(:now AS timestamptz)
              AND COALESCE((metadata_jsonb ->> 'attempt_count')::int, 0)
                  < COALESCE((metadata_jsonb ->> 'max_attempts')::int, 1)
              AND (
                  CAST(:delivery_scope_id AS uuid) IS NULL
                  OR delivery_id = CAST(:delivery_scope_id AS uuid)
              )
            ORDER BY CAST(metadata_jsonb ->> 'available_at' AS timestamptz), created_at, delivery_id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE app.email_delivery_history AS delivery
        SET metadata_jsonb = delivery.metadata_jsonb || jsonb_build_object(
                'submission_status', 'PROCESSING',
                'attempt_count', COALESCE((delivery.metadata_jsonb ->> 'attempt_count')::int, 0) + 1,
                'claim_token', CAST(:claim_token AS text),
                'claim_expires_at', CAST(:claim_expires_at AS timestamptz),
                'claimed_by', CAST(:claimed_by AS text),
                'last_event_at', CAST(:now AS timestamptz)
            )
        FROM candidate
        WHERE delivery.delivery_id = candidate.delivery_id
        RETURNING delivery.*
        """,
        {
            "now": effective_now,
            "claim_token": claim_token,
            "claim_expires_at": claim_expires_at,
            "claimed_by": claimed_by,
            "delivery_scope_id": delivery_scope_id,
        },
    )
    return _row_to_delivery(row) if row is not None else None


def _raise_stale_claim(delivery_id: str) -> None:
    raise AppError(
        status_code=409,
        component=EMAIL_OUTBOX_COMPONENT,
        code=EMAIL_OUTBOX_STALE_CLAIM_CODE,
        message="Email delivery claim is no longer current",
        details={"delivery_id": delivery_id},
    )


async def mark_sent(
    db: Any, *, delivery_id: str, claim_token: str, provider_message_id: str | None = None
) -> dict[str, Any]:
    now = _now()
    row = await execute_one(
        db,
        """
        UPDATE app.email_delivery_history
        SET status = 'sent', sent_at = CAST(:now AS timestamptz),
            provider_message_id = CAST(:provider_message_id AS text), error_message = NULL,
            metadata_jsonb = metadata_jsonb || jsonb_build_object(
                'submission_status', 'SENT',
                'provider_submission_status', 'accepted',
                'provider_delivery_status', 'pending',
                'provider_status_checked_at', CAST(:now AS timestamptz),
                'provider_event_at', NULL,
                'provider_status_source', 'provider_response',
                'claim_token', NULL, 'claim_expires_at', NULL, 'claimed_by', NULL,
                'safe_failure_category', NULL, 'last_event_at', CAST(:now AS timestamptz)
            )
        WHERE delivery_id = CAST(:delivery_id AS uuid)
          AND metadata_jsonb ->> 'submission_status' = 'PROCESSING'
          AND metadata_jsonb ->> 'claim_token' = :claim_token
        RETURNING *
        """,
        {"delivery_id": delivery_id, "claim_token": claim_token, "provider_message_id": provider_message_id, "now": now},
    )
    if row is None:
        _raise_stale_claim(delivery_id)
    return _row_to_delivery(row)


async def mark_retry_pending(
    db: Any,
    *,
    delivery_id: str,
    claim_token: str,
    available_at: datetime,
    error_code: str | None,
    error_message: str | None,
    provider_message_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    category = _normalize_error_code(error_code)
    row = await execute_one(
        db,
        """
        UPDATE app.email_delivery_history
        SET status = CASE
                WHEN COALESCE((metadata_jsonb ->> 'attempt_count')::int, 0)
                   < COALESCE((metadata_jsonb ->> 'max_attempts')::int, 1)
                THEN 'draft' ELSE 'failed' END,
            provider_message_id = COALESCE(:provider_message_id, provider_message_id),
            error_message = :error_message,
            metadata_jsonb = metadata_jsonb || jsonb_build_object(
                'submission_status', CASE
                    WHEN COALESCE((metadata_jsonb ->> 'attempt_count')::int, 0)
                       < COALESCE((metadata_jsonb ->> 'max_attempts')::int, 1)
                    THEN 'RETRY_PENDING' ELSE 'FAILED' END,
                'available_at', CAST(:available_at AS timestamptz),
                'claim_token', NULL, 'claim_expires_at', NULL, 'claimed_by', NULL,
                'safe_failure_category', CAST(:category AS text),
                'last_event_at', CAST(:now AS timestamptz)
            )
        WHERE delivery_id = CAST(:delivery_id AS uuid)
          AND metadata_jsonb ->> 'submission_status' = 'PROCESSING'
          AND metadata_jsonb ->> 'claim_token' = :claim_token
        RETURNING *
        """,
        {
            "delivery_id": delivery_id,
            "claim_token": claim_token,
            "available_at": available_at,
            "error_message": _safe_error(error_message),
            "provider_message_id": provider_message_id,
            "category": category,
            "now": now,
        },
    )
    if row is None:
        _raise_stale_claim(delivery_id)
    return _row_to_delivery(row)


async def mark_failed(
    db: Any,
    *,
    delivery_id: str,
    claim_token: str,
    error_code: str | None,
    error_message: str | None,
    provider_message_id: str | None = None,
) -> dict[str, Any]:
    now = _now()
    category = _normalize_error_code(error_code)
    row = await execute_one(
        db,
        """
        UPDATE app.email_delivery_history
        SET status = 'failed', provider_message_id = COALESCE(:provider_message_id, provider_message_id),
            error_message = :error_message,
            metadata_jsonb = metadata_jsonb || jsonb_build_object(
                'submission_status', 'FAILED', 'claim_token', NULL, 'claim_expires_at', NULL,
                'claimed_by', NULL, 'safe_failure_category', CAST(:category AS text),
                'last_event_at', CAST(:now AS timestamptz)
            )
        WHERE delivery_id = CAST(:delivery_id AS uuid)
          AND metadata_jsonb ->> 'submission_status' = 'PROCESSING'
          AND metadata_jsonb ->> 'claim_token' = :claim_token
        RETURNING *
        """,
        {
            "delivery_id": delivery_id,
            "claim_token": claim_token,
            "error_message": _safe_error(error_message),
            "provider_message_id": provider_message_id,
            "category": category,
            "now": now,
        },
    )
    if row is None:
        _raise_stale_claim(delivery_id)
    return _row_to_delivery(row)


async def mark_cancelled(
    db: Any,
    *,
    delivery_id: str,
    claim_token: str,
    error_code: str | None,
    error_message: str | None = None,
) -> dict[str, Any]:
    now = _now()
    row = await execute_one(
        db,
        """
        UPDATE app.email_delivery_history
        SET status = 'failed', error_message = :error_message,
            metadata_jsonb = metadata_jsonb || jsonb_build_object(
                'submission_status', 'CANCELLED', 'claim_token', NULL, 'claim_expires_at', NULL,
                'claimed_by', NULL, 'safe_failure_category', CAST(:category AS text),
                'last_event_at', CAST(:now AS timestamptz)
            )
        WHERE delivery_id = CAST(:delivery_id AS uuid)
          AND metadata_jsonb ->> 'submission_status' = 'PROCESSING'
          AND metadata_jsonb ->> 'claim_token' = :claim_token
        RETURNING *
        """,
        {
            "delivery_id": delivery_id,
            "claim_token": claim_token,
            "error_message": _safe_error(error_message),
            "category": _normalize_error_code(error_code),
            "now": now,
        },
    )
    if row is None:
        _raise_stale_claim(delivery_id)
    return _row_to_delivery(row)
