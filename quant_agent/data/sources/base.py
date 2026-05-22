"""Common source-client helpers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import time
from typing import Any, Callable, TypeVar

from quant_agent.data.config import RetryConfig

T = TypeVar("T")


class SourceConfigurationError(RuntimeError):
    """Raised when a source client cannot run due to missing runtime config."""


class SourceResponseError(RuntimeError):
    """Raised when a source returns an unusable response."""


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "nan", "NaN", "None"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def retry_call(fn: Callable[[], T], retry: RetryConfig) -> T:
    last_error: Exception | None = None
    for attempt in range(1, retry.attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - preserve final source error context
            last_error = exc
            if attempt >= retry.attempts:
                break
            time.sleep(retry.backoff_seconds * attempt)
    assert last_error is not None
    raise last_error

