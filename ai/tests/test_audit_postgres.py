from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import time
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from ai_graph.audit import (
    NoOpAuditSession,
    NoOpAuditSink,
    audit_failure_count,
    create_audit_correlation,
)
from ai_graph.audit_postgres import (
    AuthorizedAuditSink,
    _authorized_sink,
    _create_test_audit_sink,
    _new_raw_audit_admission,
    create_audit_sink_from_env,
)
from ai_graph.api import create_app
from ai_graph.graph import run_analysis

_AUDIT_ADMISSION_SECRET = "test-ai-audit-admission-secret"
_AUDIT_ADMISSION_KEY_VERSION = "test-v1"
_AUDIT_ADMISSION_AUDIENCE = "quantagent.ai.audit"
_AUDIT_ADMISSION_EVIDENCE_ID = "gate-b-evidence-001"
_AUDIT_ADMISSION_REVISION = "revision-9"

def _create_test_persistent_sink(
    dsn: str,
    *,
    connector=psycopg.connect,
    connect_timeout_seconds: int = 2,
    statement_timeout_ms: int = 2_000,
) -> AuthorizedAuditSink:
    return _authorized_sink(
        dsn,
        admission=_new_raw_audit_admission(time.time() + 300),
        connector=connector,
        connect_timeout_seconds=connect_timeout_seconds,
        statement_timeout_ms=statement_timeout_ms,
    )

