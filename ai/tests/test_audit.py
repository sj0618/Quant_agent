from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import UUID

from ai_graph.audit import NoOpAuditSink, RecordingAuditSink, create_audit_correlation


def test_create_audit_correlation_generates_fresh_db_trace_id_and_preserves_public_ids() -> None:
    correlation = create_audit_correlation(
        trace_id="trace-public-123",
        debug_ref="debug-public-456",
        entrypoint="api",
        feature="analysis",
        strategy_id="strategy-1",
        client_request_id="client-req-1",
        user_id="user-1",
        session_id="session-1",
    )

    assert isinstance(correlation.db_trace_id, UUID)
    assert correlation.db_trace_id.version == 4
    assert correlation.trace_id == "trace-public-123"
    assert correlation.debug_ref == "debug-public-456"
    assert correlation.entrypoint == "api"
    assert correlation.feature == "analysis"
    assert correlation.strategy_id == "strategy-1"
    assert correlation.client_request_id == "client-req-1"
    assert correlation.user_id == "user-1"
    assert correlation.session_id == "session-1"


def test_recording_audit_sink_captures_append_only_events_in_order() -> None:
    correlation = create_audit_correlation(
        trace_id="trace-public-123",
        debug_ref="debug-public-456",
        entrypoint="api",
        feature="analysis",
    )
    sink = RecordingAuditSink()
    session = sink.open_session(correlation)
    started_at = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
    failed_at = datetime(2026, 7, 9, 12, 1, tzinfo=UTC)
    finalized_at = datetime(2026, 7, 9, 12, 2, tzinfo=UTC)

    step_event = session.record_step("interpret", message="entered interpreter", emitted_at=started_at)
    error_event = session.record_error(
        "retrieve",
        error_type="db_timeout",
        message="statement timeout",
        emitted_at=failed_at,
    )
    finalization_event = session.record_finalization(
        "failed",
        message="response finalized with failure envelope",
        emitted_at=finalized_at,
    )

    assert sink.sessions == (session,)
    assert session.buffered_events == (step_event, error_event, finalization_event)
    assert sink.buffered_events == (step_event, error_event, finalization_event)
    assert [event.kind for event in session.buffered_events] == ["step", "error", "finalization"]
    assert [event.emitted_at for event in session.buffered_events] == [started_at, failed_at, finalized_at]


def test_noop_audit_sink_accepts_calls_without_buffering_events() -> None:
    correlation = create_audit_correlation(
        trace_id="trace-public-123",
        debug_ref="debug-public-456",
        entrypoint="api",
        feature="analysis",
    )
    sink = NoOpAuditSink()
    session = sink.open_session(correlation)

    step_event = session.record_step("interpret", message="entered interpreter")
    error_event = session.record_error("retrieve", error_type="db_timeout", message="statement timeout")
    finalization_event = session.record_finalization("failed", message="finalized")

    assert step_event.kind == "step"
    assert error_event.kind == "error"
    assert finalization_event.kind == "finalization"
    assert session.buffered_events == ()


def test_audit_boundary_api_is_synchronous() -> None:
    correlation = create_audit_correlation(
        trace_id="trace-public-123",
        debug_ref="debug-public-456",
        entrypoint="api",
        feature="analysis",
    )
    recording_session = RecordingAuditSink().open_session(correlation)
    noop_session = NoOpAuditSink().open_session(correlation)

    assert inspect.iscoroutinefunction(RecordingAuditSink.open_session) is False
    assert inspect.iscoroutinefunction(type(recording_session).record_step) is False
    assert inspect.iscoroutinefunction(type(recording_session).record_error) is False
    assert inspect.iscoroutinefunction(type(recording_session).record_finalization) is False
    assert inspect.iscoroutinefunction(type(noop_session).record_step) is False
    assert inspect.isawaitable(recording_session.record_step("interpret")) is False
    assert inspect.isawaitable(noop_session.record_finalization("completed")) is False
