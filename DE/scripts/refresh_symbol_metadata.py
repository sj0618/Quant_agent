"""Refresh symbol lifecycle metadata from loaded OHLCV observations.

This script is intentionally DB-local. It does not call external APIs and does
not load ``.env`` files.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import DatabaseConfig  # noqa: E402
from quant_agent.data.repository import DataRepository  # noqa: E402


METADATA_SOURCE_ID = "QA"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    as_of_date = date.fromisoformat(args.as_of_date)
    db_config = DatabaseConfig.from_env()
    if args.db_mode:
        db_config = DatabaseConfig(**{**db_config.__dict__, "execution_mode": args.db_mode})
    repository = DataRepository(db_config=db_config)
    run_id = repository.start_ingestion_run(
        dag_id=args.dag_id,
        task_id=args.task_id,
        source_id=METADATA_SOURCE_ID,
        params={
            "as_of_date": as_of_date.isoformat(),
            "source_id": args.source_id,
            "purpose": "symbol_lifecycle_refresh",
        },
    )
    try:
        repository.refresh_symbol_lifecycle(run_id=run_id, as_of_date=as_of_date, source_id=args.source_id)
        repository.finish_ingestion_run(run_id, status="success")
    except Exception as exc:
        repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
        raise

    summary = {
        "run_id": str(run_id),
        "status": "success",
        "as_of_date": as_of_date.isoformat(),
        "source_id": args.source_id,
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh symbol listing/name lifecycle metadata from loaded OHLCV.")
    parser.add_argument("--as-of-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--source-id", default="KRX")
    parser.add_argument("--db-mode", choices=["docker", "psycopg"], default=None)
    parser.add_argument("--dag-id", default="manual_symbol_metadata_refresh")
    parser.add_argument("--task-id", default="refresh_symbol_metadata")
    parser.add_argument("--output", default=None)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
