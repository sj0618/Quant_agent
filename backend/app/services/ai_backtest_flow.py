from __future__ import annotations

import hashlib
import json
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

    async def run_generated_backtest(self, request: AICodeBacktestFlowRequest) -> AICodeBacktestFlowResult:
        trace_id = request.trace_id or uuid4()
        audit = _AuditWrites(self.repository, trace_id)
        try:
            return await self._execute_generated_backtest(request, trace_id=trace_id, audit=audit)
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, AppError) and exc.code == "generated_code_rejected":
                raise
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
            raise

    async def _execute_generated_backtest(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        audit: _AuditWrites,
    ) -> AICodeBacktestFlowResult:
        parse_id = uuid4()
        code_id = uuid4()
        validation_id = uuid4()
        execution_run_id = uuid4()
        started_at = _utcnow()

        await audit.start(
            AITraceCreate(
                trace_id=trace_id,
                user_id=request.user_id,
                session_id=request.session_id,
                metadata_jsonb={"entrypoint": "ai_generated_backtest", "strategy_id": request.strategy_id},
                started_at=started_at,
            )
        )
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
            result = await self.code_executor.execute(
                request,
                generated,
                trace_id=trace_id,
                execution_run_id=execution_run_id,
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
