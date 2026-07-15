from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.db.ai_backtest_repository import SqlAIBacktestRepository
from app.schemas.ai_backtest import (
    AICodeBacktestFlowRequest,
    AIBacktestExecutionContext,
    AITraceCreate,
    ModelCallLogBundle,
    PromptLogBundle,
)
from app.services.raw_audit_admission import RawAuditAdmission, issue_raw_audit_admission


class FakeResult:
    def __init__(self, row=None) -> None:
        self.row = row
        self.rowcount = 1

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeConnection:
    def __init__(self, *, fail_on: int | None = None, responses: list[dict | None] | None = None) -> None:
        self.executions = []
        self.fail_on = fail_on
        self.responses = responses

    async def execute(self, statement, params):
        self.executions.append((str(statement), params))
        if self.fail_on == len(self.executions):
            raise RuntimeError("injected constraint failure")
        if self.responses is not None:
            return FakeResult(self.responses.pop(0))
        return SimpleNamespace(rowcount=1)


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.exited_with = None

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.exited_with = exc_type


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.transaction = FakeTransaction(connection)
        self.begin_calls = 0

    def begin(self) -> FakeTransaction:
        self.begin_calls += 1
        return self.transaction


def make_bundle() -> ModelCallLogBundle:
    return ModelCallLogBundle(
        task_type="backtest_code_generation",
        provider="aoai",
        model_name="gpt-test",
        response_schema_name="quantagent.backtest_code.v1",
        web_search_used=True,
        status="succeeded",
        prompt_log=PromptLogBundle(
            system_prompt="full system prompt",
            user_prompt="full user prompt",
            assistant_response="full assistant response",
            masked=False,
        ),
    )

_RAW_AUDIT_SECRET = "test-raw-audit-admission-secret"
_RAW_AUDIT_KEY_VERSION = "test-v1"
_RAW_AUDIT_AUDIENCE = "quantagent.backend.raw-audit"
_RAW_AUDIT_EVIDENCE_ID = "gate-b-evidence-001"
_RAW_AUDIT_REVISION = "revision-9"


