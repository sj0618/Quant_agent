from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


AI_DATABASE_DSN_ENV = "AI_DATABASE_DSN"
AI_DEFAULT_TICKER_ENV = "AI_DEFAULT_TICKER"
AI_BACKTEST_LOOKBACK_DAYS_ENV = "AI_BACKTEST_LOOKBACK_DAYS"
AI_L4_EVIDENCE_LIMIT_ENV = "AI_L4_EVIDENCE_LIMIT"
AI_DB_CONNECT_TIMEOUT_SECONDS_ENV = "AI_DB_CONNECT_TIMEOUT_SECONDS"
AI_DB_STATEMENT_TIMEOUT_MS_ENV = "AI_DB_STATEMENT_TIMEOUT_MS"

DEFAULT_BACKTEST_TICKER = "005930"
TRADING_DAYS_PER_YEAR = 252
DEFAULT_BACKTEST_LOOKBACK_YEARS = 10
DEFAULT_BACKTEST_LOOKBACK_DAYS = TRADING_DAYS_PER_YEAR * DEFAULT_BACKTEST_LOOKBACK_YEARS
DEFAULT_L4_EVIDENCE_LIMIT = 5
DEFAULT_DB_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_DB_STATEMENT_TIMEOUT_MS = 10_000
POSTGRES_TIMEOUT_UNIT = "ms"
BACKTEST_LOOKBACK_CALENDAR_DAY_MULTIPLIER = 3
RSI_OVERSOLD_THRESHOLD = 30.0

KIS_FEATURE_FRAME_VIEW = "mart.kis_adjusted_feature_frame_asof"
KIS_ADJUSTED_OHLCV_TABLE = "feature.kis_adjusted_ohlcv_daily"
TA_MOMENTUM_TICKER_TABLE = "feature.ta_momentum_ticker_daily"
UNIVERSE_VIEW = "meta.view_common_stock_universe"
ANALYST_REPORT_TABLE = "raw.analyst_report_summary"
BOK_MACRO_VIEW = "mart.bok_macro_asof"

TICKER_PATTERN = re.compile(r"\b\d{6}\b")
RSI_KEYS = ("rsi", "RSI", "rsi_14", "RSI_14", "talib_rsi_14", "TA_RSI_14")


class DataSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_dsn: str | None = None
    default_ticker: str = Field(default=DEFAULT_BACKTEST_TICKER, min_length=6, max_length=6)
    backtest_lookback_days: int = Field(default=DEFAULT_BACKTEST_LOOKBACK_DAYS, gt=0)
    l4_evidence_limit: int = Field(default=DEFAULT_L4_EVIDENCE_LIMIT, gt=0)
    connect_timeout_seconds: int = Field(default=DEFAULT_DB_CONNECT_TIMEOUT_SECONDS, gt=0)
    statement_timeout_ms: int = Field(default=DEFAULT_DB_STATEMENT_TIMEOUT_MS, gt=0)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "DataSourceConfig":
        env = environ or os.environ
        return cls(
            database_dsn=_blank_to_none(env.get(AI_DATABASE_DSN_ENV)),
            default_ticker=env.get(AI_DEFAULT_TICKER_ENV, DEFAULT_BACKTEST_TICKER),
            backtest_lookback_days=_int_env(
                env, AI_BACKTEST_LOOKBACK_DAYS_ENV, DEFAULT_BACKTEST_LOOKBACK_DAYS
            ),
            l4_evidence_limit=_int_env(
                env, AI_L4_EVIDENCE_LIMIT_ENV, DEFAULT_L4_EVIDENCE_LIMIT
            ),
            connect_timeout_seconds=_int_env(
                env, AI_DB_CONNECT_TIMEOUT_SECONDS_ENV, DEFAULT_DB_CONNECT_TIMEOUT_SECONDS
            ),
            statement_timeout_ms=_int_env(
                env, AI_DB_STATEMENT_TIMEOUT_MS_ENV, DEFAULT_DB_STATEMENT_TIMEOUT_MS
            ),
        )


class PipelineDataBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_rows: list[dict[str, Any]] = Field(default_factory=list)
    l4_evidence: list[dict[str, Any]] = Field(default_factory=list)
    macro_snapshot: dict[str, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PostgresPipelineDataSource:
    def __init__(self, config: DataSourceConfig) -> None:
        if not config.database_dsn:
            raise ValueError(f"{AI_DATABASE_DSN_ENV} is required for PostgreSQL data source")
        self.config = config

    def load(self, query: str, trace_id: str) -> PipelineDataBundle:
        with self._connect() as conn:
            self._set_statement_timeout(conn)
            ticker = self._resolve_ticker(conn, query)
            universe = self._fetch_universe_status(conn, ticker)
            price_rows, effective_lookback_days = self._fetch_price_rows(
                conn, ticker, universe, query
            )
            if not price_rows:
                raise ValueError(f"{KIS_ADJUSTED_OHLCV_TABLE} returned no price rows for {ticker}")
            l4_evidence = self._fetch_l4_evidence(conn, ticker, trace_id)
            macro_status = self._fetch_macro_status(conn)

        return PipelineDataBundle(
            price_rows=price_rows,
            l4_evidence=l4_evidence,
            metadata={
                "source": "postgres",
                "ticker": ticker,
                "price_source": KIS_ADJUSTED_OHLCV_TABLE,
                "indicator_sources": [TA_MOMENTUM_TICKER_TABLE],
                "price_rows": len(price_rows),
                "backtest_lookback_days": effective_lookback_days,
                "l4_evidence_source": ANALYST_REPORT_TABLE,
                "l4_evidence_rows": len(l4_evidence),
                "universe_source": UNIVERSE_VIEW,
                "universe": universe,
                "macro_source": BOK_MACRO_VIEW,
                "macro_status": macro_status,
            },
        )

    def _connect(self) -> Any:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            self.config.database_dsn,
            connect_timeout=self.config.connect_timeout_seconds,
            row_factory=dict_row,
        )

    def _set_statement_timeout(self, conn: Any) -> None:
        timeout_value = f"{self.config.statement_timeout_ms}{POSTGRES_TIMEOUT_UNIT}"
        _ = conn.execute("SELECT set_config('statement_timeout', %s, true)", [timeout_value])

    def _resolve_ticker(self, conn: Any, query: str) -> str:
        explicit_ticker = TICKER_PATTERN.search(query)
        if explicit_ticker:
            return explicit_ticker.group(0)

        rows = conn.execute(
            """
            SELECT symbol, name
            FROM meta.view_common_stock_universe
            WHERE listing_status IS NULL OR listing_status = 'LISTED'
            """
        ).fetchall()
        for row in rows:
            symbol = str(row.get("symbol") or "")
            name = str(row.get("name") or "")
            if symbol and symbol in query:
                return symbol.zfill(6)
            if name and name in query:
                return symbol.zfill(6)
        return self.config.default_ticker

    def _fetch_price_rows(
        self, conn: Any, ticker: str, universe: Mapping[str, Any], query: str
    ) -> tuple[list[dict[str, Any]], int]:
        lookback_days = self.config.backtest_lookback_days
        price_rows = self._fetch_price_rows_for_lookback(conn, ticker, universe, lookback_days)
        if (
            _query_requires_rsi_oversold(query)
            and lookback_days < DEFAULT_BACKTEST_LOOKBACK_DAYS
            and not _has_rsi_oversold_entry(price_rows)
        ):
            lookback_days = DEFAULT_BACKTEST_LOOKBACK_DAYS
            price_rows = self._fetch_price_rows_for_lookback(conn, ticker, universe, lookback_days)
        return price_rows, lookback_days

    def _fetch_price_rows_for_lookback(
        self, conn: Any, ticker: str, universe: Mapping[str, Any], lookback_days: int
    ) -> list[dict[str, Any]]:
        calendar_lookback_days = (
            lookback_days * BACKTEST_LOOKBACK_CALENDAR_DAY_MULTIPLIER
        )
        rows = conn.execute(
            """
            SELECT
                time AS as_of_date,
                ticker,
                adj_open AS open,
                adj_high AS high,
                adj_low AS low,
                adj_close AS close,
                adj_volume AS volume,
                quality_flags AS adjusted_ohlcv_quality_flags
            FROM feature.kis_adjusted_ohlcv_daily
            WHERE ticker = %s
              AND time >= CURRENT_DATE - make_interval(days => %s)
            ORDER BY time DESC
            LIMIT %s
            """,
            [ticker, calendar_lookback_days, lookback_days],
        ).fetchall()
        momentum_by_date = self._fetch_momentum_values_by_date(
            conn, ticker, calendar_lookback_days, lookback_days
        )
        return [
            _price_row_from_feature_frame_record(
                _feature_frame_row_from_sources(row, momentum_by_date, universe)
            )
            for row in reversed(rows)
        ]

    def _fetch_momentum_values_by_date(
        self, conn: Any, ticker: str, calendar_lookback_days: int, lookback_days: int
    ) -> dict[date, Mapping[str, Any]]:
        rows = conn.execute(
            """
            SELECT time, values_jsonb
            FROM feature.ta_momentum_ticker_daily
            WHERE ticker = %s
              AND time >= CURRENT_DATE - make_interval(days => %s)
            ORDER BY time DESC
            LIMIT %s
            """,
            [ticker, calendar_lookback_days, lookback_days],
        ).fetchall()
        values_by_date: dict[date, Mapping[str, Any]] = {}
        for row in rows:
            values = row.get("values_jsonb")
            values_by_date[_date_value(row["time"])] = values if isinstance(values, Mapping) else {}
        return values_by_date

    def _fetch_l4_evidence(self, conn: Any, ticker: str, trace_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT
                report_date,
                ticker,
                company_name,
                summary,
                opinion,
                institution,
                author,
                source_payload_hash,
                created_at
            FROM raw.analyst_report_summary
            WHERE ticker = %s
            ORDER BY report_date DESC, created_at DESC
            LIMIT %s
            """,
            [ticker, self.config.l4_evidence_limit],
        ).fetchall()
        return [_l4_evidence_from_report(row, trace_id) for row in rows]

    def _fetch_universe_status(self, conn: Any, ticker: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT symbol, name, market, market_segment, listing_status
            FROM meta.view_common_stock_universe
            WHERE symbol = %s
            LIMIT 1
            """,
            [ticker],
        ).fetchone()
        if row is None:
            return {"ticker": ticker, "included": False}
        return {
            "ticker": ticker,
            "included": True,
            "name": row.get("name"),
            "market": row.get("market"),
            "market_segment": row.get("market_segment"),
            "listing_status": row.get("listing_status"),
        }

    def _fetch_macro_status(self, conn: Any) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT count(*) AS row_count, max(effective_date) AS latest_effective_date
            FROM mart.bok_macro_asof
            """
        ).fetchone()
        row_count = int(row["row_count"]) if row else 0
        latest = row.get("latest_effective_date") if row else None
        return {
            "usable_for_risk_rules": False,
            "row_count": row_count,
            "latest_effective_date": latest.isoformat() if latest else None,
            "reason": "BOK macro mart is pilot-only and does not cover KOSPI/FX/VKOSPI rules.",
        }


def load_pipeline_data_from_env(query: str, trace_id: str) -> PipelineDataBundle:
    config = DataSourceConfig.from_env()
    if not config.database_dsn:
        return PipelineDataBundle(
            metadata={
                "source": "fixture",
                "reason": f"{AI_DATABASE_DSN_ENV} is not set.",
                "available_db_objects": [
                    KIS_FEATURE_FRAME_VIEW,
                    KIS_ADJUSTED_OHLCV_TABLE,
                    TA_MOMENTUM_TICKER_TABLE,
                    UNIVERSE_VIEW,
                    ANALYST_REPORT_TABLE,
                ],
            }
        )
    return PostgresPipelineDataSource(config).load(query, trace_id)


def _price_row_from_feature_frame_record(row: Mapping[str, Any]) -> dict[str, Any]:
    trade_date = _date_value(row["as_of_date"]).isoformat()
    price_row = {
        "date": trade_date,
        "ticker": str(row["ticker"]).zfill(6),
        "name": row.get("name") or "",
        "market": row.get("market_segment") or "KRX",
        "open": _float_value(row["open"]),
        "high": _float_value(row["high"]),
        "low": _float_value(row["low"]),
        "close": _float_value(row["close"]),
        "volume": _float_value(row["volume"]),
    }
    _merge_metric_values(price_row, row)
    rsi = _find_metric_value(row.get("momentum_values"), RSI_KEYS, contains="rsi")
    if rsi is not None:
        price_row["rsi"] = rsi
    return price_row


def _feature_frame_row_from_sources(
    row: Mapping[str, Any],
    momentum_by_date: Mapping[date, Mapping[str, Any]],
    universe: Mapping[str, Any],
) -> dict[str, Any]:
    trade_date = _date_value(row["as_of_date"])
    return {
        **dict(row),
        "as_of_date": trade_date,
        "name": universe.get("name") or "",
        "market_segment": universe.get("market_segment") or "KRX",
        "trend_values": {},
        "momentum_values": momentum_by_date.get(trade_date, {}),
        "volatility_values": {},
        "volume_values": {},
        "pattern_values": {},
    }


def _l4_evidence_from_report(row: Mapping[str, Any], trace_id: str) -> dict[str, Any]:
    report_date = _date_value(row["report_date"])
    published_at = datetime.combine(report_date, time.min)
    retrieved_at = _datetime_value(row.get("created_at")) or published_at
    publisher = row.get("institution") or "SEIBro"
    payload_hash = row.get("source_payload_hash") or f"{row.get('ticker')}:{report_date}"
    freshness_days = max(0, (datetime.now(UTC).date() - report_date).days)
    company_name = row.get("company_name") or row.get("ticker")
    opinion = row.get("opinion") or "opinion unavailable"
    author = row.get("author") or "author unavailable"
    return {
        "publisher": str(publisher),
        "published_at": published_at,
        "retrieved_at": retrieved_at,
        "freshness_days": freshness_days,
        "dedupe_group": f"{trace_id}:seibro:{payload_hash}",
        "access_status": "available",
        "quality_note": (
            f"SEIBro raw analyst report for {company_name}; opinion={opinion}; "
            f"author={author}; feature.seibro_* mart is not populated yet."
        ),
    }


def _merge_metric_values(target: dict[str, Any], row: Mapping[str, Any]) -> None:
    for field_name in (
        "trend_values",
        "momentum_values",
        "volatility_values",
        "volume_values",
        "pattern_values",
    ):
        values = row.get(field_name)
        if not isinstance(values, Mapping):
            continue
        for key, value in values.items():
            parsed = _optional_float_value(value)
            if parsed is None:
                continue
            target.setdefault(_metric_key(str(key)), parsed)


def _find_metric_value(
    values: Any, preferred_keys: tuple[str, ...], *, contains: str
) -> float | None:
    if not isinstance(values, Mapping):
        return None
    for key in preferred_keys:
        parsed = _optional_float_value(values.get(key))
        if parsed is not None:
            return parsed
    for key, value in values.items():
        if contains.lower() not in str(key).lower():
            continue
        parsed = _optional_float_value(value)
        if parsed is not None:
            return parsed
    return None


def _query_requires_rsi_oversold(query: str) -> bool:
    lowered = query.lower()
    return "rsi" in lowered and ("30" in lowered or "과매도" in query)


def _has_rsi_oversold_entry(price_rows: list[dict[str, Any]]) -> bool:
    for row in price_rows:
        for key in RSI_KEYS:
            value = _optional_float_value(row.get(_metric_key(key)))
            if value is not None and value <= RSI_OVERSOLD_THRESHOLD:
                return True
    return False


def _metric_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    return datetime.fromisoformat(str(value))


def _float_value(value: Any) -> float:
    parsed = _optional_float_value(value)
    if parsed is None:
        raise ValueError(f"value must be numeric: {value!r}")
    return parsed


def _optional_float_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _blank_to_none(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value


def _int_env(env: Mapping[str, str], key: str, default: int) -> int:
    value = env.get(key)
    if value is None or not value.strip():
        return default
    return int(value)
