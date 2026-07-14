from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import psycopg

from ai_graph.audit import (
    AuditCorrelation,
    AuditEvent,
    AuditSession,
    AuditSink,
    ErrorAuditEvent,
    FinalizationAuditEvent,
    FinalizationStatus,
    NoOpAuditSession,
    NoOpAuditSink,
    StepAuditEvent,
    report_audit_failure,
)
from ai_graph.data_sources.db import resolve_database_dsn_from_env


AI_AUDIT_SINK_ENV = "AI_AUDIT_SINK"
AI_AUDIT_CONNECT_TIMEOUT_SECONDS_ENV = "AI_AUDIT_CONNECT_TIMEOUT_SECONDS"
AI_AUDIT_STATEMENT_TIMEOUT_MS_ENV = "AI_AUDIT_STATEMENT_TIMEOUT_MS"
AI_AUDIT_GATE_B_ADMISSION_HMAC_SECRET_ENV = "AI_AUDIT_GATE_B_ADMISSION_HMAC_SECRET"
AI_AUDIT_GATE_B_ADMISSION_HMAC_KEY_VERSION_ENV = "AI_AUDIT_GATE_B_ADMISSION_HMAC_KEY_VERSION"
AI_AUDIT_GATE_B_ADMISSION_TOKEN_ENV = "AI_AUDIT_GATE_B_ADMISSION_TOKEN"
AI_AUDIT_GATE_B_ADMISSION_AUDIENCE_ENV = "AI_AUDIT_GATE_B_ADMISSION_AUDIENCE"
AI_AUDIT_GATE_B_EVIDENCE_ID_ENV = "AI_AUDIT_GATE_B_EVIDENCE_ID"
AI_AUDIT_GATE_B_DEPLOYMENT_REVISION_ENV = "AI_AUDIT_GATE_B_DEPLOYMENT_REVISION"
DEFAULT_AUDIT_CONNECT_TIMEOUT_SECONDS = 2
DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS = 2_000
_AUDIT_WRITER_CAPABILITY = object()
_AUDIT_TEST_SINK_CAPABILITY = object()
_RAW_AUDIT_ADMISSION_ISSUER = object()


class _RawAuditAdmission:
    __slots__ = ("_expires_at", "_issuer_token")

    def __init__(self) -> None:
        raise TypeError("raw audit admission is issued only after signed Gate B verification")

    def authorizes_writer(self) -> bool:
        expires_at = getattr(self, "_expires_at", None)
        return (
            getattr(self, "_issuer_token", None) is _RAW_AUDIT_ADMISSION_ISSUER
            and _valid_timestamp(expires_at)
            and expires_at > time.time()
        )


class _TestAuditSink:
    __slots__ = ("_sink", "_capability")

    def __init__(self, sink: AuditSink, *, _capability: object) -> None:
        if _capability is not _AUDIT_TEST_SINK_CAPABILITY:
            raise PermissionError("test audit sinks must be issued by the test sink factory")
        self._sink = sink
        self._capability = _capability

    def authorizes_ingress(self) -> bool:
        return self._capability is _AUDIT_TEST_SINK_CAPABILITY

    def open_session(self, correlation: AuditCorrelation) -> AuditSession:
        return self._sink.open_session(correlation)


class AuthorizedAuditSink:
    """Persistent audit sink issued only after Gate B admission verification."""

    __slots__ = ("_writer",)

    def __init__(self, writer: "_PostgresAuditWriter", *, _capability: object) -> None:
        if _capability is not _AUDIT_WRITER_CAPABILITY:
            raise PermissionError("persistent audit sinks must be issued by the audit resolver")
        self._writer = writer

    def open_session(self, correlation: AuditCorrelation) -> AuditSession:
        return self._writer.open_session(correlation)


