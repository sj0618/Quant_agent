"""Backfill SEIBro analyst report summaries into TimescaleDB."""

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
from quant_agent.data.db import make_executor, sql_literal  # noqa: E402
from quant_agent.data.external import ExternalDataIngestionService  # noqa: E402
from quant_agent.data.repository import DataRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill SEIBro analyst report summaries.")
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--chunk-months", type=int, default=None)
    parser.add_argument("--page-size", type=int, default=None)
    parser.add_argument("--sleep-min-seconds", type=float, default=None)
    parser.add_argument("--sleep-max-seconds", type=float, default=None)
    parser.add_argument("--company-code", default="")
    parser.add_argument("--db-mode", choices=["psycopg", "docker"], default=None)
    parser.add_argument("--db-container", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--print-sample", type=int, default=0)
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
    repository = DataRepository(make_executor(db_config))
    service = ExternalDataIngestionService(repository=repository)
    summary = service.backfill_seibro_analyst_report_summaries(
        start_date=args.start_date,
        end_date=args.end_date,
        chunk_months=args.chunk_months,
        page_size=args.page_size,
        sleep_min_seconds=args.sleep_min_seconds,
        sleep_max_seconds=args.sleep_max_seconds,
        company_code=args.company_code,
    )
    if args.print_sample > 0:
        summary["sample_rows"] = _sample_rows(repository, args.start_date, args.end_date, args.print_sample)
    text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


def _sample_rows(repository: DataRepository, start_date: date, end_date: date, limit: int) -> list[dict[str, object]]:
    return repository.executor.fetch_json(
        f"""
        SELECT report_date, ticker, company_name, left(summary, 160) AS summary_preview,
               opinion, target_price, close_price, institution, author
          FROM raw.analyst_report_summary
         WHERE report_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
         ORDER BY report_date DESC, ticker, institution, author
         LIMIT {int(limit)}
        """
    )


if __name__ == "__main__":
    raise SystemExit(main())
