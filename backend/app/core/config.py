from __future__ import annotations

import hmac
import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_MARKERS = (
    "<",
    ">",
    "changeme",
    "change_me",
    "placeholder",
    "example.com",
    "your-",
    "insert-",
)
_PRODUCTION_ENVS = {"prod", "production"}
_ALLOWED_SAMESITE = {"lax", "strict", "none"}
_ALLOWED_PDF_TEMP_PERSISTENCE = {"db", "manifest"}
_ALLOWED_EMAIL_ROLLOUT_MODES = {"disabled", "allowlist", "production"}
_EXPECTED_EMAIL_SENDER_DOMAIN = "qt-agent.kro.kr"
_EMAIL_LOCAL_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_EMAIL_LOCAL_PART_PATTERN = re.compile(rf"^{_EMAIL_LOCAL_ATOM}(?:\.{_EMAIL_LOCAL_ATOM})*$")
_EMAIL_DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_VALIDATION_LOCATION_PATTERN = re.compile(r"^[A-Za-z0-9_.\-\[\]]{1,96}$")
_VALIDATION_VALUE_KEYS = {
    "ctx",
    "exception",
    "input",
    "message",
    "msg",
    "raw",
    "url",
    "value",
}
_DEFAULT_VALIDATION_CLASSIFICATION = ("configuration_validation", "configuration_validation_failed")
_VALIDATION_CLASSIFICATION_BY_TYPE = {
    "bool_parsing": ("configuration_type", "invalid_setting_type"),
    "bool_type": ("configuration_type", "invalid_setting_type"),
    "email_sender_domain_not_authenticated": (
        "configuration_value",
        "email_sender_domain_not_authenticated",
    ),
    "email_sender_mailbox_invalid": ("configuration_value", "email_sender_mailbox_invalid"),
    "email_sender_mailbox_missing": ("configuration_missing", "email_sender_mailbox_missing"),
    "extra_forbidden": ("configuration_structure", "unexpected_setting"),
    "greater_than_equal": ("configuration_constraint", "setting_constraint_failed"),
    "int_parsing": ("configuration_type", "invalid_setting_type"),
    "int_type": ("configuration_type", "invalid_setting_type"),
    "less_than_equal": ("configuration_constraint", "setting_constraint_failed"),
    "literal_error": ("configuration_value", "invalid_setting_value"),
    "missing": ("configuration_missing", "required_setting_missing"),
    "model_type": ("configuration_type", "invalid_setting_type"),
    "server_email_sender_invalid": ("configuration_value", "email_sender_mailbox_invalid"),
    "string_too_long": ("configuration_constraint", "setting_constraint_failed"),
    "string_too_short": ("configuration_constraint", "setting_constraint_failed"),
    "string_type": ("configuration_type", "invalid_setting_type"),
    "url_parsing": ("configuration_value", "invalid_setting_url"),
    "url_scheme": ("configuration_value", "invalid_setting_url"),
    "value_error": ("configuration_value", "invalid_setting_value"),
}
_TRUSTED_VALIDATION_CLASSIFICATIONS = set(_VALIDATION_CLASSIFICATION_BY_TYPE.values()) | {
    _DEFAULT_VALIDATION_CLASSIFICATION
}
_SAFE_CONFIGURATION_ERROR_MESSAGES = {
    "Invalid or missing backend configuration",
    "Redis readiness check failed",
}
_MAX_HANKYUNG_CRAWL_PAGES = 10
_MAX_HANKYUNG_CRAWL_REPORTS = 200


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_local_runtime_host(hostname: str | None) -> bool:
    normalized = str(hostname or "").strip().lower().rstrip(".")
    if (
        not normalized
        or normalized == "localhost"
        or normalized.endswith(".localhost")
        or normalized.endswith(".local")
    ):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_server_public_url(value: str | None, *, name: str) -> None:
    parsed = urlsplit(value or "")
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute https URL for server email rollout")
    if parsed.username or parsed.password or _is_local_runtime_host(parsed.hostname):
        raise ValueError(f"{name} must use a non-local public host for server email rollout")


def _sender_domain(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if "@" not in normalized:
        return None
    return normalized.rsplit("@", 1)[1] or None


def validate_sender_mailbox(value: str | None, *, require_authenticated_domain: bool) -> str:
    if value is None or value == "":
        raise PydanticCustomError("email_sender_mailbox_missing", "email_sender_mailbox_missing")
    has_unsafe_character = any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    )
    if value != value.strip() or has_unsafe_character:
        raise PydanticCustomError("email_sender_mailbox_invalid", "email_sender_mailbox_invalid")
    if value.count("@") != 1 or "<" in value or ">" in value:
        raise PydanticCustomError("email_sender_mailbox_invalid", "email_sender_mailbox_invalid")

    local_part, domain = value.split("@", 1)
    if (
        not local_part
        or not domain
        or len(local_part) > 64
        or len(value) > 254
        or _EMAIL_LOCAL_PART_PATTERN.fullmatch(local_part) is None
        or _EMAIL_DOMAIN_PATTERN.fullmatch(domain) is None
    ):
        raise PydanticCustomError("email_sender_mailbox_invalid", "email_sender_mailbox_invalid")

    normalized_domain = domain.lower()
    if require_authenticated_domain and normalized_domain != _EXPECTED_EMAIL_SENDER_DOMAIN:
        raise PydanticCustomError(
            "email_sender_domain_not_authenticated",
            "email_sender_domain_not_authenticated",
        )
    return f"{local_part}@{normalized_domain}"


