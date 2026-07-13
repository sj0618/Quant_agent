from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executions.append((sql, params))
        if sql == self.conn.module.CUTOFF_SQL:
            self.conn.cutoff_queries += 1
            self.result = [(self.conn.cutoff,)]
            return
        if self.conn.fail_batch:
            raise RuntimeError("injected batch failure")
        if self.conn.rows is not None:
            cutoff, batch_size = params
            expired = sorted(
                (row for row in self.conn.rows if row[1] < cutoff),
                key=lambda row: (row[1], row[0]),
            )[:batch_size]
            expired_ids = {row[0] for row in expired}
            self.conn.rows = [row for row in self.conn.rows if row[0] not in expired_ids]
            self.result = [(row[0],) for row in expired]
            return
        size = self.conn.batch_sizes.pop(0) if self.conn.batch_sizes else 0
        self.result = [(index,) for index in range(size)]

    def fetchone(self):
        return self.result[0]

    def fetchall(self):
        return self.result


class FakeConnection:
    def __init__(self, module, batch_sizes=(), *, fail_batch=False, rows=None):
        self.module = module
        self.batch_sizes = list(batch_sizes)
        self.fail_batch = fail_batch
        self.rows = rows
        self.cutoff = datetime(2026, 4, 14, tzinfo=timezone.utc)
        self.cutoff_queries = 0
        self.executions = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


class AiPromptRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_script()

    def test_policy_and_sql_boundary_are_fixed(self):
        self.assertEqual(self.module.RETENTION_DAYS, 90)
        self.assertEqual(self.module.BATCH_SIZE, 1_000)
        self.assertIn("now() - INTERVAL '90 days'", self.module.CUTOFF_SQL)
        self.assertIn("created_at < %s", self.module.DELETE_BATCH_SQL)
        self.assertIn("ORDER BY created_at, prompt_log_id", self.module.DELETE_BATCH_SQL)
        self.assertIn("FOR UPDATE SKIP LOCKED", self.module.DELETE_BATCH_SQL)
        self.assertIn("DELETE FROM app.ai_prompt_log", self.module.DELETE_BATCH_SQL)
        self.assertNotIn("ai_model_call_log", self.module.DELETE_BATCH_SQL)
        self.assertNotIn("ai_trace", self.module.DELETE_BATCH_SQL)

    def test_2501_rows_are_deleted_in_committed_batches_using_one_cutoff(self):
        conn = FakeConnection(self.module, (1_000, 1_000, 501, 0))

        deleted = self.module.purge_expired_prompt_logs(conn)

        self.assertEqual(deleted, 2_501)
        self.assertEqual(conn.cutoff_queries, 1)
        self.assertEqual(conn.commits, 4)
        delete_params = [params for sql, params in conn.executions if sql == self.module.DELETE_BATCH_SQL]
        self.assertEqual(delete_params, [(conn.cutoff, 1_000)] * 4)

    def test_exact_cutoff_and_newer_rows_are_retained(self):
        cutoff = datetime(2026, 4, 14, tzinfo=timezone.utc)
        delta = timedelta(microseconds=1)
        conn = FakeConnection(
            self.module,
            rows=[("old", cutoff - delta), ("boundary", cutoff), ("new", cutoff + delta)],
        )

        self.assertEqual(self.module.purge_expired_prompt_logs(conn), 1)
        self.assertEqual(conn.rows, [("boundary", cutoff), ("new", cutoff + delta)])

    def test_repeated_run_is_safe_when_no_expired_rows_remain(self):
        first = FakeConnection(self.module, (2, 0))
        second = FakeConnection(self.module, (0,))

        self.assertEqual(self.module.purge_expired_prompt_logs(first), 2)
        self.assertEqual(self.module.purge_expired_prompt_logs(second), 0)
        self.assertEqual(second.commits, 1)

    def test_batch_failure_rolls_back_and_main_returns_nonzero(self):
        conn = FakeConnection(self.module, fail_batch=True)
        connect_calls = []

        def connect(dsn, **kwargs):
            connect_calls.append((dsn, kwargs))
            return conn

        fake_psycopg = type("FakePsycopg", (), {"connect": staticmethod(connect)})

        with patch.object(self.module, "psycopg", fake_psycopg), patch.dict(
            self.module.os.environ, {"AI_DATABASE_DSN": "postgresql://test"}, clear=True
        ):
            self.assertEqual(self.module.main(), 1)

        self.assertEqual(conn.rollbacks, 1)
        self.assertEqual(conn.closed, 1)
        self.assertEqual(
            connect_calls,
            [
                (
                    "postgresql://test",
                    {
                        "connect_timeout": self.module.CONNECT_TIMEOUT_SECONDS,
                        "options": (
                            f"-c statement_timeout={self.module.STATEMENT_TIMEOUT_MS}"
                        ),
                    },
                )
            ],
        )

    def test_dsn_priority_matches_ai_runtime(self):
        environ = {
            "AI_DATABASE_DSN": "ai",
            "QUANT_DB_DSN": "quant",
            "DATABASE_URL": "fallback",
        }
        self.assertEqual(self.module.resolve_dsn(environ), "ai")
        self.assertEqual(self.module.resolve_dsn({"QUANT_DB_DSN": "quant"}), "quant")
        self.assertEqual(self.module.resolve_dsn({"DATABASE_URL": "fallback"}), "fallback")
        self.assertEqual(
            self.module.resolve_dsn({"DATABASE_URL": "postgresql+asyncpg://db/app"}),
            "postgresql://db/app",
        )
        with self.assertRaises(RuntimeError):
            self.module.resolve_dsn({})


def _load_script():
    path = Path("scripts/purge_ai_prompt_logs.py")
    spec = importlib.util.spec_from_file_location("purge_ai_prompt_logs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
