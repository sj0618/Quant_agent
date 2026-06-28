"""PostgreSQL execution helpers for the data pipeline.

The preferred runtime path is psycopg with a DSN/password supplied by the
process environment. For local Docker-only verification, a constrained
``docker exec ... psql`` executor is available so tests can validate a running
container without reading the repository ``.env`` file.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import subprocess
from typing import Any, Protocol

from quant_agent.data.config import DatabaseConfig


class SqlExecutionError(RuntimeError):
    """Raised when SQL execution fails."""


class SqlExecutor(Protocol):
    def execute_script(self, sql: str) -> None:
        """Execute a SQL script, raising on failure."""

    def fetch_json(self, sql: str) -> list[dict[str, Any]]:
        """Run a SELECT statement and return rows as dictionaries."""


@dataclass(frozen=True)
class PsycopgExecutor:
    config: DatabaseConfig

    def execute_script(self, sql: str) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on runtime image
            raise SqlExecutionError("psycopg is required for QUANT_DB_EXECUTION_MODE=psycopg.") from exc

        with psycopg.connect(self.config.psycopg_conninfo()) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()

    def fetch_json(self, sql: str) -> list[dict[str, Any]]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on runtime image
            raise SqlExecutionError("psycopg is required for QUANT_DB_EXECUTION_MODE=psycopg.") from exc

        with psycopg.connect(self.config.psycopg_conninfo(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]


@dataclass(frozen=True)
class PsycopgScriptClient:
    """psycopg-backed helper for script-style COPY / temp-table workflows."""

    config: DatabaseConfig

    def connect(self):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on runtime image
            raise SqlExecutionError("psycopg is required for direct PostgreSQL script execution.") from exc

        try:
            return psycopg.connect(self.config.psycopg_conninfo())
        except Exception as exc:  # pragma: no cover - surfaced in integration tests
            raise SqlExecutionError(f"PostgreSQL connection failed: {exc}") from exc

    def execute(self, sql: str) -> str:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        return ""

    def fetch_csv_text(self, query: str) -> str:
        copy_sql = f"COPY ({query.rstrip().rstrip(';')}) TO STDOUT WITH (FORMAT csv, HEADER true);"
        chunks: list[bytes] = []
        with self.connect() as conn:
            with conn.cursor() as cur:
                with cur.copy(copy_sql) as copy:
                    while True:
                        chunk = copy.read()
                        if not chunk:
                            break
                        chunks.append(bytes(chunk))
        return b"".join(chunks).decode("utf-8")

    def execute_copy_csv(self, pre_sql: str, copy_sql: str, csv_text: str, post_sql: str) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                if pre_sql.strip():
                    cur.execute(pre_sql)
                with cur.copy(copy_sql) as copy:
                    copy.write(csv_text)
                if post_sql.strip():
                    cur.execute(post_sql)


@dataclass(frozen=True)
class DockerPsqlExecutor:
    config: DatabaseConfig

    def execute_script(self, sql: str) -> None:
        completed = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                self.config.docker_container,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                self.config.user,
                "-d",
                self.config.database,
            ],
            input=sql,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SqlExecutionError(completed.stderr.strip() or completed.stdout.strip())

    def fetch_json(self, sql: str) -> list[dict[str, Any]]:
        wrapped_sql = (
            "COPY (SELECT COALESCE(json_agg(row_to_json(q)), '[]'::json) "
            f"FROM ({sql.rstrip().rstrip(';')}) AS q) TO STDOUT;"
        )
        completed = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                self.config.docker_container,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-qAt",
                "-U",
                self.config.user,
                "-d",
                self.config.database,
            ],
            input=wrapped_sql,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SqlExecutionError(completed.stderr.strip() or completed.stdout.strip())
        output = completed.stdout.strip() or "[]"
        loaded = json.loads(output)
        if not isinstance(loaded, list):
            raise SqlExecutionError("Expected JSON array from psql query wrapper.")
        return [dict(row) for row in loaded]


def resolve_execution_mode(config: DatabaseConfig, requested_mode: str | None = None) -> str:
    mode = (requested_mode or config.execution_mode or "").lower()
    if mode not in {"docker", "psycopg"}:
        raise ValueError(f"Unsupported QUANT_DB_EXECUTION_MODE: {mode}")
    if mode == "docker":
        return "docker"
    if config.dsn or config.password:
        return "psycopg"
    if requested_mode is None:
        return "docker"
    raise ValueError(
        "QUANT_DB_EXECUTION_MODE=psycopg requires QUANT_DB_DSN/DATABASE_URL or QUANT_DB_PASSWORD."
    )


def make_executor(config: DatabaseConfig | None = None) -> SqlExecutor:
    db_config = config or DatabaseConfig.from_env()
    mode = resolve_execution_mode(db_config, os.getenv("QUANT_DB_EXECUTION_MODE"))
    if mode == "docker":
        return DockerPsqlExecutor(db_config)
    if mode == "psycopg":
        return PsycopgExecutor(db_config)
    raise ValueError(f"Unsupported QUANT_DB_EXECUTION_MODE: {mode}")


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def jsonb_literal(value: Any) -> str:
    return f"{sql_literal(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))}::jsonb"
