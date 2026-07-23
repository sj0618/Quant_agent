import unittest

import pandas as pd

from scripts import compute_technical_indicators_pipeline as pipeline


class ComputeTechnicalIndicatorsPipelineTests(unittest.TestCase):
    def test_resolve_worker_count_caps_requested_workers(self):
        self.assertEqual(
            pipeline.resolve_worker_count(requested_workers=16, cpu_count=32, worker_cap=4),
            4,
        )

    def test_resolve_worker_count_caps_default_cpu_workers(self):
        self.assertEqual(pipeline.resolve_worker_count(cpu_count=32, worker_cap=2), 2)
        self.assertEqual(pipeline.resolve_worker_count(cpu_count=1, worker_cap=8), 1)

    def test_dataframe_ta_accessor_is_registered(self):
        self.assertTrue(hasattr(pd.DataFrame(), "ta"))

    def test_combine_outputs_runs_with_ta_accessor(self):
        frame = pd.DataFrame(
            {
                "open": list(range(1, 21)),
                "high": list(range(2, 22)),
                "low": [value - 0.5 for value in range(1, 21)],
                "close": [value + 0.5 for value in range(1, 21)],
                "volume": [10 * value for value in range(1, 21)],
            }
        )
        result = pipeline.combine_outputs(
            frame,
            [
                ("sma", {"length": 2}),
                ("cmf", {"length": 2}),
                ("cdl_pattern", {"name": pipeline.PATTERN_NAMES}),
            ],
        )
        self.assertIn("SMA_2", result.columns)
        self.assertIn("CMF_2", result.columns)
        self.assertIn("CDL_DOJI_10_0.1", result.columns)
        self.assertIn("CDL_HAMMER", result.columns)
        self.assertIn("CDL_PIERCING", result.columns)


if __name__ == "__main__":
    unittest.main()
