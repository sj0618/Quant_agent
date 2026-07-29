from __future__ import annotations

import asyncio
import logging
import os
import socket
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.errors import AppError
from app.db import email_outbox
from app.schemas.email_delivery import EmailDeliveryMessage
from app.services import email_delivery as email_delivery_service
from app.services.email_observability import emit_email_event
from app.services.email_provider import BrevoEmailProvider

logger = logging.getLogger(__name__)
MAX_BACKOFF_SECONDS = 30 * 60


def _now() -> datetime:
    return datetime.now(UTC)


async def load_report_completed_delivery_context(
    db: AsyncEngine,
    *,
    user_id: str | int,
    report_id: str,
) -> dict[str, Any] | None:
    return await email_delivery_service.load_report_completed_delivery_context(db, user_id=user_id, report_id=report_id)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class EmailDeliveryWorkerState:
    worker_id: str
    batch_size: int
    claim_lease_seconds: int
    poll_interval_seconds: float
    shutdown_grace_seconds: int


class EmailDeliveryWorker:
    def __init__(
        self,
        engine: AsyncEngine,
        settings: Settings,
        *,
        provider: Any | None = None,
        provider_factory: type[BrevoEmailProvider] = BrevoEmailProvider,
        logger_obj: logging.Logger | None = None,
        delivery_scope_id: str | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.provider = provider or provider_factory(settings)
        self.logger = logger_obj or logger
        self.delivery_scope_id = delivery_scope_id
        self.state = EmailDeliveryWorkerState(
            worker_id=self._resolve_worker_id(),
            batch_size=settings.email_worker_batch_size,
            claim_lease_seconds=settings.email_worker_claim_lease_seconds,
            poll_interval_seconds=settings.email_worker_poll_interval_seconds,
            shutdown_grace_seconds=settings.email_worker_shutdown_grace_seconds,
        )
        self.stop_event = asyncio.Event()
        self._startup_validated = False

    def _resolve_worker_id(self) -> str:
        configured = _normalize_text(self.settings.email_worker_id)
        if configured:
            return configured
        return f"email-worker:{socket.gethostname()}:{os.getpid()}"

    def stop(self) -> None:
        self.stop_event.set()

    def validate_startup(self) -> None:
        if not self.settings.email_delivery_worker_enabled:
            raise AppError(
                status_code=503,
                component="email_worker",
                code="email_worker_disabled",
                message="Email worker is disabled",
            )
        if self.settings.email_effective_rollout_mode == "disabled":
            raise AppError(
                status_code=503,
                component="email_worker",
                code="email_rollout_disabled",
                message="Email rollout is disabled",
            )
        self.provider.validate_configuration()
        self._startup_validated = True

    def validate_readiness(self) -> None:
        if self.settings.email_effective_rollout_mode != "disabled":
            self.provider.validate_configuration()

    async def run_once(self) -> int:
        if not self._startup_validated:
            self.validate_startup()
        recovered_rows = await email_outbox.release_expired_claims(
            self.engine,
            delivery_scope_id=self.delivery_scope_id,
        )
        for recovered in recovered_rows:
            emit_email_event(
                self.logger,
                "claim_recovered",
                worker_id=self.state.worker_id,
                delivery_id=str(recovered.get("delivery_id")),
                report_id=str(recovered.get("report_id")),
                trigger_type=str(recovered.get("trigger_type")),
                attempt_count=int(recovered.get("attempt_count") or 0),
                status=str(recovered.get("status") or ""),
                reason_code="expired_claim",
            )
        claims: list[dict[str, Any]] = []

        for _ in range(self.state.batch_size):
            if self.stop_event.is_set():
                break
            claim = await email_outbox.claim_next_delivery(
                self.engine,
                claimed_by=self.state.worker_id,
                claim_ttl_seconds=self.state.claim_lease_seconds,
                delivery_scope_id=self.delivery_scope_id,
            )
            if claim is None:
                break
            claims.append(claim)
            emit_email_event(
                self.logger,
                "delivery_claimed",
                worker_id=self.state.worker_id,
                delivery_id=str(claim.get("delivery_id")),
                report_id=str(claim.get("report_id")),
                trigger_type=str(claim.get("trigger_type")),
                attempt_count=int(claim.get("attempt_count") or 0),
                status=str(claim.get("status") or "PROCESSING"),
            )

        if not claims:
            return 0

        shutdown_deadline: float | None = None
        loop = asyncio.get_running_loop()
        for claim in claims:
            if self.stop_event.is_set() and shutdown_deadline is None:
                shutdown_deadline = loop.time() + self.state.shutdown_grace_seconds
            await self._process_claim_with_optional_timeout(claim, shutdown_deadline)

        return len(claims)

    async def run(self) -> None:
        self.validate_startup()
        emit_email_event(
            self.logger,
            "worker_started",
            worker_id=self.state.worker_id,
            batch_size=self.state.batch_size,
            claim_ttl_seconds=self.state.claim_lease_seconds,
            shutdown_grace_seconds=self.state.shutdown_grace_seconds,
        )
        stopping_emitted = False
        try:
            while True:
                processed = await self.run_once()
                if self.stop_event.is_set():
                    if not stopping_emitted:
                        emit_email_event(
                            self.logger,
                            "worker_stopping",
                            worker_id=self.state.worker_id,
                            batch_size=self.state.batch_size,
                            claim_ttl_seconds=self.state.claim_lease_seconds,
                            shutdown_grace_seconds=self.state.shutdown_grace_seconds,
                            worker_state="stopping",
                        )
                        stopping_emitted = True
                    if processed == 0:
                        break
                    continue
                if processed == 0:
                    emit_email_event(
                        self.logger,
                        "worker_idle",
                        worker_id=self.state.worker_id,
                        batch_size=self.state.batch_size,
                        claim_ttl_seconds=self.state.claim_lease_seconds,
                        worker_state="idle",
                    )
                    await asyncio.sleep(self.state.poll_interval_seconds)
        finally:
            emit_email_event(
                self.logger,
                "worker_stopped",
                worker_id=self.state.worker_id,
                batch_size=self.state.batch_size,
                claim_ttl_seconds=self.state.claim_lease_seconds,
                shutdown_grace_seconds=self.state.shutdown_grace_seconds,
            )

    async def _process_claim_with_optional_timeout(
        self,
        claim: dict[str, Any],
        shutdown_deadline: float | None,
    ) -> None:
        if shutdown_deadline is None:
            await self._process_claim(claim)
            return

        loop = asyncio.get_running_loop()
        remaining = shutdown_deadline - loop.time()
        if remaining <= 0:
            return
        try:
            await asyncio.wait_for(self._process_claim(claim), timeout=remaining)
        except asyncio.TimeoutError:
            emit_email_event(
                self.logger,
                "claim_lost",
                worker_id=self.state.worker_id,
                delivery_id=str(claim.get("delivery_id")),
                report_id=str(claim.get("report_id")),
                trigger_type=str(claim.get("trigger_type")),
                reason_code="shutdown_grace_expired",
            )

    async def _process_claim(self, claim: dict[str, Any]) -> None:
        delivery_id = str(claim["delivery_id"])
        claim_token = str(claim["claim_token"])
        report_id = str(claim["report_id"])
        trigger_type = str(claim["trigger_type"])
        attempt_count = int(claim.get("attempt_count") or 0)
        row_status = str(claim.get("status") or "PROCESSING")

        if row_status == "CANCELLED":
            return

        try:
            decision = await self._revalidate_claim(claim)
            if not decision.allowed:
                await self._handle_revalidation_rejection(claim, decision)
                return

            message = self._build_message_from_claim(claim)
            send_result = await self.provider.send(message)
        except AppError as exc:
            await self._handle_app_error(claim, exc)
            return

        if send_result.status == "accepted":
            try:
                updated = await email_outbox.mark_sent(
                    self.engine,
                    delivery_id=delivery_id,
                    claim_token=claim_token,
                    provider_message_id=send_result.provider_message_id,
                )
            except AppError as exc:
                await self._handle_claim_lost(claim, exc)
                return
            emit_email_event(
                self.logger,
                "provider_request_succeeded",
                worker_id=self.state.worker_id,
                delivery_id=delivery_id,
                report_id=report_id,
                trigger_type=trigger_type,
                attempt_count=int(updated.get("attempt_count") or attempt_count),
                provider_status_class="success",
                provider_message_id_present=bool(send_result.provider_message_id),
                status=str(updated.get("status")),
            )
            return

        if send_result.retryable:
            delay_seconds = self._calculate_retry_delay(attempt_count)
            available_at = _now() + timedelta(seconds=delay_seconds)
            try:
                updated = await email_outbox.mark_retry_pending(
                    self.engine,
                    delivery_id=delivery_id,
                    claim_token=claim_token,
                    available_at=available_at,
                    error_code=send_result.error_code,
                    error_message=send_result.error_message,
                    provider_message_id=send_result.provider_message_id,
                )
            except AppError as exc:
                await self._handle_claim_lost(claim, exc)
                return
            if updated["status"] == "RETRY_PENDING":
                emit_email_event(
                    self.logger,
                    "provider_request_retryable_failed",
                    worker_id=self.state.worker_id,
                    delivery_id=delivery_id,
                    report_id=report_id,
                    trigger_type=trigger_type,
                    attempt_count=int(updated.get("attempt_count") or attempt_count),
                    provider_status_class="retryable",
                    status=str(updated.get("status")),
                    available_at=available_at,
                )
            else:
                emit_email_event(
                    self.logger,
                    "provider_request_retryable_failed",
                    worker_id=self.state.worker_id,
                    delivery_id=delivery_id,
                    report_id=report_id,
                    trigger_type=trigger_type,
                    attempt_count=int(updated.get("attempt_count") or attempt_count),
                    provider_status_class="retryable",
                    status=str(updated.get("status")),
                    error_code=send_result.error_code,
                )
            return

        try:
            updated = await email_outbox.mark_failed(
                self.engine,
                delivery_id=delivery_id,
                claim_token=claim_token,
                error_code=send_result.error_code,
                error_message=send_result.error_message,
                provider_message_id=send_result.provider_message_id,
            )
        except AppError as exc:
            await self._handle_claim_lost(claim, exc)
            return
        emit_email_event(
            self.logger,
            "provider_request_permanent_failed",
            worker_id=self.state.worker_id,
            delivery_id=delivery_id,
            report_id=report_id,
            trigger_type=trigger_type,
            attempt_count=int(updated.get("attempt_count") or attempt_count),
            provider_status_class="permanent",
            status=str(updated.get("status")),
            error_code=send_result.error_code,
        )

    async def _revalidate_claim(self, claim: dict[str, Any]) -> Any:
        context = await load_report_completed_delivery_context(
            self.engine,
            user_id=str(claim["user_id"]),
            report_id=str(claim["report_id"]),
        )
        decision = email_delivery_service.resolve_report_completed_delivery_eligibility(self.settings, context=context)
        current_recipient = _normalize_text(decision.recipient_email)
        queued_recipient = _normalize_text(claim.get("recipient_email"))
        if decision.allowed and (
            current_recipient is None
            or queued_recipient is None
            or current_recipient.casefold() != queued_recipient.casefold()
        ):
            return replace(
                decision,
                allowed=False,
                reason_code="recipient_changed",
                reason_message="Notification recipient changed after enqueue",
            )
        return decision

    def _build_message_from_claim(self, claim: dict[str, Any]) -> EmailDeliveryMessage:
        payload = claim.get("payload_jsonb")
        if not isinstance(payload, dict):
            raise AppError(
                status_code=503,
                component="email_worker",
                code="email_delivery_payload_invalid",
                message="Email delivery payload is invalid",
                details={"delivery_id": str(claim.get("delivery_id"))},
            )
        subject = _normalize_text(payload.get("subject"))
        html_body = _normalize_text(payload.get("htmlBody") or payload.get("html"))
        text_body = _normalize_text(payload.get("textBody") or payload.get("text"))
        recipient_email = _normalize_text(claim.get("recipient_email")) or _normalize_text(payload.get("recipientEmail"))
        if not subject or not html_body or not text_body or not recipient_email:
            raise AppError(
                status_code=503,
                component="email_worker",
                code="email_delivery_payload_missing",
                message="Email delivery payload is incomplete",
                details={"delivery_id": str(claim.get("delivery_id"))},
            )
        return EmailDeliveryMessage(
            recipient_email=recipient_email,
            sender_email=_normalize_text(self.settings.email_from_address) or "",
            sender_name=self.settings.email_from_name,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            correlation_id=_normalize_text(claim.get("correlation_id")),
            idempotency_key=str(claim.get("idempotency_key")),
            template_name=str(claim.get("template_name")),
            template_version=str(claim.get("template_version")),
        )

    async def _handle_revalidation_rejection(self, claim: dict[str, Any], decision) -> None:
        reason_code = str(decision.reason_code)
        if reason_code in email_delivery_service.POLICY_SKIP_REASON_CODES or reason_code == "recipient_changed":
            await self._mark_cancelled(claim, reason_code=reason_code, error_message=decision.reason_message)
            return
        await self._mark_failed(claim, reason_code=reason_code, error_message=decision.reason_message)

    async def _handle_app_error(self, claim: dict[str, Any], exc: AppError) -> None:
        code = str(getattr(exc, "code", type(exc).__name__))
        await self._mark_failed(claim, reason_code=code, error_message=str(exc))

    async def _handle_claim_lost(self, claim: dict[str, Any], exc: AppError) -> None:
        emit_email_event(
            self.logger,
            "claim_lost",
            worker_id=self.state.worker_id,
            delivery_id=str(claim.get("delivery_id")),
            report_id=str(claim.get("report_id")),
            trigger_type=str(claim.get("trigger_type")),
            reason_code=str(getattr(exc, "code", type(exc).__name__)),
        )

    async def _mark_cancelled(self, claim: dict[str, Any], *, reason_code: str, error_message: str | None = None) -> None:
        delivery_id = str(claim["delivery_id"])
        try:
            updated = await email_outbox.mark_cancelled(
                self.engine,
                delivery_id=delivery_id,
                claim_token=str(claim["claim_token"]),
                error_code=reason_code,
                error_message=error_message,
            )
        except AppError as exc:
            await self._handle_claim_lost(claim, exc)
            return
        emit_email_event(
            self.logger,
            "delivery_cancelled",
            worker_id=self.state.worker_id,
            delivery_id=delivery_id,
            report_id=str(claim.get("report_id")),
            trigger_type=str(claim.get("trigger_type")),
            attempt_count=int(updated.get("attempt_count") or claim.get("attempt_count") or 0),
            reason_code=reason_code,
        )

    async def _mark_failed(self, claim: dict[str, Any], *, reason_code: str, error_message: str | None = None) -> None:
        delivery_id = str(claim["delivery_id"])
        claim_token = str(claim["claim_token"])
        try:
            updated = await email_outbox.mark_failed(
                self.engine,
                delivery_id=delivery_id,
                claim_token=claim_token,
                error_code=reason_code,
                error_message=error_message,
            )
        except AppError as exc:
            await self._handle_claim_lost(claim, exc)
            return
        emit_email_event(
            self.logger,
            "delivery_failed",
            worker_id=self.state.worker_id,
            delivery_id=delivery_id,
            report_id=str(claim.get("report_id")),
            trigger_type=str(claim.get("trigger_type")),
            attempt_count=int(updated.get("attempt_count") or claim.get("attempt_count") or 0),
            provider_status_class="permanent",
            status=str(updated.get("status")),
            error_code=reason_code,
        )

    def _calculate_retry_delay(self, attempt_count: int) -> int:
        base = max(1, int(self.settings.email_retry_base_seconds))
        exponent = max(0, attempt_count - 1)
        delay_seconds = min(base * (2**exponent), MAX_BACKOFF_SECONDS)
        return int(delay_seconds)
