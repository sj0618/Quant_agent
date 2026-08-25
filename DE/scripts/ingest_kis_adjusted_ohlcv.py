"""Collect KIS official adjusted OHLCV and store it in TimescaleDB.

KIS ``inquire-daily-itemchartprice`` uses ``FID_ORG_ADJ_PRC=0`` for adjusted
prices and returns at most 100 rows per request in the official sample code.
This script therefore slices long windows and stores adjusted rows separately
from the KRX-sourced ``core.ohlcv_daily`` table.

Secrets are read only from process environment. This script never loads
``.env`` files.

Database access auto-detects ``psycopg`` when ``QUANT_DB_DSN`` /
``DATABASE_URL`` or ``QUANT_DB_PASSWORD`` is present; otherwise the local
Docker container path is used. Pass ``--db-mode docker`` or
``--db-mode psycopg`` to force a mode explicitly.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import csv
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock
import time
from typing import Any, Iterable, Protocol
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import DatabaseConfig, KisConfig  # noqa: E402
from quant_agent.data.db import PsycopgScriptClient, resolve_execution_mode  # noqa: E402
from quant_agent.data.models import ApiRequestLog  # noqa: E402
from quant_agent.data.sources.kis import KisOhlcvClient, normalize_kis_daily_price  # noqa: E402


KIS_ADJUSTED_TABLE = "feature.kis_adjusted_ohlcv_daily"
KIS_SOURCE_ID = "KIS"
KIS_ADJUSTED_CURSOR_DATASET = "kis_adjusted_ohlcv_daily"
KIS_ADJUSTED_COMPLETED_WINDOW_CURSOR_PREFIX = "completed_window"
DEFAULT_REQUEST_WINDOW_DAYS = 120
DEFAULT_REQUEST_SLEEP_SECONDS = 0.25
DEFAULT_FLUSH_ROWS = 10_000
DEFAULT_TOKEN_RETRY_WAIT_SECONDS = 65
DEFAULT_INCREMENTAL_LOOKBACK_DAYS = 0
KIS_ADJUSTED_TRANSFORM_VERSION = "kis-adjusted-normalize-v1"


@dataclass(frozen=True)
class FetchWindow:
    start_date: date
    end_date: date


class KisDbClient(Protocol):
    def execute(self, sql: str) -> str:
        ...

    def fetch_csv(self, query: str, parse_dates: list[str] | None = None) -> list[dict[str, Any]]:
        ...

    def copy_adjusted_rows(self, rows: list[dict[str, Any]], run_id: str) -> None:
        ...

    def copy_api_request_logs(self, events: list[ApiRequestLog], run_id: str) -> None:
        ...


class DockerPsqlClient:
    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config

    def _base_command(self) -> list[str]:
        return [
            "docker",
            "exec",
            "-i",
            self.config.docker_container,
            "psql",
            "-U",
            self.config.user,
            "-d",
            self.config.database,
            "-v",
            "ON_ERROR_STOP=1",
        ]

    def execute(self, sql: str) -> str:
        completed = subprocess.run(
            self._base_command(),
            input=sql,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        return completed.stdout

    def fetch_csv(self, query: str, parse_dates: list[str] | None = None) -> list[dict[str, Any]]:
        sql = f"COPY ({query.rstrip().rstrip(';')}) TO STDOUT WITH (FORMAT csv, HEADER true);"
        text = self.execute(sql)
        if not text.strip():
            return []
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]

    def copy_adjusted_rows(self, rows: list[dict[str, Any]], run_id: str) -> None:
        if not rows:
            return

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer, lineterminator="\n")
        for row in rows:
            writer.writerow(
                [
                    row["time"],
                    row["ticker"],
                    row["adj_open"],
                    row["adj_high"],
                    row["adj_low"],
                    row["adj_close"],
                    row["adj_volume"],
                    row.get("mod_yn"),
                    row.get("revision_reason"),
                    json.dumps(row.get("raw", {}), ensure_ascii=False, separators=(",", ":"), default=str),
                    json.dumps(row.get("quality_flags", {}), ensure_ascii=False, separators=(",", ":"), default=str),
                    run_id,
                ]
            )

        sql = f"""
BEGIN;
CREATE TEMP TABLE tmp_kis_adjusted_ohlcv (
  "time" DATE,
  ticker TEXT,
  adj_open NUMERIC(20, 6),
  adj_high NUMERIC(20, 6),
  adj_low NUMERIC(20, 6),
  adj_close NUMERIC(20, 6),
  adj_volume NUMERIC(28, 6),
  mod_yn TEXT,
  revision_reason TEXT,
  raw_payload_jsonb JSONB,
  quality_flags JSONB,
  run_id UUID
) ON COMMIT DROP;
COPY tmp_kis_adjusted_ohlcv
  ("time", ticker, adj_open, adj_high, adj_low, adj_close, adj_volume, mod_yn, revision_reason,
   raw_payload_jsonb, quality_flags, run_id)
