"""Compute and load technical indicators from local OHLCV history.

The pipeline is intentionally DB-first:

1. Read local TimescaleDB OHLCV rows and build ``{ticker: DataFrame}`` batches.
2. Preprocess each ticker for listing windows, short trading halts, inferred
   relisting segments, and adjusted-price continuity.
3. Compute indicators through the Pandas-TA interface with TA-Lib enabled.
4. Load five category tables with ``PRIMARY KEY ("time", ticker)``.

Secrets are never loaded from ``.env``. For local Docker DB usage, prefer:

    python scripts/compute_technical_indicators_pipeline.py --db-mode docker

For public/shared DB usage, set ``QUANT_DB_DSN`` or the host/user/password
environment variables and the script will auto-select ``psycopg`` unless you
override it with ``--db-mode``.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Iterable, Protocol
from uuid import uuid4

import numpy as np
import pandas as pd

try:
    import pandas_ta_classic as ta  # noqa: F401
except ImportError:  # pragma: no cover - fallback for environments that still carry the legacy package
    import pandas_ta as ta  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import DatabaseConfig  # noqa: E402
from quant_agent.data.db import PsycopgScriptClient, resolve_execution_mode  # noqa: E402


DEFAULT_TICKER_BATCH_SIZE = 64
DEFAULT_FLUSH_ROWS = 50_000
DEFAULT_HALT_FFILL_DAYS = 5
DEFAULT_RELIST_GAP_DAYS = 30
DEFAULT_WORKER_RESERVE = 1
DEFAULT_TA_WORKER_CAP = 4
TA_SOURCE_ID = "TA"
TA_TRANSFORM_VERSION = "pandas-ta-talib-v1"
ADJUSTED_OHLCV_TRANSFORM_VERSION = "adjusted-ohlcv-v1"
MART_FEATURE_VIEW = "mart.kis_adjusted_feature_frame_asof"
CANONICAL_SYMBOL_FEATURE_VIEW = "mart.symbol_feature_frame_asof"

CATEGORY_TABLES = {
    "Trend": "feature.ta_trend_ticker_daily",
    "Momentum": "feature.ta_momentum_ticker_daily",
    "Volatility": "feature.ta_volatility_ticker_daily",
    "Volume": "feature.ta_volume_ticker_daily",
    "Pattern": "feature.ta_pattern_ticker_daily",
}
ADJUSTED_OHLCV_TABLE = "feature.adjusted_ohlcv_daily"


def _configured_worker_cap() -> int:
    raw = os.getenv("QUANT_TA_MAX_WORKERS")
    if raw is None or raw.strip() == "":
        return DEFAULT_TA_WORKER_CAP
    worker_cap = int(raw)
    if worker_cap < 1:
        raise ValueError("QUANT_TA_MAX_WORKERS must be >= 1.")
    return worker_cap


def resolve_worker_count(
    requested_workers: int | None = None,
    *,
    cpu_count: int | None = None,
    worker_cap: int | None = None,
) -> int:
    cpu_total = cpu_count or os.cpu_count() or 2
    cpu_workers = max(1, cpu_total - DEFAULT_WORKER_RESERVE)
    cap = worker_cap if worker_cap is not None else _configured_worker_cap()
    if requested_workers is None:
        return max(1, min(cpu_workers, cap))
    return max(1, min(requested_workers, cap))

PATTERN_NAMES = [
    "doji",
    "hammer",
    "hangingman",
    "engulfing",
    "morningstar",
    "eveningstar",
    "shootingstar",
    "harami",
    "darkcloudcover",
    "piercing",
]


@dataclass(frozen=True)
class RuntimeOptions:
    start_date: date
    end_date: date
    halt_ffill_days: int
    relist_gap_days: int
    adjust_splits: bool
    input_price_source: str


@dataclass(frozen=True)
class TickerTask:
    ticker: str
    frame: pd.DataFrame
    calendar: list[pd.Timestamp]
    listing_windows: list[dict[str, Any]]
    options: RuntimeOptions


@dataclass(frozen=True)
class TickerResult:
    ticker: str
    category_rows: dict[str, list[dict[str, Any]]]
    adjusted_rows: list[dict[str, Any]]
    diagnostics: dict[str, Any]


class TaDbClient(Protocol):
    def execute(self, sql: str) -> str:
        ...

    def fetch_csv(self, query: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
        ...

    def copy_category_rows(self, table: str, rows: list[dict[str, Any]], run_id: str) -> None:
        ...

    def copy_adjusted_ohlcv_rows(self, rows: list[dict[str, Any]], run_id: str) -> None:
        ...


class DockerPsqlClient:
    """Small psql wrapper for local Docker-only DB access."""

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

    def fetch_csv(self, query: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
        sql = f"COPY ({query.rstrip().rstrip(';')}) TO STDOUT WITH (FORMAT csv, HEADER true);"
        text = self.execute(sql)
        if not text.strip():
            return pd.DataFrame()
        return pd.read_csv(
            io.StringIO(text),
            parse_dates=parse_dates or [],
            dtype={"ticker": "string", "base_ticker": "string", "symbol": "string"},
        )

    def copy_category_rows(self, table: str, rows: list[dict[str, Any]], run_id: str) -> None:
        if not rows:
            return

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer, lineterminator="\n")
        for row in rows:
            writer.writerow(
                [
                    row["time"],
                    row["ticker"],
                    row["base_ticker"],
                    row["segment_id"],
                    json.dumps(row["values"], ensure_ascii=False, separators=(",", ":"), default=str),
                    json.dumps(row["quality_flags"], ensure_ascii=False, separators=(",", ":"), default=str),
                    run_id,
                ]
            )

        sql = f"""
