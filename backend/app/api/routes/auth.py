from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.errors import AppError
from app.core.runtime_perf import measure_span
from app.core.security import (
    OAUTH_TRANSACTION_COOKIE_NAME,
    clear_oauth_transaction_cookie,
    clear_session_cookie,
    csrf_token_required,
    generate_token_urlsafe,
    hash_oauth_transaction_token,
    oauth_transaction_token_matches,
    public_user_payload,
    require_csrf_token,
    sanitize_return_to,
    set_oauth_transaction_cookie,
    set_session_cookie,
    validate_oauth_redirect_uri,
    validate_unsafe_request_origin,
)
from app.db.user_queries import load_user_by_id, upsert_google_user
from app.dependencies import get_db_engine, get_redis_client, get_runtime_settings
from app.schemas.auth import AuthMeResponse, CsrfResponse, GoogleAuthCallbackRequest, GoogleAuthCallbackResponse
from app.services.google_oauth import build_google_authorization_url, exchange_authorization_code, validate_google_id_token
from app.services.session_store import AuthSessionStore

router = APIRouter(prefix="/auth", tags=["auth"])


def get_session_store(request: Request) -> AuthSessionStore:
    return AuthSessionStore(get_redis_client(request), get_runtime_settings(request))


def get_session_cookie(request: Request) -> str | None:
    settings = get_runtime_settings(request)
    return request.cookies.get(settings.auth_session_cookie_name)


@router.get("/google/start")
async def google_start(
    request: Request,
    return_to: str | None = Query(default="/app"),
    redirect_uri: str | None = Query(default=None),
    response_mode: str | None = Query(default=None),
) -> Response:
    settings = get_runtime_settings(request)
    store = get_session_store(request)
    safe_return_to = sanitize_return_to(return_to)
    state = generate_token_urlsafe(32)
    nonce = generate_token_urlsafe(32)

    if response_mode is not None and response_mode != "json":
        raise AppError(status_code=400, component="auth", code="unsupported_response_mode", message="response_mode is unsupported")
    json_response_requested = response_mode == "json" or redirect_uri is not None
    if json_response_requested:
        safe_redirect_uri = validate_oauth_redirect_uri(redirect_uri, settings)
        transaction_token = generate_token_urlsafe(32)
        await store.store_oauth_state(
            state=state,
            nonce=nonce,
            return_to=safe_return_to,
            redirect_uri=safe_redirect_uri,
            flow_mode="json",
            transaction_token_hash=hash_oauth_transaction_token(transaction_token),
        )
        response = JSONResponse(
            {"authorizationUrl": build_google_authorization_url(settings, state=state, nonce=nonce, redirect_uri=safe_redirect_uri)}
        )
        set_oauth_transaction_cookie(response, settings, transaction_token)
        return response

    await store.store_oauth_state(state=state, nonce=nonce, return_to=safe_return_to)
    return RedirectResponse(build_google_authorization_url(settings, state=state, nonce=nonce), status_code=307)


async def _complete_google_callback(request: Request, *, code: str, oauth_state: dict[str, object], redirect_uri: str | None = None) -> tuple[dict[str, object], str]:
    settings = get_runtime_settings(request)
    store = get_session_store(request)
    token_response = await exchange_authorization_code(settings, code=code, redirect_uri=redirect_uri)
    identity = await validate_google_id_token(
        settings,
        id_token=str(token_response["id_token"]),
        expected_nonce=str(oauth_state["nonce"]),
    )
    user = await upsert_google_user(get_db_engine(request), identity)
    session_id, _csrf_token = await store.create_session(user_id=str(user["id"]))
    return user, session_id


@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: str) -> RedirectResponse:
    settings = get_runtime_settings(request)
    store = get_session_store(request)
    oauth_state = await store.consume_oauth_state(state)
    _user, session_id = await _complete_google_callback(request, code=code, oauth_state=oauth_state)
    response = RedirectResponse(sanitize_return_to(str(oauth_state.get("return_to") or "/app")), status_code=303)
    set_session_cookie(response, settings, session_id)
    return response


@router.post("/google/callback", response_model=GoogleAuthCallbackResponse)
async def google_callback_json(request: Request, payload: GoogleAuthCallbackRequest) -> JSONResponse:
    settings = get_runtime_settings(request)
    validate_unsafe_request_origin(request, settings)
    safe_redirect_uri = validate_oauth_redirect_uri(payload.redirectUri, settings)
    transaction_token = request.cookies.get(OAUTH_TRANSACTION_COOKIE_NAME)
    if not transaction_token:
        raise AppError(status_code=401, component="auth", code="oauth_transaction_invalid", message="OAuth transaction is invalid or expired")

    store = get_session_store(request)
    oauth_state = await store.consume_oauth_state(payload.state)
    if oauth_state.get("flow_mode") != "json":
        raise AppError(status_code=401, component="auth", code="oauth_state_invalid", message="OAuth state is invalid or expired")
    if oauth_state.get("redirect_uri") != safe_redirect_uri:
        raise AppError(status_code=400, component="auth", code="redirect_uri_mismatch", message="OAuth redirect URI does not match stored state")
    expected_transaction_hash = oauth_state.get("transaction_token_hash")
    if not isinstance(expected_transaction_hash, str) or not oauth_transaction_token_matches(transaction_token, expected_transaction_hash):
        raise AppError(status_code=401, component="auth", code="oauth_transaction_invalid", message="OAuth transaction is invalid or expired")

    user, session_id = await _complete_google_callback(request, code=payload.code, oauth_state=oauth_state, redirect_uri=safe_redirect_uri)
    response = JSONResponse(
        {
            "session": {"user": public_user_payload(user)},
            "returnTo": sanitize_return_to(str(oauth_state.get("return_to") or "/app")),
        }
    )
    set_session_cookie(response, settings, session_id)
    clear_oauth_transaction_cookie(response, settings)
    return response


@router.get("/me", response_model=AuthMeResponse)
async def auth_me(request: Request) -> dict[str, object]:
    with measure_span("auth"):
        store = get_session_store(request)
        with measure_span("cookie_parse"):
            session_id = get_session_cookie(request)
        user_id = await store.get_session_user_id(session_id)
        if not user_id:
            raise AppError(status_code=401, component="auth", code="not_authenticated", message="Authentication required")
        with measure_span("userdb"):
            user = await load_user_by_id(get_db_engine(request), user_id)
        if not user:
            raise AppError(status_code=401, component="auth", code="user_session_invalid", message="Session user is unavailable")
        with measure_span("auth_mapping"):
            payload = {"user": public_user_payload(user)}
        return payload


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
