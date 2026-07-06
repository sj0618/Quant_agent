from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
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


class AOAICodeGenerator:
    async def generate(self, request: AICodeBacktestFlowRequest, *, trace_id: UUID) -> GeneratedCodeResult:
        build_strategy_spec, create_llm_client, generate_loop3_candidates, Loop3Request, StrategySpec, AI_AOAI_MODEL_ENV = _load_generation_modules()
        strategy = (
            StrategySpec.model_validate(request.parsed_strategy_jsonb)
            if request.parsed_strategy_jsonb
            else build_strategy_spec(request.natural_language_prompt, variant="A", retrieval={"hits": []})
        )
        result = generate_loop3_candidates(
            Loop3Request(strategy=strategy, variant="A", trace_id=str(trace_id)),
            llm_client=create_llm_client(role="BACKTEST_CODE"),
        )
        selected = next((candidate for candidate in result.candidates if candidate.validation_ok), result.selected_candidate)
        model_name = os.environ.get("AI_LLM_BACKTEST_CODE_MODEL") or os.environ.get(AI_AOAI_MODEL_ENV)
        return GeneratedCodeResult(
            target_runtime=request.target_runtime,
            code_purpose=request.code_purpose,
            generated_code=selected.code,
            model_name=model_name,
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


class SandboxedBacktestExecutor:
    async def execute(
        self,
        request: AICodeBacktestFlowRequest,
        generated: GeneratedCodeResult,
        *,
        trace_id: UUID,
        execution_run_id: UUID,
    ) -> CodeExecutionResult:
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
            command = [
                sys.executable,
                "-m",
                runner_module,
                str(request_path),
                str(generated_path),
                str(output_path),
                str(trace_id),
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=temp_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=request.timeout_seconds,
                    preexec_fn=_limit_subprocess_resources(request.memory_limit_mb, request.timeout_seconds),
                )
            except subprocess.TimeoutExpired as exc:
                ended_at = datetime.now(UTC)
                return CodeExecutionResult(
                    runtime_env=generated.target_runtime,
                    status="timeout",
                    timeout_seconds=request.timeout_seconds,
                    memory_limit_mb=request.memory_limit_mb,
                    sandbox_id=f"subprocess:{execution_run_id}",
                    latency_ms=round((ended_at - started_at).total_seconds() * 1000, 6),
                    stdout=exc.stdout,
                    stderr=(exc.stderr or "") + "\nexecution timed out",
                    output_artifacts_jsonb=None,
                    started_at=started_at,
                    ended_at=ended_at,
                    backtest_result=None,
                )
            ended_at = datetime.now(UTC)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            if completed.returncode != 0:
                return CodeExecutionResult(
                    runtime_env=generated.target_runtime,
                    status="failed",
                    timeout_seconds=request.timeout_seconds,
                    memory_limit_mb=request.memory_limit_mb,
                    sandbox_id=f"subprocess:{execution_run_id}",
                    latency_ms=round((ended_at - started_at).total_seconds() * 1000, 6),
                    stdout=stdout,
                    stderr=stderr or f"subprocess exited with code {completed.returncode}",
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
                f"AI generated backtest for '{request.natural_language_prompt[:80]}' completed with "
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
        from ai_graph.llm.factory import AI_AOAI_MODEL_ENV, create_llm_client
        from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
        from ai_graph.schemas import StrategySpec
    except ModuleNotFoundError as exc:
        raise _pythonpath_error(exc) from exc
    return build_strategy_spec, create_llm_client, generate_loop3_candidates, Loop3Request, StrategySpec, AI_AOAI_MODEL_ENV


def _load_validate_backtest_code():
    try:
        from ai_graph.security.ast_validator import validate_backtest_code
    except ModuleNotFoundError as exc:
        raise _pythonpath_error(exc) from exc
    return validate_backtest_code


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