def _base64url_json(value: dict[str, object]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def _signed_admission_token(claim_overrides: dict[str, object] | None = None) -> str:
    claims: dict[str, object] = {
        "audience": _AUDIT_ADMISSION_AUDIENCE,
        "deployment_revision": _AUDIT_ADMISSION_REVISION,
        "evidence_id": _AUDIT_ADMISSION_EVIDENCE_ID,
        "expiry": time.time() + 300,
        "issued_at": time.time() - 1,
        "key_version": _AUDIT_ADMISSION_KEY_VERSION,
    }
    if claim_overrides:
        claims.update(claim_overrides)
    header = {"alg": "HS256", "key_version": _AUDIT_ADMISSION_KEY_VERSION}
    signing_input = f"{_base64url_json(header)}.{_base64url_json(claims)}"
    signature = hmac.new(
        _AUDIT_ADMISSION_SECRET.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{signing_input}.{encoded_signature}"


def _audit_sink_env(
    *,
    token: str | None = None,
    audience: str = _AUDIT_ADMISSION_AUDIENCE,
    revision: str = _AUDIT_ADMISSION_REVISION,
) -> dict[str, str]:
    return {
        "AI_AUDIT_SINK": "postgres",
        "APP_ENV": "development",
        "AI_AUDIT_GATE_B_ADMISSION_HMAC_SECRET": _AUDIT_ADMISSION_SECRET,
        "AI_AUDIT_GATE_B_ADMISSION_HMAC_KEY_VERSION": _AUDIT_ADMISSION_KEY_VERSION,
        "AI_AUDIT_GATE_B_ADMISSION_TOKEN": token or _signed_admission_token(),
        "AI_AUDIT_GATE_B_ADMISSION_AUDIENCE": audience,
        "AI_AUDIT_GATE_B_EVIDENCE_ID": _AUDIT_ADMISSION_EVIDENCE_ID,
        "AI_AUDIT_GATE_B_DEPLOYMENT_REVISION": revision,
        "AI_DATABASE_DSN": "postgresql://preferred",
    }


class FakeConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0
        self.close_calls = 0
        self.closed = False
        self.fail_matching: str | None = None
        self.failure: Exception = RuntimeError("injected SQL failure")

    def execute(self, sql: str, params: Any = None) -> None:
        normalized = " ".join(sql.split())
        self.executions.append((normalized, params))
        if self.fail_matching and self.fail_matching in normalized:
            self.fail_matching = None
            raise self.failure

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True
class RevokingConnection(FakeConnection):
    def __init__(self, env: dict[str, str]) -> None:
        super().__init__()
        self._env = env

    def commit(self) -> None:
        super().commit()
        if self.commits == 1:
            self._env["AI_AUDIT_GATE_B_ADMISSION_REVOCATION_STATE"] = "revoked"




class CapturingConnector:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, dsn: str, **kwargs: Any) -> FakeConnection:
        self.calls.append((dsn, kwargs))
        return self.connection


class RecursiveFailureConnection(FakeConnection):
    def __init__(self) -> None:
        super().__init__()
        self.fail_after_open = False

    def execute(self, sql: str, params: Any = None) -> None:
        normalized = " ".join(sql.split())
        self.executions.append((normalized, params))
        if self.fail_after_open:
            raise RuntimeError("secret recursive SQL detail")


def make_correlation():
    return create_audit_correlation(
        trace_id="public-trace",
        debug_ref="debug-ref",
        entrypoint="api.analysis_jobs",
        feature="analysis_job",
        strategy_id="strategy-1",
        client_request_id="request-1",
        user_id="untrusted-user-string",
        session_id="untrusted-session-string",
    )


def test_postgres_session_persists_joined_lifecycles_and_closes_once() -> None:
    conn = FakeConnection()
    connector = CapturingConnector(conn)
    session = _create_test_persistent_sink("postgresql://db.example/app",
    connector=connector,).open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)
    execution_id = session.start_agent_execution(
        "Research",
        step_name="Research",
        input_jsonb={"keys": ["trace_id", "status"]},
    )
    call_id = session.start_model_call(
        task_type="research_bull",
        provider="mock",
        model_name="deterministic",
        system_prompt="전체 시스템 프롬프트",
        user_prompt="전체 사용자 프롬프트",
        variables_jsonb={"query": "삼성전자"},
        prompt_template_name="role_debate",
        prompt_version="v1",
        temperature=0.0,
        response_schema_name="quantagent.role_debate.v1",
        web_search_used=False,
        execution_id=execution_id,
    )
    session.finish_model_call(
        call_id,
        status="succeeded",
        assistant_response='{"summary":"전체 응답"}',
        provider_request_id="provider-request-1",
        model_name="deterministic",
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
        latency_ms=3.5,
        retry_count=2,
    )
    session.finish_agent_execution(
        execution_id,
        status="succeeded",
        output_jsonb={"keys": ["research"]},
        latency_ms=4.0,
    )
    session.record_finalization(
        "completed",
        metadata_jsonb={"debug_ref": "debug-ref"},
    )
    session.close()

    sql = "\n".join(statement for statement, _ in conn.executions)
    assert "INSERT INTO app.ai_trace" in sql
    assert "INSERT INTO app.ai_agent_execution_log" in sql
    assert "INSERT INTO app.ai_model_call_log" in sql
    assert "INSERT INTO app.ai_prompt_log" in sql
    assert "UPDATE app.ai_model_call_log" in sql
    assert "UPDATE app.ai_prompt_log" in sql
    assert "UPDATE app.ai_agent_execution_log" in sql
    assert "UPDATE app.ai_trace" in sql
    assert conn.close_calls == 1
    assert connector.calls == [
        (
            "postgresql://db.example/app",
            {"connect_timeout": 2, "autocommit": False},
        )
    ]

    model_params = next(
        params for statement, params in conn.executions if "INSERT INTO app.ai_model_call_log" in statement
    )
    prompt_params = next(
        params for statement, params in conn.executions if "INSERT INTO app.ai_prompt_log" in statement
    )
    assert model_params[0] == prompt_params[1] == call_id
    assert model_params[2] == execution_id
    model_update_params = next(
        params
        for statement, params in conn.executions
        if "UPDATE app.ai_model_call_log" in statement
    )
    assert model_update_params == (
        "provider-request-1",
        "deterministic",
        11,
        7,
        18,
        3.5,
        2,
        "succeeded",
        None,
        call_id,
    )


def test_initial_model_prompt_serialization_failure_rolls_back_and_breaks_session(
    capsys,
) -> None:
    conn = FakeConnection()
    session = _create_test_persistent_sink("postgresql://test",
    connector=CapturingConnector(conn),).open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)

    session.start_model_call(
        task_type="bad_json",
        provider="mock",
        model_name="deterministic",
        system_prompt="system",
        user_prompt="user",
        variables_jsonb={"not_json": object()},
        prompt_template_name="test",
        prompt_version="v1",
        temperature=0.0,
        response_schema_name="test.v1",
        web_search_used=False,
        execution_id=None,
    )
    executions_after_failure = len(conn.executions)
    session.record_step("ignored")
    session.start_agent_execution("ignored", step_name="ignored")

    assert conn.rollbacks >= 1
    assert conn.close_calls == 1
    assert len(conn.executions) == executions_after_failure
    assert "ai_audit_failure" in capsys.readouterr().err


