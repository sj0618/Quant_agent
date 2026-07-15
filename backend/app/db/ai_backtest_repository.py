from __future__ import annotations

import json
import hashlib
from collections.abc import Mapping
from secrets import token_urlsafe
from datetime import UTC, date, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import redact_secrets
from app.core.errors import AppError
from app.schemas.ai_backtest import (
    AIBacktestReportCreate,
    AICodeGenerationCreate,
    AICodeValidationResultCreate,
    AIErrorLogCreate,
    AIStrategyParseCreate,
    AITraceCreate,
    AgentExecutionLogCreate,
    AIBacktestRequestClaim,
    AIBacktestReplacementApproval,
    AICodeBacktestFlowRequest,
    AgentExecutionLogUpdate,
    BacktestResultPayload,
    CodeExecutionRunCreate,
    CodeExecutionRunUpdate,
    ModelCallLogBundle,
)
from app.services.raw_audit_admission import RawAuditAdmission, verify_raw_audit_admission


class AIBacktestRepository(Protocol):
    async def claim_idempotent_request(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace: AITraceCreate,
    ) -> AIBacktestRequestClaim: ...

    async def transition_idempotent_request(
        self,
        request_id: UUID,
        *,
        expected_state: str,
        next_state: str,
        safety_lease: str | None = None,
        execution_run_id: UUID | None = None,
        terminal_response: Mapping[str, Any] | None = None,
        terminal_evidence: Mapping[str, Any] | None = None,
    ) -> AIBacktestRequestClaim: ...
    async def release_armed_execution_request(
        self,
        request_id: UUID,
        *,
        expected_state_version: int,
        execution_run_id: UUID,
        attempt_id: UUID,
    ) -> AIBacktestRequestClaim: ...
    async def operator_terminalize_idempotent_request(
        self,
        request_id: UUID,
        *,
        expected_state: str,
        expected_state_version: int,
        terminal_state: str,
        terminal_evidence: Mapping[str, Any],
    ) -> AIBacktestRequestClaim: ...
    async def operator_record_terminal_evidence(
        self,
        request_id: UUID,
        *,
        expected_state: str,
        expected_state_version: int,
        terminal_evidence: Mapping[str, Any],
    ) -> AIBacktestRequestClaim: ...
    async def operator_issue_replacement_approval(
        self,
        source_request_id: UUID,
        *,
        expires_at: datetime,
    ) -> AIBacktestReplacementApproval: ...


    async def create_trace(self, record: AITraceCreate) -> UUID: ...

    async def finish_trace(
        self,
        trace_id: UUID,
        *,
        status: str,
        metadata_jsonb: Mapping[str, Any] | None = None,
        ended_at: datetime | None = None,
    ) -> None: ...

    async def create_strategy_parse(self, record: AIStrategyParseCreate) -> UUID: ...

    async def create_code_generation(self, record: AICodeGenerationCreate) -> UUID: ...

    async def update_code_generation_status(self, code_id: UUID, status: str) -> None: ...

    async def create_code_validation_result(self, record: AICodeValidationResultCreate) -> UUID: ...

    async def create_code_execution_run(self, record: CodeExecutionRunCreate) -> UUID: ...

    async def update_code_execution_run(self, execution_run_id: UUID, update: CodeExecutionRunUpdate) -> None: ...
    async def record_code_execution_process_identity(
        self,
        execution_run_id: UUID,
        *,
        attempt_id: UUID,
        worker_host: str,
        worker_pid: int,
        worker_pgid: int,
        worker_started_at: datetime,
        idempotency_request_id: UUID | None = None,
    ) -> None: ...

    async def persist_backtest_result(self, payload: BacktestResultPayload) -> UUID: ...

    async def create_ai_backtest_report(self, record: AIBacktestReportCreate) -> UUID: ...

    async def create_model_call_log(
        self,
        *,
        trace_id: UUID | None,
        execution_id: UUID | None,
        user_id: int | None,
        session_id: UUID | None,
        message_id: UUID | None,
        code_id: UUID | None,
        bundle: ModelCallLogBundle,
        raw_audit_admission: RawAuditAdmission,
    ) -> UUID | None: ...

    async def create_agent_execution_log(self, record: AgentExecutionLogCreate) -> UUID: ...

    async def update_agent_execution_log(self, execution_id: UUID, update: AgentExecutionLogUpdate) -> None: ...

    async def create_error_log(self, record: AIErrorLogCreate) -> UUID: ...


