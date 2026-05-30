from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import unquote, urlsplit

from fastapi import Request, Response

from app.core.config import Settings
from app.core.errors import AppError


def generate_token_urlsafe(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


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
        max_age=settings.auth_session_ttl_seconds,
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
