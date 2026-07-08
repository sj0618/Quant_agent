"""Compute and store TA-Lib indicators for an OHLCV date window."""

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
from quant_agent.data.indicators.service import TechnicalIndicatorService  # noqa: E402
from quant_agent.data.repository import DataRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute TA-Lib indicators and store category JSONB rows.")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbols.")
    parser.add_argument("--db-mode", choices=["psycopg", "docker"], default=None)
    parser.add_argument("--db-container", default=None)
    parser.add_argument("--output", default=None)
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

    service = TechnicalIndicatorService(repository=DataRepository(make_executor(db_config)))
    counts = service.compute_and_store(
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        symbols=[symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()] or None,
    )
    text = json.dumps({"stored_rows": counts}, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
