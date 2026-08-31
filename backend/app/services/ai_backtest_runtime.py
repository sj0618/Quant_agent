from __future__ import annotations

import ast
import hashlib
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.core.errors import AppError
from app.schemas.ai_backtest import (
    AIBacktestReportDraft,
    AICodeBacktestFlowRequest,
    CodeExecutionResult,
    CodeValidationOutcome,
    GeneratedCodeResult,
    ModelCallLogBundle,
    PromptLogBundle,
)

RUNTIME_ALLOWED_IMPORTS = frozenset({"datetime", "math", "statistics"})
NETWORK_MODULE_ROOTS = frozenset({"socket", "requests", "urllib", "urllib3", "httpx", "aiohttp", "ftplib"})
FILE_IO_MODULE_ROOTS = frozenset({"pathlib", "pickle", "shelve", "tempfile", "shutil"})
SUSPICIOUS_NETWORK_CALLS = frozenset(
    {
        "socket",
        "socket.socket",
        "socket.create_connection",
        "urllib.request.urlopen",
        "urllib.request.Request",
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.delete",
        "requests.request",
        "httpx.get",
        "httpx.post",
        "httpx.put",
        "httpx.delete",
        "httpx.request",
        "httpx.Client",
        "httpx.AsyncClient",
        "aiohttp.ClientSession",
        "ftplib.FTP",
    }
)
SUSPICIOUS_FILE_CALLS = frozenset(
    {
        "open",
        "pathlib.Path.open",
        "pathlib.Path.write_text",
        "pathlib.Path.write_bytes",
        "pathlib.Path.touch",
        "pathlib.Path.mkdir",
        "pathlib.Path.unlink",
        "pathlib.Path.rename",
        "pathlib.Path.replace",
        "pickle.dump",
        "shelve.open",
        "tempfile.NamedTemporaryFile",
        "tempfile.mkstemp",
        "tempfile.mkdtemp",
        "shutil.copy",
        "shutil.copy2",
        "shutil.copyfile",
        "shutil.move",
        "shutil.rmtree",
        "pandas.read_csv",
        "pandas.read_excel",
        "pandas.read_json",
        "pandas.read_parquet",
        "pandas.read_pickle",
        "pandas.DataFrame.to_csv",
        "pandas.DataFrame.to_excel",
        "pandas.DataFrame.to_json",
        "pandas.DataFrame.to_parquet",
        "pandas.DataFrame.to_pickle",
    }
)


class CodeGenerationFailure(RuntimeError):
    def __init__(self, message: str, *, model_call: ModelCallLogBundle) -> None:
        super().__init__(message)
        self.model_call = model_call


