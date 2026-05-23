"""Apply and verify symbol security_type classification in the local DB.

This script is DB-local. It does not call external APIs and does not load
``.env`` files; database connection settings come from the process environment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import DatabaseConfig  # noqa: E402
from quant_agent.data.db import make_executor  # noqa: E402


DEFAULT_MIGRATION_PATH = ROOT / "migrations" / "006_symbol_security_type_classification.sql"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    db_config = DatabaseConfig.from_env()
    if args.db_mode:
        db_config = DatabaseConfig(**{**db_config.__dict__, "execution_mode": args.db_mode})

    executor = make_executor(db_config)
    if not args.verify_only:
        migration_path = Path(args.migration_path)
        executor.execute_script(migration_path.read_text(encoding="utf-8"))

    summary = {
        "security_type_counts": executor.fetch_json(
            """
            SELECT security_type, COUNT(*)::int AS symbol_count
              FROM core.symbol_master
             GROUP BY security_type
             ORDER BY security_type
            """
        ),
        "null_security_type_count": executor.fetch_json(
            """
            SELECT COUNT(*)::int AS null_count
              FROM core.symbol_master
             WHERE security_type IS NULL
            """
        )[0]["null_count"],
        "common_stock_universe_count": executor.fetch_json(
            """
            SELECT COUNT(*)::int AS symbol_count
              FROM meta.view_common_stock_universe
            """
        )[0]["symbol_count"],
        "invalid_common_stock_universe_count": executor.fetch_json(
            """
            SELECT COUNT(*)::int AS invalid_count
              FROM meta.view_common_stock_universe
             WHERE market_segment NOT IN ('KOSPI', 'KOSDAQ')
                OR security_type <> 'common_stock'
                OR listing_status <> 'listed'
            """
        )[0]["invalid_count"],
    }

    if summary["null_security_type_count"] != 0:
        raise RuntimeError(f"security_type still has NULL rows: {summary['null_security_type_count']}")
    if summary["invalid_common_stock_universe_count"] != 0:
        raise RuntimeError(
            "meta.view_common_stock_universe contains rows outside KOSPI/KOSDAQ common_stock: "
            f"{summary['invalid_common_stock_universe_count']}"
        )

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify and verify core.symbol_master security_type values.")
    parser.add_argument("--db-mode", choices=["docker", "psycopg"], default=None)
    parser.add_argument("--migration-path", default=str(DEFAULT_MIGRATION_PATH))
    parser.add_argument("--verify-only", action="store_true", help="Skip migration execution and only run verification queries.")
    parser.add_argument("--output", default=None, help="Optional JSON summary output path.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
