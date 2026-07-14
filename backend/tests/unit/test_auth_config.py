from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, redact_secrets, redact_url


def valid_settings(**overrides):
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+asyncpg://real_user:real_secret@db.local:5432/quant_agent",
        "REDIS_URL": "redis://localhost:6379/0",
        "GOOGLE_CLIENT_ID": "google-client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "real-google-client-secret",
        "GOOGLE_REDIRECT_URI": "https://api.example.co.kr/auth/google/callback",
        "AUTH_PUBLIC_BACKEND_ORIGIN": "https://api.example.co.kr",
        "AUTH_ALLOWED_HOSTS": "api.example.co.kr",
        "AUTH_COOKIE_SECURE": True,
        "AUTH_COOKIE_SAMESITE": "lax",
        "AI_BACKTEST_SCOPE_HMAC_PRIMARY": "real-ai-backtest-scope-hmac-secret",
        "AI_BACKTEST_SCOPE_HMAC_PRIMARY_VERSION": "v1",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_SECRET": "real-raw-audit-admission-hmac-secret",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_KEY_VERSION": "v1",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_TOKEN": "signed-gate-b-admission-token",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_AUDIENCE": "quantagent.backend.raw-audit",
        "AI_BACKTEST_RAW_AUDIT_EVIDENCE_ID": "gate-b-evidence-001",
        "AI_BACKTEST_RAW_AUDIT_DEPLOYMENT_REVISION": "revision-9",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_production_auth_settings_are_accepted():
    settings = valid_settings()
    assert settings.auth_enabled is True
    assert settings.is_production is True
    assert settings.redis_url_value == "redis://localhost:6379/0"
    assert settings.sqlalchemy_database_url.startswith("postgresql+asyncpg://")
    assert settings.safe_summary()["google_client_id"] == "<configured>"
    assert settings.hankyung_consensus_crawler_enabled is False
    assert settings.hankyung_consensus_crawl_max_pages == 1
    assert settings.hankyung_consensus_crawl_max_reports <= 50
    assert settings.hankyung_consensus_api_base_url == "https://markets.hankyung.com"


@pytest.mark.parametrize(
    "missing_key",
    [
        "REDIS_URL",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_SECRET",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_KEY_VERSION",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_TOKEN",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_AUDIENCE",
        "AI_BACKTEST_RAW_AUDIT_EVIDENCE_ID",
        "AI_BACKTEST_RAW_AUDIT_DEPLOYMENT_REVISION",
    ],
)
def test_auth_enabled_runtime_rejects_missing_auth_critical_settings(missing_key: str):
    values = valid_settings().model_dump(by_alias=True)
    values.pop(missing_key)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_production_rejects_insecure_redirect_and_cookie():
    with pytest.raises(ValidationError):
        valid_settings(GOOGLE_REDIRECT_URI="http://api.example.co.kr/auth/google/callback")
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


def test_raw_audit_hmac_secret_must_not_reuse_the_oauth_secret():
    with pytest.raises(ValidationError):
        valid_settings(AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_SECRET="real-google-client-secret")



def test_secret_redaction_covers_urls_codes_and_tokens():
    assert redact_url("redis" + "://:secret@localhost:6379/0") == "redis://<redacted>"
    raw = "code=abc123 id_token=secret-token client_secret=real_secret " + "postgresql" + "://u:p@host/db"
    redacted = redact_secrets(raw)
    assert "abc123" not in redacted
    assert "secret-token" not in redacted
    assert "real_secret" not in redacted
    assert "u:p@host" not in redacted


def test_hankyung_crawler_auth_config_is_redacted_from_safe_summary():
    settings = valid_settings(
        HANKYUNG_CONSENSUS_API_BEARER_TOKEN="real-hankyung-bearer",
        HANKYUNG_CONSENSUS_AUTH_HEADER="X-Hankyung-Auth: real-hankyung-header",
    )

    summary = settings.safe_summary()

    assert summary["hankyung_consensus_api_bearer_token"] == "<configured>"
    assert summary["hankyung_consensus_auth_header"] == "<configured>"
    assert "real-hankyung" not in str(summary)


def test_hankyung_crawler_rejects_invalid_base_url_and_unbounded_limits():
    with pytest.raises(ValidationError):
        valid_settings(HANKYUNG_CONSENSUS_API_BASE_URL="ftp://markets.hankyung.com")
    with pytest.raises(ValidationError):
        valid_settings(HANKYUNG_CONSENSUS_API_BASE_URL="https://consensus.hankyung.com")
    with pytest.raises(ValidationError):
        valid_settings(HANKYUNG_CONSENSUS_CRAWL_MAX_PAGES=999)
    with pytest.raises(ValidationError):
        valid_settings(HANKYUNG_CONSENSUS_CRAWL_MAX_REPORTS=9999)
