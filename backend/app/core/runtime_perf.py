from __future__ import annotations

import json
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Iterator
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders

logger = logging.getLogger("uvicorn.error.runtime_perf")

_REQUEST_ID_PATTERN = re.compile(r"^trace-[a-f0-9]{12}4[a-f0-9]{3}[89ab][a-f0-9]{15}$")
_REPORT_DETAIL_PATTERN = re.compile(r"^/api/v1/reports/[^/]+$")
_SERVER_TIMING_ORDER = (
    "total",
    "auth",
    "redis",
    "userdb",
    "dbacquire",
    "query",
    "fetch",
    "mapping",
    "response",
)
_LOG_SPAN_NAMES = frozenset(
    {
        *_SERVER_TIMING_ORDER,
        "cookie_parse",
        "session_decode",
        "auth_mapping",
    }
)


@dataclass
class RuntimePerformanceCollector:
    request_id: str
    method: str
    route: str
    spans_ms: dict[str, float] = field(default_factory=dict)
    row_count: int | None = None
    has_more: bool | None = None


_current_collector: ContextVar[RuntimePerformanceCollector | None] = ContextVar(
    "runtime_performance_collector",
    default=None,
)
_report_database_phase: ContextVar[bool] = ContextVar("runtime_performance_report_database_phase", default=False)


def _target_route(method: str, path: str) -> str | None:
    if method != "GET":
        return None
    if path == "/api/v1/auth/me":
        return "/api/v1/auth/me"
    if path == "/api/v1/reports":
        return "/api/v1/reports"
    if _REPORT_DETAIL_PATTERN.fullmatch(path):
        return "/api/v1/reports/{report_id}"
    return None


def _safe_request_id(candidate: str | None) -> str:
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return f"trace-{uuid4().hex}"


def _now() -> float | None:
    try:
        return perf_counter()
    except Exception:  # pragma: no cover - defensive instrumentation boundary
        return None


def _record_duration(name: str, duration_ms: float) -> None:
    try:
        collector = _current_collector.get()
        if collector is None or name not in _LOG_SPAN_NAMES:
            return
        safe_duration = max(0.0, float(duration_ms))
        collector.spans_ms[name] = collector.spans_ms.get(name, 0.0) + safe_duration
    except Exception:  # pragma: no cover - diagnostics must not affect requests
        return


@contextmanager
def measure_span(name: str) -> Iterator[None]:
    try:
        active = _current_collector.get() is not None and name in _LOG_SPAN_NAMES
    except Exception:  # pragma: no cover
        active = False
    if not active:
        yield
        return
    started = _now()
    try:
        yield
    finally:
        ended = _now()
        if started is not None and ended is not None:
            _record_duration(name, (ended - started) * 1000.0)


@contextmanager
def report_database_phase() -> Iterator[None]:
    try:
        active = _current_collector.get() is not None
    except Exception:  # pragma: no cover
        active = False
    if not active:
        yield
        return
    token = None
    try:
        token = _report_database_phase.set(True)
    except Exception:  # pragma: no cover - diagnostics must not affect requests
        pass
    try:
        yield
    finally:
        if token is not None:
            try:
                _report_database_phase.reset(token)
            except Exception:  # pragma: no cover
                pass


@contextmanager
def measure_report_database_span(name: str) -> Iterator[None]:
    try:
        enabled = _report_database_phase.get()
    except Exception:  # pragma: no cover
        enabled = False
    if not enabled:
        yield
        return
    with measure_span(name):
        yield


def record_report_database_duration(name: str, duration_ms: float) -> None:
    try:
        if _report_database_phase.get():
            _record_duration(name, duration_ms)
    except Exception:  # pragma: no cover
        return


def start_report_database_timer() -> float | None:
    try:
        return _now() if _report_database_phase.get() else None
    except Exception:  # pragma: no cover
        return None


def record_report_database_elapsed(name: str, started: float | None) -> None:
    ended = _now()
    if started is not None and ended is not None:
        record_report_database_duration(name, (ended - started) * 1000.0)


def set_report_metadata(*, row_count: int | None = None, has_more: bool | None = None) -> None:
    try:
        collector = _current_collector.get()
        if collector is None:
            return
        if row_count is not None:
            collector.row_count = max(0, int(row_count))
        if has_more is not None:
            collector.has_more = bool(has_more)
    except Exception:  # pragma: no cover
        return


def _server_timing_value(collector: RuntimePerformanceCollector) -> str:
    values = []
    for name in _SERVER_TIMING_ORDER:
        duration = collector.spans_ms.get(name)
        if duration is not None:
            values.append(f"{name};dur={duration:.3f}")
    return ", ".join(values)


def _log_collector(collector: RuntimePerformanceCollector, status_code: int) -> None:
    try:
        ordered_spans = {
            name: round(collector.spans_ms[name], 3)
            for name in sorted(collector.spans_ms)
            if name in _LOG_SPAN_NAMES
        }
        logger.info(
            "event=runtime_perf request_id=%s method=%s route=%s status=%d spans_ms=%s row_count=%s has_more=%s",
            collector.request_id,
            collector.method,
            collector.route,
            int(status_code),
            json.dumps(ordered_spans, separators=(",", ":"), sort_keys=True),
            collector.row_count if collector.row_count is not None else "na",
            str(collector.has_more).lower() if collector.has_more is not None else "na",
        )
    except Exception:  # pragma: no cover
        return


class RuntimePerformanceMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        try:
            app = scope.get("app")
            settings = getattr(getattr(app, "state", None), "settings", None)
            enabled = bool(getattr(settings, "perf_diagnostics_enabled", False))
            method = str(scope.get("method", ""))
            route = _target_route(method, str(scope.get("path", "")))
        except Exception:
            enabled = False
            route = None

        if not enabled or route is None:
            await self.app(scope, receive, send)
            return

        try:
            incoming_request_id = Headers(scope=scope).get("x-request-id")
        except Exception:
            incoming_request_id = None
        try:
            collector = RuntimePerformanceCollector(
                request_id=_safe_request_id(incoming_request_id),
                method=method,
                route=route,
            )
            token = _current_collector.set(collector)
            started = _now()
        except Exception:  # pragma: no cover
            await self.app(scope, receive, send)
            return
        status_code = 500

        async def send_with_diagnostics(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                try:
                    status_code = int(message.get("status", 500))
                    ended = _now()
                    if started is not None and ended is not None:
                        _record_duration("total", (ended - started) * 1000.0)
                    headers = MutableHeaders(scope=message)
                    headers["X-Request-ID"] = collector.request_id
                    server_timing = _server_timing_value(collector)
                    if server_timing:
                        headers["Server-Timing"] = server_timing
                except Exception:  # pragma: no cover
                    pass
            await send(message)

        try:
            await self.app(scope, receive, send_with_diagnostics)
        finally:
            if "total" not in collector.spans_ms:
                ended = _now()
                if started is not None and ended is not None:
                    _record_duration("total", (ended - started) * 1000.0)
            _log_collector(collector, status_code)
            try:
                _current_collector.reset(token)
            except Exception:  # pragma: no cover
                pass


def install_runtime_performance_middleware(app: Any) -> None:
    app.add_middleware(RuntimePerformanceMiddleware)
