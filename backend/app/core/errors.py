from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.config import ConfigurationError, redact_secrets


class AppError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        component: str,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.component = component
        self.code = code
        self.message = message
        self.details = redact_secrets(details or {})

    def payload(self) -> dict[str, Any]:
        return {
            "error": {
                "component": self.component,
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


def config_app_error(error: ConfigurationError) -> AppError:
    return AppError(
        status_code=503,
        component="config",
        code="invalid_config",
        message=str(error),
        details=error.details,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.payload())

    @app.exception_handler(ConfigurationError)
    async def handle_config_error(_: Request, exc: ConfigurationError) -> JSONResponse:
        app_error = config_app_error(exc)
        return JSONResponse(status_code=app_error.status_code, content=app_error.payload())

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        app_error = AppError(
            status_code=422,
            component="api",
            code="request_validation_failed",
            message="Request validation failed",
            details=exc.errors(),
        )
        return JSONResponse(status_code=app_error.status_code, content=app_error.payload())

    @app.exception_handler(ValidationError)
    async def handle_pydantic_validation(_: Request, exc: ValidationError) -> JSONResponse:
        app_error = AppError(
            status_code=422,
            component="api",
            code="payload_validation_failed",
            message="Payload validation failed",
            details=exc.errors(include_url=False),
        )
        return JSONResponse(status_code=app_error.status_code, content=app_error.payload())
