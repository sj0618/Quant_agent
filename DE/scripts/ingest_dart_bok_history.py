"""Schema-first OpenDART/BOK ingestion into the local PostgreSQL feature DB.

This script intentionally performs no ``CREATE`` or ``ALTER`` statements.
It scans the live target table definitions first, maps API-normalized rows to
the scanned columns, and writes with ``ON CONFLICT DO NOTHING``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Iterable, Sequence
from uuid import UUID, uuid4

try:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - exercised only in incomplete local envs.
    psycopg = None
    sql = None
    dict_row = None
    Jsonb = None


def jsonb_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.catalogs import (  # noqa: E402
    BOK_SERIES_PRESETS as SHARED_BOK_SERIES_PRESETS,
    DART_REPORT_DISCLOSURE_MONTH_DAY,
    DART_REPORT_CODE_PERIOD_END as SHARED_DART_REPORT_CODE_PERIOD_END,
)
from quant_agent.data.config import BokConfig, DartConfig  # noqa: E402
from quant_agent.data.models import RawSourcePayload  # noqa: E402
from quant_agent.data.sources.bok import BokEcosClient, normalize_bok_observations  # noqa: E402
from quant_agent.data.sources.dart import (  # noqa: E402
    OpenDartClient,
    normalize_corp_code_zip,
    normalize_financial_statement,
)
from quant_agent.data.sources.base import SourceResponseError  # noqa: E402


DEFAULT_DB_HOST = "127.0.0.1"
DEFAULT_DB_PORT = 5432
DEFAULT_DB_NAME = "quant_agent"
DEFAULT_DB_USER = "quant_agent"
DEFAULT_TEST_LOOKBACK_DAYS = 30
DEFAULT_FULL_START_DATE = date(2016, 1, 1)
DEFAULT_DAILY_LOOKBACK_DAYS = 7
DEFAULT_BOK_WINDOW_DAYS = 366
DEFAULT_REQUEST_SLEEP_SECONDS = 0.2
DEFAULT_DART_TEST_MAX_COMPANIES = 5
DEFAULT_DART_FS_DIV = "CFS"
DEFAULT_DART_NO_DATA_STATUS_CODES = frozenset({"013"})
BOK_SERIES_ENV_NAMES = ("BOK_SERIES_JSON", "BOK_DAILY_SERIES_JSON")
DART_SYMBOLS_ENV_NAME = "DART_SYMBOLS"

BOK_SERIES_PRESETS = SHARED_BOK_SERIES_PRESETS
DART_REPORT_CODE_PERIOD_END = SHARED_DART_REPORT_CODE_PERIOD_END

DATA_SOURCE_ROWS = {
    "BOK": ("Bank of Korea ECOS", "BOK_BASE_URL", False),
    "DART": ("OpenDART Financial Supervisory Service", "DART_BASE_URL", False),
}


class SchemaMappingError(RuntimeError):
    """Raised when the scanned DB schema cannot accept normalized API rows."""


@dataclass(frozen=True)
class TableColumn:
    name: str
    data_type: str
    udt_name: str
    is_nullable: bool
    column_default: str | None
    ordinal_position: int
    identity_generation: str | None = None

    @property
    def has_server_value(self) -> bool:
        return bool(self.column_default or self.identity_generation)


@dataclass(frozen=True)
class TableSchema:
    schema_name: str
    table_name: str
    columns: tuple[TableColumn, ...]
    primary_key: tuple[str, ...]
    unique_constraints: tuple[tuple[str, ...], ...]

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}"

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def column(self, name: str) -> TableColumn:
        for column in self.columns:
            if column.name == name:
                return column
        raise KeyError(name)

    def as_log_dict(self) -> dict[str, Any]:
        return {
            "table": self.qualified_name,
            "columns": [
                {
                    "name": column.name,
                    "data_type": column.data_type,
                    "udt_name": column.udt_name,
                    "nullable": column.is_nullable,
                    "has_server_value": column.has_server_value,
                }
                for column in self.columns
            ],
            "primary_key": list(self.primary_key),
            "unique_constraints": [list(item) for item in self.unique_constraints],
        }


@dataclass(frozen=True)
class BokSeriesConfig:
    stat_code: str
    cycle: str
    item_code1: str
    language: str = "kr"
    limit: int = 10000


@dataclass(frozen=True)
class DartReportPeriod:
    business_year: int
    report_code: str
    period_end: date


@dataclass(frozen=True)
class DartUniverseEntry:
    symbol: str
    corp_code: str
    symbol_id: int


@dataclass
class SourceStats:
    api_calls: int = 0
    raw_payloads_attempted: int = 0
    raw_payloads_inserted: int = 0
    rows_seen: int = 0
    rows_inserted: int = 0
    rows_skipped: int = 0
    no_data_responses: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "api_calls": self.api_calls,
            "raw_payloads_attempted": self.raw_payloads_attempted,
            "raw_payloads_inserted": self.raw_payloads_inserted,
            "rows_seen": self.rows_seen,
            "rows_inserted": self.rows_inserted,
            "rows_skipped": self.rows_skipped,
            "no_data_responses": self.no_data_responses,
            "errors": self.errors,
        }


@dataclass
class RunStats:
    scope: str
    start_date: date
    end_date: date
    dry_run: bool
    schema_snapshot: dict[str, Any] = field(default_factory=dict)
    bok: SourceStats = field(default_factory=SourceStats)
    dart: SourceStats = field(default_factory=SourceStats)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "date_window": {"start_date": self.start_date.isoformat(), "end_date": self.end_date.isoformat()},
            "dry_run": self.dry_run,
            "schema_snapshot": self.schema_snapshot,
            "bok": self.bok.as_dict(),
            "dart": self.dart.as_dict(),
        }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    start_date, end_date = resolve_date_window(args)
    stats = RunStats(scope=args.scope, start_date=start_date, end_date=end_date, dry_run=args.dry_run)

    with connect_db() as conn:
        schemas = scan_required_schemas(conn)
        stats.schema_snapshot = {key: value.as_log_dict() for key, value in schemas.items()}

        if args.validate_schema_only:
            write_output(args.output, stats.as_dict())
            return 0

        if args.sources in {"both", "bok"}:
            run_id = start_ingestion_run(
                conn,
                dag_id=args.dag_id,
                task_id="ingest_bok_history",
                source_id="BOK",
                params=run_params(args, start_date, end_date),
                dry_run=args.dry_run,
            )
            try:
                ingest_bok_history(conn, args, start_date, end_date, run_id, schemas, stats.bok)
                finish_ingestion_run(conn, run_id, "success", None, args.dry_run)
            except Exception as exc:
                finish_ingestion_run(conn, run_id, "failed", str(exc), args.dry_run)
                raise

        if args.sources in {"both", "dart"}:
            run_id = start_ingestion_run(
                conn,
                dag_id=args.dag_id,
                task_id="ingest_dart_history",
                source_id="DART",
                params=run_params(args, start_date, end_date),
                dry_run=args.dry_run,
            )
            try:
                ingest_dart_history(conn, args, start_date, end_date, run_id, schemas, stats.dart)
                finish_ingestion_run(conn, run_id, "success", None, args.dry_run)
            except Exception as exc:
                finish_ingestion_run(conn, run_id, "failed", str(exc), args.dry_run)
                raise

    write_output(args.output, stats.as_dict())
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load OpenDART/BOK data into existing feature tables after scanning the live DB schema."
    )
    parser.add_argument("--scope", choices=["test-1m", "full-10y", "daily", "custom"], default="custom")
    parser.add_argument("--sources", choices=["both", "bok", "dart"], default="both")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--output")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-schema-only", action="store_true")
    parser.add_argument("--dag-id", default=os.getenv("QUANT_DAG_ID", "manual_dart_bok_history_ingestion"))

    parser.add_argument("--bok-series-json", default=None)
    parser.add_argument(
        "--bok-series-preset",
        choices=sorted(BOK_SERIES_PRESETS),
        default=os.getenv("BOK_SERIES_PRESET"),
        help="Built-in BOK series set. Use 'rate-fx' for interest-rate and FX indicators.",
    )
    parser.add_argument("--bok-window-days", type=int, default=int(os.getenv("BOK_WINDOW_DAYS", str(DEFAULT_BOK_WINDOW_DAYS))))
    parser.add_argument(
        "--bok-request-sleep-seconds",
        type=float,
        default=float(os.getenv("BOK_REQUEST_SLEEP_SECONDS", str(DEFAULT_REQUEST_SLEEP_SECONDS))),
    )

    parser.add_argument("--dart-symbols", default=os.getenv(DART_SYMBOLS_ENV_NAME))
    parser.add_argument("--dart-report-years", default=None)
    parser.add_argument("--dart-report-codes", default=None)
    parser.add_argument("--dart-fs-div", default=os.getenv("DART_FS_DIV", DEFAULT_DART_FS_DIV))
    parser.add_argument(
        "--dart-skip-existing",
        action="store_true",
        default=os.getenv("DART_SKIP_EXISTING", "false").lower() == "true",
        help="Skip DART company/period jobs whose feature rows already exist; do not use for restatement refreshes.",
    )
    parser.add_argument(
        "--dart-refresh-existing",
        action="store_true",
        help="Override --dart-skip-existing and refetch existing periods so filing restatements are retained.",
    )
    parser.add_argument(
        "--dart-period-mode",
        choices=["period-end", "filing-window"],
        default=None,
        help="period-end uses financial period_end; filing-window uses configured disclosure-date windows.",
    )
    parser.add_argument("--dart-refresh-corp-codes", action="store_true", default=os.getenv("DART_REFRESH_CORP_CODES", "false").lower() == "true")
    parser.add_argument("--max-dart-companies", type=int, default=_optional_int(os.getenv("DART_MAX_COMPANIES")))
    parser.add_argument(
        "--dart-request-sleep-seconds",
        type=float,
        default=float(os.getenv("DART_REQUEST_SLEEP_SECONDS", str(DEFAULT_REQUEST_SLEEP_SECONDS))),
    )
    parser.add_argument(
        "--dart-no-data-status-codes",
        default=os.getenv("DART_NO_DATA_STATUS_CODES", ",".join(sorted(DEFAULT_DART_NO_DATA_STATUS_CODES))),
    )
    return parser.parse_args(argv)


def connect_db() -> Any:
    if psycopg is None or dict_row is None:
        raise RuntimeError("psycopg[binary] is required for PostgreSQL ingestion.")
    dsn = os.getenv("QUANT_DB_DSN") or os.getenv("DATABASE_URL")
    if dsn:
        try:
            return psycopg.connect(dsn, row_factory=dict_row)
        except Exception as exc:
            raise SystemExit(f"PostgreSQL connection failed via DSN/DATABASE_URL: {exc}") from exc

    params: dict[str, Any] = {
        "host": os.getenv("QUANT_DB_HOST", DEFAULT_DB_HOST),
        "port": int(os.getenv("QUANT_DB_PORT", str(DEFAULT_DB_PORT))),
        "dbname": os.getenv("QUANT_DB_NAME", DEFAULT_DB_NAME),
        "user": os.getenv("QUANT_DB_USER", DEFAULT_DB_USER),
        "row_factory": dict_row,
    }
    password = os.getenv("QUANT_DB_PASSWORD") or os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD")
    if password:
        params["password"] = password
    try:
        return psycopg.connect(**params)
    except Exception as exc:
        raise SystemExit(
            "PostgreSQL connection failed. Set QUANT_DB_DSN/DATABASE_URL or "
            "QUANT_DB_PASSWORD/PGPASSWORD/POSTGRES_PASSWORD for host "
            f"{params['host']}:{params['port']} db={params['dbname']} user={params['user']}: {exc}"
        ) from exc


def scan_required_schemas(conn: psycopg.Connection) -> dict[str, TableSchema]:
    required = {
        "feature.bok_macro_daily": ("feature", "bok_macro_daily"),
        "feature.dart_financial_quarterly": ("feature", "dart_financial_quarterly"),
        "feature.dart_financial_filing": ("feature", "dart_financial_filing"),
        "feature.dart_financial_account_value": ("feature", "dart_financial_account_value"),
    }
    optional = {
        "raw.bok_response": ("raw", "bok_response"),
        "raw.dart_response": ("raw", "dart_response"),
        "feature.dart_corp_symbol_map": ("feature", "dart_corp_symbol_map"),
        "meta.data_source": ("meta", "data_source"),
        "meta.ingestion_run": ("meta", "ingestion_run"),
    }
    schemas = {}
    for key, (schema_name, table_name) in {**required, **optional}.items():
        table_schema = scan_table_schema(conn, schema_name, table_name, required=key in required)
        if table_schema is not None:
            schemas[key] = table_schema
    assert_target_columns(
        schemas["feature.bok_macro_daily"],
        {"series_id", "effective_date", "available_from", "value"},
    )
    assert_target_columns(
        schemas["feature.dart_financial_quarterly"],
        {"symbol_id", "corp_code", "period_end", "available_from", "report_code", "fs_div", "accounts_jsonb"},
    )
    return schemas


def scan_table_schema(
    conn: psycopg.Connection, schema_name: str, table_name: str, *, required: bool
) -> TableSchema | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name,
                   data_type,
                   udt_name,
                   is_nullable,
                   column_default,
                   ordinal_position,
                   identity_generation
              FROM information_schema.columns
             WHERE table_schema = %s
               AND table_name = %s
             ORDER BY ordinal_position;
            """,
            (schema_name, table_name),
        )
        column_rows = cur.fetchall()
        if not column_rows:
            if required:
                raise SchemaMappingError(f"Required table {schema_name}.{table_name} does not exist.")
            return None
        cur.execute(
            """
            SELECT tc.constraint_type,
                   array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON tc.constraint_schema = kcu.constraint_schema
               AND tc.constraint_name = kcu.constraint_name
               AND tc.table_schema = kcu.table_schema
               AND tc.table_name = kcu.table_name
             WHERE tc.table_schema = %s
               AND tc.table_name = %s
               AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
             GROUP BY tc.constraint_name, tc.constraint_type
             ORDER BY tc.constraint_type, tc.constraint_name;
            """,
            (schema_name, table_name),
        )
        constraints = cur.fetchall()
    columns = tuple(
        TableColumn(
            name=str(row["column_name"]),
            data_type=str(row["data_type"]),
            udt_name=str(row["udt_name"]),
            is_nullable=str(row["is_nullable"]).upper() == "YES",
            column_default=row["column_default"],
            ordinal_position=int(row["ordinal_position"]),
            identity_generation=row["identity_generation"],
        )
        for row in column_rows
    )
    primary_key = tuple(
        str(column)
        for row in constraints
        if row["constraint_type"] == "PRIMARY KEY"
        for column in row["columns"]
    )
    unique_constraints = tuple(
        tuple(str(column) for column in row["columns"])
        for row in constraints
        if row["constraint_type"] == "UNIQUE"
    )
    return TableSchema(schema_name, table_name, columns, primary_key, unique_constraints)


