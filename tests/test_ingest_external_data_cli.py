from pathlib import Path
import unittest


class IngestExternalDataCliTests(unittest.TestCase):
    def test_ingest_external_data_does_not_include_seibro_job(self):
        source = Path("scripts/ingest_external_data.py").read_text(encoding="utf-8")

        self.assertIn('choices=["bok-series", "dart-corp-codes", "dart-financial", "kind-sector"]', source)
        self.assertNotIn("seibro-reports", source)
        self.assertNotIn("SEIBRO_REPORT_ENDPOINT", source)


if __name__ == "__main__":
    unittest.main()