FROM STDIN WITH (FORMAT csv);
{csv_buffer.getvalue()}\\.
INSERT INTO {KIS_ADJUSTED_TABLE}
  ("time", ticker, adj_open, adj_high, adj_low, adj_close, adj_volume, mod_yn, revision_reason,
   raw_payload_jsonb, quality_flags, run_id)
SELECT "time", ticker, adj_open, adj_high, adj_low, adj_close, adj_volume, mod_yn, revision_reason,
       raw_payload_jsonb, quality_flags, run_id
  FROM tmp_kis_adjusted_ohlcv
ON CONFLICT ("time", ticker) DO UPDATE SET
  adj_open = EXCLUDED.adj_open,
  adj_high = EXCLUDED.adj_high,
  adj_low = EXCLUDED.adj_low,
  adj_close = EXCLUDED.adj_close,
  adj_volume = EXCLUDED.adj_volume,
  mod_yn = EXCLUDED.mod_yn,
  revision_reason = EXCLUDED.revision_reason,
  raw_payload_jsonb = EXCLUDED.raw_payload_jsonb,
  quality_flags = EXCLUDED.quality_flags,
  run_id = EXCLUDED.run_id,
  updated_at = now();
INSERT INTO meta.lineage_event
  (target_table, target_key, source_table, source_key, run_id, transform_version, metadata_jsonb)
SELECT
  {sql_literal(KIS_ADJUSTED_TABLE)},
  ticker || ':' || "time"::text,
  'kis_api.inquire_daily_itemchartprice',
  ticker || ':' || "time"::text || ':fid_org_adj_prc=0',
  run_id,
  {sql_literal(KIS_ADJUSTED_TRANSFORM_VERSION)},
  jsonb_build_object(
    'stage', 'kis_adjusted_ingestion',
    'adjusted_price_method', 'kis_official_adjusted',
    'fid_org_adj_prc', '0'
  )
