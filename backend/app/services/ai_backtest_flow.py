from __future__ import annotations

import hashlib
import json
import math
import unicodedata
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.core.errors import AppError
from app.db.ai_backtest_repository import AIBacktestRepository
from app.schemas.ai_backtest import (
    AIBacktestReportCreate,
    AIBacktestReportDraft,
    AICodeBacktestFlowRequest,
    AIBacktestRequestClaim,
    AIBacktestErrorResponse,
    AIBacktestRunningResponse,
    AICodeBacktestFlowResult,
    AICodeGenerationCreate,
    AICodeValidationResultCreate,
    AIErrorLogCreate,
    AIStrategyParseCreate,
    AITraceCreate,
    AgentExecutionLogCreate,
    AgentExecutionLogUpdate,
    CodeExecutionResult,
    CodeExecutionRunCreate,
    CodeExecutionRunUpdate,
    CodeValidationOutcome,
    GeneratedCodeResult,
    ModelCallLogBundle,
)
from app.services.raw_audit_admission import RawAuditAdmission
from app.services.ai_backtest_runtime import ProcessIdentityRecorder, ReleaseAuthorizer


_AUDIT_FAILURE_COUNT = 0
_AUDIT_FAILURE_COUNT_LOCK = Lock()


@dataclass(slots=True)
class _AuditWrites:
    repository: AIBacktestRepository
    trace_id: UUID
    trace_persisted: bool = False
    broken: bool = False
    failure_recorded: bool = False
    current_execution_id: UUID | None = None

    @property
    def trace_reference(self) -> UUID | None:
        return self.trace_id if self.trace_persisted else None

    async def start(self, record: AITraceCreate) -> None:
        created = await self.write("create_trace", lambda: self.repository.create_trace(record))
        self.trace_persisted = created is not None

    async def write(
        self,
        operation: str,
        action: Callable[[], Awaitable[Any]],
    ) -> Any | None:
        if self.broken:
            return None
        try:
            return await action()
        except Exception:  # noqa: BLE001 - audit persistence must remain fail-open
            self.broken = True
            _report_audit_failure(operation)
            return None


class CodeGenerator(Protocol):
    async def generate(self, request: AICodeBacktestFlowRequest, *, trace_id: UUID) -> GeneratedCodeResult: ...


class CodeValidator(Protocol):
    def validate(self, generated: GeneratedCodeResult, *, trace_id: UUID) -> CodeValidationOutcome: ...


class CodeExecutor(Protocol):
    async def execute(
        self,
        request: AICodeBacktestFlowRequest,
        generated: GeneratedCodeResult,
        *,
        trace_id: UUID,
        execution_run_id: UUID,
        process_identity_recorder: ProcessIdentityRecorder | None = None,
        release_authorizer: ReleaseAuthorizer | None = None,
    ) -> CodeExecutionResult: ...


class BacktestReportGenerator(Protocol):
    async def build_report(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        run_id: UUID,
        execution: CodeExecutionResult,
    ) -> AIBacktestReportDraft: ...


