from datetime import date
import unittest

from quant_agent.data.ingestion import chunk_date_range, each_date


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


if __name__ == "__main__":
    unittest.main()
