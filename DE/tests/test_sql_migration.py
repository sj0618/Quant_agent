from pathlib import Path
import unittest


class SqlMigrationTests(unittest.TestCase):
    def test_m0_migration_contains_required_schemas_and_hypertables(self):
        sql = Path("migrations/001_data_engineering_m0.sql").read_text(encoding="utf-8")
        for schema in ("meta", "raw", "core", "feature", "mart"):
            self.assertIn(f"CREATE SCHEMA IF NOT EXISTS {schema};", sql)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS timescaledb;", sql)
        self.assertIn("create_hypertable('core.ohlcv_daily'", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.full_universe_asof", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.seibro_universe_asof", sql)

    def test_migration_has_lineage_and_quality_tables(self):
        sql = Path("migrations/001_data_engineering_m0.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS meta.data_quality_issue", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS meta.lineage_event", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS meta.ingestion_cursor", sql)
        self.assertIn("success BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertIn("retry_count INTEGER NOT NULL DEFAULT 0", sql)
        self.assertIn("metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb", sql)

    def test_runtime_migration_has_backtest_reader_and_asof_views(self):
        sql = Path("migrations/002_data_engineering_runtime.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS feature.dart_corp_symbol_map", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.symbol_feature_frame_asof", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.bok_macro_asof", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.dart_financial_asof", sql)
        self.assertIn("CREATE ROLE backtest_reader NOLOGIN", sql)

    def test_phase2_migration_has_observability_and_lineage_view(self):
        sql = Path("migrations/003_quality_observability_lineage.sql").read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS success", sql)
        self.assertIn("ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS retry_count", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.kis_adjusted_feature_frame_asof", sql)
        self.assertIn("feature.adjusted_ohlcv_daily", sql)
        self.assertIn("feature.ta_volume_ticker_daily", sql)

    def test_phase3_migration_rewrites_mart_and_symbol_metadata(self):
        sql = Path("migrations/004_mart_symbol_metadata.sql").read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS market_segment", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS core.symbol_name_history", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.symbol_feature_frame_asof", sql)
        self.assertIn("feature.ta_trend_ticker_daily", sql)
        self.assertIn("feature.adjusted_ohlcv_daily", sql)

    def test_symbol_security_type_migration_classifies_and_exposes_common_stock_universe(self):
        sql = Path("migrations/006_symbol_security_type_classification.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE OR REPLACE FUNCTION meta.classify_krx_security_type", sql)
        self.assertIn("UPDATE core.symbol_master", sql)
        self.assertIn("ALTER COLUMN security_type SET NOT NULL", sql)
        self.assertIn("chk_symbol_master_security_type", sql)
        self.assertIn("CREATE OR REPLACE VIEW meta.view_common_stock_universe", sql)
        self.assertIn("market_segment IN ('KOSPI', 'KOSDAQ')", sql)
        self.assertIn("security_type = '보통주'", sql)
        self.assertIn("listing_status = 'listed'", sql)
        self.assertIn("'인프라펀드'", sql)

    def test_app_ai_backtest_erd_migration_contains_requested_tables(self):
        sql = Path("migrations/011_app_ai_backtest_erd.sql").read_text(encoding="utf-8")
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

    def test_app_ai_backtest_erd_migration_contains_key_columns(self):
        sql = Path("migrations/011_app_ai_backtest_erd.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TYPE app.ai_code_status AS ENUM", sql)
        self.assertIn("CREATE TYPE app.code_execution_status AS ENUM", sql)
        self.assertIn("CREATE TYPE app.backtest_execution_mode AS ENUM", sql)
        self.assertIn("profile_image_url TEXT", sql)
        self.assertIn("trace_id UUID REFERENCES app.ai_trace(trace_id)", sql)
        self.assertIn("parse_id UUID REFERENCES app.ai_strategy_parse(parse_id) ON DELETE SET NULL", sql)
        self.assertIn("source_message_id UUID REFERENCES app.ai_chat_message(message_id)", sql)
        self.assertIn("code_status app.ai_code_status NOT NULL DEFAULT 'generated'", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS app.ai_code_validation_result", sql)
        self.assertIn("blocks_network_access BOOLEAN NOT NULL", sql)
        self.assertIn("blocks_file_write BOOLEAN NOT NULL", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS app.code_execution_run", sql)
        self.assertIn("status app.code_execution_status NOT NULL DEFAULT 'queued'", sql)
        self.assertIn("execution_run_id UUID UNIQUE REFERENCES app.code_execution_run(execution_run_id)", sql)
        self.assertIn("execution_mode app.backtest_execution_mode NOT NULL DEFAULT 'engine'", sql)
        self.assertIn("excluded_tickers_jsonb JSONB NOT NULL DEFAULT '[]'::jsonb", sql)
        self.assertIn("monthly_return_json JSONB NOT NULL DEFAULT '[]'::jsonb", sql)
        self.assertIn("tool_calls_jsonb JSONB NOT NULL DEFAULT '[]'::jsonb", sql)
        self.assertIn("code_id UUID REFERENCES app.ai_code_generation(code_id)", sql)
        self.assertIn("execution_run_id UUID REFERENCES app.code_execution_run(execution_run_id)", sql)
        self.assertIn("UNIQUE (auth_provider, provider_user_id)", sql)
        self.assertIn("UNIQUE (run_id, sequence_no)", sql)
        self.assertNotIn("CREATE EXTENSION IF NOT EXISTS pgcrypto", sql)
        self.assertIn("application must provide UUID values explicitly", sql)


if __name__ == "__main__":
    unittest.main()