BEGIN;
CREATE TEMP TABLE tmp_ta_rows (
  "time" DATE,
  ticker TEXT,
  base_ticker TEXT,
  segment_id INTEGER,
  values_jsonb JSONB,
  quality_flags JSONB,
  run_id UUID
) ON COMMIT DROP;
COPY tmp_ta_rows ("time", ticker, base_ticker, segment_id, values_jsonb, quality_flags, run_id)
FROM STDIN WITH (FORMAT csv);
{csv_buffer.getvalue()}\\.
INSERT INTO {table} ("time", ticker, base_ticker, segment_id, values_jsonb, quality_flags, run_id)
SELECT "time", ticker, base_ticker, segment_id, values_jsonb, quality_flags, run_id
FROM tmp_ta_rows
ON CONFLICT ("time", ticker) DO UPDATE SET
  base_ticker = EXCLUDED.base_ticker,
  segment_id = EXCLUDED.segment_id,
  values_jsonb = EXCLUDED.values_jsonb,
  quality_flags = EXCLUDED.quality_flags,
  run_id = EXCLUDED.run_id,
  updated_at = now();
INSERT INTO meta.lineage_event
  (target_table, target_key, source_table, source_key, run_id, transform_version, metadata_jsonb)
SELECT
  {sql_literal(table)},
  ticker || ':' || "time"::text,
  {sql_literal(ADJUSTED_OHLCV_TABLE)},
  base_ticker || ':' || "time"::text,
  run_id,
  {sql_literal(TA_TRANSFORM_VERSION)},
  jsonb_build_object('stage', 'ta_indicator_compute', 'target_table', {sql_literal(table)})
FROM tmp_ta_rows;
COMMIT;
"""
        self.execute(sql)

    def copy_adjusted_ohlcv_rows(self, rows: list[dict[str, Any]], run_id: str) -> None:
        if not rows:
            return

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer, lineterminator="\n")
        for row in rows:
            writer.writerow(
                [
                    row["time"],
                    row["ticker"],
                    row["base_ticker"],
                    row["segment_id"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row["adj_open"],
                    row["adj_high"],
                    row["adj_low"],
                    row["adj_close"],
                    row["adj_volume"],
                    row["adjustment_factor"],
                    json.dumps(row["quality_flags"], ensure_ascii=False, separators=(",", ":"), default=str),
                    run_id,
                ]
            )

        sql = f"""
BEGIN;
CREATE TEMP TABLE tmp_adjusted_ohlcv (
  "time" DATE,
  ticker TEXT,
  base_ticker TEXT,
  segment_id INTEGER,
  open NUMERIC(20, 6),
  high NUMERIC(20, 6),
  low NUMERIC(20, 6),
  close NUMERIC(20, 6),
  volume NUMERIC(28, 6),
  adj_open NUMERIC(20, 6),
  adj_high NUMERIC(20, 6),
  adj_low NUMERIC(20, 6),
  adj_close NUMERIC(20, 6),
  adj_volume NUMERIC(28, 6),
  adjustment_factor NUMERIC(28, 12),
  quality_flags JSONB,
  run_id UUID
) ON COMMIT DROP;
COPY tmp_adjusted_ohlcv (
  "time", ticker, base_ticker, segment_id,
  open, high, low, close, volume,
  adj_open, adj_high, adj_low, adj_close, adj_volume,
  adjustment_factor, quality_flags, run_id
)
FROM STDIN WITH (FORMAT csv);
{csv_buffer.getvalue()}\\.
INSERT INTO {ADJUSTED_OHLCV_TABLE} (
  "time", ticker, base_ticker, segment_id,
  open, high, low, close, volume,
  adj_open, adj_high, adj_low, adj_close, adj_volume,
  adjustment_factor, quality_flags, run_id
)
SELECT
  "time", ticker, base_ticker, segment_id,
  open, high, low, close, volume,
  adj_open, adj_high, adj_low, adj_close, adj_volume,
  adjustment_factor, quality_flags, run_id
FROM tmp_adjusted_ohlcv
ON CONFLICT ("time", ticker) DO UPDATE SET
  base_ticker = EXCLUDED.base_ticker,
  segment_id = EXCLUDED.segment_id,
  open = EXCLUDED.open,
  high = EXCLUDED.high,
  low = EXCLUDED.low,
  close = EXCLUDED.close,
  volume = EXCLUDED.volume,
  adj_open = EXCLUDED.adj_open,
  adj_high = EXCLUDED.adj_high,
  adj_low = EXCLUDED.adj_low,
  adj_close = EXCLUDED.adj_close,
  adj_volume = EXCLUDED.adj_volume,
  adjustment_factor = EXCLUDED.adjustment_factor,
  quality_flags = EXCLUDED.quality_flags,
  run_id = EXCLUDED.run_id,
  updated_at = now();
INSERT INTO meta.lineage_event
  (target_table, target_key, source_table, source_key, run_id, transform_version, metadata_jsonb)
SELECT
  {sql_literal(ADJUSTED_OHLCV_TABLE)},
  ticker || ':' || "time"::text,
  CASE
    WHEN quality_flags->>'adjusted_price_method' = 'kis_official_adjusted'
    THEN 'feature.kis_adjusted_ohlcv_daily'
    ELSE 'core.ohlcv_daily'
  END,
  base_ticker || ':' || "time"::text,
  run_id,
  {sql_literal(ADJUSTED_OHLCV_TRANSFORM_VERSION)},
  jsonb_build_object(
    'stage', 'adjusted_ohlcv_build',
    'adjusted_price_method', quality_flags->>'adjusted_price_method',
    'segment_id', segment_id
  )
