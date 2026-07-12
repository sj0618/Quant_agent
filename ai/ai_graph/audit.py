from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol, TypeAlias
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
    kind: Literal["error"] = field(init=False, default="error")


@dataclass(frozen=True, slots=True)
class FinalizationAuditEvent(AuditEventBase):
    status: FinalizationStatus
    message: str | None = None
    kind: Literal["finalization"] = field(init=False, default="finalization")


AuditEvent: TypeAlias = StepAuditEvent | ErrorAuditEvent | FinalizationAuditEvent


class AuditSession(Protocol):
    correlation: AuditCorrelation

    @property
    def buffered_events(self) -> Sequence[AuditEvent]:
        ...

    def record_step(
        self,
        step: str,
        *,
        message: str | None = None,
        emitted_at: datetime | None = None,
    ) -> StepAuditEvent:
        ...

    def record_error(
        self,
        step: str,
        *,
        error_type: str,
        message: str,
        emitted_at: datetime | None = None,
    ) -> ErrorAuditEvent:
        ...

    def record_finalization(
        self,
        status: FinalizationStatus,
        *,
        message: str | None = None,
        emitted_at: datetime | None = None,
    ) -> FinalizationAuditEvent:
        ...


class AuditSink(Protocol):
    def open_session(self, correlation: AuditCorrelation) -> AuditSession:
        ...


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
        return StepAuditEvent(
            correlation=self.correlation,
            emitted_at=_timestamp(emitted_at),
            step=step,
            message=message,
        )

    def record_error(
        self,
        step: str,
        *,
        error_type: str,
        message: str,
        emitted_at: datetime | None = None,
    ) -> ErrorAuditEvent:
        return ErrorAuditEvent(
            correlation=self.correlation,
            emitted_at=_timestamp(emitted_at),
            step=step,
            error_type=error_type,
            message=message,
        )

    def record_finalization(
        self,
        status: FinalizationStatus,
        *,
        message: str | None = None,
        emitted_at: datetime | None = None,
    ) -> FinalizationAuditEvent:
        return FinalizationAuditEvent(
            correlation=self.correlation,
            emitted_at=_timestamp(emitted_at),
            status=status,
            message=message,
        )


@dataclass(slots=True)
class NoOpAuditSink:
    def open_session(self, correlation: AuditCorrelation) -> NoOpAuditSession:
        return NoOpAuditSession(correlation=correlation)


@dataclass(slots=True)
class RecordingAuditSession:
    correlation: AuditCorrelation
    _buffer: list[AuditEvent] = field(default_factory=list)

    @property
    def buffered_events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._buffer)

    def record_step(
        self,
        step: str,
        *,
        message: str | None = None,
        emitted_at: datetime | None = None,
    ) -> StepAuditEvent:
        event = StepAuditEvent(
            correlation=self.correlation,
            emitted_at=_timestamp(emitted_at),
            step=step,
            message=message,
        )
        self._buffer.append(event)
        return event

    def record_error(
        self,
        step: str,
        *,
        error_type: str,
        message: str,
        emitted_at: datetime | None = None,
    ) -> ErrorAuditEvent:
        event = ErrorAuditEvent(
            correlation=self.correlation,
            emitted_at=_timestamp(emitted_at),
            step=step,
            error_type=error_type,
            message=message,
        )
        self._buffer.append(event)
        return event

    def record_finalization(
        self,
        status: FinalizationStatus,
        *,
        message: str | None = None,
        emitted_at: datetime | None = None,
    ) -> FinalizationAuditEvent:
        event = FinalizationAuditEvent(
            correlation=self.correlation,
            emitted_at=_timestamp(emitted_at),
            status=status,
            message=message,
        )
        self._buffer.append(event)
        return event


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
        session = RecordingAuditSession(correlation=correlation)
        self._sessions.append(session)
        return session


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
    "AuditCorrelation",
    "AuditEvent",
    "AuditEventBase",
    "AuditEventKind",
    "AuditSession",
    "AuditSink",
    "ErrorAuditEvent",
    "FinalizationAuditEvent",
    "FinalizationStatus",
    "NoOpAuditSession",
    "NoOpAuditSink",
    "RecordingAuditSession",
    "RecordingAuditSink",
    "StepAuditEvent",
    "create_audit_correlation",
    "new_db_trace_id",
]
