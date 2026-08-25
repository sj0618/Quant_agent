from __future__ import annotations

import asyncio
import base64
from datetime import UTC, date, datetime, timedelta
import json
import logging

import httpx
import pytest

from app.core.errors import AppError
from app.db.email_delivery_history import _decode_cursor, _to_entry
from app.db.email_outbox import build_email_delivery_idempotency_key, deterministic_delivery_id
from app.schemas.email_delivery import EmailDeliveryMessage
from app.services import email_delivery, email_unsubscribe
from app.services.email_observability import emit_email_event
from app.services.email_provider import BrevoEmailProvider, _normalize_message_id
from app.services.email_provider_inspection import BrevoEmailInspector, map_brevo_delivery_event
from app.services.email_templates import render_report_completed_template
from app.workers import email_delivery_worker
from app.workers.email_delivery_worker import EmailDeliveryWorker
from tests.unit.test_auth_config import valid_settings


def _email_settings(**overrides):
    values = {
        "EMAIL_DELIVERY_ENABLED": True,
        "EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED": True,
        "EMAIL_FROM_ADDRESS": "sender@example.test",
        "EMAIL_API_KEY": "test-provider-key",
        "EMAIL_PUBLIC_BASE_URL": "https://reports.example.test",
        "EMAIL_UNSUBSCRIBE_ENABLED": True,
        "EMAIL_UNSUBSCRIBE_SIGNING_SECRET": "track4-test-signing-secret",
        "EMAIL_UNSUBSCRIBE_BASE_URL": "https://app.example.test",
        "EMAIL_LOCAL_LIVE_SEND_ENABLED": True,
        "EMAIL_LOCAL_RECIPIENT_ALLOWLIST": (
            "owner@example.test,current@example.test,queued@example.test,allowed@example.test"
        ),
    }
    values.update(overrides)
    return valid_settings(**values)


def test_delivery_identity_is_deterministic_and_scope_sensitive():
    first_key = build_email_delivery_idempotency_key(
        user_id=7,
        report_id="report-1",
        trigger_type="report_completed",
        template_version="v1",
    )
    replay_key = build_email_delivery_idempotency_key(
        user_id="7",
        report_id="report-1",
        trigger_type="report_completed",
        template_version="v1",
    )
    other_key = build_email_delivery_idempotency_key(
        user_id=7,
        report_id="report-2",
        trigger_type="report_completed",
        template_version="v1",
    )

    assert first_key == replay_key
    assert deterministic_delivery_id(first_key) == deterministic_delivery_id(replay_key)
    assert deterministic_delivery_id(first_key) != deterministic_delivery_id(other_key)


def test_report_template_escapes_user_content_and_includes_unsubscribe():
    rendered = render_report_completed_template(
        public_base_url="https://reports.example.test",
        report_id="report/1",
        report_title="<script>alert(1)</script>",
        report_summary="safe & bounded",
        recipient_email="owner@example.test",
        recipient_name="Owner <Admin>",
        unsubscribe_url="https://app.example.test/unsubscribe?token=opaque",
    )

    assert "<script>" not in rendered.html_body
    assert "&lt;script&gt;" in rendered.html_body
    assert "report%2F1" in rendered.html_body
    assert "Unsubscribe" in rendered.text_body

    with pytest.raises(ValueError):
        render_report_completed_template(
            public_base_url="/relative",
            report_id="report-1",
            report_title=None,
            report_summary=None,
            recipient_email="owner@example.test",
        )


def test_report_delivery_eligibility_obeys_runtime_and_user_policy():
    context = {
        "user_id": "7",
        "report_id": "report-1",
        "recipient_email": "owner@example.test",
        "daily_report_email": True,
        "action_emails": True,
        "report_status": "sent",
    }
    assert email_delivery.resolve_report_completed_delivery_eligibility(_email_settings(), context=context).allowed is True
    assert (
        email_delivery.resolve_report_completed_delivery_eligibility(
            _email_settings(EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED=False), context=context
        ).reason_code
        == "trigger_disabled"
    )
    assert (
        email_delivery.resolve_report_completed_delivery_eligibility(
            _email_settings(), context={**context, "daily_report_email": False}
        ).reason_code
        == "daily_report_email_disabled"
    )
    assert (
        email_delivery.resolve_report_completed_delivery_eligibility(
            _email_settings(), context={**context, "action_emails": False}
        ).reason_code
        == "action_emails_disabled"
    )


def test_disabled_delivery_short_circuits_before_email_schema_access(monkeypatch):
    async def fail_if_loaded(*_args, **_kwargs):
        raise AssertionError("email schema must not be queried while delivery is disabled")

    monkeypatch.setattr(email_delivery, "_load_report_delivery_context", fail_if_loaded)
    eligibility, request, template = asyncio.run(
        email_delivery.build_report_completed_delivery_request(
            object(),
            settings=_email_settings(EMAIL_DELIVERY_ENABLED=False),
            user_id="7",
            report_id="report-1",
        )
    )

    assert eligibility.reason_code == "delivery_disabled"
    assert request is None
    assert template is None


