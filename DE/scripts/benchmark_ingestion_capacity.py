"""Benchmark ingestion normalization and failed-record resume control flow.

This benchmark measures a local deterministic transformation and recovery path only;
it is not a PostgreSQL capacity or production freshness claim.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from quant_agent.data.sources.krx import normalize_krx_market_day
from scripts.run_kis_adjusted_full_pipeline import summary_is_successful

BENCHMARK_SCHEMA_VERSION = "ingestion-capacity-benchmark.v1"
BENCHMARK_SOURCE = "synthetic_normalizer_workload"
RECOVERY_FAILURE_KEYS = ("failed_windows",)


def run_capacity_benchmark(*, rows: int, as_of: date) -> dict[str, Any]:
    if rows < 1:
        raise ValueError("rows must be >= 1")
    payload = _benchmark_payload(rows=rows, as_of=as_of)
    started = perf_counter()
    normalized = normalize_krx_market_day(payload)
    elapsed_seconds = perf_counter() - started
    recovery = _benchmark_failed_record_recovery(as_of=as_of)
    generated_at = datetime.now(UTC).isoformat()
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "execution_scope": "local_normalizer_and_resume_control_flow",
        "source": BENCHMARK_SOURCE,
        "load": {
            "rows_requested": rows,
            "rows_normalized": len(normalized),
            "elapsed_seconds": elapsed_seconds,
            "rows_per_second": len(normalized) / elapsed_seconds if elapsed_seconds else None,
        },
        "freshness": {
            "input_as_of": as_of.isoformat(),
            "artifact_generated_at": generated_at,
            "status": "measured_local_only",
        },
        "recovery": recovery,
    }


def _benchmark_payload(*, rows: int, as_of: date) -> dict[str, Any]:
    return {
        "OutBlock_1": [
            {
                "BAS_DD": as_of.isoformat().replace("-", ""),
                "ISU_CD": f"{index:06d}",
                "ISU_NM": f"benchmark-{index:06d}",
                "TDD_OPNPRC": "100",
                "TDD_HGPRC": "101",
                "TDD_LWPRC": "99",
                "TDD_CLSPRC": "100",
                "ACC_TRDVOL": "1000",
            }
            for index in range(rows)
        ]
    }


def _benchmark_failed_record_recovery(*, as_of: date) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="quant-agent-recovery-") as temporary_directory:
        summary_path = Path(temporary_directory) / "failed-record-summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "start_date": as_of.isoformat(),
                    "end_date": as_of.isoformat(),
                    "failed_windows": [{"record": "benchmark-record"}],
                }
            ),
            encoding="utf-8",
        )
        failed_before_resume = not summary_is_successful(
            summary_path,
            as_of.isoformat(),
            as_of.isoformat(),
            RECOVERY_FAILURE_KEYS,
        )
        summary_path.write_text(
            json.dumps(
                {
                    "start_date": as_of.isoformat(),
                    "end_date": as_of.isoformat(),
                    "failed_windows": [],
                }
            ),
            encoding="utf-8",
        )
        recovered_after_resume = summary_is_successful(
            summary_path,
            as_of.isoformat(),
            as_of.isoformat(),
            RECOVERY_FAILURE_KEYS,
        )
    return {
        "failed_records_before_resume": int(failed_before_resume),
        "recovered_records_after_resume": int(recovered_after_resume),
        "recovery_status": "pass" if failed_before_resume and recovered_after_resume else "fail",
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark local ingestion capacity and resume recovery")
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_capacity_benchmark(rows=args.rows, as_of=date.fromisoformat(args.as_of))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["recovery"]["recovery_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
