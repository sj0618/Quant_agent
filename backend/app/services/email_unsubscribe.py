from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.config import Settings
from app.core.errors import AppError
from app.db import user_preferences
from app.db.user_queries import load_user_by_id

UNSUBSCRIBE_COMPONENT = "unsubscribe"
UNSUBSCRIBE_DISABLED_CODE = "unsubscribe_disabled"
UNSUBSCRIBE_TOKEN_REQUIRED_CODE = "unsubscribe_token_required"
UNSUBSCRIBE_TOKEN_MALFORMED_CODE = "unsubscribe_token_malformed"
UNSUBSCRIBE_TOKEN_INVALID_CODE = "unsubscribe_token_invalid"
UNSUBSCRIBE_TOKEN_EXPIRED_CODE = "unsubscribe_token_expired"
UNSUBSCRIBE_TARGET_INVALID_CODE = "unsubscribe_target_invalid"
UNSUBSCRIBE_PURPOSE = "action_email_unsubscribe"
UNSUBSCRIBE_TOKEN_VERSION = 1
UNSUBSCRIBE_TOKEN_PREFIX = "u1"
DEFAULT_UNSUBSCRIBE_TTL_SECONDS = 60 * 60 * 24 * 30


@dataclass(frozen=True, slots=True)
class UnsubscribeTokenClaims:
    version: int
    user_id: str
    purpose: str
    issued_at: datetime
    expires_at: datetime
    nonce: str


def _disabled_error() -> AppError:
    return AppError(
        status_code=503,
        component=UNSUBSCRIBE_COMPONENT,
        code=UNSUBSCRIBE_DISABLED_CODE,
        message="Public unsubscribe is disabled",
    )


def _invalid_token_error(code: str, message: str, *, status_code: int = 400) -> AppError:
    return AppError(
        status_code=status_code,
        component=UNSUBSCRIBE_COMPONENT,
        code=code,
        message=message,
    )


def assert_unsubscribe_enabled(settings: Settings) -> None:
    if not settings.email_unsubscribe_enabled:
        raise _disabled_error()
    if not settings.email_unsubscribe_signing_secret_value:
        raise AppError(
            status_code=503,
            component=UNSUBSCRIBE_COMPONENT,
            code="unsubscribe_secret_missing",
            message="Public unsubscribe is not configured",
        )
    if not settings.email_unsubscribe_base_url_value:
        raise AppError(
            status_code=503,
            component=UNSUBSCRIBE_COMPONENT,
            code="unsubscribe_base_url_missing",
            message="Public unsubscribe is not configured",
        )


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sign_payload(secret: str, payload_bytes: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _encode_payload(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(_canonical_payload(payload)).rstrip(b"=").decode("ascii")


def _decode_base64url(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}".encode("ascii"))


def _parse_timestamp(raw: Any, *, field_name: str) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_MALFORMED_CODE, f"Unsubscribe token {field_name} is invalid")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception as exc:  # noqa: BLE001
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_MALFORMED_CODE, f"Unsubscribe token {field_name} is invalid") from exc


def _normalize_user_id(raw: Any) -> str:
    user_id = str(raw).strip()
    if not user_id:
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_MALFORMED_CODE, "Unsubscribe token user id is invalid")
    return user_id


def generate_unsubscribe_token(
    settings: Settings,
    *,
    user_id: str | int,
    purpose: str = UNSUBSCRIBE_PURPOSE,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
    nonce: str | None = None,
) -> str:
    assert_unsubscribe_enabled(settings)
    signing_secret = settings.email_unsubscribe_signing_secret_value
    if signing_secret is None:
        raise _disabled_error()
    now = issued_at or datetime.now(UTC)
    expiry = expires_at or (now + timedelta(seconds=settings.email_unsubscribe_token_ttl_seconds or DEFAULT_UNSUBSCRIBE_TTL_SECONDS))
    payload = {
        "version": UNSUBSCRIBE_TOKEN_VERSION,
        "user_id": str(user_id),
        "purpose": purpose,
        "issued_at": now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "expires_at": expiry.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "nonce": nonce or uuid4().hex,
    }
    payload_bytes = _canonical_payload(payload)
    signature = _sign_payload(signing_secret, payload_bytes)
    return f"{UNSUBSCRIBE_TOKEN_PREFIX}.{_encode_payload(payload)}.{signature}"


def build_unsubscribe_url(settings: Settings, *, user_id: str | int) -> str:
    assert_unsubscribe_enabled(settings)
    base_url = settings.email_unsubscribe_base_url_value
    if not base_url:
        raise _disabled_error()
    token = generate_unsubscribe_token(settings, user_id=user_id)
    query = urlencode({"token": token})
    return f"{base_url.rstrip('/')}/unsubscribe?{query}"


