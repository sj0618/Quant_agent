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

if __name__ == "__main__":
    unittest.main()