FROM tmp_adjusted_ohlcv;
COMMIT;
"""
        self.execute(sql)


class PsycopgClient(PsycopgScriptClient):
    def fetch_csv(self, query: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
        text = self.fetch_csv_text(query)
        if not text.strip():
            return pd.DataFrame()
        return pd.read_csv(
            io.StringIO(text),
            parse_dates=parse_dates or [],
            dtype={"ticker": "string", "base_ticker": "string", "symbol": "string"},
        )

    def copy_category_rows(self, table: str, rows: list[dict[str, Any]], run_id: str) -> None:
        if not rows:
            return

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer, lineterminator="\n")
        for row in rows:
            writer.writerow(
                [
                    row["time"],
                    row["ticker"],
                    row["base_ticker"],
                    row["segment_id"],
                    json.dumps(row["values"], ensure_ascii=False, separators=(",", ":"), default=str),
                    json.dumps(row["quality_flags"], ensure_ascii=False, separators=(",", ":"), default=str),
                    run_id,
                ]
            )

        self.execute_copy_csv(
            """
            CREATE TEMP TABLE tmp_ta_rows (
              "time" DATE,
              ticker TEXT,
              base_ticker TEXT,
              segment_id INTEGER,
              values_jsonb JSONB,
              quality_flags JSONB,
              run_id UUID
            ) ON COMMIT DROP;
            """,
            """
            COPY tmp_ta_rows ("time", ticker, base_ticker, segment_id, values_jsonb, quality_flags, run_id)
            FROM STDIN WITH (FORMAT csv)
            """,
            csv_buffer.getvalue(),
            f"""
            INSERT INTO {table} ("time", ticker, base_ticker, segment_id, values_jsonb, quality_flags, run_id)
            SELECT "time", ticker, base_ticker, segment_id, values_jsonb, quality_flags, run_id
            FROM tmp_ta_rows
            ON CONFLICT ("time", ticker) DO UPDATE SET
              base_ticker = EXCLUDED.base_ticker,
              segment_id = EXCLUDED.segment_id,
              values_jsonb = EXCLUDED.values_jsonb,
              quality_flags = EXCLUDED.quality_flags,
              run_id = EXCLUDED.run_id,
              updated_at = now();
            INSERT INTO meta.lineage_event
              (target_table, target_key, source_table, source_key, run_id, transform_version, metadata_jsonb)
            SELECT
              {sql_literal(table)},
              ticker || ':' || "time"::text,
              {sql_literal(ADJUSTED_OHLCV_TABLE)},
              base_ticker || ':' || "time"::text,
              run_id,
              {sql_literal(TA_TRANSFORM_VERSION)},
              jsonb_build_object('stage', 'ta_indicator_compute', 'target_table', {sql_literal(table)})
            FROM tmp_ta_rows;
            """,
        )

    def copy_adjusted_ohlcv_rows(self, rows: list[dict[str, Any]], run_id: str) -> None:
        if not rows:
            return

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer, lineterminator="\n")
        for row in rows:
            writer.writerow(
                [
                    row["time"],
                    row["ticker"],
                    row["base_ticker"],
                    row["segment_id"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row["adj_open"],
                    row["adj_high"],
                    row["adj_low"],
                    row["adj_close"],
                    row["adj_volume"],
                    row["adjustment_factor"],
                    json.dumps(row["quality_flags"], ensure_ascii=False, separators=(",", ":"), default=str),
                    run_id,
                ]
            )

        self.execute_copy_csv(
            """
            CREATE TEMP TABLE tmp_adjusted_ohlcv (
              "time" DATE,
              ticker TEXT,
              base_ticker TEXT,
              segment_id INTEGER,
              open NUMERIC(20, 6),
              high NUMERIC(20, 6),
              low NUMERIC(20, 6),
              close NUMERIC(20, 6),
              volume NUMERIC(28, 6),
              adj_open NUMERIC(20, 6),
              adj_high NUMERIC(20, 6),
              adj_low NUMERIC(20, 6),
              adj_close NUMERIC(20, 6),
              adj_volume NUMERIC(28, 6),
              adjustment_factor NUMERIC(28, 12),
              quality_flags JSONB,
              run_id UUID
            ) ON COMMIT DROP;
            """,
            """
            COPY tmp_adjusted_ohlcv (
              "time", ticker, base_ticker, segment_id,
              open, high, low, close, volume,
              adj_open, adj_high, adj_low, adj_close, adj_volume,
              adjustment_factor, quality_flags, run_id
            )
            FROM STDIN WITH (FORMAT csv)
            """,
            csv_buffer.getvalue(),
            f"""
            INSERT INTO {ADJUSTED_OHLCV_TABLE} (
              "time", ticker, base_ticker, segment_id,
              open, high, low, close, volume,
              adj_open, adj_high, adj_low, adj_close, adj_volume,
              adjustment_factor, quality_flags, run_id
            )
            SELECT
              "time", ticker, base_ticker, segment_id,
              open, high, low, close, volume,
              adj_open, adj_high, adj_low, adj_close, adj_volume,
              adjustment_factor, quality_flags, run_id
            FROM tmp_adjusted_ohlcv
            ON CONFLICT ("time", ticker) DO UPDATE SET
              base_ticker = EXCLUDED.base_ticker,
              segment_id = EXCLUDED.segment_id,
              open = EXCLUDED.open,
              high = EXCLUDED.high,
              low = EXCLUDED.low,
              close = EXCLUDED.close,
              volume = EXCLUDED.volume,
              adj_open = EXCLUDED.adj_open,
              adj_high = EXCLUDED.adj_high,
              adj_low = EXCLUDED.adj_low,
              adj_close = EXCLUDED.adj_close,
              adj_volume = EXCLUDED.adj_volume,
              adjustment_factor = EXCLUDED.adjustment_factor,
              quality_flags = EXCLUDED.quality_flags,
              run_id = EXCLUDED.run_id,
              updated_at = now();
            INSERT INTO meta.lineage_event
              (target_table, target_key, source_table, source_key, run_id, transform_version, metadata_jsonb)
            SELECT
              {sql_literal(ADJUSTED_OHLCV_TABLE)},
              ticker || ':' || "time"::text,
              CASE
                WHEN quality_flags->>'adjusted_price_method' = 'kis_official_adjusted'
                THEN 'feature.kis_adjusted_ohlcv_daily'
                ELSE 'core.ohlcv_daily'
              END,
              base_ticker || ':' || "time"::text,
              run_id,
              {sql_literal(ADJUSTED_OHLCV_TRANSFORM_VERSION)},
              jsonb_build_object(
                'stage', 'adjusted_ohlcv_build',
                'adjusted_price_method', quality_flags->>'adjusted_price_method',
                'segment_id', segment_id
              )
            FROM tmp_adjusted_ohlcv;
            """,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute 10y TA indicators from local TimescaleDB OHLCV data.")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD. Defaults to min core.ohlcv_daily date.")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD. Defaults to max core.ohlcv_daily date.")
    parser.add_argument("--tickers", default="", help="Optional comma-separated ticker subset.")
    parser.add_argument("--limit-tickers", type=int, default=None, help="Optional deterministic ticker limit for smoke runs.")
    parser.add_argument(
        "--workers",
        type=int,
        default=resolve_worker_count(),
        help="Requested worker count; actual execution is capped by QUANT_TA_MAX_WORKERS.",
    )
    parser.add_argument("--ticker-batch-size", type=int, default=DEFAULT_TICKER_BATCH_SIZE)
    parser.add_argument("--flush-rows", type=int, default=DEFAULT_FLUSH_ROWS)
    parser.add_argument("--halt-ffill-days", type=int, default=DEFAULT_HALT_FFILL_DAYS)
    parser.add_argument("--relist-gap-days", type=int, default=DEFAULT_RELIST_GAP_DAYS)
    parser.add_argument("--disable-split-adjustment", action="store_true")
    parser.add_argument(
        "--input-price-source",
        choices=["core", "kis-adjusted"],
        default="core",
        help="core uses core.ohlcv_daily plus continuity adjustment; kis-adjusted uses feature.kis_adjusted_ohlcv_daily.",
    )
    parser.add_argument(
        "--db-mode",
        choices=["docker", "psycopg"],
        default=None,
        help="Database access mode. Defaults to psycopg when DB credentials are configured; otherwise docker.",
    )
    parser.add_argument("--db-container", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not write indicator rows.")
    parser.add_argument("--output", default=None, help="Optional JSON summary artifact path.")
    args = parser.parse_args()

    require_talib()

    config = DatabaseConfig.from_env()
    if args.db_container:
        config = DatabaseConfig(**{**config.__dict__, "docker_container": args.db_container})
    requested_db_mode = args.db_mode or os.getenv("QUANT_DB_EXECUTION_MODE")
    db_mode = resolve_execution_mode(config, requested_db_mode)
    client: TaDbClient = DockerPsqlClient(config) if db_mode == "docker" else PsycopgClient(config)
    workers = resolve_worker_count(args.workers)

    start_date, end_date = resolve_date_window(client, args.start_date, args.end_date)
    options = RuntimeOptions(
        start_date=start_date,
        end_date=end_date,
        halt_ffill_days=args.halt_ffill_days,
        relist_gap_days=args.relist_gap_days,
        adjust_splits=(not args.disable_split_adjustment) and args.input_price_source == "core",
        input_price_source=args.input_price_source,
    )

    run_id = str(uuid4())
    if not args.dry_run:
        ensure_feature_tables(client)
        start_run(client, run_id, args, start_date, end_date)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "dry_run": args.dry_run,
        "workers": workers,
        "ticker_batch_size": args.ticker_batch_size,
        "input_price_source": args.input_price_source,
        "adjusted_ohlcv_table": ADJUSTED_OHLCV_TABLE,
        "mart_feature_view": MART_FEATURE_VIEW,
        "adjusted_ohlcv_rows": 0,
        "stored_rows": {category: 0 for category in CATEGORY_TABLES},
        "processed_tickers": 0,
        "failed_tickers": [],
        "diagnostics": [],
    }

    try:
        tickers = select_tickers(client, start_date, end_date, args.tickers, args.limit_tickers)
        calendar = load_trading_calendar(client, start_date, end_date)
        listing_windows = load_listing_windows(client)

        pending_rows: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORY_TABLES}
        pending_adjusted_rows: list[dict[str, Any]] = []
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for batch in chunked(tickers, args.ticker_batch_size):
                frames = load_ohlcv_frames(client, start_date, end_date, batch, args.input_price_source)
                tasks = [
                    TickerTask(
                        ticker=ticker,
                        frame=frame,
                        calendar=calendar,
                        listing_windows=listing_windows.get(ticker, []),
                        options=options,
                    )
                    for ticker, frame in frames.items()
                ]
                futures = [executor.submit(process_ticker, task) for task in tasks]
                for future in as_completed(futures):
                    result = future.result()
                    summary["processed_tickers"] += 1
                    summary["diagnostics"].append(result.diagnostics)
                    pending_adjusted_rows.extend(result.adjusted_rows)
                    if len(pending_adjusted_rows) >= args.flush_rows:
                        if not args.dry_run:
                            client.copy_adjusted_ohlcv_rows(pending_adjusted_rows, run_id)
                        summary["adjusted_ohlcv_rows"] += len(pending_adjusted_rows)
                        pending_adjusted_rows.clear()
                    for category, rows in result.category_rows.items():
                        pending_rows[category].extend(rows)
                        if len(pending_rows[category]) >= args.flush_rows:
                            if not args.dry_run:
                                client.copy_category_rows(CATEGORY_TABLES[category], pending_rows[category], run_id)
                            summary["stored_rows"][category] += len(pending_rows[category])
                            pending_rows[category].clear()

        for category, rows in pending_rows.items():
            if rows:
                if not args.dry_run:
                    client.copy_category_rows(CATEGORY_TABLES[category], rows, run_id)
                summary["stored_rows"][category] += len(rows)
                rows.clear()

        if pending_adjusted_rows:
            if not args.dry_run:
                client.copy_adjusted_ohlcv_rows(pending_adjusted_rows, run_id)
            summary["adjusted_ohlcv_rows"] += len(pending_adjusted_rows)
            pending_adjusted_rows.clear()

        if not args.dry_run:
            record_mart_lineage(client, run_id, start_date, end_date)
            finish_run(client, run_id, "success", None)
    except Exception as exc:
        if not args.dry_run:
            finish_run(client, run_id, "failed", str(exc))
        raise

    text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


def require_talib() -> None:
    try:
        import talib  # noqa: F401
    except ImportError as exc:
        raise SystemExit("TA-Lib is required as the core indicator engine.") from exc


def resolve_date_window(client: DockerPsqlClient, raw_start: str | None, raw_end: str | None) -> tuple[date, date]:
    rows = client.fetch_csv(
        """
        SELECT min(trade_date)::text AS min_date, max(trade_date)::text AS max_date
          FROM core.ohlcv_daily
        """
    )
    if rows.empty or pd.isna(rows.iloc[0]["min_date"]) or pd.isna(rows.iloc[0]["max_date"]):
        raise RuntimeError("core.ohlcv_daily has no OHLCV rows.")
    start = date.fromisoformat(raw_start or str(rows.iloc[0]["min_date"]))
    end = date.fromisoformat(raw_end or str(rows.iloc[0]["max_date"]))
    if end < start:
        raise ValueError("--end-date must be greater than or equal to --start-date.")
    return start, end


def ensure_feature_tables(client: DockerPsqlClient) -> None:
    table_statements = []
    adjusted_table_statement = f"""
            CREATE TABLE IF NOT EXISTS {ADJUSTED_OHLCV_TABLE} (
              "time" DATE NOT NULL,
              ticker TEXT NOT NULL,
              base_ticker TEXT NOT NULL,
              segment_id INTEGER NOT NULL DEFAULT 1,
              open NUMERIC(20, 6),
              high NUMERIC(20, 6),
              low NUMERIC(20, 6),
              close NUMERIC(20, 6),
              volume NUMERIC(28, 6),
              adj_open NUMERIC(20, 6),
              adj_high NUMERIC(20, 6),
              adj_low NUMERIC(20, 6),
              adj_close NUMERIC(20, 6),
              adj_volume NUMERIC(28, 6),
              adjustment_factor NUMERIC(28, 12) NOT NULL DEFAULT 1,
              quality_flags JSONB NOT NULL DEFAULT '{{}}'::jsonb,
              run_id UUID REFERENCES meta.ingestion_run(run_id),
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY ("time", ticker)
            );
            SELECT create_hypertable('{ADJUSTED_OHLCV_TABLE}', 'time', if_not_exists => TRUE);
            CREATE INDEX IF NOT EXISTS idx_feature_adjusted_ohlcv_daily_base_ticker_time
              ON {ADJUSTED_OHLCV_TABLE} (base_ticker, "time" DESC);
            """
    for table in CATEGORY_TABLES.values():
        table_statements.append(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
              "time" DATE NOT NULL,
              ticker TEXT NOT NULL,
              base_ticker TEXT NOT NULL,
              segment_id INTEGER NOT NULL DEFAULT 1,
              values_jsonb JSONB NOT NULL,
              quality_flags JSONB NOT NULL DEFAULT '{{}}'::jsonb,
              run_id UUID REFERENCES meta.ingestion_run(run_id),
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY ("time", ticker)
            );
            SELECT create_hypertable('{table}', 'time', if_not_exists => TRUE);
            CREATE INDEX IF NOT EXISTS idx_{table.replace('.', '_')}_ticker_time
              ON {table} (ticker, "time" DESC);
            """
        )
    client.execute(
        """
        CREATE SCHEMA IF NOT EXISTS feature;
        CREATE SCHEMA IF NOT EXISTS mart;
        ALTER TABLE meta.lineage_event ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB NOT NULL DEFAULT '{{}}'::jsonb;
        INSERT INTO meta.data_source (source_id, name, base_url_key, version, is_primary)
        VALUES ('TA', 'TA-Lib technical indicator transform', 'TA_TRANSFORM_VERSION', 'pandas-ta-talib-v1', FALSE)
        ON CONFLICT (source_id) DO UPDATE SET
          name = EXCLUDED.name,
          version = EXCLUDED.version,
          updated_at = now();
        """
        + adjusted_table_statement
        + "\n".join(table_statements)
        + mart_feature_view_sql()
    )