def test_disabled_rollout_short_circuits_before_email_schema_access(monkeypatch):
    async def fail_if_loaded(*_args, **_kwargs):
        raise AssertionError("email schema must not be queried while rollout is disabled")

    monkeypatch.setattr(email_delivery, "_load_report_delivery_context", fail_if_loaded)
    settings = _email_settings(
        EMAIL_LOCAL_LIVE_SEND_ENABLED=False,
        EMAIL_LOCAL_RECIPIENT_ALLOWLIST="",
    )
    eligibility, request, template = asyncio.run(
        email_delivery.build_report_completed_delivery_request(
            object(),
            settings=settings,
            user_id="7",
            report_id="report-1",
        )
    )

    assert eligibility.reason_code == "rollout_disabled"
    assert request is None
    assert template is None


def test_allowlist_rollout_rejects_unlisted_recipient_before_enqueue():
    decision = email_delivery.resolve_report_completed_delivery_eligibility(
        _email_settings(EMAIL_LOCAL_RECIPIENT_ALLOWLIST="allowed@example.test"),
        context={
            "user_id": "7",
            "report_id": "report-1",
            "recipient_email": "other@example.test",
            "daily_report_email": True,
            "action_emails": True,
            "report_status": "sent",
        },
    )

    assert decision.allowed is False
    assert decision.reason_code == "recipient_not_allowlisted"
    assert decision.recipient_email is None


def test_delivery_history_cursor_rejects_non_uuid_delivery_id():
    payload = json.dumps(
        {"created_at": "2030-01-01T00:00:00+00:00", "delivery_id": "not-a-uuid"},
        separators=(",", ":"),
    )
    cursor = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

    with pytest.raises(AppError) as invalid:
        _decode_cursor(cursor)
    assert invalid.value.code == "email_delivery_history_invalid_cursor"


def test_worker_revalidation_cancels_changed_recipient_and_user_policy(monkeypatch):
    async def current_context(*_args, **_kwargs):
        return {
            "user_id": "7",
            "report_id": "report-1",
            "recipient_email": "current@example.test",
            "daily_report_email": True,
            "action_emails": True,
            "report_status": "sent",
        }

    monkeypatch.setattr(email_delivery_worker, "load_report_completed_delivery_context", current_context)
    worker = EmailDeliveryWorker(object(), _email_settings(), provider=object())
    claim = {
        "delivery_id": "delivery-1",
        "user_id": "7",
        "report_id": "report-1",
        "recipient_email": "queued@example.test",
        "claim_token": "claim-1",
    }

    changed = asyncio.run(worker._revalidate_claim(claim))
    assert changed.allowed is False
    assert changed.reason_code == "recipient_changed"

    transitions: list[str] = []

    async def cancelled(*_args, **_kwargs):
        transitions.append("cancelled")

    async def failed(*_args, **_kwargs):
        transitions.append("failed")

    monkeypatch.setattr(worker, "_mark_cancelled", cancelled)
    monkeypatch.setattr(worker, "_mark_failed", failed)
    daily_disabled = email_delivery.resolve_report_completed_delivery_eligibility(
        _email_settings(),
        context={
            "user_id": "7",
            "report_id": "report-1",
            "recipient_email": "current@example.test",
            "daily_report_email": False,
            "action_emails": True,
            "report_status": "sent",
        },
    )
    asyncio.run(worker._handle_revalidation_rejection(claim, daily_disabled))
    asyncio.run(worker._handle_revalidation_rejection(claim, changed))

    assert transitions == ["cancelled", "cancelled"]


def test_unsubscribe_token_round_trip_invalid_and_expired():
    settings = _email_settings()
    issued_at = datetime(2030, 1, 1, tzinfo=UTC)
    token = email_unsubscribe.generate_unsubscribe_token(
        settings,
        user_id="7",
        issued_at=issued_at,
        expires_at=issued_at + timedelta(minutes=5),
        nonce="unit-test",
    )
    claims = email_unsubscribe.verify_unsubscribe_token(settings, token, now=issued_at + timedelta(minutes=1))
    assert claims.user_id == "7"

    with pytest.raises(AppError) as not_active:
        email_unsubscribe.verify_unsubscribe_token(settings, token, now=issued_at - timedelta(minutes=1))
    assert not_active.value.code == "unsubscribe_token_invalid"

    with pytest.raises(AppError) as invalid:
        email_unsubscribe.verify_unsubscribe_token(settings, token + "x", now=issued_at + timedelta(minutes=1))
    assert invalid.value.code == "unsubscribe_token_invalid"

    with pytest.raises(AppError) as expired:
        email_unsubscribe.verify_unsubscribe_token(settings, token, now=issued_at + timedelta(minutes=6))
    assert expired.value.status_code == 410