class _PostgresAuditWriter:
    __slots__ = ("dsn", "admission", "connect_timeout_seconds", "statement_timeout_ms", "connector")

    def __init__(
        self,
        dsn: str,
        *,
        admission: _RawAuditAdmission,
        connect_timeout_seconds: int = DEFAULT_AUDIT_CONNECT_TIMEOUT_SECONDS,
        statement_timeout_ms: int = DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS,
        connector: Callable[..., Any] = psycopg.connect,
    ) -> None:
        if not isinstance(admission, _RawAuditAdmission) or not admission.authorizes_writer():
            raise PermissionError("raw audit writer requires a verified Gate B admission")
        self.dsn = dsn
        self.admission = admission
        self.connect_timeout_seconds = connect_timeout_seconds
        self.statement_timeout_ms = statement_timeout_ms
        self.connector = connector

    def open_session(self, correlation: AuditCorrelation) -> "_PostgresAuditSession | NoOpAuditSession":
        if not self.admission.authorizes_writer():
            report_audit_failure("gate_b_admission_denied")
            return NoOpAuditSession(correlation)
        conn: Any | None = None
        try:
            conn = self.connector(
                self.dsn,
                connect_timeout=self.connect_timeout_seconds,
                autocommit=False,
            )
            conn.execute(
                "SELECT set_config('statement_timeout', %s, false)",
                (f"{self.statement_timeout_ms}ms",),
            )
            metadata = _correlation_metadata(correlation)
            conn.execute(
                """
                INSERT INTO app.ai_trace (
                    trace_id, trace_kind, status, metadata_jsonb, started_at
                ) VALUES (%s, %s, 'running', %s::jsonb, %s)
                """,
                (
                    correlation.db_trace_id,
                    correlation.feature or "ai_runtime",
                    _json(metadata),
                    _utcnow(),
                ),
            )
            conn.commit()
        except Exception:  # noqa: BLE001 - audit must remain fail-open
            _rollback(conn)
            _close(conn)
            report_audit_failure("open_session")
            return NoOpAuditSession(correlation)
        return _PostgresAuditSession(
            correlation=correlation,
            connection=conn,
            _capability=_AUDIT_WRITER_CAPABILITY,
        )