def start_run(
    client: DockerPsqlClient,
    run_id: str,
    args: argparse.Namespace,
    start_date: date,
    end_date: date,
) -> None:
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "tickers": args.tickers,
        "limit_tickers": args.limit_tickers,
        "workers": args.workers,
        "ticker_batch_size": args.ticker_batch_size,
        "halt_ffill_days": args.halt_ffill_days,
        "relist_gap_days": args.relist_gap_days,
        "adjust_splits": not args.disable_split_adjustment,
        "adjusted_ohlcv_table": ADJUSTED_OHLCV_TABLE,
        "table_contract": 'PRIMARY KEY ("time", ticker)',
    }
    client.execute(
        f"""
        INSERT INTO meta.ingestion_run
          (run_id, dag_id, task_id, source_id, started_at, status, params_jsonb)
        VALUES
          ('{run_id}', 'manual_ta_indicator_pipeline', 'compute_technical_indicators_pipeline',
           '{TA_SOURCE_ID}', now(), 'running', '{json.dumps(params, ensure_ascii=False)}'::jsonb);
        """
    )


def finish_run(client: DockerPsqlClient, run_id: str, status: str, error: str | None) -> None:
    error_sql = "NULL" if error is None else "'" + error.replace("'", "''")[:4000] + "'"
    client.execute(
        f"""
        UPDATE meta.ingestion_run
           SET status = '{status}', ended_at = now(), error_message = {error_sql}
         WHERE run_id = '{run_id}';
        """
    )


