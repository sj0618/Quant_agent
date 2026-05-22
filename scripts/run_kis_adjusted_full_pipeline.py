"""Run the full KIS official adjusted OHLCV + TA recomputation pipeline.

This wrapper intentionally runs the expensive steps sequentially:
1. collect KIS official adjusted OHLCV into ``feature.kis_adjusted_ohlcv_daily``;
2. recompute canonical adjusted OHLCV and all five TA category tables from that
   official adjusted input;
3. run local regression tests.

It does not load ``.env`` files; credentials must already be present in the
process environment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
DEFAULT_START_DATE = "2016-05-20"
DEFAULT_END_DATE = "2026-05-20"
DEFAULT_KIS_WORKERS = 4
DEFAULT_TA_WORKERS = 8
DEFAULT_REQUEST_WINDOW_DAYS = 120
DEFAULT_FLUSH_ROWS = 25_000


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full KIS adjusted OHLCV ingestion and TA recomputation.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--kis-workers", type=int, default=DEFAULT_KIS_WORKERS)
    parser.add_argument("--ta-workers", type=int, default=DEFAULT_TA_WORKERS)
    parser.add_argument("--request-window-days", type=int, default=DEFAULT_REQUEST_WINDOW_DAYS)
    parser.add_argument("--flush-rows", type=int, default=DEFAULT_FLUSH_ROWS)
    parser.add_argument("--artifact-dir", default=".omx/artifacts")
    args = parser.parse_args()

    artifact_dir = ROOT / args.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    kis_output = artifact_dir / "kis-adjusted-full.json"
    ta_output = artifact_dir / "technical-indicators-kis-adjusted-full.json"

    run_step(
        [
            str(PYTHON),
            "scripts/ingest_kis_adjusted_ohlcv.py",
            "--start-date",
            args.start_date,
            "--end-date",
            args.end_date,
            "--request-window-days",
            str(args.request_window_days),
            "--request-sleep-seconds",
            "0",
            "--workers",
            str(args.kis_workers),
            "--flush-rows",
            str(args.flush_rows),
            "--output",
            str(kis_output),
        ],
        "KIS official adjusted OHLCV ingestion",
    )

    kis_summary = json.loads(kis_output.read_text(encoding="utf-8"))
    if kis_summary.get("failed_windows"):
        print(json.dumps({"status": "stopped_before_ta", "kis_summary": kis_summary}, ensure_ascii=False, indent=2))
        return 2

    run_step(
        [
            str(PYTHON),
            "scripts/compute_technical_indicators_pipeline.py",
            "--db-mode",
            "docker",
            "--start-date",
            args.start_date,
            "--end-date",
            args.end_date,
            "--input-price-source",
            "kis-adjusted",
            "--workers",
            str(args.ta_workers),
            "--ticker-batch-size",
            "32",
            "--flush-rows",
            str(args.flush_rows),
            "--output",
            str(ta_output),
        ],
        "TA recomputation from KIS official adjusted OHLCV",
    )

    run_step(
        [
            str(PYTHON),
            "-m",
            "py_compile",
            "scripts/ingest_kis_adjusted_ohlcv.py",
            "scripts/compute_technical_indicators_pipeline.py",
            "quant_agent/data/config.py",
            "quant_agent/data/sources/kis.py",
        ],
        "py_compile",
    )
    run_step([str(PYTHON), "-m", "pytest", "tests"], "pytest")

    print(
        json.dumps(
            {
                "status": "success",
                "kis_output": str(kis_output),
                "ta_output": str(ta_output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def run_step(command: list[str], label: str) -> None:
    print(json.dumps({"step": label, "command": command}, ensure_ascii=False), flush=True)
    completed = subprocess.run(command, cwd=ROOT, text=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
