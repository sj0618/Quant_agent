from __future__ import annotations

import math
import os
import re
import statistics
from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


AI_DATABASE_DSN_ENV = "AI_DATABASE_DSN"
QUANT_DB_DSN_ENV = "QUANT_DB_DSN"
DATABASE_URL_ENV = "DATABASE_URL"
DATABASE_DSN_ENV_CANDIDATES = (
    AI_DATABASE_DSN_ENV,
    QUANT_DB_DSN_ENV,
    DATABASE_URL_ENV,
)
AI_DEFAULT_TICKER_ENV = "AI_DEFAULT_TICKER"
AI_BACKTEST_LOOKBACK_DAYS_ENV = "AI_BACKTEST_LOOKBACK_DAYS"
AI_L4_EVIDENCE_LIMIT_ENV = "AI_L4_EVIDENCE_LIMIT"
AI_DB_CONNECT_TIMEOUT_SECONDS_ENV = "AI_DB_CONNECT_TIMEOUT_SECONDS"
AI_DB_STATEMENT_TIMEOUT_MS_ENV = "AI_DB_STATEMENT_TIMEOUT_MS"
AI_SCREENING_LIMIT_ENV = "AI_SCREENING_LIMIT"

DEFAULT_BACKTEST_TICKER = "005930"
TRADING_DAYS_PER_YEAR = 252
DEFAULT_BACKTEST_LOOKBACK_YEARS = 10
DEFAULT_BACKTEST_LOOKBACK_DAYS = TRADING_DAYS_PER_YEAR * DEFAULT_BACKTEST_LOOKBACK_YEARS
DEFAULT_L4_EVIDENCE_LIMIT = 5
DEFAULT_SCREENING_LIMIT = 10
DEFAULT_DB_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_DB_STATEMENT_TIMEOUT_MS = 10_000
SCREENING_BACKTEST_SELECTION_LIMIT = 10
PORTFOLIO_BACKTEST_TICKER_LIMIT = 5
POSTGRES_TIMEOUT_UNIT = "ms"
BACKTEST_LOOKBACK_CALENDAR_DAY_MULTIPLIER = 3
RSI_OVERSOLD_THRESHOLD = 30.0

KIS_FEATURE_FRAME_VIEW = "mart.kis_adjusted_feature_frame_asof"
KIS_ADJUSTED_OHLCV_TABLE = "feature.kis_adjusted_ohlcv_daily"
TA_MOMENTUM_TICKER_TABLE = "feature.ta_momentum_ticker_daily"
TA_TREND_TICKER_TABLE = "feature.ta_trend_ticker_daily"
TA_VOLATILITY_TICKER_TABLE = "feature.ta_volatility_ticker_daily"
TA_VOLUME_TICKER_TABLE = "feature.ta_volume_ticker_daily"
UNIVERSE_VIEW = "meta.view_common_stock_universe"
ANALYST_REPORT_TABLE = "raw.analyst_report_summary"
BOK_MACRO_VIEW = "mart.bok_macro_asof"

TICKER_PATTERN = re.compile(r"\b\d{6}\b")
RSI_KEYS = ("rsi", "RSI", "rsi_14", "RSI_14", "talib_rsi_14", "TA_RSI_14")
BROAD_UNIVERSE_TERMS = (
    "KOSPI200",
    "KOSPI 200",
    "코스피200",
    "코스피 200",
    "KOSDAQ150",
    "KOSDAQ 150",
    "코스닥150",
    "코스닥 150",
)
BROAD_SCREENING_TERMS = (
    "종목을 찾아",
    "종목 찾아",
    "찾아줘",
    "찾아 줘",
    "스크리닝",
    "후보",
    "조건에 맞는",
    "조건 맞는",
)


class DataSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_dsn: str | None = None
    database_dsn_env: str = AI_DATABASE_DSN_ENV
    default_ticker: str = Field(default=DEFAULT_BACKTEST_TICKER, min_length=6, max_length=6)
    backtest_lookback_days: int = Field(default=DEFAULT_BACKTEST_LOOKBACK_DAYS, gt=0)
    l4_evidence_limit: int = Field(default=DEFAULT_L4_EVIDENCE_LIMIT, gt=0)
    screening_limit: int = Field(default=DEFAULT_SCREENING_LIMIT, gt=0)
    connect_timeout_seconds: int = Field(default=DEFAULT_DB_CONNECT_TIMEOUT_SECONDS, gt=0)
    statement_timeout_ms: int = Field(default=DEFAULT_DB_STATEMENT_TIMEOUT_MS, gt=0)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "DataSourceConfig":
        env = environ or os.environ
        database_dsn, database_dsn_env = resolve_database_dsn_from_env(env)
        return cls(
            database_dsn=database_dsn,
            database_dsn_env=database_dsn_env,
            default_ticker=env.get(AI_DEFAULT_TICKER_ENV, DEFAULT_BACKTEST_TICKER),
            backtest_lookback_days=_int_env(
                env, AI_BACKTEST_LOOKBACK_DAYS_ENV, DEFAULT_BACKTEST_LOOKBACK_DAYS
            ),
            l4_evidence_limit=_int_env(
                env, AI_L4_EVIDENCE_LIMIT_ENV, DEFAULT_L4_EVIDENCE_LIMIT
            ),
            screening_limit=_int_env(env, AI_SCREENING_LIMIT_ENV, DEFAULT_SCREENING_LIMIT),
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
    screening_candidates: list[dict[str, Any]] = Field(default_factory=list)
    l4_evidence: list[dict[str, Any]] = Field(default_factory=list)
    macro_snapshot: dict[str, float] | None = None
    data_availability: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PostgresPipelineDataSource:
    def __init__(self, config: DataSourceConfig) -> None:
        if not config.database_dsn:
            raise ValueError(f"{AI_DATABASE_DSN_ENV} is required for PostgreSQL data source")
        self.config = config

    def load(self, query: str, trace_id: str) -> PipelineDataBundle:
        with self._connect() as conn:
            self._set_statement_timeout(conn)
            screening_candidates = []
            if _query_requests_universe_screening(query):
                screening_candidates = self._fetch_screening_candidates(conn, query)
            if screening_candidates:
                tickers, universe, price_rows, effective_lookback_days, selection_score = (
                    self._fetch_screening_portfolio_price_rows(
                        conn, screening_candidates, query
                    )
                )
                ticker = tickers[0]
            else:
                ticker = self._resolve_ticker(conn, query)
                tickers = [ticker]
                universe = self._fetch_universe_status(conn, ticker)
                price_rows, effective_lookback_days = self._fetch_price_rows(
                    conn, ticker, universe, query
                )
                selection_score = None
            if not price_rows:
                raise ValueError(f"{KIS_ADJUSTED_OHLCV_TABLE} returned no price rows for {ticker}")
            l4_evidence = self._fetch_l4_evidence(conn, ticker, trace_id)
            macro_status = self._fetch_macro_status(conn)

        return PipelineDataBundle(
            price_rows=price_rows,
            screening_candidates=screening_candidates,
            l4_evidence=l4_evidence,
            data_availability=_data_availability_for_query(query, source="postgres"),
            metadata={
                "source": "postgres",
                "dsn_env": self.config.database_dsn_env,
                "ticker": ticker,
                "tickers": tickers,
                "price_source": KIS_ADJUSTED_OHLCV_TABLE,
                "indicator_sources": [
                    TA_MOMENTUM_TICKER_TABLE,
                    TA_TREND_TICKER_TABLE,
                    TA_VOLATILITY_TICKER_TABLE,
                    TA_VOLUME_TICKER_TABLE,
                ],
                "price_rows": len(price_rows),
                "screening_candidates": len(screening_candidates),
                "screening_selection_score": selection_score,
                "backtest_lookback_days": effective_lookback_days,
                "l4_evidence_source": ANALYST_REPORT_TABLE,
                "l4_evidence_rows": len(l4_evidence),
                "universe_source": UNIVERSE_VIEW,
                "universe": universe,
                "macro_source": BOK_MACRO_VIEW,
                "macro_status": macro_status,
            },
        )

    def _fetch_screening_candidates(self, conn: Any, query: str) -> list[dict[str, Any]]:
        profile = _screening_profile(query)
        rows = conn.execute(
            _screening_sql(profile),
            [
                self.config.screening_limit,
            ],
        ).fetchall()
        return [_screening_candidate_from_row(row, profile) for row in rows]

    def _select_screening_backtest_candidate(
        self, conn: Any, screening_candidates: list[dict[str, Any]], query: str
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]], int, float]:
        best: tuple[float, str, dict[str, Any], list[dict[str, Any]], int] | None = None
        for candidate in screening_candidates[:SCREENING_BACKTEST_SELECTION_LIMIT]:
            ticker = str(candidate["ticker"]).zfill(6)
            universe = self._fetch_universe_status(ticker=ticker, conn=conn)
            price_rows, effective_lookback_days = self._fetch_price_rows(
                conn, ticker, universe, query
            )
            if not price_rows:
                continue
            score = _screening_price_quality_score(price_rows)
            if best is None or score > best[0]:
                best = (score, ticker, universe, price_rows, effective_lookback_days)
        if best is None:
            ticker = str(screening_candidates[0]["ticker"]).zfill(6)
            universe = self._fetch_universe_status(conn, ticker)
            price_rows, effective_lookback_days = self._fetch_price_rows(
                conn, ticker, universe, query
            )
            return ticker, universe, price_rows, effective_lookback_days, 0.0
        score, ticker, universe, price_rows, effective_lookback_days = best
        return ticker, universe, price_rows, effective_lookback_days, round(score, 6)

    def _fetch_screening_portfolio_price_rows(
        self, conn: Any, screening_candidates: list[dict[str, Any]], query: str
    ) -> tuple[list[str], dict[str, Any], list[dict[str, Any]], int, float]:
        ranked: list[tuple[float, str, dict[str, Any], list[dict[str, Any]], int]] = []
        for candidate in screening_candidates[:SCREENING_BACKTEST_SELECTION_LIMIT]:
            ticker = str(candidate["ticker"]).zfill(6)
            universe = self._fetch_universe_status(conn, ticker)
            price_rows, effective_lookback_days = self._fetch_price_rows(
                conn, ticker, universe, query
            )
            if not price_rows:
                continue
            ranked.append(
                (
                    _screening_price_quality_score(price_rows),
                    ticker,
                    universe,
                    price_rows,
                    effective_lookback_days,
                )
            )
        if not ranked:
            ticker, universe, price_rows, effective_lookback_days, score = (
                self._select_screening_backtest_candidate(conn, screening_candidates, query)
            )
            return [ticker], universe, price_rows, effective_lookback_days, score

        selected = sorted(ranked, key=lambda item: item[0], reverse=True)[
            :PORTFOLIO_BACKTEST_TICKER_LIMIT
        ]
        tickers = [item[1] for item in selected]
        combined_rows = [
            row
            for _score, _ticker, _universe, rows, _lookback_days in selected
            for row in rows
        ]
        combined_rows.sort(key=lambda row: (str(row["date"]), str(row["ticker"]).zfill(6)))
        effective_lookback_days = max(item[4] for item in selected)
        primary_universe = dict(selected[0][2])
        primary_universe["portfolio_tickers"] = tickers
        average_score = sum(item[0] for item in selected) / len(selected)
        return tickers, primary_universe, combined_rows, effective_lookback_days, round(average_score, 6)

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
        if _has_broad_universe_reference(query) or _has_broad_screening_reference(query):
            return self.config.default_ticker

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
        return _fixture_bundle(
            f"database DSN is not set in any of {', '.join(DATABASE_DSN_ENV_CANDIDATES)}.",
            query=query,
        )
    try:
        return PostgresPipelineDataSource(config).load(query, trace_id)
    except Exception as exc:
        return _fixture_bundle(
            f"PostgreSQL data source unavailable: {type(exc).__name__}: {exc}",
            query=query,
        )


