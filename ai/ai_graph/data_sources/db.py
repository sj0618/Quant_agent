from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .sectors import extract_sector_from_query, get_known_sectors


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

DEFAULT_BACKTEST_TICKER = "005930"
TRADING_DAYS_PER_YEAR = 252
DEFAULT_BACKTEST_LOOKBACK_YEARS = 10
DEFAULT_BACKTEST_LOOKBACK_DAYS = TRADING_DAYS_PER_YEAR * DEFAULT_BACKTEST_LOOKBACK_YEARS
DEFAULT_L4_EVIDENCE_LIMIT = 5
# 조건에 일치한 종목은 점수로 다시 줄이지 않고 모두 추천 결과에 남긴다.
DEFAULT_DB_CONNECT_TIMEOUT_SECONDS = 20
DEFAULT_DB_STATEMENT_TIMEOUT_MS = 30_000
POSTGRES_TIMEOUT_UNIT = "ms"
BACKTEST_LOOKBACK_CALENDAR_DAY_MULTIPLIER = 3
RSI_OVERSOLD_THRESHOLD = 30.0
# Sentinel profile whose WHERE clause is the permissive `close > 0` baseline: screening
# selects the whole universe once and filters it per relaxation round in-process.
SCREENING_BASELINE_PROFILE = "__baseline__"
MAX_SCREENING_RELAXATION_ROUNDS = 3

KIS_FEATURE_FRAME_VIEW = "mart.kis_adjusted_feature_frame_asof"
KIS_ADJUSTED_OHLCV_TABLE = "feature.kis_adjusted_ohlcv_daily"
TA_MOMENTUM_TICKER_TABLE = "feature.ta_momentum_ticker_daily"
TA_TREND_TICKER_TABLE = "feature.ta_trend_ticker_daily"
TA_VOLATILITY_TICKER_TABLE = "feature.ta_volatility_ticker_daily"
TA_VOLUME_TICKER_TABLE = "feature.ta_volume_ticker_daily"
UNIVERSE_VIEW = "meta.view_common_stock_universe"
# meta.view_common_stock_universe filters on core.symbol_master.listing_status, which is
# currently bulk-broken upstream (see _resolve_ticker/_fetch_symbol_info/_screening_sql):
# every symbol reads as 'delisted'. Universe membership is derived from symbol_master directly
# (scoped to KOSPI/KOSDAQ common stock) or from which tickers actually have OHLCV rows, instead.
SYMBOL_MASTER_TABLE = "core.symbol_master"
ANALYST_REPORT_TABLE = "raw.analyst_report_summary"
BOK_MACRO_VIEW = "mart.bok_macro_asof"