def assert_target_columns(table_schema: TableSchema, required_columns: set[str]) -> None:
    missing = sorted(required_columns - set(table_schema.column_names))
    if missing:
        raise SchemaMappingError(
            f"{table_schema.qualified_name} is missing required ingestion columns: {', '.join(missing)}. "
            "Schema change may be required on local and server DBs before ingestion."
        )


def resolve_date_window(args: argparse.Namespace) -> tuple[date, date]:
    end_date = date.fromisoformat(args.end_date) if args.end_date else date.today()
    if args.start_date:
        start_date = date.fromisoformat(args.start_date)
    elif args.scope == "test-1m":
        start_date = end_date - timedelta(days=DEFAULT_TEST_LOOKBACK_DAYS)
    elif args.scope == "full-10y":
        start_date = date.fromisoformat(os.getenv("DART_BOK_FULL_START_DATE", DEFAULT_FULL_START_DATE.isoformat()))
    elif args.scope == "daily":
        start_date = end_date - timedelta(days=int(os.getenv("DART_BOK_DAILY_LOOKBACK_DAYS", str(DEFAULT_DAILY_LOOKBACK_DAYS))))
    else:
        raise SystemExit("--start-date is required when --scope custom is used.")
    if start_date > end_date:
        raise SystemExit("start_date must be before or equal to end_date.")
    return start_date, end_date