def _fixture_bundle(reason: str, *, query: str) -> PipelineDataBundle:
    return PipelineDataBundle(
        data_availability=_data_availability_for_query(query, source="fixture"),
        metadata={
            "source": "fixture",
            "reason": reason,
            "dsn_env_candidates": list(DATABASE_DSN_ENV_CANDIDATES),
            "available_db_objects": [
                KIS_FEATURE_FRAME_VIEW,
                KIS_ADJUSTED_OHLCV_TABLE,
                TA_MOMENTUM_TICKER_TABLE,
                UNIVERSE_VIEW,
                ANALYST_REPORT_TABLE,
            ],
        }
    )


def _query_requests_universe_screening(query: str) -> bool:
    return (
        TICKER_PATTERN.search(query) is None
        and (_has_broad_universe_reference(query) or _has_broad_screening_reference(query))
    )


def _screening_profile(query: str) -> str:
    lowered = query.lower()
    if "rsi" in lowered or "과매도" in query or "반등" in query:
        return "rsi_rebound"
    if "볼린저" in query or "밴드" in query or "변동성" in query:
        return "bollinger_squeeze"
    if "200일" in query or "눌림목" in query or "20일선" in query:
        return "pullback_trend"
    if "상대강도" in query or "시장보다" in query or "주도주" in query:
        return "relative_strength"
    if "신고가" in query or "거래량" in query or "돌파" in query or "모멘텀" in query:
        return "breakout_volume"
    return "technical_proxy"


