"""AST 기반 백테스트 코드 검증기.

LLM이 생성한 코드는 실제 실행 전에 이 모듈의 allowlist 검사를 통과해야 한다.
검사는 보수적으로 실패하도록 설계되어 있으며, 네트워크/파일/프로세스 접근과
위험한 내장 함수 호출을 금지한다.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


ALLOWED_IMPORTS = frozenset({"math", "statistics"})
BLOCKED_CALLS = frozenset(
    {
        "__import__",
        "compile",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
)
BLOCKED_ATTRIBUTE_ROOTS = frozenset(
    {
        "os",
        "pathlib",
        "requests",
        "socket",
        "subprocess",
        "sys",
    }
)
ALLOWED_TOP_LEVEL_FUNCTIONS = frozenset({"build_signals"})


class ASTViolation(BaseModel):
    """검증 실패 사유."""

    model_config = ConfigDict(frozen=True)

    line: int = Field(ge=0)
    column: int = Field(ge=0)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ASTValidationResult(BaseModel):
    """AST 검증 결과."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    violations: tuple[ASTViolation, ...] = ()

    def raise_for_violations(self) -> None:
        if not self.ok:
            details = "; ".join(v.message for v in self.violations)
            raise ValueError(f"unsafe backtest code: {details}")


class _BacktestASTVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ASTViolation] = []
        self._function_depth = 0

    def _reject(self, node: ast.AST, code: str, message: str) -> None:
        self.violations.append(
            ASTViolation(
                line=getattr(node, "lineno", 0),
                column=getattr(node, "col_offset", 0),
                code=code,
                message=message,
            )
        )

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            root_name = alias.name.split(".", 1)[0]
            if root_name not in ALLOWED_IMPORTS:
                self._reject(node, "import.blocked", f"import '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        root_name = (node.module or "").split(".", 1)[0]
        if node.level or root_name not in ALLOWED_IMPORTS:
            self._reject(node, "import_from.blocked", f"from import '{node.module}' is not allowed")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        if self._function_depth == 0 and node.name not in ALLOWED_TOP_LEVEL_FUNCTIONS:
            self._reject(
                node,
                "function.name",
                f"top-level function '{node.name}' is not an allowed backtest entrypoint",
            )
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._reject(node, "async.blocked", "async functions are not allowed in backtest code")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self._reject(node, "class.blocked", "classes are not allowed in backtest code")
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> Any:
        self._reject(node, "with.blocked", "with statements are not allowed in backtest code")
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> Any:
        self._reject(node, "async_with.blocked", "async with statements are not allowed")
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> Any:
        self._reject(node, "global.blocked", "global statements are not allowed")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> Any:
        self._reject(node, "nonlocal.blocked", "nonlocal statements are not allowed")

    def visit_Call(self, node: ast.Call) -> Any:
        call_name = _call_name(node.func)
        if call_name in BLOCKED_CALLS:
            self._reject(node, "call.blocked", f"call '{call_name}' is not allowed")
        if "." in call_name and call_name.split(".", 1)[0] in BLOCKED_ATTRIBUTE_ROOTS:
            self._reject(node, "attribute_call.blocked", f"call '{call_name}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        root_name = _attribute_root_name(node)
        if root_name in BLOCKED_ATTRIBUTE_ROOTS:
            self._reject(node, "attribute.blocked", f"attribute access on '{root_name}' is not allowed")
        self.generic_visit(node)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        root = _attribute_root_name(node)
        parts: list[str] = []
        cursor: ast.AST | None = node
        while isinstance(cursor, ast.Attribute):
            parts.append(cursor.attr)
            cursor = cursor.value
        if isinstance(cursor, ast.Name):
            parts.append(cursor.id)
        return ".".join(reversed(parts)) if parts else root
    return "<dynamic>"


def _attribute_root_name(node: ast.Attribute) -> str:
    cursor: ast.AST = node
    while isinstance(cursor, ast.Attribute):
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        return cursor.id
    return "<dynamic>"


def validate_backtest_code(source: str, *, required_functions: Iterable[str] = ("build_signals",)) -> ASTValidationResult:
    """백테스트 코드를 파싱하고 안전 규칙 위반 목록을 반환한다."""

    violations: list[ASTViolation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        violations.append(
            ASTViolation(
                line=exc.lineno or 0,
                column=exc.offset or 0,
                code="syntax.error",
                message=exc.msg,
            )
        )
        return ASTValidationResult(ok=False, violations=tuple(violations))

    visitor = _BacktestASTVisitor()
    visitor.visit(tree)
    violations.extend(visitor.violations)

    function_names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    for function_name in required_functions:
        if function_name not in function_names:
            violations.append(
                ASTViolation(
                    line=0,
                    column=0,
                    code="function.missing",
                    message=f"required function '{function_name}' is missing",
                )
            )

    return ASTValidationResult(ok=not violations, violations=tuple(violations))