def test_connection_error_does_not_attempt_recursive_db_error_insert(capsys) -> None:
    conn = FakeConnection()
    connector = CapturingConnector(conn)
    session = _create_test_persistent_sink("postgresql://test", connector=connector).open_session(
        make_correlation()
    )
    assert not isinstance(session, NoOpAuditSession)
    conn.fail_matching = "INSERT INTO app.ai_agent_execution_log"
    conn.failure = psycopg.OperationalError("connection closed")

    session.start_agent_execution("Research", step_name="Research")

    sql = "\n".join(statement for statement, _ in conn.executions)
    assert "audit_persistence_failure" not in sql
    assert conn.close_calls == 1
    assert "ai_audit_failure" in capsys.readouterr().err


def test_terminal_update_failure_closes_once_and_keeps_business_path_open(capsys) -> None:
    conn = FakeConnection()
    session = _create_test_persistent_sink("postgresql://test",
    connector=CapturingConnector(conn),).open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)
    conn.fail_matching = "UPDATE app.ai_trace"

    event = session.record_finalization("completed")

    assert event.status == "completed"
    assert conn.rollbacks >= 1
    assert conn.close_calls == 1
    assert "ai_audit_failure" in capsys.readouterr().err


def test_sink_factory_requires_signed_gate_b_admission_before_issuing_persistent_sink() -> None:
    assert isinstance(create_audit_sink_from_env({}), NoOpAuditSink)
    assert isinstance(
        create_audit_sink_from_env(
            {
                "AI_AUDIT_SINK": "postgres",
                "AI_AUDIT_GATE_B_ADMISSION": "approved",
                "AI_AUDIT_GATE_B_EVIDENCE_ID": _AUDIT_ADMISSION_EVIDENCE_ID,
                "AI_DATABASE_DSN": "postgresql://preferred",
            }
        ),
        NoOpAuditSink,
    )

    sink = create_audit_sink_from_env(_audit_sink_env())
    assert isinstance(sink, AuthorizedAuditSink)
    assert "postgresql://preferred" not in repr(sink)

@pytest.mark.parametrize("app_env", ["production", "prod", "staging", "stage"])
def test_postgres_sink_and_admission_are_hard_disabled_without_external_provider(
    app_env: str,
) -> None:
    module = importlib.import_module("ai_graph.audit_postgres")
    env = _audit_sink_env()
    env["APP_ENV"] = app_env
    env["AI_AUDIT_GATE_B_ADMISSION_REVOCATION_STATE"] = "active"

    assert module._admission_from_env(env) is None
    assert isinstance(
        module.resolve_audit_sink(_create_test_persistent_sink("postgresql://test"), environ=env),
        NoOpAuditSink,
    )
    assert isinstance(create_audit_sink_from_env(env), NoOpAuditSink)


@pytest.mark.parametrize(
    "token",
    [
        _signed_admission_token({"expiry": time.time() - 1}),
        _signed_admission_token({"audience": "wrong-audience"}),
        _signed_admission_token({"deployment_revision": "wrong-revision"}),
        "forged.admission.token",
    ],
)
def test_sink_factory_denies_invalid_signed_gate_b_admissions(token: str) -> None:
    assert isinstance(create_audit_sink_from_env(_audit_sink_env(token=token)), NoOpAuditSink)


def test_factory_create_app_and_run_analysis_deny_forged_environment_admission(monkeypatch) -> None:
    for name, value in _audit_sink_env(token="forged.admission.token").items():
        monkeypatch.setenv(name, value)

    app = create_app()
    envelope = run_analysis("저평가주 사줘")

    assert isinstance(app.state.audit_sink, NoOpAuditSink)
    assert envelope.status == "need_clarification"


def test_forgeable_test_marker_is_noop_for_app_and_direct_graph_ingress() -> None:
    class ForgedSink:
        __audit_sink_test_only__ = True

        def __init__(self) -> None:
            self.open_calls = 0

        def open_session(self, correlation):
            self.open_calls += 1
            raise AssertionError("forged audit sink must not be opened")

    sink = ForgedSink()
    app = create_app(audit_sink=sink)
    assert isinstance(app.state.audit_sink, NoOpAuditSink)

    envelope = run_analysis("저평가주 사줘", audit_sink=sink)

    assert envelope.status == "need_clarification"
    assert sink.open_calls == 0