def _screening_sql(profile: str) -> str:
    where_clause = {
        "breakout_volume": (
            "close >= high_252 * 0.995 AND volume_ratio_20 >= 1.5 "
            "AND close > sma20 AND relative_strength_20d >= 0"
        ),
        "rsi_rebound": "(rsi <= 35 OR (prev_rsi < 30 AND rsi >= 30))",
        "pullback_trend": (
            "close > sma200 AND sma20 > 0 AND abs(close / sma20 - 1) <= 0.04"
        ),
        "bollinger_squeeze": (
            "bb_width > 0 AND bb_width <= 0.18 AND close >= bb_upper * 0.995"
        ),
        "relative_strength": "relative_strength_20d >= 0 AND relative_strength_60d >= 0",
    }.get(profile, "technical_score > 0")
    return f"""
        WITH latest_date AS (
            SELECT max(time) AS as_of_date
            FROM feature.kis_adjusted_ohlcv_daily
        ),
        prices AS (
            SELECT
                p.time,
                p.ticker,
                u.name,
                u.market,
                u.market_segment,
                p.adj_open AS open,
                p.adj_high AS high,
                p.adj_low AS low,
                p.adj_close AS close,
                p.adj_volume AS volume
            FROM feature.kis_adjusted_ohlcv_daily p
            JOIN meta.view_common_stock_universe u
              ON u.symbol = p.ticker
            WHERE p.time >= (SELECT as_of_date FROM latest_date) - INTERVAL '420 days'
              AND (u.listing_status IS NULL OR u.listing_status = 'LISTED')
        ),
        features AS (
            SELECT
                prices.*,
                avg(close) OVER w20 AS sma20,
                avg(close) OVER w50 AS sma50,
                avg(close) OVER w200 AS sma200,
                max(high) OVER w20 AS high_20,
                max(high) OVER w120 AS high_120,
                max(high) OVER w252 AS high_252,
                avg(volume) OVER w20 AS avg_volume_20,
                stddev_samp(close) OVER w20 AS std20,
                lag(close, 20) OVER wt AS close_20d_ago,
                lag(close, 60) OVER wt AS close_60d_ago,
                lag(close, 120) OVER wt AS close_120d_ago
            FROM prices
            WINDOW
                wt AS (PARTITION BY ticker ORDER BY time),
                w20 AS (PARTITION BY ticker ORDER BY time ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
                w50 AS (PARTITION BY ticker ORDER BY time ROWS BETWEEN 49 PRECEDING AND CURRENT ROW),
                w120 AS (PARTITION BY ticker ORDER BY time ROWS BETWEEN 119 PRECEDING AND CURRENT ROW),
                w200 AS (PARTITION BY ticker ORDER BY time ROWS BETWEEN 199 PRECEDING AND CURRENT ROW),
                w252 AS (PARTITION BY ticker ORDER BY time ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)
        ),
        momentum_raw AS (
            SELECT
                time,
                ticker,
                COALESCE(
                    values_jsonb->>'RSI_14',
                    values_jsonb->>'rsi_14',
                    values_jsonb->>'RSI',
                    values_jsonb->>'rsi'
                ) AS rsi_text
            FROM feature.ta_momentum_ticker_daily
            WHERE time >= (SELECT as_of_date FROM latest_date) - INTERVAL '90 days'
        ),
        momentum AS (
            SELECT
                time,
                ticker,
                CASE
                    WHEN rsi_text ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN rsi_text::numeric
                    ELSE NULL
                END AS rsi
            FROM momentum_raw
        ),
        momentum_with_prev AS (
            SELECT
                time,
                ticker,
                rsi,
                lag(rsi) OVER (PARTITION BY ticker ORDER BY time) AS prev_rsi
            FROM momentum
        ),
        latest_rows AS (
            SELECT
                f.*,
                mwp.rsi,
                mwp.prev_rsi,
                CASE WHEN avg_volume_20 > 0 THEN volume / avg_volume_20 ELSE NULL END AS volume_ratio_20,
                CASE WHEN close_20d_ago > 0 THEN close / close_20d_ago - 1 ELSE NULL END AS return_20d,
                CASE WHEN close_60d_ago > 0 THEN close / close_60d_ago - 1 ELSE NULL END AS return_60d,
                CASE WHEN close_120d_ago > 0 THEN close / close_120d_ago - 1 ELSE NULL END AS return_120d,
                (sma20 + 2 * COALESCE(std20, 0)) AS bb_upper,
                CASE WHEN sma20 > 0 THEN (4 * COALESCE(std20, 0)) / sma20 ELSE NULL END AS bb_width,
                close * volume AS turnover
            FROM features f
            LEFT JOIN momentum_with_prev mwp
              ON mwp.ticker = f.ticker AND mwp.time = f.time
            WHERE f.time = (SELECT as_of_date FROM latest_date)
        ),
        market AS (
            SELECT
                avg(return_20d) AS market_return_20d,
                avg(return_60d) AS market_return_60d
            FROM latest_rows
        ),
        scored AS (
            SELECT
                latest_rows.*,
                COALESCE(return_20d, 0) - COALESCE(market.market_return_20d, 0) AS relative_strength_20d,
                COALESCE(return_60d, 0) - COALESCE(market.market_return_60d, 0) AS relative_strength_60d,
                (
                    CASE WHEN close >= high_252 * 0.995 THEN 3 ELSE 0 END +
                    CASE WHEN volume_ratio_20 >= 1.5 THEN 2 ELSE 0 END +
                    CASE WHEN close > sma20 THEN 1 ELSE 0 END +
                    CASE WHEN close > sma200 THEN 1 ELSE 0 END +
                    CASE WHEN rsi <= 35 THEN 1 ELSE 0 END
                ) AS technical_score
            FROM latest_rows
            CROSS JOIN market
        )
        SELECT *
        FROM scored
        WHERE {where_clause}
        ORDER BY technical_score DESC, turnover DESC NULLS LAST
        LIMIT %s
    """


