from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.errors import AppError
from app.core.security import (
    clear_session_cookie,
    csrf_token_required,
    generate_token_urlsafe,
    public_user_payload,
    require_csrf_token,
    sanitize_return_to,
    set_session_cookie,
    validate_unsafe_request_origin,
)
from app.db.user_queries import load_user_by_id, upsert_google_user
from app.dependencies import get_db_engine, get_redis_client, get_runtime_settings
from app.schemas.auth import AuthMeResponse, CsrfResponse
from app.services.google_oauth import build_google_authorization_url, exchange_authorization_code, validate_google_id_token
from app.services.session_store import AuthSessionStore

router = APIRouter(prefix="/auth", tags=["auth"])


def get_session_store(request: Request) -> AuthSessionStore:
    return AuthSessionStore(get_redis_client(request), get_runtime_settings(request))


def get_session_cookie(request: Request) -> str | None:
    settings = get_runtime_settings(request)
    return request.cookies.get(settings.auth_session_cookie_name)


@router.get("/google/start")
async def google_start(request: Request, return_to: str | None = Query(default="/app")) -> RedirectResponse:
    settings = get_runtime_settings(request)
    store = get_session_store(request)
    safe_return_to = sanitize_return_to(return_to)
    state = generate_token_urlsafe(32)
    nonce = generate_token_urlsafe(32)
    await store.store_oauth_state(state=state, nonce=nonce, return_to=safe_return_to)
    return RedirectResponse(build_google_authorization_url(settings, state=state, nonce=nonce), status_code=307)


@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: str) -> RedirectResponse:
    settings = get_runtime_settings(request)
    store = get_session_store(request)
    oauth_state = await store.consume_oauth_state(state)
    token_response = await exchange_authorization_code(settings, code=code)
    identity = await validate_google_id_token(
        settings,
        id_token=str(token_response["id_token"]),
        expected_nonce=str(oauth_state["nonce"]),
    )
    user = await upsert_google_user(get_db_engine(request), identity)
    session_id, _csrf_token = await store.create_session(user_id=str(user["id"]))
    response = RedirectResponse(sanitize_return_to(str(oauth_state.get("return_to") or "/app")), status_code=303)
    set_session_cookie(response, settings, session_id)
    return response


@router.get("/me", response_model=AuthMeResponse)
async def auth_me(request: Request) -> dict[str, object]:
    store = get_session_store(request)
    user_id = await store.get_session_user_id(get_session_cookie(request))
    if not user_id:
        raise AppError(status_code=401, component="auth", code="not_authenticated", message="Authentication required")
    user = await load_user_by_id(get_db_engine(request), user_id)
    if not user:
        raise AppError(status_code=401, component="auth", code="user_session_invalid", message="Session user is unavailable")
    return {"user": public_user_payload(user)}


@router.get("/csrf", response_model=CsrfResponse)
async def auth_csrf(request: Request) -> dict[str, str]:
    store = get_session_store(request)
    session_id = get_session_cookie(request)
    user_id = await store.get_session_user_id(session_id)
    if not user_id:
        raise AppError(status_code=401, component="auth", code="not_authenticated", message="Authentication required")
    token = await store.get_csrf_token(session_id)
    if not token:
        raise AppError(status_code=503, component="auth", code="csrf_unavailable", message="CSRF token is unavailable")
    return {"csrfToken": token}


@router.post("/logout")
async def auth_logout(request: Request) -> Response:
    settings = get_runtime_settings(request)
    validate_unsafe_request_origin(request, settings)
    store = get_session_store(request)
    session_id = get_session_cookie(request)
    if csrf_token_required(settings):
        require_csrf_token(request.headers.get("X-CSRF-Token"), await store.get_csrf_token(session_id))
    await store.revoke_session(session_id)
    response = Response(status_code=204)
    clear_session_cookie(response, settings)
    return response
