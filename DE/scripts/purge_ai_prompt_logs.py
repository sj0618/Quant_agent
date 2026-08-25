"""Delete AI prompt/response content older than the fixed 90-day policy."""

from __future__ import annotations

from datetime import datetime
import os
import sys
from typing import Any, Mapping

try:
    import psycopg
except ImportError:  # pragma: no cover - production dependency, covered by main failure test.
    psycopg = None


RETENTION_DAYS = 90
BATCH_SIZE = 1_000
CONNECT_TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MS = 30_000

CUTOFF_SQL = "SELECT now() - INTERVAL '90 days'"
DELETE_BATCH_SQL = """
WITH expired AS (
    SELECT prompt_log_id
    FROM app.ai_prompt_log
    WHERE created_at < %s
    ORDER BY created_at, prompt_log_id
    LIMIT %s
    FOR UPDATE SKIP LOCKED
)
DELETE FROM app.ai_prompt_log AS prompt
USING expired
WHERE prompt.prompt_log_id = expired.prompt_log_id
RETURNING prompt.prompt_log_id
"""


def resolve_dsn(environ: Mapping[str, str] = os.environ) -> str:
    for name in ("AI_DATABASE_DSN", "QUANT_DB_DSN", "DATABASE_URL"):
        if dsn := environ.get(name):
            for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
                if dsn.startswith(prefix):
                    return "postgresql://" + dsn.removeprefix(prefix)
            return dsn
    raise RuntimeError("AI_DATABASE_DSN, QUANT_DB_DSN, or DATABASE_URL is required")


def purge_expired_prompt_logs(
    conn: Any,
    *,
    batch_size: int = BATCH_SIZE,
    cutoff: datetime | None = None,
) -> int:
    """Delete all expired rows using one cutoff and batch commits.

    Production callers omit ``cutoff`` so PostgreSQL supplies the timestamp once.
    The optional value exists only to make retention-boundary tests deterministic.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    try:
        if cutoff is None:
            with conn.cursor() as cursor:
                cursor.execute(CUTOFF_SQL)
                cutoff = cursor.fetchone()[0]

        total_deleted = 0
        while True:
            with conn.cursor() as cursor:
                cursor.execute(DELETE_BATCH_SQL, (cutoff, batch_size))
                deleted = len(cursor.fetchall())
            conn.commit()
            total_deleted += deleted
            if deleted == 0:
                return total_deleted
    except Exception:
        conn.rollback()
        raise


def main() -> int:
    conn = None
    try:
        if psycopg is None:
            raise RuntimeError("psycopg[binary] is required")
        conn = psycopg.connect(
            resolve_dsn(),
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
        )
        deleted = purge_expired_prompt_logs(conn)
        print(f"deleted {deleted} expired AI prompt log rows")
        return 0
    except Exception as exc:
        print(f"AI prompt retention failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