def run_params(args: argparse.Namespace, start_date: date, end_date: date) -> dict[str, Any]:
    return {
        "scope": args.scope,
        "sources": args.sources,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "dry_run": args.dry_run,
        "dart_period_mode": resolve_dart_period_mode(args),
        "dart_skip_existing": args.dart_skip_existing and not args.dart_refresh_existing,
        "dart_refresh_existing": args.dart_refresh_existing,
        "max_dart_companies": args.max_dart_companies,
        "bok_series_preset": args.bok_series_preset,
    }


def start_ingestion_run(
    conn: psycopg.Connection,
    *,
    dag_id: str,
    task_id: str,
    source_id: str,
    params: dict[str, Any],
    dry_run: bool,
) -> UUID | None:
    if dry_run:
        return None
    run_id = uuid4()
    ensure_data_source(conn, source_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meta.ingestion_run
              (run_id, dag_id, task_id, source_id, started_at, status, params_jsonb)
            VALUES (%s, %s, %s, %s, %s, 'running', %s)
            ON CONFLICT DO NOTHING;
            """,
            (run_id, dag_id, task_id, source_id, datetime.now(timezone.utc), Jsonb(params, dumps=jsonb_dumps)),
        )
    conn.commit()
    return run_id


def ensure_data_source(conn: psycopg.Connection, source_id: str) -> None:
    if source_id not in DATA_SOURCE_ROWS:
        return
    name, base_url_key, is_primary = DATA_SOURCE_ROWS[source_id]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meta.data_source (source_id, name, base_url_key, version, is_primary)
            VALUES (%s, %s, %s, 'v1', %s)
            ON CONFLICT DO NOTHING;
            """,
            (source_id, name, base_url_key, is_primary),
        )


