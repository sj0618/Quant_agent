from __future__ import annotations

import hashlib
import secrets
from typing import Any
from urllib.parse import unquote, urlsplit

from fastapi import Request, Response

from app.core.config import Settings
from app.core.errors import AppError

OAUTH_CALLBACK_PATH = "/auth/google/callback"
OAUTH_TRANSACTION_COOKIE_NAME = "qa_oauth_state"
OAUTH_TRANSACTION_COOKIE_PATH = "/api/v1/auth/google"
_LOOPBACK_HTTP_HOSTS = {"localhost", "127.0.0.1", "::1"}


def generate_token_urlsafe(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def _invalid_oauth_redirect_uri() -> AppError:
    return AppError(status_code=400, component="auth", code="invalid_redirect_uri", message="redirect_uri is invalid")


def _normalized_loopback_host(host: str | None) -> str | None:
    if host is None:
        return None
    return host.strip("[]").lower()


def _normalized_netloc(host: str, port: int | None) -> str:
    host = host.lower()
    display_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"{display_host}:{port}" if port is not None else display_host


def _parse_oauth_redirect_uri(raw: str | None, settings: Settings) -> tuple[str, str]:
    value = str(raw or "").strip()
    if not value or "\\" in value:
        raise _invalid_oauth_redirect_uri()
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        port = parsed.port
    except Exception as exc:  # noqa: BLE001
        raise _invalid_oauth_redirect_uri() from exc
    host = _normalized_loopback_host(hostname)
    if scheme not in {"http", "https"} or not parsed.netloc or host is None:
        raise _invalid_oauth_redirect_uri()
    if parsed.username or parsed.password:
        raise _invalid_oauth_redirect_uri()
    if parsed.fragment or parsed.query:
        raise _invalid_oauth_redirect_uri()
    if parsed.path != OAUTH_CALLBACK_PATH:
        raise _invalid_oauth_redirect_uri()
    if settings.is_production and scheme != "https":
        raise _invalid_oauth_redirect_uri()
    if scheme == "http" and host not in _LOOPBACK_HTTP_HOSTS:
        raise _invalid_oauth_redirect_uri()

    netloc = _normalized_netloc(host, port)
    origin = f"{scheme}://{netloc}"
    return f"{origin}{OAUTH_CALLBACK_PATH}", origin


def _configured_oauth_redirect_uris(settings: Settings) -> set[str]:
    uris: set[str] = set()
    if settings.google_redirect_uri:
        configured_uri: str | None
        try:
            configured_uri, _origin = _parse_oauth_redirect_uri(settings.google_redirect_uri, settings)
        except AppError:
            configured_uri = None
        if configured_uri is not None:
            uris.add(configured_uri)
    for raw_origin in settings.allowed_origins:
        try:
            parsed = urlsplit(raw_origin.strip().rstrip("/"))
            scheme = parsed.scheme.lower()
            host = _normalized_loopback_host(parsed.hostname)
            port = parsed.port
        except Exception:  # noqa: BLE001
            continue
        if scheme not in {"http", "https"} or not parsed.netloc or host is None:
            continue
        if settings.is_production and scheme != "https":
            continue
        if scheme == "http" and host not in _LOOPBACK_HTTP_HOSTS:
            continue
        uris.add(f"{scheme}://{_normalized_netloc(host, port)}{OAUTH_CALLBACK_PATH}")
    return uris


def validate_oauth_redirect_uri(raw: str | None, settings: Settings) -> str:
    """Return the normalized OAuth callback URI or fail closed.

    The SPA JSON OAuth flow may override Google's redirect_uri, but only to a
    configured origin and only for the canonical FE callback path.
    """

    redirect_uri, _origin = _parse_oauth_redirect_uri(raw, settings)
    if redirect_uri not in _configured_oauth_redirect_uris(settings):
        raise _invalid_oauth_redirect_uri()
    return redirect_uri


def hash_oauth_transaction_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def oauth_transaction_token_matches(token: str | None, expected_hash: str | None) -> bool:
    if not token or not expected_hash:
        return False
    return secrets.compare_digest(hash_oauth_transaction_token(token), expected_hash)


def sanitize_return_to(raw: str | None, *, default: str = "/app") -> str:
    """Allow only local absolute paths for post-login redirects."""

    if raw is None or not str(raw).strip():
        return default
    value = str(raw).strip()
    previous = None
    decoded = value
    # Defend against encoded protocol-relative or traversal attempts.
    for _ in range(3):
        previous = decoded
        decoded = unquote(decoded)
        if decoded == previous:
            break
    if "\\" in decoded:
        raise AppError(status_code=400, component="auth", code="invalid_return_to", message="return_to is invalid")
    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc:
        raise AppError(status_code=400, component="auth", code="invalid_return_to", message="return_to must be a relative path")
    if not decoded.startswith("/") or decoded.startswith("//"):
        raise AppError(status_code=400, component="auth", code="invalid_return_to", message="return_to must start with a single /")
    parts = [part for part in parsed.path.split("/") if part]
    if any(part == ".." for part in parts):
        raise AppError(status_code=400, component="auth", code="invalid_return_to", message="return_to cannot traverse paths")
    return decoded


def set_session_cookie(response: Response, settings: Settings, session_id: str) -> None:
    response.set_cookie(
        key=settings.auth_session_cookie_name,
        value=session_id,
        max_age=settings.auth_session_absolute_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        domain=settings.auth_cookie_domain,
        path=settings.auth_cookie_path,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.auth_session_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        domain=settings.auth_cookie_domain,
        path=settings.auth_cookie_path,
    )


def set_oauth_transaction_cookie(response: Response, settings: Settings, transaction_token: str) -> None:
    response.set_cookie(
        key=OAUTH_TRANSACTION_COOKIE_NAME,
        value=transaction_token,
        max_age=settings.auth_state_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        domain=settings.auth_cookie_domain,
        path=OAUTH_TRANSACTION_COOKIE_PATH,
    )


def clear_oauth_transaction_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=OAUTH_TRANSACTION_COOKIE_NAME,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        domain=settings.auth_cookie_domain,
        path=OAUTH_TRANSACTION_COOKIE_PATH,
    )