def test_private_test_sink_factory_allows_explicit_test_doubles() -> None:
    class TestSink:
        def __init__(self) -> None:
            self.open_calls = 0

        def open_session(self, correlation):
            self.open_calls += 1
            return NoOpAuditSink().open_session(correlation)

    sink = TestSink()
    app = create_app(audit_sink=_create_test_audit_sink(sink))
    app.state.audit_sink.open_session(make_correlation())
    assert sink.open_calls == 1


def test_legacy_raw_symbols_are_not_importable_and_private_writers_reject_bypass() -> None:
    module = importlib.import_module("ai_graph.audit_postgres")

    with pytest.raises(ImportError):
        exec("from ai_graph.audit_postgres import PostgresAuditSink", {})
    with pytest.raises(ImportError):
        exec("from ai_graph.audit_postgres import PostgresAuditSession", {})
    with pytest.raises(PermissionError):
        module.AuthorizedAuditSink(None, _capability=object())
    with pytest.raises(PermissionError):
        module._PostgresAuditWriter("postgresql://test", admission=None)

    forged_admission = object.__new__(module._RawAuditAdmission)
    forged_admission._issuer_token = object()
    forged_admission._expires_at = time.time() + 300
    connector = CapturingConnector(FakeConnection())
    with pytest.raises(PermissionError):
        module._PostgresAuditWriter(
            "postgresql://test",
            admission=forged_admission,
            connector=connector,
        )
    assert connector.calls == []


def test_direct_writer_denies_expired_admission_before_connecting() -> None:
    module = importlib.import_module("ai_graph.audit_postgres")
    admission = module._admission_from_env(_audit_sink_env())
    assert admission is not None
    connector = CapturingConnector(FakeConnection())
    writer = module._PostgresAuditWriter(
        "postgresql://test",
        admission=admission,
        connector=connector,
    )
    admission._expires_at = time.time() - 1

    session = writer.open_session(make_correlation())

    assert isinstance(session, NoOpAuditSession)
    assert connector.calls == []

def test_unavailable_revocation_verifier_denies_initial_raw_audit_write(capsys) -> None:
    module = importlib.import_module("ai_graph.audit_postgres")
    admission = module._admission_from_env(_audit_sink_env())
    assert admission is not None
    connector = CapturingConnector(FakeConnection())
    writer = module._PostgresAuditWriter(
        "postgresql://test",
        admission=admission,
        connector=connector,
    )

    session = writer.open_session(make_correlation())

    assert isinstance(session, NoOpAuditSession)
    assert connector.calls == []
    assert "ai_audit_failure" in capsys.readouterr().err

def test_active_env_admission_allows_raw_audit_write(capsys) -> None:
    module = importlib.import_module("ai_graph.audit_postgres")
    env = _audit_sink_env()
    env["AI_AUDIT_GATE_B_ADMISSION_REVOCATION_STATE"] = "active"
    admission = module._admission_from_env(env)
    assert admission is not None
    conn = FakeConnection()
    writer = module._PostgresAuditWriter(
        "postgresql://test",
        admission=admission,
        connector=CapturingConnector(conn),
    )
    session = writer.open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)

    session.start_agent_execution("Research", step_name="Research")

    assert any("INSERT INTO app.ai_agent_execution_log" in sql for sql, _ in conn.executions)
    assert "ai_audit_failure" not in capsys.readouterr().err

def test_write_time_expiry_denies_subsequent_raw_audit_write(capsys) -> None:
    module = importlib.import_module("ai_graph.audit_postgres")
    admission = _new_raw_audit_admission(time.time() + 300)
    conn = FakeConnection()
    writer = module._PostgresAuditWriter(
        "postgresql://test",
        admission=admission,
        connector=CapturingConnector(conn),
    )
    session = writer.open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)

    admission._expires_at = time.time() - 1
    before = audit_failure_count()
    writes_before_denial = len(conn.executions)
    session.start_agent_execution("Research", step_name="Research")

    assert len(conn.executions) == writes_before_denial
    assert conn.rollbacks == 1
    assert conn.close_calls == 1
    assert audit_failure_count() == before + 1
    assert "ai_audit_failure" in capsys.readouterr().err


