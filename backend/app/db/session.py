from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings, redact_secrets
from app.core.errors import AppError


def create_db_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)


async def dispose_db_engine(engine: AsyncEngine | None) -> None:
    if engine is not None:
        await engine.dispose()


async def check_db(engine: AsyncEngine) -> dict[str, Any]:
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 AS ok"))
            value = result.scalar_one()
        return {"status": "ok", "check": "SELECT 1", "value": value}
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=503,
            component="db",
            code="db_unavailable",
            message="Database connectivity check failed",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        ) from exc


async def fetch_all(engine: AsyncEngine, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params or {})
            return [dict(row) for row in result.mappings().all()]
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=503,
            component="db",
            code="db_query_failed",
            message="Database query failed",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        ) from exc


async def fetch_one(engine: AsyncEngine, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = await fetch_all(engine, sql, params)
    return rows[0] if rows else None


async def execute_one(engine: AsyncEngine, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            row = result.mappings().first()
            return dict(row) if row is not None else None
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=503,
            component="db",
            code="db_query_failed",
            message="Database query failed",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        ) from exc


def rows_from_mappings(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
