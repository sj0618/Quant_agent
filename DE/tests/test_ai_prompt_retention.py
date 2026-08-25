from datetime import datetime, timedelta, timezone
import os
import importlib.util
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import unittest

try:
    import psycopg
except ImportError:  # pragma: no cover - exercised by the integration-test skip condition.
    psycopg = None


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

    def test_strict_cutoff_retains_boundary_and_newer_rows_with_injected_cutoff(self):
        cutoff = datetime(2026, 4, 14, tzinfo=timezone.utc)
        delta = timedelta(microseconds=1)
        conn = FakeConnection(
            self.module,
            rows=[("old", cutoff - delta), ("boundary", cutoff), ("new", cutoff + delta)],
        )

        self.assertEqual(self.module.purge_expired_prompt_logs(conn, cutoff=cutoff), 1)
        self.assertEqual(conn.cutoff_queries, 0)
        self.assertEqual(conn.rows, [("boundary", cutoff), ("new", cutoff + delta)])

    def test_future_rows_are_retained_and_reruns_delete_zero(self):
        cutoff = datetime(2026, 4, 14, tzinfo=timezone.utc)
        conn = FakeConnection(
            self.module,
            rows=[("future", cutoff + timedelta(microseconds=1))],
        )

        self.assertEqual(self.module.purge_expired_prompt_logs(conn, cutoff=cutoff), 0)
        self.assertEqual(self.module.purge_expired_prompt_logs(conn, cutoff=cutoff), 0)
        self.assertEqual(conn.rows, [("future", cutoff + timedelta(microseconds=1))])
        self.assertEqual(conn.commits, 2)

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


class CommitCountingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.commits = 0

    def cursor(self):
        return self.connection.cursor()

    def commit(self):
        self.commits += 1
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()


@unittest.skipUnless(
    psycopg is not None and os.environ.get("AI_PROMPT_RETENTION_TEST_DSN"),
    "real PostgreSQL retention integration skipped: set AI_PROMPT_RETENTION_TEST_DSN to a disposable database",
)
class PostgresAiPromptRetentionIntegrationTests(unittest.TestCase):
    cutoff = datetime(2026, 4, 14, tzinfo=timezone.utc)

    @classmethod
    def setUpClass(cls):
        cls.module = _load_script()
        cls.dsn = os.environ["AI_PROMPT_RETENTION_TEST_DSN"]
        try:
            conn = psycopg.connect(cls.dsn, connect_timeout=2)
        except Exception as exc:
            raise unittest.SkipTest(
                f"real PostgreSQL retention integration skipped: disposable database unavailable ({type(exc).__name__})"
            ) from exc
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                database_name = cursor.fetchone()[0]
        finally:
            conn.close()
        if not database_name.startswith("ai_prompt_retention_test"):
            raise RuntimeError(
                "AI_PROMPT_RETENTION_TEST_DSN must target a disposable database named "
                "ai_prompt_retention_test*"
            )

    def setUp(self):
        self._reset_schema()

    def tearDown(self):
        self._reset_schema(drop_only=True)

    def _connect(self):
        return psycopg.connect(self.dsn, connect_timeout=2)

    def _reset_schema(self, *, drop_only=False):
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA IF EXISTS app CASCADE")
                if not drop_only:
                    cursor.execute("CREATE SCHEMA app")
                    cursor.execute("CREATE TABLE app.ai_trace (trace_id UUID PRIMARY KEY)")
                    cursor.execute(
                        """
                        CREATE TABLE app.ai_model_call_log (
                            call_id UUID PRIMARY KEY,
                            trace_id UUID REFERENCES app.ai_trace(trace_id)
                        )
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE app.ai_prompt_log (
                            prompt_log_id UUID PRIMARY KEY,
                            call_id UUID NOT NULL UNIQUE
                                REFERENCES app.ai_model_call_log(call_id),
                            created_at TIMESTAMPTZ NOT NULL
                        )
                        """
                    )
                    cursor.execute(
                        "CREATE INDEX idx_ai_prompt_log_retention "
                        "ON app.ai_prompt_log (created_at, prompt_log_id)"
                    )
            conn.commit()
        finally:
            conn.close()

    def _seed_prompt_rows(self, expired_count, retained_timestamps=()):
        records = []
        for _ in range(expired_count):
            records.append((uuid4(), uuid4(), uuid4(), self.cutoff - timedelta(microseconds=1)))
        for created_at in retained_timestamps:
            records.append((uuid4(), uuid4(), uuid4(), created_at))

        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO app.ai_trace (trace_id) VALUES (%s)",
                    [(trace_id,) for trace_id, _, _, _ in records],
                )
                cursor.executemany(
                    "INSERT INTO app.ai_model_call_log (call_id, trace_id) VALUES (%s, %s)",
                    [(call_id, trace_id) for trace_id, call_id, _, _ in records],
                )
                cursor.executemany(
                    """
                    INSERT INTO app.ai_prompt_log (prompt_log_id, call_id, created_at)
                    VALUES (%s, %s, %s)
                    """,
                    [(prompt_id, call_id, created_at) for _, call_id, prompt_id, created_at in records],
                )
            conn.commit()
        finally:
            conn.close()
        return {prompt_id for _, _, prompt_id, _ in records}

    def _count(self, table_name):
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {table_name}")
                return cursor.fetchone()[0]
        finally:
            conn.close()

    def test_real_postgres_purges_1001_rows_in_three_commits_and_preserves_parents(self):
        retained_timestamps = [self.cutoff] + [
            self.cutoff + timedelta(microseconds=index) for index in range(1, 10)
        ]
        prompt_ids = self._seed_prompt_rows(1_001, retained_timestamps)
        conn = self._connect()
        counting_conn = CommitCountingConnection(conn)
        try:
            self.assertEqual(
                self.module.purge_expired_prompt_logs(counting_conn, cutoff=self.cutoff),
                1_001,
            )
            self.assertEqual(counting_conn.commits, 3)
            self.assertEqual(
                self.module.purge_expired_prompt_logs(counting_conn, cutoff=self.cutoff),
                0,
            )
            self.assertEqual(counting_conn.commits, 4)
        finally:
            conn.close()

        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT prompt_log_id FROM app.ai_prompt_log")
                retained_ids = {row[0] for row in cursor.fetchall()}
        finally:
            conn.close()

        self.assertEqual(len(retained_ids), 10)
        self.assertTrue(retained_ids.issubset(prompt_ids))
        self.assertEqual(self._count("app.ai_model_call_log"), 1_011)
        self.assertEqual(self._count("app.ai_trace"), 1_011)

    def test_real_postgres_skip_locked_workers_delete_disjoint_rows(self):
        self._seed_prompt_rows(1_001)
        first = self._connect()
        second = self._connect()
        try:
            with first.cursor() as cursor:
                cursor.execute(self.module.DELETE_BATCH_SQL, (self.cutoff, 1_000))
                first_ids = {row[0] for row in cursor.fetchall()}
            with second.cursor() as cursor:
                cursor.execute(self.module.DELETE_BATCH_SQL, (self.cutoff, 1_000))
                second_ids = {row[0] for row in cursor.fetchall()}

            self.assertEqual(len(first_ids), 1_000)
            self.assertEqual(len(second_ids), 1)
            self.assertFalse(first_ids & second_ids)
            first.commit()
            second.commit()
        finally:
            first.close()
            second.close()

        self.assertEqual(self._count("app.ai_prompt_log"), 0)


if __name__ == "__main__":
    unittest.main()