def test_write_time_revocation_denies_subsequent_raw_audit_write(capsys) -> None:
    module = importlib.import_module("ai_graph.audit_postgres")
    env = _audit_sink_env()
    env["AI_AUDIT_GATE_B_ADMISSION_REVOCATION_STATE"] = "active"
    admission = module._admission_from_env(env)
    assert admission is not None
    conn = FakeConnection()
    writer = module._PostgresAuditWriter(
        "postgresql://test",
        admission=admission,
        connector=CapturingConnector(conn),
    )
    session = writer.open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)

    env["AI_AUDIT_GATE_B_ADMISSION_REVOCATION_STATE"] = "revoked"
    before = audit_failure_count()
    writes_before_denial = len(conn.executions)
    session.start_agent_execution("Research", step_name="Research")

    assert len(conn.executions) == writes_before_denial
    assert conn.rollbacks == 1
    assert conn.close_calls == 1
    assert audit_failure_count() == before + 1
    assert "ai_audit_failure" in capsys.readouterr().err


def test_write_time_claim_integrity_failure_denies_raw_audit_write(capsys) -> None:
    module = importlib.import_module("ai_graph.audit_postgres")
    env = _audit_sink_env()
    env["AI_AUDIT_GATE_B_ADMISSION_REVOCATION_STATE"] = "active"
    admission = module._admission_from_env(env)
    assert admission is not None
    conn = FakeConnection()
    writer = module._PostgresAuditWriter(
        "postgresql://test",
        admission=admission,
        connector=CapturingConnector(conn),
    )
    session = writer.open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)

    env["AI_AUDIT_GATE_B_ADMISSION_AUDIENCE"] = "tampered-audience"
    writes_before_denial = len(conn.executions)
    session.start_agent_execution("Research", step_name="Research")

    assert len(conn.executions) == writes_before_denial
    assert "ai_audit_failure" in capsys.readouterr().err


def test_unavailable_write_time_revocation_verifier_denies_raw_audit_write(capsys) -> None:
    module = importlib.import_module("ai_graph.audit_postgres")
    env = _audit_sink_env()
    env["AI_AUDIT_GATE_B_ADMISSION_REVOCATION_STATE"] = "active"
    admission = module._admission_from_env(env)
    assert admission is not None
    conn = FakeConnection()
    writer = module._PostgresAuditWriter(
        "postgresql://test",
        admission=admission,
        connector=CapturingConnector(conn),
    )
    session = writer.open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)

    del env["AI_AUDIT_GATE_B_ADMISSION_REVOCATION_STATE"]
    writes_before_denial = len(conn.executions)
    session.start_agent_execution("Research", step_name="Research")

    assert len(conn.executions) == writes_before_denial
    assert "ai_audit_failure" in capsys.readouterr().err


def test_write_time_revocation_keeps_analysis_result_successful(capsys) -> None:
    module = importlib.import_module("ai_graph.audit_postgres")
    query = "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어"
    baseline = run_analysis(query, trace_id="trace-write-time-revocation")
    env = _audit_sink_env()
    env["AI_AUDIT_GATE_B_ADMISSION_REVOCATION_STATE"] = "active"
    admission = module._admission_from_env(env)
    assert admission is not None
    conn = RevokingConnection(env)
    actual = run_analysis(
        query,
        trace_id="trace-write-time-revocation",
        audit_sink=_authorized_sink(
            "postgresql://test",
            admission=admission,
            connector=CapturingConnector(conn),
        ),
    )

    assert actual.status == baseline.status == "ready"
    statements = [statement for statement, _ in conn.executions]
    assert sum("INSERT INTO app.ai_trace" in sql for sql in statements) == 1
    assert not any("ai_agent_execution_log" in sql for sql in statements)
    assert "ai_audit_failure" in capsys.readouterr().err

def test_terminal_model_persistence_failure_stops_db_writes(capsys) -> None:
    conn = FakeConnection()
    session = _create_test_persistent_sink("postgresql://test",
    connector=CapturingConnector(conn),).open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)
    execution_id = session.start_agent_execution("Research", step_name="Research")
    call_id = session.start_model_call(
        task_type="research",
        provider="mock",
        model_name="deterministic",
        system_prompt="system",
        user_prompt="user",
        variables_jsonb={},
        prompt_template_name="research",
        prompt_version="v1",
        temperature=0.0,
        response_schema_name="research.v1",
        web_search_used=False,
        execution_id=execution_id,
    )
    conn.fail_matching = "UPDATE app.ai_model_call_log"
    executions_before_failure = len(conn.executions)

    session.finish_model_call(
        call_id,
        status="succeeded",
        assistant_response='{"ok":true}',
    )

    assert len(conn.executions) == executions_before_failure + 1
    assert "audit_persistence_failure" not in "\n".join(statement for statement, _ in conn.executions)
    assert conn.close_calls == 1
    assert "ai_audit_failure" in capsys.readouterr().err


