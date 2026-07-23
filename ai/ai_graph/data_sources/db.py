from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import logging

from .sectors import extract_sector_from_query, get_known_sectors

_logger = logging.getLogger(__name__)


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
AI_DB_BACKTEST_STATEMENT_TIMEOUT_MS_ENV = "AI_DB_BACKTEST_STATEMENT_TIMEOUT_MS"
AI_BACKTEST_MAX_TICKERS_ENV = "AI_BACKTEST_MAX_TICKERS"

DEFAULT_BACKTEST_TICKER = "005930"
TRADING_DAYS_PER_YEAR = 252
DEFAULT_BACKTEST_LOOKBACK_YEARS = 10
DEFAULT_BACKTEST_LOOKBACK_DAYS = TRADING_DAYS_PER_YEAR * DEFAULT_BACKTEST_LOOKBACK_YEARS
DEFAULT_L4_EVIDENCE_LIMIT = 5
# Screening can match hundreds of names; every extra ticker multiplies the price rows
# pulled for the backtest (lookback_days each), so the pool is capped rather than
# loading the whole match set.
DEFAULT_BACKTEST_MAX_TICKERS = 20
# Financial metrics we track a consecutive-rise count for (for "N quarters rising"
# strategies). Computed sequentially per filing; see _fetch_financial_timeline.
_STREAK_METRICS = ("revenue", "operating_income", "operating_margin", "roe")
# 조건에 일치한 종목은 점수로 다시 줄이지 않고 모두 추천 결과에 남긴다.
DEFAULT_DB_CONNECT_TIMEOUT_SECONDS = 20
DEFAULT_DB_STATEMENT_TIMEOUT_MS = 30_000
# The universe backtest load (200-name KOSPI200 price/momentum/financial history) is a
# genuinely heavy analytical scan and needs a longer budget than a quick screening SELECT.
# Expanding the backtest universe from ~20 to 200 names is what pushed it past the 30s
# default and started timing out; screening queries keep the tight default.
DEFAULT_DB_BACKTEST_STATEMENT_TIMEOUT_MS = 120_000
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
DART_FINANCIAL_TABLE = "mart.dart_financial_asof"
# DART accounts are stored as objects, with the figure under "amount" and the prior
# period under raw.frmtrm_amount. Values are text and not always numeric.
DART_ACCOUNTS = {
    "equity": "ifrs-full_Equity",
    "liabilities": "ifrs-full_Liabilities",
    "profit_loss": "ifrs-full_ProfitLoss",
    "revenue": "ifrs-full_Revenue",
    "operating_income": "dart_OperatingIncomeLoss",
    "eps": "ifrs-full_BasicEarningsLossPerShare",
}

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
    backtest_statement_timeout_ms: int = Field(
        default=DEFAULT_DB_BACKTEST_STATEMENT_TIMEOUT_MS, gt=0
    )
    backtest_max_tickers: int = Field(default=DEFAULT_BACKTEST_MAX_TICKERS, gt=0)

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
            backtest_statement_timeout_ms=_int_env(
                env,
                AI_DB_BACKTEST_STATEMENT_TIMEOUT_MS_ENV,
                DEFAULT_DB_BACKTEST_STATEMENT_TIMEOUT_MS,
            ),
            backtest_max_tickers=_int_env(
                env, AI_BACKTEST_MAX_TICKERS_ENV, DEFAULT_BACKTEST_MAX_TICKERS
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
                # The matched names are the recommendation ("buy these today"). The
                # backtest, though, runs over a liquidity-selected universe so build_signals
                # can enter and exit per date across many names instead of replaying the
                # past of whichever handful is at a high right now. Recommendation and
                # backtest universe are deliberately different things.
                recommended = [str(item["ticker"]).zfill(6) for item in screening_candidates]
                tickers = self._fetch_backtest_universe(conn, recommended)
                ticker = recommended[0]
                symbol_info_by_ticker = self._fetch_symbol_info_map(conn, tickers)
                symbol_info = symbol_info_by_ticker.get(ticker, {"ticker": ticker, "included": False})
                # Widen the statement timeout for the universe price/momentum/financial
                # scan - it is far heavier than the screening SELECTs above and 30s is not
                # enough once the backtest universe is 200 names.
                self._set_statement_timeout(conn, self.config.backtest_statement_timeout_ms)
                price_rows, effective_lookback_days = self._fetch_price_rows(
                    conn, tickers, symbol_info_by_ticker, query
                )
                self._set_statement_timeout(conn)
            elif single_ticker:
                ticker = single_ticker
                tickers = [ticker]
                symbol_info = self._fetch_symbol_info(conn, ticker)
                price_rows, effective_lookback_days = self._fetch_price_rows(
                    conn, tickers, {ticker: symbol_info}, query
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
            capability_availability = measure_capabilities(conn)

        return PipelineDataBundle(
            price_rows=price_rows,
            screening_candidates=screening_candidates,
            l4_evidence=l4_evidence,
            data_availability=_data_availability_for_query(
                query, source="postgres", available=capability_availability
            ),
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

    def _fetch_backtest_universe(self, conn: Any, recommended: Sequence[str]) -> list[str]:
        """The universe the backtest actually trades over: KOSPI 200.

        The screen answers "which names meet the condition today"; using that as the
        backtest universe means trading only the two stocks that happen to be at a
        52-week high right now, then judging the strategy on their past - which is
        look-ahead, since being at a high today is exactly "went up in the past". The
        generated build_signals already decides entries per date from each stock's own
        history, so it just needs a fixed, outcome-independent market to trade in.

        KOSPI 200 is that market. There is no index-membership table, so it is
        approximated the standard way - the 200 largest KOSPI common stocks by market
        cap (MKTCAP on symbol_master). The strategy's recommended names are unioned in so
        they remain tradable even if one sits just outside the top 200.
        """

        rows = conn.execute(
            """
            SELECT symbol
            FROM core.symbol_master
            WHERE market = 'KOSPI'
              AND security_type = '보통주'
              AND metadata_jsonb->>'MKTCAP' ~ '^[0-9]+$'
            ORDER BY (metadata_jsonb->>'MKTCAP')::numeric DESC
            LIMIT 200
            """
        ).fetchall()
        universe = [str(row["symbol"]).zfill(6) for row in rows]
        seen = set(universe)
        # Recommended names first, then KOSPI 200, so a recommendation is never dropped.
        extra = [t for t in (str(x).zfill(6) for x in recommended) if t not in seen]
        return [*extra, *universe]

    def _fetch_screening_candidates(self, conn: Any, query: str) -> list[dict[str, Any]]:
        return self._screen_with_relaxation(conn, query)[0]

    def _screen_via_llm(
        self, conn: Any, query: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
        """Let the model write the screen against the real schema.

        Returns None when that path is unavailable - no live provider, or it could not
        produce a usable query - so screening falls back to the deterministic profiles
        rather than failing the analysis.
        """

        try:
            from ai_graph.data_sources.llm_screen import screen_with_llm

            result = screen_with_llm(conn, query)
        except Exception:
            _logger.exception("LLM screening failed; falling back to profile screening")
            return None
        finally:
            # statement_timeout is set transaction-locally, and this path rolls back
            # after a failed query - which discards it. Without this the rest of the
            # load runs with no timeout at all, so one bad plan hangs the analysis
            # instead of erroring out.
            self._set_statement_timeout(conn)
        if not result or not result.get("rows"):
            return None

        sector = None
        candidates = [
            _llm_screening_candidate(row, sector=sector) for row in result["rows"]
        ]
        trace = {
            "mode": "llm_authored_sql",
            "attempts": result.get("attempts") or [],
            "metrics": result.get("metrics") or [],
            "unmet_requirements": result.get("unmet_requirements") or [],
            "research": result.get("research"),
            "matched_count": len(candidates),
            "relaxed": len(result.get("attempts") or []) > 1,
            "relaxation_rounds": max(len(result.get("attempts") or []) - 1, 0),
            # The screen's rule as structured conditions, carried so the strategy spec
            # (and eventually the backtest) can reuse the exact same definition.
            "entry_conditions": result.get("entry_conditions") or [],
            "exit_conditions": result.get("exit_conditions") or [],
        }
        return candidates, trace

    def _screen_with_relaxation(
        self, conn: Any, query: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Screen for candidates, progressively loosening the thresholds until some match.

        An empty strict screen is a normal market outcome (on a given day nothing may
        sit at a 52-week high *and* on a volume surge), not a failure, so instead of
        giving up we re-ask for a looser screen and retry - recording every round so
        the report can disclose that the conditions were widened.
        """

        llm_result = self._screen_via_llm(conn, query)
        if llm_result is not None:
            return llm_result

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

    def _set_statement_timeout(self, conn: Any, timeout_ms: int | None = None) -> None:
        effective_ms = self.config.statement_timeout_ms if timeout_ms is None else timeout_ms
        timeout_value = f"{effective_ms}{POSTGRES_TIMEOUT_UNIT}"
        # is_local=true: scoped to the current transaction, so the caller can widen the
        # budget for a heavy fetch and have it revert on the next transaction on its own.
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
        self,
        conn: Any,
        tickers: Sequence[str],
        symbol_info_by_ticker: Mapping[str, Mapping[str, Any]],
        query: str,
    ) -> tuple[list[dict[str, Any]], int]:
        lookback_days = self.config.backtest_lookback_days
        price_rows = self._fetch_price_rows_for_lookback(
            conn, tickers, symbol_info_by_ticker, lookback_days
        )
        if (
            _query_requires_rsi_oversold(query)
            and lookback_days < DEFAULT_BACKTEST_LOOKBACK_DAYS
            and not _has_rsi_oversold_entry(price_rows)
        ):
            lookback_days = DEFAULT_BACKTEST_LOOKBACK_DAYS
            price_rows = self._fetch_price_rows_for_lookback(
                conn, tickers, symbol_info_by_ticker, lookback_days
            )
        return price_rows, lookback_days

    def _fetch_price_rows_for_lookback(
        self,
        conn: Any,
        tickers: Sequence[str],
        symbol_info_by_ticker: Mapping[str, Mapping[str, Any]],
        lookback_days: int,
    ) -> list[dict[str, Any]]:
        calendar_lookback_days = (
            lookback_days * BACKTEST_LOOKBACK_CALENDAR_DAY_MULTIPLIER
        )
        ticker_list = list(tickers)
        # row_number keeps the lookback per ticker: a plain LIMIT would spend the whole
        # budget on whichever ticker sorted first and starve the rest.
        rows = conn.execute(
            """
            SELECT as_of_date, ticker, open, high, low, close, volume,
                   adjusted_ohlcv_quality_flags
            FROM (
                SELECT
                    time AS as_of_date,
                    ticker,
                    adj_open AS open,
                    adj_high AS high,
                    adj_low AS low,
                    adj_close AS close,
                    adj_volume AS volume,
                    quality_flags AS adjusted_ohlcv_quality_flags,
                    row_number() OVER (PARTITION BY ticker ORDER BY time DESC) AS ticker_rank
                FROM feature.kis_adjusted_ohlcv_daily
                WHERE ticker = ANY(%s)
                  AND time >= CURRENT_DATE - make_interval(days => %s)
            ) ranked
            WHERE ticker_rank <= %s
            ORDER BY ticker, as_of_date
            """,
            [ticker_list, calendar_lookback_days, lookback_days],
        ).fetchall()
        momentum_by_ticker = self._fetch_momentum_values_by_date(
            conn, ticker_list, calendar_lookback_days, lookback_days
        )
        financials_by_ticker = self._fetch_financial_timeline(conn, ticker_list)
        price_rows = [
            _price_row_from_feature_frame_record(
                _feature_frame_row_from_sources(
                    row,
                    momentum_by_ticker.get(str(row.get("ticker") or "").zfill(6), {}),
                    symbol_info_by_ticker.get(str(row.get("ticker") or "").zfill(6), {}),
                )
            )
            for row in rows
        ]
        _attach_pointintime_financials(price_rows, financials_by_ticker)
        return price_rows

    def _fetch_financial_timeline(
        self, conn: Any, tickers: Sequence[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Each ticker's filings as a time-ordered list of (filed_date, ratios).

        Loaded small (tens of filings per name) and forward-filled onto trading days in
        Python; the SQL as-of join was ~30 minutes over the universe, this is seconds.

        The filing date is the DART receipt number's date (rcept_no's first 8 digits),
        NOT available_from - that column is the warehouse load date (mostly 2026-06), so
        joining on it would hide every filing before the load and make the whole backtest
        look-ahead or empty.
        """

        rows = conn.execute(
            f"""
            WITH filings AS (
                SELECT
                    symbol,
                    to_date(left(accounts_jsonb->'ifrs-full_Equity'->'raw'->>'rcept_no', 8),
                            'YYYYMMDD') AS filed,
                    {_dart_amount('equity')} AS equity,
                    {_dart_amount('liabilities')} AS liabilities,
                    {_dart_amount('profit_loss')} AS profit_loss,
                    {_dart_amount('revenue')} AS revenue,
                    {_dart_amount('operating_income')} AS operating_income
                FROM {DART_FINANCIAL_TABLE}
                WHERE symbol = ANY(%s)
                  AND left(accounts_jsonb->'ifrs-full_Equity'->'raw'->>'rcept_no', 8) ~ '^[0-9]{{8}}$'
            )
            SELECT symbol, filed, equity, liabilities, profit_loss, revenue, operating_income
            FROM filings
            WHERE filed IS NOT NULL
            ORDER BY symbol, filed
            """,
            [list(tickers)],
        ).fetchall()

        timelines: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            ticker = str(row.get("symbol") or "").zfill(6)
            equity = _optional_float_value(row.get("equity"))
            liabilities = _optional_float_value(row.get("liabilities"))
            profit = _optional_float_value(row.get("profit_loss"))
            revenue = _optional_float_value(row.get("revenue"))
            operating = _optional_float_value(row.get("operating_income"))
            ratios: dict[str, float] = {}
            if equity and equity > 0:
                if profit is not None:
                    ratios["roe"] = profit / equity
                if liabilities is not None:
                    ratios["debt_to_equity"] = liabilities / equity
            if revenue and revenue > 0 and operating is not None:
                ratios["operating_margin"] = operating / revenue
            if operating is not None:
                ratios["operating_income"] = operating
            if revenue is not None:
                ratios["revenue"] = revenue
            timelines.setdefault(ticker, []).append(
                {"filed": _date_value(row["filed"]), "ratios": ratios}
            )

        # Consecutive-rise counts for "N quarters of rising revenue/profit" strategies.
        # Sequential (each filing vs the one before), not year-over-year: we don't carry
        # report_code here to line up the same quarter across years, so seasonal drops
        # (Q1 < prior Q4) can break a streak that a YoY view would keep. Documented so the
        # backtest treats these as sequential-rise, not calendar-quarter-YoY.
        for filings in timelines.values():
            previous: dict[str, float] = {}
            streaks: dict[str, int] = {}
            for filing in filings:  # already ordered oldest-first (ORDER BY symbol, filed)
                ratios = filing["ratios"]
                for metric in _STREAK_METRICS:
                    value = ratios.get(metric)
                    if value is None:
                        continue
                    prior = previous.get(metric)
                    if prior is not None:
                        streaks[metric] = streaks.get(metric, 0) + 1 if value > prior else 0
                    ratios[f"{metric}_up_streak"] = streaks.get(metric, 0)
                    previous[metric] = value
        return timelines

    def _fetch_momentum_values_by_date(
        self, conn: Any, tickers: Sequence[str], calendar_lookback_days: int, lookback_days: int
    ) -> dict[str, dict[date, Mapping[str, Any]]]:
        rows = conn.execute(
            """
            SELECT base_ticker, time, values_jsonb
            FROM (
                SELECT DISTINCT ON (split_part(ticker, '#', 1), time)
                    split_part(ticker, '#', 1) AS base_ticker,
                    time,
                    values_jsonb
                FROM feature.ta_momentum_ticker_daily
                WHERE split_part(ticker, '#', 1) = ANY(%s)
                  AND time >= CURRENT_DATE - make_interval(days => %s)
                ORDER BY split_part(ticker, '#', 1), time, ticker
            ) deduped
            """,
            [list(tickers), calendar_lookback_days],
        ).fetchall()
        values_by_ticker: dict[str, dict[date, Mapping[str, Any]]] = {}
        for row in rows:
            values = row.get("values_jsonb")
            ticker_key = str(row.get("base_ticker") or "").zfill(6)
            values_by_ticker.setdefault(ticker_key, {})[_date_value(row["time"])] = (
                values if isinstance(values, Mapping) else {}
            )
        return values_by_ticker

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

    def _fetch_symbol_info_map(
        self, conn: Any, tickers: Sequence[str]
    ) -> dict[str, dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT symbol, name, market, market_segment, listing_status
            FROM core.symbol_master
            WHERE symbol = ANY(%s)
            """,
            [list(tickers)],
        ).fetchall()
        found = {
            str(row.get("symbol") or "").zfill(6): {
                "ticker": str(row.get("symbol") or "").zfill(6),
                "included": True,
                "name": row.get("name"),
                "market": row.get("market"),
                "market_segment": row.get("market_segment"),
                "listing_status": row.get("listing_status"),
            }
            for row in rows
        }
        # symbol_master is a display-only join (see _screening_sql), so a ticker missing
        # from it still trades - it just has no name/market to show.
        return {
            ticker: found.get(ticker, {"ticker": ticker, "included": False})
            for ticker in tickers
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
    # Fundamentals, from the latest DART filing available as of the screening date.
    roe_min: float = Field(default=0.08, ge=-1.0, le=1.0)
    debt_to_equity_max: float = Field(default=2.0, ge=0.1, le=20.0)
    operating_margin_min: float = Field(default=0.05, ge=-1.0, le=1.0)
    revenue_growth_min: float = Field(default=0.10, ge=-1.0, le=10.0)


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
            "roe_min": _clamped(base.roe_min - 0.02 * step, -1.0, 1.0),
            "debt_to_equity_max": _clamped(base.debt_to_equity_max + 0.5 * step, 0.1, 20.0),
            "operating_margin_min": _clamped(
                base.operating_margin_min - 0.02 * step, -1.0, 1.0
            ),
            "revenue_growth_min": _clamped(base.revenue_growth_min - 0.03 * step, -1.0, 10.0),
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

    def value_quality(row: Mapping[str, Any]) -> bool:
        return (
            _at_least(row.get("roe"), thresholds.roe_min)
            and _numeric(row.get("debt_to_equity")) is not None
            and _numeric(row["debt_to_equity"]) <= thresholds.debt_to_equity_max
        )

    def quality_growth(row: Mapping[str, Any]) -> bool:
        return (
            _at_least(row.get("roe"), thresholds.roe_min)
            and _at_least(row.get("operating_margin"), thresholds.operating_margin_min)
            and _at_least(row.get("revenue_growth_yoy"), thresholds.revenue_growth_min)
        )

    def growth_momentum(row: Mapping[str, Any]) -> bool:
        return _at_least(row.get("revenue_growth_yoy"), thresholds.revenue_growth_min) and _above(
            row.get("close"), row.get("sma50")
        )

    return {
        "breakout_volume": breakout_volume,
        "rsi_rebound": rsi_rebound,
        "pullback_trend": pullback_trend,
        "bollinger_squeeze": bollinger_squeeze,
        "relative_strength": relative_strength,
        "value_quality": value_quality,
        "quality_growth": quality_growth,
        "growth_momentum": growth_momentum,
    }.get(profile, lambda row: _above(row.get("close"), 0))


def _llm_screening_candidate(row: Mapping[str, Any], *, sector: str | None) -> dict[str, Any]:
    """Shape an LLM-screened row into a candidate card.

    The query chose its own metric columns, so anything beyond the identifiers is
    carried through as-is under `metrics` instead of being forced into a fixed set.
    """

    ticker = str(row.get("ticker") or "").zfill(6)
    reserved = {"ticker", "name", "market", "market_segment", "sector", "as_of_date", "time"}
    metrics = {
        key: _optional_float_value(value) if _numeric(value) is not None else value
        for key, value in row.items()
        if key not in reserved
    }
    return {
        # ScreeningMatch requires a non-empty name and market, and the generated SQL is
        # only asked for a ticker and its metrics - fall back to the code rather than
        # letting a blank identity fail validation and take the analysis with it.
        "ticker": ticker,
        "name": row.get("name") or ticker,
        "market": row.get("market_segment") or row.get("market") or "KRX",
        "sector": row.get("sector") or sector,
        "as_of_date": _date_value(row.get("as_of_date") or row.get("time") or datetime.now(UTC)).isoformat(),
        "screening_profile": "llm_authored_sql",
        "close": _optional_float_value(row.get("close")),
        "volume_ratio_20": _optional_float_value(row.get("volume_ratio_20")),
        "rsi": _optional_float_value(row.get("rsi")),
        "relative_strength_20d": _optional_float_value(row.get("relative_strength_20d")),
        "relative_strength_60d": _optional_float_value(row.get("relative_strength_60d")),
        "roe": _optional_float_value(row.get("roe")),
        "debt_to_equity": _optional_float_value(row.get("debt_to_equity")),
        "operating_margin": _optional_float_value(row.get("operating_margin")),
        "revenue_growth_yoy": _optional_float_value(row.get("revenue_growth_yoy")),
        "metrics": metrics,
        "matched_rules": [f"{key}={value}" for key, value in list(metrics.items())[:6]],
    }


def _backtest_ticker_pool(
    screening_candidates: Sequence[Mapping[str, Any]], max_tickers: int
) -> list[str]:
    """Pick which matched names the backtest actually trades.

    The screen returns rows ordered by ticker code, so truncating it as-is would select
    by numeric code - meaningless. Rank by 20-day relative strength (already computed
    for every row) so the cap keeps the strongest matches, and keep the order stable for
    rows that share a score.
    """

    ranked = sorted(
        screening_candidates,
        key=lambda item: (
            _numeric(item.get("relative_strength_20d")) is None,
            -(_numeric(item.get("relative_strength_20d")) or 0.0),
        ),
    )
    pool: list[str] = []
    for item in ranked[:max_tickers]:
        ticker = str(item.get("ticker") or "").zfill(6)
        if ticker and ticker not in pool:
            pool.append(ticker)
    return pool


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


def _mentions_fundamentals(query: str, terms: Sequence[str]) -> bool:
    lowered = query.lower()
    return any(term.lower() in lowered for term in terms)


def _screening_profile(query: str) -> str:
    lowered = query.lower()
    # Fundamental intent is checked first and on stronger evidence than the technical
    # keywords below. Without this a query like "저PER·고ROE·부채비율" fell through to a
    # price-only profile and silently returned the same names as an unrelated momentum
    # screen - different strategies, identical candidates.
    if _mentions_fundamentals(query, ("roe", "per", "pbr", "부채비율", "저평가", "가치주")):
        return "value_quality"
    if _mentions_fundamentals(query, ("영업이익률", "퀄리티", "이익률")):
        return "quality_growth"
    if _mentions_fundamentals(query, ("매출 성장", "매출성장", "성장률", "성장주")):
        return "growth_momentum"
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


def _dart_amount(field: str, *, prior: bool = False) -> str:
    """SQL for one DART figure, guarded so non-numeric text yields NULL rather than erroring."""

    account = DART_ACCOUNTS[field]
    path = (
        f"accounts_jsonb->'{account}'->'raw'->>'frmtrm_amount'"
        if prior
        else f"accounts_jsonb->'{account}'->>'amount'"
    )
    return f"CASE WHEN {path} ~ '^-?[0-9]+$' THEN ({path})::numeric END"


def _financial_cte() -> str:
    """Latest DART filing per symbol, as ratios, joined into screening.

    Filings are selected on available_from - the date the statement became public -
    rather than period_end, so a screen never sees numbers that were not yet filed.
    Revenue growth compares against the same report_code roughly a year earlier;
    raw.frmtrm_amount is present too rarely (4% of symbols) to rely on.
    """

    return f"""financial_raw AS (
            SELECT
                symbol,
                period_end,
                available_from,
                report_code,
                {_dart_amount('equity')} AS equity,
                {_dart_amount('liabilities')} AS liabilities,
                {_dart_amount('profit_loss')} AS profit_loss,
                {_dart_amount('revenue')} AS revenue,
                {_dart_amount('operating_income')} AS operating_income,
                {_dart_amount('eps')} AS eps
            FROM {DART_FINANCIAL_TABLE}
            -- Only the newest filing per symbol is used, and a year-ago comparison for
            -- growth, so there is no reason to scan back to 2016.
            WHERE available_from <= (SELECT as_of_date FROM latest_date)
              AND available_from >= (SELECT as_of_date FROM latest_date) - INTERVAL '3 years'
        ),
        financial_latest AS (
            SELECT DISTINCT ON (symbol) *
            FROM financial_raw
            ORDER BY symbol, available_from DESC, period_end DESC
        ),
        financials AS (
            SELECT
                current_filing.symbol,
                current_filing.period_end AS financial_period_end,
                CASE
                    WHEN current_filing.equity > 0
                    THEN current_filing.profit_loss / current_filing.equity
                END AS roe,
                CASE
                    WHEN current_filing.equity > 0
                    THEN current_filing.liabilities / current_filing.equity
                END AS debt_to_equity,
                CASE
                    WHEN current_filing.revenue > 0
                    THEN current_filing.operating_income / current_filing.revenue
                END AS operating_margin,
                CASE
                    WHEN current_filing.revenue > 0 AND prior_filing.revenue > 0
                    THEN current_filing.revenue / prior_filing.revenue - 1
                END AS revenue_growth_yoy,
                current_filing.eps
            FROM financial_latest current_filing
            LEFT JOIN financial_raw prior_filing
              ON prior_filing.symbol = current_filing.symbol
             AND prior_filing.report_code = current_filing.report_code
             AND prior_filing.period_end BETWEEN current_filing.period_end - INTERVAL '400 days'
                                             AND current_filing.period_end - INTERVAL '330 days'
        )"""


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
            -- The window is what makes this affordable: the table has 531 date
            -- partitions and an unbounded max() locks every one of them. With
            -- max_locks_per_transaction at 64 the whole statement then dies with
            -- "out of shared memory" before it reads a single row.
            SELECT max(time) AS as_of_date
            FROM feature.kis_adjusted_ohlcv_daily
            WHERE time >= CURRENT_DATE - INTERVAL '90 days'
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
        {_financial_cte()},
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
                close * volume AS turnover,
                fin.roe,
                fin.debt_to_equity,
                fin.operating_margin,
                fin.revenue_growth_yoy,
                -- PER needs no share count: DART reports basic EPS directly.
                CASE WHEN fin.eps > 0 THEN close / fin.eps END AS per,
                fin.financial_period_end
            FROM features f
            LEFT JOIN momentum_with_prev mwp
              ON mwp.ticker = f.ticker AND mwp.time = f.time
            -- LEFT so a ticker without filings still screens on price alone; the
            -- fundamental predicates simply will not match it.
            LEFT JOIN financials fin ON fin.symbol = f.ticker
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
        "roe": _optional_float_value(row.get("roe")),
        "debt_to_equity": _optional_float_value(row.get("debt_to_equity")),
        "operating_margin": _optional_float_value(row.get("operating_margin")),
        "revenue_growth_yoy": _optional_float_value(row.get("revenue_growth_yoy")),
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
    roe = _optional_float_value(row.get("roe"))
    if roe is not None:
        rules.append(f"ROE {roe:.1%}")
    debt_to_equity = _optional_float_value(row.get("debt_to_equity"))
    if debt_to_equity is not None:
        rules.append(f"부채비율 {debt_to_equity:.0%}")
    operating_margin = _optional_float_value(row.get("operating_margin"))
    if operating_margin is not None:
        rules.append(f"영업이익률 {operating_margin:.1%}")
    revenue_growth = _optional_float_value(row.get("revenue_growth_yoy"))
    if revenue_growth is not None:
        rules.append(f"매출성장률 {revenue_growth:+.1%}")
    return rules


def _compare(left: Any, right: Any, *, factor: float = 1.0) -> bool:
    left_value = _optional_float_value(left)
    right_value = _optional_float_value(right)
    if left_value is None or right_value is None:
        return False
    return left_value >= right_value * factor


# What each kind of condition needs, and how to tell whether we actually have it.
# `probe` is a table that must contain rows; `supported=False` marks something the
# warehouse cannot express at all, regardless of what is loaded.
DATA_CAPABILITIES: dict[str, dict[str, Any]] = {
    "price_ta": {
        "label": "가격·기술지표",
        "probe": KIS_ADJUSTED_OHLCV_TABLE,
        "terms": (),
    },
    "financial_statements": {
        "label": "재무제표(ROE·부채비율·영업이익률·매출성장률)",
        "probe": DART_FINANCIAL_TABLE,
        "terms": ("roe", "부채", "영업이익", "매출", "재무", "순이익", "이익률"),
    },
    "per": {
        "label": "PER",
        # Derived as price / basic EPS; DART reports EPS per share, so no share count
        # is needed. An earlier version assumed otherwise and wrongly blocked PER.
        "probe": DART_FINANCIAL_TABLE,
        "terms": ("per", "주가수익비율"),
    },
    "book_value_multiples": {
        "label": "PBR·배당수익률",
        # Both need a per-share book value or per-share dividend, and only aggregate
        # equity and total dividends paid are loaded.
        "supported": False,
        "reason": "주당순자산·주당배당금이 없어 PBR·배당수익률을 계산할 수 없습니다.",
        "terms": ("pbr", "배당수익률", "주당순자산"),
    },
    "institutional_flow": {
        "label": "기관·외국인 수급",
        "probe": "feature.seibro_universe_daily",
        "reason": "수급 데이터가 적재되어 있지 않습니다.",
        "terms": ("기관", "외국인", "순매수", "수급"),
    },
    "short_interest": {
        "label": "공매도 잔고",
        "supported": False,
        "reason": "공매도 잔고 데이터 소스가 연결되어 있지 않습니다.",
        "terms": ("공매도", "숏커버", "대차잔고"),
    },
    "earnings_revision": {
        "label": "실적 컨센서스 변화·가이던스",
        "supported": False,
        "reason": "컨센서스 추정치 시계열이 없어 상향/하향 판정이 불가능합니다.",
        "terms": ("컨센서스", "가이던스", "어닝 서프라이즈", "어닝서프라이즈", "eps 추정", "이익 전망"),
    },
    "analyst_reports": {
        "label": "애널리스트 리포트",
        "probe": ANALYST_REPORT_TABLE,
        "terms": ("리포트", "투자의견", "목표주가"),
    },
    "macro": {
        "label": "거시지표",
        "probe": BOK_MACRO_VIEW,
        "terms": ("금리", "환율", "원달러", "원자재"),
    },
}


def _required_capabilities(query: str) -> list[str]:
    lowered = query.lower()
    required = ["price_ta"]
    for name, spec in DATA_CAPABILITIES.items():
        terms = spec.get("terms") or ()
        if terms and any(term.lower() in lowered for term in terms):
            required.append(name)
    return required


def measure_capabilities(conn: Any) -> dict[str, bool]:
    """Check which capabilities the warehouse can actually serve right now.

    Availability used to be a hardcoded string, and it had drifted from reality in
    both directions - it claimed OpenDART was missing while 73k filings were loaded,
    and claimed macro was pilot-only while it was current.
    """

    available: dict[str, bool] = {}
    for name, spec in DATA_CAPABILITIES.items():
        if spec.get("supported") is False:
            available[name] = False
            continue
        probe = spec.get("probe")
        if not probe:
            available[name] = True
            continue
        try:
            row = conn.execute(f"SELECT EXISTS (SELECT 1 FROM {probe} LIMIT 1) AS present").fetchone()
            available[name] = bool(row and row.get("present"))
        except Exception:
            # A missing or unreadable table is simply an unavailable capability.
            available[name] = False
    return available


def unsupported_capabilities(query: str, available: Mapping[str, bool]) -> list[dict[str, str]]:
    unsupported = []
    for name in _required_capabilities(query):
        if available.get(name, True):
            continue
        spec = DATA_CAPABILITIES.get(name, {})
        unsupported.append(
            {
                "capability": name,
                "label": str(spec.get("label") or name),
                "reason": str(spec.get("reason") or "필요한 데이터가 적재되어 있지 않습니다."),
            }
        )
    return unsupported


def _data_availability_for_query(
    query: str, *, source: str, available: Mapping[str, bool] | None = None
) -> dict[str, Any]:
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
    measured = dict(available or {})
    unsupported = unsupported_capabilities(query, measured) if measured else []
    return {
        "source": source,
        "price_ta": "available" if source == "postgres" else "fixture",
        "open_dart": _availability_word(measured.get("financial_statements")),
        "bok_macro": _availability_word(measured.get("macro")),
        "seibro_report": _availability_word(measured.get("analyst_reports")),
        "agentic_web_search": "not_connected",
        "capabilities": {
            name: _availability_word(measured.get(name)) for name in DATA_CAPABILITIES
        },
        "required_capabilities": _required_capabilities(query),
        "unsupported_capabilities": unsupported,
        "proxy_used": proxy_used,
    }


def _availability_word(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "available" if value else "unavailable"


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


def _attach_pointintime_financials(
    price_rows: list[dict[str, Any]],
    financials_by_ticker: Mapping[str, list[dict[str, Any]]],
) -> None:
    """Forward-fill each trading day with the most recent filing available by that date.

    Point-in-time: a day sees only filings whose receipt date is on or before it, so the
    backtest never reads a number that had not yet been disclosed. Rows are grouped by
    ticker and walked in date order, advancing a pointer through that ticker's filings -
    O(rows + filings), not a per-row scan.
    """

    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in price_rows:
        by_ticker.setdefault(str(row.get("ticker") or "").zfill(6), []).append(row)

    for ticker, rows in by_ticker.items():
        filings = financials_by_ticker.get(ticker) or []
        if not filings:
            continue
        rows.sort(key=lambda item: str(item.get("date") or ""))
        pointer = 0
        current: dict[str, float] = {}
        for row in rows:
            row_date = _date_value(row.get("date"))
            while pointer < len(filings) and filings[pointer]["filed"] <= row_date:
                current = filings[pointer]["ratios"]
                pointer += 1
            for metric, value in current.items():
                row.setdefault(metric, value)


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
