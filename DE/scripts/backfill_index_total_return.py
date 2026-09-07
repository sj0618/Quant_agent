"""Load official KRX total-return index levels and the monthly benchmark split.

Fills the two tables ``DE/migrations/013_krx_official_benchmark_tr.sql`` creates, which
the AI backtest's primary benchmark reads through ``mart.krx_index_total_return_daily``
and ``mart.krx_benchmark_monthly_weights``.

Both writes are idempotent upserts, so the same range can be replayed and the daily DAG
can run the same script over a short trailing window.

    python3 scripts/backfill_index_total_return.py --start-date 2016-05-20 --end-date 2026-09-04
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import BokConfig, DatabaseConfig, KisConfig  # noqa: E402
from quant_agent.data.db import make_executor  # noqa: E402
from quant_agent.data.repository import DataRepository  # noqa: E402
from quant_agent.data.sources.bok import BokEcosClient  # noqa: E402
from quant_agent.data.sources.krx_index import (  # noqa: E402
    ECOS_MARKET_CAP_ITEMS,
    ECOS_MARKET_CAP_STAT_CODE,
    INDEX_CODE_TO_KIS_SECTOR,
    MARKET_CAP_WEIGHT_BASIS,
    KrxIndexTotalReturnClient,
    benchmark_weight_rows,
    normalize_ecos_market_caps,
    normalize_index_total_return,
)

# ECOS publishes 901Y014 about six weeks after month end, but the AI needs the previous
# month's split for the *current* trading month or the benchmark is unavailable. For
# those still-unpublished months only, the split is recomputed from warehouse closes and
# labelled with a different basis so the substitution stays visible in the table.
WAREHOUSE_WEIGHT_BASIS = "warehouse_month_end_close_times_listed_shares"
DEFAULT_REQUEST_SLEEP_SECONDS = 0.35


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

    run_id = repository.start_ingestion_run(
        dag_id=args.dag_id,
        task_id=args.task_id,
        source_id="KRX",
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "index_codes": sorted(INDEX_CODE_TO_KIS_SECTOR),
            "purpose": "official_krx_total_return_benchmark",
            "level_vendor": "KIS inquire-daily-indexchartprice",
            "weight_source": f"ECOS {ECOS_MARKET_CAP_STAT_CODE}",
        },
    )

    summary: dict[str, Any] = {"levels": {}, "weights": {}}
    try:
        levels_written = _load_levels(
            repository,
            run_id,
            start_date=start_date,
            end_date=end_date,
            sleep_seconds=args.sleep_seconds,
            summary=summary,
        )
        weights_written = _load_weights(
            repository,
            run_id,
            start_date=start_date,
            end_date=end_date,
            summary=summary,
        )
        repository.finish_ingestion_run(run_id, status="success")
    except Exception as error:  # noqa: BLE001 - the run row must record the failure.
        repository.finish_ingestion_run(run_id, status="failed", error_message=str(error))
        raise

    print(
        json.dumps(
            {
                "run_id": str(run_id),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "tr_level_rows": levels_written,
                "weight_rows": weights_written,
                **summary,
            },
            ensure_ascii=False,
            default=str,
        )
    )
    return 0


def _load_levels(
    repository: DataRepository,
    run_id: Any,
    *,
    start_date: date,
    end_date: date,
    sleep_seconds: float,
    summary: dict[str, Any],
) -> int:
    client = KrxIndexTotalReturnClient(KisConfig.from_env(), page_sleep_seconds=sleep_seconds)
    written = 0
    for index_code in sorted(INDEX_CODE_TO_KIS_SECTOR):
        rows: dict[date, dict[str, Any]] = {}
        for payload in client.fetch_index_payloads(index_code, start_date, end_date):
            for row in normalize_index_total_return(
                payload.payload,
                index_code=index_code,
                start_date=start_date,
                end_date=end_date,
            ):
                rows[row["trade_date"]] = row
        ordered = [rows[key] for key in sorted(rows)]
        written += repository.upsert_index_total_return(ordered, run_id)
        summary["levels"][index_code] = {
            "rows": len(ordered),
            "first": ordered[0]["trade_date"].isoformat() if ordered else None,
            "last": ordered[-1]["trade_date"].isoformat() if ordered else None,
        }
    return written


def _load_weights(
    repository: DataRepository,
    run_id: Any,
    *,
    start_date: date,
    end_date: date,
    summary: dict[str, Any],
) -> int:
    # One month before the window start: the first trading month rebalances on it.
    first_month = _add_months(start_date.replace(day=1), -1)
    last_month = end_date.replace(day=1)

    client = BokEcosClient(BokConfig.from_env())
    market_caps: dict[str, dict[str, Any]] = {}
    for market, item_code in ECOS_MARKET_CAP_ITEMS.items():
        payload = client.fetch_statistic_search(
            stat_code=ECOS_MARKET_CAP_STAT_CODE,
            cycle="M",
            start_period=first_month.strftime("%Y%m"),
            end_period=last_month.strftime("%Y%m"),
            item_code1=item_code,
        )
        market_caps[market] = normalize_ecos_market_caps(payload.payload, market=market)

    rows = benchmark_weight_rows(
        market_caps["KOSPI"], market_caps["KOSDAQ"], basis=MARKET_CAP_WEIGHT_BASIS
    )
    published = {row["month"] for row in rows}
    summary["weights"]["ecos_months"] = len(rows)
    summary["weights"]["ecos_last_month"] = (
        max(published).isoformat() if published else None
    )

    missing = [
        month
        for month in _months_between(first_month, last_month)
        if month not in published
    ]
    fallback_rows = (
        _warehouse_weight_rows(repository, missing) if missing else []
    )
    summary["weights"]["warehouse_fallback_months"] = [
        row["month"].isoformat() for row in fallback_rows
    ]
    summary["weights"]["unresolved_months"] = sorted(
        month.isoformat()
        for month in set(missing) - {row["month"] for row in fallback_rows}
    )
    return repository.upsert_index_benchmark_weights(rows + fallback_rows, run_id)


def _warehouse_weight_rows(
    repository: DataRepository, months: Sequence[date]
) -> list[dict[str, Any]]:
    if not months:
        return []
    observed = repository.fetch_month_end_market_caps(
        start_month=min(months), end_month=max(months)
    )
    wanted = set(months)
    by_month: dict[date, dict[str, Any]] = {}
    for row in observed:
        month = _as_date(row["month"])
        if month in wanted:
            by_month.setdefault(month, {})[str(row["market"])] = row["market_cap"]
    return benchmark_weight_rows(
        {
            month.strftime("%Y%m"): caps["KOSPI"]
            for month, caps in by_month.items()
            if caps.get("KOSPI") and caps.get("KOSDAQ")
        },
        {
            month.strftime("%Y%m"): caps["KOSDAQ"]
            for month, caps in by_month.items()
            if caps.get("KOSPI") and caps.get("KOSDAQ")
        },
        basis=WAREHOUSE_WEIGHT_BASIS,
    )


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _add_months(anchor: date, months: int) -> date:
    total = anchor.year * 12 + (anchor.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def _months_between(first: date, last: date) -> list[date]:
    months: list[date] = []
    cursor = first
    while cursor <= last:
        months.append(cursor)
        cursor = _add_months(cursor, 1)
    return months


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default_end = date.today()
    parser.add_argument("--start-date", default=(default_end - timedelta(days=30)).isoformat())
    parser.add_argument("--end-date", default=default_end.isoformat())
    parser.add_argument("--dag-id", default="manual")
    parser.add_argument("--task-id", default="backfill_index_total_return")
    parser.add_argument("--db-mode", default=None, choices=["psycopg", "docker"])
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_REQUEST_SLEEP_SECONDS)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
