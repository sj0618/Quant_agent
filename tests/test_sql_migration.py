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

    def test_runtime_migration_has_backtest_reader_and_asof_views(self):
        sql = Path("migrations/002_data_engineering_runtime.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS feature.dart_corp_symbol_map", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.symbol_feature_frame_asof", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.bok_macro_asof", sql)
        self.assertIn("CREATE OR REPLACE VIEW mart.dart_financial_asof", sql)
        self.assertIn("CREATE ROLE backtest_reader NOLOGIN", sql)


if __name__ == "__main__":
    unittest.main()
