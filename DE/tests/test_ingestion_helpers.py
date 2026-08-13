import unittest
from datetime import date

from quant_agent.data.ingestion import (
    OhlcvIngestionRequest,
    OhlcvIngestionService,
    chunk_date_range,
    each_date,
)
from quant_agent.data.models import OhlcvBar


class IngestionHelperTests(unittest.TestCase):
    def test_each_date_inclusive(self):
        self.assertEqual(
            list(each_date(date(2026, 5, 15), date(2026, 5, 17))),
            [date(2026, 5, 15), date(2026, 5, 16), date(2026, 5, 17)],
        )

    def test_chunk_date_range(self):
        chunks = list(chunk_date_range(date(2026, 5, 1), date(2026, 5, 5), 2))
        self.assertEqual(
            chunks,
            [
                (date(2026, 5, 1), date(2026, 5, 2)),
                (date(2026, 5, 3), date(2026, 5, 4)),
                (date(2026, 5, 5), date(2026, 5, 5)),
            ],
        )

    def test_generic_ingestion_rejects_kis_core_writes(self):
        service = OhlcvIngestionService()
        with self.assertRaisesRegex(ValueError, "canonical KRX"):
            service.ingest_range(
                OhlcvIngestionRequest(
                    source="KIS",
                    start_date=date(2026, 5, 1),
                    end_date=date(2026, 5, 1),
                    symbols=("005930",),
                )
            )

    def test_generic_ingestion_rejects_inverted_date_range_before_db_write(self):
        service = OhlcvIngestionService()
        with self.assertRaisesRegex(ValueError, "end_date"):
            service.ingest_range(
                OhlcvIngestionRequest(
                    source="KRX",
                    start_date=date(2026, 5, 2),
                    end_date=date(2026, 5, 1),
                )
            )

    def test_krx_symbol_filter_keeps_only_requested_symbols(self):
        service = OhlcvIngestionService()
        bars = [
            _bar("005930"),
            _bar("000660"),
        ]

        self.assertEqual(
            [bar.symbol for bar in service._filter_krx_bars(bars, ("005930",))],
            ["005930"],
        )


def _bar(symbol: str) -> OhlcvBar:
    return OhlcvBar(
        source="KRX",
        symbol=symbol,
        trade_date=date(2026, 5, 1),
        open=None,
        high=None,
        low=None,
        close=None,
        volume=None,
    )


if __name__ == "__main__":
    unittest.main()
