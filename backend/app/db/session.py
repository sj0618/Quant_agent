from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core.config import Settings, redact_secrets
from app.core.errors import AppError
from app.core.runtime_perf import (
    measure_report_database_span,
    record_report_database_duration,
    record_report_database_elapsed,
    start_report_database_timer,
)


def _sql_params_with_bigint_user_id(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    effective_params = dict(params or {})
    if "user_id" not in effective_params:
        return effective_params
    if "cast(:user_id as bigint)" not in sql.lower():
        return effective_params
    user_id_value = effective_params["user_id"]
    if isinstance(user_id_value, int):
        return effective_params
    effective_params["user_id"] = int(str(user_id_value).strip())
    return effective_params


def create_db_engine_from_url(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_db_engine(settings: Settings) -> AsyncEngine:
    return create_db_engine_from_url(settings.sqlalchemy_database_url)


def create_trading_data_db_engine(settings: Settings) -> AsyncEngine | None:
    database_url = getattr(settings, "trading_data_sqlalchemy_database_url", None)
    if not database_url:
        return None
    return create_db_engine_from_url(database_url)


async def dispose_db_engine(engine: AsyncEngine | None) -> None:
    if engine is not None:
        await engine.dispose()


def _is_active_connection(handle: Any) -> bool:
    return isinstance(handle, AsyncConnection) or not hasattr(handle, "connect")


@asynccontextmanager
async def _connection_for_handle(handle: Any):
    if _is_active_connection(handle):
        record_report_database_duration("dbacquire", 0.0)
        yield handle
        return
    started = start_report_database_timer()
    async with handle.connect() as conn:
        record_report_database_elapsed("dbacquire", started)
        yield conn


async def check_db(engine: Any) -> dict[str, Any]:
    try:
        async with _connection_for_handle(engine) as conn:
            result = await conn.execute(text("SELECT 1 AS ok"))
            value = result.scalar_one()
        return {"status": "ok", "check": "SELECT 1", "value": value}
    except Exception as exc:
        raise AppError(
            status_code=503,
            component="db",
            code="db_unavailable",
            message="Database connectivity check failed",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        ) from exc


async def fetch_all(engine: Any, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        effective_params = _sql_params_with_bigint_user_id(sql, params)
        async with _connection_for_handle(engine) as conn:
            with measure_report_database_span("query"):
                result = await conn.execute(text(sql), effective_params)
            with measure_report_database_span("fetch"):
                return [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        raise AppError(
            status_code=503,
            component="db",
            code="db_query_failed",
            message="Database query failed",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        ) from exc


async def fetch_one(engine: Any, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = await fetch_all(engine, sql, params)
    return rows[0] if rows else None


async def execute_one(engine: Any, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        effective_params = _sql_params_with_bigint_user_id(sql, params)
        if _is_active_connection(engine):
            result = await engine.execute(text(sql), effective_params)
            row = result.mappings().first()
            return dict(row) if row is not None else None
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), effective_params)
            row = result.mappings().first()
            return dict(row) if row is not None else None
    except Exception as exc:
        raise AppError(
            status_code=503,
            component="db",
            code="db_query_failed",
            message="Database query failed",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        ) from exc

