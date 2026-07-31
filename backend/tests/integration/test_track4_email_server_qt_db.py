from __future__ import annotations

import asyncio
import copy
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.core.errors import AppError
from app.db import email_delivery_history, email_outbox
from app.schemas.email_delivery import EmailDeliverySendResult
from app.services import email_delivery, email_unsubscribe, fe_contract_store
from app.workers.email_delivery_worker import EmailDeliveryWorker
from tests.integration.test_track_c_server_run_report_qt_db import (
    API_ORIGIN,
    _completion_payload,
    _count,
    _execute,
    _fetch_one,
    _prepare_context,
)
from tests.unit.test_auth_config import valid_settings

OPT_IN_ENV = "TRACK4_EMAIL_SERVER_WRITE_INTEGRATION"
SYNTHETIC_SOURCE = "track4-email-report-e2e"
TARGET_RELATIONS = (
    "app.users",
    "app.strategy",
    "app.strategy_report_profile",
    "app.backtest_run",
    "app.ai_backtest_report",
    "app.backtest_summary",
    "app.backtest_metric_detail",
    "app.strategy_email_report",
    "app.strategy_email_report_candidate",
    "app.strategy_email_report_news",
    "app.email_digest_subscription",
    "app.email_delivery_history",
)


def _enabled() -> bool:
    return os.getenv(OPT_IN_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


class SequenceProvider:
    def __init__(self, *results: EmailDeliverySendResult) -> None:
        self._results = list(results)
        self.send_count = 0

    def validate_configuration(self) -> None:
        return None

    async def send(self, _message: Any) -> EmailDeliverySendResult:
        self.send_count += 1
        if not self._results:
            raise AssertionError("fake provider result sequence was exhausted")
        return self._results.pop(0)


def _accepted(message_id: str) -> EmailDeliverySendResult:
    return EmailDeliverySendResult(
        provider="brevo",
        provider_message_id=message_id,
        status="accepted",
        retryable=False,
    )


def _retryable() -> EmailDeliverySendResult:
    return EmailDeliverySendResult(
        provider="brevo",
        status="retryable_error",
        retryable=True,
        error_code="provider_temporarily_unavailable",
        error_message="controlled retryable provider failure",
    )


def _email_settings(context: dict[str, Any]) -> Any:
    return valid_settings(
        include_raw_audit=False,
        APP_ENV="test",
        AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN,
        AUTH_ALLOWED_ORIGINS="https://fe.example.co.kr",
        AUTH_CSRF_REQUIRED=True,
        DATABASE_URL=context["settings"].database_url_value,
        TRADING_DATA_DATABASE_URL=context["settings"].trading_data_database_url_value,
        EMAIL_DELIVERY_ENABLED=True,
        EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED=True,
        EMAIL_DELIVERY_WORKER_ENABLED=True,
        EMAIL_PROVIDER="brevo",
        BREVO_SENDER_EMAIL="reports@qt-agent.kro.kr",
        BREVO_API_KEY="track4-controlled-fake-provider-key",
        EMAIL_PUBLIC_BASE_URL="https://reports.example.test",
        EMAIL_UNSUBSCRIBE_ENABLED=True,
        EMAIL_UNSUBSCRIBE_SIGNING_SECRET="track4-controlled-ephemeral-signing-secret",
        EMAIL_UNSUBSCRIBE_BASE_URL="https://preferences.example.test",
        EMAIL_LOCAL_LIVE_SEND_ENABLED=True,
        EMAIL_LOCAL_RECIPIENT_ALLOWLIST=f"track2-report-remediation-owner-{context['token']}@example.com",
        EMAIL_MAX_ATTEMPTS=3,
        EMAIL_RETRY_BASE_SECONDS=1,
        EMAIL_WORKER_BATCH_SIZE=1,
        EMAIL_WORKER_CLAIM_LEASE_SECONDS=1,
    )


def _run_identifiers(owner_id: str, create_payload: dict[str, Any]) -> tuple[str, str, str]:
    run_id = fe_contract_store._analysis_run_uuid(owner_id, create_payload)  # type: ignore[attr-defined]
    strategy_id = fe_contract_store._analysis_run_strategy_uuid(owner_id, create_payload)  # type: ignore[attr-defined]
    report_id, _ = fe_contract_store._analysis_completion_report_id(run_id)  # type: ignore[attr-defined]
    return run_id, strategy_id, report_id


async def _cleanup(context: dict[str, Any], identifiers: list[tuple[str, str, str]]) -> dict[str, int]:
    engine = context["trading_engine"]
    owner_id = int(context["owner_id"])
    intruder_id = int(context["intruder_id"])
    await _execute(
        engine,
        "DELETE FROM app.email_delivery_history WHERE user_id IN (CAST(:owner_id AS bigint), CAST(:intruder_id AS bigint))",
        {"owner_id": owner_id, "intruder_id": intruder_id},
    )
    await _execute(
        engine,
        "DELETE FROM app.email_digest_subscription WHERE user_id IN (CAST(:owner_id AS bigint), CAST(:intruder_id AS bigint))",
        {"owner_id": owner_id, "intruder_id": intruder_id},
    )
    await _execute(
        engine,
        "DELETE FROM app.users WHERE user_id IN (CAST(:owner_id AS bigint), CAST(:intruder_id AS bigint))",
        {"owner_id": owner_id, "intruder_id": intruder_id},
    )
    for run_id, strategy_id, report_id in identifiers:
        params = {"run_id": run_id, "strategy_id": strategy_id, "report_id": report_id}
        for sql in (
            "DELETE FROM app.strategy_email_report_candidate WHERE report_id = :report_id",
            "DELETE FROM app.strategy_email_report_news WHERE report_id = :report_id",
            "DELETE FROM app.strategy_email_report WHERE report_id = :report_id",
            "DELETE FROM app.backtest_summary WHERE run_id = :run_id",
            "DELETE FROM app.backtest_metric_detail WHERE run_id = :run_id",
            "DELETE FROM app.ai_backtest_report WHERE report_id = CAST(:report_id AS uuid)",
            "DELETE FROM app.backtest_run WHERE run_id = :run_id",
            "DELETE FROM app.strategy_report_profile WHERE strategy_id = :strategy_id",
            "DELETE FROM app.strategy WHERE strategy_id = :strategy_id",
        ):
            await _execute(engine, sql, params)
    await _execute(
        engine,
        "DELETE FROM app.users WHERE auth_provider = 'google' AND provider_user_id IN (:owner, :intruder)",
        {"owner": context["owner_provider_id"], "intruder": context["intruder_provider_id"]},
    )

    residual = {
        "users": await _count(
            engine,
            "app.users",
            "auth_provider = 'google' AND provider_user_id IN (:owner, :intruder)",
            {"owner": context["owner_provider_id"], "intruder": context["intruder_provider_id"]},
        ),
        "email_digest_subscription": await _count(
            engine,
            "app.email_digest_subscription",
            "user_id IN (CAST(:owner_id AS bigint), CAST(:intruder_id AS bigint))",
            {"owner_id": owner_id, "intruder_id": intruder_id},
        ),
        "email_delivery_history": await _count(
            engine,
            "app.email_delivery_history",
            "user_id IN (CAST(:owner_id AS bigint), CAST(:intruder_id AS bigint))",
            {"owner_id": owner_id, "intruder_id": intruder_id},
        ),
    }
    for run_id, strategy_id, report_id in identifiers:
        params = {"run_id": run_id, "strategy_id": strategy_id, "report_id": report_id}
        checks = {
            "strategy": ("app.strategy", "strategy_id = :strategy_id"),
            "strategy_report_profile": ("app.strategy_report_profile", "strategy_id = :strategy_id"),
            "backtest_run": ("app.backtest_run", "run_id = :run_id"),
            "ai_backtest_report": ("app.ai_backtest_report", "report_id = CAST(:report_id AS uuid)"),
            "backtest_summary": ("app.backtest_summary", "run_id = :run_id"),
            "backtest_metric_detail": ("app.backtest_metric_detail", "run_id = :run_id"),
            "strategy_email_report": ("app.strategy_email_report", "report_id = :report_id"),
            "strategy_email_report_candidate": (
                "app.strategy_email_report_candidate",
                "report_id = :report_id",
            ),
            "strategy_email_report_news": ("app.strategy_email_report_news", "report_id = :report_id"),
        }
        for name, (relation, predicate) in checks.items():
            residual[name] = residual.get(name, 0) + await _count(engine, relation, predicate, params)
    return residual


@pytest.mark.skipif(not _enabled(), reason=f"{OPT_IN_ENV}=1 is required for controlled qt_db DML")
@pytest.mark.asyncio
async def test_track4_email_report_server_qt_db() -> None:
    context = await _prepare_context()
    context["settings"] = _email_settings(context)
    context["app"].state.settings = context["settings"]
    owner_id = context["owner_id"]
    identifiers: list[tuple[str, str, str]] = []
    owner_session_id = intruder_session_id = None
    cleanup_counts: dict[str, int] | None = None
    try:
        for relation in TARGET_RELATIONS:
            row = await _fetch_one(
                context["trading_engine"],
                "SELECT to_regclass(:relation) AS relation",
                {"relation": relation},
            )
            assert row is not None and row["relation"] == relation

        owner_session_id, owner_csrf = await context["store"].create_session(user_id=owner_id)
        intruder_session_id, intruder_csrf = await context["store"].create_session(user_id=context["intruder_id"])
        owner_cookie = {context["settings"].auth_session_cookie_name: owner_session_id}
        intruder_cookie = {context["settings"].auth_session_cookie_name: intruder_session_id}
        owner_headers = {"Origin": API_ORIGIN, "X-CSRF-Token": owner_csrf}
        intruder_headers = {"Origin": API_ORIGIN, "X-CSRF-Token": intruder_csrf}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=context["app"]),
            base_url=API_ORIGIN,
        ) as client:
            defaults = await client.get("/api/v1/me/notifications", cookies=owner_cookie)
            saved = await client.patch(
                "/api/v1/me/notifications",
                cookies=owner_cookie,
                headers=owner_headers,
                json={
                    "dailyReportEmail": True,
                    "actionEmails": True,
                    "marketingEmail": False,
                    "deliveryHour": "09:30",
                },
            )
            replay_saved = await client.patch(
                "/api/v1/me/notifications",
                cookies=owner_cookie,
                headers=owner_headers,
                json={
                    "dailyReportEmail": True,
                    "actionEmails": True,
                    "marketingEmail": False,
                    "deliveryHour": "09:30",
                },
            )
            reloaded = await client.get("/api/v1/me/notifications", cookies=owner_cookie)
            invalid = await client.patch(
                "/api/v1/me/notifications",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"dailyReportEmail": True, "deliveryHour": "29:99"},
            )
            invalid_email = await client.patch(
                "/api/v1/me/notifications",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"dailyReportEmail": True, "email": "invalid"},
            )
            invalid_boolean = await client.patch(
                "/api/v1/me/notifications",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"dailyReportEmail": "yes"},
            )
            assert defaults.status_code == 200
            assert saved.status_code == replay_saved.status_code == reloaded.status_code == 200
            assert saved.json() == replay_saved.json() == reloaded.json()
            assert reloaded.json()["deliveryHour"] == "09:30"
            assert invalid.status_code == 422
            assert invalid_email.status_code == 422
            assert invalid_boolean.status_code == 422

            intruder_saved = await client.patch(
                "/api/v1/me/notifications",
                cookies=intruder_cookie,
                headers=intruder_headers,
                json={"dailyReportEmail": False, "actionEmails": False, "deliveryHour": "07:00"},
            )
            owner_after_intruder = await client.get("/api/v1/me/notifications", cookies=owner_cookie)
            assert intruder_saved.status_code == 200
            assert owner_after_intruder.json() == reloaded.json()

            daily_disabled = await client.patch(
                "/api/v1/me/notifications",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"dailyReportEmail": False, "actionEmails": True, "deliveryHour": "09:30"},
            )
            assert daily_disabled.status_code == 200
            daily_disabled_payload = {
                "query": f"{SYNTHETIC_SOURCE} daily-disabled {context['token']}",
                "aiJobId": f"{SYNTHETIC_SOURCE}:daily-disabled:{context['token']}",
                "ticker": f"D{context['token'][:7]}",
                "timeframe": "daily",
                "requestPayload": {"source": SYNTHETIC_SOURCE, "case": "daily-disabled"},
            }
            daily_disabled_ids = _run_identifiers(owner_id, daily_disabled_payload)
            identifiers.append(daily_disabled_ids)
            daily_disabled_run_id, _daily_disabled_strategy_id, daily_disabled_report_id = daily_disabled_ids
            daily_disabled_created = await client.post(
                "/api/v1/runs",
                cookies=owner_cookie,
                headers=owner_headers,
                json=daily_disabled_payload,
            )
            daily_disabled_completed = await client.post(
                f"/api/v1/runs/{daily_disabled_run_id}/complete",
                cookies=owner_cookie,
                headers=owner_headers,
                json=_completion_payload(token=f"{context['token']}d"),
            )
            assert daily_disabled_created.status_code == 201
            assert daily_disabled_completed.status_code == 200
            assert await _count(
                context["trading_engine"],
                "app.email_delivery_history",
                "user_id = CAST(:user_id AS bigint) AND report_id = :report_id",
                {"user_id": int(owner_id), "report_id": daily_disabled_report_id},
            ) == 0

            daily_reenabled = await client.patch(
                "/api/v1/me/notifications",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"dailyReportEmail": True, "actionEmails": True, "deliveryHour": "09:30"},
            )
            assert daily_reenabled.status_code == 200

            first_create_payload = {
                "query": f"{SYNTHETIC_SOURCE} eligible {context['token']}",
                "aiJobId": f"{SYNTHETIC_SOURCE}:eligible:{context['token']}",
                "ticker": f"E{context['token'][:7]}",
                "timeframe": "daily",
                "requestPayload": {"source": SYNTHETIC_SOURCE, "case": "eligible"},
            }
            first_ids = _run_identifiers(owner_id, first_create_payload)
            identifiers.append(first_ids)
            first_run_id, first_strategy_id, first_report_id = first_ids
            created = await client.post(
                "/api/v1/runs",
                cookies=owner_cookie,
                headers=owner_headers,
                json=first_create_payload,
            )
            assert created.status_code == 201, created.text

            subscribed = await client.post(
                "/api/v1/me/email-strategy-subscriptions",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"strategyId": first_strategy_id},
            )
            duplicate_subscription = await client.post(
                "/api/v1/me/email-strategy-subscriptions",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"strategyId": first_strategy_id},
            )
            intruder_subscription = await client.post(
                "/api/v1/me/email-strategy-subscriptions",
                cookies=intruder_cookie,
                headers=intruder_headers,
                json={"strategyId": first_strategy_id},
            )
            assert subscribed.status_code == duplicate_subscription.status_code == 200
            assert subscribed.json()["subscriptionCount"] == duplicate_subscription.json()["subscriptionCount"] == 1
            assert intruder_subscription.status_code == 404

            completion = _completion_payload(token=context["token"])
            completed = await client.post(
                f"/api/v1/runs/{first_run_id}/complete",
                cookies=owner_cookie,
                headers=owner_headers,
                json=completion,
            )
            replay_completed = await client.post(
                f"/api/v1/runs/{first_run_id}/complete",
                cookies=owner_cookie,
                headers=owner_headers,
                json=completion,
            )
            conflicting = copy.deepcopy(completion)
            conflicting["result"]["summary"] = "controlled conflicting summary"
            conflict = await client.post(
                f"/api/v1/runs/{first_run_id}/complete",
                cookies=owner_cookie,
                headers=owner_headers,
                json=conflicting,
            )
            assert completed.status_code == replay_completed.status_code == 200
            assert completed.json()["created"] is True
            assert replay_completed.json()["created"] is False
            assert conflict.status_code == 409
            assert await _count(
                context["trading_engine"],
                "app.email_delivery_history",
                "user_id = CAST(:user_id AS bigint) AND report_id = :report_id",
                {"user_id": int(owner_id), "report_id": first_report_id},
            ) == 1
            first_delivery = await _fetch_one(
                context["trading_engine"],
                """
                SELECT delivery_id::text AS delivery_id
                FROM app.email_delivery_history
                WHERE user_id = CAST(:user_id AS bigint) AND report_id = :report_id
                """,
                {"user_id": int(owner_id), "report_id": first_report_id},
            )
            assert first_delivery is not None
            first_delivery_id = str(first_delivery["delivery_id"])

            clock = datetime.now(UTC)
            claims = await asyncio.gather(
                email_outbox.claim_next_delivery(
                    context["trading_engine"],
                    claimed_by="track4-claim-a",
                    claim_ttl_seconds=1,
                    now=clock,
                    delivery_scope_id=first_delivery_id,
                ),
                email_outbox.claim_next_delivery(
                    context["trading_engine"],
                    claimed_by="track4-claim-b",
                    claim_ttl_seconds=1,
                    now=clock,
                    delivery_scope_id=first_delivery_id,
                ),
            )
            claimed = [claim for claim in claims if claim is not None]
            assert len(claimed) == 1
            recovered = await email_outbox.release_expired_claims(
                context["trading_engine"],
                now=clock + timedelta(seconds=2),
                delivery_scope_id=first_delivery_id,
            )
            assert len(recovered) == 1
            reclaimed = await email_outbox.claim_next_delivery(
                context["trading_engine"],
                claimed_by="track4-claim-recovered",
                claim_ttl_seconds=1,
                now=clock + timedelta(seconds=2),
                delivery_scope_id=first_delivery_id,
            )
            assert reclaimed is not None
            with pytest.raises(AppError) as stale_cancel:
                await email_outbox.mark_cancelled(
                    context["trading_engine"],
                    delivery_id=reclaimed["delivery_id"],
                    claim_token=str(claimed[0]["claim_token"]),
                    error_code="stale-worker-cancel",
                )
            assert stale_cancel.value.code == email_outbox.EMAIL_OUTBOX_STALE_CLAIM_CODE
            still_claimed = await email_outbox.get_delivery(context["trading_engine"], reclaimed["delivery_id"])
            assert still_claimed is not None
            assert still_claimed["status"] == "PROCESSING"
            assert still_claimed["claim_token"] == reclaimed["claim_token"]
            recovered_again = await email_outbox.release_expired_claims(
                context["trading_engine"],
                now=clock + timedelta(seconds=4),
                delivery_scope_id=first_delivery_id,
            )
            assert len(recovered_again) == 1
            await _execute(
                context["trading_engine"],
                """
                UPDATE app.email_delivery_history
                SET metadata_jsonb = jsonb_set(metadata_jsonb, '{available_at}', to_jsonb(now()::text), true)
                WHERE delivery_id = CAST(:delivery_id AS uuid)
                """,
                {"delivery_id": claimed[0]["delivery_id"]},
            )

            success_provider = SequenceProvider(_accepted("track4-fake-success"))
            success_worker = EmailDeliveryWorker(
                context["trading_engine"],
                context["settings"],
                provider=success_provider,
                delivery_scope_id=first_delivery_id,
            )
            success_worker.validate_startup()
            assert await success_worker.run_once() == 1
            assert success_provider.send_count == 1
            sent = await email_outbox.get_delivery(context["trading_engine"], claimed[0]["delivery_id"])
            assert sent is not None
            assert sent["status"] == "SENT"
            assert sent["sent_at"] is not None
            assert sent["attempt_count"] == 3
            assert sent["provider_submission_status"] == "accepted"
            assert sent["provider_delivery_status"] == "pending"
            assert sent["provider_status_source"] == "provider_response"
            assert await success_worker.run_once() == 0
            assert success_provider.send_count == 1

            eligibility, base_request, _template = await email_delivery.build_report_completed_delivery_request(
                context["trading_engine"],
                settings=context["settings"],
                user_id=owner_id,
                report_id=first_report_id,
            )
            assert eligibility.allowed and base_request is not None

            retry_request = replace(
                base_request,
                idempotency_key=f"{base_request.idempotency_key}:retry",
                max_attempts=2,
                available_at=datetime.now(UTC),
            )
            retry_delivery = await email_outbox.create_or_get_delivery(context["trading_engine"], retry_request)
            retry_provider = SequenceProvider(_retryable(), _accepted("track4-fake-retry-success"))
            retry_worker = EmailDeliveryWorker(
                context["trading_engine"],
                context["settings"],
                provider=retry_provider,
                delivery_scope_id=retry_delivery["delivery_id"],
            )
            assert await retry_worker.run_once() == 1
            retry_pending = await email_outbox.get_delivery(
                context["trading_engine"], retry_delivery["delivery_id"]
            )
            assert retry_pending is not None
            assert retry_pending["status"] == "RETRY_PENDING"
            assert retry_pending["attempt_count"] == 1
            assert retry_pending["safe_failure_category"] == "provider_temporarily_unavailable"
            assert await retry_worker.run_once() == 0
            await asyncio.sleep(1.1)
            assert await retry_worker.run_once() == 1
            retry_sent = await email_outbox.get_delivery(context["trading_engine"], retry_delivery["delivery_id"])
            assert retry_sent is not None
            assert retry_sent["status"] == "SENT"
            assert retry_sent["attempt_count"] == 2
            assert retry_sent["provider_submission_status"] == "accepted"
            assert retry_sent["provider_delivery_status"] == "pending"

            terminal_request = replace(
                base_request,
                idempotency_key=f"{base_request.idempotency_key}:terminal",
                max_attempts=1,
                available_at=datetime.now(UTC),
            )
            terminal_delivery = await email_outbox.create_or_get_delivery(context["trading_engine"], terminal_request)
            terminal_provider = SequenceProvider(_retryable())
            terminal_worker = EmailDeliveryWorker(
                context["trading_engine"],
                context["settings"],
                provider=terminal_provider,
                delivery_scope_id=terminal_delivery["delivery_id"],
            )
            assert await terminal_worker.run_once() == 1
            terminal_failed = await email_outbox.get_delivery(
                context["trading_engine"], terminal_delivery["delivery_id"]
            )
            assert terminal_failed is not None
            assert terminal_failed["status"] == "FAILED"
            assert terminal_failed["attempt_count"] == 1

            history_page = await client.get(
                "/api/v1/me/email-deliveries?limit=2",
                cookies=owner_cookie,
            )
            intruder_history = await client.get(
                "/api/v1/me/email-deliveries?limit=20",
                cookies=intruder_cookie,
            )
            assert history_page.status_code == intruder_history.status_code == 200
            assert len(history_page.json()["items"]) == 2
            assert history_page.json()["meta"]["hasMore"] is True
            cursor = history_page.json()["meta"]["nextCursor"]
            assert cursor
            next_page = await client.get(
                f"/api/v1/me/email-deliveries?limit=2&cursor={cursor}",
                cookies=owner_cookie,
            )
            invalid_cursor = email_delivery_history._encode_cursor(datetime.now(UTC), "not-a-uuid")
            malformed_page = await client.get(
                "/api/v1/me/email-deliveries",
                cookies=owner_cookie,
                params={"cursor": invalid_cursor},
            )
            assert next_page.status_code == 200
            assert len(next_page.json()["items"]) == 1
            assert malformed_page.status_code == 422
            assert intruder_history.json()["items"] == []
            for item in history_page.json()["items"] + next_page.json()["items"]:
                assert "recipientEmail" not in item
                assert "payload" not in item
                assert "htmlBody" not in item
                assert "textBody" not in item

            token = email_unsubscribe.generate_unsubscribe_token(
                context["settings"], user_id=owner_id, nonce="track4-controlled-nonce"
            )
            inspection = await client.get("/api/v1/unsubscribe", params={"token": token})
            unsubscribed = await client.post("/api/v1/unsubscribe", json={"token": token})
            repeated_unsubscribe = await client.post("/api/v1/unsubscribe", json={"token": token})
            invalid_unsubscribe = await client.get("/api/v1/unsubscribe", params={"token": "invalid"})
            assert inspection.status_code == unsubscribed.status_code == repeated_unsubscribe.status_code == 200
            assert inspection.json()["status"] == "ready"
            assert unsubscribed.json()["status"] == "unsubscribed"
            assert repeated_unsubscribe.json()["status"] == "already_unsubscribed"
            assert invalid_unsubscribe.status_code == 400

            second_create_payload = {
                "query": f"{SYNTHETIC_SOURCE} suppressed {context['token']}",
                "aiJobId": f"{SYNTHETIC_SOURCE}:suppressed:{context['token']}",
                "ticker": f"S{context['token'][:7]}",
                "timeframe": "daily",
                "requestPayload": {"source": SYNTHETIC_SOURCE, "case": "suppressed"},
            }
            second_ids = _run_identifiers(owner_id, second_create_payload)
            identifiers.append(second_ids)
            second_run_id, _second_strategy_id, second_report_id = second_ids
            second_created = await client.post(
                "/api/v1/runs",
                cookies=owner_cookie,
                headers=owner_headers,
                json=second_create_payload,
            )
            second_completed = await client.post(
                f"/api/v1/runs/{second_run_id}/complete",
                cookies=owner_cookie,
                headers=owner_headers,
                json=_completion_payload(token=f"{context['token']}b"),
            )
            assert second_created.status_code == 201
            assert second_completed.status_code == 200
            assert await _count(
                context["trading_engine"],
                "app.email_delivery_history",
                "user_id = CAST(:user_id AS bigint) AND report_id = :report_id",
                {"user_id": int(owner_id), "report_id": second_report_id},
            ) == 0

            reenabled = await client.patch(
                "/api/v1/me/notifications",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"dailyReportEmail": True, "actionEmails": True, "deliveryHour": "09:30"},
            )
            assert reenabled.status_code == 200
            rollback_create_payload = {
                "query": f"{SYNTHETIC_SOURCE} enqueue rollback {context['token']}",
                "aiJobId": f"{SYNTHETIC_SOURCE}:rollback:{context['token']}",
                "ticker": f"R{context['token'][:7]}",
                "timeframe": "daily",
                "requestPayload": {"source": SYNTHETIC_SOURCE, "case": "enqueue-rollback"},
            }
            rollback_ids = _run_identifiers(owner_id, rollback_create_payload)
            identifiers.append(rollback_ids)
            rollback_run_id, _rollback_strategy_id, rollback_report_id = rollback_ids
            rollback_created = await client.post(
                "/api/v1/runs",
                cookies=owner_cookie,
                headers=owner_headers,
                json=rollback_create_payload,
            )
            assert rollback_created.status_code == 201
            context["app"].state.settings = context["settings"].model_copy(
                update={"email_public_base_url": None, "email_unsubscribe_enabled": False}
            )
            failed_completion = await client.post(
                f"/api/v1/runs/{rollback_run_id}/complete",
                cookies=owner_cookie,
                headers=owner_headers,
                json=_completion_payload(token=f"{context['token']}r"),
            )
            context["app"].state.settings = context["settings"]
            assert failed_completion.status_code == 503
            rollback_run = await _fetch_one(
                context["trading_engine"],
                "SELECT status, ended_at FROM app.backtest_run WHERE run_id = :run_id",
                {"run_id": rollback_run_id},
            )
            assert rollback_run == {"status": "queued", "ended_at": None}
            assert await _count(
                context["trading_engine"],
                "app.strategy_email_report",
                "report_id = :report_id",
                {"report_id": rollback_report_id},
            ) == 0
            assert await _count(
                context["trading_engine"],
                "app.email_delivery_history",
                "report_id = :report_id",
                {"report_id": rollback_report_id},
            ) == 0

            daily_subscription = await client.post(
                "/api/v1/me/email-strategy-subscriptions",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"strategyId": daily_disabled_ids[1]},
            )
            second_subscription = await client.post(
                "/api/v1/me/email-strategy-subscriptions",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"strategyId": second_ids[1]},
            )
            over_limit_subscription = await client.post(
                "/api/v1/me/email-strategy-subscriptions",
                cookies=owner_cookie,
                headers=owner_headers,
                json={"strategyId": rollback_ids[1]},
            )
            assert daily_subscription.status_code == second_subscription.status_code == 200
            assert second_subscription.json()["subscriptionCount"] == 3
            assert over_limit_subscription.status_code == 409

            for strategy_id, expected_count in (
                (first_strategy_id, 2),
                (daily_disabled_ids[1], 1),
                (second_ids[1], 0),
            ):
                deleted_subscription = await client.delete(
                    f"/api/v1/me/email-strategy-subscriptions/{strategy_id}",
                    cookies=owner_cookie,
                    headers=owner_headers,
                )
                assert deleted_subscription.status_code == 200
                assert deleted_subscription.json()["subscriptionCount"] == expected_count
    finally:
        if owner_session_id is not None:
            await context["store"].revoke_session(owner_session_id)
        if intruder_session_id is not None:
            await context["store"].revoke_session(intruder_session_id)
        cleanup_counts = await _cleanup(context, identifiers)
        assert cleanup_counts == {name: 0 for name in cleanup_counts}
        from app.db.session import dispose_db_engine

        await dispose_db_engine(context["auth_engine"])
        await dispose_db_engine(context["trading_engine"])
        print(
            "TRACK4_CONTROLLED_DML="
            + json.dumps(
                {
                    "source": SYNTHETIC_SOURCE,
                    "relations": list(TARGET_RELATIONS),
                    "syntheticRunCount": len(identifiers),
                    "cleanupCounts": cleanup_counts,
                },
                sort_keys=True,
            )
        )