class AOAICodeGenerator:
    async def generate(self, request: AICodeBacktestFlowRequest, *, trace_id: UUID) -> GeneratedCodeResult:
        (
            build_strategy_spec,
            build_backtest_code_json_request,
            create_llm_client,
            generate_loop3_candidates,
            Loop3Request,
            StrategySpec,
            AOAIResponsesClient,
            MockLLMClient,
        ) = _load_generation_modules()
        strategy = (
            StrategySpec.model_validate(request.parsed_strategy_jsonb)
            if request.parsed_strategy_jsonb
            else build_strategy_spec(request.natural_language_prompt, variant="A")
        )
        prompt_request = build_backtest_code_json_request(strategy, "A")
        llm_client = create_llm_client(role="BACKTEST_CODE")
        RecordingAuditSink, bind_audit_context, create_audit_correlation = _load_audit_modules()
        capture_sink = RecordingAuditSink()
        capture_session = capture_sink.open_session(
            create_audit_correlation(
                trace_id=str(trace_id),
                debug_ref=None,
                entrypoint="backend.ai_backtest",
                feature="backtest_code_generation",
                strategy_id=getattr(strategy, "strategy_id", None),
                user_id=str(request.user_id) if request.user_id is not None else None,
                session_id=str(request.session_id) if request.session_id is not None else None,
                db_trace_id=trace_id,
            )
        )
        provider, model_name = _observed_provider_and_model(
            llm_client,
            aoai_client_type=AOAIResponsesClient,
            mock_client_type=MockLLMClient,
        )
        try:
            with bind_audit_context(capture_session):
                result = generate_loop3_candidates(
                    Loop3Request(strategy=strategy, variant="A", trace_id=str(trace_id)),
                    llm_client=llm_client,
                )
        except Exception as exc:
            if not capture_session.model_calls:
                raise
            raise CodeGenerationFailure(
                "Code generation failed after the model call and deterministic fallback.",
                model_call=_build_generation_model_call(
                    request,
                    prompt_request=prompt_request,
                    strategy_id=getattr(strategy, "strategy_id", None),
                    provider=provider,
                    model_name=model_name,
                    fallback_error=_generation_exception_error(exc),
                    captured_model=capture_session.model_calls[0],
                    captured_prompt=capture_session.prompt_logs[0],
                    captured_error=next(
                        (event for event in capture_session.buffered_events if event.kind == "error"),
                        None,
                    ),
                ),
            ) from exc
        selected = next((candidate for candidate in result.candidates if candidate.validation_ok), result.selected_candidate)
        fallback_error = _fallback_error(result)
        return GeneratedCodeResult(
            target_runtime=request.target_runtime,
            code_purpose=request.code_purpose,
            generated_code=selected.code,
            model_name=model_name,
            model_call=_build_generation_model_call(
                request,
                prompt_request=prompt_request,
                strategy_id=getattr(strategy, "strategy_id", None),
                provider=provider,
                model_name=model_name,
                fallback_error=fallback_error,
                captured_model=capture_session.model_calls[0] if capture_session.model_calls else None,
                captured_prompt=capture_session.prompt_logs[0] if capture_session.prompt_logs else None,
                captured_error=next(
                    (event for event in capture_session.buffered_events if event.kind == "error"),
                    None,
                ),
            ),
        )


class ASTCodeValidator:
    def validate(self, generated: GeneratedCodeResult, *, trace_id: UUID) -> CodeValidationOutcome:
        validate_backtest_code = _load_validate_backtest_code()
        result = validate_backtest_code(generated.generated_code)
        try:
            tree = ast.parse(generated.generated_code)
        except SyntaxError:
            tree = None

        import_violations = [] if tree is None else _runtime_import_violations(tree)
        network_violations = [] if tree is None else _suspicious_usage(tree, SUSPICIOUS_NETWORK_CALLS, NETWORK_MODULE_ROOTS)
        file_violations = [] if tree is None else _suspicious_usage(tree, SUSPICIOUS_FILE_CALLS, FILE_IO_MODULE_ROOTS)
        errors = [
            {"code": violation.code, "message": violation.message, "line": violation.line}
            for violation in result.violations
        ]
        errors.extend(import_violations)
        errors.extend(network_violations)
        errors.extend(file_violations)
        syntax_valid = not any(error["code"] == "syntax.error" for error in errors)
        uses_allowed_imports = not import_violations and not any(str(error["code"]).startswith("import") for error in errors)
        blocks_network_access = not network_violations
        blocks_file_write = not file_violations
        is_safe = result.ok and syntax_valid and uses_allowed_imports and blocks_network_access and blocks_file_write
        return CodeValidationOutcome(
            is_safe=is_safe,
            syntax_valid=syntax_valid,
            uses_allowed_imports=uses_allowed_imports,
            blocks_network_access=blocks_network_access,
            blocks_file_write=blocks_file_write,
            warnings_jsonb=[],
            errors_jsonb=errors,
        )


@dataclass(frozen=True, slots=True)
class SubprocessProcessIdentity:
    attempt_id: UUID
    worker_host: str
    worker_pid: int
    worker_pgid: int
    worker_started_at: datetime


ProcessIdentityRecorder = Callable[[SubprocessProcessIdentity], Awaitable[None]]
ReleaseAuthorizer = Callable[[SubprocessProcessIdentity], Awaitable[None]]


