from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from threading import Lock
from typing import Any, Literal, Protocol, TypeAlias
from uuid import UUID, uuid4


AuditEventKind: TypeAlias = Literal["step", "error", "finalization"]
FinalizationStatus: TypeAlias = Literal["completed", "failed"]


@dataclass(frozen=True, slots=True)
class AuditCorrelation:
    db_trace_id: UUID
    trace_id: str | None
    debug_ref: str | None
    entrypoint: str
    feature: str
    strategy_id: str | None = None
    client_request_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class AuditEventBase:
    correlation: AuditCorrelation
    emitted_at: datetime


@dataclass(frozen=True, slots=True)
class StepAuditEvent(AuditEventBase):
    step: str
    message: str | None = None
    kind: Literal["step"] = field(init=False, default="step")


@dataclass(frozen=True, slots=True)
class ErrorAuditEvent(AuditEventBase):
    step: str
    error_type: str
    message: str
    call_id: UUID | None = None
    execution_id: UUID | None = None
    context_jsonb: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"
    kind: Literal["error"] = field(init=False, default="error")


@dataclass(frozen=True, slots=True)
class FinalizationAuditEvent(AuditEventBase):
    status: FinalizationStatus
    message: str | None = None
    metadata_jsonb: dict[str, Any] = field(default_factory=dict)
    kind: Literal["finalization"] = field(init=False, default="finalization")


AuditEvent: TypeAlias = StepAuditEvent | ErrorAuditEvent | FinalizationAuditEvent


@dataclass(slots=True)
class AgentExecutionAuditRecord:
    execution_id: UUID
    trace_id: UUID
    agent_name: str
    step_name: str
    status: str
    input_jsonb: dict[str, Any]
    output_jsonb: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    latency_ms: float | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None