@dataclass(slots=True)
class AICodeBacktestService:
    repository: AIBacktestRepository
    code_generator: CodeGenerator
    code_validator: CodeValidator
    code_executor: CodeExecutor
    report_generator: BacktestReportGenerator
    raw_audit_admission: RawAuditAdmission | None = None

    async def run_generated_backtest(
        self, request: AICodeBacktestFlowRequest
    ) -> AICodeBacktestFlowResult | AIBacktestRunningResponse | AIBacktestErrorResponse:
        _validate_execution_request(request)
        trace_id = uuid4()
        trace = AITraceCreate(
            trace_id=trace_id,
            user_id=request.execution_context.user_id if request.execution_context else None,
            metadata_jsonb={"entrypoint": "ai_generated_backtest", "strategy_id": request.strategy_id},
            started_at=_utcnow(),
        )
        claim: AIBacktestRequestClaim
        try:
            claim = await self.repository.claim_idempotent_request(request, trace=trace)
        except Exception as exc:  # noqa: BLE001 - trace bootstrap is fail-closed
            _report_audit_failure("create_trace")
            raise AppError(
                status_code=503,
                component="ai_backtest",
                code="service_unavailable",
                message="Backtest service is temporarily unavailable",
            ) from exc
        if claim.trace_id != trace_id:
            return _replay_or_conflict(claim)
        request_id = claim.request_id
        audit = _AuditWrites(self.repository, trace_id, trace_persisted=True)
        try:
            await self.repository.transition_idempotent_request(
                request_id,
                expected_state="claimed",
                next_state="generation_in_progress",
            )
            result = await self._execute_generated_backtest(
                request,
                trace_id=trace_id,
                audit=audit,
                request_id=request_id,
            )
            await self._complete_success(request_id, result)
            return result
        except Exception as exc:  # noqa: BLE001
            if not audit.failure_recorded:
                await self._record_flow_failure(request, audit=audit, exc=exc)
                await audit.write(
                    "finish_trace",
                    lambda: self.repository.finish_trace(
                        trace_id,
                        status="failed",
                        metadata_jsonb=(
                            {"failed_execution_id": str(audit.current_execution_id)}
                            if audit.current_execution_id is not None
                            else {}
                        ),
                    ),
                )
            if isinstance(exc, AppError) and exc.status_code in {422, 502, 504}:
                response = AIBacktestErrorResponse(
                    code=exc.code,
                    message=exc.message,
                    details=exc.details if isinstance(exc.details, dict) else None,
                )
                try:
                    await self._complete_failure(request_id, response.model_dump(mode="json"))
                except Exception:  # noqa: BLE001 - unresolved terminal persistence must remain blocked
                    await self._mark_outcome_unknown(request_id)
                raise
            await self._mark_outcome_unknown(request_id)
            raise

    async def _complete_success(self, request_id: UUID, result: AICodeBacktestFlowResult) -> None:
        await self._transition_from_any(
            request_id,
            ("execution_released", "generation_in_progress"),
            "succeeded",
            safety_lease="closed",
            terminal_response=result.model_dump(mode="json"),
        )

    async def _complete_failure(self, request_id: UUID, response: dict[str, object]) -> None:
        await self._transition_from_any(
            request_id,
            ("execution_released", "execution_outcome_unknown", "execution_armed", "generation_in_progress"),
            "failed",
            safety_lease="closed",
            terminal_response=response,
        )

    async def _mark_outcome_unknown(self, request_id: UUID) -> None:
        try:
            await self._transition_from_any(
                request_id,
                ("execution_released", "execution_armed", "generation_in_progress", "claimed"),
                "execution_outcome_unknown",
                safety_lease="blocked_unknown",
            )
        except AppError:
            # A concurrent observer never clears a durable unknown lease.
            return

    async def _transition_from_any(
        self,
        request_id: UUID,
        expected_states: tuple[str, ...],
        next_state: str,
        *,
        safety_lease: str | None = None,
        terminal_response: dict[str, object] | None = None,
        execution_run_id: UUID | None = None,
    ) -> None:
        last_error: AppError | None = None
        for expected_state in expected_states:
            try:
                await self.repository.transition_idempotent_request(
                    request_id,
                    expected_state=expected_state,
                    next_state=next_state,
                    safety_lease=safety_lease,
                    execution_run_id=execution_run_id,
                    terminal_response=terminal_response,
                )
                return
            except AppError as exc:
                if exc.code != "duplicate_execution_active":
                    raise
                last_error = exc
        if last_error is not None:
            raise last_error

    async def _execute_generated_backtest(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        audit: _AuditWrites,
        request_id: UUID,
    ) -> AICodeBacktestFlowResult:
        parse_id = uuid4()
        code_id = uuid4()
        validation_id = uuid4()
        execution_run_id = uuid4()
        started_at = _utcnow()

        # The request claim atomically created the trace before any external work.
        await self.repository.create_strategy_parse(
            AIStrategyParseCreate(
                parse_id=parse_id,
                session_id=request.session_id,
                user_id=request.user_id,
                trace_id=audit.trace_reference,
                raw_prompt=_redacted_prompt_token(request.natural_language_prompt),
                parsed_strategy_jsonb=request.parsed_strategy_jsonb,
                confidence=request.parse_confidence,
                model_name=request.parse_model_name,
                parse_status="parsed",
            )
        )

        generated = await self._run_generation(
            request,
            audit=audit,
            trace_id=trace_id,
            parse_id=parse_id,
            code_id=code_id,
        )
        await self._run_validation(
            request,
            audit=audit,
            trace_id=trace_id,
            code_id=code_id,
            validation_id=validation_id,
            generated=generated,
        )

        execution = await self._run_execution(
            request,
            audit=audit,
            trace_id=trace_id,
            code_id=code_id,
            request_id=request_id,
            execution_run_id=execution_run_id,
            generated=generated,
        )

        if execution.status != "succeeded" or execution.backtest_result is None:
            await self.repository.update_code_generation_status(code_id, "failed")
            audit.failure_recorded = True
            await audit.write(
                "finish_trace",
                lambda: self.repository.finish_trace(
                    trace_id,
                    status="failed",
                    metadata_jsonb={
                        "parse_id": str(parse_id),
                        "code_id": str(code_id),
                        "validation_id": str(validation_id),
                        "execution_run_id": str(execution_run_id),
                    },
                ),
            )
            raise AppError(
                status_code=504 if execution.status == "timeout" else 502,
                component="ai_backtest",
                code="code_execution_failed",
                message="Generated code execution failed before producing a backtest result",
                details={"trace_id": str(trace_id), "execution_run_id": str(execution_run_id), "status": execution.status},
            )

        await self.repository.update_code_generation_status(code_id, "executed")
        run_payload = execution.backtest_result.model_copy(
            update={
                "run": execution.backtest_result.run.model_copy(
                    update={
                        "run_id": execution.backtest_result.run.run_id,
                        "strategy_id": request.strategy_id,
                        "user_id": request.user_id,
                        "session_id": request.session_id,
                        "source_parse_id": parse_id,
                        "code_id": code_id,
                        "execution_run_id": execution_run_id,
                        "trace_id": audit.trace_reference,
                        "execution_mode": "ai_generated_code",
                        "data_source": execution.backtest_result.run.data_source or request.data_source,
                        "benchmark_ticker": execution.backtest_result.run.benchmark_ticker or request.benchmark_ticker,
                        "strategy_snapshot_jsonb": execution.backtest_result.run.strategy_snapshot_jsonb
                        or request.parsed_strategy_jsonb,
                    }
                )
            }
        )
        run_id = await self.repository.persist_backtest_result(run_payload)
        report = await self._run_report(
            request,
            audit=audit,
            trace_id=trace_id,
            run_id=run_id,
            execution=execution,
        )

        await audit.write(
            "finish_trace",
            lambda: self.repository.finish_trace(
                trace_id,
                status="succeeded",
                metadata_jsonb={
                    "parse_id": str(parse_id),
                    "code_id": str(code_id),
                    "validation_id": str(validation_id),
                    "execution_run_id": str(execution_run_id),
                    "run_id": str(run_id),
                    "report_id": str(report.report_id),
                },
            ),
        )
        return AICodeBacktestFlowResult(
            trace_id=trace_id,
            parse_id=parse_id,
            code_id=code_id,
            validation_id=validation_id,
            execution_run_id=execution_run_id,
            run_id=run_id,
            report_id=report.report_id,
            code_status="executed",
            execution_status=execution.status,
        )

    async def _run_generation(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        audit: _AuditWrites,
        trace_id: UUID,
        parse_id: UUID,
        code_id: UUID,
    ) -> GeneratedCodeResult:
        execution_id = uuid4()
        audit.current_execution_id = execution_id
        started_at = _utcnow()
        await audit.write(
            "create_agent_execution_log",
            lambda: self.repository.create_agent_execution_log(
                AgentExecutionLogCreate(
                    execution_id=execution_id,
                    trace_id=audit.trace_reference,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    agent_name="ai_backtest",
                    step_name="code_generation",
                    input_jsonb=_generation_input_payload(request),
                    started_at=started_at,
                )
            ),
        )
        try:
            generated = await self.code_generator.generate(request, trace_id=trace_id)
            code_hash = hashlib.sha256(generated.generated_code.encode("utf-8")).hexdigest()
            await self.repository.create_code_generation(
                AICodeGenerationCreate(
                    code_id=code_id,
                    parse_id=parse_id,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    trace_id=audit.trace_reference,
                    source_message_id=request.source_message_id,
                    target_runtime=generated.target_runtime,
                    code_purpose=generated.code_purpose,
                    generated_code=generated.generated_code,
                    code_hash=code_hash,
                    model_name=generated.model_name,
                    code_status="generated",
                )
            )
            if generated.model_call is not None:
                await self._persist_model_call(
                    request,
                    audit=audit,
                    execution_id=execution_id,
                    code_id=code_id,
                    bundle=generated.model_call,
                )
            await audit.write(
                "update_agent_execution_log",
                lambda: self.repository.update_agent_execution_log(
                    execution_id,
                    AgentExecutionLogUpdate(
                        status="succeeded",
                        output_jsonb=_generation_output_payload(
                            code_id=code_id,
                            code_hash=code_hash,
                            generated=generated,
                        ),
                        latency_ms=_latency_ms(started_at),
                    ),
                ),
            )
            audit.current_execution_id = None
            return generated
        except Exception as exc:  # noqa: BLE001
            captured_model_call = getattr(exc, "model_call", None)
            if isinstance(captured_model_call, ModelCallLogBundle):
                await self._persist_model_call(
                    request,
                    audit=audit,
                    execution_id=execution_id,
                    code_id=None,
                    bundle=captured_model_call,
                )
            await self._record_step_failure(
                request,
                audit=audit,
                trace_id=trace_id,
                execution_id=execution_id,
                error_type="code_generation_failed",
                cause_type=type(exc).__name__,
                cause_code=exc.code if isinstance(exc, AppError) else None,
                started_at=started_at,
            )
            raise

    async def _run_validation(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        audit: _AuditWrites,
        trace_id: UUID,
        code_id: UUID,
        validation_id: UUID,
        generated: GeneratedCodeResult,
    ) -> AICodeValidationResultCreate:
        execution_id = uuid4()
        audit.current_execution_id = execution_id
        started_at = _utcnow()
        await audit.write(
            "create_agent_execution_log",
            lambda: self.repository.create_agent_execution_log(
                AgentExecutionLogCreate(
                    execution_id=execution_id,
                    trace_id=audit.trace_reference,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    agent_name="ai_backtest",
                    step_name="code_validation",
                    input_jsonb={"code_id": str(code_id)},
                    started_at=started_at,
                )
            ),
        )
        try:
            validation_outcome = self.code_validator.validate(generated, trace_id=trace_id)
            validation = AICodeValidationResultCreate(
                validation_id=validation_id,
                code_id=code_id,
                **validation_outcome.model_dump(mode="python"),
            )
            await self.repository.create_code_validation_result(validation)
            if not validation.allows_execution:
                await self.repository.update_code_generation_status(code_id, "rejected")
                await audit.write(
                    "update_agent_execution_log",
                    lambda: self.repository.update_agent_execution_log(
                        execution_id,
                        AgentExecutionLogUpdate(
                            status="failed",
                            output_jsonb=_validation_output_payload(code_id=code_id, validation=validation),
                            error_message="Generated code failed validation",
                            latency_ms=_latency_ms(started_at),
                        ),
                    ),
                )
                await audit.write(
                    "create_error_log",
                    lambda: self.repository.create_error_log(
                        AIErrorLogCreate(
                            error_id=uuid4(),
                            trace_id=audit.trace_reference,
                            user_id=request.user_id,
                            session_id=request.session_id,
                            execution_id=execution_id,
                            error_type="generated_code_rejected",
                            error_message="Generated code failed validation",
                            context_jsonb=_validation_error_context(validation),
                            severity="warning",
                        )
                    ),
                )
                await audit.write(
                    "finish_trace",
                    lambda: self.repository.finish_trace(
                        trace_id,
                        status="rejected",
                        metadata_jsonb={"code_id": str(code_id), "validation_id": str(validation.validation_id)},
                    ),
                )
                audit.failure_recorded = True
                raise AppError(
                    status_code=422,
                    component="ai_backtest",
                    code="generated_code_rejected",
                    message="Generated code failed validation and was not executed",
                    details={
                        "trace_id": str(trace_id),
                        "code_id": str(code_id),
                        "validation_id": str(validation.validation_id),
                        "errors": validation.errors_jsonb,
                    },
                )
            await self.repository.update_code_generation_status(code_id, "validated")
            await audit.write(
                "update_agent_execution_log",
                lambda: self.repository.update_agent_execution_log(
                    execution_id,
                    AgentExecutionLogUpdate(
                        status="succeeded",
                        output_jsonb={"code_id": str(code_id), "validation_id": str(validation.validation_id)},
                        latency_ms=_latency_ms(started_at),
                    ),
                ),
            )
            audit.current_execution_id = None
            return validation
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, AppError) and exc.code == "generated_code_rejected":
                raise
            await self._record_step_failure(
                request,
                audit=audit,
                trace_id=trace_id,
                execution_id=execution_id,
                error_type="code_validation_failed",
                cause_type=type(exc).__name__,
                cause_code=exc.code if isinstance(exc, AppError) else None,
                started_at=started_at,
            )
            raise

    async def _run_execution(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        audit: _AuditWrites,
        trace_id: UUID,
        code_id: UUID,
        request_id: UUID,
        execution_run_id: UUID,
        generated: GeneratedCodeResult,
    ) -> CodeExecutionResult:
        execution_id = uuid4()
        audit.current_execution_id = execution_id
        started_at = _utcnow()
        await audit.write(
            "create_agent_execution_log",
            lambda: self.repository.create_agent_execution_log(
                AgentExecutionLogCreate(
                    execution_id=execution_id,
                    trace_id=audit.trace_reference,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    execution_run_id=execution_run_id,
                    agent_name="ai_backtest",
                    step_name="code_execution",
                    input_jsonb={"code_id": str(code_id), "target_runtime": generated.target_runtime},
                    started_at=started_at,
                )
            ),
        )
        try:
            await self.repository.create_code_execution_run(
                CodeExecutionRunCreate(
                    execution_run_id=execution_run_id,
                    code_id=code_id,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    trace_id=audit.trace_reference,
                    runtime_env=generated.target_runtime,
                    status="running",
                    timeout_seconds=request.timeout_seconds,
                    memory_limit_mb=request.memory_limit_mb,
                    started_at=started_at,
                )
            )
            armed_claim = await self.repository.transition_idempotent_request(
                request_id,
                expected_state="generation_in_progress",
                next_state="execution_armed",
                execution_run_id=execution_run_id,
            )

            async def persist_process_identity(identity) -> None:
                await self.repository.record_code_execution_process_identity(
                    execution_run_id,
                    attempt_id=identity.attempt_id,
                    worker_host=identity.worker_host,
                    worker_pid=identity.worker_pid,
                    worker_pgid=identity.worker_pgid,
                    worker_started_at=identity.worker_started_at,
                    idempotency_request_id=request_id,
                )

            release_authorized = False

            async def authorize_subprocess_release(identity) -> None:
                nonlocal release_authorized
                await self.repository.release_armed_execution_request(
                    request_id,
                    expected_state_version=armed_claim.state_version,
                    execution_run_id=execution_run_id,
                    attempt_id=identity.attempt_id,
                )
                release_authorized = True

            result = await self.code_executor.execute(
                request,
                generated,
                trace_id=trace_id,
                execution_run_id=execution_run_id,
                process_identity_recorder=persist_process_identity,
                release_authorizer=authorize_subprocess_release,
            )
            if not release_authorized:
                raise AppError(
                    status_code=503,
                    component="ai_backtest",
                    code="execution_release_not_authorized",
                    message="Execution completed without a durable release authorization",
                    details={"request_id": str(request_id), "execution_run_id": str(execution_run_id)},
                )
            await self.repository.update_code_execution_run(
                execution_run_id,
                CodeExecutionRunUpdate(
                    status=result.status,
                    latency_ms=result.latency_ms,
                    stdout=_redacted_stream_summary("stdout", result.stdout),
                    stderr=_redacted_stream_summary("stderr", result.stderr),
                    output_artifacts_jsonb=result.output_artifacts_jsonb,
                    sandbox_id=result.sandbox_id,
                    started_at=result.started_at or started_at,
                    ended_at=result.ended_at,
                ),
            )
            await audit.write(
                "update_agent_execution_log",
                lambda: self.repository.update_agent_execution_log(
                    execution_id,
                    AgentExecutionLogUpdate(
                        status="succeeded" if result.status == "succeeded" else "failed",
                        output_jsonb=_execution_output_payload(execution_run_id=execution_run_id, result=result),
                        error_message=(
                            None if result.status == "succeeded" else _execution_failure_message(result.status)
                        ),
                        latency_ms=result.latency_ms or _latency_ms(started_at),
                    ),
                ),
            )
            if result.status != "succeeded":
                await audit.write(
                    "create_error_log",
                    lambda: self.repository.create_error_log(
                        AIErrorLogCreate(
                            error_id=uuid4(),
                            trace_id=audit.trace_reference,
                            user_id=request.user_id,
                            session_id=request.session_id,
                            execution_id=execution_id,
                            execution_run_id=execution_run_id,
                            error_type="code_execution_failed",
                            error_message=_execution_failure_message(result.status),
                            context_jsonb=_execution_failure_context(result),
                            severity="warning" if result.status == "timeout" else "error",
                        )
                    ),
                )
            audit.current_execution_id = None
            return result
        except Exception as exc:  # noqa: BLE001
            await self._record_step_failure(
                request,
                audit=audit,
                trace_id=trace_id,
                execution_id=execution_id,
                execution_run_id=execution_run_id,
                error_type="code_execution_failed",
                cause_type=type(exc).__name__,
                cause_code=exc.code if isinstance(exc, AppError) else None,
                started_at=started_at,
            )
            raise

    async def _run_report(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        audit: _AuditWrites,
        trace_id: UUID,
        run_id: UUID,
        execution: CodeExecutionResult,
    ) -> AIBacktestReportCreate:
        execution_id = uuid4()
        audit.current_execution_id = execution_id
        started_at = _utcnow()
        await audit.write(
            "create_agent_execution_log",
            lambda: self.repository.create_agent_execution_log(
                AgentExecutionLogCreate(
                    execution_id=execution_id,
                    trace_id=audit.trace_reference,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    run_id=run_id,
                    agent_name="ai_backtest",
                    step_name="report_generation",
                    input_jsonb={"run_id": str(run_id)},
                    started_at=started_at,
                )
            ),
        )
        try:
            report_draft = await self.report_generator.build_report(
                request,
                trace_id=trace_id,
                run_id=run_id,
                execution=execution,
            )
            report = AIBacktestReportCreate(
                report_id=uuid4(),
                run_id=run_id,
                user_id=request.user_id,
                trace_id=audit.trace_reference,
                **report_draft.model_dump(mode="python"),
            )
            await self.repository.create_ai_backtest_report(report)
            if report.model_call is not None:
                await self._persist_model_call(
                    request,
                    audit=audit,
                    execution_id=execution_id,
                    code_id=None,
                    bundle=report.model_call,
                )
            await audit.write(
                "update_agent_execution_log",
                lambda: self.repository.update_agent_execution_log(
                    execution_id,
                    AgentExecutionLogUpdate(
                        status="succeeded",
                        output_jsonb={"report_id": str(report.report_id), "run_id": str(run_id)},
                        latency_ms=_latency_ms(started_at),
                    ),
                ),
            )
            audit.current_execution_id = None
            return report
        except Exception as exc:  # noqa: BLE001
            await self._record_step_failure(
                request,
                audit=audit,
                trace_id=trace_id,
                execution_id=execution_id,
                run_id=run_id,
                error_type="report_generation_failed",
                cause_type=type(exc).__name__,
                cause_code=exc.code if isinstance(exc, AppError) else None,
                started_at=started_at,
            )
            raise

    async def _record_flow_failure(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        audit: _AuditWrites,
        exc: Exception,
    ) -> None:
        audit.failure_recorded = True
        cause_type = type(exc).__name__
        error_type = exc.code if isinstance(exc, AppError) else cause_type
        message = f"AI backtest flow failed. Cause type: {cause_type}."
        if isinstance(exc, AppError):
            message = f"{message} Error code: {exc.code}."
        if audit.current_execution_id is not None:
            await audit.write(
                "update_agent_execution_log",
                lambda: self.repository.update_agent_execution_log(
                    audit.current_execution_id,
                    AgentExecutionLogUpdate(
                        status="failed",
                        output_jsonb={"error_code": error_type, "cause_type": cause_type},
                        error_message=message,
                    ),
                ),
            )
        await audit.write(
            "create_error_log",
            lambda: self.repository.create_error_log(
                AIErrorLogCreate(
                    error_id=uuid4(),
                    trace_id=audit.trace_reference,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    execution_id=audit.current_execution_id,
                    error_type=error_type,
                    error_message=message,
                    context_jsonb={"cause_type": cause_type, "error_code": error_type},
                    severity="error",
                )
            ),
        )

    async def _persist_model_call(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        audit: _AuditWrites,
        execution_id: UUID,
        code_id: UUID | None,
        bundle: ModelCallLogBundle,
    ) -> None:
        call_id = await audit.write(
            "create_model_call_log",
            lambda: self.repository.create_model_call_log(
                trace_id=audit.trace_reference,
                execution_id=execution_id,
                user_id=request.user_id,
                session_id=request.session_id,
                message_id=request.source_message_id,
                code_id=code_id,
                bundle=bundle,
                raw_audit_admission=self.raw_audit_admission,
            ),
        )
        if bundle.status != "failed" or not isinstance(call_id, UUID):
            return
        await audit.write(
            "create_error_log",
            lambda: self.repository.create_error_log(
                AIErrorLogCreate(
                    error_id=uuid4(),
                    trace_id=audit.trace_reference,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    call_id=call_id,
                    execution_id=execution_id,
                    error_type=bundle.error_type or "model_call_failed",
                    error_message=bundle.error_message or "Model call failed before fallback execution.",
                    context_jsonb={"task_type": bundle.task_type, "fallback_used": True},
                    severity="error",
                )
            ),
        )

    async def _record_step_failure(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        audit: _AuditWrites,
        trace_id: UUID,
        execution_id: UUID,
        error_type: str,
        cause_type: str,
        cause_code: str | None,
        started_at: datetime,
        execution_run_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> None:
        audit.failure_recorded = True
        message = _step_failure_message(error_type, cause_type=cause_type, cause_code=cause_code)
        await audit.write(
            "update_agent_execution_log",
            lambda: self.repository.update_agent_execution_log(
                execution_id,
                AgentExecutionLogUpdate(
                    status="failed",
                    output_jsonb=_step_failure_output_payload(
                        error_type=error_type,
                        cause_type=cause_type,
                        cause_code=cause_code,
                        run_id=run_id,
                    ),
                    error_message=message,
                    latency_ms=_latency_ms(started_at),
                ),
            ),
        )
        await audit.write(
            "create_error_log",
            lambda: self.repository.create_error_log(
                AIErrorLogCreate(
                    error_id=uuid4(),
                    trace_id=audit.trace_reference,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    execution_id=execution_id,
                    execution_run_id=execution_run_id,
                    error_type=error_type,
                    error_message=message,
                    context_jsonb=_step_failure_context(
                        error_type=error_type,
                        cause_type=cause_type,
                        cause_code=cause_code,
                        run_id=run_id,
                    ),
                    severity="error",
                )
            ),
        )
        await audit.write(
            "finish_trace",
            lambda: self.repository.finish_trace(
                trace_id,
                status="failed",
                metadata_jsonb={"failed_execution_id": str(execution_id)},
            ),
        )


REQUEST_FINGERPRINT_VERSION = "ai-backtest-intent-v1"
_IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9._~-]{8,128}$"


