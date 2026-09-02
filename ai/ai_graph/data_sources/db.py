from __future__ import annotations

import logging
import math
import os
import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.immutable_snapshot import build_snapshot_bundle
from ai_graph.quant_strategy import rsi_trade_rules
from ai_graph.research_eligibility import ResearchRuntimeFacts
from ai_graph.source_manifest import (
    build_pipeline_extract_snapshot,
    build_source_manifest,
    compute_pipeline_extract_hash,
)

from .sectors import extract_sector_from_query, get_known_sectors

_logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


AI_DATABASE_DSN_ENV = "AI_DATABASE_DSN"
QUANT_DB_DSN_ENV = "QUANT_DB_DSN"
DATABASE_URL_ENV = "DATABASE_URL"
DATABASE_DSN_ENV_CANDIDATES = (
    AI_DATABASE_DSN_ENV,
    QUANT_DB_DSN_ENV,
    DATABASE_URL_ENV,
)
AI_DEFAULT_TICKER_ENV = "AI_DEFAULT_TICKER"
AI_L4_EVIDENCE_LIMIT_ENV = "AI_L4_EVIDENCE_LIMIT"
AI_DB_CONNECT_TIMEOUT_SECONDS_ENV = "AI_DB_CONNECT_TIMEOUT_SECONDS"
AI_DB_STATEMENT_TIMEOUT_MS_ENV = "AI_DB_STATEMENT_TIMEOUT_MS"
AI_DB_BACKTEST_STATEMENT_TIMEOUT_MS_ENV = "AI_DB_BACKTEST_STATEMENT_TIMEOUT_MS"
AI_BACKTEST_MAX_TICKERS_ENV = "AI_BACKTEST_MAX_TICKERS"
AI_BACKTEST_LOOKBACK_YEARS_ENV = "AI_BACKTEST_LOOKBACK_YEARS"
AI_BACKTEST_UNIVERSE_MAX_TICKERS_ENV = "AI_BACKTEST_UNIVERSE_MAX_TICKERS"

DEFAULT_BACKTEST_TICKER = "005930"
TRADING_DAYS_PER_YEAR = 252
# The backtest window is a calendar window ending at the most recent settled KRX
# session, not a number of bars: the manifest records the resolved sessions for
# reproducibility.  The walk-forward exploration policy (V2) contracts on five years of
# history and `run_analysis` compares this constant to the sealed policy's
# `history_years`; the window the loader actually reads is a separate, tunable decision
# - see backtest_lookback_years.
BACKTEST_EVALUATION_YEARS = 5
DEFAULT_BACKTEST_LOOKBACK_DAYS = TRADING_DAYS_PER_YEAR * BACKTEST_EVALUATION_YEARS
# A five-year full-universe read is 3.2M price rows plus four TA families, which cost
# the production node 875s and ~21GB RSS for a single request.  One year is the default
# because it is what the 60-second budget affords; three is the ceiling, past which the
# node runs out of memory rather than time.
DEFAULT_BACKTEST_LOOKBACK_YEARS = 1
MIN_BACKTEST_LOOKBACK_YEARS = 1
MAX_BACKTEST_LOOKBACK_YEARS = 3
# The PIT window holds every common stock that was ever a member (1,717 over five
# years).  Loading all of them is what made the read unaffordable, so it is capped by
# liquidity measured *before* the window - see _fetch_backtest_universe.
DEFAULT_BACKTEST_UNIVERSE_MAX_TICKERS = 100
UNIVERSE_RANKING_SESSIONS = 60
DEFAULT_L4_EVIDENCE_LIMIT = 5
# A broad screen can match many names, but recommendations never define historical
# membership. They are presentation output only.
DEFAULT_BACKTEST_MAX_TICKERS = 20
_STREAK_METRICS = ("revenue", "operating_income", "operating_margin", "roe")
DEFAULT_DB_CONNECT_TIMEOUT_SECONDS = 20
DEFAULT_DB_STATEMENT_TIMEOUT_MS = 30_000
# A PIT KOSPI/KOSDAQ universe is substantially wider than a current large-cap proxy.
DEFAULT_DB_BACKTEST_STATEMENT_TIMEOUT_MS = 120_000
POSTGRES_TIMEOUT_UNIT = "ms"
RSI_OVERSOLD_THRESHOLD = 30.0
# Sentinel profile whose WHERE clause is the permissive `close > 0` baseline: screening
# selects the whole universe once and filters it per relaxation round in-process.
SCREENING_BASELINE_PROFILE = "__baseline__"
MAX_SCREENING_RELAXATION_ROUNDS = 3
# How far back the screen looks for the latest trading date. Wide enough to survive a
# long market closure or a stalled ingestion, narrow enough that chunk pruning keeps the
# lock footprint small - see _resolve_screening_date.
SCREENING_DATE_LOOKBACK_DAYS = 90

KIS_FEATURE_FRAME_VIEW = "mart.kis_adjusted_feature_frame_asof"
KIS_ADJUSTED_OHLCV_TABLE = "feature.kis_adjusted_ohlcv_daily"
# The base table mart.symbol_feature_frame_asof (and so KIS_FEATURE_FRAME_VIEW) is built
# from, together with the quality flag that view selects on. Read directly by
# _feature_frame_sql - see the comment there for why the view itself cannot be.
ADJUSTED_OHLCV_TABLE = "feature.adjusted_ohlcv_daily"
KIS_ADJUSTED_PRICE_METHOD = "kis_official_adjusted"
# Carried by the frame statement so log readers and tests can recognise it. The tables it
# reads are each read by other statements too, so matching on a table name would not
# identify this one.
FEATURE_FRAME_MARKER = "-- feature-frame:one-date"
TA_MOMENTUM_TICKER_TABLE = "feature.ta_momentum_ticker_daily"
TA_TREND_TICKER_TABLE = "feature.ta_trend_ticker_daily"
TA_VOLATILITY_TICKER_TABLE = "feature.ta_volatility_ticker_daily"
TA_VOLUME_TICKER_TABLE = "feature.ta_volume_ticker_daily"
PIT_UNIVERSE_VIEW = "mart.common_stock_universe_asof"
SYMBOL_LISTING_HISTORY_TABLE = "core.symbol_listing_history"
SYMBOL_MASTER_TABLE = "core.symbol_master"
ANALYST_REPORT_TABLE = "raw.analyst_report_summary"
BOK_MACRO_VIEW = "mart.bok_macro_asof"
# Official KRX total-return index levels and the published KOSPI/KOSDAQ split. The
# primary benchmark must be explicitly unavailable when these optional views are absent;
# it must never silently substitute the price-only universe proxy.
OFFICIAL_BENCHMARK_TR_VIEW = "mart.krx_index_total_return_daily"
OFFICIAL_BENCHMARK_WEIGHT_VIEW = "mart.krx_benchmark_monthly_weights"
OFFICIAL_BENCHMARK_INDEX_CODES = {"kospi_tr": "KOSPI_TR", "kosdaq_tr": "KOSDAQ_TR"}
# These codes may cross into report/metric contracts.  They intentionally contain no
# database driver text, SQL, host, or credential material.
OFFICIAL_BENCHMARK_LEVELS_UNAVAILABLE = "official_benchmark_levels_unavailable"
OFFICIAL_BENCHMARK_WEIGHTS_UNAVAILABLE = "official_benchmark_weights_unavailable"
OFFICIAL_BENCHMARK_LEVELS_MISSING = "official_benchmark_levels_missing"
OFFICIAL_BENCHMARK_WEIGHTS_MISSING = "official_benchmark_weights_missing"
# BOK ECOS daily 원/달러 rate. The only macro series the risk rules can be fed from
# directly; there is no equity index and no volatility index in this warehouse.
USD_KRW_SERIES_ID = "731Y003:0000003"
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
# The rebound screen deliberately runs wider than the textbook 30 so names that are still
# working off an oversold reading are not dropped a point early. That widening is why a
# match can carry RSI 33 while the strategy card reads "RSI <= 30", so the label prints the
# actual reading - "RSI 과매도권" alone let a 33 pass for a 30.
RSI_OVERSOLD_MAX = 35
RSI_OVERBOUGHT_MIN = 65
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
    l4_evidence_limit: int = Field(default=DEFAULT_L4_EVIDENCE_LIMIT, gt=0)
    connect_timeout_seconds: int = Field(default=DEFAULT_DB_CONNECT_TIMEOUT_SECONDS, gt=0)
    statement_timeout_ms: int = Field(default=DEFAULT_DB_STATEMENT_TIMEOUT_MS, gt=0)
    backtest_statement_timeout_ms: int = Field(
        default=DEFAULT_DB_BACKTEST_STATEMENT_TIMEOUT_MS, gt=0
    )
    backtest_max_tickers: int = Field(default=DEFAULT_BACKTEST_MAX_TICKERS, gt=0)
    backtest_lookback_years: int = Field(
        default=DEFAULT_BACKTEST_LOOKBACK_YEARS,
        ge=MIN_BACKTEST_LOOKBACK_YEARS,
        le=MAX_BACKTEST_LOOKBACK_YEARS,
    )
    backtest_universe_max_tickers: int = Field(
        default=DEFAULT_BACKTEST_UNIVERSE_MAX_TICKERS, gt=0
    )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> DataSourceConfig:
        env = environ or os.environ
        database_dsn, database_dsn_env = resolve_database_dsn_from_env(env)
        return cls(
            database_dsn=database_dsn,
            database_dsn_env=database_dsn_env,
            default_ticker=env.get(AI_DEFAULT_TICKER_ENV, DEFAULT_BACKTEST_TICKER),
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
            # Clamped rather than rejected: an out-of-range value in a deployment env
            # must not take the whole service down, and the manifest records the years
            # actually used either way.
            backtest_lookback_years=min(
                MAX_BACKTEST_LOOKBACK_YEARS,
                max(
                    MIN_BACKTEST_LOOKBACK_YEARS,
                    _int_env(
                        env, AI_BACKTEST_LOOKBACK_YEARS_ENV, DEFAULT_BACKTEST_LOOKBACK_YEARS
                    ),
                ),
            ),
            backtest_universe_max_tickers=_int_env(
                env,
                AI_BACKTEST_UNIVERSE_MAX_TICKERS_ENV,
                DEFAULT_BACKTEST_UNIVERSE_MAX_TICKERS,
            ),
        )


RELEASE_PROFILE_ENV = "APP_ENV"
RELEASE_PROFILE_VALUES = frozenset({"production", "prod"})


def is_release_profile() -> bool:
    """Whether this process is running as a release deployment.

    One definition, because "is this production?" is asked from both the API layer and
    the data layer and the two must never disagree. A second copy of this literal set
    is how a fixture guard ends up silently disabled on the host it exists to protect.
    """

    return (os.environ.get(RELEASE_PROFILE_ENV) or "").strip().lower() in RELEASE_PROFILE_VALUES


def backtest_window_policy_id(lookback_years: int) -> str:
    """The versioned identifier of the window policy an extract was produced under.

    The window length is configuration now, so it has to be part of the identifier: a
    manifest that says only "settled session" cannot tell a one-year extract from a
    five-year one, and two runs with different lookbacks would otherwise claim the same
    reproducibility contract.
    """

    return f"krx_pit_common_stock_{lookback_years}y_kst_settled_session_v3"


class PipelineDataUnavailableError(ValueError):
    """The warehouse is healthy but has nothing to run this strategy on.

    Subclasses ValueError because that is what these two conditions were raised as
    before, so anything already catching them keeps working - the point of the class is
    the `reason` code, not a new place in the hierarchy.

    Distinct from an infrastructure error on purpose. Both used to be raised as bare
    ValueErrors, so `classify_failure` sorted "no stock matches your condition today"
    into `unknown_failure` - a message that tells the user nothing and reads as a
    crash, which is what left runs looking like they had stalled until the client's
    wall-clock timeout gave up on them. Carrying the reason as a code lets the job
    layer turn it into an answer ("조건에 맞는 종목이 없습니다") instead.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class FixtureModeForbiddenError(PipelineDataUnavailableError):
    """A release profile asked for the local fixture bundle. FT-FIX-08 forbids it.

    Fixtures existed as a convenience for running without a warehouse, and the release
    profile inherited that convenience by accident: with no DSN configured, production
    fell through to fixture rows and produced a complete analysis - status `ready`, a
    report, metrics - labelled `production_eligible: false` and nothing more. A label is
    not a gate. This is the gate.

    It subclasses `PipelineDataUnavailableError` so the job layer classifies it as an
    answerable failure with a reason code rather than an unknown crash.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            "fixture_mode_forbidden_in_release",
            "운영 환경에서는 로컬 fixture 데이터로 분석할 수 없습니다. "
            f"데이터 소스를 설정한 뒤 다시 시도해 주세요. ({detail})",
        )


class PipelineDataBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_rows: list[dict[str, Any]] = Field(default_factory=list)
    screening_candidates: list[dict[str, Any]] = Field(default_factory=list)
    l4_evidence: list[dict[str, Any]] = Field(default_factory=list)
    # Carries the measured values plus the label saying what the equity leg was
    # measured against, so a report can never call a universe proxy "the KOSPI".
    macro_snapshot: dict[str, Any] | None = None
    # This high-cardinality series must not be folded into metadata because metadata is
    # republished in public provenance. Backtest code receives it as a separate input.
    official_benchmark: dict[str, Any] | None = None
    data_availability: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def research_runtime_facts_from_bundle(
    bundle: PipelineDataBundle,
    *,
    dsn_configured: bool,
    trace_id: str,
    retrieved_at: datetime | None = None,
) -> ResearchRuntimeFacts:
    """Derive secret-free eligibility facts from a loader-produced bundle.

    This is deliberately an adapter measurement, not a caller-controlled public
    assertion: the only PostgreSQL path that calls it is ``PostgresPipelineDataSource``.
    Contract fixtures may exercise it locally, but cannot constitute server evidence.
    """

    metadata = bundle.metadata
    source = metadata.get("source")
    as_of = metadata.get("research_as_of")
    session_state = metadata.get("research_session_state")
    freshness = metadata.get("research_freshness")
    required = frozenset(metadata.get("research_required_families", ()))
    available = frozenset(metadata.get("research_available_families", ()))
    snapshot_id = metadata.get("research_snapshot_id")
    return ResearchRuntimeFacts(
        dsn_configured=dsn_configured,
        source=source if isinstance(source, str) else None,
        # A source label alone is never enough: this flag only becomes true after the
        # live adapter measured all session/family/count fields below.
        production_eligible=bool(metadata.get("research_measurement_complete")),
        as_of=as_of if isinstance(as_of, str) else None,
        retrieved_at=retrieved_at or datetime.now(UTC),
        session_state=session_state if isinstance(session_state, str) else None,
        freshness=freshness if isinstance(freshness, str) else None,
        required_families=required,
        available_families=available,
        row_count=len(bundle.price_rows),
        universe_count=_safe_int(metadata.get("pit_member_count")),
        candidate_count=len(bundle.screening_candidates),
        candidate_items_count=len(bundle.screening_candidates),
        snapshot_or_result_id=snapshot_id if isinstance(snapshot_id, str) else trace_id,
    )


def classify_research_runtime_failure(*, dsn_configured: bool) -> ResearchRuntimeFacts:
    """Classify a configured adapter failure without exposing DSN/SQL/error text."""

    return ResearchRuntimeFacts(
        dsn_configured=dsn_configured,
        load_state="database_error",
        source=None,
        production_eligible=False,
    )