def _failed_execution_result(
    *,
    request: AICodeBacktestFlowRequest,
    generated: GeneratedCodeResult,
    execution_run_id: UUID,
    started_at: datetime,
    stderr: str,
) -> CodeExecutionResult:
    ended_at = datetime.now(UTC)
    return CodeExecutionResult(
        runtime_env=generated.target_runtime,
        status="failed",
        timeout_seconds=request.timeout_seconds,
        memory_limit_mb=request.memory_limit_mb,
        sandbox_id=f"subprocess:{execution_run_id}",
        latency_ms=round((ended_at - started_at).total_seconds() * 1000, 6),
        stdout="",
        stderr=stderr,
        output_artifacts_jsonb=None,
        started_at=started_at,
        ended_at=ended_at,
        backtest_result=None,
    )


def _timeout_execution_result(
    *,
    request: AICodeBacktestFlowRequest,
    generated: GeneratedCodeResult,
    execution_run_id: UUID,
    started_at: datetime,
    stdout: str,
    stderr: str,
) -> CodeExecutionResult:
    ended_at = datetime.now(UTC)
    return CodeExecutionResult(
        runtime_env=generated.target_runtime,
        status="timeout",
        timeout_seconds=request.timeout_seconds,
        memory_limit_mb=request.memory_limit_mb,
        sandbox_id=f"subprocess:{execution_run_id}",
        latency_ms=round((ended_at - started_at).total_seconds() * 1000, 6),
        stdout=stdout,
        stderr=f"{stderr}\nexecution timed out".strip(),
        output_artifacts_jsonb=None,
        started_at=started_at,
        ended_at=ended_at,
        backtest_result=None,
    )


async def _withhold_release_and_wait(process: subprocess.Popen[str]) -> None:
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()