def finish_ingestion_run(
    conn: psycopg.Connection, run_id: UUID | None, status: str, error_message: str | None, dry_run: bool
) -> None:
    if dry_run or run_id is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE meta.ingestion_run
               SET ended_at = now(),
                   status = %s,
                   error_message = %s
             WHERE run_id = %s;
            """,
            (status, error_message, run_id),
        )
    conn.commit()


def ingest_bok_history(
    conn: psycopg.Connection,
    args: argparse.Namespace,
    start_date: date,
    end_date: date,
    run_id: UUID | None,
    schemas: dict[str, TableSchema],
    stats: SourceStats,
) -> None:
    series_configs = load_bok_series_configs(args.bok_series_json, args.bok_series_preset)
    client = BokEcosClient(BokConfig.from_env())
    for series in series_configs:
        for window_start, window_end in chunk_date_range(start_date, end_date, args.bok_window_days):
            raw_payload = client.fetch_statistic_search(
                stat_code=series.stat_code,
                cycle=series.cycle,
                start_period=format_bok_period(window_start, series.cycle),
                end_period=format_bok_period(window_end, series.cycle),
                item_code1=series.item_code1,
                language=series.language,
                limit=series.limit,
            )
            stats.api_calls += 1
            stats.raw_payloads_attempted += 1
            raw_inserted = insert_raw_payload(conn, schemas.get("raw.bok_response"), raw_payload, run_id, dry_run=args.dry_run)
            stats.raw_payloads_inserted += raw_inserted

            rows = normalize_bok_observations(raw_payload)
            stats.rows_seen += len(rows)
            candidate_rows = [
                {
                    "series_id": row["series_id"],
                    "effective_date": row["effective_date"],
                    "published_at": row.get("published_at"),
                    "available_from": row["available_from"],
                    "value": row.get("value"),
                    "metadata_jsonb": row.get("metadata", {}),
                    "run_id": run_id,
                }
                for row in rows
            ]
            stats.rows_inserted += insert_rows(
                conn,
                schemas["feature.bok_macro_daily"],
                candidate_rows,
                dry_run=args.dry_run,
                commit=True,
            )
            time.sleep(args.bok_request_sleep_seconds)


def load_bok_series_configs(raw_cli_json: str | None, preset: str | None = None) -> list[BokSeriesConfig]:
    if preset:
        return [
            BokSeriesConfig(
                stat_code=str(item["stat_code"]),
                cycle=str(item["cycle"]).upper(),
                item_code1=str(item["item_code1"]),
                language=str(item.get("language", "kr")),
                limit=int(item.get("limit", 10000)),
            )
            for item in BOK_SERIES_PRESETS[preset]
        ]
    raw = raw_cli_json
    if raw is None:
        raw = next((os.getenv(name) for name in BOK_SERIES_ENV_NAMES if os.getenv(name)), None)
    if not raw:
        raise SystemExit(
            "BOK series configuration is required. Set BOK_SERIES_JSON or BOK_DAILY_SERIES_JSON "
            'to a JSON list such as [{"stat_code":"722Y001","cycle":"D","item_code1":"0101000"}].'
        )
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        preview = raw[:160].replace("\n", "\\n").replace("\r", "\\r")
        raise SystemExit(
            "BOK series configuration is not valid JSON. "
            "Use --bok-series-preset rate-fx for the recommended rate/FX set, or set BOK_SERIES_JSON as one-line JSON. "
            f"JSON error at line {exc.lineno} column {exc.colno} char {exc.pos}. "
            f"Value preview: {preview!r}"
        ) from exc
    if not isinstance(loaded, list):
        raise SystemExit("BOK series configuration must be a JSON list.")
    configs = []
    for item in loaded:
        if not isinstance(item, dict):
            raise SystemExit("Each BOK series item must be a JSON object.")
        for required in ("stat_code", "cycle", "item_code1"):
            if not item.get(required):
                raise SystemExit(f"BOK series item is missing {required}: {item}")
        configs.append(
            BokSeriesConfig(
                stat_code=str(item["stat_code"]),
                cycle=str(item["cycle"]).upper(),
                item_code1=str(item["item_code1"]),
                language=str(item.get("language", "kr")),
                limit=int(item.get("limit", 10000)),
            )
        )
    return configs


def ingest_dart_history(
    conn: psycopg.Connection,
    args: argparse.Namespace,
    start_date: date,
    end_date: date,
    run_id: UUID | None,
    schemas: dict[str, TableSchema],
    stats: SourceStats,
) -> None:
    client = OpenDartClient(DartConfig.from_env())
    corp_rows = normalize_corp_code_zip(client.fetch_corp_codes())
    stats.api_calls += 1

    if args.dart_refresh_corp_codes and "feature.dart_corp_symbol_map" in schemas:
        stats.rows_inserted += insert_corp_code_rows(
            conn,
            schemas["feature.dart_corp_symbol_map"],
            corp_rows,
            run_id,
            dry_run=args.dry_run,
        )

    universe = resolve_dart_universe(conn, corp_rows, parse_symbol_list(args.dart_symbols))
    max_companies = resolve_max_dart_companies(args)
    if max_companies is not None:
        universe = universe[:max_companies]

    report_periods = resolve_dart_report_periods(args, start_date, end_date)
    existing_feature_keys = (
        load_existing_dart_feature_keys(conn, schemas["feature.dart_financial_quarterly"])
        if args.dart_skip_existing and not args.dart_refresh_existing
        else set()
    )
    no_data_status_codes = {item.strip() for item in args.dart_no_data_status_codes.split(",") if item.strip()}

    for company, period in iter_resumable_dart_jobs(
        universe,
        report_periods,
        args.dart_fs_div,
        existing_feature_keys,
        skip_existing=args.dart_skip_existing and not args.dart_refresh_existing,
        stats=stats,
    ):
        raw_payload = client.fetch_financial_statement(
            corp_code=company.corp_code,
            business_year=period.business_year,
            report_code=period.report_code,
            fs_div=args.dart_fs_div,
        )
        stats.api_calls += 1
        stats.raw_payloads_attempted += 1
        stats.raw_payloads_inserted += insert_raw_payload(
            conn, schemas.get("raw.dart_response"), raw_payload, run_id, dry_run=args.dry_run
        )

        status = str(raw_payload.payload.get("status", "")).strip()
        if status and status != "000":
            message = str(raw_payload.payload.get("message", ""))
            if status in no_data_status_codes:
                stats.no_data_responses += 1
                time.sleep(args.dart_request_sleep_seconds)
                continue
            error = f"DART status={status} symbol={company.symbol} corp_code={company.corp_code}: {message}"
            stats.errors.append(error)
            raise SourceResponseError(error)

        rows = normalize_financial_statement(raw_payload, symbol=company.symbol, period_end=period.period_end)
        stats.rows_seen += len(rows)
        candidate_rows = [
            {
                "symbol_id": company.symbol_id,
                "corp_code": row["corp_code"],
                "period_end": row["period_end"],
                "reported_at": row.get("reported_at"),
                "available_from": row.get("available_from"),
                "filing_id": row.get("filing_id") or f"payload:{stable_hash(raw_payload.payload)}",
                "source_payload_hash": stable_hash(raw_payload.payload),
                "availability_policy": "source_filing_date" if row.get("reported_at") else "conservative_report_deadline",
                "report_code": row["report_code"],
                "fs_div": row["fs_div"],
                "accounts_jsonb": row.get("accounts", {}),
                "run_id": run_id,
            }
            for row in rows
        ]
        stats.rows_inserted += upsert_rows(
            conn,
            schemas["feature.dart_financial_quarterly"],
            candidate_rows,
            dry_run=args.dry_run,
            commit=True,
        )
        filing_rows = [
            {
                "symbol_id": company.symbol_id,
                "corp_code": row["corp_code"],
                "period_end": row["period_end"],
                "available_from": row["available_from"],
                "reported_at": row.get("reported_at"),
                "report_code": row["report_code"],
                "fs_div": row["fs_div"],
                "filing_id": row.get("filing_id") or f"payload:{stable_hash(raw_payload.payload)}",
                "source_payload_hash": stable_hash(raw_payload.payload),
                "availability_policy": "source_filing_date" if row.get("reported_at") else "conservative_report_deadline",
                "accounts_jsonb": row.get("accounts", {}),
                "run_id": run_id,
            }
            for row in rows
        ]
        stats.rows_inserted += insert_rows(
            conn,
            schemas["feature.dart_financial_filing"],
            filing_rows,
            dry_run=args.dry_run,
            commit=True,
        )
        if not args.dry_run:
            account_rows = []
            payload_hash = stable_hash(raw_payload.payload)
            for row in rows:
                filing_version_id = find_filing_version_id(
                    conn,
                    symbol_id=company.symbol_id,
                    period_end=row["period_end"],
                    report_code=row["report_code"],
                    fs_div=row["fs_div"],
                    source_payload_hash=payload_hash,
                )
                for account in row.get("account_rows", []):
                    account_rows.append(
                        {
                            "filing_version_id": filing_version_id,
                            "account_id": account["account_id"],
                            "account_name": account.get("account_name"),
                            "statement_code": account.get("statement_code"),
                            "amount": account.get("amount"),
                            "current_cumulative_amount": account.get("current_cumulative_amount"),
                            "prior_quarter_amount": account.get("prior_quarter_amount"),
                            "prior_amount": account.get("prior_amount"),
                            "prior_year_amount": account.get("prior_year_amount"),
                            "currency": account.get("currency"),
                            "raw_jsonb": account.get("raw", {}),
                        }
                    )
            stats.rows_inserted += insert_rows(
                conn,
                schemas["feature.dart_financial_account_value"],
                account_rows,
                dry_run=False,
                commit=True,
            )
        time.sleep(args.dart_request_sleep_seconds)


def load_existing_dart_feature_keys(
    conn: psycopg.Connection,
    table_schema: TableSchema,
) -> set[tuple[int, date, str, str]]:
    query = sql.SQL("SELECT symbol_id, period_end, report_code, fs_div FROM {}").format(
        sql.SQL(".").join([sql.Identifier(table_schema.schema_name), sql.Identifier(table_schema.table_name)])
    )
    keys: set[tuple[int, date, str, str]] = set()
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur.fetchall():
            keys.add(
                (
                    int(row["symbol_id"]),
                    row["period_end"],
                    str(row["report_code"]),
                    str(row["fs_div"]),
                )
            )
    return keys


def find_filing_version_id(
    conn: psycopg.Connection,
    *,
    symbol_id: int,
    period_end: date,
    report_code: str,
    fs_div: str,
    source_payload_hash: str,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT filing_version_id
              FROM feature.dart_financial_filing
             WHERE symbol_id = %s
               AND period_end = %s
               AND report_code = %s
               AND fs_div = %s
               AND source_payload_hash = %s
            """,
            (symbol_id, period_end, report_code, fs_div, source_payload_hash),
        )
        row = cur.fetchone()
    if not row:
        raise SchemaMappingError("DART filing version was not found after idempotent insert.")
    return int(row["filing_version_id"])