def _origin_from_header(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _request_origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}".lower()


def allowed_request_origins(request: Request, settings: Settings) -> set[str]:
    origins = {_request_origin(request)}
    if settings.auth_public_backend_origin:
        origins.add(settings.auth_public_backend_origin.lower().rstrip("/"))
    origins.update(origin.lower().rstrip("/") for origin in settings.allowed_origins)
    return origins


def validate_unsafe_request_origin(request: Request, settings: Settings) -> None:
    """Fail closed for unsafe authenticated methods with bad/missing Origin/Referer."""

    header_origin = _origin_from_header(request.headers.get("origin"))
    header_referer = _origin_from_header(request.headers.get("referer"))
    candidate = header_origin or header_referer
    if candidate is None:
        raise AppError(
            status_code=403,
            component="auth",
            code="origin_required",
            message="Origin or Referer header is required for unsafe authenticated requests",
        )
    if candidate.lower().rstrip("/") not in allowed_request_origins(request, settings):
        raise AppError(
            status_code=403,
            component="auth",
            code="origin_not_allowed",
            message="Request origin is not allowed",
        )


def csrf_token_required(settings: Settings) -> bool:
    return settings.auth_csrf_required or settings.auth_cookie_samesite == "none"


def require_csrf_token(provided: str | None, expected: str | None) -> None:
    if not provided or not expected or not secrets.compare_digest(provided, expected):
        raise AppError(status_code=403, component="auth", code="csrf_invalid", message="CSRF token is invalid")


def public_user_payload(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user.get("id")),
        "name": user.get("name"),
        "email": user.get("email"),
        "provider": "google",
        "avatarUrl": user.get("avatar_url") or user.get("picture"),
    }
