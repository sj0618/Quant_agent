from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.core.config as config_module
from app.core.config import (
    ConfigurationError,
    Settings,
    redact_secrets,
    redact_url,
    sanitize_configuration_validation_details,
    validate_sender_mailbox,
)
from app.core.errors import configuration_error_observability_event, register_exception_handlers

WEBHOOK_SECRET = "whsec_dGVzdC13ZWJob29rLXNlY3JldA=="


def _invalid_configuration_errors(marker: str) -> list[dict[str, object]]:
    with pytest.raises(ValidationError) as rejected:
        server_email_settings(BREVO_SENDER_EMAIL=f"{marker} reports@qt-agent.kro.kr")
    return rejected.value.errors(include_url=False)


def valid_settings(**overrides):
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+asyncpg://db.local:5432/quant_agent",
        "REDIS_URL": "redis://localhost:6379/0",
        "GOOGLE_CLIENT_ID": "google-client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "real-google-client-secret",
        "GOOGLE_REDIRECT_URI": "https://api.example.co.kr/api/v1/auth/google/callback",
        "AI_BACKTEST_SCOPE_HMAC_PRIMARY": "backtest-scope-hmac-primary-v1",
        "AI_BACKTEST_SCOPE_HMAC_PRIMARY_VERSION": "v1",
        "AUTH_PUBLIC_BACKEND_ORIGIN": "https://api.example.co.kr",
        "AUTH_ALLOWED_HOSTS": "api.example.co.kr",
        "AUTH_COOKIE_SECURE": True,
        "AUTH_COOKIE_SAMESITE": "lax",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def server_email_settings(**overrides):
    values = {
        "DATABASE_URL": "postgresql+asyncpg://db.internal.example:5432/qt_db",
        "REDIS_URL": "rediss://cache.internal.example:6379/11",
        "EMAIL_ROLLOUT_MODE": "allowlist",
        "EMAIL_DELIVERY_ENABLED": True,
        "EMAIL_PROVIDER": "brevo",
        "BREVO_API_KEY": "synthetic-provider-key",
        "BREVO_SENDER_EMAIL": "reports@qt-agent.kro.kr",
        "BREVO_SANDBOX_MODE": False,
        "EMAIL_PUBLIC_BASE_URL": "https://app.qt-agent.kro.kr",
        "EMAIL_UNSUBSCRIBE_ENABLED": True,
        "EMAIL_UNSUBSCRIBE_SIGNING_SECRET": "synthetic-unsubscribe-secret",
        "EMAIL_UNSUBSCRIBE_BASE_URL": "https://app.qt-agent.kro.kr",
        "EMAIL_LOCAL_RECIPIENT_ALLOWLIST": "controlled@example.test",
    }
    values.update(overrides)
    return valid_settings(**values)


def test_authenticated_sender_mailbox_is_accepted_and_domain_is_normalized():
    assert (
        validate_sender_mailbox(
            "reports@QT-AGENT.KRO.KR",
            require_authenticated_domain=True,
        )
        == "reports@qt-agent.kro.kr"
    )


@pytest.mark.parametrize(
    "sender",
    [
        "report sender@qt-agent.kro.kr",
        " reports@qt-agent.kro.kr",
        "reports@qt-agent.kro.kr ",
        "reports@@qt-agent.kro.kr",
        "@qt-agent.kro.kr",
        "reports@",
        "reports@other.example",
        "reports..daily@qt-agent.kro.kr",
        ".reports@qt-agent.kro.kr",
        "reports.@qt-agent.kro.kr",
        "reports\x00@qt-agent.kro.kr",
        "QuantAgent <reports@qt-agent.kro.kr>",
        "reports@qt-agent.kro.kr\nBcc: synthetic@example.test",
    ],
)
def test_authenticated_sender_mailbox_rejects_unsafe_syntax_without_echo(sender: str):
    with pytest.raises(ValueError) as rejected:
        validate_sender_mailbox(sender, require_authenticated_domain=True)

    assert str(rejected.value) in {
        "email_sender_mailbox_invalid",
        "email_sender_domain_not_authenticated",
    }
    assert sender not in str(rejected.value)