class SqlAIBacktestRepository:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def claim_idempotent_request(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace: AITraceCreate,
    ) -> AIBacktestRequestClaim:
        context = request.execution_context
        if (
            context is None
            or request.idempotency_key is None
            or request.request_fingerprint is None
            or request.fingerprint_version is None
        ):
            raise AppError(
                status_code=401,
                component="ai_backtest",
                code="execution_context_required",
                message="Authenticated execution context is required",
            )

        request_id = uuid4()
        advisory_key = _scope_advisory_key(
            context.scope_family_id,
            request.fingerprint_version,
            request.request_fingerprint,
        )
        try:
            async with self.engine.begin() as conn:
                await conn.execute(
                    text("SELECT pg_advisory_xact_lock(CAST(:lock_key AS bigint))"),
                    {"lock_key": advisory_key},
                )
                key_row = (
                    await conn.execute(
                        text(
                            """
                            SELECT request_id, trace_id, state, safety_lease, state_version,
                                   terminal_response_jsonb, payload_fingerprint, fingerprint_version
                            FROM app.ai_backtest_request
                            WHERE scope_family_id = :scope_family_id
                              AND client_request_key = :client_request_key
                            FOR UPDATE
                            """
                        ),
                        {
                            "scope_family_id": str(context.scope_family_id),
                            "client_request_key": request.idempotency_key,
                        },
                    )
                ).mappings().first()
                if key_row is not None:
                    if (
                        key_row["payload_fingerprint"] != request.request_fingerprint
                        or key_row["fingerprint_version"] != request.fingerprint_version
                    ):
                        raise AppError(
                            status_code=409,
                            component="ai_backtest",
                            code="idempotency_key_reused",
                            message="Idempotency key was reused with a different request",
                            details={"request_id": str(key_row["request_id"])},
                        )
                    return _claim_from_row(key_row)

                prior = (
                    await conn.execute(
                        text(
                            """
                            SELECT request_id, trace_id, state, safety_lease, state_version,
                                   terminal_response_jsonb
                            FROM app.ai_backtest_request
                            WHERE scope_family_id = :scope_family_id
                              AND fingerprint_version = :fingerprint_version
                              AND payload_fingerprint = :payload_fingerprint
                            ORDER BY CASE WHEN safety_lease IN ('active', 'blocked_unknown') THEN 0 ELSE 1 END,
                                     created_at DESC
                            FOR UPDATE
                            """
                        ),
                        {
                            "scope_family_id": str(context.scope_family_id),
                            "fingerprint_version": request.fingerprint_version,
                            "payload_fingerprint": request.request_fingerprint,
                        },
                    )
                ).mappings().first()
                if prior is not None:
                    if prior["safety_lease"] in {"active", "blocked_unknown"}:
                        return _claim_from_row(prior)
                    if request.replacement_approval_id is None or request.replacement_approval_token is None:
                        raise AppError(
                            status_code=409,
                            component="ai_backtest",
                            code="terminal_evidence_required",
                            message="A replacement approval is required",
                            details={"request_id": str(prior["request_id"])},
                        )
                    approval = (
                        await conn.execute(
                            text(
                                """
                                SELECT approval_id, source_request_id, scope_family_id, fingerprint_version,
                                       payload_fingerprint, replacement_key_hash, status, expires_at
                                FROM app.ai_backtest_replacement_approval
                                WHERE approval_id = :approval_id
                                FOR UPDATE
                                """
                            ),
                            {"approval_id": str(request.replacement_approval_id)},
                        )
                    ).mappings().first()
                    if (
                        approval is None
                        or str(approval["scope_family_id"]) != str(context.scope_family_id)
                        or approval["fingerprint_version"] != request.fingerprint_version
                        or approval["payload_fingerprint"] != request.request_fingerprint
                        or approval["replacement_key_hash"]
                        != _replacement_key_hash(request.replacement_approval_token.get_secret_value())
                        or approval["status"] != "issued"
                        or approval["expires_at"] <= _utcnow()
                    ):
                        raise AppError(
                            status_code=409,
                            component="ai_backtest",
                            code="replacement_approval_invalid",
                            message="Replacement approval is invalid",
                        )
                    source = (
                        await conn.execute(
                            text(
                                """
                                SELECT request_id
                                FROM app.ai_backtest_request
                                WHERE request_id = :source_request_id
                                  AND scope_family_id = :scope_family_id
                                  AND fingerprint_version = :fingerprint_version
                                  AND payload_fingerprint = :payload_fingerprint
                                  AND state IN ('succeeded', 'failed', 'abandoned')
                                  AND safety_lease = 'closed'
                                  AND terminal_evidence_jsonb IS NOT NULL
                                FOR UPDATE
                                """
                            ),
                            {
                                "source_request_id": str(approval["source_request_id"]),
                                "scope_family_id": str(context.scope_family_id),
                                "fingerprint_version": request.fingerprint_version,
                                "payload_fingerprint": request.request_fingerprint,
                            },
                        )
                    ).mappings().first()
                    if source is None:
                        raise AppError(
                            status_code=409,
                            component="ai_backtest",
                            code="terminal_evidence_required",
                            message="Terminal evidence is required before replacement",
                        )
                    consumed = (
                        await conn.execute(
                            text(
                                """
                                UPDATE app.ai_backtest_replacement_approval
                                SET status = 'consumed',
                                    consumed_at = :consumed_at
                                WHERE approval_id = :approval_id
                                  AND status = 'issued'
                                  AND expires_at > :consumed_at
                                RETURNING approval_id
                                """
                            ),
                            {
                                "approval_id": str(request.replacement_approval_id),
                                "consumed_at": _utcnow(),
                            },
                        )
                    ).mappings().first()
                    if consumed is None:
                        raise AppError(
                            status_code=409,
                            component="ai_backtest",
                            code="replacement_approval_invalid",
                            message="Replacement approval is invalid",
                        )
                inserted = (
                    await conn.execute(
                        text(
                            """
                            INSERT INTO app.ai_backtest_request (
                                request_id, scope_family_id, client_request_key,
                                payload_fingerprint, fingerprint_version, session_hmac,
                                session_hmac_version, state, safety_lease
                            ) VALUES (
                                :request_id, :scope_family_id, :client_request_key,
                                :payload_fingerprint, :fingerprint_version, :session_hmac,
                                :session_hmac_version, 'claimed', 'active'
                            )
                            ON CONFLICT DO NOTHING
                            RETURNING request_id, trace_id, state, safety_lease, state_version,
                                      terminal_response_jsonb
                            """
                        ),
                        {
                            "request_id": str(request_id),
                            "scope_family_id": str(context.scope_family_id),
                            "client_request_key": request.idempotency_key,
                            "payload_fingerprint": request.request_fingerprint,
                            "fingerprint_version": request.fingerprint_version,
                            "session_hmac": context.session_hmac,
                            "session_hmac_version": context.session_hmac_version,
                        },
                    )
                ).mappings().first()
                if inserted is not None:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO app.ai_trace (
                                trace_id, user_id, session_id, trace_kind, status,
                                metadata_jsonb, started_at, ended_at
                            ) VALUES (
                                :trace_id, :user_id, :session_id, :trace_kind, :status,
                                :metadata_jsonb::jsonb, :started_at, :ended_at
                            )
                            """
                        ),
                        {
                            "trace_id": str(trace.trace_id),
                            "user_id": trace.user_id,
                            "session_id": str(trace.session_id) if trace.session_id else None,
                            "trace_kind": trace.trace_kind,
                            "status": trace.status,
                            "metadata_jsonb": _json_dumps(trace.metadata_jsonb),
                            "started_at": trace.started_at or _utcnow(),
                            "ended_at": trace.ended_at,
                        },
                    )
                    await conn.execute(
                        text(
                            """
                            UPDATE app.ai_backtest_request
                            SET trace_id = :trace_id
                            WHERE request_id = :request_id
                            """
                        ),
                        {"request_id": str(request_id), "trace_id": str(trace.trace_id)},
                    )
                    return AIBacktestRequestClaim(
                        request_id=request_id,
                        trace_id=trace.trace_id,
                        state="claimed",
                        safety_lease="active",
                        state_version=1,
                    )

                existing = (
                    await conn.execute(
                        text(
                            """
                            SELECT request_id, trace_id, state, safety_lease, state_version,
                                   terminal_response_jsonb, payload_fingerprint, fingerprint_version
                            FROM app.ai_backtest_request
                            WHERE scope_family_id = :scope_family_id
                              AND client_request_key = :client_request_key
                            FOR UPDATE
                            """
                        ),
                        {
                            "scope_family_id": str(context.scope_family_id),
                            "client_request_key": request.idempotency_key,
                        },
                    )
                ).mappings().first()
                if existing is not None:
                    if (
                        existing["payload_fingerprint"] != request.request_fingerprint
                        or existing["fingerprint_version"] != request.fingerprint_version
                    ):
                        raise AppError(
                            status_code=409,
                            component="ai_backtest",
                            code="idempotency_key_reused",
                            message="Idempotency key was reused with a different request",
                            details={"request_id": str(existing["request_id"])},
                        )
                    return _claim_from_row(existing)

                equivalent = (
                    await conn.execute(
                        text(
                            """
                            SELECT request_id, trace_id, state, safety_lease, state_version,
                                   terminal_response_jsonb
                            FROM app.ai_backtest_request
                            WHERE scope_family_id = :scope_family_id
                              AND fingerprint_version = :fingerprint_version
                              AND payload_fingerprint = :payload_fingerprint
                              AND safety_lease IN ('active', 'blocked_unknown')
                            FOR UPDATE
                            """
                        ),
                        {
                            "scope_family_id": str(context.scope_family_id),
                            "fingerprint_version": request.fingerprint_version,
                            "payload_fingerprint": request.request_fingerprint,
                        },
                    )
                ).mappings().first()
                if equivalent is None:
                    raise AppError(
                        status_code=503,
                        component="ai_backtest",
                        code="idempotency_claim_inconsistent",
                        message="Idempotency claim outcome was not found",
                    )
                return _claim_from_row(equivalent)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc

    async def transition_idempotent_request(
        self,
        request_id: UUID,
        *,
        expected_state: str,
        next_state: str,
        safety_lease: str | None = None,
        execution_run_id: UUID | None = None,
        terminal_response: Mapping[str, Any] | None = None,
        terminal_evidence: Mapping[str, Any] | None = None,
    ) -> AIBacktestRequestClaim:
        terminal = next_state in {"succeeded", "failed", "abandoned"}
        sql = """
            UPDATE app.ai_backtest_request
            SET state = :next_state,
                safety_lease = COALESCE(:safety_lease, safety_lease),
                execution_run_id = COALESCE(:execution_run_id, execution_run_id),
                terminal_response_jsonb = COALESCE(:terminal_response::jsonb, terminal_response_jsonb),
                terminal_evidence_jsonb = COALESCE(:terminal_evidence::jsonb, terminal_evidence_jsonb),
                state_version = state_version + 1,
                updated_at = :updated_at,
                terminal_at = CASE WHEN :terminal THEN :updated_at ELSE terminal_at END
            WHERE request_id = :request_id
              AND state = :expected_state
            RETURNING request_id, trace_id, state, safety_lease, state_version, terminal_response_jsonb
        """
        try:
            async with self.engine.begin() as conn:
                row = (
                    await conn.execute(
                        text(sql),
                        {
                            "request_id": str(request_id),
                            "expected_state": expected_state,
                            "next_state": next_state,
                            "safety_lease": safety_lease,
                            "execution_run_id": str(execution_run_id) if execution_run_id else None,
                            "terminal_response": _json_dumps(terminal_response) if terminal_response is not None else None,
                            "terminal_evidence": _json_dumps(terminal_evidence) if terminal_evidence is not None else None,
                            "updated_at": _utcnow(),
                            "terminal": terminal,
                        },
                    )
                ).mappings().first()
                if row is None:
                    raise AppError(
                        status_code=409,
                        component="ai_backtest",
                        code="duplicate_execution_active",
                        message="Idempotency request state changed concurrently",
                        details={"request_id": str(request_id)},
                    )
                return _claim_from_row(row)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc
    async def release_armed_execution_request(
        self,
        request_id: UUID,
        *,
        expected_state_version: int,
        execution_run_id: UUID,
        attempt_id: UUID,
    ) -> AIBacktestRequestClaim:
        sql = """
            UPDATE app.ai_backtest_request AS request
            SET state = 'execution_released',
                state_version = state_version + 1,
                updated_at = :updated_at
            WHERE request.request_id = :request_id
              AND request.state = 'execution_armed'
              AND request.safety_lease = 'active'
              AND request.state_version = :expected_state_version
              AND request.execution_run_id = :execution_run_id
              AND EXISTS (
                  SELECT 1
                  FROM app.code_execution_run AS execution
                  WHERE execution.execution_run_id = request.execution_run_id
                    AND execution.attempt_id = :attempt_id
                    AND execution.worker_host IS NOT NULL
                    AND execution.worker_pid IS NOT NULL
                    AND execution.worker_pgid IS NOT NULL
                    AND execution.worker_started_at IS NOT NULL
              )
            RETURNING request_id, trace_id, state, safety_lease, state_version, terminal_response_jsonb
        """
        try:
            async with self.engine.begin() as conn:
                row = (
                    await conn.execute(
                        text(sql),
                        {
                            "request_id": str(request_id),
                            "expected_state_version": expected_state_version,
                            "execution_run_id": str(execution_run_id),
                            "attempt_id": str(attempt_id),
                            "updated_at": _utcnow(),
                        },
                    )
                ).mappings().first()
                if row is None:
                    raise AppError(
                        status_code=409,
                        component="ai_backtest",
                        code="duplicate_execution_active",
                        message="Execution release ownership changed concurrently",
                        details={"request_id": str(request_id)},
                    )
                return _claim_from_row(row)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc
    async def operator_terminalize_idempotent_request(
        self,
        request_id: UUID,
        *,
        expected_state: str,
        expected_state_version: int,
        terminal_state: str,
        terminal_evidence: Mapping[str, Any],
    ) -> AIBacktestRequestClaim:
        requires_execution_evidence = expected_state in {"execution_armed", "execution_released"}
        evidence_execution_run_id = _evidence_uuid(terminal_evidence.get("execution_run_id"))
        evidence_attempt_id = _evidence_uuid(terminal_evidence.get("attempt_id"))
        release_state = terminal_evidence.get("release_state")
        if (
            terminal_state not in {"failed", "abandoned"}
            or not terminal_evidence
            or (
                requires_execution_evidence
                and (
                    evidence_execution_run_id is None
                    or evidence_attempt_id is None
                    or release_state != expected_state
                )
            )
        ):
            raise AppError(
                status_code=409,
                component="ai_backtest",
                code="terminal_evidence_required",
                message="Process and release evidence is required",
                details={"request_id": str(request_id)},
            )
        try:
            async with self.engine.begin() as conn:
                row = (
                    await conn.execute(
                        text(
                            """
                            UPDATE app.ai_backtest_request
                            SET state = :terminal_state,
                                safety_lease = 'closed',
                                terminal_evidence_jsonb = :terminal_evidence::jsonb,
                                state_version = state_version + 1,
                                updated_at = :updated_at,
                                terminal_at = :updated_at
                            WHERE request_id = :request_id
                              AND state = :expected_state
                              AND state_version = :expected_state_version
                              AND safety_lease IN ('active', 'blocked_unknown')
                              AND (
                                  NOT :requires_execution_evidence
                                  OR (
                                      execution_run_id = :evidence_execution_run_id
                                      AND :release_state = :expected_state
                                      AND EXISTS (
                                          SELECT 1
                                          FROM app.code_execution_run AS execution
                                          WHERE execution.execution_run_id = app.ai_backtest_request.execution_run_id
                                            AND execution.attempt_id = :evidence_attempt_id
                                            AND execution.worker_host IS NOT NULL
                                            AND execution.worker_pid IS NOT NULL
                                            AND execution.worker_pgid IS NOT NULL
                                            AND execution.worker_started_at IS NOT NULL
                                            AND (
                                                app.ai_backtest_request.state <> 'execution_released'
                                                OR (
                                                    execution.status IN ('succeeded', 'failed', 'timeout')
                                                    AND execution.ended_at IS NOT NULL
                                                )
                                            )
                                      )
                                  )
                              )
                            RETURNING request_id, trace_id, state, safety_lease, state_version,
                                      terminal_response_jsonb
                            """
                        ),
                        {
                            "request_id": str(request_id),
                            "expected_state": expected_state,
                            "expected_state_version": expected_state_version,
                            "terminal_state": terminal_state,
                            "terminal_evidence": _json_dumps(terminal_evidence),
                            "updated_at": _utcnow(),
                            "requires_execution_evidence": requires_execution_evidence,
                            "evidence_execution_run_id": str(evidence_execution_run_id)
                            if evidence_execution_run_id is not None
                            else None,
                            "evidence_attempt_id": str(evidence_attempt_id)
                            if evidence_attempt_id is not None
                            else None,
                            "release_state": release_state,
                        },
                    )
                ).mappings().first()
                if row is None:
                    raise AppError(
                        status_code=409,
                        component="ai_backtest",
                        code="duplicate_execution_active",
                        message="Idempotency request state changed concurrently",
                        details={"request_id": str(request_id)},
                    )
                return _claim_from_row(row)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc
    async def operator_record_terminal_evidence(
        self,
        request_id: UUID,
        *,
        expected_state: str,
        expected_state_version: int,
        terminal_evidence: Mapping[str, Any],
    ) -> AIBacktestRequestClaim:
        if not terminal_evidence:
            raise AppError(
                status_code=409,
                component="ai_backtest",
                code="terminal_evidence_required",
                message="Terminal evidence is required",
                details={"request_id": str(request_id)},
            )
        try:
            async with self.engine.begin() as conn:
                row = (
                    await conn.execute(
                        text(
                            """
                            UPDATE app.ai_backtest_request
                            SET terminal_evidence_jsonb = :terminal_evidence::jsonb,
                                state_version = state_version + 1,
                                updated_at = :updated_at
                            WHERE request_id = :request_id
                              AND state = :expected_state
                              AND state_version = :expected_state_version
                              AND state IN ('succeeded', 'failed', 'abandoned')
                              AND safety_lease = 'closed'
                              AND terminal_evidence_jsonb IS NULL
                            RETURNING request_id, trace_id, state, safety_lease, state_version,
                                      terminal_response_jsonb
                            """
                        ),
                        {
                            "request_id": str(request_id),
                            "expected_state": expected_state,
                            "expected_state_version": expected_state_version,
                            "terminal_evidence": _json_dumps(terminal_evidence),
                            "updated_at": _utcnow(),
                        },
                    )
                ).mappings().first()
                if row is None:
                    raise AppError(
                        status_code=409,
                        component="ai_backtest",
                        code="terminal_evidence_required",
                        message="Terminal evidence state changed concurrently",
                        details={"request_id": str(request_id)},
                    )
                return _claim_from_row(row)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc

    async def operator_issue_replacement_approval(
        self,
        source_request_id: UUID,
        *,
        expires_at: datetime,
    ) -> AIBacktestReplacementApproval:
        now = _utcnow()
        if expires_at.tzinfo is None or expires_at <= now:
            raise AppError(
                status_code=409,
                component="ai_backtest",
                code="replacement_approval_invalid",
                message="Replacement approval expiry must be in the future",
            )
        approval_id = uuid4()
        approval_token = token_urlsafe(32)
        try:
            async with self.engine.begin() as conn:
                source = (
                    await conn.execute(
                        text(
                            """
                            SELECT request_id, scope_family_id, fingerprint_version, payload_fingerprint,
                                   state, safety_lease, terminal_evidence_jsonb
                            FROM app.ai_backtest_request
                            WHERE request_id = :source_request_id
                            FOR UPDATE
                            """
                        ),
                        {"source_request_id": str(source_request_id)},
                    )
                ).mappings().first()
                if (
                    source is None
                    or source["state"] not in {"succeeded", "failed", "abandoned"}
                    or source["safety_lease"] != "closed"
                    or source["terminal_evidence_jsonb"] is None
                ):
                    raise AppError(
                        status_code=409,
                        component="ai_backtest",
                        code="terminal_evidence_required",
                        message="Terminal evidence is required before replacement approval",
                        details={"request_id": str(source_request_id)},
                    )
                await conn.execute(
                    text(
                        """
                        UPDATE app.ai_backtest_replacement_approval
                        SET status = 'expired'
                        WHERE source_request_id = :source_request_id
                          AND status = 'issued'
                          AND expires_at <= :now
                        """
                    ),
                    {"source_request_id": str(source_request_id), "now": now},
                )
                live_approval = (
                    await conn.execute(
                        text(
                            """
                            SELECT approval_id
                            FROM app.ai_backtest_replacement_approval
                            WHERE source_request_id = :source_request_id
                              AND status = 'issued'
                              AND expires_at > :now
                            FOR UPDATE
                            """
                        ),
                        {"source_request_id": str(source_request_id), "now": now},
                    )
                ).mappings().first()
                if live_approval is not None:
                    raise AppError(
                        status_code=409,
                        component="ai_backtest",
                        code="replacement_approval_already_issued",
                        message="A live replacement approval already exists",
                        details={"request_id": str(source_request_id)},
                    )
                await conn.execute(
                    text(
                        """
                        INSERT INTO app.ai_backtest_replacement_approval (
                            approval_id, source_request_id, scope_family_id, fingerprint_version,
                            payload_fingerprint, replacement_key_hash, expires_at
                        ) VALUES (
                            :approval_id, :source_request_id, :scope_family_id, :fingerprint_version,
                            :payload_fingerprint, :replacement_key_hash, :expires_at
                        )
                        """
                    ),
                    {
                        "approval_id": str(approval_id),
                        "source_request_id": str(source_request_id),
                        "scope_family_id": str(source["scope_family_id"]),
                        "fingerprint_version": source["fingerprint_version"],
                        "payload_fingerprint": source["payload_fingerprint"],
                        "replacement_key_hash": _replacement_key_hash(approval_token),
                        "expires_at": expires_at,
                    },
                )
                return AIBacktestReplacementApproval(
                    approval_id=approval_id,
                    source_request_id=source_request_id,
                    scope_family_id=UUID(str(source["scope_family_id"])),
                    fingerprint_version=source["fingerprint_version"],
                    payload_fingerprint=source["payload_fingerprint"],
                    approval_token=approval_token,
                    expires_at=expires_at,
                )
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc
    async def create_trace(self, record: AITraceCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_trace (
                trace_id, user_id, session_id, trace_kind, status,
                metadata_jsonb, started_at, ended_at
            ) VALUES (
                :trace_id, :user_id, :session_id, :trace_kind, :status,
                :metadata_jsonb::jsonb, :started_at, :ended_at
            )
            """,
            {
                "trace_id": str(record.trace_id),
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "trace_kind": record.trace_kind,
                "status": record.status,
                "metadata_jsonb": _json_dumps(record.metadata_jsonb),
                "started_at": record.started_at or _utcnow(),
                "ended_at": record.ended_at,
            },
        )
        return record.trace_id

    async def finish_trace(
        self,
        trace_id: UUID,
        *,
        status: str,
        metadata_jsonb: Mapping[str, Any] | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        await self._execute(
            """
            UPDATE app.ai_trace
            SET status = :status,
                metadata_jsonb = COALESCE(:metadata_jsonb::jsonb, metadata_jsonb),
                ended_at = :ended_at
            WHERE trace_id = :trace_id
            """,
            {
                "trace_id": str(trace_id),
                "status": status,
                "metadata_jsonb": _json_dumps(metadata_jsonb) if metadata_jsonb is not None else None,
                "ended_at": ended_at or _utcnow(),
            },
        )

    async def create_strategy_parse(self, record: AIStrategyParseCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_strategy_parse (
                parse_id, session_id, user_id, trace_id, raw_prompt,
                parsed_strategy_jsonb, confidence, model_name, parse_status
            ) VALUES (
                :parse_id, :session_id, :user_id, :trace_id, :raw_prompt,
                :parsed_strategy_jsonb::jsonb, :confidence, :model_name, :parse_status
            )
            """,
            {
                "parse_id": str(record.parse_id),
                "session_id": str(record.session_id) if record.session_id else None,
                "user_id": record.user_id,
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "raw_prompt": record.raw_prompt,
                "parsed_strategy_jsonb": _json_dumps(record.parsed_strategy_jsonb),
                "confidence": record.confidence,
                "model_name": record.model_name,
                "parse_status": record.parse_status,
            },
        )
        return record.parse_id

    async def create_code_generation(self, record: AICodeGenerationCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_code_generation (
                code_id, parse_id, user_id, session_id, trace_id,
                source_message_id, target_runtime, code_purpose,
                generated_code, code_hash, model_name, code_status
            ) VALUES (
                :code_id, :parse_id, :user_id, :session_id, :trace_id,
                :source_message_id, :target_runtime, :code_purpose,
                :generated_code, :code_hash, :model_name, :code_status
            )
            """,
            {
                "code_id": str(record.code_id),
                "parse_id": str(record.parse_id) if record.parse_id else None,
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "source_message_id": str(record.source_message_id) if record.source_message_id else None,
                "target_runtime": record.target_runtime,
                "code_purpose": record.code_purpose,
                "generated_code": record.generated_code,
                "code_hash": record.code_hash,
                "model_name": record.model_name,
                "code_status": record.code_status,
            },
        )
        return record.code_id

    async def update_code_generation_status(self, code_id: UUID, status: str) -> None:
        await self._execute(
            """
            UPDATE app.ai_code_generation
            SET code_status = :status,
                updated_at = :updated_at
            WHERE code_id = :code_id
            """,
            {
                "code_id": str(code_id),
                "status": status,
                "updated_at": _utcnow(),
            },
        )

    async def create_code_validation_result(self, record: AICodeValidationResultCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_code_validation_result (
                validation_id, code_id, is_safe, syntax_valid,
                uses_allowed_imports, blocks_network_access,
                blocks_file_write, warnings_jsonb, errors_jsonb
            ) VALUES (
                :validation_id, :code_id, :is_safe, :syntax_valid,
                :uses_allowed_imports, :blocks_network_access,
                :blocks_file_write, :warnings_jsonb::jsonb, :errors_jsonb::jsonb
            )
            """,
            {
                "validation_id": str(record.validation_id),
                "code_id": str(record.code_id),
                "is_safe": record.is_safe,
                "syntax_valid": record.syntax_valid,
                "uses_allowed_imports": record.uses_allowed_imports,
                "blocks_network_access": record.blocks_network_access,
                "blocks_file_write": record.blocks_file_write,
                "warnings_jsonb": _json_dumps(record.warnings_jsonb),
                "errors_jsonb": _json_dumps(record.errors_jsonb),
            },
        )
        return record.validation_id

    async def create_code_execution_run(self, record: CodeExecutionRunCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.code_execution_run (
                execution_run_id, code_id, user_id, session_id, trace_id,
                runtime_env, sandbox_id, status, timeout_seconds,
                memory_limit_mb, latency_ms, stdout, stderr,
                output_artifacts_jsonb, started_at, ended_at
            ) VALUES (
                :execution_run_id, :code_id, :user_id, :session_id, :trace_id,
                :runtime_env, :sandbox_id, :status, :timeout_seconds,
                :memory_limit_mb, :latency_ms, :stdout, :stderr,
                :output_artifacts_jsonb::jsonb, :started_at, :ended_at
            )
            """,
            {
                "execution_run_id": str(record.execution_run_id),
                "code_id": str(record.code_id),
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "runtime_env": record.runtime_env,
                "sandbox_id": record.sandbox_id,
                "status": record.status,
                "timeout_seconds": record.timeout_seconds,
                "memory_limit_mb": record.memory_limit_mb,
                "latency_ms": record.latency_ms,
                "stdout": record.stdout,
                "stderr": record.stderr,
                "output_artifacts_jsonb": _json_dumps(record.output_artifacts_jsonb) if record.output_artifacts_jsonb is not None else None,
                "started_at": record.started_at,
                "ended_at": record.ended_at,
            },
        )
        return record.execution_run_id

    async def update_code_execution_run(self, execution_run_id: UUID, update: CodeExecutionRunUpdate) -> None:
        await self._execute(
            """
            UPDATE app.code_execution_run
            SET status = :status,
                latency_ms = :latency_ms,
                stdout = :stdout,
                stderr = :stderr,
                output_artifacts_jsonb = :output_artifacts_jsonb::jsonb,
                sandbox_id = :sandbox_id,
                started_at = COALESCE(:started_at, started_at),
                ended_at = :ended_at
            WHERE execution_run_id = :execution_run_id
            """,
            {
                "execution_run_id": str(execution_run_id),
                "status": update.status,
                "latency_ms": update.latency_ms,
                "stdout": update.stdout,
                "stderr": update.stderr,
                "output_artifacts_jsonb": _json_dumps(update.output_artifacts_jsonb) if update.output_artifacts_jsonb is not None else None,
                "sandbox_id": update.sandbox_id,
                "started_at": update.started_at,
                "ended_at": update.ended_at,
            },
        )

    async def record_code_execution_process_identity(
        self,
        execution_run_id: UUID,
        *,
        attempt_id: UUID,
        worker_host: str,
        worker_pid: int,
        worker_pgid: int,
        worker_started_at: datetime,
        idempotency_request_id: UUID | None = None,
    ) -> None:
        try:
            async with self.engine.begin() as conn:
                sql = """
                    UPDATE app.code_execution_run
                    SET attempt_id = :attempt_id,
                        worker_host = :worker_host,
                        worker_pid = :worker_pid,
                        worker_pgid = :worker_pgid,
                        worker_started_at = :worker_started_at
                    WHERE execution_run_id = :execution_run_id
                """
                params: dict[str, object] = {
                    "execution_run_id": str(execution_run_id),
                    "attempt_id": str(attempt_id),
                    "worker_host": worker_host,
                    "worker_pid": worker_pid,
                    "worker_pgid": worker_pgid,
                    "worker_started_at": worker_started_at,
                }
                if idempotency_request_id is not None:
                    sql += """
                        AND EXISTS (
                            SELECT 1
                            FROM app.ai_backtest_request AS request
                            WHERE request.request_id = :request_id
                              AND request.execution_run_id = :execution_run_id
                              AND request.state = 'execution_armed'
                              AND request.safety_lease = 'active'
                        )
                    """
                    params["request_id"] = str(idempotency_request_id)
                result = await conn.execute(text(sql), params)
                if result.rowcount != 1:
                    raise AppError(
                        status_code=409 if idempotency_request_id is not None else 503,
                        component="ai_backtest" if idempotency_request_id is not None else "db",
                        code="duplicate_execution_active" if idempotency_request_id is not None else "execution_run_not_found",
                        message=(
                            "Execution request state changed before ownership persistence"
                            if idempotency_request_id is not None
                            else "Execution ownership could not be persisted"
                        ),
                        details={"request_id": str(idempotency_request_id)}
                        if idempotency_request_id is not None
                        else None,
                    )
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc
    async def persist_backtest_result(self, payload: BacktestResultPayload) -> UUID:
        async with self.engine.begin() as conn:
            try:
                run = payload.run
                await conn.execute(
                    text(
                        """
                        INSERT INTO app.backtest_run (
                            run_id, strategy_id, user_id, session_id, source_parse_id,
                            code_id, execution_run_id, trace_id, initial_capital, max_tickers,
                            talib_mode, config_jsonb, backtest_start_date, backtest_end_date,
                            benchmark_ticker, data_source, strategy_snapshot_jsonb,
                            universe_snapshot_jsonb, as_of_at, status, started_at,
                            ended_at, error_message, output_paths_jsonb, execution_mode
                        ) VALUES (
                            :run_id, :strategy_id, :user_id, :session_id, :source_parse_id,
                            :code_id, :execution_run_id, :trace_id, :initial_capital, :max_tickers,
                            :talib_mode, :config_jsonb::jsonb, :backtest_start_date, :backtest_end_date,
                            :benchmark_ticker, :data_source, :strategy_snapshot_jsonb::jsonb,
                            :universe_snapshot_jsonb::jsonb, :as_of_at, :status, :started_at,
                            :ended_at, :error_message, :output_paths_jsonb::jsonb, :execution_mode
                        )
                        """
                    ),
                    {
                        "run_id": str(run.run_id),
                        "strategy_id": run.strategy_id,
                        "user_id": run.user_id,
                        "session_id": str(run.session_id) if run.session_id else None,
                        "source_parse_id": str(run.source_parse_id) if run.source_parse_id else None,
                        "code_id": str(run.code_id) if run.code_id else None,
                        "execution_run_id": str(run.execution_run_id) if run.execution_run_id else None,
                        "trace_id": str(run.trace_id) if run.trace_id else None,
                        "initial_capital": run.initial_capital,
                        "max_tickers": run.max_tickers,
                        "talib_mode": run.talib_mode,
                        "config_jsonb": _json_dumps(run.config_jsonb),
                        "backtest_start_date": run.backtest_start_date,
                        "backtest_end_date": run.backtest_end_date,
                        "benchmark_ticker": run.benchmark_ticker,
                        "data_source": run.data_source,
                        "strategy_snapshot_jsonb": _json_dumps(run.strategy_snapshot_jsonb),
                        "universe_snapshot_jsonb": _json_dumps(run.universe_snapshot_jsonb),
                        "as_of_at": run.as_of_at,
                        "status": run.status,
                        "started_at": run.started_at,
                        "ended_at": run.ended_at,
                        "error_message": run.error_message,
                        "output_paths_jsonb": _json_dumps(run.output_paths_jsonb),
                        "execution_mode": run.execution_mode,
                    },
                )

                summary = payload.summary
                await conn.execute(
                    text(
                        """
                        INSERT INTO app.backtest_summary (
                            summary_id, run_id, final_equity, final_cash, open_positions,
                            period_return, cagr, benchmark_return, alpha, beta,
                            max_drawdown, volatility, sharpe_ratio, sortino_ratio,
                            calmar_ratio, win_rate, profit_factor, payoff_ratio,
                            avg_win, avg_loss, max_consecutive_wins, max_consecutive_losses,
                            trade_count, signal_count, avg_holding_days, turnover,
                            total_commission, total_tax, total_slippage,
                            excluded_ticker_count, excluded_tickers_jsonb,
                            indicator_report_jsonb, cost_model_jsonb,
                            position_sizing_jsonb, metrics_version
                        ) VALUES (
                            :summary_id, :run_id, :final_equity, :final_cash, :open_positions,
                            :period_return, :cagr, :benchmark_return, :alpha, :beta,
                            :max_drawdown, :volatility, :sharpe_ratio, :sortino_ratio,
                            :calmar_ratio, :win_rate, :profit_factor, :payoff_ratio,
                            :avg_win, :avg_loss, :max_consecutive_wins, :max_consecutive_losses,
                            :trade_count, :signal_count, :avg_holding_days, :turnover,
                            :total_commission, :total_tax, :total_slippage,
                            :excluded_ticker_count, :excluded_tickers_jsonb::jsonb,
                            :indicator_report_jsonb::jsonb, :cost_model_jsonb::jsonb,
                            :position_sizing_jsonb::jsonb, :metrics_version
                        )
                        """
                    ),
                    {"summary_id": str(uuid4()), "run_id": str(run.run_id), **_summary_params(summary)},
                )

                detail = payload.metric_detail
                await conn.execute(
                    text(
                        """
                        INSERT INTO app.backtest_metric_detail (
                            run_id, compare_json, composition_json, drawdown_detail_json,
                            drawdown_series_json, greeks_json, rolling_returns_json,
                            monthly_return_json, montecarlo_json, montecarlo_cagr_json,
                            montecarlo_drawdown_json, montecarlo_sharpe_json, outliers_json
                        ) VALUES (
                            :run_id, :compare_json::jsonb, :composition_json::jsonb, :drawdown_detail_json::jsonb,
                            :drawdown_series_json::jsonb, :greeks_json::jsonb, :rolling_returns_json::jsonb,
                            :monthly_return_json::jsonb, :montecarlo_json::jsonb, :montecarlo_cagr_json::jsonb,
                            :montecarlo_drawdown_json::jsonb, :montecarlo_sharpe_json::jsonb, :outliers_json::jsonb
                        )
                        """
                    ),
                    {"run_id": str(run.run_id), **_metric_detail_params(detail)},
                )

                if payload.equity_points:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO app.backtest_equity_point (
                                point_id, run_id, trade_date, cash,
                                positions_value, total_equity, daily_return
                            ) VALUES (
                                :point_id, :run_id, :trade_date, :cash,
                                :positions_value, :total_equity, :daily_return
                            )
                            """
                        ),
                        [
                            {
                                "point_id": str(uuid4()),
                                "run_id": str(run.run_id),
                                "trade_date": point.trade_date,
                                "cash": point.cash,
                                "positions_value": point.positions_value,
                                "total_equity": point.total_equity,
                                "daily_return": point.daily_return,
                            }
                            for point in payload.equity_points
                        ],
                    )

                if payload.signals:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO app.backtest_signal (
                                run_id, signal_date, scheduled_execution_date,
                                execution_timing, sequence_no, ticker, action,
                                reasons, matching_entry_rules, matching_exit_rules
                            ) VALUES (
                                :run_id, :signal_date, :scheduled_execution_date,
                                :execution_timing, :sequence_no, :ticker, :action,
                                :reasons::jsonb, :matching_entry_rules::jsonb, :matching_exit_rules::jsonb
                            )
                            """
                        ),
                        [
                            {
                                "run_id": str(run.run_id),
                                "signal_date": signal.signal_date,
                                "scheduled_execution_date": signal.scheduled_execution_date,
                                "execution_timing": signal.execution_timing,
                                "sequence_no": signal.sequence_no,
                                "ticker": signal.ticker,
                                "action": signal.action,
                                "reasons": _json_dumps(signal.reasons),
                                "matching_entry_rules": _json_dumps(signal.matching_entry_rules),
                                "matching_exit_rules": _json_dumps(signal.matching_exit_rules),
                            }
                            for signal in payload.signals
                        ],
                    )

                if payload.trades:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO app.backtest_trade (
                                run_id, entry_signal_id, exit_signal_id, ticker,
                                entry_date, exit_date, entry_price, exit_price,
                                quantity, entry_cost, exit_cost, gross_pnl,
                                net_pnl, return_pct, reason
                            ) VALUES (
                                :run_id, :entry_signal_id, :exit_signal_id, :ticker,
                                :entry_date, :exit_date, :entry_price, :exit_price,
                                :quantity, :entry_cost, :exit_cost, :gross_pnl,
                                :net_pnl, :return_pct, :reason
                            )
                            """
                        ),
                        [
                            {
                                "run_id": str(run.run_id),
                                "entry_signal_id": trade.entry_signal_id,
                                "exit_signal_id": trade.exit_signal_id,
                                "ticker": trade.ticker,
                                "entry_date": trade.entry_date,
                                "exit_date": trade.exit_date,
                                "entry_price": trade.entry_price,
                                "exit_price": trade.exit_price,
                                "quantity": trade.quantity,
                                "entry_cost": trade.entry_cost,
                                "exit_cost": trade.exit_cost,
                                "gross_pnl": trade.gross_pnl,
                                "net_pnl": trade.net_pnl,
                                "return_pct": trade.return_pct,
                                "reason": trade.reason,
                            }
                            for trade in payload.trades
                        ],
                    )
            except AppError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise self._db_error(exc) from exc
        return payload.run.run_id

    async def create_ai_backtest_report(self, record: AIBacktestReportCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_backtest_report (
                report_id, run_id, user_id, trace_id, period_return, cagr,
                max_drawdown, sharpe_ratio, sortino_ratio, calmar_ratio,
                win_rate, profit_factor, volatility, benchmark_return,
                overall_rating, summary, return_analysis, risk_analysis,
                trade_analysis, benchmark_analysis, improvement_suggestions,
                report_jsonb, model_name
            ) VALUES (
                :report_id, :run_id, :user_id, :trace_id, :period_return, :cagr,
                :max_drawdown, :sharpe_ratio, :sortino_ratio, :calmar_ratio,
                :win_rate, :profit_factor, :volatility, :benchmark_return,
                :overall_rating, :summary, :return_analysis, :risk_analysis,
                :trade_analysis, :benchmark_analysis, :improvement_suggestions,
                :report_jsonb::jsonb, :model_name
            )
            """,
            {
                "report_id": str(record.report_id),
                "run_id": str(record.run_id),
                "user_id": record.user_id,
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "period_return": record.period_return,
                "cagr": record.cagr,
                "max_drawdown": record.max_drawdown,
                "sharpe_ratio": record.sharpe_ratio,
                "sortino_ratio": record.sortino_ratio,
                "calmar_ratio": record.calmar_ratio,
                "win_rate": record.win_rate,
                "profit_factor": record.profit_factor,
                "volatility": record.volatility,
                "benchmark_return": record.benchmark_return,
                "overall_rating": record.overall_rating,
                "summary": record.summary,
                "return_analysis": record.return_analysis,
                "risk_analysis": record.risk_analysis,
                "trade_analysis": record.trade_analysis,
                "benchmark_analysis": record.benchmark_analysis,
                "improvement_suggestions": record.improvement_suggestions,
                "report_jsonb": _json_dumps(record.report_jsonb),
                "model_name": record.model_name,
            },
        )
        return record.report_id

    async def create_model_call_log(
        self,
        *,
        trace_id: UUID | None,
        execution_id: UUID | None,
        user_id: int | None,
        session_id: UUID | None,
        message_id: UUID | None,
        code_id: UUID | None,
        bundle: ModelCallLogBundle,
        raw_audit_admission: RawAuditAdmission,
    ) -> UUID | None:
        if not verify_raw_audit_admission(raw_audit_admission):
            return None
        call_id = uuid4()
        try:
            async with self.engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        INSERT INTO app.ai_model_call_log (
                            call_id, trace_id, execution_id, user_id, session_id,
                            message_id, code_id, task_type, provider,
                            provider_request_id, model_name, temperature, top_p,
                            seed, response_schema_name, web_search_used,
                            prompt_tokens, completion_tokens, total_tokens,
                            latency_ms, cost, retry_count, cache_hit,
                            tool_calls_jsonb, status, error_message
                        ) VALUES (
                            :call_id, :trace_id, :execution_id, :user_id, :session_id,
                            :message_id, :code_id, :task_type, :provider,
                            :provider_request_id, :model_name, :temperature, :top_p,
                            :seed, :response_schema_name, :web_search_used,
                            :prompt_tokens, :completion_tokens, :total_tokens,
                            :latency_ms, :cost, :retry_count, :cache_hit,
                            :tool_calls_jsonb::jsonb, :status, :error_message
                        )
                        """
                    ),
                    {
                        "call_id": str(call_id),
                        "trace_id": str(trace_id) if trace_id else None,
                        "execution_id": str(execution_id) if execution_id else None,
                        "user_id": user_id,
                        "session_id": str(session_id) if session_id else None,
                        "message_id": str(message_id) if message_id else None,
                        "code_id": str(code_id) if code_id else None,
                        "task_type": bundle.task_type,
                        "provider": bundle.provider,
                        "provider_request_id": bundle.provider_request_id,
                        "model_name": bundle.model_name,
                        "temperature": bundle.temperature,
                        "top_p": bundle.top_p,
                        "seed": bundle.seed,
                        "response_schema_name": bundle.response_schema_name,
                        "web_search_used": bundle.web_search_used,
                        "prompt_tokens": bundle.prompt_tokens,
                        "completion_tokens": bundle.completion_tokens,
                        "total_tokens": bundle.total_tokens,
                        "latency_ms": bundle.latency_ms,
                        "cost": bundle.cost,
                        "retry_count": bundle.retry_count,
                        "cache_hit": bundle.cache_hit,
                        "tool_calls_jsonb": _json_dumps(bundle.tool_calls_jsonb),
                        "status": bundle.status,
                        "error_message": bundle.error_message,
                    },
                )
                await conn.execute(
                    text(
                        """
                        INSERT INTO app.ai_prompt_log (
                            prompt_log_id, call_id, user_id, session_id,
                            prompt_template_name, system_prompt, user_prompt,
                            assistant_response, variables_jsonb, prompt_version,
                            contains_pii, masked
                        ) VALUES (
                            :prompt_log_id, :call_id, :user_id, :session_id,
                            :prompt_template_name, :system_prompt, :user_prompt,
                            :assistant_response, :variables_jsonb::jsonb, :prompt_version,
                            :contains_pii, :masked
                        )
                        """
                    ),
                    {
                        "prompt_log_id": str(uuid4()),
                        "call_id": str(call_id),
                        "user_id": user_id,
                        "session_id": str(session_id) if session_id else None,
                        "prompt_template_name": bundle.prompt_log.prompt_template_name,
                        "system_prompt": bundle.prompt_log.system_prompt,
                        "user_prompt": bundle.prompt_log.user_prompt,
                        "assistant_response": bundle.prompt_log.assistant_response,
                        "variables_jsonb": _json_dumps(bundle.prompt_log.variables_jsonb),
                        "prompt_version": bundle.prompt_log.prompt_version,
                        "contains_pii": bundle.prompt_log.contains_pii,
                        "masked": bundle.prompt_log.masked,
                    },
                )
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc
        return call_id

    async def create_agent_execution_log(self, record: AgentExecutionLogCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_agent_execution_log (
                execution_id, trace_id, user_id, session_id, run_id,
                execution_run_id, agent_name, step_name, status,
                input_jsonb, output_jsonb, error_message, latency_ms,
                started_at, ended_at
            ) VALUES (
                :execution_id, :trace_id, :user_id, :session_id, :run_id,
                :execution_run_id, :agent_name, :step_name, :status,
                :input_jsonb::jsonb, :output_jsonb::jsonb, :error_message, :latency_ms,
                :started_at, :ended_at
            )
            """,
            {
                "execution_id": str(record.execution_id),
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "run_id": str(record.run_id) if record.run_id else None,
                "execution_run_id": str(record.execution_run_id) if record.execution_run_id else None,
                "agent_name": record.agent_name,
                "step_name": record.step_name,
                "status": record.status,
                "input_jsonb": _json_dumps(record.input_jsonb),
                "output_jsonb": _json_dumps(record.output_jsonb),
                "error_message": record.error_message,
                "latency_ms": record.latency_ms,
                "started_at": record.started_at or _utcnow(),
                "ended_at": record.ended_at,
            },
        )
        return record.execution_id

    async def update_agent_execution_log(self, execution_id: UUID, update: AgentExecutionLogUpdate) -> None:
        await self._execute(
            """
            UPDATE app.ai_agent_execution_log
            SET status = :status,
                output_jsonb = :output_jsonb::jsonb,
                error_message = :error_message,
                latency_ms = :latency_ms,
                ended_at = :ended_at
            WHERE execution_id = :execution_id
            """,
            {
                "execution_id": str(execution_id),
                "status": update.status,
                "output_jsonb": _json_dumps(update.output_jsonb),
                "error_message": update.error_message,
                "latency_ms": update.latency_ms,
                "ended_at": update.ended_at or _utcnow(),
            },
        )

    async def create_error_log(self, record: AIErrorLogCreate) -> UUID:
        await self._execute(
            """
            INSERT INTO app.ai_error_log (
                error_id, trace_id, user_id, session_id, call_id,
                execution_id, execution_run_id, error_type, error_message,
                stack_trace, context_jsonb, severity
            ) VALUES (
                :error_id, :trace_id, :user_id, :session_id, :call_id,
                :execution_id, :execution_run_id, :error_type, :error_message,
                :stack_trace, :context_jsonb::jsonb, :severity
            )
            """,
            {
                "error_id": str(record.error_id),
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "user_id": record.user_id,
                "session_id": str(record.session_id) if record.session_id else None,
                "call_id": str(record.call_id) if record.call_id else None,
                "execution_id": str(record.execution_id) if record.execution_id else None,
                "execution_run_id": str(record.execution_run_id) if record.execution_run_id else None,
                "error_type": record.error_type,
                "error_message": record.error_message,
                "stack_trace": record.stack_trace,
                "context_jsonb": _json_dumps(record.context_jsonb),
                "severity": record.severity,
            },
        )
        return record.error_id

    async def _execute(self, sql: str, params: Mapping[str, Any]) -> None:
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text(sql), params)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._db_error(exc) from exc

    def _db_error(self, exc: Exception) -> AppError:
        return AppError(
            status_code=503,
            component="db",
            code="db_query_failed",
            message="Database query failed",
            details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
        )


