from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.errors import AppError
from app.db.ai_backtest_repository import SqlAIBacktestRepository
from app.dependencies import get_db_engine, get_redis_client, get_runtime_settings
from app.schemas.ai_backtest import AICodeBacktestFlowRequest, AICodeBacktestFlowResult
from app.services.ai_backtest_flow import AICodeBacktestService
from app.services.ai_backtest_runtime import (
    AOAICodeGenerator,
    ASTCodeValidator,
    DeterministicBacktestReportGenerator,
    SandboxedBacktestExecutor,
)
from app.services.session_store import AuthSessionStore

router = APIRouter(prefix="/ai/backtests", tags=["ai-backtest"])


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
    )


@router.post("/generate-and-run", response_model=AICodeBacktestFlowResult)
async def generate_and_run_backtest(request: Request, payload: AICodeBacktestFlowRequest) -> AICodeBacktestFlowResult:
    user_id = await get_authenticated_user_id(request)
    service = get_ai_backtest_service(request)
    bound_payload = payload.model_copy(update={"user_id": user_id})
    return await service.run_generated_backtest(bound_payload)
