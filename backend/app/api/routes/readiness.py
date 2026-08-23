from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict

from app.core.errors import AppError
from app.db.session import check_db
from app.dependencies import get_db_engine, get_redis_client, get_runtime_settings, get_trading_data_engine

router = APIRouter(tags=["readiness"])
ReadinessCheckName = Literal["auth_runtime", "main_db", "trading_data_db", "redis"]


class ReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ReadinessCheckName
    ready: bool
    reason: str | None = None


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "unavailable"]
    checks: list[ReadinessCheck]


def _ready(name: ReadinessCheckName) -> ReadinessCheck:
    return ReadinessCheck(name=name, ready=True)


def _not_ready(name: ReadinessCheckName, reason: str) -> ReadinessCheck:
    return ReadinessCheck(name=name, ready=False, reason=reason)


async def _auth_runtime_check(request: Request) -> ReadinessCheck:
    try:
        settings = get_runtime_settings(request)
    except AppError as exc:
        return _not_ready("auth_runtime", exc.code)
    if not getattr(settings, "auth_enabled", False):
        return _not_ready("auth_runtime", "auth_disabled")
    return _ready("auth_runtime")


async def _main_db_check(request: Request) -> ReadinessCheck:
    try:
        engine = get_db_engine(request)
    except AppError as exc:
        return _not_ready("main_db", exc.code)
    try:
        await check_db(engine)
    except AppError as exc:
        return _not_ready("main_db", exc.code)
    return _ready("main_db")


async def _trading_data_db_check(request: Request) -> ReadinessCheck:
    try:
        engine = get_trading_data_engine(request)
    except AppError as exc:
        reason = "trading_data_db_required" if exc.code == "trading_data_not_configured" else exc.code
        return _not_ready("trading_data_db", reason)
    if engine is None:
        return _not_ready("trading_data_db", "trading_data_db_required")
    try:
        await check_db(engine)
    except AppError as exc:
        return _not_ready("trading_data_db", exc.code)
    return _ready("trading_data_db")


async def _redis_check(request: Request) -> ReadinessCheck:
    try:
        client = get_redis_client(request)
    except AppError as exc:
        return _not_ready("redis", exc.code)
    try:
        ping = getattr(client, "ping", None)
        if callable(ping):
            result = ping()
        else:
            result = client.get("__readiness__")
        if hasattr(result, "__await__"):
            await result
    except Exception:  # noqa: BLE001 - readiness must not leak dependency internals.
        return _not_ready("redis", "redis_unavailable")
    return _ready("redis")


@router.get(
    "/readiness",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(request: Request, response: Response) -> ReadinessResponse:
    checks = [
        await _auth_runtime_check(request),
        await _main_db_check(request),
        await _trading_data_db_check(request),
        await _redis_check(request),
    ]
    result = ReadinessResponse(
        status="ready" if all(check.ready for check in checks) else "unavailable",
        checks=checks,
    )
    if result.status == "unavailable":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
