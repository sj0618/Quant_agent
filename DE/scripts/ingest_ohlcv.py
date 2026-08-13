"""Run OHLCV backfill or daily update ingestion.

Credentials are read only from process environment. This script does not load
``.env`` files.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import DatabaseConfig, OhlcvIngestionConfig  # noqa: E402
from quant_agent.data.db import make_executor  # noqa: E402
from quant_agent.data.ingestion import (  # noqa: E402
    KIS_ADJUSTED_INGESTION_SCRIPT,
    OhlcvIngestionRequest,
    OhlcvIngestionService,
)
from quant_agent.data.repository import DataRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest OHLCV raw/core data into PostgreSQL/TimescaleDB.")
    parser.add_argument(
        "--source",
        default=None,
        choices=["KRX", "krx"],
        help=f"Canonical raw/core ingestion source. KIS adjusted data uses {KIS_ADJUSTED_INGESTION_SCRIPT}.",
    )
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbols for KRX filtering.")
    parser.add_argument("--db-mode", choices=["psycopg", "docker"], default=None)
    parser.add_argument("--db-container", default=None)
    parser.add_argument("--dag-id", default="manual_ohlcv_ingestion")
    parser.add_argument("--task-id", default="ingest_ohlcv")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    ingestion_config = OhlcvIngestionConfig.from_env()
    source = (args.source or ingestion_config.primary_source).upper()
    db_config = DatabaseConfig.from_env()
    if args.db_mode or args.db_container:
        db_config = DatabaseConfig(
            **{
                **db_config.__dict__,
                "execution_mode": args.db_mode or db_config.execution_mode,
                "docker_container": args.db_container or db_config.docker_container,
            }
        )

    repository = DataRepository(make_executor(db_config))
    service = OhlcvIngestionService(repository=repository, ingestion_config=ingestion_config)
    result = service.ingest_range(
        OhlcvIngestionRequest(
            source=source,
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
            symbols=tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()),
            dag_id=args.dag_id,
            task_id=args.task_id,
        )
    )
    payload = {
        **asdict(result),
        "run_id": str(result.run_id),
        "start_date": result.start_date.isoformat(),
        "end_date": result.end_date.isoformat(),
        "quality_issues": [asdict(issue) for issue in result.quality_issues],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
