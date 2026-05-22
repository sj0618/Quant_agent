import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

from scripts import run_kis_adjusted_full_pipeline as wrapper


class KisAdjustedPipelineWrapperTests(unittest.TestCase):
    def test_daily_incremental_defaults_to_single_target_date(self):
        args = wrapper.parse_args(["--run-mode", "daily-incremental", "--target-date", "2026-05-21"])

        self.assertEqual(
            wrapper.resolve_window(args, today=date(2026, 5, 22)),
            ("2026-05-21", "2026-05-21", "daily-2026-05-21"),
        )

    def test_resume_skips_completed_kis_and_runs_ta_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            (artifact_dir / "kis-adjusted-daily-2026-05-21.json").write_text(
                json.dumps(
                    {
                        "start_date": "2026-05-21",
                        "end_date": "2026-05-21",
                        "failed_windows": [],
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            def fake_run_step(command, label):
                calls.append((label, command))
                if label == "TA recomputation from KIS official adjusted OHLCV":
                    (artifact_dir / "technical-indicators-kis-adjusted-daily-2026-05-21.json").write_text(
                        json.dumps(
                            {
                                "start_date": "2026-05-21",
                                "end_date": "2026-05-21",
                                "failed_tickers": [],
                            }
                        ),
                        encoding="utf-8",
                    )

            args = wrapper.parse_args(
                [
                    "--run-mode",
                    "daily-incremental",
                    "--target-date",
                    "2026-05-21",
                    "--resume",
                    "--artifact-dir",
                    str(artifact_dir),
                ]
            )

            self.assertEqual(wrapper.run_pipeline(args, run_step_func=fake_run_step, today=date(2026, 5, 22)), 0)

        labels = [label for label, _ in calls]
        self.assertNotIn("KIS official adjusted OHLCV ingestion", labels)
        self.assertEqual(
            labels,
            ["TA recomputation from KIS official adjusted OHLCV", "py_compile", "pytest"],
        )

    def test_resume_does_not_skip_failed_kis_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            output = artifact_dir / "kis-adjusted-daily-2026-05-21.json"
            output.write_text(
                json.dumps(
                    {
                        "start_date": "2026-05-21",
                        "end_date": "2026-05-21",
                        "failed_windows": [{"ticker": "005930"}],
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            def fake_run_step(command, label):
                calls.append((label, command))
                if label == "KIS official adjusted OHLCV ingestion":
                    output.write_text(
                        json.dumps(
                            {
                                "start_date": "2026-05-21",
                                "end_date": "2026-05-21",
                                "failed_windows": [],
                            }
                        ),
                        encoding="utf-8",
                    )
                if label == "TA recomputation from KIS official adjusted OHLCV":
                    (artifact_dir / "technical-indicators-kis-adjusted-daily-2026-05-21.json").write_text(
                        json.dumps(
                            {
                                "start_date": "2026-05-21",
                                "end_date": "2026-05-21",
                                "failed_tickers": [],
                            }
                        ),
                        encoding="utf-8",
                    )

            args = wrapper.parse_args(
                [
                    "--run-mode",
                    "daily-incremental",
                    "--target-date",
                    "2026-05-21",
                    "--resume",
                    "--artifact-dir",
                    str(artifact_dir),
                ]
            )

            self.assertEqual(wrapper.run_pipeline(args, run_step_func=fake_run_step, today=date(2026, 5, 22)), 0)

        labels = [label for label, _ in calls]
        self.assertIn("KIS official adjusted OHLCV ingestion", labels)


if __name__ == "__main__":
    unittest.main()
