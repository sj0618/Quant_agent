import unittest

from quant_agent.data.indicators.catalog import CATALOG_COUNTS, INDICATOR_CATALOG, validate_catalog_counts


class IndicatorCatalogTests(unittest.TestCase):
    def test_catalog_counts_match_product_contract(self):
        validate_catalog_counts()
        actual = {}
        for item in INDICATOR_CATALOG:
            actual[item.category] = actual.get(item.category, 0) + 1
        self.assertEqual(actual, CATALOG_COUNTS)
        self.assertEqual(sum(actual.values()), 158)


if __name__ == "__main__":
    unittest.main()
