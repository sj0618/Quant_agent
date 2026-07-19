from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from pydantic import ValidationError

from app.core.config import Settings, redact_secrets, redact_url
from app.services.raw_audit_admission import issue_raw_audit_admission, issue_test_raw_audit_admission


def valid_settings(*, include_raw_audit: bool = True, **overrides):
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
        "AI_BACKTEST_RAW_AUDIT_ENABLED": True,
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_SECRET": "real-raw-audit-admission-hmac-secret",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_KEY_VERSION": "v1",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_TOKEN": "signed-gate-b-admission-token",
        "AI_BACKTEST_RAW_AUDIT_ADMISSION_AUDIENCE": "quantagent.backend.raw-audit",
        "AI_BACKTEST_RAW_AUDIT_EVIDENCE_ID": "gate-b-evidence-001",
        "AI_BACKTEST_RAW_AUDIT_DEPLOYMENT_REVISION": "revision-9",
    }
    if not include_raw_audit:
        for key in (
            "AI_BACKTEST_RAW_AUDIT_ENABLED",
            "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_SECRET",
            "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_KEY_VERSION",
            "AI_BACKTEST_RAW_AUDIT_ADMISSION_TOKEN",
            "AI_BACKTEST_RAW_AUDIT_ADMISSION_AUDIENCE",
            "AI_BACKTEST_RAW_AUDIT_EVIDENCE_ID",
            "AI_BACKTEST_RAW_AUDIT_DEPLOYMENT_REVISION",
        ):
            values.pop(key)
    values.update(overrides)
    return Settings(_env_file=None, **values)


def signed_raw_audit_admission_token() -> str:
    header = {"alg": "HS256", "key_version": "v1"}
    claims = {
        "audience": "quantagent.backend.raw-audit",
        "deployment_revision": "revision-9",
        "evidence_id": "gate-b-evidence-001",
        "expiry": time.time() + 300,
        "issued_at": time.time() - 1,
        "key_version": "v1",
    }
    encoded_header = base64.urlsafe_b64encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    encoded_claims = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    signing_input = f"{encoded_header}.{encoded_claims}"
    signature = hmac.new(
        b"real-raw-audit-admission-hmac-secret",
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


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


def test_raw_audit_defaults_disabled_without_signed_admission_settings():
    settings = valid_settings(include_raw_audit=False, APP_ENV="test")

    assert settings.ai_backtest_raw_audit_enabled is False
    assert issue_test_raw_audit_admission(settings) is None
def test_development_allows_a_valid_signed_raw_audit_admission():
    settings = valid_settings(
        APP_ENV="development",
        AI_BACKTEST_RAW_AUDIT_ADMISSION_TOKEN=signed_raw_audit_admission_token(),
    )

    assert issue_raw_audit_admission(settings) is not None


@pytest.mark.parametrize("app_env", ["production", "prod", "staging", "stage"])
def test_production_and_staging_aliases_hard_disable_signed_raw_audit_admission(app_env: str):
    settings = valid_settings(
        APP_ENV=app_env,
        AI_BACKTEST_RAW_AUDIT_ADMISSION_TOKEN=signed_raw_audit_admission_token(),
    )

    assert issue_raw_audit_admission(settings) is None


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