def test_terminal_agent_persistence_failure_stops_db_writes(capsys) -> None:
    conn = FakeConnection()
    session = _create_test_persistent_sink("postgresql://test",
    connector=CapturingConnector(conn),).open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)
    execution_id = session.start_agent_execution("Research", step_name="Research")
    conn.fail_matching = "UPDATE app.ai_agent_execution_log"
    executions_before_failure = len(conn.executions)

    session.finish_agent_execution(execution_id, status="succeeded")

    assert len(conn.executions) == executions_before_failure + 1
    assert "audit_persistence_failure" not in "\n".join(statement for statement, _ in conn.executions)
    assert conn.close_calls == 1
    assert "ai_audit_failure" in capsys.readouterr().err


def test_connect_failure_returns_noop_and_emits_one_sanitized_signal(capsys) -> None:
    def fail_connect(*args, **kwargs):
        raise psycopg.OperationalError("password=must-not-appear")

    before = audit_failure_count()
    session = _create_test_persistent_sink("postgresql://secret", connector=fail_connect).open_session(
        make_correlation()
    )

    assert isinstance(session, NoOpAuditSession)
    assert audit_failure_count() == before + 1
    stderr = capsys.readouterr().err
    assert "ai_audit_failure" in stderr
    assert "password=must-not-appear" not in stderr
    assert "postgresql://secret" not in stderr


def test_failure_signal_stops_without_recursive_db_write(capsys) -> None:
    conn = RecursiveFailureConnection()
    session = _create_test_persistent_sink("postgresql://test",
    connector=CapturingConnector(conn),).open_session(make_correlation())
    assert not isinstance(session, NoOpAuditSession)
    before = audit_failure_count()
    executions_before_failure = len(conn.executions)
    conn.fail_after_open = True

    session.start_agent_execution("Research", step_name="Research")

    assert len(conn.executions) == executions_before_failure + 1
    assert conn.rollbacks == 1
    assert conn.close_calls == 1
    assert audit_failure_count() == before + 1
    stderr = capsys.readouterr().err
    assert "ai_audit_failure" in stderr
    assert "secret recursive SQL detail" not in stderr


@pytest.mark.parametrize(
    "failure",
    [
        psycopg.errors.UniqueViolation("injected unique violation"),
        psycopg.errors.QueryCanceled("injected statement timeout"),
    ],
)
def test_mid_session_sql_fault_does_not_change_analysis_result(failure, capsys) -> None:
    query = "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어"
    baseline = run_analysis(query, trace_id="trace-fail-open")
    conn = FakeConnection()
    conn.fail_matching = "INSERT INTO app.ai_agent_execution_log"
    conn.failure = failure

    actual = run_analysis(
        query,
        trace_id="trace-fail-open",
        audit_sink=_create_test_persistent_sink("postgresql://user:password@db/app",
        connector=CapturingConnector(conn),),
    )

    assert (
        actual.status,
        actual.trace_id,
        actual.user_payload,
        actual.strategy_spec,
        actual.failure_cause,
        actual.retryable,
    ) == (
        baseline.status,
        baseline.trace_id,
        baseline.user_payload,
        baseline.strategy_spec,
        baseline.failure_cause,
        baseline.retryable,
    )
    assert conn.close_calls == 1
    stderr = capsys.readouterr().err
    assert stderr.count("ai_audit_failure") == 1
    assert "password" not in stderr
    assert "injected" not in stderr


def test_ready_analysis_with_postgres_sink_persists_all_calls_and_finalizes(capsys) -> None:
    conn = FakeConnection()

    envelope = run_analysis(
        "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어",
        trace_id="trace-postgres-ready",
        audit_sink=_create_test_persistent_sink("postgresql://test",
        connector=CapturingConnector(conn),),
    )

    statements = [statement for statement, _ in conn.executions]
    assert envelope.status == "ready"
    assert sum("INSERT INTO app.ai_agent_execution_log" in sql for sql in statements) == 10
    assert sum("INSERT INTO app.ai_model_call_log" in sql for sql in statements) == 10
    assert sum("INSERT INTO app.ai_prompt_log" in sql for sql in statements) == 10
    assert sum("UPDATE app.ai_agent_execution_log" in sql for sql in statements) == 10
    assert sum("UPDATE app.ai_model_call_log" in sql for sql in statements) == 10
    assert sum("UPDATE app.ai_prompt_log" in sql for sql in statements) == 10
    assert sum("UPDATE app.ai_trace" in sql for sql in statements) == 1
    assert conn.close_calls == 1
    assert "ai_audit_failure" not in capsys.readouterr().err


