import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SERVICE_DB_ROOT = Path(__file__).resolve().parents[1]
REPLAY_VERIFIER_PATH = SERVICE_DB_ROOT / "scripts/verify_fixed_migration_replay.py"
REPLAY_RUNNER_PATH = SERVICE_DB_ROOT / "scripts/run_fixed_migration_replay.py"
WORKFLOW_PATH = SERVICE_DB_ROOT.parents[0] / ".github/workflows/ai-logging.yml"
ARCHIVE_MIGRATION = "023_archive_undecodable_analysis_jobs.sql"
ARCHIVE_TEST_DSN_ENV = "SERVICE_DB_ARCHIVE_TEST_DSN"
ARCHIVE_TEST_DATABASE = "ai_analysis_job_archive_test"


def _normalized(sql_fragment: str) -> str:
    return " ".join(sql_fragment.split())


def _between(sql: str, opening: str, closing: str) -> str:
    start = sql.index(opening) + len(opening)
    return sql[start : sql.index(closing, start)]


def load_replay_verifier():
    spec = importlib.util.spec_from_file_location("service_db_replay_verifier", REPLAY_VERIFIER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module




class ServiceDbSqlMigrationTests(unittest.TestCase):
    def test_app_ai_backtest_baseline_contains_requested_tables(self):
        sql = (SERVICE_DB_ROOT / "migrations/011_app_ai_backtest_erd.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE SCHEMA IF NOT EXISTS app;", sql)
        for table_name in (
            "app.users",
            "app.strategy",
            "app.ai_chat_session",
            "app.ai_chat_message",
            "app.ai_trace",
            "app.ai_strategy_parse",
            "app.ai_validation_result",
            "app.ai_code_generation",
            "app.ai_code_validation_result",
            "app.code_execution_run",
            "app.backtest_run",
            "app.backtest_summary",
            "app.backtest_metric_detail",
            "app.ai_backtest_report",
            "app.ai_backtest_report_metric",
            "app.ai_model_call_log",
            "app.ai_prompt_log",
            "app.ai_agent_execution_log",
            "app.ai_error_log",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table_name}", sql)

    def test_app_ai_backtest_baseline_matches_writer_contract(self):
        sql = (SERVICE_DB_ROOT / "migrations/011_app_ai_backtest_erd.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TYPE app.ai_code_status AS ENUM", sql)
        self.assertIn("CREATE TYPE app.code_execution_status AS ENUM", sql)
        self.assertIn("CREATE TYPE app.backtest_execution_mode AS ENUM", sql)
        self.assertIn("trace_id UUID REFERENCES app.ai_trace(trace_id)", sql)
        self.assertIn("execution_run_id UUID UNIQUE REFERENCES app.code_execution_run(execution_run_id)", sql)
        self.assertIn("execution_mode app.backtest_execution_mode NOT NULL DEFAULT 'engine'", sql)
        self.assertIn("UNIQUE (run_id, sequence_no)", sql)
        self.assertNotIn("CREATE EXTENSION IF NOT EXISTS pgcrypto", sql)

    def test_email_report_can_trace_its_source_run_and_ai_report(self):
        sql = (SERVICE_DB_ROOT / "migrations/014_create_report_email_tables.sql").read_text(encoding="utf-8")
        self.assertIn("backtest_run_id uuid", sql)
        self.assertIn("REFERENCES app.backtest_run(run_id)", sql)
        self.assertIn("ai_report_id uuid", sql)
        self.assertIn("REFERENCES app.ai_backtest_report(report_id)", sql)

    def test_ai_runtime_logging_migration_is_additive_and_idempotent(self):
        sql = (SERVICE_DB_ROOT / "migrations/013_ai_runtime_logging.sql").read_text(encoding="utf-8")
        upper_sql = sql.upper()
        self.assertIn("ADD COLUMN IF NOT EXISTS execution_id UUID", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS response_schema_name TEXT", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS web_search_used BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertIn("REFERENCES app.ai_agent_execution_log(execution_id)", sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_ai_prompt_log_retention", sql)
        self.assertNotIn("DROP ", upper_sql)
        self.assertNotIn("TRUNCATE ", upper_sql)


    def test_ai_prompt_response_summary_migration_is_additive_and_idempotent(self):
        sql = (
            SERVICE_DB_ROOT / "migrations/019_ai_prompt_response_summary.sql"
        ).read_text(encoding="utf-8")
        upper_sql = sql.upper()
        self.assertIn(
            "ADD COLUMN IF NOT EXISTS assistant_response_summary TEXT",
            sql,
        )
        self.assertNotIn("DROP ", upper_sql)
        self.assertNotIn("TRUNCATE ", upper_sql)

    def test_ai_analysis_job_migration_is_additive_and_idempotent(self):
        sql = (SERVICE_DB_ROOT / "migrations/021_ai_analysis_jobs.sql").read_text(encoding="utf-8")
        upper_sql = sql.upper()
        self.assertIn("CREATE TABLE IF NOT EXISTS app.ai_analysis_job", sql)
        self.assertIn("job_jsonb JSONB NOT NULL", sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_user_updated", sql)
        self.assertNotIn("DROP ", upper_sql)
        self.assertNotIn("TRUNCATE ", upper_sql)


    def test_execution_process_identity_migration_is_additive_and_idempotent(self):
        sql = (
            SERVICE_DB_ROOT
            / "migrations/015_ai_backtest_execution_process_identity.sql"
        ).read_text(encoding="utf-8")
        upper_sql = sql.upper()
        for column_definition in (
            "ADD COLUMN IF NOT EXISTS attempt_id UUID",
            "ADD COLUMN IF NOT EXISTS worker_host TEXT",
            "ADD COLUMN IF NOT EXISTS worker_pid INTEGER",
            "ADD COLUMN IF NOT EXISTS worker_pgid INTEGER",
            "ADD COLUMN IF NOT EXISTS worker_started_at TIMESTAMPTZ",
        ):
            self.assertIn(column_definition, sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_code_execution_run_attempt", sql)
        self.assertNotIn("DROP ", upper_sql)
        self.assertNotIn("TRUNCATE ", upper_sql)

    def test_ai_backtest_idempotency_migration_is_additive_and_idempotent(self):
        sql = (SERVICE_DB_ROOT / "migrations/016_ai_backtest_idempotency.sql").read_text(encoding="utf-8")
        upper_sql = sql.upper()
        self.assertIn("CREATE TABLE IF NOT EXISTS app.ai_backtest_request", sql)
        self.assertIn("scope_family_id UUID NOT NULL", sql)
        self.assertIn("client_request_key TEXT NOT NULL", sql)
        self.assertIn("payload_fingerprint TEXT NOT NULL", sql)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_backtest_request_scope_key", sql)
        self.assertIn("WHERE safety_lease IN ('active', 'blocked_unknown')", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS app.ai_backtest_replacement_approval", sql)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_backtest_replacement_key_hash", sql)
        self.assertIn("WHERE status = 'issued'", sql)
        self.assertNotIn("DROP ", upper_sql)
        self.assertNotIn("TRUNCATE ", upper_sql)

    def test_notification_settings_migration_is_additive_and_idempotent(self):
        sql = (
            SERVICE_DB_ROOT
            / "migrations/017_add_notification_settings_to_users.sql"
        ).read_text(encoding="utf-8")
        upper_sql = sql.upper()
        for column_definition in (
            "ADD COLUMN IF NOT EXISTS daily_report_email BOOLEAN NOT NULL DEFAULT TRUE",
            "ADD COLUMN IF NOT EXISTS action_emails BOOLEAN NOT NULL DEFAULT TRUE",
            "ADD COLUMN IF NOT EXISTS marketing_email BOOLEAN NOT NULL DEFAULT FALSE",
            "ADD COLUMN IF NOT EXISTS delivery_hour TEXT NOT NULL DEFAULT '08:00'",
        ):
            self.assertIn(column_definition, sql)
        self.assertNotIn("UPDATE APP.USER_NOTIFICATION_SETTINGS", upper_sql)
        self.assertNotIn("DROP TABLE", upper_sql)
        self.assertNotIn("TRUNCATE ", upper_sql)

    def test_email_delivery_outbox_is_separate_from_history(self):
        sql = (
            SERVICE_DB_ROOT
            / "migrations/018_create_email_delivery_outbox.sql"
        ).read_text(encoding="utf-8")
        upper_sql = sql.upper()
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS app.email_delivery_outbox",
            sql,
        )
        for column_definition in (
            "idempotency_key text NOT NULL",
            "attempt_count integer DEFAULT 0 NOT NULL",
            "max_attempts integer DEFAULT 3 NOT NULL",
            "next_attempt_at timestamptz DEFAULT now() NOT NULL",
            "claimed_by text",
            "claim_token uuid",
            "claim_expires_at timestamptz",
        ):
            self.assertIn(column_definition, sql)
        self.assertIn(
            "CREATE INDEX IF NOT EXISTS idx_email_delivery_outbox_due",
            sql,
        )
        self.assertIn(
            "CREATE INDEX IF NOT EXISTS idx_email_delivery_outbox_claim_expiry",
            sql,
        )
        self.assertNotIn("ALTER TABLE app.email_delivery_history", sql)
        self.assertNotIn("DROP TABLE", upper_sql)
        self.assertNotIn("TRUNCATE ", upper_sql)

    def test_fixed_replay_verifier_rejects_wrong_disposable_dsn_components(self):
        verifier = load_replay_verifier()
        with self.assertRaises(verifier.ReplayContractError):
            verifier.validate_disposable_dsn(
                "postgresql://replay:secret@127.0.0.1:5433/not_disposable"
                "?application_name=p0_disposable",
                expected_host="127.0.0.1",
                expected_port="5433",
                expected_user="replay",
                expected_database="p0_replay_disposable",
                disposable_marker="p0_disposable",
            )
        with self.assertRaises(verifier.ReplayContractError):
            verifier.validate_disposable_dsn(
                "postgresql://replay:secret@127.0.0.1:5433/p0_replay_disposable"
                "?application_name=wrong_marker",
                expected_host="127.0.0.1",
                expected_port="5433",
                expected_user="replay",
                expected_database="p0_replay_disposable",
                disposable_marker="p0_disposable",
            )

    def test_fixed_replay_verifier_blocks_before_sql_without_external_inputs(self):
        verifier = load_replay_verifier()
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "replay-artifact.json"
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(verifier.main(["--artifact", str(artifact)]), 2)
            payload = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(
            payload["missing_external_inputs"], ["external_signer", "sbom", "trusted_root"]
        )
        self.assertIn("artifact_sha256", payload)
        self.assertEqual(payload["markers"][-1], {"version": 1, "state": "BLOCKED"})
        stored_hash = payload.pop("artifact_sha256")
        self.assertEqual(stored_hash, verifier._canonical_hash(payload))

    def test_fixed_replay_contract_pins_order_catalog_and_pg17_golden(self):
        verifier = load_replay_verifier()
        migrations = tuple(
            path.name for path in sorted((SERVICE_DB_ROOT / "migrations").glob("*.sql"))
        )
        self.assertEqual(migrations, verifier.FIXED_MIGRATIONS)
        source = REPLAY_VERIFIER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("inet_server_addr", source)
        self.assertIn("pgcrypto", source)
        self.assertIn("PG17_GOLDEN_SHA256", source)
        self.assertIn("PASS1_COMPLETE", source)
        self.assertIn("PASS2_COMPLETE", source)
        self.assertIn("final_catalog_union_sha256", source)
        self.assertIn("catalog union digest parity", source)
        self.assertIn("INTERNAL_TRANSACTION_MIGRATION", source)

    def test_replay_workflow_has_separate_databases_and_artifact_discard_contract(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        runner = REPLAY_RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("migration-replay-db:", workflow)
        self.assertIn("audit-purge-db:", workflow)
        self.assertIn("5433:5432", workflow)
        self.assertIn("5434:5432", workflow)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS pgcrypto", workflow)
        self.assertIn("--port=5433", workflow)
        self.assertLess(
            workflow.index("CREATE EXTENSION IF NOT EXISTS pgcrypto"),
            workflow.index("run_fixed_migration_replay.py"),
        )
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("run_fixed_migration_replay.py", workflow)
        self.assertIn("service_db/scripts/**", workflow)
        self.assertIn("service_db/tests/test_sql_migration.py", workflow)
        self.assertIn("DROP DATABASE IF EXISTS", runner)
        self.assertIn("forced_discard", runner)
        self.assertIn("missing_external_inputs", runner)


    def test_archive_migration_moves_undecodable_rows_in_one_statement(self):
        sql = (SERVICE_DB_ROOT / "migrations" / ARCHIVE_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS app.ai_analysis_job_legacy", sql)
        # The delete and the insert must be one statement, so a row can never be removed
        # from the live table without landing in the archive.
        delete_at = sql.index("DELETE FROM app.ai_analysis_job")
        insert_at = sql.index("INSERT INTO app.ai_analysis_job_legacy")
        self.assertLess(sql.index("WITH moved AS ("), delete_at)
        self.assertLess(delete_at, insert_at)
        self.assertEqual(sql.count("DELETE FROM"), 1)
        self.assertNotIn("DROP TABLE", sql.upper())
        self.assertNotIn("TRUNCATE ", sql.upper())
        self.assertIn(
            "VALIDATE CONSTRAINT ai_analysis_job_execution_manifest_v1_check", sql
        )

    def test_archive_predicate_is_the_exact_negation_of_the_closing_check(self):
        """A row must not be able to both survive the move and fail the new constraint."""

        sql = (SERVICE_DB_ROOT / "migrations" / ARCHIVE_MIGRATION).read_text(encoding="utf-8")
        moved = _between(sql, "DELETE FROM app.ai_analysis_job\n    WHERE (", ") IS NOT TRUE")
        checked = _between(
            sql,
            "ADD CONSTRAINT ai_analysis_job_decodable_document_check CHECK ((",
            ") IS TRUE);",
        )
        self.assertEqual(_normalized(moved), _normalized(checked))

    def test_archive_migration_is_null_safe_on_every_json_type_test(self):
        """`jsonb_typeof` returns NULL for an absent key, and NULL passes a CHECK.

        That is how migration 021's constraint came to accept the manifest-less rows it was
        written to forbid, and an un-COALESCEd test in the move predicate would likewise
        leave those rows in place - or, on the performance branch, sweep valid rows out.
        """

        sql = (SERVICE_DB_ROOT / "migrations" / ARCHIVE_MIGRATION).read_text(encoding="utf-8")
        for line in sql.splitlines():
            if "jsonb_typeof" in line and not line.lstrip().startswith("--"):
                self.assertIn("COALESCE(jsonb_typeof", line, f"un-COALESCEd type test: {line.strip()}")
        self.assertIn(") IS NOT TRUE", sql)
        self.assertIn(") IS TRUE);", sql)

    def test_archive_migration_is_registered_everywhere_it_has_to_run(self):
        verifier = load_replay_verifier()
        self.assertIn(ARCHIVE_MIGRATION, verifier.FIXED_MIGRATIONS)
        self.assertIn("ai_analysis_job_legacy", verifier.OWNED_RELATIONS["r"])
        self.assertIn("ai_analysis_job_decodable_document_check", verifier.OWNED_CONSTRAINTS)
        self.assertIn("ai_analysis_job_execution_manifest_v1_check", verifier.OWNED_CONSTRAINTS)
        deploy = (SERVICE_DB_ROOT.parents[0] / ".github/workflows/deploy.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(ARCHIVE_MIGRATION, deploy)


@unittest.skipUnless(
    os.getenv(ARCHIVE_TEST_DSN_ENV), f"{ARCHIVE_TEST_DSN_ENV} is not configured"
)
class AnalysisJobArchiveMigrationTests(unittest.TestCase):
    """Replay 023 against a real server; string assertions cannot see three-valued logic."""

    MANIFEST = json.dumps(
        {
            "schema_version": "1",
            "contract_hash": "0" * 64,
            "run_identity": {"incarnation": "x"},
            "policy_hashes": {"p": "h"},
            "session": {},
            "capabilities": {},
            "events": {
                "signals": [], "orders": [], "fills": [],
                "positions": [], "trades": [], "equity": [],
            },
        }
    )

    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.psycopg = psycopg
        admin = os.environ[ARCHIVE_TEST_DSN_ENV]
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{ARCHIVE_TEST_DATABASE}"')
            conn.execute(f'CREATE DATABASE "{ARCHIVE_TEST_DATABASE}"')
        cls.dsn = admin.rsplit("/", 1)[0] + "/" + ARCHIVE_TEST_DATABASE

    @classmethod
    def tearDownClass(cls):
        with cls.psycopg.connect(os.environ[ARCHIVE_TEST_DSN_ENV], autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{ARCHIVE_TEST_DATABASE}"')

    def _migration(self, name):
        return (SERVICE_DB_ROOT / "migrations" / name).read_text(encoding="utf-8")

    def _seeded_connection(self, conn):
        # Each test replays onto a clean schema, the way the fixed replay resets between passes.
        conn.execute("DROP SCHEMA IF EXISTS app CASCADE")
        conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        for path in sorted((SERVICE_DB_ROOT / "migrations").glob("*.sql")):
            if path.name != ARCHIVE_MIGRATION:
                conn.execute(path.read_text(encoding="utf-8"))
        # These rows predate 021, so seed them with its constraint absent and then re-apply
        # 021, whose ADD CONSTRAINT ... NOT VALID grandfathers them exactly as production does.
        conn.execute(
            "ALTER TABLE app.ai_analysis_job"
            " DROP CONSTRAINT ai_analysis_job_execution_manifest_v1_check"
        )
        for job_id, document in self._fixtures().items():
            conn.execute(
                "INSERT INTO app.ai_analysis_job (job_id, user_id, job_jsonb, created_at, updated_at)"
                " VALUES (%s, 'u', %s::jsonb, now(), now())",
                (job_id, document),
            )
        conn.execute(self._migration("021_ai_analysis_jobs.sql"))

    def _fixtures(self):
        manifest = json.loads(self.MANIFEST)
        no_equity = json.loads(self.MANIFEST)
        del no_equity["events"]["equity"]
        empty_policy = json.loads(self.MANIFEST)
        empty_policy["policy_hashes"] = {}
        return {
            # Decodable: performance may be absent, JSON null, or either union member.
            "keep_no_result": json.dumps({"execution_manifest": manifest}),
            "keep_no_performance": json.dumps(
                {"execution_manifest": manifest, "result": {"summary": "s"}}
            ),
            "keep_null_performance": json.dumps(
                {"execution_manifest": manifest, "result": {"performance": None}}
            ),
            "keep_available": json.dumps(
                {
                    "execution_manifest": manifest,
                    "result": {"performance": {"availability": "available"}},
                }
            ),
            "keep_unavailable": json.dumps(
                {
                    "execution_manifest": manifest,
                    "result": {"performance": {"availability": "unavailable"}},
                }
            ),
            # Undecodable, one per way a legacy document falls short.
            "drop_no_manifest": json.dumps({"status": "completed"}),
            "drop_partial_manifest": json.dumps({"execution_manifest": no_equity}),
            "drop_empty_policy_hashes": json.dumps({"execution_manifest": empty_policy}),
            "drop_no_availability": json.dumps(
                {"execution_manifest": manifest, "result": {"performance": {"x": 1}}}
            ),
            "drop_bad_availability": json.dumps(
                {
                    "execution_manifest": manifest,
                    "result": {"performance": {"availability": "maybe"}},
                }
            ),
        }

    def test_archive_keeps_decodable_rows_and_collects_every_legacy_shape(self):
        with self.psycopg.connect(self.dsn, autocommit=True) as conn:
            self._seeded_connection(conn)
            conn.execute(self._migration(ARCHIVE_MIGRATION))

            live = {row[0] for row in conn.execute("SELECT job_id FROM app.ai_analysis_job")}
            archived = dict(
                conn.execute("SELECT job_id, archive_reason FROM app.ai_analysis_job_legacy")
            )

        expected_live = {name for name in self._fixtures() if name.startswith("keep_")}
        self.assertEqual(live, expected_live)
        self.assertEqual(
            set(archived), {name for name in self._fixtures() if name.startswith("drop_")}
        )
        self.assertEqual(archived["drop_no_manifest"], "missing_execution_manifest")
        self.assertEqual(archived["drop_no_availability"], "missing_performance_availability")
        self.assertEqual(archived["drop_bad_availability"], "missing_performance_availability")
        self.assertEqual(archived["drop_partial_manifest"], "incomplete_execution_manifest")
        self.assertEqual(archived["drop_empty_policy_hashes"], "incomplete_execution_manifest")

    def test_archive_ends_the_grandfathering_and_closes_the_table(self):
        with self.psycopg.connect(self.dsn, autocommit=True) as conn:
            self._seeded_connection(conn)
            conn.execute(self._migration(ARCHIVE_MIGRATION))

            validated = dict(
                conn.execute(
                    "SELECT conname, convalidated FROM pg_constraint"
                    " WHERE conrelid = 'app.ai_analysis_job'::regclass AND contype = 'c'"
                )
            )
            self.assertTrue(validated["ai_analysis_job_execution_manifest_v1_check"])
            self.assertTrue(validated["ai_analysis_job_decodable_document_check"])

            # The shapes 021 admitted must now be refused outright.
            for document in (
                '{"job_id": "probe"}',
                json.dumps(
                    {
                        "execution_manifest": json.loads(self.MANIFEST),
                        "result": {"performance": {"x": 1}},
                    }
                ),
            ):
                with self.assertRaises(self.psycopg.errors.CheckViolation):
                    conn.execute(
                        "INSERT INTO app.ai_analysis_job"
                        " (job_id, user_id, job_jsonb, created_at, updated_at)"
                        " VALUES ('probe', 'u', %s::jsonb, now(), now())",
                        (document,),
                    )

    def test_archive_migration_is_idempotent(self):
        with self.psycopg.connect(self.dsn, autocommit=True) as conn:
            self._seeded_connection(conn)
            conn.execute(self._migration(ARCHIVE_MIGRATION))
            first = conn.execute(
                "SELECT (SELECT count(*) FROM app.ai_analysis_job),"
                " (SELECT count(*) FROM app.ai_analysis_job_legacy)"
            ).fetchone()
            conn.execute(self._migration(ARCHIVE_MIGRATION))
            second = conn.execute(
                "SELECT (SELECT count(*) FROM app.ai_analysis_job),"
                " (SELECT count(*) FROM app.ai_analysis_job_legacy)"
            ).fetchone()
        self.assertEqual(first, second)



if __name__ == "__main__":
    unittest.main()
