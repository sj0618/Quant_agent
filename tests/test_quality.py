from datetime import date
from decimal import Decimal
import unittest

from quant_agent.data.models import OhlcvBar
from quant_agent.data.quality import coverage_ratio, duplicate_keys, has_ohlc_order_issue, summarize_ohlcv_quality


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


def _bar(symbol: str, trade_date: date, high: str = "110", close: str = "105") -> OhlcvBar:
    return OhlcvBar(
        source="TEST",
        symbol=symbol,
        trade_date=trade_date,
        open=Decimal("100"),
        high=Decimal(high),
        low=Decimal("95"),
        close=Decimal(close),
        volume=Decimal("1000"),
    )


if __name__ == "__main__":
    unittest.main()

