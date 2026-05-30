from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings, redact_secrets
from app.core.errors import AppError

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str | None = None
    picture: str | None = None


def build_google_authorization_url(settings: Settings, *, state: str, nonce: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def exchange_authorization_code(settings: Settings, *, code: str, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret_value,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    close_client = client is None
    http = client or httpx.AsyncClient(timeout=10)
    try:
        response = await http.post(GOOGLE_TOKEN_ENDPOINT, data=payload)
        if response.status_code >= 400:
            raise AppError(
                status_code=401,
                component="auth",
                code="google_token_exchange_failed",
                message="Google token exchange failed",
                details={"status_code": response.status_code, "body": redact_secrets(response.text[:500])},
            )
        data = response.json()
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=503,
            component="auth",
            code="google_token_exchange_unavailable",
            message="Google token exchange unavailable",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        ) from exc
    finally:
        if close_client:
            await http.aclose()
    if not data.get("id_token"):
        raise AppError(status_code=401, component="auth", code="google_id_token_missing", message="Google response did not include an ID token")
    return data


async def validate_google_id_token(
    settings: Settings,
    *,
    id_token: str,
    expected_nonce: str,
    client: httpx.AsyncClient | None = None,
) -> GoogleIdentity:
    """Validate Google ID token through Google's tokeninfo boundary.

    Runtime code treats this as an external verification boundary and still
    verifies issuer, audience, expiry, nonce, subject, email, and email_verified.
    Tests mock this boundary; no fake identity is created on failure.
    """

    close_client = client is None
    http = client or httpx.AsyncClient(timeout=10)
    try:
        response = await http.get(GOOGLE_TOKENINFO_ENDPOINT, params={"id_token": id_token})
        if response.status_code >= 400:
            raise AppError(status_code=401, component="auth", code="google_id_token_invalid", message="Google ID token is invalid")
        claims = response.json()
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=503,
            component="auth",
            code="google_id_token_verification_unavailable",
            message="Google ID token verification unavailable",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        ) from exc
    finally:
        if close_client:
            await http.aclose()
    return validate_google_claims(settings, claims=claims, expected_nonce=expected_nonce)


def validate_google_claims(settings: Settings, *, claims: dict[str, Any], expected_nonce: str) -> GoogleIdentity:
    aud = claims.get("aud")
    iss = claims.get("iss")
    exp = claims.get("exp")
    nonce = claims.get("nonce")
    sub = claims.get("sub")
    email = claims.get("email")
    email_verified = claims.get("email_verified")

    if aud != settings.google_client_id:
        raise AppError(status_code=401, component="auth", code="google_audience_invalid", message="Google ID token audience is invalid")
    if iss not in GOOGLE_ISSUERS:
        raise AppError(status_code=401, component="auth", code="google_issuer_invalid", message="Google ID token issuer is invalid")
    try:
        if int(exp) <= int(time()):
            raise ValueError("expired")
    except Exception as exc:  # noqa: BLE001
        raise AppError(status_code=401, component="auth", code="google_token_expired", message="Google ID token is expired") from exc
    if nonce != expected_nonce:
        raise AppError(status_code=401, component="auth", code="google_nonce_invalid", message="Google ID token nonce is invalid")
    if not sub:
        raise AppError(status_code=401, component="auth", code="google_sub_missing", message="Google ID token subject is missing")
    if not email:
        raise AppError(status_code=401, component="auth", code="google_email_missing", message="Google ID token email is missing")
    if str(email_verified).lower() != "true":
        raise AppError(status_code=401, component="auth", code="google_email_unverified", message="Google email must be verified")
    return GoogleIdentity(
        sub=str(sub),
        email=str(email),
        email_verified=True,
        name=claims.get("name"),
        picture=claims.get("picture"),
    )
