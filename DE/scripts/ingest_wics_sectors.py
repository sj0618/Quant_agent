"""One-time WICS sector snapshot ingestion for listed common stocks."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import DatabaseConfig  # noqa: E402
from quant_agent.data.db import make_executor  # noqa: E402
from quant_agent.data.external import ExternalDataIngestionService  # noqa: E402
from quant_agent.data.repository import DataRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest WICS sector snapshots for listed common stocks.")
    parser.add_argument("--db-mode", choices=["psycopg", "docker"], default=None)
    parser.add_argument("--db-container", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--as-of-date")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    db_config = DatabaseConfig.from_env()
    if args.db_mode or args.db_container:
        db_config = DatabaseConfig(
            **{
                **db_config.__dict__,
                "execution_mode": args.db_mode or db_config.execution_mode,
                "docker_container": args.db_container or db_config.docker_container,
            }
        )

    service = ExternalDataIngestionService(repository=DataRepository(make_executor(db_config)))
    count = service.ingest_wics_sector_snapshot(
        as_of_date=date.fromisoformat(args.as_of_date) if args.as_of_date else None,
        max_workers=args.workers,
        symbol_limit=args.limit,
    )

    text = json.dumps({"job": "wics-sector", "written": count}, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
