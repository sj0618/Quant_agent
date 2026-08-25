import unittest
from datetime import date

from quant_agent.data.indicators.catalog import (
    CATALOG_COUNTS,
    INDICATOR_CATALOG,
    validate_catalog_counts,
)
from quant_agent.data.indicators.compute import compute_symbol_indicator_rows


class IndicatorCatalogTests(unittest.TestCase):
    def test_catalog_counts_match_product_contract(self):
        validate_catalog_counts()
        actual = {}
        for item in INDICATOR_CATALOG:
            actual[item.category] = actual.get(item.category, 0) + 1
        self.assertEqual(actual, CATALOG_COUNTS)
        self.assertEqual(sum(actual.values()), 158)

    def test_explicit_empty_definition_list_does_not_compute_entire_catalog(self):
        rows = [
            {
                "symbol_id": 1,
                "trade_date": date(2026, 5, 15),
                "open": 100,
                "high": 110,
                "low": 90,
                "close": 105,
                "volume": 1000,
            }
        ]

        self.assertEqual(compute_symbol_indicator_rows(rows, definitions=[]), {})


if __name__ == "__main__":
    unittest.main()
