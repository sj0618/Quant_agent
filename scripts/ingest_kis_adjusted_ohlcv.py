"""Collect KIS official adjusted OHLCV and store it in TimescaleDB.

KIS ``inquire-daily-itemchartprice`` uses ``FID_ORG_ADJ_PRC=0`` for adjusted
prices and returns at most 100 rows per request in the official sample code.
This script therefore slices long windows and stores adjusted rows separately
from the KRX-sourced ``core.ohlcv_daily`` table.

Secrets are read only from process environment. This script never loads
``.env`` files.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import csv
from dataclasses import dataclass
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import DatabaseConfig, KisConfig  # noqa: E402
from quant_agent.data.sources.kis import KisOhlcvClient, normalize_kis_daily_price  # noqa: E402


KIS_ADJUSTED_TABLE = "feature.kis_adjusted_ohlcv_daily"
KIS_SOURCE_ID = "KIS"
DEFAULT_REQUEST_WINDOW_DAYS = 120
DEFAULT_REQUEST_SLEEP_SECONDS = 0.25
DEFAULT_FLUSH_ROWS = 10_000
DEFAULT_TOKEN_RETRY_WAIT_SECONDS = 65


@dataclass(frozen=True)
class FetchWindow:
    start_date: date
    end_date: date


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
COMMIT;
"""
        self.execute(sql)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest KIS official adjusted OHLCV into TimescaleDB.")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
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
    parser.add_argument("--db-mode", choices=["docker"], default="docker")
    parser.add_argument("--db-container", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise ValueError("--end-date must be greater than or equal to --start-date.")
    if args.request_window_days < 1:
        raise ValueError("--request-window-days must be >= 1.")
    if args.flush_rows < 1:
        raise ValueError("--flush-rows must be >= 1.")

    db_config = DatabaseConfig.from_env()
    if args.db_container:
        db_config = DatabaseConfig(**{**db_config.__dict__, "docker_container": args.db_container})
    db = DockerPsqlClient(db_config)
    kis_client = KisOhlcvClient(KisConfig.from_env())

    run_id = str(uuid4())
    ensure_tables(db)
    start_run(db, run_id, args, start_date, end_date)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "table": KIS_ADJUSTED_TABLE,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "request_window_days": args.request_window_days,
        "request_sleep_seconds": args.request_sleep_seconds,
        "workers": args.workers,
        "tickers": 0,
        "requests": 0,
        "rows": 0,
        "failed_windows": [],
    }

    pending_rows: list[dict[str, Any]] = []
    try:
        tickers = select_tickers(db, start_date, end_date, args.tickers, args.limit_tickers)
        summary["tickers"] = len(tickers)
        if args.workers == 1:
            for ticker, window in iter_fetch_jobs(tickers, start_date, end_date, args.request_window_days):
                if args.max_requests is not None and summary["requests"] >= args.max_requests:
                    flush_rows(db, pending_rows, run_id, summary)
                    finish_run(db, run_id, "partial_success", None)
                    write_output(args.output, summary)
                    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
                    return 0
                fetch_and_collect(kis_client, ticker, window, pending_rows, summary, args.request_sleep_seconds)
                if len(pending_rows) >= args.flush_rows:
                    flush_rows(db, pending_rows, run_id, summary)
        else:
            issue_token_with_retry(kis_client)
            run_parallel_fetches(
                kis_client=kis_client,
                jobs=iter_fetch_jobs(tickers, start_date, end_date, args.request_window_days),
                pending_rows=pending_rows,
                summary=summary,
                max_requests=args.max_requests,
                workers=args.workers,
                request_sleep_seconds=args.request_sleep_seconds,
                flush=lambda: flush_rows(db, pending_rows, run_id, summary),
                flush_threshold=args.flush_rows,
            )

        flush_rows(db, pending_rows, run_id, summary)
        finish_run(db, run_id, "success" if not summary["failed_windows"] else "partial_success", None)
    except Exception as exc:
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


def fetch_and_collect(
    kis_client: KisOhlcvClient,
    ticker: str,
    window: FetchWindow,
    pending_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    request_sleep_seconds: float,
) -> None:
    try:
        rows, request_count = fetch_adjusted_rows_recursive(kis_client, ticker, window)
        summary["requests"] += request_count
        pending_rows.extend(rows)
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


def flush_rows(db: DockerPsqlClient, rows: list[dict[str, Any]], run_id: str, summary: dict[str, Any]) -> None:
    if not rows:
        return
    db.copy_adjusted_rows(rows, run_id)
    summary["rows"] += len(rows)
    rows.clear()


def write_output(path: str | None, summary: dict[str, Any]) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def normalize_ticker(value: Any) -> str:
    text = str(value).strip()
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


if __name__ == "__main__":
    raise SystemExit(main())
