from __future__ import annotations

import ast
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


ALLOWED_MODULES = frozenset(
    {
        "pandas",
        "numpy",
        "backtrader",
        "datetime",
        "math",
        "talib",
        "scipy.stats",
    }
)
BLOCKED_MODULES = frozenset({"subprocess", "os", "sys", "importlib"})
BLOCKED_CALLS = frozenset({"eval", "exec", "__import__", "open", "getattr", "setattr"})
ALLOWED_ENTRYPOINTS = frozenset({"build_signals"})


class ASTViolation(BaseModel):
    model_config = ConfigDict(frozen=True)

    line: int = Field(ge=0)
    column: int = Field(ge=0)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ASTValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    violations: tuple[ASTViolation, ...] = ()

    def raise_for_violations(self) -> None:
        if not self.ok:
            joined = "; ".join(violation.message for violation in self.violations)
            raise ValueError(f"unsafe generated code: {joined}")


class BacktestASTVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[ASTViolation] = []
        self._function_depth = 0

    def reject(self, node: ast.AST, code: str, message: str) -> None:
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
            module_name = alias.name
            root_name = module_name.split(".", 1)[0]
            if root_name in BLOCKED_MODULES or module_name not in ALLOWED_MODULES:
                self.reject(node, "import.blocked", f"import '{module_name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        module_name = node.module or ""
        root_name = module_name.split(".", 1)[0]
        if node.level or root_name in BLOCKED_MODULES or module_name not in ALLOWED_MODULES:
            self.reject(node, "import_from.blocked", f"from import '{module_name}' is not allowed")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        if self._function_depth == 0 and node.name not in ALLOWED_ENTRYPOINTS:
            self.reject(
                node,
                "function.name",
                f"top-level function '{node.name}' is not an allowed entrypoint",
            )
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.reject(node, "async.blocked", "async functions are not allowed")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.reject(node, "class.blocked", "classes are not allowed")
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> Any:
        self.reject(node, "with.blocked", "with statements are not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        call_name = call_path(node.func)
        if call_name in BLOCKED_CALLS:
            self.reject(node, "call.blocked", f"call '{call_name}' is not allowed")
        root_name = call_name.split(".", 1)[0]
        if root_name in BLOCKED_MODULES:
            self.reject(node, "call.module_blocked", f"call '{call_name}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        root_name = attribute_root(node)
        if root_name in BLOCKED_MODULES:
            self.reject(node, "attribute.blocked", f"attribute access on '{root_name}' is blocked")
        self.generic_visit(node)


def validate_backtest_code(
    source: str, *, required_functions: Iterable[str] = ("build_signals",)
) -> ASTValidationResult:
    violations: list[ASTViolation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ASTValidationResult(
            ok=False,
            violations=(
                ASTViolation(
                    line=exc.lineno or 0,
                    column=exc.offset or 0,
                    code="syntax.error",
                    message=exc.msg,
                ),
            ),
        )

    visitor = BacktestASTVisitor()
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


def call_path(node: ast.AST) -> str:
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


def attribute_root(node: ast.Attribute) -> str:
    cursor: ast.AST = node
    while isinstance(cursor, ast.Attribute):
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        return cursor.id
    return "<dynamic>"
