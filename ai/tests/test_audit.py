from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
from threading import Barrier
from uuid import UUID

import pytest

from ai_graph.audit import (
    NoOpAuditSink,
    RecordingAuditSink,
    active_audit_session,
    active_execution_id,
    audit_failure_count,
    begin_model_call,
    bind_audit_context,
    create_audit_correlation,
    report_audit_failure,
)
from ai_graph.graph import instrument_node


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


def test_nested_audit_context_restores_tokens_after_return_and_exception() -> None:
    outer = RecordingAuditSink().open_session(
        create_audit_correlation(
            trace_id="outer",
            debug_ref=None,
            entrypoint="test",
            feature="outer",
        )
    )
    inner = RecordingAuditSink().open_session(
        create_audit_correlation(
            trace_id="inner",
            debug_ref=None,
            entrypoint="test",
            feature="inner",
        )
    )

    assert active_audit_session() is None
    with bind_audit_context(outer):
        assert active_audit_session() is outer
        try:
            with bind_audit_context(inner, UUID("00000000-0000-4000-8000-000000000001")):
                assert active_audit_session() is inner
                assert active_execution_id() is not None
                raise RuntimeError("expected")
        except RuntimeError:
            pass
        assert active_audit_session() is outer
        assert active_execution_id() is None
    assert active_audit_session() is None
    assert active_execution_id() is None


def test_instrumented_node_binds_explicit_session_inside_executor_thread() -> None:
    session = RecordingAuditSink().open_session(
        create_audit_correlation(
            trace_id="thread",
            debug_ref=None,
            entrypoint="test",
            feature="thread",
        )
    )

    def node(state):
        assert active_audit_session() is session
        assert active_execution_id() is not None
        return {"status": "ready", **state}

    wrapped = instrument_node(session, "Thread Node", node)
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(wrapped, {"trace_id": "thread"}).result()

    assert result["status"] == "ready"
    assert len(session.agent_executions) == 1
    assert session.agent_executions[0].status == "succeeded"
    assert active_audit_session() is None


def test_concurrent_audit_contexts_do_not_cross_trace_or_execution_ids() -> None:
    sessions = [
        RecordingAuditSink().open_session(
            create_audit_correlation(
                trace_id=f"trace-{index}",
                debug_ref=None,
                entrypoint="test",
                feature="concurrent",
            )
        )
        for index in range(2)
    ]
    execution_ids = [
        UUID("00000000-0000-4000-8000-000000000001"),
        UUID("00000000-0000-4000-8000-000000000002"),
    ]
    barrier = Barrier(2)

    def observe(index: int):
        with bind_audit_context(sessions[index], execution_ids[index]):
            barrier.wait()
            return active_audit_session(), active_execution_id()

    with ThreadPoolExecutor(max_workers=2) as executor:
        observed = list(executor.map(observe, range(2)))

    assert observed == list(zip(sessions, execution_ids, strict=True))


def test_instrumented_node_failure_links_error_to_failed_execution() -> None:
    session = RecordingAuditSink().open_session(
        create_audit_correlation(
            trace_id="trace-node-failure",
            debug_ref=None,
            entrypoint="test",
            feature="node_failure",
        )
    )

    def failing_node(state):
        raise RuntimeError("private failure detail")

    with pytest.raises(RuntimeError, match="private failure detail"):
        instrument_node(session, "Failing Node", failing_node)({"trace_id": "trace-node-failure"})

    execution = session.agent_executions[0]
    error = session.buffered_events[0]
    assert execution.status == "failed"
    assert error.kind == "error"
    assert error.execution_id == execution.execution_id
    assert "private failure detail" not in error.message
    assert active_audit_session() is None
    assert active_execution_id() is None


def test_audit_failure_reporter_never_propagates_stderr_failure(monkeypatch) -> None:
    class BrokenStderr:
        def write(self, value):
            raise OSError("stderr unavailable")

        def flush(self):
            raise OSError("stderr unavailable")

    before = audit_failure_count()
    monkeypatch.setattr("ai_graph.audit.sys.stderr", BrokenStderr())

    report_audit_failure("record_error")

    assert audit_failure_count() == before + 1


def test_model_call_variables_are_normalized_to_json_values() -> None:
    session = RecordingAuditSink().open_session(
        create_audit_correlation(
            trace_id="trace-json-values",
            debug_ref=None,
            entrypoint="test",
            feature="json_values",
        )
    )
    value_id = UUID("00000000-0000-4000-8000-000000000001")

    with bind_audit_context(session):
        call_id = begin_model_call(
            task_type="json_values",
            provider="mock",
            model_name="deterministic",
            system_prompt="system",
            user_prompt="user",
            variables_jsonb={
                "datetime": datetime(2026, 7, 13, 9, 30, tzinfo=UTC),
                "date": date(2026, 7, 13),
                "uuid": value_id,
                "decimal": Decimal("1.2300"),
                "tuple": (1, "two"),
            },
            prompt_template_name="json_values",
            prompt_version="v1",
            temperature=0.0,
            response_schema_name="json-values.v1",
            web_search_used=False,
        )

    assert call_id is not None
    assert session.prompt_logs[0].variables_jsonb == {
        "datetime": "2026-07-13T09:30:00+00:00",
        "date": "2026-07-13",
        "uuid": str(value_id),
        "decimal": "1.2300",
        "tuple": [1, "two"],
    }
