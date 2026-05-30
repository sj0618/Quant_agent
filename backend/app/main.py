from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, health, pages
from app.core.config import ConfigurationError, load_settings
from app.core.errors import AppError, register_exception_handlers
from app.db.session import create_db_engine, dispose_db_engine


def create_redis_client(redis_url: str | None):
    if not redis_url:
        return None
    try:
        from redis import asyncio as redis_asyncio
    except Exception as exc:  # pragma: no cover
        raise AppError(
            status_code=503,
            component="redis",
            code="redis_dependency_missing",
            message="redis package is required for auth/session state",
            details={"error": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return redis_asyncio.from_url(redis_url, decode_responses=True)


async def close_redis_client(client) -> None:
    if client is None:
        return
    close = getattr(client, "aclose", None) or getattr(client, "close", None)
    if close is not None:
        result = close()
        if hasattr(result, "__await__"):
            await result


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = None
    app.state.db_engine = None
    app.state.redis_client = None
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    try:
        settings = load_settings()
        app.state.settings = settings
        app.state.db_engine = create_db_engine(settings)
    except ConfigurationError as exc:
        app.state.startup_config_error = exc
    else:
        try:
            app.state.redis_client = create_redis_client(settings.redis_url_value)
        except AppError as exc:
            app.state.startup_redis_error = exc
    yield
    await close_redis_client(getattr(app.state, "redis_client", None))
    await dispose_db_engine(getattr(app.state, "db_engine", None))


def create_app() -> FastAPI:
    app = FastAPI(
        title="QuantAgent Backend API",
        version="0.1.0",
        description="Backend-owned production Google auth and simple same-origin UI surface.",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(pages.router)
    return app


app = create_app()