FROM tmp_kis_adjusted_ohlcv;
COMMIT;
"""
        self.execute(sql)

    def copy_api_request_logs(self, events: list[ApiRequestLog], run_id: str) -> None:
        if not events:
            return
        values = []
        for event in events:
            values.append(
                "("
                f"{sql_literal(run_id)}, {sql_literal(event.source_id)}, {sql_literal(event.endpoint_key)}, "
                f"{sql_literal(stable_hash(event.request))}, {sql_literal(event.success)}, {sql_literal(event.status_code)}, "
                f"{sql_literal(event.elapsed_ms)}, {sql_literal(event.retry_count)}, "
                f"{sql_literal(stable_hash(event.response) if event.response is not None else None)}, "
                f"{sql_literal(truncate(event.error_message, 4000))}, {jsonb_literal(event.metadata)}, "
                f"{sql_literal(event.request_started_at.isoformat())}"
                ")"
            )
        self.execute(
            f"""
            INSERT INTO meta.api_request_log
              (run_id, source_id, endpoint_key, request_hash, success, status_code,
               elapsed_ms, retry_count, response_hash, error_message, metadata_jsonb, request_started_at)
            VALUES {", ".join(values)};
            """
        )


class PsycopgClient(PsycopgScriptClient):
    def fetch_csv(self, query: str, parse_dates: list[str] | None = None) -> list[dict[str, Any]]:
        text = self.fetch_csv_text(query)
        if not text.strip():
            return []
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]

    def copy_adjusted_rows(self, rows: list[dict[str, Any]], run_id: str) -> None:
        if not rows:
            return

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer, lineterminator="\n")
        for row in rows:
            writer.writerow(
                [
                    row["time"],
                    row["ticker"],
                    row["adj_open"],
                    row["adj_high"],
                    row["adj_low"],
                    row["adj_close"],
                    row["adj_volume"],
                    row.get("mod_yn"),
                    row.get("revision_reason"),
                    json.dumps(row.get("raw", {}), ensure_ascii=False, separators=(",", ":"), default=str),
                    json.dumps(row.get("quality_flags", {}), ensure_ascii=False, separators=(",", ":"), default=str),
                    run_id,
                ]
            )

        self.execute_copy_csv(
            """
            CREATE TEMP TABLE tmp_kis_adjusted_ohlcv (
              "time" DATE,
              ticker TEXT,
              adj_open NUMERIC(20, 6),
              adj_high NUMERIC(20, 6),
              adj_low NUMERIC(20, 6),
              adj_close NUMERIC(20, 6),
              adj_volume NUMERIC(28, 6),
              mod_yn TEXT,
              revision_reason TEXT,
              raw_payload_jsonb JSONB,
              quality_flags JSONB,
              run_id UUID
            ) ON COMMIT DROP;
            """,
            """
            COPY tmp_kis_adjusted_ohlcv
              ("time", ticker, adj_open, adj_high, adj_low, adj_close, adj_volume, mod_yn, revision_reason,
               raw_payload_jsonb, quality_flags, run_id)
            FROM STDIN WITH (FORMAT csv)
            """,
            csv_buffer.getvalue(),
            f"""
            INSERT INTO {KIS_ADJUSTED_TABLE}
              ("time", ticker, adj_open, adj_high, adj_low, adj_close, adj_volume, mod_yn, revision_reason,
               raw_payload_jsonb, quality_flags, run_id)
            SELECT "time", ticker, adj_open, adj_high, adj_low, adj_close, adj_volume, mod_yn, revision_reason,
                   raw_payload_jsonb, quality_flags, run_id
              FROM tmp_kis_adjusted_ohlcv
            ON CONFLICT ("time", ticker) DO UPDATE SET
              adj_open = EXCLUDED.adj_open,
              adj_high = EXCLUDED.adj_high,
              adj_low = EXCLUDED.adj_low,
              adj_close = EXCLUDED.adj_close,
              adj_volume = EXCLUDED.adj_volume,
              mod_yn = EXCLUDED.mod_yn,
              revision_reason = EXCLUDED.revision_reason,
              raw_payload_jsonb = EXCLUDED.raw_payload_jsonb,
              quality_flags = EXCLUDED.quality_flags,
              run_id = EXCLUDED.run_id,
              updated_at = now();
            INSERT INTO meta.lineage_event
              (target_table, target_key, source_table, source_key, run_id, transform_version, metadata_jsonb)
            SELECT
              {sql_literal(KIS_ADJUSTED_TABLE)},
              ticker || ':' || "time"::text,
              'kis_api.inquire_daily_itemchartprice',
              ticker || ':' || "time"::text || ':fid_org_adj_prc=0',
              run_id,
              {sql_literal(KIS_ADJUSTED_TRANSFORM_VERSION)},
              jsonb_build_object(
                'stage', 'kis_adjusted_ingestion',
                'adjusted_price_method', 'kis_official_adjusted',
                'fid_org_adj_prc', '0'
              )
            FROM tmp_kis_adjusted_ohlcv;
            """,
        )

    def copy_api_request_logs(self, events: list[ApiRequestLog], run_id: str) -> None:
        if not events:
            return
        values = []
        for event in events:
            values.append(
                "("
                f"{sql_literal(run_id)}, {sql_literal(event.source_id)}, {sql_literal(event.endpoint_key)}, "
                f"{sql_literal(stable_hash(event.request))}, {sql_literal(event.success)}, {sql_literal(event.status_code)}, "
                f"{sql_literal(event.elapsed_ms)}, {sql_literal(event.retry_count)}, "
                f"{sql_literal(stable_hash(event.response) if event.response is not None else None)}, "
                f"{sql_literal(truncate(event.error_message, 4000))}, {jsonb_literal(event.metadata)}, "
                f"{sql_literal(event.request_started_at.isoformat())}"
                ")"
            )
        self.execute(
            f"""
            INSERT INTO meta.api_request_log
              (run_id, source_id, endpoint_key, request_hash, success, status_code,
               elapsed_ms, retry_count, response_hash, error_message, metadata_jsonb, request_started_at)
            VALUES {", ".join(values)};
            """
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest KIS official adjusted OHLCV into TimescaleDB.")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD. Required unless --daily-incremental is set.")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD. Required unless --daily-incremental is set.")
    parser.add_argument(
        "--daily-incremental",
        action="store_true",
        help="Select the latest core OHLCV trade date on or before --as-of-date.",
    )
    parser.add_argument("--as-of-date", default=None, help="YYYY-MM-DD upper bound for --daily-incremental.")
    parser.add_argument(
        "--incremental-lookback-days",
        type=int,
        default=DEFAULT_INCREMENTAL_LOOKBACK_DAYS,
        help="Calendar-day warmup lookback before the selected daily incremental end date.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Resume safely by skipping ticker/date windows already complete in DB state.",
    )
    parser.add_argument("--tickers", default="", help="Optional comma-separated ticker subset.")
    parser.add_argument("--limit-tickers", type=int, default=None, help="Optional deterministic ticker limit.")
    parser.add_argument("--request-window-days", type=int, default=DEFAULT_REQUEST_WINDOW_DAYS)
    parser.add_argument("--workers", type=int, default=int(os.getenv("KIS_ADJUSTED_WORKERS", "1")))
    parser.add_argument(
        "--request-sleep-seconds",
        type=float,
        default=float(os.getenv("KIS_REQUEST_SLEEP_SECONDS", DEFAULT_REQUEST_SLEEP_SECONDS)),
    )
    parser.add_argument("--flush-rows", type=int, default=DEFAULT_FLUSH_ROWS)
    parser.add_argument("--max-requests", type=int, default=None, help="Optional safety limit for smoke runs.")
    parser.add_argument(
        "--db-mode",
        choices=["docker", "psycopg"],
        default=None,
        help="Database access mode. Defaults to psycopg when DB credentials are configured; otherwise docker.",
    )
    parser.add_argument("--db-container", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.request_window_days < 1:
        raise ValueError("--request-window-days must be >= 1.")
    if args.flush_rows < 1:
        raise ValueError("--flush-rows must be >= 1.")
    if args.incremental_lookback_days < 0:
        raise ValueError("--incremental-lookback-days must be >= 0.")

    db_config = DatabaseConfig.from_env()
    if args.db_container:
        db_config = DatabaseConfig(**{**db_config.__dict__, "docker_container": args.db_container})
    requested_db_mode = args.db_mode or os.getenv("QUANT_DB_EXECUTION_MODE")
    db_mode = resolve_execution_mode(db_config, requested_db_mode)
    db: KisDbClient = DockerPsqlClient(db_config) if db_mode == "docker" else PsycopgClient(db_config)
    kis_client = KisOhlcvClient(KisConfig.from_env())

    run_id = str(uuid4())
    pending_api_logs: list[ApiRequestLog] = []
    api_log_lock = Lock()

    def observe_api_request(event: ApiRequestLog) -> None:
        with api_log_lock:
            pending_api_logs.append(event)

    kis_client.set_request_observer(observe_api_request)
    ensure_tables(db)
    start_date, end_date = resolve_requested_date_window(db, args)
    if end_date < start_date:
        raise ValueError("--end-date must be greater than or equal to --start-date.")
    start_run(db, run_id, args, start_date, end_date)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "table": KIS_ADJUSTED_TABLE,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "request_window_days": args.request_window_days,
        "request_sleep_seconds": args.request_sleep_seconds,
        "workers": args.workers,
        "daily_incremental": args.daily_incremental,
        "incremental_lookback_days": args.incremental_lookback_days,
        "skip_existing": args.skip_existing,
        "tickers": 0,
        "requests": 0,
        "rows": 0,
        "api_request_logs": 0,
        "skipped_windows": 0,
        "failed_windows": [],
    }

    pending_rows: list[dict[str, Any]] = []
    pending_completed_windows: list[tuple[str, FetchWindow]] = []
    try:
        tickers = select_tickers(db, start_date, end_date, args.tickers, args.limit_tickers)
        summary["tickers"] = len(tickers)
        jobs = iter_resumable_fetch_jobs(
            db=db,
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            window_days=args.request_window_days,
            skip_existing=args.skip_existing,
            summary=summary,
        )
        if args.workers == 1:
            for ticker, window in jobs:
                if args.max_requests is not None and summary["requests"] >= args.max_requests:
                    flush_rows(db, pending_rows, run_id, summary, pending_completed_windows, pending_api_logs, api_log_lock)
                    finish_run(db, run_id, "partial_success", None)
                    write_output(args.output, summary)
                    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
                    return 0
                completed = fetch_and_collect(kis_client, ticker, window, pending_rows, summary, args.request_sleep_seconds)
                if completed:
                    pending_completed_windows.append((ticker, window))
                if len(pending_rows) >= args.flush_rows:
                    flush_rows(db, pending_rows, run_id, summary, pending_completed_windows, pending_api_logs, api_log_lock)
        else:
            issue_token_with_retry(kis_client)
            run_parallel_fetches(
                kis_client=kis_client,
                jobs=jobs,
                pending_rows=pending_rows,
                pending_completed_windows=pending_completed_windows,
                summary=summary,
                max_requests=args.max_requests,
                workers=args.workers,
                request_sleep_seconds=args.request_sleep_seconds,
                flush=lambda: flush_rows(
                    db,
                    pending_rows,
                    run_id,
                    summary,
                    pending_completed_windows,
                    pending_api_logs,
                    api_log_lock,
                ),
                flush_threshold=args.flush_rows,
            )

        flush_rows(db, pending_rows, run_id, summary, pending_completed_windows, pending_api_logs, api_log_lock)
        finish_run(db, run_id, "success" if not summary["failed_windows"] else "partial_success", None)
    except Exception as exc:
        flush_api_request_logs(db, pending_api_logs, run_id, summary, api_log_lock)
        finish_run(db, run_id, "failed", str(exc))
        raise

    write_output(args.output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


def ensure_tables(db: DockerPsqlClient) -> None:
    db.execute(
        f"""
        CREATE SCHEMA IF NOT EXISTS feature;
        INSERT INTO meta.data_source (source_id, name, base_url_key, version, is_primary)
        VALUES ('KIS', 'Korea Investment Securities', 'KIS_BASE_URL', 'v1', FALSE)
        ON CONFLICT (source_id) DO UPDATE SET
          name = EXCLUDED.name,
          base_url_key = EXCLUDED.base_url_key,
          version = EXCLUDED.version,
          updated_at = now();

        CREATE TABLE IF NOT EXISTS meta.ingestion_cursor (
          source_id TEXT NOT NULL REFERENCES meta.data_source(source_id),
          dataset TEXT NOT NULL,
          cursor_key TEXT NOT NULL,
          cursor_value TEXT NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (source_id, dataset, cursor_key)
        );

        CREATE TABLE IF NOT EXISTS meta.api_request_log (
          request_id BIGSERIAL PRIMARY KEY,
          run_id UUID REFERENCES meta.ingestion_run(run_id),
          source_id TEXT REFERENCES meta.data_source(source_id),
          endpoint_key TEXT NOT NULL,
          request_hash TEXT NOT NULL,
          success BOOLEAN NOT NULL DEFAULT FALSE,
          status_code INTEGER,
          elapsed_ms INTEGER,
          retry_count INTEGER NOT NULL DEFAULT 0,
          response_hash TEXT,
          error_message TEXT,
          metadata_jsonb JSONB NOT NULL DEFAULT '{{}}'::jsonb,
          request_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS success BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS error_message TEXT;
        ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB NOT NULL DEFAULT '{{}}'::jsonb;
        ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS request_started_at TIMESTAMPTZ NOT NULL DEFAULT now();
        CREATE INDEX IF NOT EXISTS idx_api_request_log_run_source_created
          ON meta.api_request_log (run_id, source_id, created_at DESC);

        ALTER TABLE meta.lineage_event ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB NOT NULL DEFAULT '{{}}'::jsonb;

        CREATE TABLE IF NOT EXISTS {KIS_ADJUSTED_TABLE} (
          "time" DATE NOT NULL,
          ticker TEXT NOT NULL,
          adj_open NUMERIC(20, 6),
          adj_high NUMERIC(20, 6),
          adj_low NUMERIC(20, 6),
          adj_close NUMERIC(20, 6),
          adj_volume NUMERIC(28, 6),
          mod_yn TEXT,
          revision_reason TEXT,
          raw_payload_jsonb JSONB NOT NULL DEFAULT '{{}}'::jsonb,
          quality_flags JSONB NOT NULL DEFAULT '{{}}'::jsonb,
          run_id UUID REFERENCES meta.ingestion_run(run_id),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY ("time", ticker)
        );
        SELECT create_hypertable('{KIS_ADJUSTED_TABLE}', 'time', if_not_exists => TRUE);
        CREATE INDEX IF NOT EXISTS idx_feature_kis_adjusted_ohlcv_daily_ticker_time
          ON {KIS_ADJUSTED_TABLE} (ticker, "time" DESC);
        """
    )


def start_run(db: DockerPsqlClient, run_id: str, args: argparse.Namespace, start_date: date, end_date: date) -> None:
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "tickers": args.tickers,
        "limit_tickers": args.limit_tickers,
        "request_window_days": args.request_window_days,
        "request_sleep_seconds": args.request_sleep_seconds,
        "daily_incremental": args.daily_incremental,
        "as_of_date": args.as_of_date,
        "incremental_lookback_days": args.incremental_lookback_days,
        "skip_existing": args.skip_existing,
        "table": KIS_ADJUSTED_TABLE,
        "fid_org_adj_prc": "0",
        "adjusted_price_method": "kis_official_adjusted",
    }
    db.execute(
        f"""
        INSERT INTO meta.ingestion_run
          (run_id, dag_id, task_id, source_id, started_at, status, params_jsonb)
        VALUES
          ('{run_id}', 'manual_kis_adjusted_ohlcv_ingestion', 'ingest_kis_adjusted_ohlcv',
           '{KIS_SOURCE_ID}', now(), 'running', '{json.dumps(params, ensure_ascii=False)}'::jsonb);
        """
    )


def finish_run(db: DockerPsqlClient, run_id: str, status: str, error: str | None) -> None:
    error_sql = "NULL" if error is None else "'" + error.replace("'", "''")[:4000] + "'"
    db.execute(
        f"""
        UPDATE meta.ingestion_run
           SET status = '{status}', ended_at = now(), error_message = {error_sql}
         WHERE run_id = '{run_id}';
        """
    )


def select_tickers(
    db: DockerPsqlClient,
    start_date: date,
    end_date: date,
    raw_tickers: str,
    limit: int | None,
) -> list[str]:
    requested = [normalize_ticker(item) for item in raw_tickers.split(",") if item.strip()]
    where = [f"o.trade_date BETWEEN DATE '{start_date.isoformat()}' AND DATE '{end_date.isoformat()}'"]
    if requested:
        quoted = ", ".join("'" + item.replace("'", "''") + "'" for item in requested)
        where.append(f"sm.symbol IN ({quoted})")
    limit_sql = f" LIMIT {int(limit)}" if limit else ""
    rows = db.fetch_csv(
        f"""
        SELECT sm.symbol AS ticker
          FROM core.ohlcv_daily o
          JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
         WHERE {' AND '.join(where)}
         GROUP BY sm.symbol
         ORDER BY sm.symbol
         {limit_sql}
        """
    )
    return [normalize_ticker(row["ticker"]) for row in rows]


def resolve_requested_date_window(db: DockerPsqlClient, args: argparse.Namespace) -> tuple[date, date]:
    if args.daily_incremental:
        if args.start_date or args.end_date:
            raise ValueError("--daily-incremental cannot be combined with --start-date or --end-date.")
        as_of_date = date.fromisoformat(args.as_of_date) if args.as_of_date else date.today()
        return select_daily_incremental_window(db, as_of_date, args.incremental_lookback_days)

    if not args.start_date or not args.end_date:
        raise ValueError("--start-date and --end-date are required unless --daily-incremental is set.")
    return date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)


def select_daily_incremental_window(
    db: DockerPsqlClient,
    as_of_date: date,
    incremental_lookback_days: int,
) -> tuple[date, date]:
    latest_trade_date = select_latest_core_trade_date(db, as_of_date)
    return resolve_daily_incremental_window(latest_trade_date, incremental_lookback_days)


def select_latest_core_trade_date(db: DockerPsqlClient, as_of_date: date) -> date:
    rows = db.fetch_csv(
        f"""
        SELECT MAX(o.trade_date)::text AS trade_date
          FROM core.ohlcv_daily o
         WHERE o.trade_date <= DATE {sql_literal(as_of_date.isoformat())}
        """
    )
    raw_trade_date = rows[0].get("trade_date") if rows else None
    if not raw_trade_date:
        raise ValueError(f"No core OHLCV trade date found on or before {as_of_date.isoformat()}.")
    return date.fromisoformat(str(raw_trade_date))


def resolve_daily_incremental_window(latest_trade_date: date, incremental_lookback_days: int) -> tuple[date, date]:
    if incremental_lookback_days < 0:
        raise ValueError("incremental_lookback_days must be >= 0.")
    return latest_trade_date - timedelta(days=incremental_lookback_days), latest_trade_date


def iter_windows(start_date: date, end_date: date, window_days: int) -> Iterable[FetchWindow]:
    current = start_date
    while current <= end_date:
        window_end = min(current + timedelta(days=window_days - 1), end_date)
        yield FetchWindow(start_date=current, end_date=window_end)
        current = window_end + timedelta(days=1)


def iter_fetch_jobs(
    tickers: list[str],
    start_date: date,
    end_date: date,
    window_days: int,
) -> Iterable[tuple[str, FetchWindow]]:
    for ticker in tickers:
        for window in iter_windows(start_date, end_date, window_days):
            yield ticker, window


def iter_resumable_fetch_jobs(
    *,
    db: DockerPsqlClient,
    tickers: list[str],
    start_date: date,
    end_date: date,
    window_days: int,
    skip_existing: bool,
    summary: dict[str, Any],
) -> Iterable[tuple[str, FetchWindow]]:
    for ticker, window in iter_fetch_jobs(tickers, start_date, end_date, window_days):
        if skip_existing and window_is_complete(db, ticker, window):
            summary["skipped_windows"] += 1
            continue
        yield ticker, window


def window_is_complete(db: DockerPsqlClient, ticker: str, window: FetchWindow) -> bool:
    return parse_window_completion(db.fetch_csv(build_window_completion_query(ticker, window)))


def build_window_completion_query(ticker: str, window: FetchWindow) -> str:
    normalized_ticker = normalize_ticker(ticker)
    cursor_key = completed_window_cursor_key(normalized_ticker, window)
    return f"""
        WITH expected AS (
            SELECT COUNT(*)::int AS expected_count
              FROM core.ohlcv_daily o
              JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
             WHERE sm.symbol = {sql_literal(normalized_ticker)}
               AND o.trade_date BETWEEN DATE {sql_literal(window.start_date.isoformat())}
                                    AND DATE {sql_literal(window.end_date.isoformat())}
        ),
        observed AS (
            SELECT COUNT(DISTINCT k."time")::int AS observed_count
              FROM {KIS_ADJUSTED_TABLE} k
             WHERE k.ticker = {sql_literal(normalized_ticker)}
               AND k."time" BETWEEN DATE {sql_literal(window.start_date.isoformat())}
                                AND DATE {sql_literal(window.end_date.isoformat())}
        ),
        cursor_state AS (
            SELECT EXISTS (
                SELECT 1
                  FROM meta.ingestion_cursor
                 WHERE source_id = {sql_literal(KIS_SOURCE_ID)}
                   AND dataset = {sql_literal(KIS_ADJUSTED_CURSOR_DATASET)}
                   AND cursor_key = {sql_literal(cursor_key)}
            ) AS cursor_complete
        )
        SELECT
            expected.expected_count,
            observed.observed_count,
            cursor_state.cursor_complete,
            (
                expected.expected_count = 0
                OR observed.observed_count >= expected.expected_count
                OR cursor_state.cursor_complete
            ) AS complete
          FROM expected, observed, cursor_state
        """


def parse_window_completion(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    return parse_sql_bool(rows[0].get("complete"))


def parse_sql_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "t", "true", "y", "yes"}


def fetch_and_collect(
    kis_client: KisOhlcvClient,
    ticker: str,
    window: FetchWindow,
    pending_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    request_sleep_seconds: float,
) -> bool:
    completed = False
    try:
        rows, request_count = fetch_adjusted_rows_recursive(kis_client, ticker, window)
        summary["requests"] += request_count
        pending_rows.extend(rows)
        completed = bool(rows)
        if request_sleep_seconds > 0:
            time.sleep(request_sleep_seconds)
    except Exception as exc:  # noqa: BLE001 - keep full run moving and report failed windows
        summary["failed_windows"].append(
            {
                "ticker": ticker,
                "start_date": window.start_date.isoformat(),
                "end_date": window.end_date.isoformat(),
                "error": str(exc)[:500],
            }
        )
    return completed


def fetch_adjusted_rows_recursive(
    kis_client: KisOhlcvClient,
    ticker: str,
    window: FetchWindow,
) -> tuple[list[dict[str, Any]], int]:
    try:
        payload = fetch_payload_with_token_retry(kis_client, ticker, window)
        return payload_to_adjusted_rows(payload.payload, ticker), 1
    except Exception:
        if window.start_date >= window.end_date:
            raise
        midpoint = window.start_date + (window.end_date - window.start_date) // 2
        left = FetchWindow(window.start_date, midpoint)
        right = FetchWindow(midpoint + timedelta(days=1), window.end_date)
        left_rows, left_requests = fetch_adjusted_rows_recursive(kis_client, ticker, left)
        right_rows, right_requests = fetch_adjusted_rows_recursive(kis_client, ticker, right)
        return left_rows + right_rows, left_requests + right_requests


def run_parallel_fetches(
    *,
    kis_client: KisOhlcvClient,
    jobs: Iterable[tuple[str, FetchWindow]],
    pending_rows: list[dict[str, Any]],
    pending_completed_windows: list[tuple[str, FetchWindow]],
    summary: dict[str, Any],
    max_requests: int | None,
    workers: int,
    request_sleep_seconds: float,
    flush: Any,
    flush_threshold: int,
) -> None:
    max_pending = max(workers * 4, workers)
    job_iter = iter(jobs)
    pending: set[Future[tuple[str, FetchWindow, list[dict[str, Any]] | None, int, str | None]]] = set()

    def submit_next(executor: ThreadPoolExecutor) -> bool:
        if max_requests is not None and summary["requests"] + len(pending) >= max_requests:
            return False
        try:
            ticker, window = next(job_iter)
        except StopIteration:
            return False
        pending.add(executor.submit(fetch_adjusted_rows, kis_client, ticker, window, request_sleep_seconds))
        return True

    with ThreadPoolExecutor(max_workers=workers) as executor:
        while len(pending) < max_pending and submit_next(executor):
            pass
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                ticker, window, rows, request_count, error = future.result()
                if error is None and rows is not None:
                    summary["requests"] += request_count
                    pending_rows.extend(rows)
                    if rows:
                        pending_completed_windows.append((ticker, window))
                else:
                    summary["failed_windows"].append(
                        {
                            "ticker": ticker,
                            "start_date": window.start_date.isoformat(),
                            "end_date": window.end_date.isoformat(),
                            "error": str(error)[:500],
                        }
                    )
                if len(pending_rows) >= flush_threshold:
                    flush()
            while len(pending) < max_pending and submit_next(executor):
                pass


def fetch_adjusted_rows(
    kis_client: KisOhlcvClient,
    ticker: str,
    window: FetchWindow,
    request_sleep_seconds: float,
) -> tuple[str, FetchWindow, list[dict[str, Any]] | None, int, str | None]:
    try:
        rows, request_count = fetch_adjusted_rows_recursive(kis_client, ticker, window)
        if request_sleep_seconds > 0:
            time.sleep(request_sleep_seconds)
        return ticker, window, rows, request_count, None
    except Exception as exc:  # noqa: BLE001 - failure is captured in summary
        return ticker, window, None, 0, str(exc)


def fetch_payload_with_token_retry(kis_client: KisOhlcvClient, ticker: str, window: FetchWindow):
    try:
        return kis_client.fetch_daily_price_payload(
            symbol=ticker,
            start_date=window.start_date,
            end_date=window.end_date,
            adjusted=True,
        )
    except Exception as exc:
        if "403" not in str(exc):
            raise
        time.sleep(float(os.getenv("KIS_TOKEN_RETRY_WAIT_SECONDS", DEFAULT_TOKEN_RETRY_WAIT_SECONDS)))
        return kis_client.fetch_daily_price_payload(
            symbol=ticker,
            start_date=window.start_date,
            end_date=window.end_date,
            adjusted=True,
        )


def issue_token_with_retry(kis_client: KisOhlcvClient) -> str:
    try:
        return kis_client.issue_access_token()
    except Exception as exc:
        if "403" not in str(exc):
            raise
        time.sleep(float(os.getenv("KIS_TOKEN_RETRY_WAIT_SECONDS", DEFAULT_TOKEN_RETRY_WAIT_SECONDS)))
        return kis_client.issue_access_token()


def payload_to_adjusted_rows(payload: dict[str, Any], ticker: str) -> list[dict[str, Any]]:
    if payload.get("rt_cd") not in (None, "0"):
        raise RuntimeError(f"KIS response failed: {payload.get('msg_cd')} {payload.get('msg1')}")

    bars = normalize_kis_daily_price(payload, symbol=ticker)
    rows = []
    for bar in bars:
        quality_flags = {
            "source": KIS_SOURCE_ID,
            "adjusted_price_method": "kis_official_adjusted",
            "fid_org_adj_prc": "0",
        }
        if bar.raw.get("mod_yn"):
            quality_flags["mod_yn"] = bar.raw.get("mod_yn")
        if bar.raw.get("revl_issu_reas"):
            quality_flags["revision_reason"] = bar.raw.get("revl_issu_reas")
        rows.append(
            {
                "time": bar.trade_date.isoformat(),
                "ticker": normalize_ticker(ticker),
                "adj_open": bar.open,
                "adj_high": bar.high,
                "adj_low": bar.low,
                "adj_close": bar.close,
                "adj_volume": bar.volume,
                "mod_yn": bar.raw.get("mod_yn"),
                "revision_reason": bar.raw.get("revl_issu_reas"),
                "raw": bar.raw,
                "quality_flags": quality_flags,
            }
        )
    return rows


def flush_rows(
    db: DockerPsqlClient,
    rows: list[dict[str, Any]],
    run_id: str,
    summary: dict[str, Any],
    completed_windows: list[tuple[str, FetchWindow]] | None = None,
    api_logs: list[ApiRequestLog] | None = None,
    api_log_lock: Lock | None = None,
) -> None:
    if not rows and not completed_windows and not api_logs:
        return
    flush_api_request_logs(db, api_logs, run_id, summary, api_log_lock)
    if rows:
        db.copy_adjusted_rows(rows, run_id)
        summary["rows"] += len(rows)
        rows.clear()
    if completed_windows:
        upsert_completed_windows(db, completed_windows, run_id)
        completed_windows.clear()


def flush_api_request_logs(
    db: DockerPsqlClient,
    api_logs: list[ApiRequestLog] | None,
    run_id: str,
    summary: dict[str, Any],
    api_log_lock: Lock | None = None,
) -> None:
    if not api_logs:
        return
    if api_log_lock is None:
        drained = list(api_logs)
        api_logs.clear()
    else:
        with api_log_lock:
            drained = list(api_logs)
            api_logs.clear()
    if not drained:
        return
    db.copy_api_request_logs(drained, run_id)
    summary["api_request_logs"] = summary.get("api_request_logs", 0) + len(drained)


def upsert_completed_windows(db: DockerPsqlClient, completed_windows: list[tuple[str, FetchWindow]], run_id: str) -> None:
    sql = build_completed_window_cursor_upsert(completed_windows, run_id)
    if sql:
        db.execute(sql)


def build_completed_window_cursor_upsert(completed_windows: list[tuple[str, FetchWindow]], run_id: str) -> str:
    if not completed_windows:
        return ""
    values = []
    for ticker, window in completed_windows:
        normalized_ticker = normalize_ticker(ticker)
        cursor_key = completed_window_cursor_key(normalized_ticker, window)
        cursor_value = {
            "ticker": normalized_ticker,
            "start_date": window.start_date.isoformat(),
            "end_date": window.end_date.isoformat(),
            "run_id": run_id,
        }
        values.append(
            "("
            f"{sql_literal(KIS_SOURCE_ID)}, "
            f"{sql_literal(KIS_ADJUSTED_CURSOR_DATASET)}, "
            f"{sql_literal(cursor_key)}, "
            f"{sql_literal(json.dumps(cursor_value, ensure_ascii=False, separators=(',', ':')))}"
            ")"
        )
    return f"""
        INSERT INTO meta.ingestion_cursor (source_id, dataset, cursor_key, cursor_value)
        VALUES {", ".join(values)}
        ON CONFLICT (source_id, dataset, cursor_key) DO UPDATE SET
          cursor_value = EXCLUDED.cursor_value,
          updated_at = now();
        """


def write_output(path: str | None, summary: dict[str, Any]) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def normalize_ticker(value: Any) -> str:
    text = str(value).strip()
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def completed_window_cursor_key(ticker: str, window: FetchWindow) -> str:
    return (
        f"{KIS_ADJUSTED_COMPLETED_WINDOW_CURSOR_PREFIX}:"
        f"{normalize_ticker(ticker)}:{window.start_date.isoformat()}:{window.end_date.isoformat()}"
    )


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def jsonb_literal(value: Any) -> str:
    return f"{sql_literal(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))}::jsonb"


if __name__ == "__main__":
    raise SystemExit(main())
