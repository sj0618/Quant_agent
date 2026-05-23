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


if __name__ == "__main__":
    unittest.main()
