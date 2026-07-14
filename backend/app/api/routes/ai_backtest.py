from __future__ import annotations
import hashlib
import hmac
from typing import Annotated

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from app.core.errors import AppError
from app.db.ai_backtest_repository import SqlAIBacktestRepository
from app.dependencies import get_db_engine, get_redis_client, get_runtime_settings
from app.schemas.ai_backtest import (
    AIBacktestErrorResponse,
    AIBacktestRunningResponse,
    AIBacktestExecutionContext,
    AICodeBacktestFlowRequest,
    AICodeBacktestFlowResult,
    AICodeBacktestPublicRequest,
)
from app.services.ai_backtest_flow import (
    AICodeBacktestService,
    REQUEST_FINGERPRINT_VERSION,
    build_request_fingerprint,
)
from app.services.ai_backtest_runtime import (
    AOAICodeGenerator,
    ASTCodeValidator,
    DeterministicBacktestReportGenerator,
    SandboxedBacktestExecutor,
)
from app.services.session_store import AuthSessionStore
from app.services.raw_audit_admission import issue_raw_audit_admission

_ERROR_CATALOG: dict[str, tuple[int, str]] = {
    "idempotency_key_required": (400, "Idempotency-Key is required."),
    "idempotency_key_invalid": (400, "Idempotency-Key is invalid."),
    "idempotency_key_reused": (409, "Idempotency-Key was previously used with different request content."),
    "duplicate_execution_active": (409, "An equivalent backtest request is already in progress."),
    "execution_outcome_unknown": (409, "Prior execution outcome is unresolved and cannot be retried automatically."),
    "terminal_evidence_required": (409, "Terminal evidence is required before this request can be resolved."),
    "request_validation_failed": (422, "Request validation failed."),
    "generated_code_rejected": (422, "Generated code was rejected before execution."),
    "code_generation_failed": (502, "Code generation failed."),
    "code_execution_failed": (502, "Code execution failed."),
    "service_unavailable": (503, "Backtest service is temporarily unavailable."),
    "code_execution_timeout": (504, "Code execution timed out."),
}
_SAFE_STATES = {
    "claimed",
    "generation_in_progress",
    "execution_armed",
    "execution_outcome_unknown",
    "execution_released",
    "abandoned",
}
_IDEMPOTENCY_KEY_PATTERN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-"


def _is_valid_idempotency_key(value: str) -> bool:
    return 8 <= len(value) <= 128 and all(character in _IDEMPOTENCY_KEY_PATTERN for character in value)


_ROUTE_ERROR_STATUSES = {400, 409, 422, 502, 503, 504}


def _safe_uuid(value: object) -> str | None:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _safe_details(code: str, details: object) -> dict[str, Any] | None:
    values = details if isinstance(details, dict) else {}
    safe: dict[str, Any] = {}
    allowed_ids = {
        "idempotency_key_reused": ("request_id",),
        "idempotency_key_required": (),
        "idempotency_key_invalid": (),
        "duplicate_execution_active": ("request_id", "trace_id"),
        "execution_outcome_unknown": ("request_id", "trace_id", "execution_run_id"),
        "terminal_evidence_required": ("request_id",),
        "generated_code_rejected": ("trace_id", "validation_id"),
        "code_generation_failed": ("trace_id",),
        "code_execution_failed": ("trace_id", "execution_run_id"),
        "service_unavailable": ("trace_id",),
        "code_execution_timeout": ("trace_id", "execution_run_id"),
    }
    for key in allowed_ids.get(code, ()):
        value = _safe_uuid(values.get(key))
        if value is not None:
            safe[key] = value

    if code in {"duplicate_execution_active", "execution_outcome_unknown", "terminal_evidence_required"}:
        state = values.get("state")
        if state in _SAFE_STATES:
            safe["state"] = state

    if code == "request_validation_failed":
        fields = values.get("fields")
        if isinstance(fields, list):
            safe["fields"] = [
                {"location": item["location"], "code": item["code"]}
                for item in fields
                if isinstance(item, dict)
                and item.get("location") in {"body", "cookie", "header", "path", "query", "request"}
                and isinstance(item.get("code"), str)
            ]

    return safe or None


