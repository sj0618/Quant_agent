from datetime import date
from decimal import Decimal
import unittest

from quant_agent.data.models import OhlcvBar
from quant_agent.data.quality import (
    OhlcvQualityConfig,
    OhlcvQualityFramework,
    coverage_ratio,
    duplicate_keys,
    has_ohlc_order_issue,
    summarize_ohlcv_quality,
)


class QualityTests(unittest.TestCase):
    def test_coverage_ratio(self):
        observed = [date(2026, 5, 1), date(2026, 5, 2)]
        expected = [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)]
        self.assertAlmostEqual(coverage_ratio(observed, expected), 2 / 3)

    def test_duplicate_keys(self):
        bars = [
            _bar("005930", date(2026, 5, 1)),
            _bar("005930", date(2026, 5, 1)),
            _bar("000660", date(2026, 5, 1)),
        ]
        self.assertEqual(duplicate_keys(bars), {("005930", date(2026, 5, 1))})

    def test_ohlc_order_issue(self):
        self.assertFalse(has_ohlc_order_issue(_bar("005930", date(2026, 5, 1))))
        bad = _bar("005930", date(2026, 5, 1), high="90")
        self.assertTrue(has_ohlc_order_issue(bad))

    def test_summary(self):
        bars = [
            _bar("005930", date(2026, 5, 1)),
            _bar("005930", date(2026, 5, 1), close="-1"),
        ]
        summary = summarize_ohlcv_quality(bars)
        self.assertEqual(summary["rows"], 2)
        self.assertEqual(summary["duplicate_key_rows"], 1)
        self.assertEqual(summary["non_positive_price_rows"], 1)

    def test_quality_framework_detects_missing_stale_and_volume_anomalies(self):
        framework = OhlcvQualityFramework(
            OhlcvQualityConfig(stale_price_days=3, volume_anomaly_multiplier=Decimal("5"), min_volume_sample_count=3)
        )
        bars = [
            _bar("005930", date(2026, 5, 1), close="100", volume="100"),
            _bar("005930", date(2026, 5, 2), close="100", volume="100"),
            _bar("005930", date(2026, 5, 4), close="100", volume="1000"),
            _bar("000660", date(2026, 5, 1), close="200", volume="100"),
            _bar("000660", date(2026, 5, 2), close="201", volume="100"),
            _bar("000660", date(2026, 5, 4), close="202", volume="100"),
        ]

        missing = framework.validate_symbol_dates(
            bars,
            [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3), date(2026, 5, 4)],
        )
        stale = framework.detect_stale_prices(bars)
        volume = framework.detect_volume_anomalies(bars)

        self.assertIn(("005930", date(2026, 5, 3), "MISSING_SYMBOL_DATE"), _issue_keys(missing))
        self.assertIn(("005930", date(2026, 5, 4), "STALE_PRICE"), _issue_keys(stale))
        self.assertIn(("005930", date(2026, 5, 4), "HIGH_VOLUME_ANOMALY"), _issue_keys(volume))

    def test_quality_framework_compares_kis_adjusted_to_krx(self):
        framework = OhlcvQualityFramework(OhlcvQualityConfig(price_mismatch_tolerance_ratio=Decimal("0.01")))

        issues = framework.compare_kis_krx_rows(
            kis_rows=[
                {"ticker": "005930", "time": "2026-05-01", "adj_close": "103"},
                {"ticker": "000660", "time": "2026-05-01", "adj_close": "200"},
            ],
            krx_rows=[
                {"symbol": "005930", "trade_date": "2026-05-01", "close": "100"},
                {"symbol": "035420", "trade_date": "2026-05-01", "close": "50"},
            ],
        )

        self.assertIn(("005930", date(2026, 5, 1), "KIS_KRX_CLOSE_MISMATCH"), _issue_keys(issues))
        self.assertIn(("000660", date(2026, 5, 1), "KIS_MISSING_KRX_REFERENCE"), _issue_keys(issues))
        self.assertIn(("035420", date(2026, 5, 1), "KRX_MISSING_KIS_ADJUSTED"), _issue_keys(issues))


def _bar(
    symbol: str,
    trade_date: date,
    high: str = "110",
    close: str = "105",
    volume: str = "1000",
) -> OhlcvBar:
    return OhlcvBar(
        source="TEST",
        symbol=symbol,
        trade_date=trade_date,
        open=Decimal("100"),
        high=Decimal(high),
        low=Decimal("95"),
        close=Decimal(close),
        volume=Decimal(volume),
    )


def _issue_keys(issues):
    return {(issue.symbol, issue.trade_date, issue.rule_code) for issue in issues}


if __name__ == "__main__":
    unittest.main()