def _screening_candidate_from_row(row: Mapping[str, Any], profile: str) -> dict[str, Any]:
    volume_ratio = _optional_float_value(row.get("volume_ratio_20"))
    relative_strength = _optional_float_value(row.get("relative_strength_20d"))
    close = _optional_float_value(row.get("close"))
    return {
        "ticker": str(row.get("ticker") or "").zfill(6),
        "name": row.get("name") or "",
        "market": row.get("market_segment") or row.get("market") or "KRX",
        "as_of_date": _date_value(row.get("time")).isoformat(),
        "screening_profile": profile,
        "score": _float_value(row.get("technical_score") or 0),
        "close": close,
        "volume_ratio_20": volume_ratio,
        "rsi": _optional_float_value(row.get("rsi")),
        "relative_strength_20d": relative_strength,
        "relative_strength_60d": _optional_float_value(row.get("relative_strength_60d")),
        "matched_rules": _matched_screening_rules(row, profile),
    }


def _screening_price_quality_score(price_rows: list[dict[str, Any]]) -> float:
    closes = [_optional_float_value(row.get("close")) for row in price_rows]
    prices = [value for value in closes if value is not None and value > 0]
    if len(prices) < 30:
        return float("-inf")
    returns = [
        after / before - 1
        for before, after in zip(prices[:-1], prices[1:])
        if before > 0
    ]
    if len(returns) < 2:
        return float("-inf")
    volatility = statistics.stdev(returns)
    sharpe = (
        statistics.mean(returns) / volatility * math.sqrt(TRADING_DAYS_PER_YEAR)
        if volatility > 0
        else 0.0
    )
    total_return = prices[-1] / prices[0] - 1
    recent_window = min(252, len(prices) - 1)
    recent_return = prices[-1] / prices[-recent_window] - 1 if prices[-recent_window] else 0.0
    drawdown = _price_max_drawdown(prices)
    calmar = total_return / abs(drawdown) if drawdown < 0 else 0.0
    return sharpe + 0.35 * calmar + 0.25 * recent_return + 0.10 * total_return