class SandboxedBacktestExecutor:
    async def execute(
        self,
        request: AICodeBacktestFlowRequest,
        generated: GeneratedCodeResult,
        *,
        trace_id: UUID,
        execution_run_id: UUID,
        process_identity_recorder: ProcessIdentityRecorder | None = None,
        release_authorizer: ReleaseAuthorizer | None = None,
    ) -> CodeExecutionResult:
        from app.services.ai_backtest_subprocess_runner import _RELEASE_BYTE

        runner_module = "app.services.ai_backtest_subprocess_runner"
        repo_root = Path(__file__).resolve().parents[3]
        env = os.environ.copy()
        env["PYTHONPATH"] = _compose_pythonpath(repo_root, env.get("PYTHONPATH"))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        started_at = datetime.now(UTC)
        with tempfile.TemporaryDirectory(prefix="ai-backtest-") as temp_dir:
            temp_path = Path(temp_dir)
            request_path = temp_path / "request.json"
            generated_path = temp_path / "generated_code.py"
            output_path = temp_path / "result.json"
            request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
            generated_path.write_text(generated.generated_code, encoding="utf-8")
            release_path: Path | None = None
            if os.name == "nt":
                # Windows does not preserve a numeric CRT descriptor across a
                # subprocess boundary.  A private signal file in the same temporary
                # directory keeps the release fence explicit without weakening the
                # ownership gate.
                release_read_fd = None
                release_write_fd = None
                release_path = temp_path / "release.signal"
                release_argument = f"path:{release_path}"
            else:
                release_read_fd, release_write_fd = os.pipe()
                release_argument = f"fd:{release_read_fd}"
            command = [
                sys.executable,
                "-m",
                runner_module,
                str(request_path),
                str(generated_path),
                str(output_path),
                str(trace_id),
                release_argument,
            ]
            popen_options: dict[str, Any] = {
                "cwd": temp_dir,
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "start_new_session": True,
            }
            if os.name == "nt":
                # Windows does not support ``pass_fds``.  The release fence uses the
                # private signal file passed in the command instead.
                popen_options["close_fds"] = True
            else:
                popen_options["pass_fds"] = (release_read_fd,)
                popen_options["preexec_fn"] = _limit_subprocess_resources(
                    request.memory_limit_mb, request.timeout_seconds
                )
            try:
                process = subprocess.Popen(command, **popen_options)
            except Exception:
                _close_release_writer(release_write_fd)
                raise
            finally:
                if release_read_fd is not None:
                    os.close(release_read_fd)

            if process_identity_recorder is None:
                _close_release_writer(release_write_fd)
                await _withhold_release_and_wait(process)
                return _failed_execution_result(
                    request=request,
                    generated=generated,
                    execution_run_id=execution_run_id,
                    started_at=started_at,
                    stderr="subprocess ownership persistence was not configured; execution was not released",
                )

            try:
                identity = SubprocessProcessIdentity(
                    attempt_id=uuid4(),
                    worker_host=socket.gethostname(),
                    worker_pid=process.pid,
                    worker_pgid=_process_group_id(process),
                    worker_started_at=started_at,
                )
                await process_identity_recorder(identity)
            except Exception:  # noqa: BLE001 - child must never run without durable ownership
                _close_release_writer(release_write_fd)
                await _withhold_release_and_wait(process)
                return _failed_execution_result(
                    request=request,
                    generated=generated,
                    execution_run_id=execution_run_id,
                    started_at=started_at,
                    stderr="subprocess ownership persistence failed; execution was not released",
                )
            if release_authorizer is None:
                _close_release_writer(release_write_fd)
                await _withhold_release_and_wait(process)
                return _failed_execution_result(
                    request=request,
                    generated=generated,
                    execution_run_id=execution_run_id,
                    started_at=started_at,
                    stderr="subprocess release authorization was not configured; execution was not released",
                )
            try:
                await release_authorizer(identity)
            except Exception:  # noqa: BLE001 - child must never run without a durable release fence
                _close_release_writer(release_write_fd)
                await _withhold_release_and_wait(process)
                return _failed_execution_result(
                    request=request,
                    generated=generated,
                    execution_run_id=execution_run_id,
                    started_at=started_at,
                    stderr="subprocess release authorization failed; execution was not released",
                )

            try:
                if release_path is not None:
                    release_path.write_bytes(_RELEASE_BYTE)
                    release_written = len(_RELEASE_BYTE)
                else:
                    release_written = os.write(release_write_fd, _RELEASE_BYTE)
            except OSError:
                release_written = 0
            finally:
                _close_release_writer(release_write_fd)
            if release_written != len(_RELEASE_BYTE):
                await _withhold_release_and_wait(process)
                return _failed_execution_result(
                    request=request,
                    generated=generated,
                    execution_run_id=execution_run_id,
                    started_at=started_at,
                    stderr="subprocess release failed; execution was not released",
                )

            try:
                stdout, stderr = process.communicate(timeout=request.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                stdout, stderr = process.communicate()
                return _timeout_execution_result(
                    request=request,
                    generated=generated,
                    execution_run_id=execution_run_id,
                    started_at=started_at,
                    stdout=stdout or exc.stdout or "",
                    stderr=stderr or exc.stderr or "",
                )
            ended_at = datetime.now(UTC)
            stdout = stdout or ""
            stderr = stderr or ""
            sigxcpu = getattr(signal, "SIGXCPU", None)
            if sigxcpu is not None and process.returncode == -sigxcpu:
                return _timeout_execution_result(
                    request=request,
                    generated=generated,
                    execution_run_id=execution_run_id,
                    started_at=started_at,
                    stdout=stdout,
                    stderr=stderr,
                )
            if process.returncode != 0:
                return CodeExecutionResult(
                    runtime_env=generated.target_runtime,
                    status="failed",
                    timeout_seconds=request.timeout_seconds,
                    memory_limit_mb=request.memory_limit_mb,
                    sandbox_id=f"subprocess:{execution_run_id}",
                    latency_ms=round((ended_at - started_at).total_seconds() * 1000, 6),
                    stdout=stdout,
                    stderr=stderr or f"subprocess exited with code {process.returncode}",
                    output_artifacts_jsonb=None,
                    started_at=started_at,
                    ended_at=ended_at,
                    backtest_result=None,
                )
            if not output_path.exists():
                return CodeExecutionResult(
                    runtime_env=generated.target_runtime,
                    status="failed",
                    timeout_seconds=request.timeout_seconds,
                    memory_limit_mb=request.memory_limit_mb,
                    sandbox_id=f"subprocess:{execution_run_id}",
                    latency_ms=round((ended_at - started_at).total_seconds() * 1000, 6),
                    stdout=stdout,
                    stderr=stderr or "runner completed without producing result payload",
                    output_artifacts_jsonb=None,
                    started_at=started_at,
                    ended_at=ended_at,
                    backtest_result=None,
                )
            payload = CodeExecutionResult.model_validate_json(output_path.read_text(encoding="utf-8"))
            return payload.model_copy(
                update={
                    "timeout_seconds": request.timeout_seconds,
                    "memory_limit_mb": request.memory_limit_mb,
                    "sandbox_id": payload.sandbox_id or f"subprocess:{execution_run_id}",
                    "latency_ms": round((ended_at - started_at).total_seconds() * 1000, 6),
                    "stdout": _merge_output(payload.stdout, stdout),
                    "stderr": _merge_output(payload.stderr, stderr),
                    "started_at": payload.started_at or started_at,
                    "ended_at": payload.ended_at or ended_at,
                }
            )


InProcessBacktestExecutor = SandboxedBacktestExecutor


class DeterministicBacktestReportGenerator:
    async def build_report(
        self,
        request: AICodeBacktestFlowRequest,
        *,
        trace_id: UUID,
        run_id: UUID,
        execution: CodeExecutionResult,
    ) -> AIBacktestReportDraft:
        summary = execution.backtest_result.summary if execution.backtest_result else None
        if summary is None:
            return AIBacktestReportDraft(
                overall_rating="failed",
                summary="No backtest result was available for report generation.",
                report_jsonb={"trace_id": str(trace_id), "run_id": str(run_id), "status": execution.status},
                model_name=request.report_model_name,
            )
        return AIBacktestReportDraft(
            period_return=summary.period_return,
            cagr=summary.cagr,
            max_drawdown=summary.max_drawdown,
            sharpe_ratio=summary.sharpe_ratio,
            sortino_ratio=summary.sortino_ratio,
            calmar_ratio=summary.calmar_ratio,
            win_rate=summary.win_rate,
            profit_factor=summary.profit_factor,
            volatility=summary.volatility,
            benchmark_return=summary.benchmark_return,
            overall_rating="pass" if (summary.period_return or 0) >= 0 else "watch",
            summary=(
                f"AI generated backtest for strategy '{request.strategy_id or 'unknown_strategy'}' completed with "
                f"return {summary.period_return or 0:.4f} and sharpe {summary.sharpe_ratio or 0:.4f}."
            ),
            return_analysis="Generated code was validated and executed through the AI backtest flow.",
            risk_analysis=f"Max drawdown was {summary.max_drawdown or 0:.4f}.",
            trade_analysis=f"Trade count: {summary.trade_count or 0}, win rate: {summary.win_rate or 0:.4f}.",
            benchmark_analysis=f"Benchmark return: {summary.benchmark_return or 0:.4f}.",
            improvement_suggestions="Review generated assumptions and compare with live market adapters before production trading.",
            report_jsonb={
                "trace_id": str(trace_id),
                "run_id": str(run_id),
                "execution_status": execution.status,
                "strategy_id": request.strategy_id,
            },
            model_name=request.report_model_name,
        )


def _load_generation_modules():
    try:
        from ai_graph.graph import build_strategy_spec
        from ai_graph.llm.aoai import AOAIResponsesClient
        from ai_graph.llm.factory import create_llm_client
        from ai_graph.llm.mock import MockLLMClient
        from ai_graph.llm.prompts import build_backtest_code_json_request
        from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
        from ai_graph.schemas import StrategySpec
    except ModuleNotFoundError as exc:
        raise _pythonpath_error(exc) from exc
    return (
        build_strategy_spec,
        build_backtest_code_json_request,
        create_llm_client,
        generate_loop3_candidates,
        Loop3Request,
        StrategySpec,
        AOAIResponsesClient,
        MockLLMClient,
    )


def _load_validate_backtest_code():
    try:
        from ai_graph.security.ast_validator import validate_backtest_code
    except ModuleNotFoundError as exc:
        raise _pythonpath_error(exc) from exc
    return validate_backtest_code


def _load_audit_modules():
    try:
        from ai_graph.audit import RecordingAuditSink, bind_audit_context, create_audit_correlation
    except ModuleNotFoundError as exc:
        raise _pythonpath_error(exc) from exc
    return RecordingAuditSink, bind_audit_context, create_audit_correlation


def _build_generation_model_call(
    request: AICodeBacktestFlowRequest,
    *,
    prompt_request: Any,
    strategy_id: str | None,
    provider: str | None,
    model_name: str | None,
    fallback_error: tuple[str, str] | None,
    captured_model: Any | None,
    captured_prompt: Any | None,
    captured_error: Any | None,
) -> ModelCallLogBundle:
    model_failed = captured_model is not None and captured_model.status == "failed"
    failed = fallback_error is not None or model_failed
    error_type = None
    error_message = None
    if model_failed:
        error_type = getattr(captured_error, "error_type", None) or "model_call_failed"
        error_message = captured_model.error_message or "Model call failed before fallback execution."
    elif fallback_error is not None:
        error_type, error_message = fallback_error

    return ModelCallLogBundle(
        task_type=getattr(captured_model, "task_type", None) or "backtest_code_generation",
        provider=getattr(captured_model, "provider", None) or provider,
        provider_request_id=getattr(captured_model, "provider_request_id", None),
        model_name=getattr(captured_model, "model_name", None) or model_name,
        temperature=getattr(captured_model, "temperature", None),
        response_schema_name=(
            getattr(captured_model, "response_schema_name", None) or prompt_request.schema_name
        ),
        web_search_used=bool(getattr(captured_model, "web_search_used", False)),
        prompt_tokens=getattr(captured_model, "prompt_tokens", None),
        completion_tokens=getattr(captured_model, "completion_tokens", None),
        total_tokens=getattr(captured_model, "total_tokens", None),
        latency_ms=getattr(captured_model, "latency_ms", None),
        retry_count=getattr(captured_model, "retry_count", 0),
        status="failed" if failed else "succeeded",
        error_type=error_type,
        error_message=error_message,
        prompt_log=PromptLogBundle(
            prompt_template_name=(
                getattr(captured_prompt, "prompt_template_name", None)
                or getattr(prompt_request, "prompt_template_name", None)
                or prompt_request.schema_name
            ),
            system_prompt=getattr(captured_prompt, "system_prompt", None) or prompt_request.system_prompt,
            user_prompt=getattr(captured_prompt, "user_prompt", None) or prompt_request.user_prompt,
            assistant_response=getattr(captured_prompt, "assistant_response", None),
            variables_jsonb=(
                dict(captured_prompt.variables_jsonb)
                if captured_prompt is not None
                else dict(getattr(prompt_request, "variables_jsonb", {}) or {"strategy_id": strategy_id, "variant": "A"})
            ),
            prompt_version=(
                getattr(captured_prompt, "prompt_version", None)
                or getattr(prompt_request, "prompt_version", None)
                or prompt_request.schema_name
            ),
            contains_pii=_contains_pii_text(request.natural_language_prompt),
            masked=False,
        )
    )


def _observed_provider_and_model(
    client: Any,
    *,
    aoai_client_type: type,
    mock_client_type: type,
) -> tuple[str | None, str | None]:
    if isinstance(client, aoai_client_type):
        model = getattr(client, "model", None)
        return "aoai", model if isinstance(model, str) and model else None
    if isinstance(client, mock_client_type):
        return "mock", None
    return None, None


def _fallback_error(result: Any) -> tuple[str, str] | None:
    fallback_reasons = getattr(result, "fallback_reasons", None)
    if not isinstance(fallback_reasons, list):
        return None
    for reason in fallback_reasons:
        if reason == "all generated candidates failed AST validation":
            return (
                "LLMOutputValidationError",
                "LLM generated candidates failed validation; deterministic fallback code was executed.",
            )
        if isinstance(reason, str) and reason.startswith("ValidationError:"):
            return (
                "LLMResponseSchemaError",
                "Model response did not match the required schema; deterministic fallback code was executed.",
            )
        if isinstance(reason, str) and reason.startswith("LLMClientError:"):
            return (
                "LLMClientError",
                "Model request failed; deterministic fallback code was executed.",
            )
    return None


def _generation_exception_error(exc: Exception) -> tuple[str, str] | None:
    if isinstance(exc, ValueError) and str(exc) == "safe fallback candidates failed AST validation":
        return (
            "LLMOutputValidationError",
            "LLM-generated and deterministic fallback candidates failed validation.",
        )
    return None

def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _contains_pii_text(value: str) -> bool:
    email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    phone_pattern = r"\b\d{2,4}[- ]?\d{3,4}[- ]?\d{4}\b"
    return bool(re.search(email_pattern, value) or re.search(phone_pattern, value))


def _runtime_import_violations(tree: ast.AST) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".", 1)[0]
                if module not in RUNTIME_ALLOWED_IMPORTS:
                    violations.append({
                        "code": "runtime.import.blocked",
                        "message": f"runtime import '{alias.name}' is not allowed",
                        "line": getattr(node, "lineno", 0),
                    })
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".", 1)[0]
            if node.level or module not in RUNTIME_ALLOWED_IMPORTS:
                violations.append({
                    "code": "runtime.import_from.blocked",
                    "message": f"runtime import '{node.module or ''}' is not allowed",
                    "line": getattr(node, "lineno", 0),
                })
    return violations