def iter_resumable_dart_jobs(
    universe: list[DartUniverseEntry],
    report_periods: list[DartReportPeriod],
    fs_div: str,
    existing_feature_keys: set[tuple[int, date, str, str]],
    *,
    skip_existing: bool,
    stats: SourceStats,
) -> Iterable[tuple[DartUniverseEntry, DartReportPeriod]]:
    for company in universe:
        for period in report_periods:
            feature_key = (company.symbol_id, period.period_end, period.report_code, fs_div)
            if skip_existing and feature_key in existing_feature_keys:
                stats.rows_skipped += 1
                continue
            yield company, period


def insert_corp_code_rows(
    conn: psycopg.Connection,
    table_schema: TableSchema,
    corp_rows: list[dict[str, str]],
    run_id: UUID | None,
    *,
    dry_run: bool,
) -> int:
    candidate_rows = [
        {
            "corp_code": row.get("corp_code"),
            "corp_name": row.get("corp_name"),
            "symbol": row.get("stock_code"),
            "modify_date": row.get("modify_date"),
            "run_id": run_id,
        }
        for row in corp_rows
        if row.get("stock_code")
    ]
    return insert_rows(conn, table_schema, candidate_rows, dry_run=dry_run, commit=True)


def resolve_dart_universe(
    conn: psycopg.Connection,
    corp_rows: list[dict[str, str]],
    requested_symbols: set[str] | None,
) -> list[DartUniverseEntry]:
    corp_by_symbol = {
        normalize_symbol(row.get("stock_code")): str(row.get("corp_code", "")).strip()
        for row in corp_rows
        if normalize_symbol(row.get("stock_code")) and row.get("corp_code")
    }
    symbol_ids = fetch_symbol_ids(conn, sorted(requested_symbols) if requested_symbols else None)
    universe = []
    for symbol, symbol_id in sorted(symbol_ids.items()):
        corp_code = corp_by_symbol.get(symbol)
        if corp_code:
            universe.append(DartUniverseEntry(symbol=symbol, corp_code=corp_code, symbol_id=symbol_id))
    return universe


