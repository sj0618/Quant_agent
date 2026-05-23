"""Run the full KIS official adjusted OHLCV + TA recomputation pipeline.

This wrapper intentionally runs the expensive steps sequentially:
1. collect KIS official adjusted OHLCV into ``feature.kis_adjusted_ohlcv_daily``;
2. recompute canonical adjusted OHLCV and all five TA category tables from that
   official adjusted input;
3. run data quality checks for KIS/KRX consistency and OHLCV anomalies;
4. run local regression tests.

It does not load ``.env`` files; credentials must already be present in the
process environment.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FULL_START_DATE = "2016-05-20"
DEFAULT_KIS_WORKERS = 4
DEFAULT_TA_WORKERS = 8
DEFAULT_REQUEST_WINDOW_DAYS = 120
DEFAULT_FLUSH_ROWS = 25_000
DEFAULT_ARTIFACT_DIR = ".omx/artifacts"
SUMMARY_FAILURE_KEYS = {
    "kis": ("failed_windows",),
    "ta": ("failed_tickers",),
    "qa": (),
}


def main() -> int:
    return run_pipeline(parse_args())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full KIS adjusted OHLCV ingestion and TA recomputation.")
    parser.add_argument(
        "--run-mode",
        choices=["full", "daily-incremental"],
        default=os.getenv("KIS_ADJUSTED_PIPELINE_MODE", "full"),
        help="full backfills the requested range; daily-incremental defaults to one target trade date.",
    )
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD. Full mode defaults to 2016-05-20.")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD. Defaults to today unless daily target-date is set.")
    parser.add_argument("--target-date", default=None, help="YYYY-MM-DD for daily-incremental runs.")
    parser.add_argument("--resume", action="store_true", help="Skip KIS/TA steps whose JSON summaries already succeeded.")
    parser.add_argument("--kis-workers", type=int, default=DEFAULT_KIS_WORKERS)
    parser.add_argument("--ta-workers", type=int, default=DEFAULT_TA_WORKERS)
    parser.add_argument("--request-window-days", type=int, default=DEFAULT_REQUEST_WINDOW_DAYS)
    parser.add_argument("--flush-rows", type=int, default=DEFAULT_FLUSH_ROWS)
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    return parser.parse_args(argv)


def run_pipeline(
    args: argparse.Namespace,
    *,
    run_step_func: Callable[[list[str], str], None] | None = None,
    today: date | None = None,
) -> int:
    run_step_func = run_step if run_step_func is None else run_step_func
    start_date, end_date, artifact_label = resolve_window(args, today=today)
    artifact_dir = ROOT / args.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    kis_output = artifact_dir / f"kis-adjusted-{artifact_label}.json"
    ta_output = artifact_dir / f"technical-indicators-kis-adjusted-{artifact_label}.json"
    qa_output = artifact_dir / f"data-quality-kis-adjusted-{artifact_label}.json"
    python_executable = resolve_python_executable()

    if args.resume and summary_is_successful(kis_output, start_date, end_date, SUMMARY_FAILURE_KEYS["kis"]):
        print(json.dumps({"step": "KIS official adjusted OHLCV ingestion", "status": "skipped_resume", "output": str(kis_output)}, ensure_ascii=False))
    else:
        run_step_func(
            [
                str(python_executable),
                "scripts/ingest_kis_adjusted_ohlcv.py",
                "--start-date",
                start_date,
                "--end-date",
                end_date,
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

    if args.resume and summary_is_successful(ta_output, start_date, end_date, SUMMARY_FAILURE_KEYS["ta"]):
        print(json.dumps({"step": "TA recomputation from KIS official adjusted OHLCV", "status": "skipped_resume", "output": str(ta_output)}, ensure_ascii=False))
    else:
        run_step_func(
            [
                str(python_executable),
                "scripts/compute_technical_indicators_pipeline.py",
                "--db-mode",
                "docker",
                "--start-date",
                start_date,
                "--end-date",
                end_date,
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

    if args.resume and summary_is_successful(qa_output, start_date, end_date, SUMMARY_FAILURE_KEYS["qa"]):
        print(json.dumps({"step": "Data quality checks for KIS adjusted pipeline", "status": "skipped_resume", "output": str(qa_output)}, ensure_ascii=False))
    else:
        run_step_func(
            [
                str(python_executable),
                "scripts/run_data_quality_checks.py",
                "--db-mode",
                "docker",
                "--start-date",
                start_date,
                "--end-date",
                end_date,
                "--checks",
                "all",
                "--output",
                str(qa_output),
            ],
            "Data quality checks for KIS adjusted pipeline",
        )

    run_step_func(
        [
            str(python_executable),
            "-m",
            "py_compile",
            "scripts/ingest_kis_adjusted_ohlcv.py",
            "scripts/compute_technical_indicators_pipeline.py",
            "scripts/run_kis_adjusted_full_pipeline.py",
            "scripts/run_data_quality_checks.py",
            "scripts/refresh_symbol_metadata.py",
            "quant_agent/data/config.py",
            "quant_agent/data/quality.py",
            "quant_agent/data/repository.py",
            "quant_agent/data/sources/kis.py",
        ],
        "py_compile",
    )
    run_step_func([str(python_executable), "-m", "pytest", "tests"], "pytest")

    print(
        json.dumps(
            {
                "status": "success",
                "kis_output": str(kis_output),
                "ta_output": str(ta_output),
                "qa_output": str(qa_output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def resolve_window(args: argparse.Namespace, *, today: date | None = None) -> tuple[str, str, str]:
    today = today or date.today()
    if args.run_mode == "daily-incremental":
        target = args.target_date or today.isoformat()
        start = args.start_date or target
        end = args.end_date or target
        label = f"daily-{end}"
    else:
        start = args.start_date or DEFAULT_FULL_START_DATE
        end = args.end_date or today.isoformat()
        label = "full"

    if date.fromisoformat(end) < date.fromisoformat(start):
        raise ValueError("--end-date must be greater than or equal to --start-date.")
    return start, end, label


def resolve_python_executable() -> Path:
    configured = os.getenv("QUANT_PIPELINE_PYTHON")
    if configured:
        return Path(configured)
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    return venv_python if venv_python.exists() else Path(sys.executable)


def summary_is_successful(path: Path, start_date: str, end_date: str, failure_keys: tuple[str, ...]) -> bool:
    if not path.exists():
        return False
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if summary.get("start_date") != start_date or summary.get("end_date") != end_date:
        return False
    return all(not summary.get(key) for key in failure_keys)


def run_step(command: list[str], label: str) -> None:
    print(json.dumps({"step": label, "command": command}, ensure_ascii=False), flush=True)
    completed = subprocess.run(command, cwd=ROOT, text=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