@pytest.mark.skipif(
    not os.getenv("AI_LOGGING_TEST_DSN"),
    reason="AI_LOGGING_TEST_DSN must point to a disposable TimescaleDB database",
)
def test_disposable_timescaledb_migrations_and_large_unicode_round_trip() -> None:
    dsn = os.environ["AI_LOGGING_TEST_DSN"]
    migrations_dir = Path(__file__).resolve().parents[2] / "service_db" / "migrations"
    migrations = sorted(migrations_dir.glob("*.sql"))
    assert migrations

    with psycopg.connect(dsn, autocommit=True) as conn:
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))
        conn.execute(
            (migrations_dir / "013_ai_runtime_logging.sql").read_text(encoding="utf-8")
        )
        columns = {
            row[0]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'app'
                  AND table_name = 'ai_model_call_log'
                  AND column_name IN (
                    'execution_id', 'response_schema_name', 'web_search_used'
                  )
                """
            )
        }
        assert columns == {"execution_id", "response_schema_name", "web_search_used"}
        fk_definition = conn.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'fk_ai_model_call_log_execution'
              AND conrelid = 'app.ai_model_call_log'::regclass
            """
        ).fetchone()
        assert fk_definition is not None
        assert "FOREIGN KEY (execution_id)" in fk_definition[0]
        assert "ON DELETE SET NULL" in fk_definition[0]
        indexes = {
            row[0]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'app'
                  AND indexname IN (
                    'idx_ai_model_call_log_execution_created',
                    'idx_ai_prompt_log_retention'
                  )
                """
            )
        }
        assert indexes == {
            "idx_ai_model_call_log_execution_created",
            "idx_ai_prompt_log_retention",
        }
        prompt_unique = conn.execute(
            """
            SELECT count(*)
            FROM pg_constraint
            WHERE conrelid = 'app.ai_prompt_log'::regclass
              AND contype = 'u'
              AND pg_get_constraintdef(oid) = 'UNIQUE (call_id)'
            """
        ).fetchone()
        assert prompt_unique == (1,)

    correlation = create_audit_correlation(
        db_trace_id=uuid4(),
        trace_id="large-unicode-test",
        debug_ref="debug-large-unicode-test",
        entrypoint="test.postgres",
        feature="large_content",
    )
    large_text = "가" * 349_525 + "x"
    assert len(large_text.encode("utf-8")) == 1024 * 1024
    variables = {"payload": large_text}
    session = _create_test_persistent_sink(dsn).open_session(correlation)
    assert not isinstance(session, NoOpAuditSession)

    try:
        execution_id = session.start_agent_execution("Research", step_name="Research")
        call_id = session.start_model_call(
            task_type="large_content",
            provider="mock",
            model_name="deterministic",
            system_prompt=large_text,
            user_prompt=large_text,
            variables_jsonb=variables,
            prompt_template_name="large_content",
            prompt_version="v1",
            temperature=0.0,
            response_schema_name="large-content.v1",
            web_search_used=False,
            execution_id=execution_id,
        )
        session.finish_model_call(
            call_id,
            status="succeeded",
            assistant_response=large_text,
            model_name="deterministic",
        )
        session.record_error(
            "verification",
            error_type="VerificationError",
            message="sanitized verification error",
            call_id=call_id,
            execution_id=execution_id,
        )
        session.finish_agent_execution(execution_id, status="succeeded")
        session.record_finalization("completed")

        with psycopg.connect(dsn) as conn:
            row = conn.execute(
                """
                SELECT trace.status, agent.status, model.status,
                       prompt.system_prompt, prompt.user_prompt,
                       prompt.variables_jsonb, prompt.assistant_response,
                       error.error_type
                FROM app.ai_trace AS trace
                JOIN app.ai_agent_execution_log AS agent USING (trace_id)
                JOIN app.ai_model_call_log AS model
                  ON model.trace_id = trace.trace_id
                 AND model.execution_id = agent.execution_id
                JOIN app.ai_prompt_log AS prompt USING (call_id)
                JOIN app.ai_error_log AS error
                  ON error.trace_id = trace.trace_id
                 AND error.execution_id = agent.execution_id
                 AND error.call_id = model.call_id
                WHERE trace.trace_id = %s
                """,
                (correlation.db_trace_id,),
            ).fetchone()

        assert row is not None
        assert row[:3] == ("completed", "succeeded", "succeeded")
        for value in (row[3], row[4], row[6]):
            assert value == large_text
            assert len(value.encode("utf-8")) == 1024 * 1024
            assert sha256(value.encode("utf-8")).digest() == sha256(
                large_text.encode("utf-8")
            ).digest()
        assert row[5] == variables
        assert sha256(
            json.dumps(row[5], ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).digest() == sha256(
            json.dumps(variables, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).digest()
        assert row[7] == "VerificationError"

        retention_script = Path(__file__).resolve().parents[2] / "DE" / "scripts" / (
            "purge_ai_prompt_logs.py"
        )
        spec = importlib.util.spec_from_file_location(
            "ai_logging_retention_integration",
            retention_script,
        )
        assert spec is not None and spec.loader is not None
        retention = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(retention)
        retention_call_ids = [uuid4(), uuid4(), uuid4()]
        retention_prompt_ids = [uuid4(), uuid4(), uuid4()]
        with psycopg.connect(dsn) as conn:
            cutoff = conn.execute("SELECT now() - INTERVAL '90 days'").fetchone()[0]
            timestamps = [
                cutoff - timedelta(microseconds=1),
                cutoff,
                cutoff + timedelta(microseconds=1),
            ]
            for test_call_id, prompt_id, created_at in zip(
                retention_call_ids,
                retention_prompt_ids,
                timestamps,
                strict=True,
            ):
                conn.execute(
                    """
                    INSERT INTO app.ai_model_call_log (
                        call_id, trace_id, task_type, provider, status, created_at
                    ) VALUES (%s, %s, 'retention_test', 'mock', 'succeeded', %s)
                    """,
                    (test_call_id, correlation.db_trace_id, created_at),
                )
                conn.execute(
                    """
                    INSERT INTO app.ai_prompt_log (
                        prompt_log_id, call_id, system_prompt, user_prompt,
                        assistant_response, variables_jsonb, created_at
                    ) VALUES (%s, %s, 'system', 'user', 'assistant', '{}'::jsonb, %s)
                    """,
                    (prompt_id, test_call_id, created_at),
                )

            assert retention.purge_expired_prompt_logs(conn) == 1
            remaining_prompt_ids = {
                row[0]
                for row in conn.execute(
                    "SELECT prompt_log_id FROM app.ai_prompt_log WHERE call_id = ANY(%s)",
                    (retention_call_ids,),
                )
            }
            remaining_model_calls = conn.execute(
                "SELECT count(*) FROM app.ai_model_call_log WHERE call_id = ANY(%s)",
                (retention_call_ids,),
            ).fetchone()[0]
            parent_counts = conn.execute(
                """
                SELECT
                    (SELECT count(*) FROM app.ai_trace WHERE trace_id = %s),
                    (SELECT count(*) FROM app.ai_agent_execution_log WHERE trace_id = %s),
                    (SELECT count(*) FROM app.ai_error_log WHERE trace_id = %s)
                """,
                (
                    correlation.db_trace_id,
                    correlation.db_trace_id,
                    correlation.db_trace_id,
                ),
            ).fetchone()

        assert remaining_prompt_ids == set(retention_prompt_ids[1:])
        assert remaining_model_calls == 3
        assert parent_counts == (1, 1, 1)
    finally:
        session.close()
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "DELETE FROM app.ai_prompt_log WHERE call_id IN "
                "(SELECT call_id FROM app.ai_model_call_log WHERE trace_id = %s)",
                (correlation.db_trace_id,),
            )
            conn.execute(
                "DELETE FROM app.ai_error_log WHERE trace_id = %s",
                (correlation.db_trace_id,),
            )
            conn.execute(
                "DELETE FROM app.ai_model_call_log WHERE trace_id = %s",
                (correlation.db_trace_id,),
            )
            conn.execute(
                "DELETE FROM app.ai_agent_execution_log WHERE trace_id = %s",
                (correlation.db_trace_id,),
            )
            conn.execute(
                "DELETE FROM app.ai_trace WHERE trace_id = %s",
                (correlation.db_trace_id,),
            )