def fetch_symbol_ids(conn: psycopg.Connection, symbols: list[str] | None) -> dict[str, int]:
    with conn.cursor() as cur:
        if symbols:
            cur.execute(
                "SELECT symbol, symbol_id FROM core.symbol_master WHERE symbol = ANY(%s) ORDER BY symbol;",
                (symbols,),
            )
        else:
            cur.execute("SELECT symbol, symbol_id FROM core.symbol_master ORDER BY symbol;")
        rows = cur.fetchall()
    return {normalize_symbol(row["symbol"]): int(row["symbol_id"]) for row in rows if normalize_symbol(row["symbol"])}


def resolve_dart_report_periods(
    args: argparse.Namespace,
    start_date: date,
    end_date: date,
) -> list[DartReportPeriod]:
    report_codes = parse_report_codes(args.dart_report_codes)
    if args.dart_report_years:
        years = parse_years(args.dart_report_years)
        return [
            DartReportPeriod(year, report_code, period_end_for_report(year, report_code))
            for year in years
            for report_code in report_codes
        ]

    mode = resolve_dart_period_mode(args)
    start_year = start_date.year - 1 if mode == "filing-window" else start_date.year
    end_year = end_date.year
    periods = []
    for year in range(start_year, end_year + 1):
        for report_code in report_codes:
            period_end = period_end_for_report(year, report_code)
            if mode == "period-end":
                include = start_date <= period_end <= end_date
            else:
                filing_date = expected_disclosure_date(year, report_code)
                include = start_date <= filing_date <= end_date
            if include and period_end <= end_date:
                periods.append(DartReportPeriod(year, report_code, period_end))
    return sorted(set(periods), key=lambda item: (item.business_year, item.report_code))