@dataclass(slots=True, init=False)
class _PostgresAuditSession:
    correlation: AuditCorrelation
    connection: Any = field(repr=False)
    _broken: bool = False
    _closed: bool = False
    _failure_reported: bool = False
    _model_execution_ids: dict[UUID, UUID | None] = field(default_factory=dict)
    _capability: object = field(default=None, repr=False)

    def __init__(
        self,
        correlation: AuditCorrelation,
        connection: Any,
        *,
        _capability: object,
    ) -> None:
        if _capability is not _AUDIT_WRITER_CAPABILITY:
            raise PermissionError("raw audit sessions must be opened by an authorized sink")
        self.correlation = correlation
        self.connection = connection
        self._broken = False
        self._closed = False
        self._failure_reported = False
        self._capability = _capability
        self._model_execution_ids = {}

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
        event = ErrorAuditEvent(
            self.correlation,
            _timestamp(emitted_at),
            step,
            _bounded(error_type, 128),
            _bounded(message, 512),
            call_id,
            execution_id,
            dict(context_jsonb or {}),
            _bounded(severity, 32),
        )

        def action() -> None:
            self.connection.execute(
                """
                INSERT INTO app.ai_error_log (
                    error_id, trace_id, call_id, execution_id, error_type,
                    error_message, stack_trace, context_jsonb, severity, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s::jsonb, %s, %s)
                """,
                (
                    uuid4(),
                    self.correlation.db_trace_id,
                    call_id,
                    execution_id,
                    event.error_type,
                    event.message,
                    _json({"step": step, **event.context_jsonb}),
                    event.severity,
                    event.emitted_at,
                ),
            )

        self._transaction("record_error", action)
        return event

    def record_finalization(
        self,
        status: FinalizationStatus,
        *,
        message: str | None = None,
        metadata_jsonb: Mapping[str, Any] | None = None,
        emitted_at: datetime | None = None,
    ) -> FinalizationAuditEvent:
        event = FinalizationAuditEvent(
            self.correlation,
            _timestamp(emitted_at),
            status,
            message,
            dict(metadata_jsonb or {}),
        )

        def action() -> None:
            self.connection.execute(
                """
                UPDATE app.ai_trace
                SET status = %s,
                    metadata_jsonb = metadata_jsonb || %s::jsonb,
                    ended_at = %s
                WHERE trace_id = %s
                """,
                (
                    status,
                    _json({"finalization_message": message, **event.metadata_jsonb}),
                    event.emitted_at,
                    self.correlation.db_trace_id,
                ),
            )

        try:
            self._transaction("record_finalization", action)
        finally:
            self.close()
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
        timestamp = _timestamp(started_at)

        def action() -> None:
            self.connection.execute(
                """
                INSERT INTO app.ai_agent_execution_log (
                    execution_id, trace_id, agent_name, step_name, status,
                    input_jsonb, output_jsonb, started_at
                ) VALUES (%s, %s, %s, %s, 'running', %s::jsonb, '{}'::jsonb, %s)
                """,
                (
                    execution_id,
                    self.correlation.db_trace_id,
                    agent_name,
                    step_name,
                    _json(input_jsonb or {}),
                    timestamp,
                ),
            )

        self._transaction("start_agent_execution", action)
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
        timestamp = _timestamp(ended_at)
        safe_error = _bounded(error_message, 512) if error_message else None

        def action() -> None:
            self.connection.execute(
                """
                UPDATE app.ai_agent_execution_log
                SET status = %s, output_jsonb = %s::jsonb, error_message = %s,
                    latency_ms = %s, ended_at = %s
                WHERE execution_id = %s
                """,
                (status, _json(output_jsonb or {}), safe_error, latency_ms, timestamp, execution_id),
            )

        self._transaction("finish_agent_execution", action)

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
        prompt_log_id = uuid4()
        timestamp = _timestamp(created_at)
        self._model_execution_ids[call_id] = execution_id

        def action() -> None:
            self.connection.execute(
                """
                INSERT INTO app.ai_model_call_log (
                    call_id, trace_id, execution_id, task_type, provider,
                    model_name, temperature, retry_count, status,
                    response_schema_name, web_search_used, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 'running', %s, %s, %s)
                """,
                (
                    call_id,
                    self.correlation.db_trace_id,
                    execution_id,
                    task_type,
                    provider,
                    model_name,
                    temperature,
                    response_schema_name,
                    web_search_used,
                    timestamp,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO app.ai_prompt_log (
                    prompt_log_id, call_id, prompt_template_name, system_prompt,
                    user_prompt, assistant_response, variables_jsonb,
                    prompt_version, contains_pii, masked, created_at
                ) VALUES (%s, %s, %s, %s, %s, NULL, %s::jsonb, %s, FALSE, FALSE, %s)
                """,
                (
                    prompt_log_id,
                    call_id,
                    prompt_template_name,
                    system_prompt,
                    user_prompt,
                    _json(variables_jsonb),
                    prompt_version,
                    timestamp,
                ),
            )

        self._transaction("start_model_call", action)
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
        safe_error = _bounded(error_message, 512) if error_message else None
        execution_id = self._model_execution_ids.get(call_id)

        def action() -> None:
            self.connection.execute(
                """
                UPDATE app.ai_model_call_log
                SET provider_request_id = %s,
                    model_name = COALESCE(%s, model_name),
                    prompt_tokens = %s,
                    completion_tokens = %s,
                    total_tokens = %s,
                    latency_ms = %s,
                    retry_count = %s,
                    status = %s,
                    error_message = %s
                WHERE call_id = %s
                """,
                (
                    provider_request_id,
                    model_name,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    latency_ms,
                    retry_count,
                    status,
                    safe_error,
                    call_id,
                ),
            )
            self.connection.execute(
                "UPDATE app.ai_prompt_log SET assistant_response = %s WHERE call_id = %s",
                (assistant_response, call_id),
            )
            if status == "failed" and error_type:
                self._insert_error(
                    call_id=call_id,
                    execution_id=execution_id,
                    error_type=error_type,
                    error_message=safe_error or "model call failed",
                    context_jsonb={"operation": "finish_model_call"},
                )

        self._transaction("finish_model_call", action)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close(self.connection)

    def _insert_error(
        self,
        *,
        call_id: UUID | None,
        execution_id: UUID | None,
        error_type: str,
        error_message: str,
        context_jsonb: Mapping[str, Any],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO app.ai_error_log (
                error_id, trace_id, call_id, execution_id, error_type,
                error_message, stack_trace, context_jsonb, severity, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s::jsonb, 'error', %s)
            """,
            (
                uuid4(),
                self.correlation.db_trace_id,
                call_id,
                execution_id,
                _bounded(error_type, 128),
                _bounded(error_message, 512),
                _json(context_jsonb),
                _utcnow(),
            ),
        )

    def _transaction(
        self,
        operation: str,
        action: Callable[[], None],
    ) -> bool:
        if self._broken or self._closed:
            return False
        try:
            action()
            self.connection.commit()
            return True
        except Exception:  # noqa: BLE001 - audit must remain fail-open
            self._handle_failure(operation)
            return False

    def _handle_failure(self, operation: str) -> None:
        if self._broken:
            return
        self._broken = True
        _rollback(self.connection)
        if not self._failure_reported:
            self._failure_reported = True
            report_audit_failure(operation)
        self.close()


def create_audit_sink_from_env(
    environ: Mapping[str, str] | None = None,
) -> AuthorizedAuditSink | NoOpAuditSink:
    env = os.environ if environ is None else environ
    selector = env.get(AI_AUDIT_SINK_ENV, "noop").strip().lower()
    if selector in {"", "noop"}:
        return NoOpAuditSink()
    if selector != "postgres":
        report_audit_failure("invalid_sink_selector")
        return NoOpAuditSink()
    admission = _admission_from_env(env)
    if admission is None:
        return NoOpAuditSink()
    dsn, _ = resolve_database_dsn_from_env(env)
    if not dsn:
        report_audit_failure("missing_database_dsn")
        return NoOpAuditSink()
    return _authorized_sink(
        dsn,
        admission=admission,
        connect_timeout_seconds=_positive_int(
            env.get(AI_AUDIT_CONNECT_TIMEOUT_SECONDS_ENV),
            DEFAULT_AUDIT_CONNECT_TIMEOUT_SECONDS,
        ),
        statement_timeout_ms=_positive_int(
            env.get(AI_AUDIT_STATEMENT_TIMEOUT_MS_ENV),
            DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS,
        ),
    )


def resolve_audit_sink(
    candidate: AuditSink | None,
    *,
    environ: Mapping[str, str] | None = None,
) -> AuditSink:
    """Normalize every audit ingress to an authorized, no-op, or private test sink."""
    if candidate is None:
        return create_audit_sink_from_env(environ)
    if isinstance(candidate, (AuthorizedAuditSink, NoOpAuditSink)):
        return candidate
    if isinstance(candidate, _TestAuditSink) and candidate.authorizes_ingress():
        return candidate
    report_audit_failure("unapproved_audit_sink")
    return NoOpAuditSink()

def is_authorized_audit_session(candidate: object) -> bool:
    return not isinstance(candidate, _PostgresAuditSession) or getattr(candidate, "_capability", None) is _AUDIT_WRITER_CAPABILITY



def _create_test_audit_sink(sink: AuditSink) -> AuditSink:
    """Wrap a test double for explicit, non-production audit ingress."""
    return _TestAuditSink(sink, _capability=_AUDIT_TEST_SINK_CAPABILITY)


def _admission_from_env(env: Mapping[str, str]) -> _RawAuditAdmission | None:
    secret = _required_text(env.get(AI_AUDIT_GATE_B_ADMISSION_HMAC_SECRET_ENV))
    token = _required_text(env.get(AI_AUDIT_GATE_B_ADMISSION_TOKEN_ENV))
    key_version = _required_text(env.get(AI_AUDIT_GATE_B_ADMISSION_HMAC_KEY_VERSION_ENV))
    evidence_id = _required_text(env.get(AI_AUDIT_GATE_B_EVIDENCE_ID_ENV))
    deployment_revision = _required_text(env.get(AI_AUDIT_GATE_B_DEPLOYMENT_REVISION_ENV))
    audience = _required_text(env.get(AI_AUDIT_GATE_B_ADMISSION_AUDIENCE_ENV))
    if not all((secret, token, key_version, evidence_id, deployment_revision, audience)):
        report_audit_failure("gate_b_admission_denied")
        return None
    parsed = _parse_signed_admission(token, secret)
    if parsed is None:
        report_audit_failure("gate_b_admission_denied")
        return None
    header, claims = parsed
    if (
        header.get("alg") != "HS256"
        or header.get("key_version") != key_version
        or claims.get("key_version") != key_version
        or claims.get("evidence_id") != evidence_id
        or claims.get("deployment_revision") != deployment_revision
        or claims.get("audience") != audience
    ):
        report_audit_failure("gate_b_admission_denied")
        return None
    issued_at = claims.get("issued_at")
    expires_at = claims.get("expiry")
    now = time.time()
    if (
        not _valid_timestamp(issued_at)
        or not _valid_timestamp(expires_at)
        or issued_at > now
        or expires_at <= now
        or expires_at <= issued_at
    ):
        report_audit_failure("gate_b_admission_denied")
        return None
    return _new_raw_audit_admission(expires_at)

def _new_raw_audit_admission(expires_at: float) -> _RawAuditAdmission:
    admission = object.__new__(_RawAuditAdmission)
    admission._issuer_token = _RAW_AUDIT_ADMISSION_ISSUER
    admission._expires_at = expires_at
    return admission


def _parse_signed_admission(token: str, secret: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    encoded_header, encoded_claims, encoded_signature = parts
    try:
        header = _decode_json_segment(encoded_header)
        claims = _decode_json_segment(encoded_claims)
        signature = _decode_segment(encoded_signature)
    except (ValueError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
        return None
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    expected_signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        return None
    return header, claims


def _decode_json_segment(value: str) -> dict[str, Any]:
    parsed = json.loads(_decode_segment(value).decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("token segment must be an object")
    return parsed


def _decode_segment(value: str) -> bytes:
    if not value or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in value):
        raise ValueError("invalid base64url token segment")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _required_text(value: object) -> str | None:
    normalized = value.strip() if isinstance(value, str) else ""
    return normalized or None


def _valid_timestamp(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _authorized_sink(
    dsn: str,
    *,
    admission: _RawAuditAdmission,
    connector: Callable[..., Any] = psycopg.connect,
    connect_timeout_seconds: int = DEFAULT_AUDIT_CONNECT_TIMEOUT_SECONDS,
    statement_timeout_ms: int = DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS,
) -> AuthorizedAuditSink:
    writer = _PostgresAuditWriter(
        dsn,
        admission=admission,
        connector=connector,
        connect_timeout_seconds=connect_timeout_seconds,
        statement_timeout_ms=statement_timeout_ms,
    )
    return AuthorizedAuditSink(writer, _capability=_AUDIT_WRITER_CAPABILITY)


def _correlation_metadata(correlation: AuditCorrelation) -> dict[str, str]:
    values = {
        "public_trace_id": correlation.trace_id,
        "debug_ref": correlation.debug_ref,
        "entrypoint": correlation.entrypoint,
        "feature": correlation.feature,
        "strategy_id": correlation.strategy_id,
        "client_request_id": correlation.client_request_id,
        "user_id": correlation.user_id,
        "session_id": correlation.session_id,
    }
    return {key: value for key, value in values.items() if value is not None}


def _rollback(conn: Any | None) -> None:
    if conn is None:
        return
    try:
        conn.rollback()
    except Exception:  # noqa: BLE001
        return


def _close(conn: Any | None) -> None:
    if conn is None or bool(getattr(conn, "closed", False)):
        return
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        return


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _bounded(value: str, limit: int) -> str:
    return value[:limit]


def _positive_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _timestamp(value: datetime | None) -> datetime:
    return value if value is not None else _utcnow()


def _utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "AI_AUDIT_CONNECT_TIMEOUT_SECONDS_ENV",
    "AI_AUDIT_GATE_B_ADMISSION_AUDIENCE_ENV",
    "AI_AUDIT_GATE_B_ADMISSION_HMAC_KEY_VERSION_ENV",
    "AI_AUDIT_GATE_B_ADMISSION_HMAC_SECRET_ENV",
    "AI_AUDIT_GATE_B_ADMISSION_TOKEN_ENV",
    "AI_AUDIT_GATE_B_DEPLOYMENT_REVISION_ENV",
    "AI_AUDIT_GATE_B_EVIDENCE_ID_ENV",
    "AI_AUDIT_SINK_ENV",
    "AI_AUDIT_STATEMENT_TIMEOUT_MS_ENV",
    "AuthorizedAuditSink",
    "create_audit_sink_from_env",
    "resolve_audit_sink",
]