@pytest.mark.parametrize(
    "sender",
    [
        "report sender@qt-agent.kro.kr",
        " reports@qt-agent.kro.kr",
        "reports@@qt-agent.kro.kr",
        "QuantAgent <reports@qt-agent.kro.kr>",
        "reports@qt-agent.kro.kr\r\nBcc: synthetic@example.test",
    ],
)
def test_server_rollout_rejects_invalid_sender_before_readiness(sender: str):
    with pytest.raises(ValidationError):
        server_email_settings(BREVO_SENDER_EMAIL=sender)


def test_configuration_validation_sanitizer_recursively_removes_rejected_values():
    marker = "track4i" + "-invalid-value-marker"
    details = {
        "errors": [
            {
                "loc": ("BREVO_SENDER_EMAIL", 0),
                "msg": f"Value error, {marker}",
                "type": "value_error",
                "input": marker,
                "ctx": {"error": ValueError(marker), "nested": (marker,)},
                "url": f"https://invalid.test/{marker}",
            }
        ],
        "input": marker,
        "raw": (marker,),
    }

    sanitized = sanitize_configuration_validation_details(details)
    serialized = json.dumps(sanitized, sort_keys=True)

    assert marker not in serialized
    assert sanitized["errors"][0] == {
        "location": ["BREVO_SENDER_EMAIL", 0],
        "category": "configuration_value",
        "reason": "invalid_setting_value",
    }


def test_category_shaped_raw_reason_never_becomes_a_safe_reason(caplog):
    marker = "category" + "_shaped_rejected_reason"
    raw_details = [
        {
            "loc": ("BREVO_SENDER_EMAIL",),
            "type": marker,
            "msg": marker,
            "input": marker,
            "ctx": {"error": ValueError(marker), marker: {"nested": marker}},
            "url": f"https://invalid.test/{marker}",
        }
    ]
    sanitized = sanitize_configuration_validation_details(raw_details)
    error = ConfigurationError(marker, raw_details)
    event = configuration_error_observability_event(error)
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/configuration-reason-probe")
    async def configuration_reason_probe():
        raise error

    with caplog.at_level("ERROR", logger="app.core.errors"):
        response = TestClient(app).get("/configuration-reason-probe")

    serialized_targets = (
        json.dumps(sanitized, sort_keys=True),
        json.dumps(error.details, sort_keys=True),
        str(error),
        response.text,
        caplog.text,
        json.dumps([record.__dict__ for record in caplog.records], default=str, sort_keys=True),
        json.dumps(event, sort_keys=True),
    )
    assert all(marker not in target for target in serialized_targets)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert sanitized == [
        {
            "location": ["BREVO_SENDER_EMAIL"],
            "category": "configuration_validation",
            "reason": "configuration_validation_failed",
        }
    ]


def test_invalid_sender_is_absent_from_configuration_error_api_logs_and_observability(caplog):
    marker = "track4i" + "-configuration-redaction-marker"
    error = ConfigurationError(
        "Invalid or missing backend configuration",
        _invalid_configuration_errors(marker),
    )
    event = configuration_error_observability_event(error)
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/configuration-probe")
    async def configuration_probe():
        raise error

    with caplog.at_level("ERROR", logger="app.core.errors"):
        response = TestClient(app).get("/configuration-probe")

    serialized_details = json.dumps(error.details, sort_keys=True)
    serialized_event = json.dumps(event, sort_keys=True)
    serialized_records = json.dumps([record.__dict__ for record in caplog.records], default=str, sort_keys=True)

    assert response.status_code == 503
    assert marker not in serialized_details
    assert marker not in response.text
    assert marker not in caplog.text
    assert marker not in serialized_records
    assert marker not in serialized_event
    assert response.json()["error"]["code"] == "invalid_config"
    assert any(
        location in {"BREVO_SENDER_EMAIL", "email_from_address"}
        for detail in error.details
        for location in detail["location"]
    )
    assert any(detail["reason"] == "email_sender_mailbox_invalid" for detail in error.details)


def test_load_settings_uses_the_same_sanitizer_without_retaining_validation_context(monkeypatch):
    marker = "track4i" + "-load-settings-redaction-marker"
    raw_errors = _invalid_configuration_errors(marker)

    with pytest.raises(ValidationError) as rejected:
        server_email_settings(BREVO_SENDER_EMAIL=f"{marker} reports@qt-agent.kro.kr")

    def invalid_settings():
        raise rejected.value

    monkeypatch.setattr(config_module, "Settings", invalid_settings)
    with pytest.raises(ConfigurationError) as sanitized:
        config_module.load_settings()

    serialized = json.dumps(sanitized.value.details, sort_keys=True)
    assert marker not in serialized
    assert sanitized.value.__cause__ is None
    assert sanitized.value.__context__ is None
    assert sanitized.value.__suppress_context__ is True
    assert sanitized.value.details == sanitize_configuration_validation_details(raw_errors)


