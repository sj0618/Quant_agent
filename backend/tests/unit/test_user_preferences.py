from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.db import user_preferences


class FakeEngine:
    pass


@pytest.mark.asyncio
async def test_get_notification_settings_reads_canonical_users_table_and_defaults_when_missing(monkeypatch):
    recorded: dict[str, object] = {}

    async def fake_fetch_one(engine, sql, params=None):
        recorded["engine"] = engine
        recorded["sql"] = sql
        recorded["params"] = params or {}
        return None

    monkeypatch.setattr(user_preferences, "fetch_one", fake_fetch_one)

    result = await user_preferences.get_notification_settings(
        FakeEngine(),
        user_id=" 42 ",
        email="owner@example.com",
    )

    assert recorded["engine"] is not None
    assert "FROM app.users" in str(recorded["sql"])
    assert recorded["params"]["user_id"] == 42
    assert result == {
        "dailyReportEmail": True,
        "actionEmails": True,
        "marketingEmail": False,
        "deliveryHour": "08:00",
        "email": "owner@example.com",
    }


@pytest.mark.asyncio
async def test_save_notification_settings_updates_canonical_users_table_and_preserves_partial_fields(monkeypatch):
    recorded: dict[str, object] = {}
    row = {
        "email": "owner@example.com",
        "daily_report_email": True,
        "action_emails": True,
        "marketing_email": False,
        "delivery_hour": "08:00",
        "created_at": "2026-07-20T00:00:00Z",
        "updated_at": "2026-07-20T00:00:00Z",
    }

    async def fake_execute_one(engine, sql, params=None):
        recorded["engine"] = engine
        recorded["sql"] = sql
        recorded["params"] = params or {}
        row["email"] = params["email"]
        row["daily_report_email"] = row["daily_report_email"] if params["daily_report_email"] is None else params["daily_report_email"]
        row["action_emails"] = row["action_emails"] if params["action_emails"] is None else params["action_emails"]
        row["marketing_email"] = row["marketing_email"] if params["marketing_email"] is None else params["marketing_email"]
        row["delivery_hour"] = row["delivery_hour"] if params["delivery_hour"] is None else params["delivery_hour"]
        return dict(row)

    monkeypatch.setattr(user_preferences, "execute_one", fake_execute_one)

    result = await user_preferences.save_notification_settings(
        FakeEngine(),
        user_id="42",
        email="new-owner@example.com",
        daily_report_email=None,
        action_emails=False,
        marketing_email=None,
        delivery_hour="09:30",
    )

    assert recorded["engine"] is not None
    assert "UPDATE app.users" in str(recorded["sql"])
    assert "COALESCE(:daily_report_email, app.users.daily_report_email)" in str(recorded["sql"])
    assert recorded["params"] == {
        "user_id": 42,
        "email": "new-owner@example.com",
        "daily_report_email": None,
        "action_emails": False,
        "marketing_email": None,
        "delivery_hour": "09:30",
    }
    assert result == {
        "dailyReportEmail": True,
        "actionEmails": False,
        "marketingEmail": False,
        "deliveryHour": "09:30",
        "email": "new-owner@example.com",
    }


@pytest.mark.asyncio
async def test_save_notification_settings_rejects_invalid_email(monkeypatch):
    called = False

    async def fake_execute_one(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("execute_one must not be called when email validation fails")

    monkeypatch.setattr(user_preferences, "execute_one", fake_execute_one)

    with pytest.raises(AppError) as exc:
        await user_preferences.save_notification_settings(
            FakeEngine(),
            user_id="42",
            email="invalid-email",
            daily_report_email=True,
        )

    assert exc.value.status_code == 422
    assert called is False