def mart_feature_view_sql() -> str:
    return f"""
        CREATE OR REPLACE VIEW {CANONICAL_SYMBOL_FEATURE_VIEW} AS
        SELECT
            a."time" AS as_of_date,
            sm.symbol,
            sm.name,
            sm.market_segment,
            sm.listing_status,
            sm.listed_at,
            sm.delisted_at,
            a.ticker,
            a.base_ticker,
            a.segment_id,
            a.adj_open AS open,
            a.adj_high AS high,
            a.adj_low AS low,
            a.adj_close AS close,
            a.adj_volume AS volume,
            a.quality_flags AS adjusted_ohlcv_quality_flags,
            tt.values_jsonb AS trend_values,
            tm.values_jsonb AS momentum_values,
            tv.values_jsonb AS volatility_values,
            tvol.values_jsonb AS volume_values,
            tp.values_jsonb AS pattern_values,
            a.run_id AS adjusted_ohlcv_run_id,
            sm.sector
        FROM {ADJUSTED_OHLCV_TABLE} a
        JOIN core.symbol_master sm ON sm.symbol = a.base_ticker
        LEFT JOIN {CATEGORY_TABLES["Trend"]} tt
               ON tt.ticker = a.ticker AND tt."time" = a."time"
        LEFT JOIN {CATEGORY_TABLES["Momentum"]} tm
               ON tm.ticker = a.ticker AND tm."time" = a."time"
        LEFT JOIN {CATEGORY_TABLES["Volatility"]} tv
               ON tv.ticker = a.ticker AND tv."time" = a."time"
        LEFT JOIN {CATEGORY_TABLES["Volume"]} tvol
               ON tvol.ticker = a.ticker AND tvol."time" = a."time"
        LEFT JOIN {CATEGORY_TABLES["Pattern"]} tp
               ON tp.ticker = a.ticker AND tp."time" = a."time";

        CREATE OR REPLACE VIEW {MART_FEATURE_VIEW} AS
        SELECT *
          FROM {CANONICAL_SYMBOL_FEATURE_VIEW}
         WHERE adjusted_ohlcv_quality_flags->>'adjusted_price_method' = 'kis_official_adjusted';
        """