def test_provider_and_observability_redact_recipient_addresses(caplog):
    settings = _email_settings(
        APP_ENV="local",
        BREVO_API_BASE_URL="https://provider.example.test",
        EMAIL_LOCAL_LIVE_SEND_ENABLED=True,
        EMAIL_LOCAL_RECIPIENT_ALLOWLIST="allowed@example.test",
    )
    provider = BrevoEmailProvider(settings)
    assert provider.api_base_url == "https://provider.example.test"
    with pytest.raises(AppError) as rejected:
        provider._assert_local_live_send_allowed("private-recipient@example.com")  # noqa: SLF001
    assert "recipient" not in rejected.value.details

    response = httpx.Response(400, text="delivery rejected for private-recipient@example.com")
    normalized = provider.normalize_error(response)
    assert "private-recipient@example.com" not in str(normalized.error_message)
    assert normalized.error_message == "Email provider request failed with HTTP 400"

    logger = logging.getLogger("track4-email-redaction-test")
    with caplog.at_level(logging.INFO, logger=logger.name):
        emit_email_event(logger, "provider_failure", error_message="private-recipient@example.com rejected")
    assert "private-recipient@example.com" not in caplog.text
    assert "<redacted-email>" in caplog.text


@pytest.mark.asyncio
async def test_invalid_sender_is_rejected_before_provider_request_construction(monkeypatch):
    marker = "category" + "_shaped_provider_sender"
    settings = _email_settings(
        EMAIL_FROM_ADDRESS="reports@qt-agent.kro.kr",
        EMAIL_LOCAL_RECIPIENT_ALLOWLIST="allowed@example.test",
    )
    object.__setattr__(settings, "email_from_address", f"{marker} invalid@qt-agent.kro.kr")
    provider = BrevoEmailProvider(settings)
    construction_calls: list[str] = []

    def unexpected_headers(*_args, **_kwargs):
        construction_calls.append("headers")
        raise AssertionError("provider request headers must not be constructed")

    def unexpected_payload(*_args, **_kwargs):
        construction_calls.append("payload")
        raise AssertionError("provider request payload must not be constructed")

    monkeypatch.setattr(provider, "_request_headers", unexpected_headers)
    monkeypatch.setattr(provider, "_request_payload", unexpected_payload)
    message = EmailDeliveryMessage(
        recipient_email="allowed@example.test",
        sender_email="reports@qt-agent.kro.kr",
        sender_name="Quant Agent",
        subject="Synthetic subject",
        html_body="<p>Synthetic body</p>",
        text_body="Synthetic body",
        correlation_id=None,
        idempotency_key="synthetic-idempotency-key",
        template_name="report_completed",
        template_version="v1",
    )

    with pytest.raises(AppError) as rejected:
        await provider.send(message)

    assert rejected.value.code == "email_from_address_invalid"
    assert marker not in rejected.value.message
    assert marker not in str(rejected.value.details)
    assert construction_calls == []


@pytest.mark.asyncio
async def test_invalid_sender_prevents_queue_release_and_claim(monkeypatch):
    marker = "category" + "_shaped_worker_sender"
    async def unexpected_outbox_call(*_args, **_kwargs):
        raise AssertionError("outbox must not be touched for an invalid sender")

    monkeypatch.setattr(
        email_delivery_worker.email_outbox,
        "release_expired_claims",
        unexpected_outbox_call,
    )
    monkeypatch.setattr(
        email_delivery_worker.email_outbox,
        "claim_next_delivery",
        unexpected_outbox_call,
    )
    settings = _email_settings(
        EMAIL_FROM_ADDRESS="reports@qt-agent.kro.kr",
        EMAIL_DELIVERY_WORKER_ENABLED=True,
    )
    object.__setattr__(settings, "email_from_address", f"{marker} invalid@qt-agent.kro.kr")
    worker = EmailDeliveryWorker(object(), settings)

    with pytest.raises(AppError) as rejected:
        await worker.run_once()

    assert rejected.value.code == "email_from_address_invalid"
    assert marker not in rejected.value.message
    assert marker not in str(rejected.value.details)


def test_observability_excludes_operational_identifiers(caplog):
    logger = logging.getLogger("track4-email-identifier-redaction-test")
    with caplog.at_level(logging.INFO, logger=logger.name):
        payload = emit_email_event(
            logger,
            "worker_check",
            delivery_id="synthetic-delivery",
            report_id="synthetic-report",
            correlation_id="synthetic-correlation",
            provider_event_id="synthetic-provider-event",
            request_id="synthetic-request",
            webhook_event_id="synthetic-webhook-event",
            status="ok",
        )

    assert payload == {"event": "worker_check", "status": "ok"}
    assert "synthetic-" not in caplog.text