def _suspicious_usage(tree: ast.AST, suspicious_calls: set[str] | frozenset[str], suspicious_roots: set[str] | frozenset[str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _call_path(node.func)
            root_name = call_name.split(".", 1)[0]
            if call_name in suspicious_calls or root_name in suspicious_roots:
                violations.append({
                    "code": "sandbox.call.blocked",
                    "message": f"call '{call_name}' is not allowed in generated backtest code",
                    "line": getattr(node, "lineno", 0),
                })
        elif isinstance(node, ast.Attribute):
            root_name = _attribute_root(node)
            if root_name in suspicious_roots:
                violations.append({
                    "code": "sandbox.attribute.blocked",
                    "message": f"attribute access on '{root_name}' is not allowed in generated backtest code",
                    "line": getattr(node, "lineno", 0),
                })
    return violations


def _call_path(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cursor: ast.AST | None = node
        while isinstance(cursor, ast.Attribute):
            parts.append(cursor.attr)
            cursor = cursor.value
        if isinstance(cursor, ast.Name):
            parts.append(cursor.id)
        return ".".join(reversed(parts))
    return "<dynamic>"


def _attribute_root(node: ast.Attribute) -> str:
    cursor: ast.AST = node
    while isinstance(cursor, ast.Attribute):
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        return cursor.id
    return "<dynamic>"


def _compose_pythonpath(repo_root: Path, existing: str | None) -> str:
    entries = [str(repo_root / "backend"), str(repo_root / "ai"), str(repo_root / "backtest_module")]
    if existing:
        entries.append(existing)
    return os.pathsep.join(entries)


def _limit_subprocess_resources(memory_limit_mb: int, timeout_seconds: int):
    if os.name == "nt":
        return None

    def _apply_limits() -> None:
        try:
            import resource
        except Exception:
            return

        memory_bytes = memory_limit_mb * 1024 * 1024
        for limit_name in ("RLIMIT_AS", "RLIMIT_DATA"):
            if hasattr(resource, limit_name):
                try:
                    resource.setrlimit(getattr(resource, limit_name), (memory_bytes, memory_bytes))
                except (OSError, ValueError):
                    continue
        if hasattr(resource, "RLIMIT_CPU"):
            cpu_seconds = max(1, timeout_seconds)
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
            except (OSError, ValueError):
                pass

    return _apply_limits


def _close_release_writer(release_write_fd: int | None) -> None:
    if release_write_fd is not None:
        os.close(release_write_fd)


def _process_group_id(process: subprocess.Popen[str]) -> int:
    """Return a durable process-group identity on POSIX and Windows."""

    getpgid = getattr(os, "getpgid", None)
    if getpgid is not None:
        try:
            return int(getpgid(process.pid))
        except OSError:
            pass
    return int(process.pid)


def _pythonpath_error(exc: ModuleNotFoundError) -> AppError:
    return AppError(
        status_code=503,
        component="ai_backtest",
        code="pythonpath_not_configured",
        message="AI backtest runtime dependencies are unavailable; start the backend with PYTHONPATH including backend, ai, and backtest_module or install those packages.",
        details={"missing_module": str(exc)},
    )


def _merge_output(primary: str | None, secondary: str | None) -> str | None:
    parts = [part for part in (primary, secondary) if part]
    if not parts:
        return None
    merged = "\n".join(parts)
    return merged[:200_000]