def verify_unsubscribe_token(
    settings: Settings,
    token: str | None,
    *,
    expected_purpose: str = UNSUBSCRIBE_PURPOSE,
    now: datetime | None = None,
) -> UnsubscribeTokenClaims:
    assert_unsubscribe_enabled(settings)
    signing_secret = settings.email_unsubscribe_signing_secret_value
    if signing_secret is None:
        raise _disabled_error()
    if token is None or not str(token).strip():
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_REQUIRED_CODE, "Unsubscribe token is required")

    raw = str(token).strip()
    parts = raw.split(".")
    if len(parts) != 3 or parts[0] != UNSUBSCRIBE_TOKEN_PREFIX:
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_MALFORMED_CODE, "Unsubscribe token is malformed")

    _, payload_part, signature_part = parts
    try:
        payload_bytes = _decode_base64url(payload_part)
        expected_signature = _sign_payload(signing_secret, payload_bytes)
    except Exception as exc:  # noqa: BLE001
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_MALFORMED_CODE, "Unsubscribe token is malformed") from exc

    if not hmac.compare_digest(expected_signature, signature_part):
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_INVALID_CODE, "Unsubscribe token is invalid")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_MALFORMED_CODE, "Unsubscribe token is malformed") from exc

    if not isinstance(payload, dict):
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_MALFORMED_CODE, "Unsubscribe token is malformed")

    try:
        version = int(payload.get("version"))
    except Exception as exc:  # noqa: BLE001
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_MALFORMED_CODE, "Unsubscribe token is malformed") from exc
    if version != UNSUBSCRIBE_TOKEN_VERSION:
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_INVALID_CODE, "Unsubscribe token is invalid")

    purpose = str(payload.get("purpose") or "").strip()
    if purpose != expected_purpose:
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_INVALID_CODE, "Unsubscribe token is invalid")

    issued_at = _parse_timestamp(payload.get("issued_at"), field_name="issued_at")
    expires_at = _parse_timestamp(payload.get("expires_at"), field_name="expires_at")
    current_time = now or datetime.now(UTC)
    if expires_at <= current_time.astimezone(UTC):
        raise _invalid_token_error(UNSUBSCRIBE_TOKEN_EXPIRED_CODE, "Unsubscribe token has expired", status_code=410)

    return UnsubscribeTokenClaims(
        version=version,
        user_id=_normalize_user_id(payload.get("user_id")),
        purpose=purpose,
        issued_at=issued_at.astimezone(UTC),
        expires_at=expires_at.astimezone(UTC),
        nonce=_normalize_user_id(payload.get("nonce")),
    )


async def _load_user_and_preferences(
    db: AsyncEngine | AsyncConnection,
    *,
    user_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    engine = db.engine if isinstance(db, AsyncConnection) else db
    user = await load_user_by_id(engine, user_id)
    if user is None:
        raise _invalid_token_error(UNSUBSCRIBE_TARGET_INVALID_CODE, "Unsubscribe target is unavailable")
    settings = await user_preferences.get_notification_settings(
        engine,
        user_id=str(user["id"]),
        email=str(user["email"]),
    )
    return user, settings


async def inspect_unsubscribe_token(
    db: AsyncEngine | AsyncConnection,
    settings: Settings,
    *,
    token: str | None,
) -> dict[str, Any]:
    claims = verify_unsubscribe_token(settings, token)
    _user, notification_settings = await _load_user_and_preferences(db, user_id=claims.user_id)
    action_emails = bool(notification_settings["actionEmails"])
    return {
        "status": "already_unsubscribed" if not action_emails else "ready",
        "actionEmails": action_emails,
    }


async def confirm_unsubscribe(
    db: AsyncEngine | AsyncConnection,
    settings: Settings,
    *,
    token: str | None,
) -> dict[str, Any]:
    claims = verify_unsubscribe_token(settings, token)
    user, notification_settings = await _load_user_and_preferences(db, user_id=claims.user_id)
    action_emails = bool(notification_settings["actionEmails"])
    if action_emails:
        await user_preferences.save_notification_settings(
            db if isinstance(db, AsyncEngine) else db.engine,
            user_id=str(user["id"]),
            email=str(user["email"]),
            daily_report_email=bool(notification_settings["dailyReportEmail"]),
            action_emails=False,
            marketing_email=bool(notification_settings["marketingEmail"]),
            delivery_hour=str(notification_settings["deliveryHour"]),
        )
    return {
        "status": "already_unsubscribed" if not action_emails else "unsubscribed",
        "actionEmails": False,
    }