def test_brevo_message_id_preserves_angle_brackets_and_logs_only_presence(caplog):
    provider_message_id = "<synthetic-provider-id>"
    assert _normalize_message_id(f"  {provider_message_id}  ") == provider_message_id

    logger = logging.getLogger("track4-provider-id-redaction-test")
    with caplog.at_level(logging.INFO, logger=logger.name):
        payload = emit_email_event(
            logger,
            "provider_request_succeeded",
            provider_message_id=provider_message_id,
            provider_message_id_present=True,
        )
    assert provider_message_id not in caplog.text
    assert "provider_message_id" not in payload
    assert payload["provider_message_id_present"] is True


def test_brevo_read_only_inspector_uses_exact_params_and_maps_safe_events():
    calls: list[httpx.Request] = []
    provider_message_id = "<synthetic-provider-id>"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/v3/smtp/emails" and request.url.params.get("messageId"):
            return httpx.Response(
                200,
                json={"transactionalEmails": [{"messageId": provider_message_id, "uuid": "synthetic-uuid"}]},
            )
        if request.url.path == "/v3/smtp/emails" and request.url.params.get("email"):
            return httpx.Response(
                200,
                json={"transactionalEmails": [{"messageId": provider_message_id, "uuid": "synthetic-uuid"}]},
            )
        if request.url.path == "/v3/smtp/emails/synthetic-uuid":
            return httpx.Response(200, json={"events": [{"name": "delivered", "time": "2030-01-02T00:00:00Z"}]})
        if request.url.path == "/v3/smtp/statistics/events":
            return httpx.Response(
                200,
                json={"events": [{"event": "requests", "messageId": provider_message_id}]},
            )
        if request.url.path == "/v3/smtp/blockedContacts":
            return httpx.Response(
                200,
                json={
                    "contacts": [
                        {
                            "email": "recipient@example.test",
                            "senderEmail": "sender@example.test",
                            "reason": {"code": "hardBounce"},
                        }
                    ],
                    "count": 1,
                },
            )
        raise AssertionError(f"unexpected read-only request path: {request.url.path}")

    inspector = BrevoEmailInspector(_email_settings(), transport=httpx.MockTransport(handler))

    async def inspect() -> None:
        lookup = await inspector.get_transactional_email_by_message_id(provider_message_id)
        assert lookup is not None and lookup.uuid == "synthetic-uuid"
        window = await inspector.get_transactional_emails_by_recipient_window(
            "recipient@example.test", start_date=date(2030, 1, 1), end_date=date(2030, 1, 2)
        )
        assert [item.message_id for item in window] == [provider_message_id]
        history = await inspector.get_transactional_email_history_by_uuid("synthetic-uuid")
        assert [event.delivery_status for event in history] == ["delivered"]
        exact_events = await inspector.get_email_events_by_message_id(provider_message_id)
        assert [event.delivery_status for event in exact_events] == ["pending"]
        window_events = await inspector.get_email_events_by_recipient_window(
            "recipient@example.test", start_date=date(2030, 1, 1), end_date=date(2030, 1, 2)
        )
        assert [event.message_id for event in window_events] == [provider_message_id]
        blocked = await inspector.get_blocked_contact_status(
            "recipient@example.test", sender_email="sender@example.test"
        )
        assert blocked.matched is True
        assert blocked.reason_category == "hard_bounce"
        assert blocked.sender_specific_match is True

    asyncio.run(inspect())

    assert calls and all(request.method == "GET" for request in calls)
    exact_request = next(request for request in calls if request.url.params.get("messageId"))
    assert exact_request.url.params["messageId"] == provider_message_id
    assert "%3Csynthetic-provider-id%3E" in str(exact_request.url)
    assert "%253C" not in str(exact_request.url)


def test_provider_acceptance_is_pending_until_a_delivery_event():
    entry = _to_entry(
        {
            "delivery_id": "delivery-1",
            "report_id": "report-1",
            "status": "sent",
            "created_at": datetime(2030, 1, 1, tzinfo=UTC),
            "metadata_jsonb": {
                "submission_status": "SENT",
                "provider_delivery_status": "accepted",
            },
        }
    )

    assert entry.providerSubmissionStatus == "accepted"
    assert entry.providerDeliveryStatus == "pending"
    assert entry.deliveredAt is None
    assert map_brevo_delivery_event("requests") == "pending"
    assert map_brevo_delivery_event("delivered") == "delivered"
    assert map_brevo_delivery_event("hardBounces") == "hard_bounce"
    assert map_brevo_delivery_event("unrecognized") == "unknown"