def record_mart_lineage(client: DockerPsqlClient, run_id: str, start_date: date, end_date: date) -> None:
    client.execute(
        f"""
        INSERT INTO meta.lineage_event
          (target_table, target_key, source_table, source_key, run_id, transform_version, metadata_jsonb)
        SELECT
          {sql_literal(MART_FEATURE_VIEW)},
          ticker || ':' || "time"::text,
          {sql_literal(ADJUSTED_OHLCV_TABLE)},
          ticker || ':' || "time"::text,
          {sql_literal(run_id)},
          'mart-view-lineage-v1',
          jsonb_build_object('stage', 'mart_feature_view', 'view_type', 'logical_view')
          FROM {ADJUSTED_OHLCV_TABLE}
         WHERE "time" BETWEEN DATE {sql_literal(start_date.isoformat())}
                          AND DATE {sql_literal(end_date.isoformat())}
           AND run_id = {sql_literal(run_id)};
        """
    )


def select_tickers(
    client: DockerPsqlClient,
    start_date: date,
    end_date: date,
    raw_tickers: str,
    limit: int | None,
) -> list[str]:
    requested = [item.strip() for item in raw_tickers.split(",") if item.strip()]
    where = [
        f"o.trade_date BETWEEN DATE '{start_date.isoformat()}' AND DATE '{end_date.isoformat()}'",
    ]
    if requested:
        quoted = ", ".join("'" + item.replace("'", "''") + "'" for item in requested)
        where.append(f"sm.symbol IN ({quoted})")
    limit_sql = f" LIMIT {int(limit)}" if limit else ""
    rows = client.fetch_csv(
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
    return [normalize_ticker(item) for item in rows["ticker"].tolist()]


def load_trading_calendar(client: DockerPsqlClient, start_date: date, end_date: date) -> list[pd.Timestamp]:
    rows = client.fetch_csv(
        f"""
        SELECT DISTINCT trade_date AS "time"
          FROM core.ohlcv_daily
         WHERE trade_date BETWEEN DATE '{start_date.isoformat()}' AND DATE '{end_date.isoformat()}'
         ORDER BY trade_date
        """,
        parse_dates=["time"],
    )
    return [pd.Timestamp(item).normalize() for item in rows["time"].tolist()]


def load_listing_windows(client: DockerPsqlClient) -> dict[str, list[dict[str, Any]]]:
    rows = client.fetch_csv(
        """
        SELECT sm.symbol AS ticker,
               h.valid_from::text AS valid_from,
               h.valid_to::text AS valid_to,
               h.listing_status
          FROM core.symbol_listing_history h
          JOIN core.symbol_master sm ON sm.symbol_id = h.symbol_id
         ORDER BY sm.symbol, h.valid_from
        """
    )
    out: dict[str, list[dict[str, Any]]] = {}
    if rows.empty:
        return out
    for row in rows.to_dict("records"):
        out.setdefault(str(row["ticker"]), []).append(row)
    return out


def load_ohlcv_frames(
    client: DockerPsqlClient,
    start_date: date,
    end_date: date,
    tickers: list[str],
    input_price_source: str,
) -> dict[str, pd.DataFrame]:
    if not tickers:
        return {}
    quoted = ", ".join("'" + item.replace("'", "''") + "'" for item in tickers)
    if input_price_source == "kis-adjusted":
        query = f"""
        SELECT ticker,
               NULL::bigint AS symbol_id,
               "time",
               adj_open AS open,
               adj_high AS high,
               adj_low AS low,
               adj_close AS close,
               adj_volume AS volume,
               TRUE AS is_tradable,
               quality_flags::text AS quality_flags
          FROM feature.kis_adjusted_ohlcv_daily
         WHERE "time" BETWEEN DATE '{start_date.isoformat()}' AND DATE '{end_date.isoformat()}'
           AND ticker IN ({quoted})
         ORDER BY ticker, "time"
        """
    else:
        query = f"""
        SELECT sm.symbol AS ticker,
               o.symbol_id,
               o.trade_date AS "time",
               o.open,
               o.high,
               o.low,
               o.close,
               o.volume,
               o.is_tradable,
               o.quality_flags::text AS quality_flags
          FROM core.ohlcv_daily o
          JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
         WHERE o.trade_date BETWEEN DATE '{start_date.isoformat()}' AND DATE '{end_date.isoformat()}'
           AND sm.symbol IN ({quoted})
         ORDER BY sm.symbol, o.trade_date
        """
    rows = client.fetch_csv(
        query,
        parse_dates=["time"],
    )
    frames = {}
    rows["ticker"] = rows["ticker"].map(normalize_ticker)
    for ticker, frame in rows.groupby("ticker", sort=True):
        frames[normalize_ticker(ticker)] = frame.drop(columns=["ticker"]).copy()
    return frames


def normalize_ticker(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) < 6:
        return text.zfill(6)
    return text


def process_ticker(task: TickerTask) -> TickerResult:
    frame, diagnostics = preprocess_ticker_frame(task)
    adjusted_rows = adjusted_frame_to_rows(frame, task.ticker)
    category_frames = compute_indicator_frames(frame)
    category_rows = {
        category: indicator_frame_to_rows(
            category=category,
            values=values,
            prepared=frame,
            base_ticker=task.ticker,
        )
        for category, values in category_frames.items()
    }
    return TickerResult(
        ticker=task.ticker,
        category_rows=category_rows,
        adjusted_rows=adjusted_rows,
        diagnostics=diagnostics,
    )


def preprocess_ticker_frame(task: TickerTask) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = task.frame.copy()
    raw["time"] = pd.to_datetime(raw["time"]).dt.normalize()
    raw = raw.sort_values("time").drop_duplicates("time", keep="last").set_index("time")
    for column in ("open", "high", "low", "close", "volume"):
        raw[column] = pd.to_numeric(raw[column], errors="coerce")

    calendar = pd.DatetimeIndex(task.calendar, name="time")
    frame = raw.reindex(calendar)
    frame["base_ticker"] = task.ticker

    segments = listing_segments(task, frame)
    frame["segment_id"] = np.nan
    for segment_id, (start, end) in enumerate(segments, start=1):
        mask = (frame.index >= start) & (frame.index <= end)
        frame.loc[mask, "segment_id"] = segment_id
    frame = frame[frame["segment_id"].notna()].copy()
    frame["segment_id"] = frame["segment_id"].astype(int)
    frame["effective_ticker"] = np.where(
        frame.groupby("segment_id")["segment_id"].transform("count").notna() & (frame["segment_id"].max() > 1),
        task.ticker + "#S" + frame["segment_id"].astype(str).str.zfill(2),
        task.ticker,
    )

    frame["halt_filled"] = False
    frame = fill_short_halts(frame, task.options.halt_ffill_days)
    if task.options.input_price_source == "kis-adjusted":
        split_events = []
        frame["adjustment_factor"] = 1.0
        for column in ("open", "high", "low", "close", "volume"):
            frame[f"adj_{column}"] = frame[column]
    elif task.options.adjust_splits:
        frame, split_events = apply_adjusted_price_continuity(frame)
    else:
        split_events = []
        frame["adjustment_factor"] = 1.0
        for column in ("open", "high", "low", "close", "volume"):
            frame[f"adj_{column}"] = frame[column]

    diagnostics = {
        "ticker": task.ticker,
        "segments": len(segments),
        "rows_after_listing_filter": int(len(frame)),
        "halt_filled_rows": int(frame["halt_filled"].sum()),
        "split_adjustment_events": split_events,
        "input_price_source": task.options.input_price_source,
        "min_time": frame.index.min().date().isoformat() if not frame.empty else None,
        "max_time": frame.index.max().date().isoformat() if not frame.empty else None,
    }
    return frame, diagnostics


def listing_segments(task: TickerTask, frame: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if task.listing_windows:
        segments = []
        for row in task.listing_windows:
            start = pd.Timestamp(row["valid_from"]).normalize()
            valid_to = row.get("valid_to")
            end = pd.Timestamp(valid_to).normalize() if valid_to and not pd.isna(valid_to) else pd.Timestamp(task.options.end_date)
            start = max(start, pd.Timestamp(task.options.start_date))
            end = min(end, pd.Timestamp(task.options.end_date))
            if start <= end:
                segments.append((start, end))
        if segments:
            return segments

    observed = frame[["open", "high", "low", "close", "volume"]].dropna(how="all")
    if observed.empty:
        return []
    observed_dates = list(observed.index)
    segments: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start = observed_dates[0]
    previous = observed_dates[0]
    for current in observed_dates[1:]:
        gap = int(frame.loc[previous:current].shape[0]) - 1
        if gap > task.options.relist_gap_days:
            segments.append((start, previous))
            start = current
        previous = current
    segments.append((start, previous))
    return segments


def fill_short_halts(frame: pd.DataFrame, halt_days: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = frame.copy()
    price_columns = ["open", "high", "low", "close", "volume"]
    observed_mask = output[price_columns].notna().any(axis=1)
    zero_or_untradable = (output["volume"].fillna(0) <= 0) | (output["is_tradable"].fillna(True) == False)  # noqa: E712
    gap_mask = (~observed_mask) | zero_or_untradable

    for segment_id, segment in output.groupby("segment_id", sort=True):
        consecutive: list[pd.Timestamp] = []
        for timestamp, is_gap in gap_mask.loc[segment.index].items():
            if bool(is_gap):
                consecutive.append(timestamp)
                continue
            if 0 < len(consecutive) <= halt_days:
                previous_position = output.index.get_loc(consecutive[0]) - 1
                if previous_position >= 0:
                    previous_values = output.iloc[previous_position][price_columns]
                    output.loc[consecutive, price_columns] = previous_values.values
                    output.loc[consecutive, "halt_filled"] = True
            consecutive = []
        if 0 < len(consecutive) <= halt_days:
            previous_position = output.index.get_loc(consecutive[0]) - 1
            if previous_position >= 0:
                previous_values = output.iloc[previous_position][price_columns]
                output.loc[consecutive, price_columns] = previous_values.values
                output.loc[consecutive, "halt_filled"] = True
    return output


def apply_adjusted_price_continuity(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    output = frame.copy()
    output["adjustment_factor"] = 1.0
    events: list[dict[str, Any]] = []

    for segment_id, segment in output.groupby("segment_id", sort=True):
        close = segment["close"].dropna()
        previous_close = close.shift(1)
        ratios = close / previous_close
        event_dates = ratios[(ratios <= 0.55) | (ratios >= 1.8)].dropna()
        for timestamp, ratio in event_dates.items():
            if not math.isfinite(float(ratio)) or float(ratio) <= 0:
                continue
            before_mask = (output["segment_id"] == segment_id) & (output.index < timestamp)
            output.loc[before_mask, "adjustment_factor"] *= float(ratio)
            events.append(
                {
                    "time": timestamp.date().isoformat(),
                    "segment_id": int(segment_id),
                    "ratio": float(ratio),
                    "rule": "close_to_previous_close_continuity",
                }
            )

    for column in ("open", "high", "low", "close"):
        output[f"adj_{column}"] = output[column] * output["adjustment_factor"]
    output["adj_volume"] = output["volume"] / output["adjustment_factor"].replace(0, np.nan)
    return output, events


def compute_indicator_frames(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    ta_input = pd.DataFrame(
        {
            "open": frame["adj_open"],
            "high": frame["adj_high"],
            "low": frame["adj_low"],
            "close": frame["adj_close"],
            "volume": frame["adj_volume"],
        },
        index=frame.index,
    )

    return {
        "Trend": combine_outputs(
            ta_input,
            [
                ("sma", {"length": 20, "talib": True}),
                ("sma", {"length": 50, "talib": True}),
                ("sma", {"length": 200, "talib": True}),
                ("ema", {"length": 20, "talib": True}),
                ("ema", {"length": 50, "talib": True}),
                ("ema", {"length": 200, "talib": True}),
                ("macd", {"fast": 12, "slow": 26, "signal": 9, "talib": True}),
                ("adx", {"length": 14, "talib": True}),
                ("aroon", {"length": 25, "talib": True}),
            ],
        ),
        "Momentum": combine_outputs(
            ta_input,
            [
                ("rsi", {"length": 14, "talib": True}),
                ("stoch", {"k": 14, "d": 3, "smooth_k": 3, "talib": True}),
                ("cci", {"length": 20, "talib": True}),
                ("roc", {"length": 10, "talib": True}),
                ("willr", {"length": 14, "talib": True}),
                ("mfi", {"length": 14, "talib": True}),
            ],
        ),
        "Volatility": combine_outputs(
            ta_input,
            [
                ("atr", {"length": 14, "talib": True}),
                ("natr", {"length": 14, "talib": True}),
                ("bbands", {"length": 20, "std": 2, "talib": True}),
            ],
        ),
        "Volume": combine_outputs(
            ta_input,
            [
                ("obv", {"talib": True}),
                ("ad", {"talib": True}),
                ("adosc", {"fast": 3, "slow": 10, "talib": True}),
                ("cmf", {"length": 20}),
            ],
        ),
        "Pattern": combine_outputs(
            ta_input,
            [
                ("cdl_pattern", {"name": PATTERN_NAMES}),
            ],
        ),
    }


def combine_outputs(frame: pd.DataFrame, calls: list[tuple[str, dict[str, Any]]]) -> pd.DataFrame:
    outputs = []
    for method_name, kwargs in calls:
        method = getattr(frame.ta, method_name)
        result = method(**kwargs)
        if result is None:
            continue
        if isinstance(result, pd.Series):
            outputs.append(result.to_frame())
        else:
            outputs.append(result)
    if not outputs:
        return pd.DataFrame(index=frame.index)
    combined = pd.concat(outputs, axis=1)
    combined = combined.loc[:, ~combined.columns.duplicated()].copy()
    return combined.replace([np.inf, -np.inf], np.nan)


def indicator_frame_to_rows(
    *,
    category: str,
    values: pd.DataFrame,
    prepared: pd.DataFrame,
    base_ticker: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if values.empty:
        return rows

    for timestamp, row in values.iterrows():
        clean_values = {
            str(name): scalar_to_json(value)
            for name, value in row.dropna().items()
            if scalar_to_json(value) is not None
        }
        if not clean_values:
            continue
        prepared_row = prepared.loc[timestamp]
        quality_flags = {
            "category": category,
            "base_ticker": base_ticker,
            "segment_id": int(prepared_row["segment_id"]),
            "halt_filled": bool(prepared_row.get("halt_filled", False)),
        }
        adjustment_factor = scalar_to_json(prepared_row.get("adjustment_factor", 1.0))
        if adjustment_factor not in (None, 1.0):
            quality_flags["adjustment_factor"] = adjustment_factor
        rows.append(
            {
                "time": timestamp.date().isoformat(),
                "ticker": str(prepared_row["effective_ticker"]),
                "base_ticker": base_ticker,
                "segment_id": int(prepared_row["segment_id"]),
                "values": clean_values,
                "quality_flags": quality_flags,
            }
        )
    return rows


def adjusted_frame_to_rows(prepared: pd.DataFrame, base_ticker: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if prepared.empty:
        return rows

    value_columns = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adj_open",
        "adj_high",
        "adj_low",
        "adj_close",
        "adj_volume",
        "adjustment_factor",
    )
    for timestamp, row in prepared.iterrows():
        if all(scalar_to_json(row.get(column)) is None for column in ("adj_open", "adj_high", "adj_low", "adj_close")):
            continue
        adjusted_price_method = (
            "kis_official_adjusted"
            if str(row.get("quality_flags", "")).find("kis_official_adjusted") >= 0
            else "close_ratio_back_adjustment"
        )
        quality_flags = {
            "base_ticker": base_ticker,
            "segment_id": int(row["segment_id"]),
            "halt_filled": bool(row.get("halt_filled", False)),
            "adjusted_price_method": adjusted_price_method,
        }
        adjustment_factor = scalar_to_json(row.get("adjustment_factor", 1.0))
        if adjustment_factor not in (None, 1.0):
            quality_flags["adjustment_factor"] = adjustment_factor
        output = {
            "time": timestamp.date().isoformat(),
            "ticker": str(row["effective_ticker"]),
            "base_ticker": base_ticker,
            "segment_id": int(row["segment_id"]),
            "quality_flags": quality_flags,
        }
        for column in value_columns:
            output[column] = scalar_to_json(row.get(column))
        rows.append(output)
    return rows


def scalar_to_json(value: Any) -> float | int | str | bool | None:
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (int, str, bool)):
        return value
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return str(value)
    return converted if math.isfinite(converted) else None


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def chunked(items: list[str], size: int) -> Iterable[list[str]]:
    if size < 1:
        raise ValueError("chunk size must be >= 1")
    for index in range(0, len(items), size):
        yield items[index : index + size]


if __name__ == "__main__":
    raise SystemExit(main())
