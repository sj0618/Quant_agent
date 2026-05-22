"""PostgreSQL execution helpers for the data pipeline.

The preferred runtime path is psycopg with a DSN/password supplied by the
process environment. For local Docker-only verification, a constrained
``docker exec ... psql`` executor is available so tests can validate a running
container without reading the repository ``.env`` file.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
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


def make_executor(config: DatabaseConfig | None = None) -> SqlExecutor:
    db_config = config or DatabaseConfig.from_env()
    if db_config.execution_mode == "docker":
        return DockerPsqlExecutor(db_config)
    if db_config.execution_mode == "psycopg":
        return PsycopgExecutor(db_config)
    raise ValueError(f"Unsupported QUANT_DB_EXECUTION_MODE: {db_config.execution_mode}")


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