def _scope_advisory_key(scope_family_id: UUID, fingerprint_version: str, fingerprint: str) -> int:
    digest = hashlib.sha256(
        f"{scope_family_id}\x00{fingerprint_version}\x00{fingerprint}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)
def _replacement_key_hash(approval_token: str) -> str:
    return hashlib.sha256(approval_token.encode("utf-8")).hexdigest()



def _claim_from_row(row: Mapping[str, Any]) -> AIBacktestRequestClaim:
    terminal_response = row.get("terminal_response_jsonb")
    if isinstance(terminal_response, str):
        try:
            terminal_response = json.loads(terminal_response)
        except json.JSONDecodeError:
            terminal_response = None
    return AIBacktestRequestClaim(
        request_id=UUID(str(row["request_id"])),
        trace_id=UUID(str(row["trace_id"])) if row.get("trace_id") else None,
        state=str(row["state"]),
        safety_lease=str(row["safety_lease"]),
        state_version=int(row["state_version"]),
        terminal_response=terminal_response if isinstance(terminal_response, dict) else None,
    )

def _summary_params(summary) -> dict[str, Any]:
    payload = summary.model_dump(mode="python")
    payload["excluded_tickers_jsonb"] = _json_dumps(payload["excluded_tickers_jsonb"])
    payload["indicator_report_jsonb"] = _json_dumps(payload["indicator_report_jsonb"])
    payload["cost_model_jsonb"] = _json_dumps(payload["cost_model_jsonb"])
    payload["position_sizing_jsonb"] = _json_dumps(payload["position_sizing_jsonb"])
    return payload


def _metric_detail_params(detail) -> dict[str, Any]:
    payload = detail.model_dump(mode="python")
    return {key: _json_dumps(value) for key, value in payload.items()}


def _evidence_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None

def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _json_default(value: Any):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC)