@dataclass(slots=True)
class ModelCallAuditRecord:
    call_id: UUID
    trace_id: UUID
    execution_id: UUID | None
    task_type: str
    provider: str
    model_name: str | None
    temperature: float | None
    response_schema_name: str | None
    web_search_used: bool
    status: str = "running"
    provider_request_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None
    retry_count: int = 0
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class PromptAuditRecord:
    prompt_log_id: UUID
    call_id: UUID
    prompt_template_name: str | None
    system_prompt: str
    user_prompt: str
    assistant_response: str | None
    variables_jsonb: dict[str, Any]
    prompt_version: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AuditSession(Protocol):
    correlation: AuditCorrelation

    @property
    def buffered_events(self) -> Sequence[AuditEvent]: ...

    def record_step(
        self,
        step: str,
        *,
        message: str | None = None,
        emitted_at: datetime | None = None,
    ) -> StepAuditEvent: ...

    def record_error(
        self,
        step: str,
        *,
        error_type: str,
        message: str,
        call_id: UUID | None = None,
        execution_id: UUID | None = None,
        context_jsonb: Mapping[str, Any] | None = None,
        severity: str = "error",
        emitted_at: datetime | None = None,
    ) -> ErrorAuditEvent: ...

    def record_finalization(
        self,
        status: FinalizationStatus,
        *,
        message: str | None = None,
        metadata_jsonb: Mapping[str, Any] | None = None,
        emitted_at: datetime | None = None,
    ) -> FinalizationAuditEvent: ...

    def start_agent_execution(
        self,
        agent_name: str,
        *,
        step_name: str,
        input_jsonb: Mapping[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> UUID: ...

    def finish_agent_execution(
        self,
        execution_id: UUID,
        *,
        status: Literal["succeeded", "failed"],
        output_jsonb: Mapping[str, Any] | None = None,
        error_message: str | None = None,
        latency_ms: float | None = None,
        ended_at: datetime | None = None,
    ) -> None: ...

    def start_model_call(
        self,
        *,
        task_type: str,
        provider: str,
        model_name: str | None,
        system_prompt: str,
        user_prompt: str,
        variables_jsonb: Mapping[str, Any],
        prompt_template_name: str | None,
        prompt_version: str | None,
        temperature: float | None,
        response_schema_name: str | None,
        web_search_used: bool,
        execution_id: UUID | None,
        created_at: datetime | None = None,
    ) -> UUID: ...

    def finish_model_call(
        self,
        call_id: UUID,
        *,
        status: Literal["succeeded", "failed"],
        assistant_response: str | None,
        provider_request_id: str | None = None,
        model_name: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_ms: float | None = None,
        retry_count: int = 0,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None: ...


class AuditSink(Protocol):
    def open_session(self, correlation: AuditCorrelation) -> AuditSession: ...


@dataclass(slots=True)
class NoOpAuditSession:
    correlation: AuditCorrelation

    @property
    def buffered_events(self) -> tuple[AuditEvent, ...]:
        return ()

    def record_step(
        self,
        step: str,
        *,
        message: str | None = None,
        emitted_at: datetime | None = None,
    ) -> StepAuditEvent:
        return StepAuditEvent(self.correlation, _timestamp(emitted_at), step, message)

    def record_error(
        self,
        step: str,
        *,
        error_type: str,
        message: str,
        call_id: UUID | None = None,
        execution_id: UUID | None = None,
        context_jsonb: Mapping[str, Any] | None = None,
        severity: str = "error",
        emitted_at: datetime | None = None,
    ) -> ErrorAuditEvent:
        return ErrorAuditEvent(
            self.correlation,
            _timestamp(emitted_at),
            step,
            error_type,
            message,
            call_id,
            execution_id,
            dict(context_jsonb or {}),
            severity,
        )

    def record_finalization(
        self,
        status: FinalizationStatus,
        *,
        message: str | None = None,
        metadata_jsonb: Mapping[str, Any] | None = None,
        emitted_at: datetime | None = None,
    ) -> FinalizationAuditEvent:
        return FinalizationAuditEvent(
            self.correlation,
            _timestamp(emitted_at),
            status,
            message,
            dict(metadata_jsonb or {}),
        )

    def start_agent_execution(
        self,
        agent_name: str,
        *,
        step_name: str,
        input_jsonb: Mapping[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> UUID:
        return uuid4()

    def finish_agent_execution(
        self,
        execution_id: UUID,
        *,
        status: Literal["succeeded", "failed"],
        output_jsonb: Mapping[str, Any] | None = None,
        error_message: str | None = None,
        latency_ms: float | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        return None

    def start_model_call(
        self,
        *,
        task_type: str,
        provider: str,
        model_name: str | None,
        system_prompt: str,
        user_prompt: str,
        variables_jsonb: Mapping[str, Any],
        prompt_template_name: str | None,
        prompt_version: str | None,
        temperature: float | None,
        response_schema_name: str | None,
        web_search_used: bool,
        execution_id: UUID | None,
        created_at: datetime | None = None,
    ) -> UUID:
        return uuid4()

    def finish_model_call(
        self,
        call_id: UUID,
        *,
        status: Literal["succeeded", "failed"],
        assistant_response: str | None,
        provider_request_id: str | None = None,
        model_name: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_ms: float | None = None,
        retry_count: int = 0,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        return None


@dataclass(slots=True)
class NoOpAuditSink:
    def open_session(self, correlation: AuditCorrelation) -> NoOpAuditSession:
        return NoOpAuditSession(correlation)


@dataclass(slots=True)
class RecordingAuditSession(NoOpAuditSession):
    _buffer: list[AuditEvent] = field(default_factory=list)
    _agent_executions: dict[UUID, AgentExecutionAuditRecord] = field(default_factory=dict)
    _model_calls: dict[UUID, ModelCallAuditRecord] = field(default_factory=dict)
    _prompt_logs: dict[UUID, PromptAuditRecord] = field(default_factory=dict)

    @property
    def buffered_events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._buffer)

    @property
    def agent_executions(self) -> tuple[AgentExecutionAuditRecord, ...]:
        return tuple(self._agent_executions.values())

    @property
    def model_calls(self) -> tuple[ModelCallAuditRecord, ...]:
        return tuple(self._model_calls.values())

    @property
    def prompt_logs(self) -> tuple[PromptAuditRecord, ...]:
        return tuple(self._prompt_logs.values())

    def record_step(self, *args: Any, **kwargs: Any) -> StepAuditEvent:
        event = NoOpAuditSession.record_step(self, *args, **kwargs)
        self._buffer.append(event)
        return event

    def record_error(self, *args: Any, **kwargs: Any) -> ErrorAuditEvent:
        event = NoOpAuditSession.record_error(self, *args, **kwargs)
        self._buffer.append(event)
        return event

    def record_finalization(self, *args: Any, **kwargs: Any) -> FinalizationAuditEvent:
        event = NoOpAuditSession.record_finalization(self, *args, **kwargs)
        self._buffer.append(event)
        return event

    def start_agent_execution(
        self,
        agent_name: str,
        *,
        step_name: str,
        input_jsonb: Mapping[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> UUID:
        execution_id = uuid4()
        self._agent_executions[execution_id] = AgentExecutionAuditRecord(
            execution_id=execution_id,
            trace_id=self.correlation.db_trace_id,
            agent_name=agent_name,
            step_name=step_name,
            status="running",
            input_jsonb=dict(input_jsonb or {}),
            started_at=_timestamp(started_at),
        )
        return execution_id

    def finish_agent_execution(
        self,
        execution_id: UUID,
        *,
        status: Literal["succeeded", "failed"],
        output_jsonb: Mapping[str, Any] | None = None,
        error_message: str | None = None,
        latency_ms: float | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        record = self._agent_executions[execution_id]
        record.status = status
        record.output_jsonb = dict(output_jsonb or {})
        record.error_message = error_message
        record.latency_ms = latency_ms
        record.ended_at = _timestamp(ended_at)

    def start_model_call(
        self,
        *,
        task_type: str,
        provider: str,
        model_name: str | None,
        system_prompt: str,
        user_prompt: str,
        variables_jsonb: Mapping[str, Any],
        prompt_template_name: str | None,
        prompt_version: str | None,
        temperature: float | None,
        response_schema_name: str | None,
        web_search_used: bool,
        execution_id: UUID | None,
        created_at: datetime | None = None,
    ) -> UUID:
        call_id = uuid4()
        timestamp = _timestamp(created_at)
        self._model_calls[call_id] = ModelCallAuditRecord(
            call_id=call_id,
            trace_id=self.correlation.db_trace_id,
            execution_id=execution_id,
            task_type=task_type,
            provider=provider,
            model_name=model_name,
            temperature=temperature,
            response_schema_name=response_schema_name,
            web_search_used=web_search_used,
            created_at=timestamp,
        )
        self._prompt_logs[call_id] = PromptAuditRecord(
            prompt_log_id=uuid4(),
            call_id=call_id,
            prompt_template_name=prompt_template_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            assistant_response=None,
            variables_jsonb=dict(variables_jsonb),
            prompt_version=prompt_version,
            created_at=timestamp,
        )
        return call_id

    def finish_model_call(
        self,
        call_id: UUID,
        *,
        status: Literal["succeeded", "failed"],
        assistant_response: str | None,
        provider_request_id: str | None = None,
        model_name: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_ms: float | None = None,
        retry_count: int = 0,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        record = self._model_calls[call_id]
        record.status = status
        record.provider_request_id = provider_request_id
        record.model_name = model_name or record.model_name
        record.prompt_tokens = prompt_tokens
        record.completion_tokens = completion_tokens
        record.total_tokens = total_tokens
        record.latency_ms = latency_ms
        record.retry_count = retry_count
        record.error_message = error_message
        self._prompt_logs[call_id].assistant_response = assistant_response
        if status == "failed" and error_type:
            self.record_error(
                "model_call",
                error_type=error_type,
                message=error_message or "model call failed",
                call_id=call_id,
                execution_id=record.execution_id,
            )


@dataclass(slots=True)
class RecordingAuditSink:
    _sessions: list[RecordingAuditSession] = field(default_factory=list)

    @property
    def sessions(self) -> tuple[RecordingAuditSession, ...]:
        return tuple(self._sessions)

    @property
    def buffered_events(self) -> tuple[AuditEvent, ...]:
        return tuple(event for session in self._sessions for event in session.buffered_events)

    def open_session(self, correlation: AuditCorrelation) -> RecordingAuditSession:
        session = RecordingAuditSession(correlation)
        self._sessions.append(session)
        return session


_ACTIVE_AUDIT_SESSION: ContextVar[AuditSession | None] = ContextVar(
    "active_audit_session", default=None
)
_ACTIVE_EXECUTION_ID: ContextVar[UUID | None] = ContextVar("active_execution_id", default=None)
_FAILURE_COUNT = 0
_FAILURE_COUNT_LOCK = Lock()


@contextmanager
def bind_audit_context(
    session: AuditSession,
    execution_id: UUID | None = None,
) -> Iterator[None]:
    session_token = _ACTIVE_AUDIT_SESSION.set(session)
    execution_token = _ACTIVE_EXECUTION_ID.set(execution_id)
    try:
        yield
    finally:
        _ACTIVE_EXECUTION_ID.reset(execution_token)
        _ACTIVE_AUDIT_SESSION.reset(session_token)


def active_audit_session() -> AuditSession | None:
    return _ACTIVE_AUDIT_SESSION.get()


def active_execution_id() -> UUID | None:
    return _ACTIVE_EXECUTION_ID.get()


def begin_model_call(
    *,
    task_type: str,
    provider: str,
    model_name: str | None,
    system_prompt: str,
    user_prompt: str,
    variables_jsonb: Mapping[str, Any],
    prompt_template_name: str | None,
    prompt_version: str | None,
    temperature: float | None,
    response_schema_name: str | None,
    web_search_used: bool,
) -> UUID | None:
    session = active_audit_session()
    if session is None:
        return None
    try:
        return session.start_model_call(
            task_type=task_type,
            provider=provider,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            variables_jsonb=_json_value(variables_jsonb),
            prompt_template_name=prompt_template_name,
            prompt_version=prompt_version,
            temperature=temperature,
            response_schema_name=response_schema_name,
            web_search_used=web_search_used,
            execution_id=active_execution_id(),
        )
    except Exception:
        report_audit_failure("start_model_call")
        return None


def finish_model_call(call_id: UUID | None, **values: Any) -> None:
    if call_id is None:
        return
    session = active_audit_session()
    if session is None:
        return
    try:
        session.finish_model_call(call_id, **values)
    except Exception:
        report_audit_failure("finish_model_call")


def audit_failure_count() -> int:
    with _FAILURE_COUNT_LOCK:
        return _FAILURE_COUNT


def report_audit_failure(operation: str) -> None:
    global _FAILURE_COUNT
    with _FAILURE_COUNT_LOCK:
        _FAILURE_COUNT += 1
    payload = {
        "event": "ai_audit_failure",
        "operation": operation[:64],
    }
    try:
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True), file=sys.stderr)
    except Exception:  # noqa: BLE001 - reporting failure must remain fail-open
        return


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not valid audit JSON")
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("audit JSON object keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise TypeError(f"unsupported audit JSON value: {type(value).__name__}")


def new_db_trace_id() -> UUID:
    return uuid4()


def create_audit_correlation(
    *,
    trace_id: str | None,
    debug_ref: str | None,
    entrypoint: str,
    feature: str,
    strategy_id: str | None = None,
    client_request_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    db_trace_id: UUID | None = None,
) -> AuditCorrelation:
    return AuditCorrelation(
        db_trace_id=db_trace_id or new_db_trace_id(),
        trace_id=trace_id,
        debug_ref=debug_ref,
        entrypoint=entrypoint,
        feature=feature,
        strategy_id=strategy_id,
        client_request_id=client_request_id,
        user_id=user_id,
        session_id=session_id,
    )


def _timestamp(value: datetime | None) -> datetime:
    return value if value is not None else datetime.now(UTC)


__all__ = [
    "AgentExecutionAuditRecord",
    "AuditCorrelation",
    "AuditEvent",
    "AuditEventBase",
    "AuditEventKind",
    "AuditSession",
    "AuditSink",
    "ErrorAuditEvent",
    "FinalizationAuditEvent",
    "FinalizationStatus",
    "ModelCallAuditRecord",
    "NoOpAuditSession",
    "NoOpAuditSink",
    "PromptAuditRecord",
    "RecordingAuditSession",
    "RecordingAuditSink",
    "StepAuditEvent",
    "active_audit_session",
    "active_execution_id",
    "audit_failure_count",
    "begin_model_call",
    "bind_audit_context",
    "create_audit_correlation",
    "finish_model_call",
    "new_db_trace_id",
    "report_audit_failure",
]
