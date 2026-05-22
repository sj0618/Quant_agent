from datetime import date
import unittest

from scripts.ingest_kis_adjusted_ohlcv import (
    FetchWindow,
    build_completed_window_cursor_upsert,
    build_window_completion_query,
    completed_window_cursor_key,
    parse_sql_bool,
    parse_window_completion,
    resolve_daily_incremental_window,
)


class KisAdjustedIngestResumeTests(unittest.TestCase):
    def test_daily_incremental_window_uses_latest_trade_date_with_calendar_warmup(self):
        self.assertEqual(
            resolve_daily_incremental_window(date(2026, 5, 22), 7),
            (date(2026, 5, 15), date(2026, 5, 22)),
        )

    def test_daily_incremental_window_rejects_negative_warmup(self):
        with self.assertRaises(ValueError):
            resolve_daily_incremental_window(date(2026, 5, 22), -1)

    def test_window_completion_query_uses_adjusted_table_and_cursor_state(self):
        window = FetchWindow(date(2026, 5, 20), date(2026, 5, 22))

        sql = build_window_completion_query("5930", window)

        self.assertIn("feature.kis_adjusted_ohlcv_daily", sql)
        self.assertIn("meta.ingestion_cursor", sql)
        self.assertIn("'005930'", sql)
        self.assertIn("'completed_window:005930:2026-05-20:2026-05-22'", sql)
        self.assertIn("observed.observed_count >= expected.expected_count", sql)

    def test_parse_window_completion_accepts_postgres_boolean_shapes(self):
        self.assertTrue(parse_window_completion([{"complete": "t"}]))
        self.assertTrue(parse_window_completion([{"complete": True}]))
        self.assertTrue(parse_window_completion([{"complete": "1"}]))
        self.assertFalse(parse_window_completion([{"complete": "f"}]))
        self.assertFalse(parse_window_completion([]))
        self.assertFalse(parse_sql_bool(None))

    def test_completed_window_cursor_upsert_records_each_window(self):
        first = FetchWindow(date(2026, 5, 20), date(2026, 5, 20))
        second = FetchWindow(date(2026, 5, 21), date(2026, 5, 22))

        sql = build_completed_window_cursor_upsert(
            [("5930", first), ("000660", second)],
            "11111111-1111-1111-1111-111111111111",
        )

        self.assertIn("INSERT INTO meta.ingestion_cursor", sql)
        self.assertIn("'kis_adjusted_ohlcv_daily'", sql)
        self.assertIn("'completed_window:005930:2026-05-20:2026-05-20'", sql)
        self.assertIn("'completed_window:000660:2026-05-21:2026-05-22'", sql)
        self.assertIn("ON CONFLICT (source_id, dataset, cursor_key) DO UPDATE", sql)

    def test_completed_window_cursor_key_normalizes_ticker(self):
        self.assertEqual(
            completed_window_cursor_key("660", FetchWindow(date(2026, 5, 21), date(2026, 5, 22))),
            "completed_window:000660:2026-05-21:2026-05-22",
        )


if __name__ == "__main__":
    unittest.main()