def _price_max_drawdown(prices: list[float]) -> float:
    peak = prices[0]
    max_drawdown = 0.0
    for price in prices:
        peak = max(peak, price)
        if peak <= 0:
            continue
        max_drawdown = min(max_drawdown, price / peak - 1)
    return max_drawdown


def _matched_screening_rules(row: Mapping[str, Any], profile: str) -> list[str]:
    rules: list[str] = []
    close = _optional_float_value(row.get("close"))
    if close is not None and _compare(close, row.get("high_252"), factor=0.995):
        rules.append("52주 신고가 근접/돌파")
    if _compare(row.get("volume_ratio_20"), 1.5):
        rules.append("거래량 20일 평균 대비 150% 이상")
    if close is not None and _compare(close, row.get("sma20")):
        rules.append("20일선 위")
    if close is not None and _compare(close, row.get("sma200")):
        rules.append("200일선 위")
    if _compare(row.get("relative_strength_20d"), 0):
        rules.append("20일 상대강도 양호")
    rsi = _optional_float_value(row.get("rsi"))
    prev_rsi = _optional_float_value(row.get("prev_rsi"))
    if rsi is not None and rsi <= 35:
        rules.append("RSI 과매도권")
    if prev_rsi is not None and rsi is not None and prev_rsi < 30 <= rsi:
        rules.append("RSI 30 상향 돌파")
    if profile == "bollinger_squeeze" and _compare(row.get("bb_upper"), close):
        rules.append("볼린저 상단 근접/돌파")
    return rules


def _compare(left: Any, right: Any, *, factor: float = 1.0) -> bool:
    left_value = _optional_float_value(left)
    right_value = _optional_float_value(right)
    if left_value is None or right_value is None:
        return False
    return left_value >= right_value * factor


def _data_availability_for_query(query: str, *, source: str) -> dict[str, Any]:
    query_text = query.lower()
    needs_financials = any(
        term in query_text or term in query
        for term in (
            "per",
            "pbr",
            "roe",
            "eps",
            "fcf",
            "부채",
            "매출",
            "영업이익",
            "배당",
            "순현금",
            "재고",
            "자사주",
            "공시",
        )
    )
    needs_macro = any(term in query for term in ("금리", "환율", "원달러", "원자재"))
    needs_reports = any(term in query for term in ("컨센서스", "리포트", "투자의견", "목표주가", "어닝", "가이던스"))
    proxy_used: list[str] = []
    if needs_financials:
        proxy_used.append("OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용")
    if needs_macro:
        proxy_used.append("BOK macro mart 파일럿 상태: 거시 조건은 설명용 availability로만 표시")
    if needs_reports:
        proxy_used.append("SEIBro feature mart 미적재: raw analyst report evidence만 사용")
    return {
        "source": source,
        "price_ta": "available" if source == "postgres" else "fixture",
        "open_dart": "unavailable",
        "bok_macro": "pilot_only",
        "seibro_report": "raw_available" if source == "postgres" else "fixture",
        "agentic_web_search": "not_connected",
        "proxy_used": proxy_used,
    }


def _has_broad_universe_reference(query: str) -> bool:
    normalized_query = query.upper()
    return any(term.upper() in normalized_query for term in BROAD_UNIVERSE_TERMS)


def _has_broad_screening_reference(query: str) -> bool:
    return any(term in query for term in BROAD_SCREENING_TERMS)


def resolve_database_dsn_from_env(environ: Mapping[str, str] | None = None) -> tuple[str | None, str]:
    env = environ or os.environ
    for env_name in DATABASE_DSN_ENV_CANDIDATES:
        raw_value = _blank_to_none(env.get(env_name))
        if raw_value:
            return _normalize_postgres_dsn(raw_value), env_name
    return None, AI_DATABASE_DSN_ENV


def _normalize_postgres_dsn(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("postgresql+asyncpg://"):
        return "postgresql://" + normalized.removeprefix("postgresql+asyncpg://")
    if normalized.startswith("postgresql+psycopg://"):
        return "postgresql://" + normalized.removeprefix("postgresql+psycopg://")
    return normalized


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
