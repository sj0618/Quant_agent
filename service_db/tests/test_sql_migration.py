from pathlib import Path
import unittest


SERVICE_DB_ROOT = Path(__file__).resolve().parents[1]


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

if __name__ == "__main__":
    unittest.main()