def _backtest_error_response(code: str, details: object = None) -> JSONResponse:
    status_code, message = _ERROR_CATALOG[code]
    safe_details = _safe_details(code, details)
    trace_id = safe_details.get("trace_id") if safe_details is not None else None
    payload = AIBacktestErrorResponse(
        code=code,
        message=message,
        trace_id=trace_id,
        details=safe_details,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _project_app_error(exc: AppError) -> JSONResponse | None:
    code = exc.code
    if exc.status_code == 504 and code == "code_execution_failed":
        code = "code_execution_timeout"
    elif exc.status_code == 503:
        code = "service_unavailable"

    expected = _ERROR_CATALOG.get(code)
    if expected is None or expected[0] != exc.status_code:
        return None
    return _backtest_error_response(code, exc.details)


def _project_request_validation_error(exc: RequestValidationError) -> JSONResponse:
    fields: list[dict[str, str]] = []
    for error in exc.errors():
        location = "request"
        raw_location = error.get("loc")
        if isinstance(raw_location, (list, tuple)) and raw_location:
            candidate = str(raw_location[0])
            if candidate in {"body", "cookie", "header", "path", "query"}:
                location = candidate
        error_code = error.get("type")
        fields.append(
            {
                "location": location,
                "code": error_code if isinstance(error_code, str) and error_code else "invalid",
            }
        )
    return _backtest_error_response("request_validation_failed", {"fields": fields})


class AIBacktestRoute(APIRoute):
    """Keep backtest projections local without changing global error envelopes."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            try:
                return await route_handler(request)
            except RequestValidationError as exc:
                return _project_request_validation_error(exc)
            except AppError as exc:
                response = _project_app_error(exc)
                if response is not None:
                    return response
                if exc.status_code in _ROUTE_ERROR_STATUSES:
                    raise AppError(
                        status_code=exc.status_code,
                        component="ai_backtest",
                        code="backtest_request_failed",
                        message="Backtest request failed",
                    ) from exc
                raise

        return custom_route_handler


router = APIRouter(prefix="/ai/backtests", tags=["ai-backtest"], route_class=AIBacktestRoute)


def get_session_store(request: Request) -> AuthSessionStore:
    return AuthSessionStore(get_redis_client(request), get_runtime_settings(request))


async def get_authenticated_user_id(request: Request) -> int:
    settings = get_runtime_settings(request)
    session_store = get_session_store(request)
    session_id = request.cookies.get(settings.auth_session_cookie_name)
    user_id = await session_store.get_session_user_id(session_id)
    if not user_id:
        raise AppError(
            status_code=401,
            component="ai_backtest",
            code="not_authenticated",
            message="Authentication required",
        )
    try:
        return int(user_id)
    except ValueError as exc:
        raise AppError(
            status_code=401,
            component="ai_backtest",
            code="invalid_session_user_id",
            message="Session user id is invalid",
        ) from exc


async def get_authenticated_execution_context(request: Request) -> AIBacktestExecutionContext:
    settings = get_runtime_settings(request)
    session_store = get_session_store(request)
    session_id = request.cookies.get(settings.auth_session_cookie_name)
    context = await session_store.get_authenticated_session_context(session_id)
    if context is None:
        raise AppError(
            status_code=401,
            component="ai_backtest",
            code="not_authenticated",
            message="Authentication required",
        )
    secret = settings.ai_backtest_scope_hmac_primary
    version = settings.ai_backtest_scope_hmac_primary_version
    if secret is None or not version:
        raise AppError(
            status_code=503,
            component="ai_backtest",
            code="service_unavailable",
            message="Backtest service is unavailable",
        )
    session_hmac = hmac.new(
        secret.get_secret_value().encode("utf-8"),
        context.redis_session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return AIBacktestExecutionContext(
        user_id=context.user_id,
        scope_family_id=context.scope_family_id,
        session_hmac=session_hmac,
        session_hmac_version=version,
    )


def get_ai_backtest_service(request: Request) -> AICodeBacktestService:
    existing = getattr(request.app.state, "ai_backtest_service", None)
    if existing is not None:
        return existing
    repository = SqlAIBacktestRepository(get_db_engine(request))
    return AICodeBacktestService(
        repository=repository,
        code_generator=AOAICodeGenerator(),
        code_validator=ASTCodeValidator(),
        code_executor=SandboxedBacktestExecutor(),
        report_generator=DeterministicBacktestReportGenerator(),
        raw_audit_admission=issue_raw_audit_admission(get_runtime_settings(request)),
    )


@router.post(
    "/generate-and-run",
    response_model=AICodeBacktestFlowResult,
    responses={
        400: {"model": AIBacktestErrorResponse, "description": "Idempotency-Key is required and validated before execution."},
        202: {"model": AIBacktestRunningResponse, "description": "An equivalent request is still running."},
        409: {"model": AIBacktestErrorResponse, "description": "The request conflicts with an active or unresolved execution."},
        422: {"model": AIBacktestErrorResponse, "description": "The request or generated code was rejected."},
        502: {"model": AIBacktestErrorResponse, "description": "Code generation or execution failed."},
        503: {"model": AIBacktestErrorResponse, "description": "The backtest service is unavailable."},
        504: {"model": AIBacktestErrorResponse, "description": "Code execution timed out."},
    },
)
async def generate_and_run_backtest(
    request: Request,
    payload: AICodeBacktestPublicRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AICodeBacktestFlowResult | JSONResponse:
    if idempotency_key is None:
        return _backtest_error_response("idempotency_key_required")
    if not _is_valid_idempotency_key(idempotency_key):
        return _backtest_error_response("idempotency_key_invalid")
    execution_context = await get_authenticated_execution_context(request)
    service = get_ai_backtest_service(request)
    provisional_payload = AICodeBacktestFlowRequest(
        **payload.model_dump(),
        user_id=execution_context.user_id,
        execution_context=execution_context,
        idempotency_key=idempotency_key,
        fingerprint_version=REQUEST_FINGERPRINT_VERSION,
        request_fingerprint="0" * 64,
    )
    fingerprint_version, request_fingerprint = build_request_fingerprint(provisional_payload)
    bound_payload = provisional_payload.model_copy(
        update={
            "fingerprint_version": fingerprint_version,
            "request_fingerprint": request_fingerprint,
        }
    )
    result = await service.run_generated_backtest(bound_payload)

    if isinstance(result, AIBacktestRunningResponse):
        return JSONResponse(status_code=202, content=result.model_dump(mode="json"))
    if isinstance(result, AIBacktestErrorResponse):
        if result.code in _ERROR_CATALOG:
            return _backtest_error_response(result.code, result.details)
        raise AppError(
            status_code=500,
            component="ai_backtest",
            code="invalid_terminal_replay",
            message="Invalid terminal replay response",
        )
    return result