def resolve_dart_period_mode(args: argparse.Namespace) -> str:
    if args.dart_period_mode:
        return args.dart_period_mode
    if args.scope in {"test-1m", "daily"}:
        return "filing-window"
    return "period-end"


def resolve_max_dart_companies(args: argparse.Namespace) -> int | None:
    if args.max_dart_companies is not None:
        return args.max_dart_companies
    if args.scope == "test-1m":
        return int(os.getenv("DART_TEST_MAX_COMPANIES", str(DEFAULT_DART_TEST_MAX_COMPANIES)))
    return None


def insert_raw_payload(
    conn: psycopg.Connection,
    table_schema: TableSchema | None,
    raw_payload: RawSourcePayload,
    run_id: UUID | None,
    *,
    dry_run: bool,
) -> int:
    if table_schema is None:
        return 0
    source = raw_payload.source.upper()
    payload_hash = stable_hash(raw_payload.payload)
    if source == "BOK":
        row = {
            "stat_code": raw_payload.request.get("stat_code"),
            "item_code": raw_payload.request.get("item_code1"),
            "payload_hash": payload_hash,
            "payload_jsonb": raw_payload.payload,
            "run_id": run_id,
        }
    elif source == "DART":
        row = {
            "corp_code": raw_payload.request.get("corp_code"),
            "report_code": raw_payload.request.get("reprt_code"),
            "business_year": raw_payload.request.get("bsns_year"),
            "fs_div": raw_payload.request.get("fs_div"),
            "request_date": raw_payload.request_date,
            "payload_hash": payload_hash,
            "payload_jsonb": raw_payload.payload,
            "run_id": run_id,
        }
    else:
        return 0
    return insert_rows(conn, table_schema, [row], dry_run=dry_run, commit=True)


