from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ApiEnvelope(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    trace_id: str
    debug_ref: str
    data: T | None = None
    error: ApiError | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


def success_envelope(
    *,
    trace_id: str,
    debug_ref: str,
    data: T,
    meta: dict[str, Any] | None = None,
) -> ApiEnvelope[T]:
    return ApiEnvelope[T](
        ok=True,
        trace_id=trace_id,
        debug_ref=debug_ref,
        data=data,
        meta=meta or {},
    )


def error_envelope(
    *,
    trace_id: str,
    debug_ref: str,
    code: str,
    message: str,
    meta: dict[str, Any] | None = None,
) -> ApiEnvelope[None]:
    return ApiEnvelope[None](
        ok=False,
        trace_id=trace_id,
        debug_ref=debug_ref,
        error=ApiError(code=code, message=message),
        meta=meta or {},
    )
