from __future__ import annotations

import ast
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


ALLOWED_MODULES = frozenset(
    {
        "datetime",
        "math",
        "statistics",
    }
)
BLOCKED_MODULES = frozenset({"subprocess", "os", "sys", "importlib"})
BLOCKED_CALLS = frozenset({"eval", "exec", "__import__", "open", "getattr", "setattr"})
ALLOWED_ENTRYPOINTS = frozenset({"build_signals"})
MAX_SOURCE_CHARS = 20_000
MAX_AST_NODES = 1_500
MAX_AST_DEPTH = 40
MAX_LOOP_NODES = 8
MAX_NESTED_LOOP_DEPTH = 2
MAX_LITERAL_RANGE = 10_000
ROLLING_AGGREGATORS = frozenset({"sum", "max", "min"})


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
        self._loop_depth = 0
        self._loop_count = 0

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
        if (
            self._loop_depth
            and call_name in ROLLING_AGGREGATORS
            and any(_contains_slice(argument) for argument in node.args)
        ):
            self.reject(
                node,
                "performance.rolling_slice",
                f"call '{call_name}' over a slice inside a loop is not allowed",
            )
        if call_name == "range" and node.args:
            literal_bounds = [
                argument.value
                for argument in node.args
                if isinstance(argument, ast.Constant)
                and isinstance(argument.value, int)
            ]
            if literal_bounds and max(abs(value) for value in literal_bounds) > MAX_LITERAL_RANGE:
                self.reject(
                    node,
                    "performance.range_limit",
                    f"literal range exceeds {MAX_LITERAL_RANGE}",
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        root_name = attribute_root(node)
        if node.attr.startswith("_"):
            self.reject(
                node,
                "attribute.private",
                f"private attribute '{node.attr}' is not allowed",
            )
        if root_name in BLOCKED_MODULES:
            self.reject(node, "attribute.blocked", f"attribute access on '{root_name}' is blocked")
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> Any:
        self.reject(node, "performance.while_loop", "while loops are not allowed")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> Any:
        self._loop_count += 1
        if self._loop_count > MAX_LOOP_NODES:
            self.reject(
                node,
                "performance.loop_count",
                f"loop count exceeds {MAX_LOOP_NODES}",
            )
        if self._loop_depth >= MAX_NESTED_LOOP_DEPTH:
            self.reject(
                node,
                "performance.nested_loop",
                f"nested loop depth exceeds {MAX_NESTED_LOOP_DEPTH}",
            )
        self.visit(node.target)
        self.visit(node.iter)
        self._loop_depth += 1
        for statement in node.body:
            self.visit(statement)
        self._loop_depth -= 1
        for statement in node.orelse:
            self.visit(statement)

    def visit_ListComp(self, node: ast.ListComp) -> Any:
        self._visit_comprehension(node, node.generators)

    def visit_SetComp(self, node: ast.SetComp) -> Any:
        self._visit_comprehension(node, node.generators)

    def visit_DictComp(self, node: ast.DictComp) -> Any:
        self._visit_comprehension(node, node.generators)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> Any:
        self._visit_comprehension(node, node.generators)

    def _visit_comprehension(
        self,
        node: ast.AST,
        generators: list[ast.comprehension],
    ) -> None:
        self._loop_count += len(generators)
        if self._loop_count > MAX_LOOP_NODES:
            self.reject(
                node,
                "performance.loop_count",
                f"loop count exceeds {MAX_LOOP_NODES}",
            )
        if self._loop_depth + len(generators) > MAX_NESTED_LOOP_DEPTH:
            self.reject(
                node,
                "performance.nested_loop",
                f"nested loop depth exceeds {MAX_NESTED_LOOP_DEPTH}",
            )
        self.generic_visit(node)


def validate_backtest_code(
    source: str, *, required_functions: Iterable[str] = ("build_signals",)
) -> ASTValidationResult:
    violations: list[ASTViolation] = []
    if len(source) > MAX_SOURCE_CHARS:
        violations.append(
            ASTViolation(
                line=0,
                column=0,
                code="performance.source_size",
                message=f"source exceeds {MAX_SOURCE_CHARS} characters",
            )
        )
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

    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES:
        violations.append(
            ASTViolation(
                line=0,
                column=0,
                code="performance.ast_nodes",
                message=f"AST node count exceeds {MAX_AST_NODES}",
            )
        )
    if _ast_depth(tree) > MAX_AST_DEPTH:
        violations.append(
            ASTViolation(
                line=0,
                column=0,
                code="performance.ast_depth",
                message=f"AST depth exceeds {MAX_AST_DEPTH}",
            )
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


def _contains_slice(node: ast.AST) -> bool:
    return any(
        isinstance(item, ast.Subscript) and isinstance(item.slice, ast.Slice)
        for item in ast.walk(node)
    )


def _ast_depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    if not children:
        return 1
    return 1 + max(_ast_depth(child) for child in children)
