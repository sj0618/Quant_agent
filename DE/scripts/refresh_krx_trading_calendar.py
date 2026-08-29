"""Refresh KRX trading-calendar evidence without writing OHLCV rows."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import DatabaseConfig, KrxConfig, OhlcvIngestionConfig  # noqa: E402
from quant_agent.data.db import make_executor  # noqa: E402
from quant_agent.data.repository import DataRepository  # noqa: E402
from quant_agent.data.sources.krx import KrxOhlcvClient  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise ValueError("--end-date must be greater than or equal to --start-date.")

    db_config = DatabaseConfig.from_env()
    if args.db_mode:
        db_config = DatabaseConfig(**{**db_config.__dict__, "execution_mode": args.db_mode})
    repository = DataRepository(make_executor(db_config))
    client = KrxOhlcvClient(KrxConfig.from_env())
    ingestion_config = OhlcvIngestionConfig.from_env()
    run_id = repository.start_ingestion_run(
        dag_id=args.dag_id,
        task_id=args.task_id,
        source_id="KRX",
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "batch_days": ingestion_config.batch_days,
            "purpose": "trading_calendar_evidence",
        },
    )

    raw_payloads_written = 0
    calendar_rows = 0
    try:
        for chunk_start, chunk_end in _chunk_dates(start_date, end_date, ingestion_config.batch_days):
            payloads = []
            observed_open_dates: set[date] = set()
            current = chunk_start
            while current <= chunk_end:
                daily_payloads = client.fetch_market_day_payloads(current)
                payloads.extend(daily_payloads)
                if any(
                    isinstance(payload.payload.get("OutBlock_1"), list) and bool(payload.payload.get("OutBlock_1"))
                    for payload in daily_payloads
                ):
                    observed_open_dates.add(current)
                current += timedelta(days=1)
            raw_payloads_written += repository.store_raw_payloads(payloads, run_id)
            calendar_rows += repository.upsert_trading_calendar_observations(
                start_date=chunk_start,
                end_date=chunk_end,
                observed_open_dates=observed_open_dates,
                run_id=run_id,
            )
        repository.finish_ingestion_run(run_id, status="success")
    except Exception as exc:
        repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
        raise

    summary = {
        "run_id": str(run_id),
        "source": "KRX",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "calendar_rows": calendar_rows,
        "raw_payloads_written": raw_payloads_written,
        "unconfirmed_weekdays_are_not_marked_closed": True,
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh KRX trading-calendar evidence.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--db-mode", choices=["psycopg", "docker"], default=None)
    parser.add_argument("--dag-id", default="quant_agent_krx_calendar_refresh")
    parser.add_argument("--task-id", default="refresh_krx_trading_calendar")
    parser.add_argument("--output", default=None)
    return parser.parse_args(argv)


def _chunk_dates(start_date: date, end_date: date, chunk_days: int):
    if chunk_days < 1:
        raise ValueError("batch_days must be >= 1.")
    current = start_date
    while current <= end_date:
        chunk_end = min(end_date, current + timedelta(days=chunk_days - 1))
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


if __name__ == "__main__":
    raise SystemExit(main())
