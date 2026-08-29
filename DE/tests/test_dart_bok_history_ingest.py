from datetime import date
import unittest

from scripts.ingest_dart_bok_history import (
    DartReportPeriod,
    DartUniverseEntry,
    SchemaMappingError,
    TableColumn,
    TableSchema,
    SourceStats,
    iter_resumable_dart_jobs,
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

    def test_parse_args_enables_dart_skip_existing_flag(self):
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
                "--dart-skip-existing",
            ]
        )

        self.assertTrue(args.dart_skip_existing)

    def test_refresh_existing_overrides_skip_existing_for_restatements(self):
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
                "--dart-skip-existing",
                "--dart-refresh-existing",
            ]
        )

        self.assertTrue(args.dart_skip_existing)
        self.assertTrue(args.dart_refresh_existing)

    def test_resumable_dart_jobs_skip_existing_feature_keys(self):
        universe = [
            DartUniverseEntry(symbol="005930", corp_code="00126380", symbol_id=1),
            DartUniverseEntry(symbol="000660", corp_code="00164742", symbol_id=2),
        ]
        periods = [
            DartReportPeriod(2026, "11013", date(2026, 3, 31)),
            DartReportPeriod(2026, "11011", date(2026, 12, 31)),
        ]
        existing_keys = {
            (1, date(2026, 3, 31), "11013", "CFS"),
            (2, date(2026, 12, 31), "11011", "CFS"),
        }
        stats = SourceStats()

        jobs = list(
            iter_resumable_dart_jobs(
                universe,
                periods,
                "CFS",
                existing_keys,
                skip_existing=True,
                stats=stats,
            )
        )

        self.assertEqual(
            jobs,
            [
                (universe[0], periods[1]),
                (universe[1], periods[0]),
            ],
        )
        self.assertEqual(stats.rows_skipped, 2)

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

    def test_all_macro_preset_includes_monthly_oil_series(self):
        configs = load_bok_series_configs(None, "all-macro")

        self.assertEqual(len(configs), 15)
        self.assertEqual(
            {config.item_code1 for config in configs if config.stat_code == "902Y003"},
            {"010101", "010102", "010103"},
        )

if __name__ == "__main__":
    unittest.main()