def insert_rows(
    conn: Any,
    table_schema: TableSchema,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool,
    commit: bool,
) -> int:
    if not rows:
        return 0
    insertable_rows = []
    columns = [column for column in table_schema.columns if any(column.name in row for row in rows) and not column.identity_generation]
    for row in rows:
        validate_required_values(table_schema, row)
        insertable_rows.append(tuple(convert_value_for_column(row.get(column.name), column) for column in columns))

    if dry_run:
        return 0
    if sql is None:
        raise RuntimeError("psycopg is required for PostgreSQL insertion.")
    query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
        sql.Identifier(table_schema.schema_name),
        sql.Identifier(table_schema.table_name),
        sql.SQL(", ").join(sql.Identifier(column.name) for column in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    with conn.cursor() as cur:
        cur.executemany(query, insertable_rows)
        inserted = max(cur.rowcount, 0)
    if commit:
        conn.commit()
    return inserted


def upsert_rows(
    conn: Any,
    table_schema: TableSchema,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool,
    commit: bool,
) -> int:
    """Upsert a scanned table while retaining the schema-drift safety checks."""

    if not rows:
        return 0
    insertable_rows = []
    columns = [
        column
        for column in table_schema.columns
        if any(column.name in row for row in rows) and not column.identity_generation
    ]
    for row in rows:
        validate_required_values(table_schema, row)
        insertable_rows.append(tuple(convert_value_for_column(row.get(column.name), column) for column in columns))

    if dry_run:
        return 0
    if sql is None:
        raise RuntimeError("psycopg is required for PostgreSQL insertion.")
    primary_key = tuple(table_schema.primary_key)
    if not primary_key:
        raise SchemaMappingError(f"{table_schema.qualified_name} requires a primary key for upsert.")
    missing_primary_key = sorted(set(primary_key) - {column.name for column in columns})
    if missing_primary_key:
        raise SchemaMappingError(
            f"{table_schema.qualified_name} upsert is missing primary-key columns: {', '.join(missing_primary_key)}."
        )
    update_columns = [column for column in columns if column.name not in primary_key]
    if update_columns:
        conflict_action = sql.SQL("DO UPDATE SET {} ").format(
            sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column.name), sql.Identifier(column.name))
                for column in update_columns
            )
        )
    else:
        conflict_action = sql.SQL("DO NOTHING")
    query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT ({}) {};").format(
        sql.Identifier(table_schema.schema_name),
        sql.Identifier(table_schema.table_name),
        sql.SQL(", ").join(sql.Identifier(column.name) for column in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.SQL(", ").join(sql.Identifier(column) for column in primary_key),
        conflict_action,
    )
    with conn.cursor() as cur:
        cur.executemany(query, insertable_rows)
        upserted = max(cur.rowcount, 0)
    if commit:
        conn.commit()
    return upserted


def validate_required_values(table_schema: TableSchema, row: dict[str, Any]) -> None:
    missing = []
    for column in table_schema.columns:
        if column.has_server_value or column.is_nullable:
            continue
        if column.name not in row or row[column.name] is None:
            missing.append(column.name)
    if missing:
        raise SchemaMappingError(
            f"{table_schema.qualified_name} requires values for non-null columns without defaults: "
            f"{', '.join(sorted(missing))}. Schema mapping or DB schema alignment is required."
        )


def convert_value_for_column(value: Any, column: TableColumn) -> Any:
    if value is None:
        return None
    if column.udt_name in {"json", "jsonb"}:
        if Jsonb is None:
            raise RuntimeError("psycopg is required for JSONB value adaptation.")
        return Jsonb(value, dumps=jsonb_dumps)
    if column.udt_name in {"date"}:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return date.fromisoformat(str(value)[:10])
    if column.udt_name in {"timestamp", "timestamptz"} or "timestamp" in column.data_type:
        if isinstance(value, datetime):
            return value
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    if column.udt_name in {"numeric", "decimal"}:
        return decimal_or_none(value)
    if column.udt_name in {"int2", "int4", "int8"}:
        return int(value)
    if column.udt_name == "bool":
        return bool(value)
    if column.udt_name == "uuid":
        return value if isinstance(value, UUID) else UUID(str(value))
    return value


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or str(value).strip() in {"", "-"}:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation as exc:
        raise SchemaMappingError(f"Cannot convert value to Decimal: {value}") from exc


def chunk_date_range(start_date: date, end_date: date, window_days: int) -> Iterable[tuple[date, date]]:
    if window_days < 1:
        raise ValueError("window_days must be positive.")
    cursor = start_date
    while cursor <= end_date:
        chunk_end = min(end_date, cursor + timedelta(days=window_days - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def format_bok_period(value: date, cycle: str) -> str:
    normalized = cycle.upper()
    if normalized == "D":
        return value.strftime("%Y%m%d")
    if normalized == "M":
        return value.strftime("%Y%m")
    if normalized == "Q":
        quarter = ((value.month - 1) // 3) + 1
        return f"{value.year}Q{quarter}"
    if normalized in {"A", "Y"}:
        return f"{value.year}"
    return value.strftime("%Y%m%d")


def parse_symbol_list(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    symbols = {normalize_symbol(item) for item in raw.split(",") if normalize_symbol(item)}
    return symbols or None


def normalize_symbol(value: Any) -> str:
    text = str(value or "").strip()
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def parse_report_codes(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return tuple(DART_REPORT_CODE_PERIOD_END)
    codes = tuple(item.strip() for item in raw.split(",") if item.strip())
    unknown = sorted(set(codes) - set(DART_REPORT_CODE_PERIOD_END))
    if unknown:
        raise SystemExit(f"Unsupported DART report code(s): {', '.join(unknown)}")
    return codes


def parse_years(raw: str) -> list[int]:
    years: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            years.update(range(int(start_text), int(end_text) + 1))
        else:
            years.add(int(item))
    return sorted(years)


def period_end_for_report(business_year: int, report_code: str) -> date:
    month, day = DART_REPORT_CODE_PERIOD_END[report_code]
    return date(business_year, month, day)


def expected_disclosure_date(business_year: int, report_code: str) -> date:
    year_offset, month, day = DART_REPORT_DISCLOSURE_MONTH_DAY[report_code]
    return date(business_year + year_offset, month, day)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def write_output(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


if __name__ == "__main__":
    raise SystemExit(main())
