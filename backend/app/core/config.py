from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
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
_MAX_HANKYUNG_CRAWL_PAGES = 10
_MAX_HANKYUNG_CRAWL_REPORTS = 200


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


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
    database_url: SecretStr = Field(..., alias="DATABASE_URL")
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
    auth_session_ttl_seconds: int = Field(default=60 * 60 * 8, alias="AUTH_SESSION_TTL_SECONDS", ge=300)
    auth_csrf_ttl_seconds: int = Field(default=3600, alias="AUTH_CSRF_TTL_SECONDS", ge=300)
    auth_csrf_required: bool = Field(default=False, alias="AUTH_CSRF_REQUIRED")

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
        "redis_url",
        "google_client_secret",
        "hankyung_consensus_api_bearer_token",
        "hankyung_consensus_auth_header",
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

    @field_validator("google_client_id", "google_redirect_uri", "auth_public_backend_origin", mode="before")
    @classmethod
    def reject_placeholder_strings(cls, value: Any) -> Any:
        if value is None:
            return None
        raw = str(value).strip()
        lowered = raw.lower()
        if raw and any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("placeholder values are not valid runtime config")
        return raw or None

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_scheme(cls, value: Any) -> Any:
        raw = str(value or "").strip()
        if raw and not raw.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
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
        if not self.auth_enabled:
            return self

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
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in _PRODUCTION_ENVS

    @property
    def database_url_value(self) -> str:
        return self.database_url.get_secret_value()

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

    def safe_summary(self) -> dict[str, object]:
        return {
            "app_env": self.app_env,
            "auth_enabled": self.auth_enabled,
            "database_url": redact_url(self.database_url_value),
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
            "auth_csrf_required": self.auth_csrf_required,
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


class ConfigurationError(RuntimeError):
    def __init__(self, message: str, details: Any | None = None):
        super().__init__(message)
        self.details = redact_secrets(details or {})


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigurationError("Invalid or missing backend configuration", exc.errors(include_url=False)) from exc