def test_valid_production_auth_settings_are_accepted():
    settings = valid_settings()
    assert settings.auth_enabled is True
    assert settings.is_production is True
    assert settings.google_redirect_uri == "https://api.example.co.kr/api/v1/auth/google/callback"
    assert settings.redis_url_value == "redis://localhost:6379/0"
    assert settings.sqlalchemy_database_url.startswith("postgresql+asyncpg://")
    assert settings.safe_summary()["google_client_id"] == "<configured>"
    assert settings.hankyung_consensus_crawler_enabled is False
    assert settings.hankyung_consensus_crawl_max_pages == 1
    assert settings.hankyung_consensus_crawl_max_reports <= 50
    assert settings.hankyung_consensus_api_base_url == "https://markets.hankyung.com"
    assert settings.perf_diagnostics_enabled is False
    assert settings.email_report_completed_trigger_enabled is False
    assert settings.email_delivery_worker_enabled is False


@pytest.mark.parametrize(
    "missing_key",
    ["REDIS_URL", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"],
)
def test_auth_enabled_runtime_rejects_missing_auth_critical_settings(missing_key: str):
    values = valid_settings().model_dump(by_alias=True)
    values.pop(missing_key)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_production_rejects_insecure_redirect_and_cookie():
    with pytest.raises(ValidationError):
        valid_settings(GOOGLE_REDIRECT_URI="http://api.example.co.kr/api/v1/auth/google/callback")
    with pytest.raises(ValidationError):
        valid_settings(AUTH_COOKIE_SECURE=False)


def test_wildcard_credentialed_origin_is_rejected():
    with pytest.raises(ValidationError):
        valid_settings(AUTH_ALLOWED_ORIGINS="*")


def test_placeholder_values_are_rejected():
    with pytest.raises(ValidationError):
        valid_settings(**{"GOOGLE_CLIENT_SECRET": "<google-client-secret>"})
    with pytest.raises(ValidationError):
        valid_settings(DATABASE_URL="postgresql+asyncpg://<user>:<password>@<host>:5432/<database>")


def test_secret_redaction_covers_urls_codes_and_tokens():
    assert redact_url("redis" + "://localhost:6379/0") == "redis://<redacted>"
    raw = "code=abc123 id_token=secret-token client_secret=real_secret " + "postgresql" + "://host/db"
    redacted = redact_secrets(raw)
    assert "abc123" not in redacted
    assert "secret-token" not in redacted
    assert "real_secret" not in redacted
    assert "postgresql://<redacted>" in redacted


def test_hankyung_crawler_auth_config_is_redacted_from_safe_summary():
    settings = valid_settings(
        HANKYUNG_CONSENSUS_API_BEARER_TOKEN="real-hankyung-bearer",
        HANKYUNG_CONSENSUS_AUTH_HEADER="X-Hankyung-Auth: real-hankyung-header",
    )

    summary = settings.safe_summary()

    assert summary["hankyung_consensus_api_bearer_token"] == "<configured>"
    assert summary["hankyung_consensus_auth_header"] == "<configured>"
    assert "real-hankyung" not in str(summary)


def test_trading_data_database_url_is_optional_and_redacted():
    settings = valid_settings(
        TRADING_DATA_DATABASE_URL="postgresql://trading-db.local:5432/trading_data",
    )

    summary = settings.safe_summary()

    assert settings.trading_data_database_url_value == "postgresql://trading-db.local:5432/trading_data"
    assert settings.trading_data_sqlalchemy_database_url == "postgresql+asyncpg://trading-db.local:5432/trading_data"
    assert summary["trading_data_database_url"] == "postgresql://<redacted>"
    assert "trading-db.local:5432/trading_data" not in str(summary)


def test_email_delivery_config_is_redacted_from_safe_summary():
    settings = valid_settings(
        APP_ENV="local",
        EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED=True,
        EMAIL_DELIVERY_ENABLED=True,
        EMAIL_PROVIDER="resend",
        EMAIL_FROM_ADDRESS="alerts@quantagent.co.kr",
        EMAIL_FROM_NAME="QuantAgent",
        EMAIL_API_KEY="resend-secret-key",
        EMAIL_PUBLIC_BASE_URL="https://reports.quantagent.co.kr",
        EMAIL_LOCAL_RECIPIENT_ALLOWLIST="alerts@quantagent.co.kr",
        EMAIL_LOCAL_LIVE_SEND_ENABLED=True,
        EMAIL_DELIVERY_WORKER_ENABLED=True,
    )

    summary = settings.safe_summary()

    assert summary["email_delivery_enabled"] is True
    assert summary["email_report_completed_trigger_enabled"] is True
    assert summary["email_delivery_worker_enabled"] is True
    assert summary["email_provider"] == "resend"
    assert summary["email_from_address"] == "<configured>"
    assert summary["email_sender_domain"] == "other"
    assert summary["email_from_name"] == "QuantAgent"
    assert summary["email_api_key"] == "<configured>"
    assert summary["email_public_base_url"] == "https://reports.quantagent.co.kr"
    assert summary["email_local_live_send_enabled"] is True
    assert summary["email_allow_local_live_send"] is True
    assert summary["email_rollout_mode"] == "allowlist"
    assert summary["email_rollout_mode_source"] == "legacy_local_canary"
    assert summary["email_local_recipient_allowlist_count"] == 1
    assert "alerts@quantagent.co.kr" not in str(summary)
    assert "resend-secret-key" not in str(summary)


def test_email_server_rollout_defaults_disabled_and_accepts_strict_allowlist_contract():
    assert valid_settings().email_effective_rollout_mode == "disabled"

    settings = server_email_settings()
    summary = settings.safe_summary()

    assert settings.email_effective_rollout_mode == "allowlist"
    assert settings.email_uses_legacy_local_canary is False
    assert summary["email_sender_domain"] == "qt-agent.kro.kr"
    assert summary["email_local_recipient_allowlist_count"] == 1
    assert "controlled@example.test" not in str(summary)
    assert "reports@qt-agent.kro.kr" not in str(summary)


@pytest.mark.parametrize(
    "overrides",
    [
        {"EMAIL_ROLLOUT_MODE": "invalid"},
        {"EMAIL_LOCAL_RECIPIENT_ALLOWLIST": ""},
        {"BREVO_API_KEY": None},
        {"BREVO_SENDER_EMAIL": "sender@other.example"},
        {"EMAIL_PUBLIC_BASE_URL": "http://app.qt-agent.kro.kr"},
        {"EMAIL_PUBLIC_BASE_URL": "https://localhost"},
        {"DATABASE_URL": "postgresql+asyncpg://localhost:5432/qt_db"},
        {"DATABASE_URL": "postgresql+asyncpg://db.internal.example:5432/other_db"},
        {"REDIS_URL": "redis://localhost:6379/11"},
        {"REDIS_URL": "rediss://cache.internal.example:6379/0"},
        {"EMAIL_UNSUBSCRIBE_BASE_URL": "http://app.qt-agent.kro.kr"},
    ],
)
def test_email_server_rollout_rejects_incomplete_or_local_configuration(overrides):
    with pytest.raises(ValidationError):
        server_email_settings(**overrides)


def test_email_production_rollout_does_not_use_allowlist_and_rejects_sandbox():
    settings = server_email_settings(EMAIL_ROLLOUT_MODE="production", EMAIL_LOCAL_RECIPIENT_ALLOWLIST="")
    assert settings.email_effective_rollout_mode == "production"

    with pytest.raises(ValidationError):
        server_email_settings(EMAIL_ROLLOUT_MODE="production", BREVO_SANDBOX_MODE=True)


def test_legacy_local_canary_requires_nonempty_allowlist():
    with pytest.raises(ValidationError):
        valid_settings(EMAIL_LOCAL_LIVE_SEND_ENABLED=True)
    with pytest.raises(ValidationError):
        valid_settings(
            EMAIL_ROLLOUT_MODE="disabled",
            EMAIL_LOCAL_LIVE_SEND_ENABLED=True,
            EMAIL_LOCAL_RECIPIENT_ALLOWLIST="controlled@example.test",
        )


def test_email_resend_webhook_config_is_redacted_from_safe_summary():
    settings = valid_settings(
        EMAIL_RESEND_WEBHOOK_ENABLED=True,
        EMAIL_RESEND_WEBHOOK_SECRET=WEBHOOK_SECRET,
        EMAIL_RESEND_WEBHOOK_TOLERANCE_SECONDS=120,
        EMAIL_RESEND_WEBHOOK_MAX_BODY_BYTES=8192,
        EMAIL_RESEND_WEBHOOK_EVENT_RETENTION_DAYS=14,
    )

    summary = settings.safe_summary()

    assert summary["email_resend_webhook_enabled"] is True
    assert summary["email_resend_webhook_secret"] == "<configured>"
    assert summary["email_resend_webhook_tolerance_seconds"] == 120
    assert summary["email_resend_webhook_max_body_bytes"] == 8192
    assert summary["email_resend_webhook_event_retention_days"] == 14
    assert WEBHOOK_SECRET not in str(summary)


def test_email_unsubscribe_config_is_redacted_from_safe_summary():
    settings = valid_settings(
        APP_ENV="local",
        EMAIL_UNSUBSCRIBE_ENABLED=True,
        EMAIL_UNSUBSCRIBE_SIGNING_SECRET="unsubscribe-secret",
        EMAIL_UNSUBSCRIBE_BASE_URL="https://fe.example.co.kr",
        EMAIL_UNSUBSCRIBE_TOKEN_TTL_SECONDS=3600,
    )

    summary = settings.safe_summary()

    assert summary["email_unsubscribe_enabled"] is True
    assert summary["email_unsubscribe_signing_secret"] == "<configured>"
    assert summary["email_unsubscribe_base_url"] == "https://fe.example.co.kr"
    assert summary["email_unsubscribe_token_ttl_seconds"] == 3600
    assert "unsubscribe-secret" not in str(summary)


def test_email_resend_webhook_requires_secret_when_enabled():
    with pytest.raises(ValidationError):
        valid_settings(EMAIL_RESEND_WEBHOOK_ENABLED=True)


def test_email_unsubscribe_requires_secret_and_base_url_when_enabled():
    with pytest.raises(ValidationError):
        valid_settings(EMAIL_UNSUBSCRIBE_ENABLED=True)
    with pytest.raises(ValidationError):
        valid_settings(
            EMAIL_UNSUBSCRIBE_ENABLED=True,
            EMAIL_UNSUBSCRIBE_SIGNING_SECRET="unsubscribe-secret",
        )


def test_email_unsubscribe_rejects_insecure_production_base_url():
    with pytest.raises(ValidationError):
        valid_settings(
            EMAIL_UNSUBSCRIBE_ENABLED=True,
            EMAIL_UNSUBSCRIBE_SIGNING_SECRET="unsubscribe-secret",
            EMAIL_UNSUBSCRIBE_BASE_URL="http://fe.example.co.kr",
        )


def test_email_worker_requires_delivery_enabled():
    with pytest.raises(ValidationError):
        valid_settings(EMAIL_DELIVERY_WORKER_ENABLED=True)


def test_hankyung_crawler_rejects_invalid_base_url_and_unbounded_limits():
    with pytest.raises(ValidationError):
        valid_settings(HANKYUNG_CONSENSUS_API_BASE_URL="ftp://markets.hankyung.com")
    with pytest.raises(ValidationError):
        valid_settings(HANKYUNG_CONSENSUS_API_BASE_URL="https://consensus.hankyung.com")
    with pytest.raises(ValidationError):
        valid_settings(HANKYUNG_CONSENSUS_CRAWL_MAX_PAGES=999)
    with pytest.raises(ValidationError):
        valid_settings(HANKYUNG_CONSENSUS_CRAWL_MAX_REPORTS=9999)

@pytest.mark.parametrize("value", [True, "true", "1", "yes", "on"])
def test_perf_diagnostics_accepts_explicit_true_values(value):
    assert valid_settings(PERF_DIAGNOSTICS_ENABLED=value).perf_diagnostics_enabled is True


@pytest.mark.parametrize("value", [False, "false", "0", "no", "off"])
def test_perf_diagnostics_accepts_explicit_false_values(value):
    assert valid_settings(PERF_DIAGNOSTICS_ENABLED=value).perf_diagnostics_enabled is False


def test_perf_diagnostics_rejects_ambiguous_values():
    with pytest.raises(ValidationError):
        valid_settings(PERF_DIAGNOSTICS_ENABLED="sometimes")
