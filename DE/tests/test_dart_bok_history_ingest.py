import os
import tempfile
from datetime import date
from pathlib import Path
import unittest

from scripts.ingest_dart_bok_history import (
    DartReportPeriod,
    SchemaMappingError,
    TableColumn,
    TableSchema,
    format_bok_period,
    load_bok_series_configs,
    parse_args,
    resolve_dart_report_periods,
    validate_required_values,
)


class DartBokHistoryIngestTests(unittest.TestCase):
    def test_bok_period_format_matches_cycle(self):
        self.assertEqual(format_bok_period(date(2026, 5, 26), "D"), "20260526")
        self.assertEqual(format_bok_period(date(2026, 5, 26), "M"), "202605")
        self.assertEqual(format_bok_period(date(2026, 5, 26), "Q"), "2026Q2")
        self.assertEqual(format_bok_period(date(2026, 5, 26), "A"), "2026")

    def test_test_one_month_dart_window_uses_filing_window(self):
        args = parse_args(
            [
                "--scope",
                "test-1m",
                "--sources",
                "dart",
                "--start-date",
                "2026-04-26",
                "--end-date",
                "2026-05-26",
            ]
        )

        periods = resolve_dart_report_periods(args, date(2026, 4, 26), date(2026, 5, 26))

        self.assertIn(DartReportPeriod(2026, "11013", date(2026, 3, 31)), periods)
        self.assertNotIn(DartReportPeriod(2025, "11011", date(2025, 12, 31)), periods)

    def test_full_period_end_window_selects_quarterly_reports(self):
        args = parse_args(
            [
                "--scope",
                "custom",
                "--sources",
                "dart",
                "--start-date",
                "2016-01-01",
                "--end-date",
                "2016-12-31",
                "--dart-period-mode",
                "period-end",
            ]
        )

        periods = resolve_dart_report_periods(args, date(2016, 1, 1), date(2016, 12, 31))

        self.assertEqual(len(periods), 4)
        self.assertEqual({period.report_code for period in periods}, {"11013", "11012", "11014", "11011"})

    def test_schema_validation_rejects_missing_non_nullable_column(self):
        table_schema = TableSchema(
            schema_name="feature",
            table_name="bok_macro_daily",
            columns=(
                TableColumn("series_id", "text", "text", False, None, 1),
                TableColumn("effective_date", "date", "date", False, None, 2),
                TableColumn("value", "numeric", "numeric", True, None, 3),
            ),
            primary_key=("series_id", "effective_date"),
            unique_constraints=(),
        )

        with self.assertRaises(SchemaMappingError):
            validate_required_values(table_schema, {"series_id": "722Y001:0101000"})

    def test_rate_fx_preset_loads_without_env_json(self):
        configs = load_bok_series_configs(None, "rate-fx")

        self.assertGreaterEqual(len(configs), 10)
        self.assertEqual(configs[0].stat_code, "722Y001")
        self.assertEqual(configs[0].item_code1, "0101000")
        self.assertIn("731Y003", {config.stat_code for config in configs})

    def test_load_runtime_dotenv_skips_when_airflow_disables_it(self):
        from scripts import ingest_dart_bok_history as module

        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_path = Path(tmpdir) / "runtime.env"
            dotenv_path.write_text("SENTINEL_DOTENV_SHOULD_NOT_APPEAR=loaded\n", encoding="utf-8")
            previous = os.environ.get("QUANT_AIRFLOW_LOAD_DOTENV")
            os.environ["QUANT_AIRFLOW_LOAD_DOTENV"] = "false"
            try:
                module.load_runtime_dotenv(str(dotenv_path))
            finally:
                if previous is None:
                    os.environ.pop("QUANT_AIRFLOW_LOAD_DOTENV", None)
                else:
                    os.environ["QUANT_AIRFLOW_LOAD_DOTENV"] = previous

        self.assertIsNone(os.environ.get("SENTINEL_DOTENV_SHOULD_NOT_APPEAR"))


if __name__ == "__main__":
    unittest.main()