TICKER_PATTERN = re.compile(r"\b\d{6}\b")
RSI_KEYS = ("rsi", "RSI", "rsi_14", "RSI_14", "talib_rsi_14", "TA_RSI_14")
MARKET_SCOPE_TERMS = (
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
            screening_relaxation: dict[str, Any] = {}
            ticker_resolution = "screening"
            if _query_requests_screening(query):
                screening_candidates, screening_relaxation = self._screen_with_relaxation(conn, query)
            single_ticker: str | None = None
            if not screening_candidates:
                single_ticker = self._resolve_ticker(conn, query)
                if single_ticker is None:
                    # Ambiguous query (no explicit ticker, no name match): retry as
                    # a broad condition screen instead of silently trading a
                    # single hardcoded default ticker.
                    screening_candidates, screening_relaxation = self._screen_with_relaxation(
                        conn, query
                    )
                    ticker_resolution = (
                        "ambiguous_fallback_to_screening"
                        if screening_candidates
                        else "ambiguous_fallback_to_default_ticker"
                    )
                else:
                    ticker_resolution = "explicit_or_name_match"
            if screening_candidates:
                tickers = [str(item["ticker"]).zfill(6) for item in screening_candidates]
                ticker = tickers[0]
                symbol_info = self._fetch_symbol_info(conn, ticker)
                price_rows, effective_lookback_days = self._fetch_price_rows(
                    conn, ticker, symbol_info, query
                )
            elif single_ticker:
                ticker = single_ticker
                tickers = [ticker]
                symbol_info = self._fetch_symbol_info(conn, ticker)
                price_rows, effective_lookback_days = self._fetch_price_rows(
                    conn, ticker, symbol_info, query
                )
            else:
                # No DB screening match and no explicit/name-resolved ticker: refuse to
                # silently substitute config.default_ticker, since that produces a
                # report that looks real but always trades the same hardcoded stock.
                raise ValueError(
                    "no screening candidates or resolvable ticker found in the database "
                    f"for this query after {screening_relaxation.get('relaxation_rounds', 0)} "
                    "relaxation round(s); refusing to fall back to a hardcoded default ticker"
                )
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
                "ticker_resolution": ticker_resolution,
                "price_source": KIS_ADJUSTED_OHLCV_TABLE,
                "indicator_sources": [
                    TA_MOMENTUM_TICKER_TABLE,
                    TA_TREND_TICKER_TABLE,
                    TA_VOLATILITY_TICKER_TABLE,
                    TA_VOLUME_TICKER_TABLE,
                ],
                "price_rows": len(price_rows),
                "screening_candidates": len(screening_candidates),
                "screening_relaxation": screening_relaxation,
                "backtest_lookback_days": effective_lookback_days,
                "l4_evidence_source": ANALYST_REPORT_TABLE,
                "l4_evidence_rows": len(l4_evidence),
                "universe_source": SYMBOL_MASTER_TABLE,
                "symbol": symbol_info,
                "macro_source": BOK_MACRO_VIEW,
                "macro_status": macro_status,
            },
        )

    def _fetch_screening_candidates(self, conn: Any, query: str) -> list[dict[str, Any]]:
        return self._screen_with_relaxation(conn, query)[0]

    def _screen_with_relaxation(
        self, conn: Any, query: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Screen for candidates, progressively loosening the thresholds until some match.

        An empty strict screen is a normal market outcome (on a given day nothing may
        sit at a 52-week high *and* on a volume surge), not a failure, so instead of
        giving up we re-ask for a looser screen and retry - recording every round so
        the report can disclose that the conditions were widened.
        """

        profile = _screening_profile(query)
        sector = extract_sector_from_query(query, get_known_sectors(conn=conn))
        params: list[Any] = [sector] if sector else []
        # The window-function CTE is the expensive part, so it runs once and every
        # relaxation round re-filters these rows in-process.
        rows = conn.execute(_screening_sql(SCREENING_BASELINE_PROFILE, sector=sector), params).fetchall()

        thresholds = ScreeningThresholds()
        rounds: list[dict[str, Any]] = []
        for round_index in range(MAX_SCREENING_RELAXATION_ROUNDS + 1):
            matches = _screening_matcher(profile, thresholds)
            matched = [row for row in rows if matches(row)]
            rounds.append(
                {
                    "round": round_index,
                    "relaxed": round_index > 0,
                    "thresholds": thresholds.model_dump(),
                    "matched_count": len(matched),
                }
            )
            if matched:
                candidates = [
                    _screening_candidate_from_row(row, profile, sector=sector) for row in matched
                ]
                return candidates, _relaxation_trace(profile, rounds, len(rows))
            if round_index == MAX_SCREENING_RELAXATION_ROUNDS:
                break
            thresholds = _propose_relaxed_thresholds(
                query=query,
                profile=profile,
                thresholds=thresholds,
                round_index=round_index,
                universe_rows=len(rows),
            )
        return [], _relaxation_trace(profile, rounds, len(rows))

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

    def _resolve_ticker(self, conn: Any, query: str) -> str | None:
        """Resolve a single explicit ticker for `query`, or None if ambiguous.

        Returning None (instead of silently defaulting to
        `self.config.default_ticker`) lets `load()` retry ambiguous queries as
        a broad condition screen rather than always trading the same
        single hardcoded ticker.
        """
        explicit_ticker = TICKER_PATTERN.search(query)
        if explicit_ticker:
            return explicit_ticker.group(0)
        if _has_market_scope_reference(query) or _has_broad_screening_reference(query):
            return None

        # core.symbol_master.listing_status is currently unreliable (bulk-marked
        # 'delisted' by an ingestion issue on the DE side), so meta.view_common_stock_universe
        # (which filters on it) returns 0 rows. Query symbol_master directly, scoped to the
        # same market_segment/security_type the view otherwise applies, without listing_status.
        rows = conn.execute(
            """
            SELECT symbol, name
            FROM core.symbol_master
            WHERE market_segment IN ('KOSPI', 'KOSDAQ') AND security_type = '보통주'
            """
        ).fetchall()
        for row in rows:
            symbol = str(row.get("symbol") or "")
            name = str(row.get("name") or "")
            if symbol and symbol in query:
                return symbol.zfill(6)
            if name and name in query:
                return symbol.zfill(6)
        return None

    def _fetch_price_rows(
        self, conn: Any, ticker: str, symbol_info: Mapping[str, Any], query: str
    ) -> tuple[list[dict[str, Any]], int]:
        lookback_days = self.config.backtest_lookback_days
        price_rows = self._fetch_price_rows_for_lookback(conn, ticker, symbol_info, lookback_days)
        if (
            _query_requires_rsi_oversold(query)
            and lookback_days < DEFAULT_BACKTEST_LOOKBACK_DAYS
            and not _has_rsi_oversold_entry(price_rows)
        ):
            lookback_days = DEFAULT_BACKTEST_LOOKBACK_DAYS
            price_rows = self._fetch_price_rows_for_lookback(conn, ticker, symbol_info, lookback_days)
        return price_rows, lookback_days

    def _fetch_price_rows_for_lookback(
        self, conn: Any, ticker: str, symbol_info: Mapping[str, Any], lookback_days: int
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
                _feature_frame_row_from_sources(row, momentum_by_date, symbol_info)
            )
            for row in reversed(rows)
        ]

    def _fetch_momentum_values_by_date(
        self, conn: Any, ticker: str, calendar_lookback_days: int, lookback_days: int
    ) -> dict[date, Mapping[str, Any]]:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (time) time, values_jsonb
            FROM feature.ta_momentum_ticker_daily
            WHERE split_part(ticker, '#', 1) = %s
              AND time >= CURRENT_DATE - make_interval(days => %s)
            ORDER BY time DESC, ticker
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

    def _fetch_symbol_info(self, conn: Any, ticker: str) -> dict[str, Any]:
        # See _resolve_ticker: meta.view_common_stock_universe is unusable right now because
        # its listing_status filter is bulk-broken upstream. Query symbol_master directly and
        # treat "included" as "known KRX symbol", not "currently listed" (listing_status is
        # still surfaced below for visibility, but not trusted as a filter).
        row = conn.execute(
            """
            SELECT symbol, name, market, market_segment, listing_status
            FROM core.symbol_master
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
    return PostgresPipelineDataSource(config).load(query, trace_id)


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


def _query_requests_screening(query: str) -> bool:
    return (
        TICKER_PATTERN.search(query) is None
        and (
            _has_market_scope_reference(query)
            or _has_broad_screening_reference(query)
            or extract_sector_from_query(query) is not None
        )
    )


class ScreeningThresholds(BaseModel):
    """Numeric knobs the screening filter is built from.

    Every relaxation proposal - including an LLM-generated one - is applied through
    this model, so a proposed value is always a bounded number and never reaches the
    filter as free text. Out-of-range proposals fail validation and the caller falls
    back to the deterministic ladder instead.
    """

    model_config = ConfigDict(extra="forbid")

    high_252_ratio: float = Field(default=0.995, ge=0.50, le=1.0)
    volume_ratio_min: float = Field(default=1.5, ge=0.5, le=10.0)
    require_close_above_sma20: bool = Field(default=True)
    relative_strength_20d_min: float = Field(default=0.0, ge=-1.0, le=1.0)
    relative_strength_60d_min: float = Field(default=0.0, ge=-1.0, le=1.0)
    rsi_max: float = Field(default=35.0, ge=5.0, le=70.0)
    rsi_cross_floor: float = Field(default=30.0, ge=5.0, le=70.0)
    sma20_band: float = Field(default=0.04, ge=0.005, le=0.50)
    bb_width_max: float = Field(default=0.18, ge=0.02, le=1.0)
    bb_upper_ratio: float = Field(default=0.995, ge=0.50, le=1.0)


def _clamped(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _relaxed_thresholds(base: ScreeningThresholds, round_index: int) -> ScreeningThresholds:
    """Deterministic widening ladder, used when no live LLM is configured and as the
    fallback whenever an LLM relaxation proposal is unusable."""

    step = round_index + 1
    return base.model_copy(
        update={
            "high_252_ratio": _clamped(base.high_252_ratio - 0.02 * step, 0.50, 1.0),
            "volume_ratio_min": _clamped(base.volume_ratio_min - 0.30 * step, 0.5, 10.0),
            # The trend filter is the most restrictive of the breakout rules, so it is
            # the first whole condition dropped rather than merely loosened.
            "require_close_above_sma20": step < 2,
            "relative_strength_20d_min": _clamped(
                base.relative_strength_20d_min - 0.05 * step, -1.0, 1.0
            ),
            "relative_strength_60d_min": _clamped(
                base.relative_strength_60d_min - 0.05 * step, -1.0, 1.0
            ),
            "rsi_max": _clamped(base.rsi_max + 5.0 * step, 5.0, 70.0),
            "sma20_band": _clamped(base.sma20_band + 0.02 * step, 0.005, 0.50),
            "bb_width_max": _clamped(base.bb_width_max + 0.06 * step, 0.02, 1.0),
            "bb_upper_ratio": _clamped(base.bb_upper_ratio - 0.02 * step, 0.50, 1.0),
        }
    )


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _at_least(left: Any, right: Any) -> bool:
    """`left >= right`, treating a missing operand as a non-match (SQL NULL semantics)."""

    left_value, right_value = _numeric(left), _numeric(right)
    return left_value is not None and right_value is not None and left_value >= right_value


def _above(left: Any, right: Any) -> bool:
    left_value, right_value = _numeric(left), _numeric(right)
    return left_value is not None and right_value is not None and left_value > right_value


def _scaled(value: Any, factor: float) -> float | None:
    numeric = _numeric(value)
    return None if numeric is None else numeric * factor


def _screening_matcher(profile: str, thresholds: ScreeningThresholds) -> Any:
    """Row predicate mirroring the profile's SQL WHERE clause.

    Screening runs the expensive window-function CTE once and then re-filters the
    returned rows here, so a relaxation round costs nothing at the database.
    """

    def breakout_volume(row: Mapping[str, Any]) -> bool:
        close = row.get("close")
        if not _at_least(close, _scaled(row.get("high_252"), thresholds.high_252_ratio)):
            return False
        if not _at_least(row.get("volume_ratio_20"), thresholds.volume_ratio_min):
            return False
        if thresholds.require_close_above_sma20 and not _above(close, row.get("sma20")):
            return False
        return _at_least(row.get("relative_strength_20d"), thresholds.relative_strength_20d_min)

    def rsi_rebound(row: Mapping[str, Any]) -> bool:
        rsi = _numeric(row.get("rsi"))
        if rsi is None:
            return False
        if rsi <= thresholds.rsi_max:
            return True
        previous = _numeric(row.get("prev_rsi"))
        return previous is not None and previous < thresholds.rsi_cross_floor <= rsi

    def pullback_trend(row: Mapping[str, Any]) -> bool:
        close = _numeric(row.get("close"))
        sma20 = _numeric(row.get("sma20"))
        if close is None or sma20 is None or sma20 <= 0:
            return False
        if not _above(close, row.get("sma200")):
            return False
        return abs(close / sma20 - 1) <= thresholds.sma20_band

    def bollinger_squeeze(row: Mapping[str, Any]) -> bool:
        width = _numeric(row.get("bb_width"))
        if width is None or width <= 0 or width > thresholds.bb_width_max:
            return False
        return _at_least(row.get("close"), _scaled(row.get("bb_upper"), thresholds.bb_upper_ratio))

    def relative_strength(row: Mapping[str, Any]) -> bool:
        return _at_least(
            row.get("relative_strength_20d"), thresholds.relative_strength_20d_min
        ) and _at_least(row.get("relative_strength_60d"), thresholds.relative_strength_60d_min)

    return {
        "breakout_volume": breakout_volume,
        "rsi_rebound": rsi_rebound,
        "pullback_trend": pullback_trend,
        "bollinger_squeeze": bollinger_squeeze,
        "relative_strength": relative_strength,
    }.get(profile, lambda row: _above(row.get("close"), 0))


def _relaxation_trace(
    profile: str, rounds: list[dict[str, Any]], universe_rows: int
) -> dict[str, Any]:
    final = rounds[-1] if rounds else {}
    return {
        "profile": profile,
        "universe_rows": universe_rows,
        "rounds": rounds,
        "relaxation_rounds": max(len(rounds) - 1, 0),
        "relaxed": bool(final.get("relaxed")) and bool(final.get("matched_count")),
        "matched_count": int(final.get("matched_count") or 0),
    }


def _propose_relaxed_thresholds(
    *,
    query: str,
    profile: str,
    thresholds: ScreeningThresholds,
    round_index: int,
    universe_rows: int,
) -> ScreeningThresholds:
    """Ask the LLM to loosen the screen, falling back to the deterministic ladder."""

    deterministic = _relaxed_thresholds(thresholds, round_index)
    try:
        # Imported lazily: ai_graph.llm pulls in the provider stack, which must stay
        # optional for fixture-only runs of this module.
        from ai_graph.llm.role_calls import generate_relaxed_screening_thresholds
    except ImportError:
        return deterministic

    proposal = generate_relaxed_screening_thresholds(
        query=query,
        profile=profile,
        current=thresholds.model_dump(),
        fallback=deterministic.model_dump(),
        round_index=round_index,
        universe_rows=universe_rows,
    )
    known = {key: value for key, value in proposal.items() if key in ScreeningThresholds.model_fields}
    try:
        return ScreeningThresholds.model_validate(known)
    except ValidationError:
        return deterministic


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


def _screening_sql(profile: str, *, sector: str | None = None) -> str:
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
    }.get(profile, "close > 0")
    sector_predicate = "\n              AND sm.sector = %s" if sector else ""
    # Universe membership comes from feature.kis_adjusted_ohlcv_daily itself (a ticker is
    # in-scope if it has recent adjusted-price rows), not meta.view_common_stock_universe —
    # see SYMBOL_MASTER_TABLE comment above for why that view is unusable right now.
    # core.symbol_master is still joined (LEFT, so a missing row can't drop a ticker) purely
    # for display fields (name/market/sector), never as a membership filter.
    return f"""
        WITH latest_date AS (
            SELECT max(time) AS as_of_date
            FROM feature.kis_adjusted_ohlcv_daily
        ),
        prices AS (
            SELECT
                p.time,
                p.ticker,
                sm.name,
                sm.market,
                sm.market_segment,
                sm.sector,
                p.adj_open AS open,
                p.adj_high AS high,
                p.adj_low AS low,
                p.adj_close AS close,
                p.adj_volume AS volume
            FROM feature.kis_adjusted_ohlcv_daily p
            LEFT JOIN core.symbol_master sm
              ON sm.symbol = p.ticker
            WHERE p.time >= (SELECT as_of_date FROM latest_date) - INTERVAL '420 days'{sector_predicate}
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
            -- ta_momentum_ticker_daily keys tickers as '000020#S05' (6-digit code plus a
            -- security-type suffix) while kis_adjusted_ohlcv_daily keys them as '000020',
            -- so joining the raw columns matches nothing and every rsi comes back NULL.
            -- Strip the suffix here; DISTINCT ON keeps one row per (ticker, time) when
            -- several security types collapse onto the same 6-digit code.
            SELECT DISTINCT ON (split_part(ticker, '#', 1), time)
                time,
                split_part(ticker, '#', 1) AS ticker,
                COALESCE(
                    values_jsonb->>'RSI_14',
                    values_jsonb->>'rsi_14',
                    values_jsonb->>'RSI',
                    values_jsonb->>'rsi'
                ) AS rsi_text
            FROM feature.ta_momentum_ticker_daily
            WHERE time >= (SELECT as_of_date FROM latest_date) - INTERVAL '90 days'
            ORDER BY split_part(ticker, '#', 1), time, ticker
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
        matched AS (
            SELECT
                latest_rows.*,
                COALESCE(return_20d, 0) - COALESCE(market.market_return_20d, 0) AS relative_strength_20d,
                COALESCE(return_60d, 0) - COALESCE(market.market_return_60d, 0) AS relative_strength_60d
            FROM latest_rows
            CROSS JOIN market
        )
        SELECT *
        FROM matched
        WHERE {where_clause}
        ORDER BY ticker
    """


def _screening_candidate_from_row(
    row: Mapping[str, Any], profile: str, *, sector: str | None = None
) -> dict[str, Any]:
    volume_ratio = _optional_float_value(row.get("volume_ratio_20"))
    relative_strength = _optional_float_value(row.get("relative_strength_20d"))
    close = _optional_float_value(row.get("close"))
    return {
        "ticker": str(row.get("ticker") or "").zfill(6),
        "name": row.get("name") or "",
        "market": row.get("market_segment") or row.get("market") or "KRX",
        "sector": row.get("sector") or sector,
        "as_of_date": _date_value(row.get("time")).isoformat(),
        "screening_profile": profile,
        "close": close,
        "volume_ratio_20": volume_ratio,
        "rsi": _optional_float_value(row.get("rsi")),
        "relative_strength_20d": relative_strength,
        "relative_strength_60d": _optional_float_value(row.get("relative_strength_60d")),
        "matched_rules": _matched_screening_rules(row, profile),
    }


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


def _has_market_scope_reference(query: str) -> bool:
    normalized_query = query.upper()
    return any(term.upper() in normalized_query for term in MARKET_SCOPE_TERMS)


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
    symbol_info: Mapping[str, Any],
) -> dict[str, Any]:
    trade_date = _date_value(row["as_of_date"])
    return {
        **dict(row),
        "as_of_date": trade_date,
        "name": symbol_info.get("name") or "",
        "market_segment": symbol_info.get("market_segment") or "KRX",
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