def _base64url_json(value: dict[str, object]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def _signed_admission_token(claim_overrides: dict[str, object] | None = None) -> str:
    claims: dict[str, object] = {
        "audience": _RAW_AUDIT_AUDIENCE,
        "deployment_revision": _RAW_AUDIT_REVISION,
        "evidence_id": _RAW_AUDIT_EVIDENCE_ID,
        "expiry": time.time() + 300,
        "issued_at": time.time() - 1,
        "key_version": _RAW_AUDIT_KEY_VERSION,
    }
    claims.update(claim_overrides or {})
    header = {"alg": "HS256", "key_version": _RAW_AUDIT_KEY_VERSION}
    signing_input = f"{_base64url_json(header)}.{_base64url_json(claims)}"
    signature = hmac.new(
        _RAW_AUDIT_SECRET.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def _raw_admission_settings(
    *,
    token: str | None = None,
    claim_overrides: dict[str, object] | None = None,
) -> Settings:
    return Settings.model_construct(
        app_env="production",
        ai_backtest_raw_audit_admission_hmac_secret=SecretStr(_RAW_AUDIT_SECRET),
        ai_backtest_raw_audit_admission_hmac_key_version=_RAW_AUDIT_KEY_VERSION,
        ai_backtest_raw_audit_admission_token=SecretStr(token or _signed_admission_token(claim_overrides)),
        ai_backtest_raw_audit_admission_audience=_RAW_AUDIT_AUDIENCE,
        ai_backtest_raw_audit_evidence_id=_RAW_AUDIT_EVIDENCE_ID,
        ai_backtest_raw_audit_deployment_revision=_RAW_AUDIT_REVISION,
    )


def make_admission() -> RawAuditAdmission:
    admission = issue_raw_audit_admission(_raw_admission_settings())
    assert admission is not None
    return admission


def test_model_call_requires_one_prompt_bundle() -> None:
    with pytest.raises(ValidationError):
        ModelCallLogBundle(task_type="backtest_code_generation")


def test_model_call_rejects_missing_raw_admission_before_opening_transaction() -> None:
    connection = FakeConnection()
    engine = FakeEngine(connection)
    repository = SqlAIBacktestRepository(engine)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        asyncio.run(
            repository.create_model_call_log(
                trace_id=None,
                execution_id=None,
                user_id=None,
                session_id=None,
                message_id=None,
                code_id=None,
                bundle=make_bundle(),
            )
        )

    assert engine.begin_calls == 0
    assert connection.executions == []


@pytest.mark.parametrize(
    "admission",
    [None, object(), object.__new__(RawAuditAdmission)],
)
def test_model_call_rejects_unverified_raw_admission_before_opening_transaction(admission: object) -> None:
    connection = FakeConnection()
    engine = FakeEngine(connection)
    repository = SqlAIBacktestRepository(engine)  # type: ignore[arg-type]

    call_id = asyncio.run(
        repository.create_model_call_log(
            trace_id=None,
            execution_id=None,
            user_id=None,
            session_id=None,
            message_id=None,
            code_id=None,
            bundle=make_bundle(),
            raw_audit_admission=admission,  # type: ignore[arg-type]
        )
    )

    assert call_id is None
    assert engine.begin_calls == 0
    assert connection.executions == []
def test_invalid_signed_admissions_never_open_a_raw_audit_transaction() -> None:
    invalid_settings = [
        _raw_admission_settings(token=_signed_admission_token().rsplit(".", 1)[0]),
        _raw_admission_settings(token=f"{_signed_admission_token()}x"),
        _raw_admission_settings(
            claim_overrides={"expiry": time.time() - 1, "issued_at": time.time() - 2}
        ),
        _raw_admission_settings(claim_overrides={"audience": "different-service"}),
        _raw_admission_settings(claim_overrides={"deployment_revision": "revision-stale"}),
        _raw_admission_settings(claim_overrides={"key_version": "retired-v0"}),
    ]

    for settings in invalid_settings:
        admission = issue_raw_audit_admission(settings)
        assert admission is None
        connection = FakeConnection()
        engine = FakeEngine(connection)
        repository = SqlAIBacktestRepository(engine)  # type: ignore[arg-type]

        call_id = asyncio.run(
            repository.create_model_call_log(
                trace_id=None,
                execution_id=None,
                user_id=None,
                session_id=None,
                message_id=None,
                code_id=None,
                bundle=make_bundle(),
                raw_audit_admission=admission,  # type: ignore[arg-type]
            )
        )

        assert call_id is None
        assert engine.begin_calls == 0
        assert connection.executions == []


def test_model_and_prompt_use_one_transaction_and_execution_correlation() -> None:
    connection = FakeConnection()
    engine = FakeEngine(connection)
    repository = SqlAIBacktestRepository(engine)  # type: ignore[arg-type]
    trace_id = uuid4()
    execution_id = uuid4()

    call_id = asyncio.run(
        repository.create_model_call_log(
            trace_id=trace_id,
            execution_id=execution_id,
            user_id=7,
            session_id=None,
            message_id=None,
            code_id=None,
            bundle=make_bundle(),
            raw_audit_admission=make_admission(),
        )
    )

    assert engine.begin_calls == 1
    assert len(connection.executions) == 2
    model_sql, model_params = connection.executions[0]
    prompt_sql, prompt_params = connection.executions[1]
    assert "execution_id" in model_sql
    assert model_params["trace_id"] == str(trace_id)
    assert model_params["execution_id"] == str(execution_id)
    assert model_params["response_schema_name"] == "quantagent.backtest_code.v1"
    assert model_params["web_search_used"] is True
    assert prompt_params["call_id"] == model_params["call_id"] == str(call_id)
    assert prompt_params["system_prompt"] == "full system prompt"
    assert prompt_params["user_prompt"] == "full user prompt"
    assert prompt_params["assistant_response"] == "full assistant response"
    assert "INSERT INTO app.ai_prompt_log" in prompt_sql


def test_prompt_insert_failure_exits_the_shared_transaction_with_error() -> None:
    connection = FakeConnection(fail_on=2)
    engine = FakeEngine(connection)
    repository = SqlAIBacktestRepository(engine)  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc_info:
        asyncio.run(
            repository.create_model_call_log(
                trace_id=uuid4(),
                execution_id=uuid4(),
                user_id=None,
                session_id=None,
                message_id=None,
                code_id=None,
                bundle=make_bundle(),
                raw_audit_admission=make_admission(),
            )
        )

    assert exc_info.value.code == "db_query_failed"
    assert engine.begin_calls == 1
    assert engine.transaction.exited_with is RuntimeError
def test_process_identity_is_committed_before_subprocess_release() -> None:
    connection = FakeConnection()
    engine = FakeEngine(connection)
    repository = SqlAIBacktestRepository(engine)  # type: ignore[arg-type]
    execution_run_id = uuid4()
    attempt_id = uuid4()
    started_at = datetime.now(UTC)

    asyncio.run(
        repository.record_code_execution_process_identity(
            execution_run_id,
            attempt_id=attempt_id,
            worker_host="worker-a",
            worker_pid=123,
            worker_pgid=123,
            worker_started_at=started_at,
        )
    )

    assert engine.begin_calls == 1
    assert engine.transaction.exited_with is None
    sql, params = connection.executions[0]
    assert "UPDATE app.code_execution_run" in sql
    assert params == {
        "execution_run_id": str(execution_run_id),
        "attempt_id": str(attempt_id),
        "worker_host": "worker-a",
        "worker_pid": 123,
        "worker_pgid": 123,
        "worker_started_at": started_at,
    }
def make_replacement_claim(*, approval_id=None, approval_token=None) -> tuple[AICodeBacktestFlowRequest, AITraceCreate]:
    context = AIBacktestExecutionContext(
        user_id=7,
        scope_family_id=uuid4(),
        session_hmac="a" * 64,
        session_hmac_version="test-v1",
    )
    request = AICodeBacktestFlowRequest(
        user_id=context.user_id,
        execution_context=context,
        idempotency_key="replacement-claim-key",
        request_fingerprint="f" * 64,
        fingerprint_version="ai-backtest-intent-v1",
        replacement_approval_id=approval_id,
        replacement_approval_token=approval_token,
        natural_language_prompt="closed request replacement",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )
    return request, AITraceCreate(trace_id=uuid4(), user_id=context.user_id)


def closed_request_row(request: AICodeBacktestFlowRequest) -> dict:
    return {
        "request_id": uuid4(),
        "trace_id": uuid4(),
        "state": "failed",
        "safety_lease": "closed",
        "state_version": 4,
        "terminal_response_jsonb": None,
        "scope_family_id": request.execution_context.scope_family_id,
        "fingerprint_version": request.fingerprint_version,
        "payload_fingerprint": request.request_fingerprint,
    }


def test_closed_request_rejects_replacement_without_operator_approval() -> None:
    request, trace = make_replacement_claim()
    connection = FakeConnection(responses=[None, None, closed_request_row(request)])
    repository = SqlAIBacktestRepository(FakeEngine(connection))  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc_info:
        asyncio.run(repository.claim_idempotent_request(request, trace=trace))

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "terminal_evidence_required"
    assert all("replacement_approval" not in sql for sql, _ in connection.executions)


def test_operator_approval_requires_terminal_evidence_and_hashes_its_token() -> None:
    source_request_id = uuid4()
    scope_family_id = uuid4()
    connection = FakeConnection(
        responses=[
            {
                "request_id": source_request_id,
                "scope_family_id": scope_family_id,
                "fingerprint_version": "ai-backtest-intent-v1",
                "payload_fingerprint": "f" * 64,
                "state": "failed",
                "safety_lease": "closed",
                "terminal_evidence_jsonb": {"operator": "verified"},
            },
            None,
            None,
            None,
        ]
    )
    repository = SqlAIBacktestRepository(FakeEngine(connection))  # type: ignore[arg-type]

    approval = asyncio.run(
        repository.operator_issue_replacement_approval(
            source_request_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )

    assert approval.source_request_id == source_request_id
    assert approval.approval_token.get_secret_value()
    insert_sql, insert_params = connection.executions[-1]
    assert "INSERT INTO app.ai_backtest_replacement_approval" in insert_sql
    assert insert_params["replacement_key_hash"] != approval.approval_token.get_secret_value()
    assert len(insert_params["replacement_key_hash"]) == 64


def test_operator_approval_rejects_closed_request_without_terminal_evidence() -> None:
    source_request_id = uuid4()
    connection = FakeConnection(
        responses=[
            {
                "request_id": source_request_id,
                "scope_family_id": uuid4(),
                "fingerprint_version": "ai-backtest-intent-v1",
                "payload_fingerprint": "f" * 64,
                "state": "failed",
                "safety_lease": "closed",
                "terminal_evidence_jsonb": None,
            }
        ]
    )
    repository = SqlAIBacktestRepository(FakeEngine(connection))  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc_info:
        asyncio.run(
            repository.operator_issue_replacement_approval(
                source_request_id,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "terminal_evidence_required"


def test_replacement_approval_consumption_is_scoped_and_single_use() -> None:
    approval_id = uuid4()
    approval_token = "a" * 43
    request, trace = make_replacement_claim(
        approval_id=approval_id,
        approval_token=approval_token,
    )
    source = closed_request_row(request)
    connection = FakeConnection(
        responses=[
            None,
            None,
            closed_request_row(request),
            {
                "approval_id": approval_id,
                "source_request_id": source["request_id"],
                "scope_family_id": request.execution_context.scope_family_id,
                "fingerprint_version": request.fingerprint_version,
                "payload_fingerprint": request.request_fingerprint,
                "replacement_key_hash": hashlib.sha256(approval_token.encode()).hexdigest(),
                "status": "issued",
                "expires_at": datetime.now(UTC) + timedelta(minutes=5),
            },
            {"request_id": source["request_id"]},
            {"approval_id": approval_id},
            {
                "request_id": uuid4(),
                "trace_id": None,
                "state": "claimed",
                "safety_lease": "active",
                "state_version": 1,
                "terminal_response_jsonb": None,
            },
            None,
            None,
        ]
    )
    repository = SqlAIBacktestRepository(FakeEngine(connection))  # type: ignore[arg-type]

    claim = asyncio.run(repository.claim_idempotent_request(request, trace=trace))

    assert claim.trace_id == trace.trace_id
    assert "pg_advisory_xact_lock" in connection.executions[0][0]
    approval_sql = "\n".join(sql for sql, _ in connection.executions)
    assert "status = 'consumed'" in approval_sql
    assert "status = 'issued'" in approval_sql
    assert "expires_at > :consumed_at" in approval_sql
    assert "terminal_evidence_jsonb IS NOT NULL" in approval_sql
@pytest.mark.parametrize(
    "approval_overrides",
    [
        {"scope_family_id": uuid4()},
        {"fingerprint_version": "other-fingerprint-version"},
        {"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        {"status": "consumed"},
    ],
)
def test_replacement_rejects_wrong_scope_expired_or_reused_approval(approval_overrides: dict) -> None:
    approval_id = uuid4()
    approval_token = "a" * 43
    request, trace = make_replacement_claim(
        approval_id=approval_id,
        approval_token=approval_token,
    )
    approval = {
        "approval_id": approval_id,
        "source_request_id": uuid4(),
        "scope_family_id": request.execution_context.scope_family_id,
        "fingerprint_version": request.fingerprint_version,
        "payload_fingerprint": request.request_fingerprint,
        "replacement_key_hash": hashlib.sha256(approval_token.encode()).hexdigest(),
        "status": "issued",
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
    }
    approval.update(approval_overrides)
    connection = FakeConnection(
        responses=[None, None, closed_request_row(request), approval]
    )
    repository = SqlAIBacktestRepository(FakeEngine(connection))  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc_info:
        asyncio.run(repository.claim_idempotent_request(request, trace=trace))

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "replacement_approval_invalid"