class Settings(BaseSettings):
    """Runtime configuration for the backend-owned production auth surface.

    Auth is enabled by default because this project pass is explicitly production
    Google login. Missing auth-critical settings are configuration errors, not
    reasons to fall back to mock or in-memory auth.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    perf_diagnostics_enabled: bool = Field(default=False, alias="PERF_DIAGNOSTICS_ENABLED")
    database_url: SecretStr = Field(..., alias="DATABASE_URL")
    trading_data_database_url: SecretStr | None = Field(
        default=None,
        alias="TRADING_DATA_DATABASE_URL",
        validation_alias=AliasChoices(
            "TRADING_DATA_DATABASE_URL",
            "INSTRUMENT_DATABASE_URL",
            "TRADING_CANDIDATE_DATABASE_URL",
        ),
    )
    redis_url: SecretStr | None = Field(default=None, alias="REDIS_URL")

    auth_enabled: bool = Field(default=True, alias="AUTH_ENABLED")
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: SecretStr | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str | None = Field(default=None, alias="GOOGLE_REDIRECT_URI")

    auth_public_backend_origin: str | None = Field(default=None, alias="AUTH_PUBLIC_BACKEND_ORIGIN")
    auth_allowed_hosts: str = Field(default="localhost,127.0.0.1", alias="AUTH_ALLOWED_HOSTS")
    auth_allowed_origins: str = Field(default="", alias="AUTH_ALLOWED_ORIGINS")
    auth_trusted_proxy_headers: bool = Field(default=False, alias="AUTH_TRUSTED_PROXY_HEADERS")

    auth_session_cookie_name: str = Field(default="qa_session", alias="AUTH_SESSION_COOKIE_NAME")
    auth_cookie_secure: bool = Field(default=True, alias="AUTH_COOKIE_SECURE")
    auth_cookie_samesite: str = Field(default="lax", alias="AUTH_COOKIE_SAMESITE")
    auth_cookie_domain: str | None = Field(default=None, alias="AUTH_COOKIE_DOMAIN")
    auth_cookie_path: str = Field(default="/", alias="AUTH_COOKIE_PATH")

    auth_state_ttl_seconds: int = Field(default=600, alias="AUTH_STATE_TTL_SECONDS", ge=60, le=3600)
    auth_session_idle_ttl_seconds: int = Field(
        default=60 * 30,
        alias="AUTH_SESSION_IDLE_TTL_SECONDS",
        ge=60,
    )

    auth_session_absolute_ttl_seconds: int = Field(
        default=60 * 60 * 8,
        alias="AUTH_SESSION_ABSOLUTE_TTL_SECONDS",
        ge=300,
    )

    auth_session_touch_interval_seconds: int = Field(
        default=60,
        alias="AUTH_SESSION_TOUCH_INTERVAL_SECONDS",
        ge=1,
    )
    auth_csrf_ttl_seconds: int = Field(default=3600, alias="AUTH_CSRF_TTL_SECONDS", ge=300)
    auth_csrf_required: bool = Field(default=False, alias="AUTH_CSRF_REQUIRED")

    email_delivery_enabled: bool = Field(default=False, alias="EMAIL_DELIVERY_ENABLED")
    email_report_completed_trigger_enabled: bool = Field(default=False, alias="EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED")
    email_delivery_worker_enabled: bool = Field(default=False, alias="EMAIL_DELIVERY_WORKER_ENABLED")
    email_rollout_mode: str = Field(default="disabled", alias="EMAIL_ROLLOUT_MODE")
    email_provider: str = Field(default="brevo", alias="EMAIL_PROVIDER")
    email_from_address: str | None = Field(
        default=None,
        alias="BREVO_SENDER_EMAIL",
        validation_alias=AliasChoices("BREVO_SENDER_EMAIL", "EMAIL_FROM_ADDRESS"),
    )
    email_from_name: str = Field(
        default="QuantAgent",
        alias="BREVO_SENDER_NAME",
        validation_alias=AliasChoices("BREVO_SENDER_NAME", "EMAIL_FROM_NAME"),
    )
    email_api_key: SecretStr | None = Field(
        default=None,
        alias="BREVO_API_KEY",
        validation_alias=AliasChoices("BREVO_API_KEY", "EMAIL_API_KEY"),
    )
    email_brevo_api_base_url: str = Field(default="https://api.brevo.com", alias="BREVO_API_BASE_URL")
    email_brevo_sandbox_mode: bool = Field(default=False, alias="BREVO_SANDBOX_MODE")
    email_brevo_webhook_enabled: bool = Field(default=False, alias="BREVO_WEBHOOK_ENABLED")
    email_brevo_webhook_bearer_token: SecretStr | None = Field(
        default=None,
        alias="BREVO_WEBHOOK_BEARER_TOKEN",
    )
    email_brevo_webhook_tolerance_seconds: int = Field(
        default=300,
        alias="BREVO_WEBHOOK_TOLERANCE_SECONDS",
        ge=1,
    )
    email_brevo_webhook_max_body_bytes: int = Field(
        default=256 * 1024,
        alias="BREVO_WEBHOOK_MAX_BODY_BYTES",
        ge=1,
    )
    email_brevo_webhook_event_retention_days: int = Field(
        default=30,
        alias="BREVO_WEBHOOK_EVENT_RETENTION_DAYS",
        ge=1,
    )
    email_public_base_url: str | None = Field(default=None, alias="EMAIL_PUBLIC_BASE_URL")
    email_unsubscribe_enabled: bool = Field(default=False, alias="EMAIL_UNSUBSCRIBE_ENABLED")
    email_unsubscribe_signing_secret: SecretStr | None = Field(default=None, alias="EMAIL_UNSUBSCRIBE_SIGNING_SECRET")
    email_unsubscribe_token_ttl_seconds: int = Field(
        default=60 * 60 * 24 * 30,
        alias="EMAIL_UNSUBSCRIBE_TOKEN_TTL_SECONDS",
        ge=60,
    )
    email_unsubscribe_base_url: str | None = Field(default=None, alias="EMAIL_UNSUBSCRIBE_BASE_URL")
    email_max_attempts: int = Field(default=5, alias="EMAIL_MAX_ATTEMPTS", ge=1)
    email_retry_base_seconds: int = Field(default=30, alias="EMAIL_RETRY_BASE_SECONDS", ge=1)
    email_claim_ttl_seconds: int = Field(default=300, alias="EMAIL_CLAIM_TTL_SECONDS", ge=1)
    email_request_timeout_seconds: float = Field(default=10.0, alias="EMAIL_REQUEST_TIMEOUT_SECONDS", gt=0)
    email_resend_webhook_enabled: bool = Field(default=False, alias="EMAIL_RESEND_WEBHOOK_ENABLED")
    email_resend_webhook_secret: SecretStr | None = Field(default=None, alias="EMAIL_RESEND_WEBHOOK_SECRET")
    email_resend_webhook_tolerance_seconds: int = Field(
        default=300,
        alias="EMAIL_RESEND_WEBHOOK_TOLERANCE_SECONDS",
        ge=1,
    )
    email_resend_webhook_max_body_bytes: int = Field(
        default=256 * 1024,
        alias="EMAIL_RESEND_WEBHOOK_MAX_BODY_BYTES",
        ge=1,
    )
    email_resend_webhook_event_retention_days: int = Field(
        default=30,
        alias="EMAIL_RESEND_WEBHOOK_EVENT_RETENTION_DAYS",
        ge=1,
    )
    email_local_recipient_allowlist: str = Field(
        default="",
        alias="EMAIL_LOCAL_RECIPIENT_ALLOWLIST",
        validation_alias=AliasChoices("EMAIL_LOCAL_RECIPIENT_ALLOWLIST", "EMAIL_DEV_RECIPIENT_ALLOWLIST"),
    )
    email_local_live_send_enabled: bool = Field(
        default=False,
        alias="EMAIL_LOCAL_LIVE_SEND_ENABLED",
        validation_alias=AliasChoices("EMAIL_LOCAL_LIVE_SEND_ENABLED", "EMAIL_ALLOW_LOCAL_LIVE_SEND"),
    )
    email_worker_id: str | None = Field(default=None, alias="EMAIL_WORKER_ID")
    email_worker_poll_interval_seconds: float = Field(
        default=5.0,
        alias="EMAIL_WORKER_POLL_INTERVAL_SECONDS",
        gt=0,
    )
    email_worker_claim_lease_seconds: int = Field(default=300, alias="EMAIL_WORKER_CLAIM_LEASE_SECONDS", ge=1)
    email_worker_batch_size: int = Field(default=10, alias="EMAIL_WORKER_BATCH_SIZE", ge=1)
    email_worker_shutdown_grace_seconds: int = Field(default=30, alias="EMAIL_WORKER_SHUTDOWN_GRACE_SECONDS", ge=1)
    email_digest_scheduler_batch_size: int = Field(default=100, alias="EMAIL_DIGEST_SCHEDULER_BATCH_SIZE", ge=1)
    email_digest_generation_concurrency: int = Field(default=4, alias="EMAIL_DIGEST_GENERATION_CONCURRENCY", ge=1)

    pdf_temp_ingest_enabled: bool = Field(default=False, alias="PDF_TEMP_INGEST_ENABLED")
    pdf_temp_storage_dir: str = Field(default="var/pdf-temp/storage", alias="PDF_TEMP_STORAGE_DIR")
    pdf_temp_seed_dir: str = Field(default="var/pdf-temp/seeds", alias="PDF_TEMP_SEED_DIR")
    pdf_temp_manifest_path: str = Field(default="var/pdf-temp/manifest.json", alias="PDF_TEMP_MANIFEST_PATH")
    pdf_temp_persistence: str = Field(default="db", alias="PDF_TEMP_PERSISTENCE")
    pdf_temp_seed_registry_json: str = Field(default="[]", alias="PDF_TEMP_SEED_REGISTRY_JSON")
    pdf_temp_max_bytes: int = Field(default=20 * 1024 * 1024, alias="PDF_TEMP_MAX_BYTES", ge=1024)
    pdf_temp_url_allowed_hosts: str = Field(default="", alias="PDF_TEMP_URL_ALLOWED_HOSTS")
    pdf_temp_http_user_agent: str = Field(
        default="Mozilla/5.0 (compatible; QuantAgentPDFTemp/0.1)",
        alias="PDF_TEMP_HTTP_USER_AGENT",
    )
    pdf_temp_url_timeout_seconds: float = Field(default=10.0, alias="PDF_TEMP_URL_TIMEOUT_SECONDS", gt=0)
    pdf_temp_url_max_redirects: int = Field(default=3, alias="PDF_TEMP_URL_MAX_REDIRECTS", ge=0, le=10)
    pdf_temp_min_text_chars: int = Field(default=20, alias="PDF_TEMP_MIN_TEXT_CHARS", ge=0)
    pdf_temp_max_seed_batch_size: int = Field(default=3, alias="PDF_TEMP_MAX_SEED_BATCH_SIZE", ge=1, le=10)

    ai_backtest_scope_hmac_primary: SecretStr | None = Field(
        default=None,
        alias="AI_BACKTEST_SCOPE_HMAC_PRIMARY",
    )
    ai_backtest_scope_hmac_primary_version: str | None = Field(
        default=None,
        alias="AI_BACKTEST_SCOPE_HMAC_PRIMARY_VERSION",
        min_length=1,
    )
    ai_backtest_scope_hmac_previous: SecretStr | None = Field(
        default=None,
        alias="AI_BACKTEST_SCOPE_HMAC_PREVIOUS",
    )
    ai_backtest_scope_hmac_previous_version: str | None = Field(
        default=None,
        alias="AI_BACKTEST_SCOPE_HMAC_PREVIOUS_VERSION",
        min_length=1,
    )
    # Allowance stamped onto every newly issued API token. Not caller-supplied: the point
    # of the quota is to bound abuse, which a self-chosen limit would not do. Raising one
    # account's ceiling is an operator action against the row, not a self-serve setting.
    ai_account_token_default_quota_limit: int = Field(
        default=60,
        alias="AI_ACCOUNT_TOKEN_DEFAULT_QUOTA_LIMIT",
        ge=1,
    )
    ai_account_token_default_quota_window_seconds: int = Field(
        default=3600,
        alias="AI_ACCOUNT_TOKEN_DEFAULT_QUOTA_WINDOW_SECONDS",
        ge=1,
    )
    ai_backtest_raw_audit_enabled: bool = Field(default=False, alias="AI_BACKTEST_RAW_AUDIT_ENABLED")
    ai_backtest_raw_audit_admission_hmac_secret: SecretStr | None = Field(
        default=None,
        alias="AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_SECRET",
    )
    ai_backtest_raw_audit_admission_hmac_key_version: str | None = Field(
        default=None,
        alias="AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_KEY_VERSION",
        min_length=1,
    )
    ai_backtest_raw_audit_admission_token: SecretStr | None = Field(
        default=None,
        alias="AI_BACKTEST_RAW_AUDIT_ADMISSION_TOKEN",
    )
    ai_backtest_raw_audit_admission_audience: str | None = Field(
        default=None,
        alias="AI_BACKTEST_RAW_AUDIT_ADMISSION_AUDIENCE",
        min_length=1,
    )
    ai_backtest_raw_audit_evidence_id: str | None = Field(
        default=None,
        alias="AI_BACKTEST_RAW_AUDIT_EVIDENCE_ID",
        min_length=1,
    )
    ai_backtest_raw_audit_deployment_revision: str | None = Field(
        default=None,
        alias="AI_BACKTEST_RAW_AUDIT_DEPLOYMENT_REVISION",
        min_length=1,
    )

    hankyung_consensus_crawler_enabled: bool = Field(default=False, alias="HANKYUNG_CONSENSUS_CRAWLER_ENABLED")
    hankyung_consensus_api_base_url: str = Field(
        default="https://markets.hankyung.com",
        alias="HANKYUNG_CONSENSUS_API_BASE_URL",
    )
    hankyung_consensus_api_bearer_token: SecretStr | None = Field(
        default=None,
        alias="HANKYUNG_CONSENSUS_API_BEARER_TOKEN",
    )
    hankyung_consensus_auth_header: SecretStr | None = Field(
        default=None,
        alias="HANKYUNG_CONSENSUS_AUTH_HEADER",
    )
    hankyung_consensus_crawl_max_pages: int = Field(
        default=1,
        alias="HANKYUNG_CONSENSUS_CRAWL_MAX_PAGES",
        ge=1,
        le=_MAX_HANKYUNG_CRAWL_PAGES,
    )
    hankyung_consensus_crawl_max_reports: int = Field(
        default=50,
        alias="HANKYUNG_CONSENSUS_CRAWL_MAX_REPORTS",
        ge=1,
        le=_MAX_HANKYUNG_CRAWL_REPORTS,
    )
    hankyung_consensus_crawl_timeout_seconds: float = Field(
        default=10.0,
        alias="HANKYUNG_CONSENSUS_CRAWL_TIMEOUT_SECONDS",
        gt=0,
        le=60,
    )
    hankyung_consensus_crawl_user_agent: str = Field(
        default="Mozilla/5.0 (compatible; QuantAgentHankyungConsensusCrawler/0.1)",
        alias="HANKYUNG_CONSENSUS_CRAWL_USER_AGENT",
    )

    @field_validator(
        "database_url",
        "trading_data_database_url",
        "redis_url",
        "google_client_secret",
        "ai_backtest_scope_hmac_primary",
        "ai_backtest_scope_hmac_previous",
        "ai_backtest_raw_audit_admission_hmac_secret",
        "ai_backtest_raw_audit_admission_token",
        "hankyung_consensus_api_bearer_token",
        "hankyung_consensus_auth_header",
        "email_api_key",
        "email_brevo_webhook_bearer_token",
        "email_unsubscribe_signing_secret",
        mode="before",
    )
    @classmethod
    def reject_placeholder_secrets(cls, value: Any) -> Any:
        if value is None:
            return None
        raw = str(value).strip()
        lowered = raw.lower()
        if not raw:
            raise ValueError("value is required")
        if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("placeholder values are not valid runtime config")
        return raw

    @field_validator(
        "google_client_id",
        "google_redirect_uri",
        "auth_public_backend_origin",
        "email_from_name",
        "email_brevo_api_base_url",
        "email_public_base_url",
        "email_unsubscribe_base_url",
        mode="before",
    )
    @classmethod
    def reject_placeholder_strings(cls, value: Any) -> Any:
        if value is None:
            return None
        raw = str(value).strip()
        lowered = raw.lower()
        if raw and any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("placeholder values are not valid runtime config")
        return raw or None

    @field_validator("email_from_address", mode="before")
    @classmethod
    def reject_placeholder_sender_address(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        raw = str(value)
        if any(marker in raw.lower() for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("email_sender_mailbox_invalid")
        return raw

    @field_validator("email_worker_id", mode="before")
    @classmethod
    def normalize_email_worker_id(cls, value: Any) -> Any:
        if value is None:
            return None
        raw = str(value).strip()
        return raw or None

    @field_validator("email_resend_webhook_secret", mode="before")
    @classmethod
    def normalize_email_resend_webhook_secret(cls, value: Any) -> Any:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        lowered = raw.lower()
        if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("placeholder values are not valid runtime config")
        if not raw.startswith("whsec_"):
            raise ValueError("EMAIL_RESEND_WEBHOOK_SECRET must use the whsec_ prefix")
        return raw

    @field_validator("email_resend_webhook_max_body_bytes", "email_resend_webhook_event_retention_days", mode="before")
    @classmethod
    def normalize_optional_webhook_ints(cls, value: Any) -> Any:
        if value is None:
            return None
        raw = str(value).strip()
        return raw or None

    @field_validator(
        "ai_backtest_scope_hmac_primary_version",
        "ai_backtest_scope_hmac_previous_version",
        "ai_backtest_raw_audit_admission_hmac_key_version",
        "ai_backtest_raw_audit_admission_audience",
        "ai_backtest_raw_audit_evidence_id",
        "ai_backtest_raw_audit_deployment_revision",
        mode="before",
    )
    @classmethod
    def normalize_ai_backtest_strings(cls, value: Any) -> Any:
        if value is None:
            return None
        raw = str(value).strip()
        return raw or None

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_scheme(cls, value: Any) -> Any:
        raw = str(value or "").strip()
        if raw and not raw.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        return raw

    @field_validator("perf_diagnostics_enabled", mode="before")
    @classmethod
    def validate_perf_diagnostics_enabled(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError("PERF_DIAGNOSTICS_ENABLED must be a boolean value")

    @field_validator("trading_data_database_url", mode="before")
    @classmethod
    def validate_trading_data_database_scheme(cls, value: Any) -> Any:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        if raw and not raw.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
            raise ValueError("TRADING_DATA_DATABASE_URL must be a PostgreSQL URL")
        return raw

    @field_validator("redis_url", mode="before")
    @classmethod
    def validate_redis_scheme(cls, value: Any) -> Any:
        if value is None:
            return None
        raw = str(value or "").strip()
        if raw and not raw.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")
        return raw

    @field_validator("auth_session_cookie_name")
    @classmethod
    def validate_cookie_name(cls, value: str) -> str:
        if not re.match(r"^[A-Za-z0-9_\-]{3,64}$", value):
            raise ValueError("AUTH_SESSION_COOKIE_NAME must be a simple cookie token")
        return value

    @field_validator("pdf_temp_storage_dir", "pdf_temp_seed_dir", "pdf_temp_manifest_path")
    @classmethod
    def validate_pdf_temp_paths(cls, value: str) -> str:
        raw = value.strip()
        if not raw:
            raise ValueError("PDF temp paths must be non-empty")
        return raw

    @field_validator("pdf_temp_persistence")
    @classmethod
    def validate_pdf_temp_persistence(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_PDF_TEMP_PERSISTENCE:
            raise ValueError("PDF_TEMP_PERSISTENCE must be db or manifest")
        return normalized

    @field_validator("email_provider")
    @classmethod
    def validate_email_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"brevo", "resend"}:
            raise ValueError("EMAIL_PROVIDER must be brevo or resend")
        return normalized

    @field_validator("email_rollout_mode")
    @classmethod
    def validate_email_rollout_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_EMAIL_ROLLOUT_MODES:
            raise ValueError("EMAIL_ROLLOUT_MODE must be disabled, allowlist, or production")
        return normalized

    @field_validator("email_from_address")
    @classmethod
    def validate_email_from_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value == "":
            return None
        return validate_sender_mailbox(value, require_authenticated_domain=False)

    @field_validator("email_from_name")
    @classmethod
    def validate_email_from_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("EMAIL_FROM_NAME must be non-empty")
        return normalized

    @field_validator("email_brevo_api_base_url")
    @classmethod
    def validate_email_brevo_api_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("BREVO_API_BASE_URL must be non-empty")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("BREVO_API_BASE_URL must be an absolute http(s) URL")
        return normalized

    @field_validator("email_public_base_url")
    @classmethod
    def validate_email_public_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not normalized:
            return None
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("EMAIL_PUBLIC_BASE_URL must be an absolute http(s) URL")
        return normalized

    @field_validator("email_unsubscribe_base_url")
    @classmethod
    def validate_email_unsubscribe_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not normalized:
            return None
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("EMAIL_UNSUBSCRIBE_BASE_URL must be an absolute http(s) URL")
        return normalized

    @field_validator("email_local_recipient_allowlist")
    @classmethod
    def validate_email_local_recipient_allowlist(cls, value: str) -> str:
        return value.strip()

    @field_validator("hankyung_consensus_api_base_url")
    @classmethod
    def validate_hankyung_consensus_api_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("HANKYUNG_CONSENSUS_API_BASE_URL must be an absolute http(s) URL")
        if (parsed.hostname or "").lower() == "consensus.hankyung.com":
            raise ValueError("consensus.hankyung.com is not allowed as a metadata crawl source")
        return normalized

    @field_validator("hankyung_consensus_crawl_user_agent")
    @classmethod
    def validate_hankyung_consensus_crawl_user_agent(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("HANKYUNG_CONSENSUS_CRAWL_USER_AGENT must be non-empty")
        return normalized

    @field_validator("auth_cookie_samesite")
    @classmethod
    def validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in _ALLOWED_SAMESITE:
            raise ValueError("AUTH_COOKIE_SAMESITE must be Lax, Strict, or None")
        return normalized

    @model_validator(mode="after")
    def validate_auth_runtime(self) -> "Settings":
        if self.auth_enabled:
            missing = []
            if not self.redis_url_value:
                missing.append("REDIS_URL")
            if not self.google_client_id:
                missing.append("GOOGLE_CLIENT_ID")
            if self.google_client_secret is None:
                missing.append("GOOGLE_CLIENT_SECRET")
            if not self.google_redirect_uri:
                missing.append("GOOGLE_REDIRECT_URI")
            if missing:
                raise ValueError(f"auth-enabled runtime requires {', '.join(missing)}")

            redirect = urlsplit(self.google_redirect_uri or "")
            if redirect.scheme not in {"http", "https"} or not redirect.netloc:
                raise ValueError("GOOGLE_REDIRECT_URI must be an absolute http(s) URL")
            if self.is_production and redirect.scheme != "https":
                raise ValueError("GOOGLE_REDIRECT_URI must use https in production")
            if self.is_production and not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
            if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
                raise ValueError("SameSite=None requires AUTH_COOKIE_SECURE=true")
            if "*" in self.allowed_origins:
                raise ValueError("AUTH_ALLOWED_ORIGINS cannot contain '*' with credentialed cookies")
            if self.auth_session_idle_ttl_seconds > self.auth_session_absolute_ttl_seconds:
                raise ValueError(
                    "AUTH_SESSION_IDLE_TTL_SECONDS must not exceed "
                    "AUTH_SESSION_ABSOLUTE_TTL_SECONDS"
                )

            if self.auth_session_touch_interval_seconds > self.auth_session_idle_ttl_seconds:
                raise ValueError(
                    "AUTH_SESSION_TOUCH_INTERVAL_SECONDS must not exceed "
                    "AUTH_SESSION_IDLE_TTL_SECONDS"
                )
            if self.ai_backtest_scope_hmac_primary is None:
                missing.append("AI_BACKTEST_SCOPE_HMAC_PRIMARY")
            if not self.ai_backtest_scope_hmac_primary_version:
                missing.append("AI_BACKTEST_SCOPE_HMAC_PRIMARY_VERSION")
            previous_present = self.ai_backtest_scope_hmac_previous is not None
            previous_version_present = bool(self.ai_backtest_scope_hmac_previous_version)
            if previous_present != previous_version_present:
                missing.append("AI_BACKTEST_SCOPE_HMAC_PREVIOUS and AI_BACKTEST_SCOPE_HMAC_PREVIOUS_VERSION must be set together")
            if self.ai_backtest_raw_audit_enabled:
                raw_audit_values = {
                    "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_SECRET": self.ai_backtest_raw_audit_admission_hmac_secret,
                    "AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_KEY_VERSION": self.ai_backtest_raw_audit_admission_hmac_key_version,
                    "AI_BACKTEST_RAW_AUDIT_ADMISSION_TOKEN": self.ai_backtest_raw_audit_admission_token,
                    "AI_BACKTEST_RAW_AUDIT_ADMISSION_AUDIENCE": self.ai_backtest_raw_audit_admission_audience,
                    "AI_BACKTEST_RAW_AUDIT_EVIDENCE_ID": self.ai_backtest_raw_audit_evidence_id,
                    "AI_BACKTEST_RAW_AUDIT_DEPLOYMENT_REVISION": self.ai_backtest_raw_audit_deployment_revision,
                }
                missing.extend(name for name, value in raw_audit_values.items() if value is None)
                if (
                    self.google_client_secret_value is not None
                    and self.ai_backtest_raw_audit_admission_hmac_secret is not None
                    and hmac.compare_digest(
                        self.google_client_secret_value,
                        self.ai_backtest_raw_audit_admission_hmac_secret.get_secret_value(),
                    )
                ):
                    missing.append("AI_BACKTEST_RAW_AUDIT_ADMISSION_HMAC_SECRET must not reuse GOOGLE_CLIENT_SECRET")
        if self.email_delivery_worker_enabled and not self.email_delivery_enabled:
            raise ValueError("EMAIL_DELIVERY_WORKER_ENABLED requires EMAIL_DELIVERY_ENABLED=true")
        rollout_mode_explicit = "email_rollout_mode" in self.model_fields_set
        if rollout_mode_explicit and self.email_local_live_send_enabled:
            raise ValueError("EMAIL_LOCAL_LIVE_SEND_ENABLED cannot be combined with EMAIL_ROLLOUT_MODE")
        if not rollout_mode_explicit and self.email_local_live_send_enabled and not self.email_local_recipient_allowlist_values:
            raise ValueError("EMAIL_LOCAL_LIVE_SEND_ENABLED requires EMAIL_LOCAL_RECIPIENT_ALLOWLIST")
        if self.email_rollout_mode == "allowlist" and not self.email_local_recipient_allowlist_values:
            raise ValueError("EMAIL_ROLLOUT_MODE=allowlist requires EMAIL_LOCAL_RECIPIENT_ALLOWLIST")
        if self.email_rollout_mode in {"allowlist", "production"}:
            if not self.email_delivery_enabled:
                raise ValueError("server email rollout requires EMAIL_DELIVERY_ENABLED=true")
            if self.email_provider != "brevo":
                raise ValueError("server email rollout requires EMAIL_PROVIDER=brevo")
            if self.email_api_key is None:
                raise ValueError("server email rollout requires BREVO_API_KEY")
            try:
                validate_sender_mailbox(self.email_from_address, require_authenticated_domain=True)
            except ValueError:
                raise PydanticCustomError("server_email_sender_invalid", "server_email_sender_invalid") from None
            _validate_server_public_url(self.email_public_base_url, name="EMAIL_PUBLIC_BASE_URL")
            if not self.email_unsubscribe_enabled:
                raise ValueError("server email rollout requires EMAIL_UNSUBSCRIBE_ENABLED=true")
            _validate_server_public_url(self.email_unsubscribe_base_url, name="EMAIL_UNSUBSCRIBE_BASE_URL")

            database = urlsplit(self.database_url_value)
            if _is_local_runtime_host(database.hostname) or database.path.rstrip("/").rsplit("/", 1)[-1] != "qt_db":
                raise ValueError("server email rollout requires a non-local PostgreSQL qt_db endpoint")
            redis = urlsplit(self.redis_url_value or "")
            if _is_local_runtime_host(redis.hostname) or redis.path.strip("/") != "11":
                raise ValueError("server email rollout requires a non-local Redis endpoint using logical DB 11")
            if self.email_rollout_mode == "production" and self.email_brevo_sandbox_mode:
                raise ValueError("EMAIL_ROLLOUT_MODE=production requires BREVO_SANDBOX_MODE=false")
        if self.email_brevo_webhook_enabled and self.email_brevo_webhook_bearer_token is None:
            raise ValueError("BREVO_WEBHOOK_ENABLED requires BREVO_WEBHOOK_BEARER_TOKEN")
        if self.email_resend_webhook_enabled and self.email_resend_webhook_secret is None:
            raise ValueError("EMAIL_RESEND_WEBHOOK_ENABLED requires EMAIL_RESEND_WEBHOOK_SECRET")
        if self.email_unsubscribe_enabled:
            missing = []
            if self.email_unsubscribe_signing_secret is None:
                missing.append("EMAIL_UNSUBSCRIBE_SIGNING_SECRET")
            if not self.email_unsubscribe_base_url:
                missing.append("EMAIL_UNSUBSCRIBE_BASE_URL")
            if missing:
                raise ValueError(f"EMAIL_UNSUBSCRIBE_ENABLED requires {', '.join(missing)}")
            unsubscribe_base_url = urlsplit(self.email_unsubscribe_base_url or "")
            if self.is_production and unsubscribe_base_url.scheme != "https":
                raise ValueError("EMAIL_UNSUBSCRIBE_BASE_URL must use https in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in _PRODUCTION_ENVS

    @property
    def database_url_value(self) -> str:
        return self.database_url.get_secret_value()

    @property
    def trading_data_database_url_value(self) -> str | None:
        if self.trading_data_database_url is None:
            return None
        return self.trading_data_database_url.get_secret_value()

    @property
    def redis_url_value(self) -> str | None:
        if self.redis_url is None:
            return None
        return self.redis_url.get_secret_value()

    @property
    def google_client_secret_value(self) -> str | None:
        if self.google_client_secret is None:
            return None
        return self.google_client_secret.get_secret_value()

    @property
    def sqlalchemy_database_url(self) -> str:
        raw = self.database_url_value
        if raw.startswith("postgresql+asyncpg://"):
            return raw
        if raw.startswith("postgresql://"):
            return "postgresql+asyncpg://" + raw.removeprefix("postgresql://")
        if raw.startswith("postgres://"):
            return "postgresql+asyncpg://" + raw.removeprefix("postgres://")
        return raw

    @property
    def trading_data_sqlalchemy_database_url(self) -> str | None:
        raw = self.trading_data_database_url_value
        if raw is None:
            return None
        if raw.startswith("postgresql+asyncpg://"):
            return raw
        if raw.startswith("postgresql://"):
            return "postgresql+asyncpg://" + raw.removeprefix("postgresql://")
        if raw.startswith("postgres://"):
            return "postgresql+asyncpg://" + raw.removeprefix("postgres://")
        return raw

    @property
    def allowed_origins(self) -> list[str]:
        return _split_csv(self.auth_allowed_origins)

    @property
    def allowed_hosts(self) -> list[str]:
        return _split_csv(self.auth_allowed_hosts)

    @property
    def pdf_temp_allowed_hosts(self) -> list[str]:
        return _split_csv(self.pdf_temp_url_allowed_hosts)

    @property
    def hankyung_consensus_api_bearer_token_value(self) -> str | None:
        if self.hankyung_consensus_api_bearer_token is None:
            return None
        return self.hankyung_consensus_api_bearer_token.get_secret_value()

    @property
    def hankyung_consensus_auth_header_value(self) -> str | None:
        if self.hankyung_consensus_auth_header is None:
            return None
        return self.hankyung_consensus_auth_header.get_secret_value()

    @property
    def email_api_key_value(self) -> str | None:
        if self.email_api_key is None:
            return None
        return self.email_api_key.get_secret_value()

    @property
    def email_brevo_webhook_bearer_token_value(self) -> str | None:
        if self.email_brevo_webhook_bearer_token is None:
            return None
        return self.email_brevo_webhook_bearer_token.get_secret_value()

    @property
    def email_unsubscribe_signing_secret_value(self) -> str | None:
        if self.email_unsubscribe_signing_secret is None:
            return None
        return self.email_unsubscribe_signing_secret.get_secret_value()

    @property
    def email_unsubscribe_base_url_value(self) -> str | None:
        if self.email_unsubscribe_base_url is None:
            return None
        return self.email_unsubscribe_base_url

    @property
    def email_resend_webhook_secret_value(self) -> str | None:
        if self.email_resend_webhook_secret is None:
            return None
        return self.email_resend_webhook_secret.get_secret_value()

    @property
    def email_local_recipient_allowlist_values(self) -> list[str]:
        return _split_csv(self.email_local_recipient_allowlist)

    @property
    def email_dev_recipient_allowlist_values(self) -> list[str]:
        return self.email_local_recipient_allowlist_values

    @property
    def email_allow_local_live_send(self) -> bool:
        return self.email_local_live_send_enabled

    @property
    def email_effective_rollout_mode(self) -> str:
        if (
            "email_rollout_mode" not in self.model_fields_set
            and self.email_rollout_mode == "disabled"
            and self.email_local_live_send_enabled
        ):
            return "allowlist"
        return self.email_rollout_mode

    @property
    def email_uses_legacy_local_canary(self) -> bool:
        return "email_rollout_mode" not in self.model_fields_set and self.email_local_live_send_enabled

    @property
    def email_sender_domain_category(self) -> str:
        domain = _sender_domain(self.email_from_address)
        if domain is None:
            return "not_configured"
        if domain == _EXPECTED_EMAIL_SENDER_DOMAIN:
            return _EXPECTED_EMAIL_SENDER_DOMAIN
        return "other"

    def safe_summary(self) -> dict[str, object]:
        return {
            "app_env": self.app_env,
            "perf_diagnostics_enabled": self.perf_diagnostics_enabled,
            "auth_enabled": self.auth_enabled,
            "database_url": redact_url(self.database_url_value),
            "trading_data_database_url": redact_url(self.trading_data_database_url_value)
            if self.trading_data_database_url_value
            else None,
            "redis_url": redact_url(self.redis_url_value) if self.redis_url_value else None,
            "google_client_id": "<configured>" if self.google_client_id else None,
            "google_redirect_uri": self.google_redirect_uri,
            "auth_public_backend_origin": self.auth_public_backend_origin,
            "auth_allowed_hosts": self.allowed_hosts,
            "auth_allowed_origins": self.allowed_origins,
            "auth_trusted_proxy_headers": self.auth_trusted_proxy_headers,
            "auth_session_cookie_name": self.auth_session_cookie_name,
            "auth_cookie_secure": self.auth_cookie_secure,
            "auth_cookie_samesite": self.auth_cookie_samesite,
            "auth_cookie_domain": self.auth_cookie_domain,
            "auth_cookie_path": self.auth_cookie_path,
            "auth_session_idle_ttl_seconds": self.auth_session_idle_ttl_seconds,
            "auth_session_absolute_ttl_seconds": self.auth_session_absolute_ttl_seconds,
            "auth_session_touch_interval_seconds": self.auth_session_touch_interval_seconds,
            "auth_csrf_required": self.auth_csrf_required,
            "ai_backtest_scope_hmac_primary": "<configured>" if self.ai_backtest_scope_hmac_primary else None,
            "ai_backtest_scope_hmac_primary_version": self.ai_backtest_scope_hmac_primary_version,
            "ai_backtest_scope_hmac_previous": "<configured>" if self.ai_backtest_scope_hmac_previous else None,
            "ai_backtest_scope_hmac_previous_version": self.ai_backtest_scope_hmac_previous_version,
            "ai_backtest_raw_audit_enabled": self.ai_backtest_raw_audit_enabled,
            "ai_account_token_default_quota_limit": self.ai_account_token_default_quota_limit,
            "ai_account_token_default_quota_window_seconds": (
                self.ai_account_token_default_quota_window_seconds
            ),
            "email_delivery_enabled": self.email_delivery_enabled,
            "email_report_completed_trigger_enabled": self.email_report_completed_trigger_enabled,
            "email_delivery_worker_enabled": self.email_delivery_worker_enabled,
            "email_rollout_mode": self.email_effective_rollout_mode,
            "email_rollout_mode_source": "legacy_local_canary" if self.email_uses_legacy_local_canary else "explicit",
            "email_provider": self.email_provider,
            "email_from_address": "<configured>" if self.email_from_address else None,
            "email_sender_domain": self.email_sender_domain_category,
            "email_from_name": self.email_from_name,
            "email_api_key": "<configured>" if self.email_api_key else None,
            "email_brevo_api_base_url": self.email_brevo_api_base_url,
            "email_brevo_sandbox_mode": self.email_brevo_sandbox_mode,
            "email_brevo_webhook_enabled": self.email_brevo_webhook_enabled,
            "email_brevo_webhook_bearer_token": "<configured>"
            if self.email_brevo_webhook_bearer_token
            else None,
            "email_brevo_webhook_tolerance_seconds": self.email_brevo_webhook_tolerance_seconds,
            "email_brevo_webhook_max_body_bytes": self.email_brevo_webhook_max_body_bytes,
            "email_brevo_webhook_event_retention_days": self.email_brevo_webhook_event_retention_days,
            "email_public_base_url": self.email_public_base_url,
            "email_unsubscribe_enabled": self.email_unsubscribe_enabled,
            "email_unsubscribe_signing_secret": "<configured>" if self.email_unsubscribe_signing_secret else None,
            "email_unsubscribe_token_ttl_seconds": self.email_unsubscribe_token_ttl_seconds,
            "email_unsubscribe_base_url": self.email_unsubscribe_base_url,
            "email_max_attempts": self.email_max_attempts,
            "email_retry_base_seconds": self.email_retry_base_seconds,
            "email_claim_ttl_seconds": self.email_claim_ttl_seconds,
            "email_request_timeout_seconds": self.email_request_timeout_seconds,
            "email_resend_webhook_enabled": self.email_resend_webhook_enabled,
            "email_resend_webhook_secret": "<configured>" if self.email_resend_webhook_secret else None,
            "email_resend_webhook_tolerance_seconds": self.email_resend_webhook_tolerance_seconds,
            "email_resend_webhook_max_body_bytes": self.email_resend_webhook_max_body_bytes,
            "email_resend_webhook_event_retention_days": self.email_resend_webhook_event_retention_days,
            "email_local_live_send_enabled": self.email_local_live_send_enabled,
            "email_allow_local_live_send": self.email_local_live_send_enabled,
            "email_local_recipient_allowlist_count": len(self.email_local_recipient_allowlist_values),
            "email_worker_id": self.email_worker_id,
            "email_worker_poll_interval_seconds": self.email_worker_poll_interval_seconds,
            "email_worker_claim_lease_seconds": self.email_worker_claim_lease_seconds,
            "email_worker_batch_size": self.email_worker_batch_size,
            "email_worker_shutdown_grace_seconds": self.email_worker_shutdown_grace_seconds,
            "email_digest_scheduler_batch_size": self.email_digest_scheduler_batch_size,
            "email_digest_generation_concurrency": self.email_digest_generation_concurrency,
            "pdf_temp_ingest_enabled": self.pdf_temp_ingest_enabled,
            "pdf_temp_storage_dir": "<configured>" if self.pdf_temp_storage_dir else None,
            "pdf_temp_seed_dir": "<configured>" if self.pdf_temp_seed_dir else None,
            "pdf_temp_manifest_path": "<configured>" if self.pdf_temp_manifest_path else None,
            "pdf_temp_persistence": self.pdf_temp_persistence,
            "pdf_temp_max_bytes": self.pdf_temp_max_bytes,
            "pdf_temp_url_allowed_hosts": self.pdf_temp_allowed_hosts,
            "pdf_temp_http_user_agent": "<configured>" if self.pdf_temp_http_user_agent else None,
            "pdf_temp_url_timeout_seconds": self.pdf_temp_url_timeout_seconds,
            "pdf_temp_url_max_redirects": self.pdf_temp_url_max_redirects,
            "pdf_temp_min_text_chars": self.pdf_temp_min_text_chars,
            "pdf_temp_max_seed_batch_size": self.pdf_temp_max_seed_batch_size,
            "hankyung_consensus_crawler_enabled": self.hankyung_consensus_crawler_enabled,
            "hankyung_consensus_api_base_url": self.hankyung_consensus_api_base_url,
            "hankyung_consensus_api_bearer_token": "<configured>"
            if self.hankyung_consensus_api_bearer_token
            else None,
            "hankyung_consensus_auth_header": "<configured>" if self.hankyung_consensus_auth_header else None,
            "hankyung_consensus_crawl_max_pages": self.hankyung_consensus_crawl_max_pages,
            "hankyung_consensus_crawl_max_reports": self.hankyung_consensus_crawl_max_reports,
            "hankyung_consensus_crawl_timeout_seconds": self.hankyung_consensus_crawl_timeout_seconds,
            "hankyung_consensus_crawl_user_agent": "<configured>"
            if self.hankyung_consensus_crawl_user_agent
            else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"Settings({self.safe_summary()!r})"


def redact_url(raw: str | None) -> str:
    if not raw:
        return "<redacted>"
    try:
        parsed = urlsplit(raw)
    except Exception:
        return "<redacted>"
    if not parsed.scheme:
        return "<redacted>"
    return f"{parsed.scheme}://<redacted>"


def redact_secrets(value: Any) -> Any:
    """Recursively remove DSNs, OAuth secrets, auth codes, tokens, and passwords."""

    if isinstance(value, dict):
        return {key: redact_secrets(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact_secrets(item) for item in value]
    if not isinstance(value, str):
        return value

    text = value
    text = re.sub(r"postgres(?:ql)?(?:\+asyncpg)?://[^\s]+", "postgresql://<redacted>", text, flags=re.I)
    text = re.sub(r"rediss?://[^\s]+", "redis://<redacted>", text, flags=re.I)
    text = re.sub(r"(password\s*[=:]\s*)[^\s,;]+", r"\1<redacted>", text, flags=re.I)
    text = re.sub(r"((?:client_)?secret\s*[=:]\s*)[^\s,;]+", r"\1<redacted>", text, flags=re.I)
    text = re.sub(r"((?:auth_)?code\s*[=:]\s*)[^\s,;]+", r"\1<redacted>", text, flags=re.I)
    text = re.sub(r"((?:id|access|refresh)?_?token\s*[=:]\s*)[^\s,;]+", r"\1<redacted>", text, flags=re.I)
    return text


_CONFIGURATION_VALIDATION_LOCATIONS = {"__root__", "field", "settings"}
for _field_name, _field in Settings.model_fields.items():
    _CONFIGURATION_VALIDATION_LOCATIONS.add(_field_name)
    if isinstance(_field.alias, str):
        _CONFIGURATION_VALIDATION_LOCATIONS.add(_field.alias)
    _validation_alias_choices = getattr(_field.validation_alias, "choices", ())
    _CONFIGURATION_VALIDATION_LOCATIONS.update(
        choice for choice in _validation_alias_choices if isinstance(choice, str)
    )


def _safe_validation_location(value: Any) -> list[str | int]:
    raw_parts = value if isinstance(value, (list, tuple)) else (value,)
    safe_parts: list[str | int] = []
    for part in raw_parts:
        if isinstance(part, int):
            safe_parts.append(part)
        elif (
            isinstance(part, str)
            and _VALIDATION_LOCATION_PATTERN.fullmatch(part)
            and part in _CONFIGURATION_VALIDATION_LOCATIONS
        ):
            safe_parts.append(part)
        else:
            safe_parts.append("field")
    return safe_parts or ["settings"]


def _validation_classification(error_type: Any) -> tuple[str, str]:
    if not isinstance(error_type, str):
        return _DEFAULT_VALIDATION_CLASSIFICATION
    return _VALIDATION_CLASSIFICATION_BY_TYPE.get(error_type, _DEFAULT_VALIDATION_CLASSIFICATION)


def sanitize_configuration_validation_details(value: Any) -> Any:
    """Return category-only Pydantic validation details without rejected values."""

    if isinstance(value, (list, tuple)):
        return [sanitize_configuration_validation_details(item) for item in value]
    if not isinstance(value, dict):
        return None

    lowered_keys = {str(key).lower() for key in value}
    if lowered_keys.intersection({"loc", "type", "msg", "ctx", "url"}):
        location = value.get("loc", value.get("location", value.get("setting", "settings")))
        category, reason = _validation_classification(value.get("type"))
        return {
            "location": _safe_validation_location(location),
            "category": category,
            "reason": reason,
        }

    sanitized: dict[str, Any] = {}
    has_classification = bool(lowered_keys.intersection({"category", "code", "reason", "type"}))
    requested_classification = (value.get("category"), value.get("reason", value.get("code")))
    trusted_classification = _DEFAULT_VALIDATION_CLASSIFICATION
    if all(isinstance(item, str) for item in requested_classification) and (
        requested_classification in _TRUSTED_VALIDATION_CLASSIFICATIONS
    ):
        trusted_classification = requested_classification
    for key, item in value.items():
        safe_key = str(key).lower()
        if safe_key in _VALIDATION_VALUE_KEYS:
            continue
        if safe_key in {"loc", "location", "setting", "field"}:
            sanitized["location"] = _safe_validation_location(item)
        elif safe_key in {"category", "code", "reason", "type"}:
            continue
        elif safe_key in {"details", "errors", "items"} and isinstance(item, (dict, list, tuple)):
            sanitized[safe_key] = sanitize_configuration_validation_details(item)
    if has_classification:
        sanitized["category"], sanitized["reason"] = trusted_classification
    return sanitized


class ConfigurationError(RuntimeError):
    def __init__(self, message: str, details: Any | None = None):
        safe_message = message if message in _SAFE_CONFIGURATION_ERROR_MESSAGES else "Backend configuration is invalid"
        super().__init__(safe_message)
        self.details = sanitize_configuration_validation_details(details or {})


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        safe_details = sanitize_configuration_validation_details(exc.errors(include_url=False))
    raise ConfigurationError(
        "Invalid or missing backend configuration",
        safe_details,
    ) from None
