from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
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
)


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
        parse_id = uuid4()
        code_id = uuid4()
        validation_id = uuid4()
        execution_run_id = uuid4()
        started_at = _utcnow()

        await self.repository.create_trace(
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
                trace_id=trace_id,
                raw_prompt=_redacted_prompt_token(request.natural_language_prompt),
                parsed_strategy_jsonb=request.parsed_strategy_jsonb,
                confidence=request.parse_confidence,
                model_name=request.parse_model_name,
                parse_status="parsed",
            )
        )

        generated = await self._run_generation(request, trace_id=trace_id, parse_id=parse_id, code_id=code_id)
        validation_outcome = self.code_validator.validate(generated, trace_id=trace_id)
        validation = AICodeValidationResultCreate(
            validation_id=validation_id,
            code_id=code_id,
            **validation_outcome.model_dump(mode="python"),
        )
        await self._run_validation(
            request,
            trace_id=trace_id,
            code_id=code_id,
            validation=validation,
        )

        execution = await self._run_execution(
            request,
            trace_id=trace_id,
            code_id=code_id,
            execution_run_id=execution_run_id,
            generated=generated,
        )

        if execution.status != "succeeded" or execution.backtest_result is None:
            await self.repository.update_code_generation_status(code_id, "failed")
            await self.repository.finish_trace(
                trace_id,
                status="failed",
                metadata_jsonb={
                    "parse_id": str(parse_id),
                    "code_id": str(code_id),
                    "validation_id": str(validation_id),
                    "execution_run_id": str(execution_run_id),
                },
            )
            failure_message = _execution_failure_message(execution.status)
            await self.repository.create_error_log(
                AIErrorLogCreate(
                    error_id=uuid4(),
                    trace_id=trace_id,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    execution_run_id=execution_run_id,
                    error_type="code_execution_failed",
                    error_message=failure_message,
                    context_jsonb=_execution_failure_context(execution),
                    severity="error" if execution.status != "timeout" else "warning",
                )
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
                        "trace_id": trace_id,
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
            trace_id=trace_id,
            run_id=run_id,
            execution=execution,
        )

        await self.repository.finish_trace(
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
        trace_id: UUID,
        parse_id: UUID,
        code_id: UUID,
    ) -> GeneratedCodeResult:
        execution_id = uuid4()
        started_at = _utcnow()
        await self.repository.create_agent_execution_log(
            AgentExecutionLogCreate(
                execution_id=execution_id,
                trace_id=trace_id,
                user_id=request.user_id,
                session_id=request.session_id,
                agent_name="ai_backtest",
                step_name="code_generation",
                input_jsonb=_generation_input_payload(request),
                started_at=started_at,
            )
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
                    trace_id=trace_id,
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
                await self.repository.create_model_call_log(
                    trace_id=trace_id,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    message_id=request.source_message_id,
                    code_id=code_id,
                    bundle=generated.model_call,
                )
            await self.repository.update_agent_execution_log(
                execution_id,
                AgentExecutionLogUpdate(
                    status="succeeded",
                    output_jsonb=_generation_output_payload(code_id=code_id, code_hash=code_hash, generated=generated),
                    latency_ms=_latency_ms(started_at),
                ),
            )
            return generated
        except Exception:  # noqa: BLE001
            await self._record_step_failure(
                request,
                trace_id=trace_id,
                execution_id=execution_id,
                error_type="code_generation_failed",
                started_at=started_at,
            )
            raise

    async def _run_validation(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        code_id: UUID,
        validation: AICodeValidationResultCreate,
    ) -> None:
        execution_id = uuid4()
        started_at = _utcnow()
        await self.repository.create_agent_execution_log(
            AgentExecutionLogCreate(
                execution_id=execution_id,
                trace_id=trace_id,
                user_id=request.user_id,
                session_id=request.session_id,
                agent_name="ai_backtest",
                step_name="code_validation",
                input_jsonb={"code_id": str(code_id)},
                started_at=started_at,
            )
        )
        await self.repository.create_code_validation_result(validation)
        if not validation.allows_execution:
            await self.repository.update_code_generation_status(code_id, "rejected")
            await self.repository.update_agent_execution_log(
                execution_id,
                AgentExecutionLogUpdate(
                    status="failed",
                    output_jsonb=_validation_output_payload(code_id=code_id, validation=validation),
                    error_message="Generated code failed validation",
                    latency_ms=_latency_ms(started_at),
                ),
            )
            await self.repository.create_error_log(
                AIErrorLogCreate(
                    error_id=uuid4(),
                    trace_id=trace_id,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    execution_id=execution_id,
                    error_type="generated_code_rejected",
                    error_message="Generated code failed validation",
                    context_jsonb=_validation_error_context(validation),
                    severity="warning",
                )
            )
            await self.repository.finish_trace(
                trace_id,
                status="rejected",
                metadata_jsonb={"code_id": str(code_id), "validation_id": str(validation.validation_id)},
            )
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
        await self.repository.update_agent_execution_log(
            execution_id,
            AgentExecutionLogUpdate(
                status="succeeded",
                output_jsonb={"code_id": str(code_id), "validation_id": str(validation.validation_id)},
                latency_ms=_latency_ms(started_at),
            ),
        )

    async def _run_execution(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        code_id: UUID,
        execution_run_id: UUID,
        generated: GeneratedCodeResult,
    ) -> CodeExecutionResult:
        execution_id = uuid4()
        started_at = _utcnow()
        await self.repository.create_agent_execution_log(
            AgentExecutionLogCreate(
                execution_id=execution_id,
                trace_id=trace_id,
                user_id=request.user_id,
                session_id=request.session_id,
                execution_run_id=execution_run_id,
                agent_name="ai_backtest",
                step_name="code_execution",
                input_jsonb={"code_id": str(code_id), "target_runtime": generated.target_runtime},
                started_at=started_at,
            )
        )
        await self.repository.create_code_execution_run(
            CodeExecutionRunCreate(
                execution_run_id=execution_run_id,
                code_id=code_id,
                user_id=request.user_id,
                session_id=request.session_id,
                trace_id=trace_id,
                runtime_env=generated.target_runtime,
                status="running",
                timeout_seconds=request.timeout_seconds,
                memory_limit_mb=request.memory_limit_mb,
                started_at=started_at,
            )
        )
        try:
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
            await self.repository.update_agent_execution_log(
                execution_id,
                AgentExecutionLogUpdate(
                    status="succeeded" if result.status == "succeeded" else "failed",
                    output_jsonb=_execution_output_payload(execution_run_id=execution_run_id, result=result),
                    error_message=None if result.status == "succeeded" else _execution_failure_message(result.status),
                    latency_ms=result.latency_ms or _latency_ms(started_at),
                ),
            )
            return result
        except Exception:  # noqa: BLE001
            await self._record_step_failure(
                request,
                trace_id=trace_id,
                execution_id=execution_id,
                execution_run_id=execution_run_id,
                error_type="code_execution_failed",
                started_at=started_at,
            )
            raise

    async def _run_report(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        run_id: UUID,
        execution: CodeExecutionResult,
    ) -> AIBacktestReportCreate:
        execution_id = uuid4()
        started_at = _utcnow()
        await self.repository.create_agent_execution_log(
            AgentExecutionLogCreate(
                execution_id=execution_id,
                trace_id=trace_id,
                user_id=request.user_id,
                session_id=request.session_id,
                run_id=run_id,
                agent_name="ai_backtest",
                step_name="report_generation",
                input_jsonb={"run_id": str(run_id)},
                started_at=started_at,
            )
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
                trace_id=trace_id,
                **report_draft.model_dump(mode="python"),
            )
            await self.repository.create_ai_backtest_report(report)
            if report.model_call is not None:
                await self.repository.create_model_call_log(
                    trace_id=trace_id,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    message_id=request.source_message_id,
                    code_id=None,
                    bundle=report.model_call,
                )
            await self.repository.update_agent_execution_log(
                execution_id,
                AgentExecutionLogUpdate(
                    status="succeeded",
                    output_jsonb={"report_id": str(report.report_id), "run_id": str(run_id)},
                    latency_ms=_latency_ms(started_at),
                ),
            )
            return report
        except Exception:  # noqa: BLE001
            await self._record_step_failure(
                request,
                trace_id=trace_id,
                execution_id=execution_id,
                run_id=run_id,
                error_type="report_generation_failed",
                started_at=started_at,
            )
            raise

    async def _record_step_failure(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        execution_id: UUID,
        error_type: str,
        started_at: datetime,
        execution_run_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> None:
        message = _step_failure_message(error_type)
        await self.repository.update_agent_execution_log(
            execution_id,
            AgentExecutionLogUpdate(
                status="failed",
                output_jsonb=_step_failure_output_payload(error_type=error_type, run_id=run_id),
                error_message=message,
                latency_ms=_latency_ms(started_at),
            ),
        )
        await self.repository.create_error_log(
            AIErrorLogCreate(
                error_id=uuid4(),
                trace_id=trace_id,
                user_id=request.user_id,
                session_id=request.session_id,
                execution_id=execution_id,
                execution_run_id=execution_run_id,
                error_type=error_type,
                error_message=message,
                context_jsonb=_step_failure_context(error_type=error_type, run_id=run_id),
                severity="error",
            )
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


def _step_failure_message(error_type: str) -> str:
    return {
        "code_generation_failed": "Code generation failed before producing a persisted result.",
        "code_execution_failed": "Code execution failed before producing a persisted result.",
        "report_generation_failed": "Report generation failed before producing a persisted result.",
    }.get(error_type, "AI backtest step failed before producing a persisted result.")


def _step_failure_output_payload(*, error_type: str, run_id: UUID | None) -> dict[str, object]:
    payload: dict[str, object] = {"error_code": error_type}
    if run_id is not None:
        payload["run_id"] = str(run_id)
    return payload


def _step_failure_context(*, error_type: str, run_id: UUID | None) -> dict[str, object]:
    payload: dict[str, object] = {"error_code": error_type}
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
def _utcnow() -> datetime:
    return datetime.now(UTC)


def _latency_ms(started_at: datetime) -> float:
    return round((_utcnow() - started_at).total_seconds() * 1000, 6)
