from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.config import Settings
from app.core.errors import AppError
from app.db.email_outbox import build_email_delivery_idempotency_key, create_or_get_delivery, requeue_delivery
from app.schemas.email_delivery import (
    DEFAULT_EMAIL_DELIVERY_TRIGGER_TYPE,
    DEFAULT_EMAIL_TEMPLATE_NAME,
    DEFAULT_EMAIL_TEMPLATE_VERSION,
    EmailDeliveryCreateRequest,
    EmailDeliveryEligibilityDecision,
    EmailTemplateRenderResult,
)
from app.services import email_unsubscribe
from app.services.email_observability import emit_email_event
from app.services.email_templates import render_report_completed_template

logger = logging.getLogger(__name__)

SENDABLE_REPORT_STATUSES = {"completed", "published", "sent"}
POLICY_SKIP_REASON_CODES = {
    "delivery_disabled",
    "rollout_disabled",
    "trigger_disabled",
    "recipient_not_allowlisted",
    "daily_report_email_disabled",
    "action_emails_disabled",
    "report_not_sendable",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


async def _fetch_one(db: AsyncEngine | AsyncConnection, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    from sqlalchemy import text

    if isinstance(db, AsyncConnection):
        result = await db.execute(text(sql), params)
        row = result.mappings().first()
        return dict(row) if row is not None else None
    async with db.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.mappings().first()
        return dict(row) if row is not None else None


async def load_report_completed_delivery_context(
    db: AsyncEngine | AsyncConnection,
    *,
    user_id: str | int,
    report_id: str,
) -> dict[str, Any] | None:
    return await _fetch_one(
        db,
        """
        SELECT
            run.user_id::text AS user_id,
            report.report_id,
            report.status AS report_status,
            report.title AS report_title,
            report.summary AS report_summary,
            report.sent_at AS published_at,
            report.strategy_id,
            profile.name AS strategy_name,
            account.email AS user_email,
            account.name AS user_name,
            account.email AS recipient_email,
            COALESCE(account.action_emails, TRUE) AS action_emails,
            COALESCE(account.daily_report_email, TRUE) AS daily_report_email,
            COALESCE(account.marketing_email, FALSE) AS marketing_email,
            COALESCE(account.delivery_hour, '08:00') AS delivery_hour
        FROM app.strategy_email_report AS report
        JOIN app.backtest_run AS run
          ON run.run_id = report.backtest_run_id
        JOIN app.users AS account
          ON account.user_id = run.user_id
        LEFT JOIN app.strategy_report_profile AS profile
          ON profile.strategy_id = report.strategy_id
        WHERE report.report_id = :report_id
          AND run.user_id = CAST(:user_id AS bigint)
        """,
        {"user_id": int(user_id), "report_id": report_id},
    )


async def _load_report_delivery_context(
    db: AsyncEngine | AsyncConnection,
    *,
    user_id: str | int,
    report_id: str,
) -> dict[str, Any] | None:
    return await load_report_completed_delivery_context(db, user_id=user_id, report_id=report_id)


def build_report_completed_delivery_idempotency_key(*, user_id: str | int, report_id: str) -> str:
    return build_email_delivery_idempotency_key(
        user_id=user_id,
        report_id=report_id,
        trigger_type=DEFAULT_EMAIL_DELIVERY_TRIGGER_TYPE,
        template_version=DEFAULT_EMAIL_TEMPLATE_VERSION,
    )


def resolve_report_completed_delivery_eligibility(
    settings: Settings,
    *,
    context: dict[str, Any] | None,
) -> EmailDeliveryEligibilityDecision:
    if not settings.email_delivery_enabled:
        return EmailDeliveryEligibilityDecision(
            allowed=False,
            reason_code="delivery_disabled",
            reason_message="Email delivery is disabled",
        )
    if settings.email_effective_rollout_mode == "disabled":
        return EmailDeliveryEligibilityDecision(
            allowed=False,
            reason_code="rollout_disabled",
            reason_message="Email rollout is disabled",
        )
    if not settings.email_report_completed_trigger_enabled:
        return EmailDeliveryEligibilityDecision(
            allowed=False,
            reason_code="trigger_disabled",
            reason_message="Report-completion email trigger is disabled",
        )

    if context is None:
        return EmailDeliveryEligibilityDecision(
            allowed=False,
            reason_code="report_or_user_missing",
            reason_message="User or report was not found",
        )

    user_id = _normalize_text(context.get("user_id"))
    report_id = _normalize_text(context.get("report_id"))
    recipient_email = _normalize_text(context.get("recipient_email")) or _normalize_text(context.get("user_email"))
    daily_report_email = bool(context.get("daily_report_email"))
    action_emails = bool(context.get("action_emails"))
    report_status = _normalize_text(context.get("report_status"))

    if not recipient_email:
        return EmailDeliveryEligibilityDecision(
            allowed=False,
            reason_code="recipient_missing",
            reason_message="User email is not available",
            user_id=user_id,
            report_id=report_id,
        )
    if settings.email_effective_rollout_mode == "allowlist":
        allowed_recipients = {item.lower() for item in settings.email_local_recipient_allowlist_values}
        if recipient_email.lower() not in allowed_recipients:
            return EmailDeliveryEligibilityDecision(
                allowed=False,
                reason_code="recipient_not_allowlisted",
                reason_message="Recipient is not eligible for the controlled rollout",
                user_id=user_id,
                report_id=report_id,
            )
    if not daily_report_email:
        return EmailDeliveryEligibilityDecision(
            allowed=False,
            reason_code="daily_report_email_disabled",
            reason_message="Notification settings do not permit report emails",
            user_id=user_id,
            report_id=report_id,
            recipient_email=recipient_email,
        )
    if not action_emails:
        return EmailDeliveryEligibilityDecision(
            allowed=False,
            reason_code="action_emails_disabled",
            reason_message="Notification settings do not permit action emails",
            user_id=user_id,
            report_id=report_id,
            recipient_email=recipient_email,
        )
    if report_status not in SENDABLE_REPORT_STATUSES:
        return EmailDeliveryEligibilityDecision(
            allowed=False,
            reason_code="report_not_sendable",
            reason_message="Report is not in a sendable state",
            user_id=user_id,
            report_id=report_id,
            recipient_email=recipient_email,
        )

    return EmailDeliveryEligibilityDecision(
        allowed=True,
        reason_code="eligible",
        reason_message="Report delivery is eligible",
        user_id=user_id,
        report_id=report_id,
        recipient_email=recipient_email,
        payload_json={
            "reportTitle": _normalize_text(context.get("report_title")),
            "reportSummary": _normalize_text(context.get("report_summary")),
            "userName": _normalize_text(context.get("user_name")),
            "publishedAt": _normalize_text(context.get("published_at")),
            "strategyId": _normalize_text(context.get("strategy_id")),
            "strategyName": _normalize_text(context.get("strategy_name")),
        },
    )


def build_report_completed_template(
    *,
    settings: Settings,
    context: dict[str, Any],
    eligibility: EmailDeliveryEligibilityDecision,
) -> EmailTemplateRenderResult:
    public_base_url = _normalize_text(settings.email_public_base_url)
    if not public_base_url:
        raise AppError(
            status_code=503,
            component="email_delivery",
            code="email_public_base_url_missing",
            message="Email public base URL is required for template rendering",
        )
    if not eligibility.allowed or not eligibility.recipient_email or not eligibility.report_id:
        raise AppError(
            status_code=503,
            component="email_delivery",
            code="email_delivery_not_eligible",
            message="Report delivery is not eligible",
        )
    unsubscribe_url = None
    if settings.email_unsubscribe_enabled and eligibility.user_id:
        unsubscribe_url = email_unsubscribe.build_unsubscribe_url(settings, user_id=eligibility.user_id)
    return render_report_completed_template(
        public_base_url=public_base_url,
        report_id=eligibility.report_id,
        report_title=_normalize_text(context.get("report_title")),
        report_summary=_normalize_text(context.get("report_summary")),
        recipient_email=eligibility.recipient_email,
        recipient_name=_normalize_text(context.get("user_name")),
        unsubscribe_url=unsubscribe_url,
    )


async def build_report_completed_delivery_request(
    db: AsyncEngine | AsyncConnection,
    *,
    settings: Settings,
    user_id: str | int,
    report_id: str,
    correlation_id: str | None = None,
) -> tuple[EmailDeliveryEligibilityDecision, EmailDeliveryCreateRequest | None, EmailTemplateRenderResult | None]:
    if (
        not settings.email_delivery_enabled
        or not settings.email_report_completed_trigger_enabled
        or settings.email_effective_rollout_mode == "disabled"
    ):
        return resolve_report_completed_delivery_eligibility(settings, context=None), None, None

    context = await _load_report_delivery_context(db, user_id=user_id, report_id=report_id)
    eligibility = resolve_report_completed_delivery_eligibility(settings, context=context)
    if not eligibility.allowed or context is None:
        return eligibility, None, None

    template = build_report_completed_template(settings=settings, context=context, eligibility=eligibility)
    if correlation_id is None:
        correlation_id = f"report:{report_id}"

    request = EmailDeliveryCreateRequest(
        user_id=str(user_id),
        report_id=report_id,
        trigger_type=DEFAULT_EMAIL_DELIVERY_TRIGGER_TYPE,
        template_name=DEFAULT_EMAIL_TEMPLATE_NAME,
        template_version=DEFAULT_EMAIL_TEMPLATE_VERSION,
        recipient_email=eligibility.recipient_email or "",
        idempotency_key=build_report_completed_delivery_idempotency_key(user_id=user_id, report_id=report_id),
        payload_json={
            **eligibility.payload_json,
            "subject": template.subject,
            "htmlBody": template.html_body,
            "textBody": template.text_body,
            "recipientEmail": eligibility.recipient_email,
            "reportId": report_id,
            "userId": str(user_id),
        },
        provider=str(settings.email_provider or "brevo").strip().lower(),
        max_attempts=settings.email_max_attempts,
        available_at=_now(),
        correlation_id=correlation_id,
    )
    return eligibility, request, template


async def create_report_completed_delivery(
    db: AsyncEngine | AsyncConnection,
    *,
    settings: Settings,
    user_id: str | int,
    report_id: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    eligibility, request, template = await build_report_completed_delivery_request(
        db,
        settings=settings,
        user_id=user_id,
        report_id=report_id,
        correlation_id=correlation_id,
    )
    if request is None:
        emit_email_event(
            logger,
            "enqueue_skipped_policy"
            if eligibility.reason_code in POLICY_SKIP_REASON_CODES
            else "enqueue_failed",
            report_id=report_id,
            trigger_type=DEFAULT_EMAIL_DELIVERY_TRIGGER_TYPE,
            reason_code=eligibility.reason_code,
            correlation_id=correlation_id or f"report:{report_id}",
        )
        return {
            "eligibility": eligibility,
            "request": None,
            "template": None,
            "delivery": None,
        }

    delivery = await create_or_get_delivery(db, request)
    return {
        "eligibility": eligibility,
        "request": request,
        "template": template,
        "delivery": delivery,
    }


REQUEUEABLE_SUBMISSION_STATUSES = {"SENT", "FAILED", "CANCELLED"}


def resolve_resend_action(delivery: dict[str, Any] | None) -> str:
    """Decide what an explicit resend must do with the deterministic delivery row.

    ``queued`` a new row was inserted, ``requeue`` the terminal row must be reset to
    PENDING, ``noop`` a pending/retry/processing delivery is already on its way.
    """

    if delivery is None:
        return "unavailable"
    if delivery.get("created"):
        return "queued"
    status = str(delivery.get("submission_status") or delivery.get("status") or "").upper()
    return "requeue" if status in REQUEUEABLE_SUBMISSION_STATUSES else "noop"


async def resend_report_completed_delivery(
    db: AsyncEngine | AsyncConnection,
    *,
    settings: Settings,
    user_id: str | int,
    report_id: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Explicit resend: unlike the completion trigger this re-queues a terminal delivery."""

    result = await create_report_completed_delivery(
        db,
        settings=settings,
        user_id=user_id,
        report_id=report_id,
        correlation_id=correlation_id,
    )
    action = resolve_resend_action(result["delivery"])
    if action == "requeue":
        requeued = await requeue_delivery(db, delivery_id=str(result["delivery"]["delivery_id"]))
        # A concurrent worker/resend may have moved the row out of a terminal state first.
        action = "queued" if requeued is not None else "noop"
        if requeued is not None:
            result = {**result, "delivery": requeued}
    emit_email_event(
        logger,
        "resend_requested",
        report_id=report_id,
        trigger_type=DEFAULT_EMAIL_DELIVERY_TRIGGER_TYPE,
        result=action,
        reused=bool(result["delivery"] and not result["delivery"].get("created")),
    )
    return {**result, "resend_action": action}
