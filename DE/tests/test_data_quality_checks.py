import unittest

from scripts.run_data_quality_checks import parse_args


class DataQualityCheckArgumentTests(unittest.TestCase):
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
