from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from app.api.routes import email_reports
from app.db import email_outbox
from app.schemas.email_delivery import EmailDeliveryMessage
from app.services import email_delivery
from app.services.email_provider import BREVO_SANDBOX_HEADER, BREVO_SANDBOX_VALUE, BrevoEmailProvider
from app.services.email_templates import render_report_completed_template
from app.workers.email_delivery_worker import EmailDeliveryWorker
from tests.unit.test_email_track4 import _email_settings
from tests.unit.test_fe_contract_routes import API_ORIGIN, _create_session, make_client


def _message() -> EmailDeliveryMessage:
    return EmailDeliveryMessage(
        recipient_email="allowed@example.test",
        sender_email="sender@example.test",
        sender_name="Quant Agent",
        subject="Synthetic subject",
        html_body="<p>Synthetic body</p>",
        text_body="Synthetic body",
        correlation_id="report:report-1",
        idempotency_key="synthetic-idempotency-key",
        template_name="report_completed",
        template_version="v1",
    )


def test_brevo_sandbox_mode_is_sent_as_an_http_request_header():
    settings = _email_settings(EMAIL_PROVIDER="brevo", BREVO_SANDBOX_MODE=True)
    provider = BrevoEmailProvider(settings)
    message = _message()

    headers = provider._request_headers(message, provider_name="brevo")  # noqa: SLF001
    payload = provider._request_payload(message, provider_name="brevo")  # noqa: SLF001

    assert headers[BREVO_SANDBOX_HEADER] == BREVO_SANDBOX_VALUE
    assert BREVO_SANDBOX_HEADER not in payload["headers"]


def test_report_email_links_to_the_owner_scoped_email_report_screen():
    rendered = render_report_completed_template(
        public_base_url="https://reports.example.test",
        report_id="report-1",
        report_title="Report",
        report_summary="Summary",
        recipient_email="owner@example.test",
    )

    assert "https://reports.example.test/me/email-reports/report-1" in rendered.text_body
    assert "https://reports.example.test/me/email-reports/report-1" in rendered.html_body


class _ExplodingEngine:
    """Stand-in for an engine whose driver has started raising on every statement."""


def test_worker_survives_a_driver_failure_while_processing_a_claim(monkeypatch, caplog):
    settings = _email_settings(EMAIL_DELIVERY_WORKER_ENABLED=True)
    worker = EmailDeliveryWorker(_ExplodingEngine(), settings, provider=object())
    worker._startup_validated = True  # noqa: SLF001
    released: list[dict[str, Any]] = []

    async def exploding_revalidate(*_args, **_kwargs):
        raise RuntimeError("connection is closed")

    async def fake_mark_retry_pending(_engine, **kwargs):
        released.append(kwargs)
        return {"status": "RETRY_PENDING"}

    monkeypatch.setattr(worker, "_revalidate_claim", exploding_revalidate)
    monkeypatch.setattr(email_outbox, "mark_retry_pending", fake_mark_retry_pending)
    claim = {
        "delivery_id": "delivery-1",
        "claim_token": "claim-1",
        "report_id": "report-1",
        "trigger_type": "report_completed",
        "user_id": "7",
        "attempt_count": 1,
        "status": "PROCESSING",
    }

    with caplog.at_level(logging.INFO, logger="app.workers.email_delivery_worker"):
        asyncio.run(worker._process_claim_guarded(claim))  # noqa: SLF001

    assert '"event": "claim_lost"' in caplog.text
    assert '"reason_code": "RuntimeError"' in caplog.text
    assert [entry["error_code"] for entry in released] == ["unexpected_worker_error"]


def test_worker_run_loop_survives_a_failing_run_once(monkeypatch, caplog):
    settings = _email_settings(EMAIL_DELIVERY_WORKER_ENABLED=True)
    worker = EmailDeliveryWorker(_ExplodingEngine(), settings, provider=object())
    monkeypatch.setattr(worker, "validate_startup", lambda: None)
    calls: list[int] = []

    async def flaky_run_once() -> int:
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("connection is closed")
        worker.stop()
        return 0

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(worker, "run_once", flaky_run_once)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    with caplog.at_level(logging.INFO, logger="app.workers.email_delivery_worker"):
        asyncio.run(worker.run())

    assert len(calls) == 2
    assert '"reason_code": "run_once_failed"' in caplog.text


@pytest.mark.parametrize(
    ("delivery", "expected"),
    [
        ({"created": True, "submission_status": "PENDING"}, "queued"),
        ({"created": False, "submission_status": "SENT"}, "requeue"),
        ({"created": False, "submission_status": "FAILED"}, "requeue"),
        ({"created": False, "submission_status": "CANCELLED"}, "requeue"),
        ({"created": False, "submission_status": "PENDING"}, "noop"),
        ({"created": False, "submission_status": "RETRY_PENDING"}, "noop"),
        ({"created": False, "submission_status": "PROCESSING"}, "noop"),
        (None, "unavailable"),
    ],
)
def test_resend_action_only_requeues_terminal_deliveries(delivery, expected):
    assert email_delivery.resolve_resend_action(delivery) == expected


def _resend(monkeypatch, *, delivery: dict[str, Any] | None, requeued: dict[str, Any] | None = None):
    client, app = make_client()
    session_id, csrf_token = _create_session(app, user_id="7")

    async def fake_user(_engine, user_id: str):
        return {"id": user_id, "email": "owner@example.test"}

    async def fake_create(*_args, **_kwargs):
        return {"eligibility": None, "request": None, "template": None, "delivery": delivery}

    async def fake_requeue(_db, *, delivery_id: str, **_kwargs):
        assert delivery_id == str(delivery["delivery_id"])
        return requeued

    monkeypatch.setattr(email_reports, "load_user_by_id", fake_user)
    monkeypatch.setattr(email_delivery, "create_report_completed_delivery", fake_create)
    monkeypatch.setattr(email_delivery, "requeue_delivery", fake_requeue)
    return client.post(
        "/api/v1/reports/report-1/resend",
        cookies={app.state.settings.auth_session_cookie_name: session_id},
        headers={"Origin": API_ORIGIN, "X-CSRF-Token": csrf_token},
    )


def test_resend_requeues_a_sent_delivery_and_reports_202(monkeypatch):
    sent = {"delivery_id": "11111111-1111-1111-1111-111111111111", "created": False, "submission_status": "SENT"}
    requeued = {**sent, "submission_status": "PENDING"}

    assert _resend(monkeypatch, delivery=sent, requeued=requeued).status_code == 202


def test_resend_is_a_noop_while_a_pending_delivery_is_still_queued(monkeypatch):
    pending = {"delivery_id": "11111111-1111-1111-1111-111111111111", "created": False, "submission_status": "PENDING"}

    assert _resend(monkeypatch, delivery=pending).status_code == 204


def test_resend_reports_409_when_no_delivery_can_be_created(monkeypatch):
    response = _resend(monkeypatch, delivery=None)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_resend_unavailable"
