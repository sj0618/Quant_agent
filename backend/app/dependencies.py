from __future__ import annotations

from typing import Any

from fastapi import Request

from app.core.config import ConfigurationError, Settings, load_settings
from app.core.errors import AppError, config_app_error


def get_runtime_settings(request: Request) -> Settings:
    config_error = getattr(request.app.state, "startup_config_error", None)
    if config_error is not None:
        raise config_app_error(config_error)
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        try:
            settings = load_settings()
        except ConfigurationError as exc:
            raise config_app_error(exc) from exc
    return settings


def get_db_engine(request: Request) -> Any:
    engine = getattr(request.app.state, "db_engine", None)
    if engine is None:
        raise AppError(
            status_code=503,
            component="db",
            code="db_engine_unavailable",
            message="Database engine is not initialized",
        )
    return engine


def get_redis_client(request: Request) -> Any:
    startup_redis_error = getattr(request.app.state, "startup_redis_error", None)
    if startup_redis_error is not None:
        raise startup_redis_error
    client = getattr(request.app.state, "redis_client", None)
    if client is None:
        raise AppError(
            status_code=503,
            component="redis",
            code="redis_client_unavailable",
            message="Redis client is not initialized",
        )
    return client