def build_request_fingerprint(payload: AICodeBacktestFlowRequest) -> tuple[str, str]:
    intent = {
        "natural_language_prompt": " ".join(unicodedata.normalize("NFC", payload.natural_language_prompt).split()),
        "parsed_strategy_jsonb": _canonical_json_value(payload.parsed_strategy_jsonb),
        "parse_confidence": _canonical_json_value(payload.parse_confidence),
        "parse_model_name": _canonical_json_value(payload.parse_model_name),
        "strategy_id": _canonical_json_value(payload.strategy_id),
        "target_runtime": _canonical_json_value(payload.target_runtime),
        "code_purpose": _canonical_json_value(payload.code_purpose),
        "benchmark_ticker": _canonical_json_value(payload.benchmark_ticker),
        "data_source": _canonical_json_value(payload.data_source),
        "report_model_name": _canonical_json_value(payload.report_model_name),
        "timeout_seconds": payload.timeout_seconds,
        "memory_limit_mb": payload.memory_limit_mb,
    }
    canonical = json.dumps(
        intent,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return REQUEST_FINGERPRINT_VERSION, hashlib.sha256(canonical).hexdigest()


def _canonical_json_value(value: object) -> object:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AppError(
                status_code=422,
                component="ai_backtest",
                code="request_validation_failed",
                message="Request contains a non-finite number",
            )
        return value
    if isinstance(value, list):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AppError(
                    status_code=422,
                    component="ai_backtest",
                    code="request_validation_failed",
                    message="Request contains a non-string JSON key",
                )
            normalized[unicodedata.normalize("NFC", key)] = _canonical_json_value(item)
        return normalized
    raise AppError(
        status_code=422,
        component="ai_backtest",
        code="request_validation_failed",
        message="Request contains a non-JSON value",
    )


def _validate_execution_request(request: AICodeBacktestFlowRequest) -> None:
    context = request.execution_context
    if context is None or request.user_id != context.user_id:
        raise AppError(
            status_code=401,
            component="ai_backtest",
            code="execution_context_required",
            message="Authenticated execution context is required",
        )
    if request.idempotency_key is None or not re.fullmatch(_IDEMPOTENCY_KEY_PATTERN, request.idempotency_key):
        raise AppError(
            status_code=400,
            component="ai_backtest",
            code="idempotency_key_invalid",
            message="A valid Idempotency-Key is required",
        )
    fingerprint_version, fingerprint = build_request_fingerprint(request)
    if request.fingerprint_version != fingerprint_version or request.request_fingerprint != fingerprint:
        raise AppError(
            status_code=422,
            component="ai_backtest",
            code="request_validation_failed",
            message="Request fingerprint is invalid",
        )


def _replay_or_conflict(
    claim: AIBacktestRequestClaim,
) -> AICodeBacktestFlowResult | AIBacktestRunningResponse | AIBacktestErrorResponse:
    if claim.terminal_response is not None:
        if "code" in claim.terminal_response:
            return AIBacktestErrorResponse.model_validate(claim.terminal_response)
        return AICodeBacktestFlowResult.model_validate(claim.terminal_response)
    if claim.state == "execution_outcome_unknown" or claim.safety_lease == "blocked_unknown":
        raise AppError(
            status_code=409,
            component="ai_backtest",
            code="execution_outcome_unknown",
            message="Prior execution outcome is unresolved",
            details={"request_id": str(claim.request_id), "trace_id": str(claim.trace_id) if claim.trace_id else None, "state": claim.state},
        )
    return AIBacktestRunningResponse(
        request_id=claim.request_id,
        trace_id=claim.trace_id,
        state=claim.state,
    )

def _generation_input_payload(request: AICodeBacktestFlowRequest) -> dict[str, object]:
    return {
        "strategy_id": request.strategy_id,
        "target_runtime": request.target_runtime,
        "code_purpose": request.code_purpose,
        "has_parsed_strategy": bool(request.parsed_strategy_jsonb),
        "request_text_sha256": _sha256_text(request.natural_language_prompt),
    }


def _generation_output_payload(
    *,
    code_id: UUID,
    code_hash: str,
    generated: GeneratedCodeResult,
) -> dict[str, object]:
    return {
        "code_id": str(code_id),
        "code_hash": code_hash,
        "model_call_logged": generated.model_call is not None,
    }


def _validation_output_payload(*, code_id: UUID, validation) -> dict[str, object]:
    return {
        "code_id": str(code_id),
        "validation_id": str(validation.validation_id),
        "error_count": len(validation.errors_jsonb),
        "warning_count": len(validation.warnings_jsonb),
        "validation_error_codes": _validation_issue_codes(validation.errors_jsonb),
        "validation_warning_codes": _validation_issue_codes(validation.warnings_jsonb),
    }


def _validation_error_context(validation) -> dict[str, object]:
    return {
        "code_id": str(validation.code_id),
        "validation_id": str(validation.validation_id),
        "error_count": len(validation.errors_jsonb),
        "warning_count": len(validation.warnings_jsonb),
        "validation_error_codes": _validation_issue_codes(validation.errors_jsonb),
        "validation_warning_codes": _validation_issue_codes(validation.warnings_jsonb),
    }


def _validation_issue_codes(items: list[dict[str, object]]) -> list[str]:
    codes: list[str] = []
    for item in items:
        code = item.get("code") or item.get("rule") or item.get("type")
        if isinstance(code, str) and code and code not in codes:
            codes.append(code)
    return codes


def _execution_output_payload(*, execution_run_id: UUID, result: CodeExecutionResult) -> dict[str, object]:
    payload = {
        "execution_run_id": str(execution_run_id),
        "status": result.status,
        "has_backtest_result": result.backtest_result is not None,
        "stdout_present": bool(result.stdout),
        "stderr_present": bool(result.stderr),
    }
    if result.sandbox_id:
        payload["sandbox_id"] = result.sandbox_id
    return payload


def _execution_failure_context(execution: CodeExecutionResult) -> dict[str, object]:
    return {
        "status": execution.status,
        "stdout_present": bool(execution.stdout),
        "stderr_present": bool(execution.stderr),
        "stdout_sha256": _sha256_text(execution.stdout) if execution.stdout else None,
        "stderr_sha256": _sha256_text(execution.stderr) if execution.stderr else None,
        "stdout_char_count": len(execution.stdout or ""),
        "stderr_char_count": len(execution.stderr or ""),
    }


def _execution_failure_message(status: str) -> str:
    return f"Sandbox execution ended with status={status} before producing a backtest result"


def _step_failure_message(error_type: str, *, cause_type: str, cause_code: str | None) -> str:
    message = {
        "code_generation_failed": "Code generation failed before producing a persisted result.",
        "code_validation_failed": "Code validation failed before producing a persisted result.",
        "code_execution_failed": "Code execution failed before producing a persisted result.",
        "report_generation_failed": "Report generation failed before producing a persisted result.",
    }.get(error_type, "AI backtest step failed before producing a persisted result.")
    message = f"{message} Cause type: {cause_type}."
    if cause_code is not None:
        message = f"{message} Error code: {cause_code}."
    return message


def _step_failure_output_payload(
    *, error_type: str, cause_type: str, cause_code: str | None, run_id: UUID | None
) -> dict[str, object]:
    payload: dict[str, object] = {"error_code": error_type, "cause_type": cause_type}
    if cause_code is not None:
        payload["cause_code"] = cause_code
    if run_id is not None:
        payload["run_id"] = str(run_id)
    return payload


def _step_failure_context(
    *, error_type: str, cause_type: str, cause_code: str | None, run_id: UUID | None
) -> dict[str, object]:
    payload: dict[str, object] = {"error_code": error_type, "cause_type": cause_type}
    if cause_code is not None:
        payload["cause_code"] = cause_code
    if run_id is not None:
        payload["run_id"] = str(run_id)
    return payload


def _redacted_stream_summary(name: str, value: str | None) -> str | None:
    if not value:
        return None
    return f"{name} redacted sha256={_sha256_text(value)} chars={len(value)}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redacted_prompt_token(value: str) -> str:
    return f"prompt_redacted_sha256={_sha256_text(value)}"


def ai_backtest_audit_failure_count() -> int:
    with _AUDIT_FAILURE_COUNT_LOCK:
        return _AUDIT_FAILURE_COUNT


def _report_audit_failure(operation: str) -> None:
    global _AUDIT_FAILURE_COUNT
    with _AUDIT_FAILURE_COUNT_LOCK:
        _AUDIT_FAILURE_COUNT += 1
    try:
        print(
            json.dumps(
                {"event": "ai_audit_failure", "operation": f"backend.{operation}"[:64]},
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
    except Exception:  # noqa: BLE001 - reporting failure must remain fail-open
        return


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _latency_ms(started_at: datetime) -> float:
    return round((_utcnow() - started_at).total_seconds() * 1000, 6)
