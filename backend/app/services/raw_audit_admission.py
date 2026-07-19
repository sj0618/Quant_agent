from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.config import Settings


_ISSUER_TOKEN = object()
_RAW_AUDIT_TEST_ONLY_MARKER = object()
_RAW_AUDIT_HARD_DISABLED_ENVS = frozenset({"prod", "production", "stage", "staging"})


class RawAuditAdmission:
    """Opaque, short-lived capability required to persist raw model content."""

    __slots__ = ("_expires_at", "_issuer_token")

    def __init__(self) -> None:
        raise TypeError("RawAuditAdmission is issued only after signed Gate B verification")


def issue_raw_audit_admission(
    settings: Settings,
    *,
    test_marker: object | None = None,
) -> RawAuditAdmission | None:
    """Issue a capability only after validating a signed, unexpired Gate B token."""

    from app.core.config import Settings

    if not isinstance(settings, Settings):
        return None
    app_env = getattr(settings, "app_env", "")
    if isinstance(app_env, str) and app_env.strip().lower() in _RAW_AUDIT_HARD_DISABLED_ENVS:
        return None
    if getattr(settings, "ai_backtest_raw_audit_enabled", False) is not True:
        return None
    if test_marker is _RAW_AUDIT_TEST_ONLY_MARKER:
        return _issue_test_raw_audit_admission(settings)
    if test_marker is not None:
        return None

    secret = getattr(settings, "ai_backtest_raw_audit_admission_hmac_secret", None)
    token = getattr(settings, "ai_backtest_raw_audit_admission_token", None)
    key_version = _required_text(getattr(settings, "ai_backtest_raw_audit_admission_hmac_key_version", None))
    evidence_id = _required_text(getattr(settings, "ai_backtest_raw_audit_evidence_id", None))
    deployment_revision = _required_text(getattr(settings, "ai_backtest_raw_audit_deployment_revision", None))
    audience = _required_text(getattr(settings, "ai_backtest_raw_audit_admission_audience", None))
    if not all((secret, token, key_version, evidence_id, deployment_revision, audience)):
        return None

    try:
        parsed = _parse_signed_token(token.get_secret_value(), secret.get_secret_value())
    except (AttributeError, TypeError, UnicodeEncodeError):
        return None
    if parsed is None:
        return None
    header, claims = parsed
    if header.get("alg") != "HS256" or header.get("key_version") != key_version:
        return None
    if claims.get("key_version") != key_version:
        return None
    if claims.get("evidence_id") != evidence_id:
        return None
    if claims.get("deployment_revision") != deployment_revision:
        return None
    if claims.get("audience") != audience:
        return None

    issued_at = claims.get("issued_at")
    expires_at = claims.get("expiry")
    if not _valid_timestamp(issued_at) or not _valid_timestamp(expires_at):
        return None
    now = time.time()
    if issued_at > now or expires_at <= now or expires_at <= issued_at:
        return None
    return _new_admission(expires_at)


def issue_test_raw_audit_admission(settings: Settings) -> RawAuditAdmission | None:
    """Issue a test-only capability with an explicit, non-configurable marker."""

    return issue_raw_audit_admission(settings, test_marker=_RAW_AUDIT_TEST_ONLY_MARKER)


def verify_raw_audit_admission(admission: object) -> bool:
    """Reject every object except a currently valid capability issued by this module."""

    return (
        isinstance(admission, RawAuditAdmission)
        and getattr(admission, "_issuer_token", None) is _ISSUER_TOKEN
        and _valid_timestamp(getattr(admission, "_expires_at", None))
        and admission._expires_at > time.time()
    )


def _issue_test_raw_audit_admission(settings: Settings) -> RawAuditAdmission | None:
    if getattr(settings, "app_env", "").lower() != "test":
        return None
    return _new_admission(time.time() + 300)


def _new_admission(expires_at: float) -> RawAuditAdmission:
    admission = object.__new__(RawAuditAdmission)
    admission._issuer_token = _ISSUER_TOKEN
    admission._expires_at = expires_at
    return admission


def _parse_signed_token(token: str, secret: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    encoded_header, encoded_claims, encoded_signature = parts
    try:
        header = _decode_json_segment(encoded_header)
        claims = _decode_json_segment(encoded_claims)
        signature = _decode_segment(encoded_signature)
    except (ValueError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(header, dict) or not isinstance(claims, dict):
        return None

    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    expected_signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        return None
    return header, claims


def _decode_json_segment(value: str) -> dict[str, Any]:
    decoded = _decode_segment(value)
    parsed = json.loads(decoded.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("token segment must be an object")
    return parsed


def _decode_segment(value: str) -> bytes:
    if not value or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in value):
        raise ValueError("invalid base64url token segment")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _required_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _valid_timestamp(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