def _safe_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class PostgresPipelineDataSource:
    def __init__(self, config: DataSourceConfig) -> None:
        if not config.database_dsn:
            raise ValueError(f"{AI_DATABASE_DSN_ENV} is required for PostgreSQL data source")
        self.config = config
        # Indicator families the warehouse could not serve within the statement budget
        # for this load, so the report can say so instead of silently not matching.
        self.unavailable_indicator_families: tuple[str, ...] = ()

    def load(
        self,
        query: str,
        trace_id: str,
        *,
        screen_current: bool = True,
        required_metrics: Sequence[str] | None = None,
        requires_financials: bool | None = None,
        compact_price_rows: bool = False,
    ) -> PipelineDataBundle:
        load_started = perf_counter()
        timings: dict[str, float] = {}
        with self._connect() as conn:
            self._set_statement_timeout(conn)
            # Ask what the warehouse can actually serve before spending anything on the
            # query. This used to run last, after screening, so a strategy whose data is
            # not loaded at all still paid for the full screen plus three LLM relaxation
            # rounds - each widening a threshold against columns that were NULL for every
            # row and could never match - and then failed with a generic message. With
            # mart.dart_financial_asof empty, every fundamental strategy took that path
            # and surfaced as "데이터 조회 시간이 초과되었습니다", which named neither the
            # missing data nor the fact that waiting longer could not help.
            capability_availability = measure_capabilities(conn)
            unsupported = unsupported_capabilities(query, capability_availability)
            if unsupported:
                return PipelineDataBundle(
                    data_availability=_data_availability_for_query(
                        query, source="postgres", available=capability_availability
                    ),
                    metadata={
                        "source": "postgres",
                        "dsn_env": self.config.database_dsn_env,
                        "stopped_before_screening": True,
                        "unsupported_capabilities": unsupported,
                        "capability_probe": capability_availability,
                    },
                )
            backtest_window = self._resolve_backtest_window(conn)
            if backtest_window is None:
                raise PipelineDataUnavailableError(
                    "pit_calendar_unavailable",
                    "KRX trading-calendar sessions are unavailable for the fixed five-year backtest window",
                )
            # V3 supplies the exact metrics from its sealed AST.  Falling back to the
            # legacy query heuristic would pull every TA family even when the executed
            # rule only needs price-derived relative strength.  Keep the legacy path
            # unchanged for unsealed callers.
            indicator_families = (
                indicator_families_for_metrics(required_metrics, include_default=False)
                if required_metrics is not None
                else indicator_families_for_query(query)
            )
            # Relative-strength-only V3 candidates derive their features from OHLCV.
            # They do not need raw-capacity fields, display fields, or any TA/DART
            # payload on every historical bar. Legacy callers remain unchanged.
            compact_execution_rows = bool(
                compact_price_rows
                and not indicator_families
                and requires_financials is False
            )
            screening_candidates = []
            screening_relaxation: dict[str, Any] = {}
            universe_descriptor: dict[str, Any] = {
                "selection": "single_ticker",
                "source": KIS_ADJUSTED_OHLCV_TABLE,
            }
            recommended: list[str] = []
            ticker_resolution = "screening"
            already_screened = screen_current and _query_requests_screening(query)
            screening_mode = not screen_current or already_screened
            pit_market: tuple[
                list[str],
                dict[str, Any],
                Mapping[str, Mapping[str, Any]],
                list[dict[str, Any]],
                int,
            ] | None = None
            parallel_screening_backtest = False
            if already_screened:
                # Today's screen affects presentation only; it does not affect the
                # historical PIT universe or price load.  Run the independent reads
                # concurrently on separate connections to avoid serial timeout debt.
                parallel_screening_backtest = True
                with ThreadPoolExecutor(max_workers=1) as executor:
                    screening = executor.submit(self._screen_on_its_own_connection, query)
                    pit_market = self._load_pit_market(
                        conn,
                        backtest_window,
                        query,
                        indicator_families,
                        requires_financials,
                        timings,
                        compact_price_rows=compact_execution_rows,
                    )
                    (
                        screening_candidates,
                        screening_relaxation,
                        screening_timings,
                    ) = screening.result()
                timings.update(screening_timings)
            single_ticker: str | None = None
            if not screening_candidates and screen_current:
                single_ticker = self._resolve_ticker(conn, query)
                if single_ticker is None:
                    screening_mode = True
                    # Ambiguous query (no explicit ticker, no name match): screen as a
                    # broad condition search instead of silently trading a single
                    # hardcoded default ticker.
                    #
                    # Only if we have not already done exactly that. The baseline screen
                    # scans every ticker in feature.kis_adjusted_ohlcv_daily and runs on
                    # the widened backtest budget; running it a second time with the same
                    # query and the same thresholds cannot produce a different answer, and
                    # for a screen that legitimately matched nothing today it doubled the
                    # cost of the request and pushed it into a statement timeout.
                    if not already_screened:
                        # The current-day screen and the PIT market load are independent
                        # reads; serialising them cost ~9 s per request. Screen on a
                        # second connection while this one loads the backtest market.
                        parallel_screening_backtest = True
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            screening = executor.submit(
                                self._screen_on_its_own_connection, query
                            )
                            pit_market = self._load_pit_market(
                                conn,
                                backtest_window,
                                query,
                                indicator_families,
                                requires_financials,
                                timings,
                                compact_price_rows=compact_execution_rows,
                            )
                            (
                                screening_candidates,
                                screening_relaxation,
                                screening_timings,
                            ) = screening.result()
                        timings.update(screening_timings)
                    ticker_resolution = (
                        "ambiguous_fallback_to_screening"
                        if screening_candidates
                        else "ambiguous_backtest_without_current_recommendations"
                    )
                else:
                    ticker_resolution = "explicit_or_name_match"
            if screening_mode:
                if pit_market is None:
                    pit_market = self._load_pit_market(
                        conn,
                        backtest_window,
                        query,
                        indicator_families,
                        requires_financials,
                        timings,
                        compact_price_rows=compact_execution_rows,
                    )
                (
                    tickers,
                    universe_descriptor,
                    symbol_info_by_ticker,
                    price_rows,
                    effective_lookback_days,
                ) = pit_market
                # Current candidates are recommendation context only.  Filter them
                # against the historical universe, but always trade the PIT member.
                # This prevents a present-day screen from entering historical results.
                candidates = _backtest_ticker_pool(
                    screening_candidates, self.config.backtest_max_tickers
                )
                pit_set = set(tickers)
                excluded_screening_candidate_count = sum(
                    1 for item in candidates if item not in pit_set
                )
                recommended = [item for item in candidates if item in pit_set]
                ticker = tickers[0]
                universe_descriptor["excluded_screening_candidate_count"] = (
                    excluded_screening_candidate_count
                )
                symbol_info = symbol_info_by_ticker.get(ticker, {"ticker": ticker, "included": False})
            elif single_ticker:
                ticker = single_ticker
                tickers = [ticker]
                symbol_info = self._fetch_symbol_info(conn, ticker)
                price_rows_started = perf_counter()
                fetch_kwargs: dict[str, Any] = {"timings": timings}
                if requires_financials is not None:
                    fetch_kwargs["requires_financials"] = requires_financials
                if compact_execution_rows:
                    fetch_kwargs["compact_price_rows"] = True
                price_rows, effective_lookback_days = self._fetch_price_rows(
                    conn,
                    tickers,
                    {ticker: symbol_info},
                    query,
                    backtest_window,
                    indicator_families,
                    **fetch_kwargs,
                )
                timings["price_rows_seconds"] = perf_counter() - price_rows_started
            else:
                # No DB screening match and no explicit/name-resolved ticker: refuse to
                # silently substitute config.default_ticker, since that produces a
                # report that looks real but always trades the same hardcoded stock.
                raise PipelineDataUnavailableError(
                    "no_screening_matches",
                    "no screening candidates or resolvable ticker found in the database "
                    f"for this query after {screening_relaxation.get('relaxation_rounds', 0)} "
                    "relaxation round(s); refusing to fall back to a hardcoded default ticker",
                )
            if not price_rows:
                raise PipelineDataUnavailableError(
                    "no_price_rows",
                    f"{KIS_ADJUSTED_OHLCV_TABLE} returned no price rows for {ticker}",
                )
            raw_price_capabilities = _raw_price_capabilities(price_rows)
            pit_members_without_price_rows = sorted(
                set(tickers) - {str(row.get("ticker") or "").zfill(6) for row in price_rows}
            )
            recommendation_ticker = recommended[0] if recommended else None
            l4_evidence_ticker = recommendation_ticker or ticker
            l4_evidence = self._fetch_l4_evidence(conn, l4_evidence_ticker, trace_id)
            macro_status = self._fetch_macro_status(conn)
            macro_snapshot = self._fetch_macro_snapshot(conn, price_rows)
            official_benchmark = self._fetch_official_benchmark(conn, backtest_window)
            # Capabilities were probed up front; nothing since then can change them.

        research_as_of = backtest_window["end"].isoformat()
        window_policy_id = backtest_window_policy_id(self.config.backtest_lookback_years)
        required_families = {"price_ta", "pit_universe", *indicator_families}
        available_families = set(required_families)
        if self.unavailable_indicator_families:
            available_families.difference_update(self.unavailable_indicator_families)
        price_dates = {
            str(row.get("date") or row.get("time") or row.get("as_of_date") or "")
            for row in price_rows
        }
        current_snapshot_price_rows = [
            {
                "ticker": str(row.get("ticker") or "").zfill(6),
                "date": str(row.get("date") or row.get("time") or row.get("as_of_date") or ""),
            }
            for row in price_rows
            if str(row.get("date") or row.get("time") or row.get("as_of_date") or "")
            == research_as_of
        ]
        current_snapshot_tickers = sorted(
            {
                str(row["ticker"]).zfill(6)
                for row in current_snapshot_price_rows
                if str(row["ticker"]).strip()
            }
        )
        # The end session comes from core.trading_calendar inside this same connection;
        # data is current only when the returned price rows actually cover that session.
        price_covers_session = research_as_of in price_dates
        research_measurement_complete = bool(
            price_covers_session
            and tickers
            and required_families.issubset(available_families)
        )
        source_freshness = "eod_current" if price_covers_session else "stale"
        data_availability = _data_availability_for_query(
            query, source="postgres", available=capability_availability
        )
        extract_hash = compute_pipeline_extract_hash(
            price_rows=price_rows,
            screening_candidates=screening_candidates,
            l4_evidence=l4_evidence,
            macro_snapshot=macro_snapshot,
            data_availability=data_availability,
            # Historical PIT members include delisted names by design.  Currentness
            # only asks which rows must exist on the declared latest session.
            required_tickers=current_snapshot_tickers,
        )
        source_manifest = build_source_manifest(
            source="postgres",
            as_of=research_as_of,
            freshness=source_freshness,
            lineage_refs=[
                KIS_ADJUSTED_OHLCV_TABLE,
                PIT_UNIVERSE_VIEW,
                SYMBOL_LISTING_HISTORY_TABLE,
                *[INDICATOR_TABLES[family] for family in indicator_families],
                *(
                    [OFFICIAL_BENCHMARK_TR_VIEW, OFFICIAL_BENCHMARK_WEIGHT_VIEW]
                    if official_benchmark["available"]
                    else []
                ),
            ],
            source_version=window_policy_id,
            extract_hash=extract_hash,
        )
        immutable_snapshot_bundle = build_snapshot_bundle(
            as_of=research_as_of,
            source="postgres",
            pit_universe={
                "members": sorted(tickers),
                "descriptor": universe_descriptor,
                "member_count": len(tickers),
            },
            delisting={
                "policy_version": "official-event-then-final-close-v1",
                "provenance": SYMBOL_LISTING_HISTORY_TABLE,
                "members_without_price_rows": pit_members_without_price_rows,
            },
            indicator_input={
                "families": list(indicator_families),
                "sources": [INDICATOR_TABLES[family] for family in indicator_families],
                "lookback_days": effective_lookback_days,
                "query": query,
            },
            lineage_refs=source_manifest.lineage_refs,
        )

        return PipelineDataBundle(
            price_rows=price_rows,
            screening_candidates=screening_candidates,
            l4_evidence=l4_evidence,
            macro_snapshot=macro_snapshot,
            official_benchmark=official_benchmark,
            data_availability=data_availability,
            metadata={
                "source": "postgres",
                "source_manifest": source_manifest.model_dump(mode="json"),
                "immutable_snapshot_bundle": immutable_snapshot_bundle.model_dump(mode="json"),
                "source_snapshot_as_of": research_as_of,
                "source_snapshot_freshness": source_freshness,
                "source_snapshot_version": window_policy_id,
                "loaded_extract_hash": source_manifest.extract_hash,
                "dsn_env": self.config.database_dsn_env,
                "ticker": ticker,
                "tickers": tickers,
                "current_snapshot_tickers": current_snapshot_tickers,
                "current_snapshot_price_rows": current_snapshot_price_rows,
                "recommended_tickers": recommended,
                "recommendation_ticker": recommended[0] if recommended else None,
                "backtest_universe": universe_descriptor,
                "parallel_screening_backtest": parallel_screening_backtest,
                "current_screening": "enabled" if screen_current else "skipped_for_sealed_exploration",
                "ticker_resolution": ticker_resolution,
                "price_source": KIS_ADJUSTED_OHLCV_TABLE,
                "indicator_sources": [
                    INDICATOR_TABLES[family] for family in indicator_families
                ],
                "indicator_families": list(indicator_families),
                "data_load_plan": {
                    "required_metrics": sorted(required_metrics or ()),
                    "requires_financials": requires_financials,
                    "compact_price_rows": compact_execution_rows,
                    "execution_price_basis": (
                        "official_adjusted_ohlcv" if compact_execution_rows else "raw_ohlcv"
                    ),
                },
                "unavailable_indicator_families": list(
                    self.unavailable_indicator_families
                ),
                "price_rows": len(price_rows),
                "pit_member_count": len(tickers),
                "pit_members_without_price_rows": pit_members_without_price_rows,
                "pit_members_without_price_row_count": len(pit_members_without_price_rows),
                "screening_candidates": len(screening_candidates),
                "screening_relaxation": screening_relaxation,
                "backtest_lookback_days": effective_lookback_days,
                "backtest_window_policy_id": window_policy_id,
                "backtest_start_session": backtest_window["start"].isoformat(),
                "backtest_end_session": backtest_window["end"].isoformat(),
                "backtest_session_count": backtest_window["session_count"],
                "universe_provenance": SYMBOL_LISTING_HISTORY_TABLE,
                "raw_price_provenance": {
                    "raw_ohlcv_source": None if compact_execution_rows else "core.ohlcv_daily",
                    "raw_notional_source": None,
                    # Bars without a raw execution price are not loaded at all, so the
                    # returned rows are exactly the ones the engine can execute on.
                    "raw_execution_join": None if compact_execution_rows else "inner_required",
                    "adjusted_signal_source": KIS_ADJUSTED_OHLCV_TABLE,
                    "execution_price_source": (
                        KIS_ADJUSTED_OHLCV_TABLE
                        if compact_execution_rows
                        else "core.ohlcv_daily"
                    ),
                    "execution_price_basis": (
                        "official_adjusted_ohlcv" if compact_execution_rows else "raw_ohlcv"
                    ),
                },
                "raw_price_capabilities": raw_price_capabilities,
                "dart_date_only_effective_policy": "next_krx_session_v1",
                "l4_evidence_source": ANALYST_REPORT_TABLE,
                "l4_evidence_ticker": l4_evidence_ticker,
                "l4_evidence_rows": len(l4_evidence),
                "official_benchmark": _official_benchmark_status(official_benchmark),
                "universe_source": universe_descriptor["source"],
                "symbol": symbol_info,
                "macro_source": BOK_MACRO_VIEW,
                "macro_status": macro_status,
                # Eligibility measurement is intentionally separate from the public
                # source label. It is safe to expose but cannot reveal DSNs, SQL, rows,
                # candidates, or exception details.
                "research_as_of": research_as_of,
                "research_session_state": "krx_completed_session",
                "research_freshness": source_freshness,
                "research_required_families": sorted(required_families),
                "research_available_families": sorted(available_families),
                # Eligibility provenance must identify the immutable extract, not the
                # request correlation id.  A trace id is useful for diagnostics but
                # can be reused or regenerated without changing the data; the source
                # manifest snapshot binds this decision to the concrete PostgreSQL
                # EOD/PIT payload that was loaded.
                "research_snapshot_id": source_manifest.snapshot_id,
                "research_measurement_complete": research_measurement_complete,
                "timings": {
                    **{name: round(seconds, 6) for name, seconds in timings.items()},
                    "total_seconds": round(perf_counter() - load_started, 6),
                },
            },
        )

    def _screen_on_its_own_connection(
        self, query: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, float]]:
        """Run the independent current screen without sharing the PIT load connection."""

        connect_started = perf_counter()
        with self._connect() as conn:
            connect_seconds = perf_counter() - connect_started
            self._set_statement_timeout(conn)
            screening_started = perf_counter()
            candidates, relaxation = self._screen_with_relaxation(conn, query)
        return candidates, relaxation, {
            "screening_connect_seconds": connect_seconds,
            "screening_seconds": perf_counter() - screening_started,
        }

    def _load_pit_market(
        self,
        conn: Any,
        window: Mapping[str, Any],
        query: str,
        indicator_families: Sequence[str],
        requires_financials: bool | None,
        timings: dict[str, float],
        *,
        compact_price_rows: bool = False,
    ) -> tuple[
        list[str],
        dict[str, Any],
        Mapping[str, Mapping[str, Any]],
        list[dict[str, Any]],
        int,
    ]:
        """Load the fixed historical universe and price rows independently of screening."""

        started = perf_counter()
        tickers, universe_descriptor = self._fetch_backtest_universe(conn, window)
        timings["universe_seconds"] = perf_counter() - started
        if not tickers:
            raise PipelineDataUnavailableError(
                "pit_universe_empty",
                "PIT KOSPI/KOSDAQ common-stock membership has no coverage in the fixed window",
            )
        started = perf_counter()
        symbol_info_by_ticker = self._fetch_symbol_info_map(conn, tickers)
        timings["symbol_info_seconds"] = perf_counter() - started
        self._set_statement_timeout(conn, self.config.backtest_statement_timeout_ms)
        started = perf_counter()
        try:
            fetch_kwargs: dict[str, Any] = {"timings": timings}
            if requires_financials is not None:
                fetch_kwargs["requires_financials"] = requires_financials
            if compact_price_rows:
                fetch_kwargs["compact_price_rows"] = True
            price_rows, effective_lookback_days = self._fetch_price_rows(
                conn,
                tickers,
                symbol_info_by_ticker,
                query,
                window,
                indicator_families,
                **fetch_kwargs,
            )
        finally:
            self._set_statement_timeout(conn)
        timings["price_rows_seconds"] = perf_counter() - started
        return (
            tickers,
            universe_descriptor,
            symbol_info_by_ticker,
            price_rows,
            effective_lookback_days,
        )

    def _fetch_backtest_universe(
        self, conn: Any, window: Mapping[str, Any]
    ) -> tuple[list[str], dict[str, Any]]:
        """The lifecycle PIT common-stock universe for the window, capped by liquidity.

        Every member of the window stays a candidate, including names that were delisted
        later on - dropping those is exactly the survivorship bias this universe exists to
        avoid, and the price join is by date so a name delisted mid-window keeps its rows
        up to its last session (delisting policy: official-event-then-final-close-v1).

        What is capped is how many of them are loaded. The rank is average traded value
        (adj_close * adj_volume) over the `UNIVERSE_RANKING_SESSIONS` sessions *ending at
        the window start*, so the selection uses only information that existed before the
        first bar the strategy trades - ranking inside the window would let the outcome
        pick its own universe. Ranking and capping happen in the database; returning all
        1,717 members to sort them in Python would defeat the point.

        ponytail: a name first listed after the window start has no pre-window traded
        value and sorts last (NULLS LAST), so it is only included when the cap is not
        already full. Rank on a forward-rolling window if mid-window IPOs need to compete.
        """

        rows = conn.execute(
            f"""
            WITH window_members AS (
                -- Point-in-time lifecycle membership straight from the history tables:
                -- any KOSPI/KOSDAQ common-stock listing interval that overlaps the window,
                -- so a name delisted *during* the window is a member (survivorship-safe)
                -- while a listing that ended before the window is not.  The mart PIT
                -- view is not used here: its security-type history only starts on
                -- 2026-08-11, so for earlier dates it returns nobody and a "PIT universe"
                -- silently collapses into today's listed names.
                SELECT DISTINCT sm.symbol
                FROM {SYMBOL_LISTING_HISTORY_TABLE} h
                JOIN {SYMBOL_MASTER_TABLE} sm ON sm.symbol_id = h.symbol_id
                JOIN core.symbol_security_type_history sh
                  ON sh.symbol_id = h.symbol_id
                 AND sh.valid_from <= %(window_end)s::date
                 AND (sh.valid_to IS NULL OR sh.valid_to >= %(window_start)s::date)
                WHERE h.listing_status = 'listed'
                  AND h.market IN ('KOSPI', 'KOSDAQ')
                  AND sh.security_type = '보통주'
                  AND h.valid_from <= %(window_end)s::date
                  AND (h.valid_to IS NULL OR h.valid_to >= %(window_start)s::date)
            ), ranking_sessions AS (
                SELECT trade_date
                FROM core.trading_calendar
                WHERE is_open AND trade_date <= %(window_start)s::date
                ORDER BY trade_date DESC
                LIMIT %(ranking_sessions)s
            ), ranking_window AS (
                SELECT min(trade_date) AS floor_date, max(trade_date) AS ceil_date
                FROM ranking_sessions
            ), live_members AS (
                SELECT symbol FROM window_members
            ), ranked AS (
                SELECT l.symbol, avg(p.adj_close * p.adj_volume) AS traded_value
                FROM live_members l
                CROSS JOIN ranking_window w
                LEFT JOIN {KIS_ADJUSTED_OHLCV_TABLE} p
                  ON p.ticker = l.symbol
                 AND p.time BETWEEN w.floor_date AND w.ceil_date
                GROUP BY l.symbol
            )
            SELECT symbol,
                   (SELECT count(*) FROM window_members) AS window_member_count
            FROM ranked
            ORDER BY traded_value DESC NULLS LAST, symbol
            LIMIT %(cap)s
            """,
            {
                "window_start": window["start"],
                "window_end": window["end"],
                "ranking_sessions": UNIVERSE_RANKING_SESSIONS,
                "cap": self.config.backtest_universe_max_tickers,
            },
        ).fetchall()
        universe = sorted(str(row["symbol"]).zfill(6) for row in rows)
        window_member_count = max(
            (int(row.get("window_member_count") or 0) for row in rows),
            default=len(universe),
        )
        return universe, {
            "selection": "lifecycle_pit_common_stock_window_top_traded",
            "as_of_start": window["start"].isoformat(),
            "as_of_end": window["end"].isoformat(),
            "session_count": window["session_count"],
            "member_count": len(universe),
            "window_member_count": window_member_count,
            "excluded_member_count": max(window_member_count - len(universe), 0),
            "ranking_metric": "avg_traded_value_adj_close_x_adj_volume",
            "ranking_sessions": UNIVERSE_RANKING_SESSIONS,
            "ranking_window_end": window["start"].isoformat(),
            "max_tickers": self.config.backtest_universe_max_tickers,
            "source": SYMBOL_LISTING_HISTORY_TABLE,
            "listing_provenance": SYMBOL_LISTING_HISTORY_TABLE,
            "delisting_policy": "official-event-then-final-close-v1",
            "delisted_during_window": "kept_until_final_session",
            "security_type": "보통주",
        }

    def _screen_via_llm(
        self, conn: Any, query: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
        """Use LLM screening when available, otherwise fall back to deterministic SQL."""
        try:
            from ai_graph.data_sources.llm_screen import screen_with_llm

            result = screen_with_llm(conn, query)
        except Exception:
            _logger.exception("LLM screening failed; falling back to profile screening")
            result = None
        if not result or not result.get("rows"):
            # A PostgreSQL statement failure aborts the whole transaction. The LLM
            # screen normally rolls back failed attempts itself, but this boundary
            # also catches failures outside that inner try/except.
            self._rollback_quietly(conn)
        # statement_timeout is transaction-local, so a rollback above (or inside the
        # LLM retry loop) discards it. Restore it before any profile/fetch query.
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

        profile = _screening_profile(query)
        # Known strategies already have bounded, audited SQL and do not benefit from
        # spending two optional AOAI calls on web research plus schema-to-SQL
        # generation. In production those calls each exhausted three response-start
        # attempts before falling back here, adding 87 seconds without changing the
        # result. Keep LLM-authored SQL for strategies outside the supported profiles.
        if profile == "technical_proxy":
            llm_result = self._screen_via_llm(conn, query)
            if llm_result is not None:
                return llm_result

        known_sectors = get_known_sectors(conn=conn)
        # The sector helper deliberately converts an unavailable optional view into a
        # static taxonomy fallback. PostgreSQL still leaves the shared transaction in
        # INERROR, and that detail is hidden by the fallback, so reset unconditionally
        # before the baseline query.
        self._rollback_quietly(conn)
        sector = extract_sector_from_query(query, known_sectors)
        # Fetched once and re-filtered in-process for every relaxation round, so a wider
        # screen costs nothing at the database.
        self._set_statement_timeout(conn, self.config.backtest_statement_timeout_ms)
        rows, frame_trace = self._load_screening_frame(conn, sector=sector, profile=profile)
        self._set_statement_timeout(conn)

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
                return candidates, _relaxation_trace(
                    profile, rounds, len(rows), frame=frame_trace
                )
            if round_index == MAX_SCREENING_RELAXATION_ROUNDS:
                break
            thresholds = _propose_relaxed_thresholds(
                query=query,
                profile=profile,
                thresholds=thresholds,
                round_index=round_index,
                universe_rows=len(rows),
            )
        return [], _relaxation_trace(profile, rounds, len(rows), frame=frame_trace)

    def _load_screening_frame(
        self, conn: Any, *, sector: str | None, profile: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """One screening date's rows: warehouse indicators plus the few path features.

        Four small statements instead of one large one, because the anchor date has to
        reach each of them as a bind parameter rather than as a subquery, which is not a
        plan-time constant and so blocks partition pruning.

        That alone was not enough to stop the "out of shared memory /
        max_locks_per_transaction" failures, because the frame read went through
        KIS_FEATURE_FRAME_VIEW, where the date can only ever restrict the price side of
        five outer joins. Bind parameter or literal made no difference there - measured
        10,718 lock entries either way. See _feature_frame_sql, which reads the same
        tables with a date restriction on each one.

        Moving averages, Bollinger bands and RSI are no longer recomputed here. The
        warehouse already stores them per ticker per date, and recomputing meant the
        screen and the backtest each had their own definition of the same indicator.
        """

        as_of = self._resolve_screening_date(conn)
        if as_of is None:
            return [], {"as_of_date": None, "reason": "no recent rows in the price table"}

        frame_rows = conn.execute(
            _mart_frame_sql(sector=bool(sector)),
            {"as_of": as_of, "sector": sector},
        ).fetchall()

        needs = (
            _ALL_PATH_NEEDS
            if profile == SCREENING_BASELINE_PROFILE
            else _PROFILE_PATH_NEEDS.get(profile, _ALL_PATH_NEEDS)
        )
        # Relative strength is measured against the whole priced universe, so the path
        # read is never sector-scoped even when the frame is.
        needs = needs | {PATH_RETURNS}
        path_sql, lookback_days = _path_features_sql(needs)
        path_rows = conn.execute(path_sql, {"as_of": as_of}).fetchall()

        prev_date = self._resolve_previous_trading_date(conn, as_of)
        prev_rsi_by_ticker: dict[str, Any] = {}
        if prev_date is not None:
            prev_rsi_by_ticker = {
                str(row["ticker"]).zfill(6): row.get("prev_rsi")
                for row in conn.execute(_prev_rsi_sql(), {"prev": prev_date}).fetchall()
            }

        financials_by_symbol = {
            str(row["symbol"]).zfill(6): row
            for row in conn.execute(_financial_sql(), {"as_of": as_of}).fetchall()
        }

        strength, benchmark = _relative_strength(path_rows)
        path_by_ticker = {str(row["ticker"]).zfill(6): row for row in path_rows}

        rows: list[dict[str, Any]] = []
        for frame_row in frame_rows:
            ticker = str(frame_row.get("ticker") or "").zfill(6)
            row = dict(frame_row)
            row["ticker"] = ticker
            path = path_by_ticker.get(ticker) or {}
            row["high_252"] = path.get("high_252")
            avg_volume_20 = _optional_float_value(path.get("avg_volume_20"))
            volume = _optional_float_value(frame_row.get("volume"))
            row["volume_ratio_20"] = (
                volume / avg_volume_20
                if volume is not None and avg_volume_20 and avg_volume_20 > 0
                else None
            )
            excess = strength.get(ticker) or {}
            row["relative_strength_20d"] = excess.get("20d")
            row["relative_strength_60d"] = excess.get("60d")
            row["prev_rsi"] = prev_rsi_by_ticker.get(ticker)
            financial = financials_by_symbol.get(ticker)
            if financial is not None:
                row["financial_period_end"] = financial.get("financial_period_end")
                for field in (
                    "roe",
                    "debt_to_equity",
                    "operating_margin",
                    "revenue_growth_yoy",
                ):
                    row[field] = financial.get(field)
                eps = _optional_float_value(financial.get("eps"))
                close = _optional_float_value(frame_row.get("close"))
                row["per"] = close / eps if eps and eps > 0 and close is not None else None
            rows.append(row)

        trace = {
            "as_of_date": as_of.isoformat(),
            "previous_trading_date": prev_date.isoformat() if prev_date else None,
            # The frame's own tables, not KIS_FEATURE_FRAME_VIEW - the view cannot be
            # read for a single date without locking every chunk behind it. Same rows,
            # same columns; see _feature_frame_sql.
            "indicator_source": ADJUSTED_OHLCV_TABLE,
            "indicators_read": list(INDICATOR_FIELDS),
            "path_features_computed": sorted(needs),
            "path_lookback_days": lookback_days,
            "frame_rows": len(frame_rows),
            "relative_strength_benchmark": benchmark,
        }
        return rows, trace

    def _resolve_screening_date(self, conn: Any, ) -> date | None:
        """The latest trading date, read from the price table rather than the mart view.

        Bounded to 90 days because an unbounded max() over a 534-chunk hypertable locks
        every chunk and exhausts max_locks_per_transaction. Anchoring on the base table
        also keeps this cheap (~80ms) - the same max() over the feature-frame view costs
        ~25s because the view's own predicates block pruning.

        The bound is computed here and bound as a parameter rather than written as
        `CURRENT_DATE - INTERVAL '90 days'`. CURRENT_DATE is STABLE, not a plan-time
        constant, so chunks are excluded only at execution: the scan reads the same 28
        chunks either way, but the planner has already locked all 534. Measured, that is
        2,142 lock entries against 62 - a third of the cluster's whole lock table spent
        before the screen has read a row.
        """

        ceiling = _kst_today()
        floor = ceiling - timedelta(days=SCREENING_DATE_LOOKBACK_DAYS)
        row = conn.execute(
            f"""
            SELECT max(time) AS as_of_date
            FROM {KIS_ADJUSTED_OHLCV_TABLE}
            WHERE time >= %(floor)s::date
              AND time < %(ceiling)s::date
            """,
            {"floor": floor, "ceiling": ceiling},
        ).fetchone()
        value = row.get("as_of_date") if row else None
        return _date_value(value) if value is not None else None

    def _resolve_previous_trading_date(self, conn: Any, as_of: date) -> date | None:
        row = conn.execute(
            f"""
            SELECT max(time) AS previous_date
            FROM {KIS_ADJUSTED_OHLCV_TABLE}
            WHERE time < %(as_of)s::date
              AND time >= %(as_of)s::date - 10
            """,
            {"as_of": as_of},
        ).fetchone()
        value = row.get("previous_date") if row else None
        return _date_value(value) if value is not None else None

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

    @staticmethod
    def _rollback_quietly(conn: Any) -> None:
        try:
            conn.rollback()
        except Exception:
            # Test doubles and already-closed connections may not support rollback.
            # The following timeout query will still surface an unusable real
            # connection instead of hiding the failure.
            _logger.debug("could not reset screening transaction", exc_info=True)

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
        window: Mapping[str, Any],
        indicator_families: Sequence[str] | None = None,
        *,
        requires_financials: bool | None = None,
        compact_price_rows: bool = False,
        timings: dict[str, float] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        del query
        timings = {} if timings is None else timings
        ticker_list = list(tickers)
        if compact_price_rows and hasattr(conn, "cursor"):
            # psycopg's dict-row factory would first materialise several million
            # dictionaries and then the adapter would build a second list of compact
            # rows. Stream tuple rows directly into the execution representation.
            # This retains the sealed price-only execution basis without materialising
            # a second set of database dictionaries before the feature engine sees it.
            compact_started = perf_counter()
            price_rows = self._fetch_compact_price_rows(conn, ticker_list, window)
            compact_elapsed = perf_counter() - compact_started
            self.unavailable_indicator_families = ()
            # The compact cursor streams the query and conversion together.  Keep that
            # fact explicit instead of reporting artificial zero-duration phases.
            timings["price_ohlcv_query_seconds"] = compact_elapsed
            timings["price_compact_stream_seconds"] = compact_elapsed
            timings["price_indicator_seconds"] = 0.0
            timings["price_financial_seconds"] = 0.0
            timings["price_row_conversion_seconds"] = compact_elapsed
            timings["price_financial_attach_seconds"] = 0.0
            return price_rows, int(window["session_count"])
        ohlcv_started = perf_counter()
        rows = conn.execute(
            f"""
            SELECT
                p.time AS as_of_date, p.ticker,
                p.adj_open AS open, p.adj_high AS high, p.adj_low AS low,
                p.adj_close AS close, p.adj_volume AS volume,
                p.adj_open AS adjusted_open, p.adj_high AS adjusted_high,
                p.adj_low AS adjusted_low, p.adj_close AS adjusted_close,
                p.adj_volume AS adjusted_volume,
                raw.open AS raw_open, raw.high AS raw_high, raw.low AS raw_low,
                raw.close AS raw_close, raw.volume AS raw_volume,
                NULL::numeric AS raw_notional
            FROM {KIS_ADJUSTED_OHLCV_TABLE} p
            JOIN core.symbol_master sm
              ON sm.symbol = p.ticker
            -- INNER, not LEFT: the execution engine refuses a bar without raw OHLCV
            -- ("raw_execution_unavailable"), so an adjusted-only bar can only be loaded,
            -- carried through the feature frame and then crash the backtest. Dropping it
            -- here is the same PIT decision made one layer earlier and for free.
            JOIN core.ohlcv_daily raw
              ON raw.symbol_id = sm.symbol_id AND raw.trade_date = p.time
             -- Keep the raw hypertable's time predicate explicit.  The equality to
             -- p.time alone prevents Timescale chunk pruning and made a five-year
             -- PIT request scan every raw OHLCV chunk before returning its first row.
             AND raw.trade_date BETWEEN %s::date AND %s::date
            WHERE p.ticker = ANY(%s)
              AND p.time BETWEEN %s::date AND %s::date
            -- PreparedFeatureStore operates date-by-date for cross-sectional rules.
            -- Returning the database rows in that same order avoids sorting the full
            -- PIT universe again in Python before each analysis.
            ORDER BY p.time, p.ticker
            """,
            [window["start"], window["end"], ticker_list, window["start"], window["end"]],
        ).fetchall()
        timings["price_ohlcv_query_seconds"] = perf_counter() - ohlcv_started
        earliest_priced_date = min((_date_value(row["as_of_date"]) for row in rows), default=None)
        # An empty tuple is an explicit sealed plan with no warehouse TA dependency
        # (for example relative strength derived from OHLCV).  Only ``None`` means the
        # legacy caller did not provide a plan and still needs all families.
        families = tuple(INDICATOR_TABLES) if indicator_families is None else indicator_families
        indicators_by_family: dict[str, dict[str, dict[date, Mapping[str, Any]]]] = {}
        unavailable_families: list[str] = []
        indicators_started = perf_counter()
        for family in families:
            try:
                indicators_by_family[family] = self._fetch_indicator_values_by_date(
                    conn, INDICATOR_TABLES[family], ticker_list, earliest_priced_date
                )
            except Exception:
                _logger.exception("indicator family %s could not be loaded", family)
                self._rollback_quietly(conn)
                self._set_statement_timeout(conn, self.config.backtest_statement_timeout_ms)
                unavailable_families.append(family)
        self.unavailable_indicator_families = tuple(unavailable_families)
        timings["price_indicator_seconds"] = perf_counter() - indicators_started
        financials_started = perf_counter()
        # Technical strategies do not need DART rows.  The legacy unspecified case
        # preserves the old behavior; a sealed V3 plan can make this dependency
        # explicit and avoid a full-universe filing scan before a price-only test.
        financials_by_ticker = (
            self._fetch_financial_timeline(conn, ticker_list)
            if requires_financials is not False
            else {}
        )
        timings["price_financial_seconds"] = perf_counter() - financials_started
        conversion_started = perf_counter()
        if compact_price_rows:
            # A non-streaming adapter (normally a test double) has already supplied
            # source raw OHLCV. Preserve it rather than changing its declared
            # execution basis; the real compact cursor below uses its separately
            # disclosed official-adjusted basis.
            price_rows = [_compact_price_row_from_source(row) for row in rows]
        else:
            price_rows = [
                _price_row_from_feature_frame_record(
                    _feature_frame_row_from_sources(
                        row,
                        {
                            family: by_ticker.get(str(row.get("ticker") or "").zfill(6), {})
                            for family, by_ticker in indicators_by_family.items()
                        },
                        symbol_info_by_ticker.get(str(row.get("ticker") or "").zfill(6), {}),
                    )
                )
                for row in rows
            ]
        timings["price_row_conversion_seconds"] = perf_counter() - conversion_started
        attach_started = perf_counter()
        if not compact_price_rows:
            _attach_pointintime_financials(price_rows, financials_by_ticker)
        timings["price_financial_attach_seconds"] = perf_counter() - attach_started
        return price_rows, int(window["session_count"])

    def _fetch_compact_price_rows(
        self,
        conn: Any,
        tickers: Sequence[str],
        window: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Stream the minimal accurate OHLCV payload for a sealed price-only plan."""

        from psycopg.rows import tuple_row

        price_rows: list[dict[str, Any]] = []
        append = price_rows.append
        # A named cursor is server-side in psycopg.  An unnamed cursor buffers the
        # entire result during ``execute`` before ``fetchmany`` runs, which made a
        # 1.9M-row PIT payload look hung even though the database query itself was
        # fast.  Streaming keeps memory bounded and lets the job report real progress.
        with conn.cursor(name="ai_compact_price_rows", row_factory=tuple_row) as cursor:
            cursor.execute(
                f"""
                SELECT
                    p.time, p.ticker,
                    p.adj_open, p.adj_high, p.adj_low, p.adj_close, p.adj_volume
                FROM {KIS_ADJUSTED_OHLCV_TABLE} p
                WHERE p.ticker = ANY(%s)
                  AND p.time BETWEEN %s::date AND %s::date
                -- The feature engine's date ranges and rank filters require a
                -- date-major stream.  This changes only transport order, never the
                -- PIT universe or the rows available to a condition.
                ORDER BY p.time, p.ticker
                """,
                [list(tickers), window["start"], window["end"]],
            )
            # A larger server-side batch amortises cursor round trips without keeping
            # the full PIT universe in the driver's result buffer.
            while batch := cursor.fetchmany(131_072):
                for row in batch:
                    append(_compact_price_row_from_tuple(row))
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

    def _resolve_backtest_window(self, conn: Any) -> dict[str, Any] | None:
        """Resolve the configured lookback window ending on the last completed KST session.

        The length is `config.backtest_lookback_years` (AI_BACKTEST_LOOKBACK_YEARS), bound
        as an interval rather than interpolated so the statement stays a fixed parameterised
        text.  The manifest records the resolved sessions and the policy id carries the
        years, so a shorter window is reproducible rather than merely cheaper.
        """
        row = conn.execute(
            """
            WITH cutoff AS (
                SELECT max(trade_date) AS session_end
                FROM core.trading_calendar
                WHERE is_open
                  AND trade_date < (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date
            ), sessions AS (
                SELECT c.trade_date
                FROM core.trading_calendar c
                CROSS JOIN cutoff
                WHERE c.is_open
                  AND c.trade_date BETWEEN cutoff.session_end - make_interval(years => %s)
                                       AND cutoff.session_end
            )
            SELECT min(trade_date) AS session_start,
                   max(trade_date) AS session_end,
                   count(*) AS session_count
            FROM sessions
            """,
            [self.config.backtest_lookback_years],
        ).fetchone()
        if not row or not row.get("session_start") or not row.get("session_end"):
            return None
        return {
            "start": _date_value(row["session_start"]),
            "end": _date_value(row["session_end"]),
            "session_count": int(row["session_count"]),
        }

    def _resolve_indicator_ticker_keys(
        self, conn: Any, table: str, tickers: Sequence[str]
    ) -> list[str]:
        """The suffixed keys ('000020#S05') this table uses for these 6-digit codes.

        Read from the table's most recent partition only, so the expensive `split_part`
        predicate is paid once over one day instead of over every partition in the
        backtest window.
        """

        rows = conn.execute(
            f"""
            WITH latest AS (
                SELECT max(time) AS time
                FROM {table}
                WHERE time >= CURRENT_DATE - INTERVAL '30 days'
            )
            SELECT DISTINCT t.ticker
            FROM {table} t, latest
            WHERE t.time = latest.time
              AND split_part(t.ticker, '#', 1) = ANY(%s)
            """,
            [list(tickers)],
        ).fetchall()
        # Both spellings, because the key format changed over the history: rows from
        # 2026 are keyed '005930#S07', rows from 2024 and earlier plain '005930'.
        # Matching only what the latest partition uses left ten-year reads at 0.2%
        # coverage. Both are equality on the indexed column, so the read stays an index
        # scan rather than reverting to split_part().
        keys = {str(row["ticker"]) for row in rows if row.get("ticker")}
        keys.update(str(ticker) for ticker in tickers)
        return sorted(keys)

    def _fetch_indicator_values_by_date(
        self, conn: Any, table: str, tickers: Sequence[str], since: date | None
    ) -> dict[str, dict[date, Mapping[str, Any]]]:
        """One ta_* table's values per ticker per date, from `since` onwards.

        Same shape for every family, so trend/volatility/volume reach the backtest the
        way momentum always has. They did not before: the frame builder hardcoded them
        to `{}`, which is why a compiled condition could only ever reference OHLCV and
        RSI - and why the backtest and the screen disagreed about every other indicator.

        Only the keys this module maps are projected, rather than hauling every
        indicator document into Python and discarding most of it - measured 1.87x on a
        205-name, 360-day read of all four tables (24.6s -> 13.2s).
        """

        if since is None:
            return {}
        keys = sorted(
            {
                spelling
                for source in _FAMILY_SOURCE_KEYS.get(table, ())
                for spelling in _key_spellings(source)
            }
        )
        if not keys:
            return {}
        # Aliases are quoted: indicator names carry dots (CCI_20_0.015, BBU_20_2.0), and
        # an unquoted `AS cci_20_0.015` is a syntax error - which is exactly how this
        # read was failing, in 188ms, while the handler below reported it as a statement
        # budget overrun.
        projection = ", ".join(
            f'(values_jsonb->>\'{key}\')::numeric AS "{_metric_key(key)}"' for key in keys
        )
        alias_by_column = {_metric_key(key): key for key in keys}
        # `split_part(ticker, '#', 1) = ANY(...)` cannot use the ticker index, so the
        # range read degenerated into a full scan of every partition in the window and
        # blew the statement budget. Resolve the suffixed keys ('000020#S05') from a
        # single recent partition first - one cheap lookup - then match them directly so
        # the multi-year read is an index scan.
        ticker_keys = self._resolve_indicator_ticker_keys(conn, table, tickers)
        if not ticker_keys:
            return {}
        # No DISTINCT ON: de-duplicating in SQL meant sorting every matched row by a
        # computed expression, which is most of what made this read unaffordable. The
        # keys are already known, so the collision (several security types sharing one
        # 6-digit code) is resolved here instead - first key wins, matching the previous
        # `ORDER BY ..., ticker` tie-break.
        rows = conn.execute(
            f"""
            SELECT ticker, time, {projection}
            FROM {table}
            WHERE ticker = ANY(%s)
              AND time >= %s::date
            ORDER BY ticker, time
            """,
            [ticker_keys, since],
        ).fetchall()
        values_by_ticker: dict[str, dict[date, Mapping[str, Any]]] = {}
        for row in rows:
            ticker_key = str(row.get("ticker") or "").split("#", 1)[0].zfill(6)
            by_date = values_by_ticker.setdefault(ticker_key, {})
            trade_date = _date_value(row["time"])
            if trade_date in by_date:
                continue
            by_date[trade_date] = {
                source: row[column]
                for column, source in alias_by_column.items()
                if row.get(column) is not None
            }
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

    def _fetch_macro_snapshot(
        self, conn: Any, price_rows: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any] | None:
        """The macro inputs the risk rules read, from the series the warehouse has.

        FX is real: BOK series 731Y003:0000003 is the daily 원/달러 rate, so its
        day-over-day change feeds FX_DAILY_MOVE_2PCT_CAP directly. There is no index
        series, so the equity leg is the loaded universe's mean daily return - a proxy,
        labelled as one in `kospi_source` so a report never calls it the KOSPI. There is
        no volatility series at all, so vkospi stays None and its rule skips rather than
        assuming a calm market.
        """

        snapshot: dict[str, Any] = {}
        try:
            rows = conn.execute(
                f"""
                SELECT value
                FROM {BOK_MACRO_VIEW}
                WHERE series_id = %(series)s
                  AND effective_date >= CURRENT_DATE - 30
                ORDER BY effective_date DESC
                LIMIT 2
                """,
                {"series": USD_KRW_SERIES_ID},
            ).fetchall()
        except Exception:  # noqa: BLE001 - macro capability failure must not abort screening.
            _logger.warning("BOK macro read failed; FX risk rule will not be evaluated")
            rows = []
        if len(rows) == 2:
            latest = _optional_float_value(rows[0].get("value"))
            prior = _optional_float_value(rows[1].get("value"))
            if latest is not None and prior and prior > 0:
                snapshot["fx_daily_change_pct"] = latest / prior - 1.0

        market_return = _latest_universe_return(price_rows)
        if market_return is not None:
            snapshot["kospi_close_change_pct"] = market_return
            snapshot["kospi_source"] = (
                "loaded universe mean daily return (no index series in the warehouse)"
            )
        return snapshot or None

    def _fetch_official_benchmark(
        self, conn: Any, window: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Read official KRX TR inputs, or expose one safe unavailable descriptor.

        The optional warehouse views must never make an otherwise valid analysis fail.
        A failed read can leave the transaction aborted, so reset it and restore the
        transaction-local statement timeout before returning the unavailable descriptor.
        """

        descriptor: dict[str, Any] = {
            "available": False,
            "unavailable_reason": None,
            "level_source": OFFICIAL_BENCHMARK_TR_VIEW,
            "weight_source": OFFICIAL_BENCHMARK_WEIGHT_VIEW,
            "index_codes": dict(OFFICIAL_BENCHMARK_INDEX_CODES),
            "window_start": window["start"].isoformat(),
            "window_end": window["end"].isoformat(),
            "weight_lag_months": 1,
            "kospi_tr": {},
            "kosdaq_tr": {},
            "monthly_weights": {},
        }
        try:
            level_rows = conn.execute(
                f"""
                SELECT index_code, trade_date, tr_value
                FROM {OFFICIAL_BENCHMARK_TR_VIEW}
                WHERE index_code = ANY(%s)
                  AND trade_date BETWEEN %s::date AND %s::date
                ORDER BY trade_date
                """,
                [list(OFFICIAL_BENCHMARK_INDEX_CODES.values()), window["start"], window["end"]],
            ).fetchall()
        except Exception:  # noqa: BLE001 - report a safe unavailable state.
            self._rollback_quietly(conn)
            self._set_statement_timeout(conn)
            descriptor["unavailable_reason"] = OFFICIAL_BENCHMARK_LEVELS_UNAVAILABLE
            return descriptor

        levels: dict[str, dict[str, float]] = {"kospi_tr": {}, "kosdaq_tr": {}}
        code_to_key = {code: key for key, code in OFFICIAL_BENCHMARK_INDEX_CODES.items()}
        for row in level_rows or ():
            key = code_to_key.get(str(row.get("index_code") or ""))
            trade_date = _optional_date_value(row.get("trade_date"))
            value = _finite_float_value(row.get("tr_value"))
            if key is not None and trade_date is not None and value is not None and value > 0.0:
                levels[key][trade_date.isoformat()] = value
        if any(not levels[key] for key in ("kospi_tr", "kosdaq_tr")):
            descriptor["unavailable_reason"] = OFFICIAL_BENCHMARK_LEVELS_MISSING
            return descriptor

        try:
            weight_rows = conn.execute(
                f"""
                SELECT month, kospi_weight, kosdaq_weight
                FROM {OFFICIAL_BENCHMARK_WEIGHT_VIEW}
                WHERE month >= (date_trunc('month', %s::date) - INTERVAL '1 month')::date
                  AND month <= date_trunc('month', %s::date)::date
                ORDER BY month
                """,
                [window["start"], window["end"]],
            ).fetchall()
        except Exception:  # noqa: BLE001 - report a safe unavailable state.
            self._rollback_quietly(conn)
            self._set_statement_timeout(conn)
            descriptor["unavailable_reason"] = OFFICIAL_BENCHMARK_WEIGHTS_UNAVAILABLE
            return descriptor

        monthly_weights: dict[str, list[float]] = {}
        for row in weight_rows or ():
            month = _optional_date_value(row.get("month"))
            kospi_weight = _finite_float_value(row.get("kospi_weight"))
            kosdaq_weight = _finite_float_value(row.get("kosdaq_weight"))
            if month is not None and kospi_weight is not None and kosdaq_weight is not None:
                monthly_weights[month.isoformat()[:7]] = [kospi_weight, kosdaq_weight]
        if not monthly_weights:
            descriptor["unavailable_reason"] = OFFICIAL_BENCHMARK_WEIGHTS_MISSING
            return descriptor

        descriptor.update(
            {
                "available": True,
                "kospi_tr": levels["kospi_tr"],
                "kosdaq_tr": levels["kosdaq_tr"],
                "monthly_weights": monthly_weights,
            }
        )
        return descriptor

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


def load_pipeline_data_from_env(
    query: str,
    trace_id: str,
    *,
    screen_current: bool = True,
    required_metrics: Sequence[str] | None = None,
    requires_financials: bool | None = None,
    compact_price_rows: bool = False,
) -> PipelineDataBundle:
    config = DataSourceConfig.from_env()
    if not config.database_dsn:
        return _fixture_bundle(
            f"database DSN is not set in any of {', '.join(DATABASE_DSN_ENV_CANDIDATES)}.",
            query=query,
        )
    return PostgresPipelineDataSource(config).load(
        query,
        trace_id,
        screen_current=screen_current,
        required_metrics=required_metrics,
        requires_financials=requires_financials,
        compact_price_rows=compact_price_rows,
    )


def measure_research_runtime_facts_from_env(
    query: str,
    trace_id: str,
) -> ResearchRuntimeFacts:
    """Run the configured read-only adapter and return only sanitized measurements.

    This deliberately does not fall back to fixtures when a configured PostgreSQL
    adapter fails. Callers can pass the result to the central policy and safely attest
    a failure as ``database_error`` without leaking operational details.
    """

    config = DataSourceConfig.from_env()
    if not config.database_dsn:
        return research_runtime_facts_from_bundle(
            _fixture_bundle("database DSN is not configured", query=query),
            dsn_configured=False,
            trace_id=trace_id,
        )
    try:
        bundle = PostgresPipelineDataSource(config).load(query, trace_id)
    except Exception:  # noqa: BLE001 - must fail closed without exposing driver detail.
        return classify_research_runtime_failure(dsn_configured=True)
    return research_runtime_facts_from_bundle(
        bundle,
        dsn_configured=True,
        trace_id=trace_id,
    )


def _fixture_bundle(reason: str, *, query: str) -> PipelineDataBundle:
    """Return an explicitly labelled local fixture; configured DB failures never use it."""
    if is_release_profile():
        raise FixtureModeForbiddenError(reason)
    fixture_as_of = datetime.now(UTC).date()
    data_availability = _data_availability_for_query(query, source="fixture")
    extract_snapshot = build_pipeline_extract_snapshot(
        price_rows=[],
        screening_candidates=[],
        l4_evidence=[],
        macro_snapshot=None,
        data_availability=data_availability,
    )
    return PipelineDataBundle(
        data_availability=data_availability,
        metadata={
            "source": "fixture",
            "immutable_snapshot_bundle": build_snapshot_bundle(
                as_of=fixture_as_of,
                source="fixture",
                pit_universe={"members": [], "policy": "fixture"},
                delisting={"events": [], "policy": "fixture"},
                indicator_input={"families": [], "query": query},
                lineage_refs=[reason, query],
            ).model_dump(mode="json"),
            "source_manifest": build_source_manifest(
                source="fixture",
                as_of=fixture_as_of,
                freshness="unknown",
                lineage_refs=[reason, query],
                source_version="local-fixture",
                extract_snapshot=extract_snapshot,
            ).model_dump(mode="json"),
            "source_snapshot_as_of": fixture_as_of.isoformat(),
            "source_snapshot_freshness": "unknown",
            "source_snapshot_version": "local-fixture",
            "reason": reason,
            "production_eligible": False,
            "dsn_env_candidates": list(DATABASE_DSN_ENV_CANDIDATES),
            "available_db_objects": [
                KIS_FEATURE_FRAME_VIEW,
                KIS_ADJUSTED_OHLCV_TABLE,
                TA_MOMENTUM_TICKER_TABLE,
                PIT_UNIVERSE_VIEW,
                ANALYST_REPORT_TABLE,
            ],
        },
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
    rsi_min: float = Field(default=70.0, ge=30.0, le=95.0)
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


def _relaxed_thresholds(
    base: ScreeningThresholds, round_index: int, *, profile: str = "rsi_rebound"
) -> ScreeningThresholds:
    """Deterministic widening ladder, used when no live LLM is configured and as the
    fallback whenever an LLM relaxation proposal is unusable."""

    step = round_index + 1
    rsi_update = (
        {"rsi_min": _clamped(base.rsi_min - 5.0 * step, RSI_OVERBOUGHT_MIN, 95.0)}
        if profile == "rsi_overbought"
        else {"rsi_max": _clamped(base.rsi_max + 5.0 * step, 5.0, 70.0)}
    )
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
            "sma20_band": _clamped(base.sma20_band + 0.02 * step, 0.005, 0.50),
            "bb_width_max": _clamped(base.bb_width_max + 0.06 * step, 0.02, 1.0),
            "bb_upper_ratio": _clamped(base.bb_upper_ratio - 0.02 * step, 0.50, 1.0),
            "roe_min": _clamped(base.roe_min - 0.02 * step, -1.0, 1.0),
            "debt_to_equity_max": _clamped(base.debt_to_equity_max + 0.5 * step, 0.1, 20.0),
            "operating_margin_min": _clamped(
                base.operating_margin_min - 0.02 * step, -1.0, 1.0
            ),
            "revenue_growth_min": _clamped(base.revenue_growth_min - 0.03 * step, -1.0, 10.0),
            **rsi_update,
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

    def rsi_overbought(row: Mapping[str, Any]) -> bool:
        rsi = _numeric(row.get("rsi"))
        return rsi is not None and rsi >= thresholds.rsi_min

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
        "rsi_overbought": rsi_overbought,
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
    profile: str,
    rounds: list[dict[str, Any]],
    universe_rows: int,
    *,
    frame: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    final = rounds[-1] if rounds else {}
    return {
        "profile": profile,
        "universe_rows": universe_rows,
        "rounds": rounds,
        "relaxation_rounds": max(len(rounds) - 1, 0),
        "relaxed": bool(final.get("relaxed")) and bool(final.get("matched_count")),
        "matched_count": int(final.get("matched_count") or 0),
        # Which date was screened, where the indicators came from, and what the
        # relative-strength benchmark was measured against - all three used to be
        # invisible in the report.
        "frame": dict(frame or {}),
    }


def _propose_relaxed_thresholds(
    *,
    query: str,
    profile: str,
    thresholds: ScreeningThresholds,
    round_index: int,
    universe_rows: int,
) -> ScreeningThresholds:
    """Return the audited relaxation ladder without invoking any provider.

    An empty screen is a normal market outcome. It must be reproducible and must not
    trigger an auxiliary LLM request (or an accidental network call) merely to widen
    thresholds. The parameters are retained for the trace-compatible call boundary.
    """

    del query, universe_rows
    return _relaxed_thresholds(thresholds, round_index, profile=profile)


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
        return (
            "rsi_overbought"
            if rsi_trade_rules(query).entry_side == "overbought"
            else "rsi_rebound"
        )
    if "볼린저" in query or "밴드" in query or "변동성" in query:
        return "bollinger_squeeze"
    if "200일" in query or "눌림목" in query or "20일선" in query:
        return "pullback_trend"
    if "상대강도" in query or "시장보다" in query or "주도주" in query:
        return "relative_strength"
    if "신고가" in query or "거래량" in query or "돌파" in query or "모멘텀" in query:
        return "breakout_volume"
    return "technical_proxy"


def screening_profile(query: str) -> str:
    """The profile the loader will actually screen this query with.

    Public so the requirement planner can be grounded in the same decision the loader
    makes, rather than deriving "what data does this need" from its own keyword table
    that had already drifted out of agreement with this one.
    """

    return _screening_profile(query)


# Which data families each screening profile reads. Every profile's WHERE clause is
# built on price/TA columns, so ohlcv_ta is unconditional; the fundamental profiles
# additionally join the DART financials CTE.
_PROFILE_DATA_FAMILIES: dict[str, tuple[str, ...]] = {
    "value_quality": ("ohlcv_ta", "fundamentals"),
    "quality_growth": ("ohlcv_ta", "fundamentals"),
    "growth_momentum": ("ohlcv_ta", "fundamentals"),
    "rsi_rebound": ("ohlcv_ta",),
    "rsi_overbought": ("ohlcv_ta",),
    "bollinger_squeeze": ("ohlcv_ta",),
    "pullback_trend": ("ohlcv_ta",),
    "relative_strength": ("ohlcv_ta",),
    "breakout_volume": ("ohlcv_ta",),
    "technical_proxy": ("ohlcv_ta",),
}


def screening_data_families(query: str) -> tuple[str, ...]:
    """Data families the screen for this query will read from the warehouse."""

    return _PROFILE_DATA_FAMILIES.get(screening_profile(query), ("ohlcv_ta",))


def _dart_amount(field: str, *, prior: bool = False) -> str:
    """SQL for one DART figure, guarded so non-numeric text yields NULL rather than erroring."""

    account = DART_ACCOUNTS[field]
    path = (
        f"accounts_jsonb->'{account}'->'raw'->>'frmtrm_amount'"
        if prior
        else f"accounts_jsonb->'{account}'->>'amount'"
    )
    return f"CASE WHEN {path} ~ '^-?[0-9]+$' THEN ({path})::numeric END"


def _financial_sql() -> str:
    """Latest DART filing per symbol, as ratios, for one screening date.

    Filings are selected on available_from - the date the statement became public -
    rather than period_end, so a screen never sees numbers that were not yet filed.
    Revenue growth compares against the same report_code roughly a year earlier;
    raw.frmtrm_amount is present too rarely (4% of symbols) to rely on.

    Takes the anchor date as a bind parameter rather than reading it from a CTE. The
    date has to be a plan-time constant for PostgreSQL to prune partitions; supplied as
    a subquery it cannot, and the screen then takes a lock on every partition of every
    daily table it touches and dies with "out of shared memory".
    """

    return f"""
        WITH financial_raw AS (
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
            WHERE available_from <= %(as_of)s::date
              AND available_from >= %(as_of)s::date - INTERVAL '3 years'
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
        )
        SELECT symbol, financial_period_end, roe, debt_to_equity, operating_margin,
               revenue_growth_yoy, eps
        FROM financials"""


# What each profile's predicate reads from the price path. Everything else it needs -
# moving averages, Bollinger bands, RSI - the warehouse has already computed, so the
# only reason to walk price history at all is the handful of things it has not.
#
# Scoping matters: a 252-row rolling max over 420 days of the whole universe is by far
# the most expensive thing the screen does (~3.0s), while the 20/60-day lags need only
# ~130 days (~0.5s). A relative-strength screen paying the 52-week-high cost it never
# reads was most of the query's runtime.
PATH_HIGH_252 = "high_252"
PATH_VOLUME_RATIO = "volume_ratio_20"
PATH_RETURNS = "returns"

_PROFILE_PATH_NEEDS: dict[str, frozenset[str]] = {
    "breakout_volume": frozenset({PATH_HIGH_252, PATH_VOLUME_RATIO, PATH_RETURNS}),
    "rsi_rebound": frozenset(),
    "rsi_overbought": frozenset(),
    "pullback_trend": frozenset(),
    "bollinger_squeeze": frozenset(),
    "relative_strength": frozenset({PATH_RETURNS}),
    "value_quality": frozenset({PATH_RETURNS}),
    "quality_growth": frozenset(),
    "growth_momentum": frozenset(),
}
# The baseline screen is re-filtered in-process for every relaxation round and for
# whichever profile is active, and _matched_screening_rules explains a candidate using
# all of them, so the baseline reads the full set.
_ALL_PATH_NEEDS = frozenset({PATH_HIGH_252, PATH_VOLUME_RATIO, PATH_RETURNS})

# Calendar days of price history each path feature needs, with slack for holidays.
_PATH_LOOKBACK_DAYS: dict[str, int] = {
    PATH_HIGH_252: 420,
    PATH_RETURNS: 130,
    PATH_VOLUME_RATIO: 40,
}

# Indicator keys inside the mart feature frame's JSONB columns, mapped to the names the
# screening predicates and candidate cards use. The warehouse computes these with
# pandas-ta on the adjusted series; reading them here is what makes the screen and the
# backtest share one definition instead of each deriving its own.
_TREND_KEYS: dict[str, str] = {
    "sma20": "SMA_20",
    "sma50": "SMA_50",
    "sma200": "SMA_200",
    "ema20": "EMA_20",
    "ema50": "EMA_50",
    "ema200": "EMA_200",
    "macd": "MACD_12_26_9",
    "macd_signal": "MACDs_12_26_9",
    "macd_hist": "MACDh_12_26_9",
    "adx": "ADX_14",
}
_VOLATILITY_KEYS: dict[str, str] = {
    "bb_upper": "BBU_20_2.0",
    "bb_lower": "BBL_20_2.0",
    "bb_middle": "BBM_20_2.0",
    "bb_pct": "BBP_20_2.0",
    "atr": "ATRr_14",
    "natr": "NATR_14",
}
# The Bollinger keys were renamed mid-pipeline: bars up to 2026-07-10 are keyed
# `BBU_20_2.0_2.0`, bars from 2025-08-28 `BBU_20_2.0`, and the two overlap. Reading only
# the current spelling left Bollinger populated on 13.5% of backtest bars while every
# other indicator sat at 99.9% - a strategy would quietly stop matching on older
# history. Each key falls back to its older spelling until the data team normalises it.
_LEGACY_KEY_SUFFIX = "_2.0"
_LEGACY_KEYED = frozenset(
    {"BBU_20_2.0", "BBL_20_2.0", "BBM_20_2.0", "BBP_20_2.0", "BBB_20_2.0"}
)


def _key_spellings(source: str) -> tuple[str, ...]:
    """Every warehouse spelling of one indicator key, most current first."""

    if source in _LEGACY_KEYED:
        return (source, f"{source}{_LEGACY_KEY_SUFFIX}")
    return (source,)
_MOMENTUM_KEYS: dict[str, str] = {
    "rsi": "RSI_14",
    "mfi": "MFI_14",
    "cci": "CCI_20_0.015",
    "willr": "WILLR_14",
    "roc": "ROC_10",
    "stoch_k": "STOCHk_14_3_3",
    "stoch_d": "STOCHd_14_3_3",
}
_VOLUME_KEYS: dict[str, str] = {
    "obv": "OBV",
    "cmf": "CMF_20",
    "ad": "AD",
    "adosc": "ADOSC_3_10",
}
# Bollinger bandwidth: pandas-ta reports BBB as a percentage of the middle band,
# (upper - lower) / middle * 100. The screen's thresholds are fractions, so it is
# divided here rather than every predicate being rewritten around a percentage.
_BB_BANDWIDTH_KEY = "BBB_20_2.0"
_BB_BANDWIDTH_SCALE = 100.0

# The per-ticker indicator tables behind the mart feature frame, read directly for the
# backtest window (the frame view is anchored to a single date).
INDICATOR_TABLES: dict[str, str] = {
    "trend": TA_TREND_TICKER_TABLE,
    "momentum": TA_MOMENTUM_TICKER_TABLE,
    "volatility": TA_VOLATILITY_TICKER_TABLE,
    "volume": TA_VOLUME_TICKER_TABLE,
}

# Which family each condition metric lives in, so the backtest reads only the tables its
# strategy actually references. Reading all four over a 200-name universe cost ~37s;
# most strategies touch one or two.
INDICATOR_FAMILY_BY_METRIC: dict[str, str] = {
    **{alias: "trend" for alias in _TREND_KEYS},
    **{alias: "momentum" for alias in _MOMENTUM_KEYS},
    **{alias: "volatility" for alias in _VOLATILITY_KEYS},
    **{alias: "volume" for alias in _VOLUME_KEYS},
    "bb_width": "volatility",
}
# Which warehouse keys each ta_* table is read for, so the query projects those columns
# instead of returning whole indicator documents.
_FAMILY_SOURCE_KEYS: dict[str, tuple[str, ...]] = {
    TA_TREND_TICKER_TABLE: tuple(_TREND_KEYS.values()),
    TA_MOMENTUM_TICKER_TABLE: tuple(_MOMENTUM_KEYS.values()),
    TA_VOLATILITY_TICKER_TABLE: (*_VOLATILITY_KEYS.values(), _BB_BANDWIDTH_KEY),
    TA_VOLUME_TICKER_TABLE: tuple(_VOLUME_KEYS.values()),
}

# Indicators each screening profile's predicate reads off the bar (path features like
# high_252 are computed separately and are not in any ta_* family).
_PROFILE_INDICATOR_METRICS: dict[str, tuple[str, ...]] = {
    "breakout_volume": ("sma20",),
    "rsi_rebound": ("rsi",),
    "rsi_overbought": ("rsi",),
    "pullback_trend": ("sma20", "sma200"),
    "bollinger_squeeze": ("bb_upper", "bb_width"),
    "relative_strength": (),
    "value_quality": (),
    "quality_growth": (),
    "growth_momentum": ("sma50",),
}


def indicator_families_for_query(query: str) -> tuple[str, ...]:
    """The ta_* families a run of this query needs on every backtest bar.

    All four, which is what a compiled condition on `sma200` or `bb_lower` needs. This
    was briefly cut to momentum while the four-family read looked like it could not be
    served; it turned out not to be a cost problem at all - the projected query carried
    an unquoted column alias for indicators whose names contain dots (CCI_20_0.015), so
    every family failed on a syntax error in under 200ms and was reported as a budget
    overrun. With the alias quoted and the ticker keys resolved up front, a ten-year
    momentum read is ~2.8s.
    """

    _ = _PROFILE_INDICATOR_METRICS.get(_screening_profile(query), ())
    return tuple(INDICATOR_TABLES)


# Momentum carries RSI, which the report and several fallbacks read whether or not the
# strategy names it, so it is never skipped.
ALWAYS_LOADED_FAMILIES = frozenset({"momentum"})


def indicator_families_for_metrics(
    metrics: Sequence[str], *, include_default: bool = True
) -> tuple[str, ...]:
    """The ta_* families needed to evaluate these condition metrics."""

    families = set(ALWAYS_LOADED_FAMILIES) if include_default else set()
    for metric in metrics:
        family = INDICATOR_FAMILY_BY_METRIC.get(str(metric).strip().lower())
        if family is not None:
            families.add(family)
    return tuple(family for family in INDICATOR_TABLES if family in families)
# Warehouse indicator key -> the name a condition uses, applied to every backtest bar
# so `sma20` on a bar means exactly what `sma20` meant in the screen.
BACKTEST_INDICATOR_ALIASES: dict[str, str] = {
    spelling: alias
    for alias, source in {
        **_TREND_KEYS,
        **_VOLATILITY_KEYS,
        **_MOMENTUM_KEYS,
        **_VOLUME_KEYS,
    }.items()
    for spelling in _key_spellings(source)
}


def available_indicator_metrics(conn: Any, *, as_of: date | None = None) -> list[str]:
    """Return indicator names that have rows in PostgreSQL's bounded recent window.

    This is intentionally a data probe, not the static compiler vocabulary.  A metric
    is offered to the language parser only when its warehouse JSONB key was observed.
    """

    from ai_graph.nodes.condition_compiler import runtime_derived_metrics, supported_metrics

    ceiling = as_of or datetime.now(KST).date()
    floor = ceiling - timedelta(days=SCREENING_DATE_LOOKBACK_DAYS)
    observed: set[str] = {"open", "high", "low", "close", "volume"}
    successful_queries = 0
    for table in INDICATOR_TABLES.values():
        rows = conn.execute(
            f"""
            SELECT DISTINCT jsonb_object_keys(values_jsonb) AS key
            FROM {table}
            WHERE time >= %s::date AND time <= %s::date
            """,
            [floor, ceiling],
        ).fetchall()
        successful_queries += 1
        for row in rows:
            source_key = str(row.get("key") or "")
            alias = BACKTEST_INDICATOR_ALIASES.get(source_key)
            if alias:
                observed.add(alias)
    try:
        financial_row = conn.execute(
            f"""
            SELECT EXISTS (
                SELECT 1 FROM {DART_FINANCIAL_TABLE}
                WHERE available_from <= %s::date
                  AND available_from >= %s::date - INTERVAL '3 years'
                LIMIT 1
            ) AS present
            """,
            [ceiling, ceiling],
        ).fetchone()
        if financial_row and financial_row.get("present"):
            observed.update({"roe", "debt_to_equity", "operating_margin", "operating_income", "revenue"})
    except Exception:
        _logger.info("financial indicator catalog is unavailable", exc_info=True)
    if successful_queries == 0:
        raise RuntimeError("indicator catalog could not be read")
    if "volume" in observed:
        observed.add("volume_ratio_20")
    for period in (20, 50, 200):
        if f"sma{period}" in observed:
            observed.update({f"close_above_sma_{period}", f"close_below_sma_{period}"})
    # The loader calculates several metrics from the real OHLCV path after this
    # catalog probe.  They do not appear as JSONB keys, so without this declaration
    # the AOAI research node is falsely told that a valid request (for example,
    # 1-month/3-month relative strength) cannot be backtested.
    observed.update(runtime_derived_metrics(observed))
    compiler_metrics = set(supported_metrics())
    return sorted(observed & compiler_metrics)


def available_indicator_metrics_from_env() -> list[str] | None:
    """Read the indicator catalog through the configured PostgreSQL connection."""

    config = DataSourceConfig.from_env()
    if not config.database_dsn:
        return None
    source = PostgresPipelineDataSource(config)
    with source._connect() as conn:
        source._set_statement_timeout(conn)
        return available_indicator_metrics(conn)

INDICATOR_FIELDS: tuple[str, ...] = (
    *_TREND_KEYS,
    *_VOLATILITY_KEYS,
    *_MOMENTUM_KEYS,
    *_VOLUME_KEYS,
    "bb_width",
)


def _jsonb_projection(column: str, keys: Mapping[str, str]) -> str:
    projections = []
    for alias, source in keys.items():
        spellings = _key_spellings(source)
        if len(spellings) == 1:
            expression = f"({column}->>'{spellings[0]}')::numeric"
        else:
            reads = ", ".join(f"{column}->>'{name}'" for name in spellings)
            expression = f"(COALESCE({reads}))::numeric"
        projections.append(f"{expression} AS {alias}")
    return ",\n            ".join(projections)


def _feature_frame_sql(date_param: str) -> str:
    """The mart feature frame for one trading date, without reading the mart view.

    KIS_FEATURE_FRAME_VIEW resolves to a join of six hypertables, the five indicator
    tables hanging off the price table by `ta.time = a.time` in a LEFT JOIN. Restricting
    the view to one date only restricts the price side: PostgreSQL will not propagate
    `a.time = <date>` across an outer join to the nullable side, so each ta_* table
    reaches the planner with no date qualification and every one of its 534 chunks is
    locked. Measured against production, one screening read of the view took 10,718 lock
    entries - the cluster's whole lock table is 6,400 (max_locks_per_transaction 64 x
    max_connections 100). That is the `out of shared memory` that has been failing
    analyses, and it is why the run this was traced from died in the Data node.

    Reading the same tables here lets each one carry its own date restriction, which the
    planner can prune on before taking locks. MATERIALIZED is load-bearing: an ordinary
    subquery is pulled up into the outer join and its WHERE degrades back into a join
    qual that prunes nothing - measured 2,150 lock entries per table pulled up, against
    18 when the pull-up is blocked.

    Only the four families the projection below reads are joined. The view also carries
    `pattern_values`, which nothing here selects; including it would cost another
    hypertable's worth of locks for a column that is discarded.
    """

    return f"""
        {FEATURE_FRAME_MARKER}
        WITH bars AS MATERIALIZED (
            SELECT time, ticker, base_ticker, adj_open, adj_high, adj_low,
                   adj_close, adj_volume, quality_flags
            FROM {ADJUSTED_OHLCV_TABLE}
            WHERE time = %({date_param})s::date
        ),
        trend_frame AS MATERIALIZED (
            SELECT ticker, time, values_jsonb FROM {TA_TREND_TICKER_TABLE}
            WHERE time = %({date_param})s::date
        ),
        momentum_frame AS MATERIALIZED (
            SELECT ticker, time, values_jsonb FROM {TA_MOMENTUM_TICKER_TABLE}
            WHERE time = %({date_param})s::date
        ),
        volatility_frame AS MATERIALIZED (
            SELECT ticker, time, values_jsonb FROM {TA_VOLATILITY_TICKER_TABLE}
            WHERE time = %({date_param})s::date
        ),
        volume_frame AS MATERIALIZED (
            SELECT ticker, time, values_jsonb FROM {TA_VOLUME_TICKER_TABLE}
            WHERE time = %({date_param})s::date
        )
        SELECT
            bars.time AS as_of_date,
            bars.ticker,
            bars.base_ticker,
            sm.name,
            sm.market_segment,
            sm.sector,
            bars.adj_open AS open,
            bars.adj_high AS high,
            bars.adj_low AS low,
            bars.adj_close AS close,
            bars.adj_volume AS volume,
            trend_frame.values_jsonb AS trend_values,
            momentum_frame.values_jsonb AS momentum_values,
            volatility_frame.values_jsonb AS volatility_values,
            volume_frame.values_jsonb AS volume_values
        FROM bars
        JOIN {SYMBOL_MASTER_TABLE} sm ON sm.symbol = bars.base_ticker
        LEFT JOIN trend_frame
          ON trend_frame.ticker = bars.ticker AND trend_frame.time = bars.time
        LEFT JOIN momentum_frame
          ON momentum_frame.ticker = bars.ticker AND momentum_frame.time = bars.time
        LEFT JOIN volatility_frame
          ON volatility_frame.ticker = bars.ticker AND volatility_frame.time = bars.time
        LEFT JOIN volume_frame
          ON volume_frame.ticker = bars.ticker AND volume_frame.time = bars.time
        WHERE (bars.quality_flags->>'adjusted_price_method') = '{KIS_ADJUSTED_PRICE_METHOD}'
          -- Today's screen is a recommendation, so it must not offer a name that is no
          -- longer listed. The historical PIT universe deliberately does not apply this
          -- predicate; applying it there is what survivorship bias is.
          AND sm.listing_status = 'listed'
    """


def _mart_frame_sql(*, sector: bool) -> str:
    """Every indicator the warehouse already has, for one trading date.

    DISTINCT ON collapses the security-type variants that share a 6-digit code; the
    feature frame keys rows as '000020#S05' in `ticker` and the bare code in
    `base_ticker`, and on some dates both variants are present.
    """

    sector_predicate = "\n          AND sector = %(sector)s" if sector else ""
    return f"""
        SELECT DISTINCT ON (base_ticker)
            base_ticker AS ticker,
            name,
            market_segment,
            market_segment AS market,
            sector,
            as_of_date AS time,
            open, high, low, close, volume,
            {_jsonb_projection("trend_values", _TREND_KEYS)},
            {_jsonb_projection("volatility_values", _VOLATILITY_KEYS)},
            {_jsonb_projection("momentum_values", _MOMENTUM_KEYS)},
            {_jsonb_projection("volume_values", _VOLUME_KEYS)},
            (COALESCE(
                {", ".join(
                    f"volatility_values->>'{name}'"
                    for name in _key_spellings(_BB_BANDWIDTH_KEY)
                )}
            ))::numeric / {_BB_BANDWIDTH_SCALE} AS bb_width
        FROM ({_feature_frame_sql("as_of")}) frame
        WHERE TRUE{sector_predicate}
        ORDER BY base_ticker, ticker
    """


def _prev_rsi_sql() -> str:
    return f"""
        SELECT DISTINCT ON (base_ticker)
            base_ticker AS ticker,
            (momentum_values->>'{_MOMENTUM_KEYS["rsi"]}')::numeric AS prev_rsi
        FROM ({_feature_frame_sql("prev")}) frame
        ORDER BY base_ticker, ticker
    """


def _path_features_sql(needs: frozenset[str]) -> tuple[str, int]:
    """Only the price-path features the warehouse does not precompute.

    Returns the statement and the calendar-day window it needs, so a screen that never
    reads a 52-week high does not pay to compute one.
    """

    lookback = max(
        (_PATH_LOOKBACK_DAYS[need] for need in needs if need in _PATH_LOOKBACK_DAYS),
        default=40,
    )
    # The close comes from here, not from the (possibly sector-scoped) feature frame,
    # so the relative-strength benchmark can be the whole priced universe.
    selected = ["ticker", "time", "adj_close AS close"]
    windows = ["wt AS (PARTITION BY ticker ORDER BY time)"]
    if PATH_HIGH_252 in needs:
        selected.append("max(adj_high) OVER w252 AS high_252")
        windows.append(
            "w252 AS (PARTITION BY ticker ORDER BY time "
            "ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)"
        )
    if PATH_VOLUME_RATIO in needs:
        selected.append("avg(adj_volume) OVER w20 AS avg_volume_20")
        windows.append(
            "w20 AS (PARTITION BY ticker ORDER BY time "
            "ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)"
        )
    if PATH_RETURNS in needs:
        selected.append("lag(adj_close, 20) OVER wt AS close_20d_ago")
        selected.append("lag(adj_close, 60) OVER wt AS close_60d_ago")
    projection = ",\n                ".join(selected)
    return (
        f"""
        WITH path AS (
            SELECT
                {projection}
            FROM {KIS_ADJUSTED_OHLCV_TABLE}
            WHERE time > %(as_of)s::date - {lookback}
              AND time <= %(as_of)s::date
            WINDOW {", ".join(windows)}
        )
        SELECT * FROM path WHERE time = %(as_of)s::date
        """,
        lookback,
    )


def _latest_universe_return(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """Mean one-day return across the loaded universe on its most recent date."""

    by_ticker: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        close = _optional_float_value(row.get("close"))
        date_value = str(row.get("date") or "")
        if close is None or not date_value:
            continue
        by_ticker.setdefault(str(row.get("ticker") or ""), []).append((date_value, close))
    returns: list[float] = []
    for series in by_ticker.values():
        if len(series) < 2:
            continue
        series.sort(key=lambda item: item[0])
        prior, latest = series[-2][1], series[-1][1]
        if prior > 0:
            returns.append(latest / prior - 1.0)
    return sum(returns) / len(returns) if returns else None


def _relative_strength(
    path_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, float | None]], dict[str, Any]]:
    """Each stock's excess return over the market, and what "the market" was.

    The benchmark is the mean return of the whole priced universe, computed before any
    sector filter is applied. It used to be the mean of whatever set the screen had
    already narrowed to, so asking for "반도체 섹터 주도주 중 상대강도 강한 종목"
    measured each chip stock against the chip sector's own average - a sector that fell
    20% while the market rose still produced "leaders", because half of any set is
    above its own mean by construction. Relative strength now means the same thing
    whatever the query filtered on, and the population is reported alongside it.

    Both the close and its lagged values come from `path_rows`, which is never
    sector-scoped. Taking the close from the feature frame instead silently put the
    filter back: tickers outside the sector had no close to pair with their return and
    dropped out of the mean.
    """

    returns: dict[str, dict[str, float | None]] = {}
    for row in path_rows:
        ticker = str(row.get("ticker") or "").zfill(6)
        close = _optional_float_value(row.get("close"))
        if close is None:
            continue
        entry: dict[str, float | None] = {}
        for horizon, column in (("20d", "close_20d_ago"), ("60d", "close_60d_ago")):
            prior = _optional_float_value(row.get(column))
            entry[horizon] = close / prior - 1.0 if prior and prior > 0 else None
        returns[ticker] = entry

    benchmark: dict[str, Any] = {
        "population": "priced_universe_before_sector_filter",
        "constituents": len(returns),
    }
    market: dict[str, float | None] = {}
    for horizon in ("20d", "60d"):
        values = [
            entry[horizon] for entry in returns.values() if entry.get(horizon) is not None
        ]
        market[horizon] = sum(values) / len(values) if values else None
        benchmark[f"market_return_{horizon}"] = market[horizon]
        benchmark[f"observations_{horizon}"] = len(values)

    strength: dict[str, dict[str, float | None]] = {}
    for ticker, entry in returns.items():
        strength[ticker] = {}
        for horizon in ("20d", "60d"):
            own, mkt = entry.get(horizon), market.get(horizon)
            # A stock without enough history has no excess return. It used to be
            # COALESCE(return, 0) - market, which handed every newly listed name the
            # negative of the market as its "relative strength" and let it screen in
            # whenever the market fell.
            strength[ticker][horizon] = (
                own - mkt if own is not None and mkt is not None else None
            )
    return strength, benchmark


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
    if profile == "rsi_overbought" and rsi is not None and rsi >= RSI_OVERBOUGHT_MIN:
        rules.append(f"RSI {rsi:.0f} 과매수권")
    elif rsi is not None and rsi <= RSI_OVERSOLD_MAX:
        rules.append(f"RSI {rsi:.0f} 과매도권")
    if (
        profile == "rsi_rebound"
        and prev_rsi is not None
        and rsi is not None
        and prev_rsi < 30 <= rsi
    ):
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
        except Exception:  # noqa: BLE001 - unreadable optional capability is unavailable.
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
            # DART receipt numbers are date-only. EOD signals may not use a filing on
            # the same date; it becomes eligible only on the following KRX session.
            while pointer < len(filings) and filings[pointer]["filed"] < row_date:
                current = filings[pointer]["ratios"]
                pointer += 1
            for metric, value in current.items():
                row.setdefault(metric, value)


def _raw_price_capabilities(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    required_ohlcv = ("raw_open", "raw_high", "raw_low", "raw_close", "raw_volume")
    missing_ohlcv_rows = [
        {
            "date": str(row.get("date") or ""),
            "ticker": str(row.get("ticker") or "").zfill(6),
            "missing_fields": [field for field in required_ohlcv if row.get(field) is None],
        }
        for row in rows
        if any(row.get(field) is None for field in required_ohlcv)
    ]
    missing_notional_rows = [
        {"date": str(row.get("date") or ""), "ticker": str(row.get("ticker") or "").zfill(6)}
        for row in rows
        if row.get("raw_notional") is None
    ]
    raw_ohlcv = bool(rows) and not missing_ohlcv_rows
    raw_notional = bool(rows) and not missing_notional_rows
    if not raw_ohlcv:
        return {
            "raw_ohlcv": False,
            "raw_notional": False,
            "reason_code": "raw_ohlcv_source_missing_or_uncovered",
            "reason": "Required raw OHLCV coverage is incomplete; no adjusted values were substituted.",
            "missing_raw_ohlcv_rows": missing_ohlcv_rows,
            "missing_raw_notional_rows": missing_notional_rows,
        }
    if not raw_notional:
        return {
            "raw_ohlcv": True,
            "raw_notional": False,
            "reason_code": "raw_notional_source_missing_or_uncovered",
            "reason": "Required verified raw traded-value coverage is incomplete; capacity must not be claimed.",
            "missing_raw_ohlcv_rows": [],
            "missing_raw_notional_rows": missing_notional_rows,
        }
    return {
        "raw_ohlcv": True,
        "raw_notional": True,
        "reason_code": None,
        "reason": None,
        "missing_raw_ohlcv_rows": [],
        "missing_raw_notional_rows": [],
    }

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
        "adjusted_open": _float_value(row.get("adjusted_open", row["open"])),
        "adjusted_high": _float_value(row.get("adjusted_high", row["high"])),
        "adjusted_low": _float_value(row.get("adjusted_low", row["low"])),
        "adjusted_close": _float_value(row.get("adjusted_close", row["close"])),
        "adjusted_volume": _float_value(row.get("adjusted_volume", row["volume"])),
        "raw_open": _optional_float_value(row.get("raw_open")),
        "raw_high": _optional_float_value(row.get("raw_high")),
        "raw_low": _optional_float_value(row.get("raw_low")),
        "raw_close": _optional_float_value(row.get("raw_close")),
        "raw_volume": _optional_float_value(row.get("raw_volume")),
        "raw_notional": _optional_float_value(row.get("raw_notional")),
    }
    _merge_metric_values(price_row, row)
    rsi = _find_metric_value(row.get("momentum_values"), RSI_KEYS, contains="rsi")
    if rsi is not None:
        price_row["rsi"] = rsi
    return price_row


def _compact_price_row_from_source(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return the lossless execution subset for a sealed OHLCV-only plan.

    ``open`` through ``volume`` remain the adjusted signal series.  ``raw_*`` fields
    remain source rows for execution.  We intentionally do not derive traded value or
    add placeholder indicator/financial fields: a missing feature must remain missing
    rather than change the strategy that was sealed.
    """

    return {
        "date": _date_value(row["as_of_date"]).isoformat(),
        "ticker": str(row["ticker"]).zfill(6),
        "open": _float_value(row["open"]),
        "high": _float_value(row["high"]),
        "low": _float_value(row["low"]),
        "close": _float_value(row["close"]),
        "volume": _float_value(row["volume"]),
        "raw_open": _optional_float_value(row.get("raw_open")),
        "raw_high": _optional_float_value(row.get("raw_high")),
        "raw_low": _optional_float_value(row.get("raw_low")),
        "raw_close": _optional_float_value(row.get("raw_close")),
        "raw_volume": _optional_float_value(row.get("raw_volume")),
        "raw_notional": _optional_float_value(row.get("raw_notional")),
    }


def _compact_price_row_from_tuple(row: Sequence[Any]) -> dict[str, Any]:
    """Convert one streamed PostgreSQL tuple without allocating an intermediate mapping.

    This deliberately uses KIS's official adjusted OHLCV for both signals and fills.
    It is not a raw-price substitute: the compact plan declares this execution basis
    explicitly and disables capacity claims when source traded value is absent.  That
    avoids a multi-million-row raw-table join for a price-only strategy while retaining
    one internally consistent, source-provided series.
    """

    (
        as_of_date,
        ticker,
        open_price,
        high_price,
        low_price,
        close_price,
        volume,
    ) = row
    return {
        "date": _date_value(as_of_date).isoformat(),
        "ticker": str(ticker).zfill(6),
        "open": _float_value(open_price),
        "high": _float_value(high_price),
        "low": _float_value(low_price),
        "close": _float_value(close_price),
        "volume": _float_value(volume),
        "execution_price_basis": "official_adjusted_ohlcv",
    }


def _feature_frame_row_from_sources(
    row: Mapping[str, Any],
    indicators_by_family: Mapping[str, Mapping[date, Mapping[str, Any]]],
    symbol_info: Mapping[str, Any],
) -> dict[str, Any]:
    """One backtest bar: prices plus every indicator family for that date.

    All four non-momentum families used to be hardcoded to `{}` here, so the backtest
    saw OHLCV and RSI and nothing else - while the screen that picked the stock had
    moving averages, bands and the rest. Filling them is what lets a compiled condition
    mean the same thing on both sides.
    """

    trade_date = _date_value(row["as_of_date"])
    return {
        **dict(row),
        "as_of_date": trade_date,
        "name": symbol_info.get("name") or "",
        "market_segment": symbol_info.get("market_segment") or "KRX",
        **{
            f"{family}_values": indicators_by_family.get(family, {}).get(trade_date, {})
            for family in INDICATOR_TABLES
        },
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
    """Flatten the indicator JSONB onto the bar, under the condition vocabulary's names.

    Both spellings are kept: the warehouse key (`SMA_20`) so nothing that already reads
    it breaks, and the canonical alias (`sma20`) that compiled conditions and the screen
    both use. Bollinger bandwidth is rescaled from pandas-ta's percentage to the
    fraction the thresholds are written in - the same conversion the screen applies, so
    `bb_width` cannot mean 16.35 on one side and 0.1635 on the other.
    """

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
            source_key = str(key)
            target.setdefault(_metric_key(source_key), parsed)
            alias = BACKTEST_INDICATOR_ALIASES.get(source_key)
            if alias is not None:
                target.setdefault(alias, parsed)
            if source_key in _key_spellings(_BB_BANDWIDTH_KEY):
                target.setdefault("bb_width", parsed / _BB_BANDWIDTH_SCALE)


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


def _metric_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _kst_today() -> date:
    """Today in the market's timezone rather than the host's timezone."""

    return datetime.now(KST).date()


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _optional_date_value(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return _date_value(value)
    except (TypeError, ValueError):
        return None


def _finite_float_value(value: Any) -> float | None:
    parsed = _optional_float_value(value)
    return parsed if parsed is not None and math.isfinite(parsed) else None


def _official_benchmark_status(descriptor: Mapping[str, Any] | None) -> dict[str, Any]:
    """Summarize benchmark provenance without copying per-session levels into metadata."""

    if not isinstance(descriptor, Mapping):
        return {"available": False, "unavailable_reason": "benchmark load was not attempted"}
    return {
        "available": bool(descriptor.get("available")),
        "unavailable_reason": descriptor.get("unavailable_reason"),
        "level_source": descriptor.get("level_source"),
        "weight_source": descriptor.get("weight_source"),
        "index_codes": descriptor.get("index_codes"),
        "weight_lag_months": descriptor.get("weight_lag_months"),
        "kospi_tr_sessions": len(descriptor.get("kospi_tr") or {}),
        "kosdaq_tr_sessions": len(descriptor.get("kosdaq_tr") or {}),
        "monthly_weight_months": len(descriptor.get("monthly_weights") or {}),
    }


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
