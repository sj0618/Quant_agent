"""Run SEIBro/BOK/OpenDART/KIND ingestion jobs."""

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
    parser = argparse.ArgumentParser(description="Ingest external macro/financial/report data.")
    parser.add_argument(
        "--job",
        required=True,
        choices=["bok-series", "dart-corp-codes", "dart-financial", "kind-sector", "seibro-reports"],
    )
    parser.add_argument("--db-mode", choices=["psycopg", "docker"], default=None)
    parser.add_argument("--db-container", default=None)
    parser.add_argument("--output", default=None)

    parser.add_argument("--stat-code")
    parser.add_argument("--cycle")
    parser.add_argument("--start-period")
    parser.add_argument("--end-period")
    parser.add_argument("--item-code1", default="?")

    parser.add_argument("--symbol")
    parser.add_argument("--corp-code")
    parser.add_argument("--business-year", type=int)
    parser.add_argument("--report-code")
    parser.add_argument("--fs-div", default="CFS")
    parser.add_argument("--period-end")

    parser.add_argument("--seibro-endpoint")
    parser.add_argument("--seibro-param", action="append", default=[], help="key=value, repeatable")
    parser.add_argument("--as-of-date")
    parser.add_argument("--universe-min-score", type=float, default=0.0)
    parser.add_argument("--universe-min-reports", type=int, default=1)
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

    if args.job == "bok-series":
        _require(args, "stat_code", "cycle", "start_period", "end_period")
        count = service.ingest_bok_series(
            stat_code=args.stat_code,
            cycle=args.cycle,
            start_period=args.start_period,
            end_period=args.end_period,
            item_code1=args.item_code1,
        )
    elif args.job == "dart-corp-codes":
        count = service.ingest_dart_corp_codes()
    elif args.job == "dart-financial":
        _require(args, "symbol", "corp_code", "business_year", "report_code")
        count = service.ingest_dart_financial_statement(
            symbol=args.symbol,
            corp_code=args.corp_code,
            business_year=args.business_year,
            report_code=args.report_code,
            fs_div=args.fs_div,
            period_end=date.fromisoformat(args.period_end) if args.period_end else None,
        )
    elif args.job == "kind-sector":
        count = service.ingest_kind_sector_snapshot(
            as_of_date=date.fromisoformat(args.as_of_date) if args.as_of_date else None,
        )
    else:
        _require(args, "seibro_endpoint", "as_of_date")
        count = service.ingest_seibro_reports(
            endpoint_path=args.seibro_endpoint,
            params=_parse_key_value(args.seibro_param),
            as_of_date=date.fromisoformat(args.as_of_date),
            universe_min_score=args.universe_min_score,
            universe_min_reports=args.universe_min_reports,
        )

    text = json.dumps({"job": args.job, "written": count}, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


def _require(args: argparse.Namespace, *names: str) -> None:
    missing = [name for name in names if getattr(args, name) in (None, "")]
    if missing:
        raise SystemExit(f"Missing required option(s) for job {args.job}: {', '.join('--' + name.replace('_', '-') for name in missing)}")


def _parse_key_value(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"Invalid --seibro-param value: {item}. Expected key=value.")
        key, value = item.split("=", 1)
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
