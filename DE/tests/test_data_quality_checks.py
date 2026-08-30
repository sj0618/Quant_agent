from datetime import date
import unittest

from quant_agent.data.repository import _expected_dart_period_values
from scripts.run_data_quality_checks import parse_args


class DataQualityCheckArgumentTests(unittest.TestCase):
    def test_expected_dart_period_values_are_explicit_dates(self):
        values = _expected_dart_period_values(date(2026, 1, 1), date(2026, 8, 28))

        self.assertEqual(
            values,
            "('11013', '2026-03-31'::date), ('11012', '2026-06-30'::date)",
        )

    def test_backtest_readiness_exposes_bok_staleness_policy(self):
        args = parse_args(
            [
                "--start-date",
                "2026-01-01",
                "--end-date",
                "2026-08-28",
                "--checks",
                "backtest-readiness",
                "--bok-staleness-days",
                "14",
            ]
        )

        self.assertEqual(args.checks, ["backtest-readiness"])
        self.assertEqual(args.bok_staleness_days, 14)


if __name__ == "__main__":
    unittest.main()
