import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ai_graph.data_sources.db import (
    AI_DATABASE_DSN_ENV,
    DATABASE_URL_ENV,
    DEFAULT_BACKTEST_LOOKBACK_DAYS,
    ADJUSTED_OHLCV_TABLE,
    DataSourceConfig,
    FEATURE_FRAME_MARKER,
    PostgresPipelineDataSource,
    QUANT_DB_DSN_ENV,
    RSI_OVERSOLD_THRESHOLD,
    ScreeningThresholds,
    _price_row_from_feature_frame_record,
    _relaxed_thresholds,
    _mart_frame_sql,
    _path_features_sql,
    _prev_rsi_sql,
    _relative_strength,
    _screening_matcher,
    load_pipeline_data_from_env,
    resolve_database_dsn_from_env,
)
from ai_graph.data_sources.sectors import clear_sector_cache


def setup_function() -> None:
    clear_sector_cache()


AS_OF = date(2026, 5, 20)
PREVIOUS_TRADING_DAY = date(2026, 5, 19)


class FakeResult:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self._row = row if row is not None else (self.rows[0] if self.rows else None)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self._row


class FakeScreeningConnection:
    """Stands in for the warehouse across the statements a screen now issues.

    The loader asks four small questions instead of one large one (anchor date, mart
    indicators, price-path features, previous-day RSI) because the date has to reach
    each as a bind parameter. Dispatching on statement shape keeps these tests honest
    about that split rather than returning one canned row to everything.
    """

    def __init__(
        self,
        *,
        frame_rows=None,
        sectors=("반도체", "화학"),
        sector_view_missing=False,
        unavailable_probes=(),
    ):
        self.frame_rows = frame_rows if frame_rows is not None else [default_frame_row()]
        self.sectors = sectors
        self.sector_view_missing = sector_view_missing
        # Tables the warehouse has no rows for, by name, so a test can reproduce the
        # "capability is configured but empty" case the probe now has to catch.
        self.unavailable_probes = tuple(unavailable_probes)
        self.aborted = False
        self.rollbacks = 0
        self.calls: list[tuple[str, object]] = []
        self.frame_reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def rollback(self):
        self.rollbacks += 1
        self.aborted = False

    def execute(self, query: str, params=None):
        self.calls.append((query, params))
        if self.sector_view_missing and "FROM mart.common_stock_universe_asof u" in query:
            self.aborted = True
            raise RuntimeError('relation "mart.common_stock_universe_asof" does not exist')
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        if "set_config('statement_timeout'" in query:
            return FakeResult()
        if "AS present" in query:
            missing = any(table in query for table in self.unavailable_probes)
            return FakeResult(row={"present": not missing})
        if "DISTINCT sm.sector" in query or "DISTINCT sector" in query:
            return FakeResult(rows=[{"sector": s} for s in self.sectors])
        if "max(time) AS as_of_date" in query:
            return FakeResult(row={"as_of_date": AS_OF})
        if "max(time) AS previous_date" in query:
            return FakeResult(row={"previous_date": PREVIOUS_TRADING_DAY})
        if "min(time) AS date_floor" in query:
            return FakeResult(row={"date_floor": AS_OF})
        if FEATURE_FRAME_MARKER in query and "prev_rsi" in query:
            return FakeResult(rows=[
                {"ticker": row["ticker"], "prev_rsi": row.get("prev_rsi")}
                for row in self.frame_rows
            ])
        if FEATURE_FRAME_MARKER in query:
            self.frame_reads += 1
            return FakeResult(rows=[dict(row) for row in self.frame_rows])
        if "WITH path AS" in query:
            return FakeResult(rows=[
                {
                    "ticker": row["ticker"],
                    "time": AS_OF,
                    "close": row.get("close"),
                    "high_252": row.get("high_252"),
                    "avg_volume_20": row.get("avg_volume_20", Decimal("1000000")),
                    "close_20d_ago": row.get("close_20d_ago"),
                    "close_60d_ago": row.get("close_60d_ago"),
                }
                for row in self.frame_rows
            ])
        if "mart.dart_financial_asof" in query:
            return FakeResult(rows=[])
        if "MKTCAP" in query:
            # Only the screener ranks by present-day market cap now. The backtest
            # universe deliberately does not - see the "WITH bounds AS" branch.
            return FakeResult(rows=[{"symbol": row["ticker"]} for row in self.frame_rows])
        if "FROM core.symbol_master" in query:
            rows = [
                {
                    "symbol": row["ticker"],
                    "name": row.get("name") or "",
                    "market": "KOSPI",
                    "market_segment": "KOSPI",
                    "listing_status": "listed",
                }
                for row in self.frame_rows
            ]
            return FakeResult(rows=rows)
        if "WITH bounds AS" in query:
            # The backtest universe, ranked by traded value as of the backtest start.
            return FakeResult(rows=[
                {"symbol": row["ticker"], "as_of": AS_OF} for row in self.frame_rows
            ])
        if "FROM feature.kis_adjusted_ohlcv_daily" in query and "adj_open" in query:
            return FakeResult(rows=[
                {
                    "as_of_date": AS_OF,
                    "ticker": row["ticker"],
                    "open": Decimal("190000"),
                    "high": Decimal("201000"),
                    "low": Decimal("189000"),
                    "close": row.get("close", Decimal("200000")),
                    "volume": Decimal("1000000"),
                }
                for row in self.frame_rows
            ])
        if "feature.ta_momentum_ticker_daily" in query:
            return FakeResult(rows=[])
        if "raw.analyst_report_summary" in query:
            return FakeResult(rows=[])
        if "mart.bok_macro_asof" in query:
            return FakeResult(row={"row_count": 0, "latest_effective_date": None})
        return FakeResult()


def default_frame_row(**overrides):
    row = {
        "time": AS_OF,
        "ticker": "000660",
        "name": "SK하이닉스",
        "market_segment": "KOSPI",
        "market": "KOSPI",
        "sector": "반도체",
        "close": Decimal("200000"),
        "volume": Decimal("1800000"),
        "avg_volume_20": Decimal("1000000"),
        "high_252": Decimal("200000"),
        "sma20": Decimal("180000"),
        "sma200": Decimal("150000"),
        "close_20d_ago": Decimal("190000"),
        "close_60d_ago": Decimal("180000"),
    }
    row.update(overrides)
    return row


def test_pipeline_data_source_uses_fixture_boundary_without_dsn(monkeypatch) -> None:
    monkeypatch.delenv(AI_DATABASE_DSN_ENV, raising=False)
    monkeypatch.delenv(QUANT_DB_DSN_ENV, raising=False)
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    bundle = load_pipeline_data_from_env("RSI가 30 이하인 KOSPI200", "trace-db")

    assert bundle.price_rows == []
    assert bundle.l4_evidence == []
    assert bundle.metadata["source"] == "fixture"
    assert bundle.metadata["dsn_env_candidates"] == [
        AI_DATABASE_DSN_ENV,
        QUANT_DB_DSN_ENV,
        DATABASE_URL_ENV,
    ]
    assert "mart.kis_adjusted_feature_frame_asof" in bundle.metadata["available_db_objects"]


def test_configured_database_failure_is_not_replaced_with_fixture(monkeypatch) -> None:
    monkeypatch.setenv(AI_DATABASE_DSN_ENV, "postgresql://quant-db")
    monkeypatch.delenv(QUANT_DB_DSN_ENV, raising=False)
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    def fail_to_load(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(PostgresPipelineDataSource, "load", fail_to_load)

    with pytest.raises(RuntimeError, match="database unavailable"):
        load_pipeline_data_from_env("005930 RSI", "trace-live-db")


def test_data_source_config_uses_quant_db_dsn_alias() -> None:
    config = DataSourceConfig.from_env({QUANT_DB_DSN_ENV: "postgresql://example"})

    assert config.database_dsn == "postgresql://example"
    assert config.database_dsn_env == QUANT_DB_DSN_ENV
    assert config.connect_timeout_seconds == 20
    assert config.statement_timeout_ms == 30_000


def test_data_source_config_normalizes_database_url_driver_prefix() -> None:
    config = DataSourceConfig.from_env({DATABASE_URL_ENV: "postgresql+asyncpg://user:pass@db/quant"})

    assert config.database_dsn == "postgresql://user:pass@db/quant"
    assert config.database_dsn_env == DATABASE_URL_ENV


def test_resolve_database_dsn_prefers_ai_database_dsn() -> None:
    dsn, env_name = resolve_database_dsn_from_env(
        {
            AI_DATABASE_DSN_ENV: "postgresql://ai-db",
            QUANT_DB_DSN_ENV: "postgresql://quant-db",
            DATABASE_URL_ENV: "postgresql://database-url",
        }
    )

    assert dsn == "postgresql://ai-db"
    assert env_name == AI_DATABASE_DSN_ENV


def test_feature_frame_record_maps_prices_and_rsi_metric() -> None:
    row = {
        "as_of_date": date(2026, 5, 20),
        "ticker": "005930",
        "name": "삼성전자",
        "market_segment": "KOSPI",
        "open": Decimal("100"),
        "high": Decimal("105"),
        "low": Decimal("99"),
        "close": Decimal("103"),
        "volume": Decimal("1000000"),
        "trend_values": {},
        "momentum_values": {"RSI_14": Decimal("28.5")},
        "volatility_values": {},
        "volume_values": {},
        "pattern_values": {},
    }

    price_row = _price_row_from_feature_frame_record(row)

    assert price_row["date"] == "2026-05-20"
    assert price_row["ticker"] == "005930"
    assert price_row["close"] == 103.0
    assert price_row["rsi"] == 28.5


def test_postgres_data_source_sets_statement_timeout_with_set_config() -> None:
    class Result:
        def __init__(
            self,
            *,
            rows: list[dict[str, object]] | None = None,
            row: dict[str, object] | None = None,
        ) -> None:
            self.rows = rows or []
            self.row = row

        def fetchall(self) -> list[dict[str, object]]:
            return self.rows

        def fetchone(self) -> dict[str, object] | None:
            return self.row

    class RecordingConnection:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[object] | None]] = []

        def __enter__(self) -> "RecordingConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: str, params: list[object] | None = None) -> Result:
            self.calls.append((query, params))
            if "AS present" in query:
                return Result(row={"present": True})
            if "min(time) AS date_floor" in query:
                return Result(row={"date_floor": date(2016, 5, 20)})
            if "SELECT DISTINCT t.ticker" in query:
                return Result(rows=[{"ticker": "005930#S01"}])
            if "feature.kis_adjusted_ohlcv_daily" in query:
                return Result(
                    rows=[
                        {
                            "as_of_date": date(2026, 5, 20),
                            "ticker": "005930",
                            "open": Decimal("100"),
                            "high": Decimal("105"),
                            "low": Decimal("99"),
                            "close": Decimal("103"),
                            "volume": Decimal("1000000"),
                        }
                    ]
                )
            if "feature.ta_momentum_ticker_daily" in query:
                return Result(
                    rows=[
                        {
                            # Momentum is fetched for the whole backtest pool at once, so
                            # rows carry the ticker they belong to, and the query now
                            # projects each indicator key into its own column rather than
                            # returning the whole document.
                            "ticker": "005930#S01",
                            "time": date(2026, 5, 20),
                            "rsi_14": Decimal("28.5"),
                        }
                    ]
                )
            if "raw.analyst_report_summary" in query:
                return Result(rows=[])
            if "meta.view_common_stock_universe" in query:
                return Result(
                    row={
                        "symbol": "005930",
                        "name": "삼성전자",
                        "market_segment": "KOSPI",
                        "listing_status": "listed",
                    }
                )
            if "mart.bok_macro_asof" in query:
                return Result(row={"row_count": 0, "latest_as_of_date": None})
            return Result()

    class RecordingDataSource(PostgresPipelineDataSource):
        def __init__(self, config: DataSourceConfig) -> None:
            super().__init__(config)
            self.conn = RecordingConnection()

        def _connect(self) -> RecordingConnection:
            return self.conn

    source = RecordingDataSource(
        DataSourceConfig(database_dsn="postgresql://example", statement_timeout_ms=12_345)
    )

    bundle = source.load("005930 RSI", "trace-db")

    assert bundle.metadata["source"] == "postgres"
    assert bundle.price_rows[0]["rsi"] == 28.5
    assert source.conn.calls[0] == (
        "SELECT set_config('statement_timeout', %s, true)",
        ["12345ms"],
    )
    price_query = next(
        query
        for query, _ in source.conn.calls
        if "WHERE ticker = ANY(%s)" in query
    )
    assert "time >= %s::date" in price_query
    assert "ORDER BY ticker, time" in price_query


def test_postgres_data_source_broad_screening_uses_screening_candidates() -> None:
    class ScreeningDataSource(PostgresPipelineDataSource):
        def __init__(self, config):
            super().__init__(config)
            self.conn = FakeScreeningConnection()

        def _connect(self):
            return self.conn

    source = ScreeningDataSource(DataSourceConfig(database_dsn="postgresql://example"))

    bundle = source.load("최근 52주 신고가 거래량 150% 종목을 찾아줘", "trace-screening")

    assert bundle.metadata["ticker"] == "000660"
    assert bundle.screening_candidates[0]["ticker"] == "000660"
    assert "거래량 20일 평균 대비 150% 이상" in bundle.screening_candidates[0]["matched_rules"]
    assert bundle.data_availability["price_ta"] == "available"
    # Indicators are read, not recomputed.
    frame = bundle.metadata["screening_relaxation"]["frame"]
    assert frame["indicator_source"] == ADJUSTED_OHLCV_TABLE
    assert frame["as_of_date"] == AS_OF.isoformat()


def test_profile_screening_recovers_when_dynamic_sector_view_is_missing(monkeypatch) -> None:
    source = PostgresPipelineDataSource(DataSourceConfig(database_dsn="postgresql://example"))
    conn = FakeScreeningConnection(sector_view_missing=True)
    monkeypatch.setattr(source, "_screen_via_llm", lambda _conn, _query: None)

    candidates, trace = source._screen_with_relaxation(
        conn, "최근 52주 신고가 거래량 종목을 찾아줘"
    )

    assert conn.rollbacks == 1
    assert any("set_config(\'statement_timeout\'" in query for query, _ in conn.calls)
    assert candidates[0]["ticker"] == "000660"
    assert trace["matched_count"] == 1


def test_postgres_data_source_filters_screening_by_sector() -> None:
    class SectorScreeningDataSource(PostgresPipelineDataSource):
        def __init__(self, config):
            super().__init__(config)
            self.conn = FakeScreeningConnection(
                frame_rows=[default_frame_row(rsi=Decimal("28"), prev_rsi=Decimal("25"))]
            )

        def _connect(self):
            return self.conn

    source = SectorScreeningDataSource(DataSourceConfig(database_dsn="postgresql://example"))

    bundle = source.load("반도체 섹터에서 RSI 과매도 종목을 찾아줘", "trace-sector-screening")

    assert bundle.screening_candidates[0]["ticker"] == "000660"
    assert bundle.screening_candidates[0]["sector"] == "반도체"

    frame_queries = [
        (query, params)
        for query, params in source.conn.calls
        if FEATURE_FRAME_MARKER in query and "base_ticker" in query
    ]
    assert frame_queries
    query, params = frame_queries[0]
    assert "AND sector = %(sector)s" in query
    assert params["sector"] == "반도체"
    # The price-path read backs the relative-strength benchmark and must stay
    # universe-wide even when the frame is scoped to one sector.
    path_queries = [q for q, _ in source.conn.calls if "WITH path AS" in q]
    assert path_queries
    assert "sector" not in path_queries[0]


def test_postgres_data_source_screening_without_sector_has_no_sector_predicate() -> None:
    class NoSectorScreeningDataSource(PostgresPipelineDataSource):
        def __init__(self, config):
            super().__init__(config)
            self.conn = FakeScreeningConnection()

        def _connect(self):
            return self.conn

    source = NoSectorScreeningDataSource(DataSourceConfig(database_dsn="postgresql://example"))

    bundle = source.load("코스피 전체에서 신고가 종목을 찾아줘", "trace-no-sector")

    assert bundle.screening_candidates
    frame_queries = [
        query
        for query, _ in source.conn.calls
        if FEATURE_FRAME_MARKER in query and "base_ticker" in query
    ]
    assert frame_queries
    assert "%(sector)s" not in frame_queries[0]


def test_postgres_data_source_ambiguous_query_falls_back_to_screening_not_default_ticker() -> None:
    class AmbiguousDataSource(PostgresPipelineDataSource):
        def __init__(self, config):
            super().__init__(config)
            self.conn = FakeScreeningConnection()

        def _connect(self):
            return self.conn

    source = AmbiguousDataSource(DataSourceConfig(database_dsn="postgresql://example"))

    # No explicit 6-digit ticker, no broad-universe/broad-screening keyword,
    # no recognizable sector, and no stock name substring match: this used to
    # silently fall back to the hardcoded default ticker (005930, Samsung
    # Electronics). It should now retry as an unfiltered screening pass.
    bundle = source.load("괜찮은 종목 하나만 골라줘", "trace-ambiguous")

    assert bundle.metadata["ticker"] == "000660"
    assert bundle.metadata["ticker"] != "005930"
    assert bundle.metadata["ticker_resolution"] == "ambiguous_fallback_to_screening"
    assert bundle.screening_candidates



@pytest.mark.skipif(
    not resolve_database_dsn_from_env(os.environ)[0],
    reason="A supported database DSN is required for common-server DB integration test.",
)
def test_postgres_screening_statements_plan_against_common_server() -> None:
    source = PostgresPipelineDataSource(DataSourceConfig.from_env())

    with source._connect() as conn:
        source._set_statement_timeout(conn)
        as_of = source._resolve_screening_date(conn)
        assert as_of is not None
        path_sql, _ = _path_features_sql(frozenset({"high_252", "returns", "volume_ratio_20"}))
        for sql, params in (
            (_mart_frame_sql(sector=False), {"as_of": as_of}),
            (_mart_frame_sql(sector=True), {"as_of": as_of, "sector": "반도체"}),
            (path_sql, {"as_of": as_of}),
            (_prev_rsi_sql(), {"prev": as_of}),
        ):
            assert conn.execute(f"EXPLAIN {sql}", params).fetchall()


@pytest.mark.skipif(
    not resolve_database_dsn_from_env(os.environ)[0],
    reason="A supported database DSN is required for common-server DB integration test.",
)
def test_screening_frame_reads_indicators_from_the_mart_view() -> None:
    """The screen must not recompute what the warehouse already stores.

    Moving averages, Bollinger bands and RSI were derived here with window functions
    over 420 days of the whole universe, while mart.kis_adjusted_feature_frame_asof
    already carried them per ticker per date. Two derivations of one indicator is how
    the screen and the backtest ended up disagreeing about what "volatility" meant.
    """

    source = PostgresPipelineDataSource(DataSourceConfig.from_env())
    with source._connect() as conn:
        source._set_statement_timeout(conn, source.config.backtest_statement_timeout_ms)
        rows, trace = source._load_screening_frame(conn, sector=None, profile="relative_strength")

    assert rows
    assert trace["indicator_source"] == "feature.adjusted_ohlcv_daily"
    # The 52-week high is the single most expensive path feature; a relative-strength
    # screen never reads it and must not pay for it.
    assert "high_252" not in trace["path_features_computed"]
    assert trace["path_lookback_days"] <= 130

    populated = [row for row in rows if row.get("sma20") is not None]
    assert len(populated) > len(rows) * 0.9
    sample = populated[0]
    for field in ("sma20", "sma200", "bb_upper", "bb_width", "rsi", "atr", "macd"):
        assert sample.get(field) is not None, field


@pytest.mark.skipif(
    not resolve_database_dsn_from_env(os.environ)[0],
    reason="A supported database DSN is required for common-server DB integration test.",
)
def test_postgres_data_source_loads_common_server_pipeline_inputs() -> None:
    source = PostgresPipelineDataSource(DataSourceConfig.from_env())

    bundle = source.load("005930 RSI가 30 이하인 KOSPI200", "trace-db-live")

    assert bundle.metadata["source"] == "postgres"
    assert bundle.price_rows
    assert bundle.metadata["price_source"] == "feature.kis_adjusted_ohlcv_daily"
    assert "feature.ta_momentum_ticker_daily" in bundle.metadata["indicator_sources"]
    assert bundle.metadata["l4_evidence_source"] == "raw.analyst_report_summary"
    assert bundle.metadata["backtest_lookback_days"] >= DEFAULT_BACKTEST_LOOKBACK_DAYS
    assert any(row.get("rsi", 100) <= RSI_OVERSOLD_THRESHOLD for row in bundle.price_rows)


def test_empty_screen_is_not_re_run_and_backtest_still_uses_its_own_universe() -> None:
    """A screen that matched nothing must not block or repeat the backtest load.

    The baseline screen scans every ticker in feature.kis_adjusted_ohlcv_daily with six
    window functions over 420 days and runs on the widened backtest statement budget.
    `load()` used to call it once for the screening branch and then, on the ambiguous
    fallback, call it again with the same query and the same thresholds - which cannot
    return anything different. For a screen that legitimately matched nothing today
    (e.g. no KOSPI200 name is at RSI <= 30) that doubled the cost of the request and
    pushed it past the statement timeout, surfacing as
    "데이터 조회 시간이 초과되었습니다".
    """

    class Result:
        def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
            self.rows = rows or []

        def fetchall(self) -> list[dict[str, object]]:
            return self.rows

        def fetchone(self) -> dict[str, object] | None:
            return self.rows[0] if self.rows else None

    class CountingConnection:
        def __init__(self) -> None:
            self.baseline_screens = 0

        def __enter__(self) -> "CountingConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def rollback(self) -> None:
            return None

        def execute(self, query: str, params: object | None = None) -> Result:
            if FEATURE_FRAME_MARKER in query and "base_ticker" in query:
                self.baseline_screens += 1
            # The frame loader anchors on the price table before anything else; with no
            # date it short-circuits, which would hide the duplicate-screen bug this
            # test is about.
            if "max(time) AS as_of_date" in query:
                return Result([{"as_of_date": date(2026, 7, 30)}])
            if "AS present" in query:
                return Result([{"present": True}])
            return Result([])

    class EmptyScreenDataSource(PostgresPipelineDataSource):
        def _connect(self) -> CountingConnection:
            return connection

        def _fetch_backtest_universe(
            self, _conn: object, recommended: list[str]
        ) -> tuple[list[str], dict[str, object]]:
            assert recommended == []
            return ["000660"], {"selection": "stub"}

        def _fetch_symbol_info_map(
            self, _conn: object, tickers: list[str]
        ) -> dict[str, dict[str, object]]:
            return {ticker: {"ticker": ticker, "included": True} for ticker in tickers}

        def _fetch_price_rows(
            self,
            _conn: object,
            tickers: list[str],
            _symbol_info: object,
            _query: str,
            _indicator_families: object | None = None,
        ) -> tuple[list[dict[str, object]], int]:
            return [
                {
                    "date": "2016-08-03",
                    "ticker": tickers[0],
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100,
                    "volume": 1_000,
                }
            ], DEFAULT_BACKTEST_LOOKBACK_DAYS

        def _fetch_macro_status(self, _conn: object) -> dict[str, object]:
            return {}

    connection = CountingConnection()
    source = EmptyScreenDataSource(
        DataSourceConfig(database_dsn="postgresql://fake/fake")
    )

    bundle = source.load(
        "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어",
        "trace-dup",
    )

    assert connection.baseline_screens == 1
    assert bundle.metadata["recommended_tickers"] == []
    assert bundle.metadata["tickers"] == ["000660"]
    assert bundle.price_rows[0]["ticker"] == "000660"


def test_indicator_reads_are_anchored_by_bind_parameter_not_a_subquery() -> None:
    """The anchor date must reach every statement as a parameter.

    Supplied as `(SELECT max(...) FROM ...)`, the date is not a plan-time constant, so
    PostgreSQL cannot prune partitions: reading the feature frame then locks every
    partition of all five ta_* tables and the screen dies with "out of shared memory /
    max_locks_per_transaction" before returning a row. Measured on the common server,
    the same read costs ~25s as a subquery and ~0.4s as a parameter.
    """

    statements = [
        _mart_frame_sql(sector=False),
        _mart_frame_sql(sector=True),
        _prev_rsi_sql(),
        _path_features_sql(frozenset({"high_252", "returns"}))[0],
    ]
    for sql in statements:
        assert "%(as_of)s" in sql or "%(prev)s" in sql
        assert "SELECT max(time)" not in sql
        assert "latest_date" not in sql


def test_path_query_only_computes_what_the_profile_reads() -> None:
    """The 52-week high is the expensive one; profiles that ignore it must not pay.

    A 252-row rolling max over 420 days of the whole universe is ~3.0s of the screen's
    runtime, against ~0.5s for the 20/60-day lags. Every profile used to compute it.
    """

    rs_sql, rs_days = _path_features_sql(frozenset({"returns"}))
    assert "high_252" not in rs_sql
    assert rs_days <= 130

    breakout_sql, breakout_days = _path_features_sql(
        frozenset({"high_252", "volume_ratio_20", "returns"})
    )
    assert "high_252" in breakout_sql
    assert "avg_volume_20" in breakout_sql
    assert breakout_days == 420


def test_relative_strength_benchmark_is_the_whole_universe_not_the_filtered_set() -> None:
    """"상대강도" must mean the same thing whatever the query filtered on.

    The benchmark used to be the mean return of the rows the screen had already
    narrowed to. Ask for "반도체 섹터 주도주 중 상대강도 강한 종목" and each chip stock
    was measured against the chip sector's own average - so a sector down 20% while the
    market rose still produced "leaders", because half of any set beats its own mean.
    """

    # A weak sector (-10% each) and a strong rest-of-market (+10% each).
    path = [
        {"ticker": f"{i:06d}", "close": 90.0 if i < 3 else 110.0,
         "close_20d_ago": 100.0, "close_60d_ago": 100.0}
        for i in range(10)
    ]

    strength, benchmark = _relative_strength(path)

    assert benchmark["population"] == "priced_universe_before_sector_filter"
    assert benchmark["constituents"] == 10
    # Market mean is +4% ((3*-10% + 7*+10%)/10), so every weak-sector name is negative.
    assert benchmark["market_return_20d"] == pytest.approx(0.04)
    for i in range(3):
        assert strength[f"{i:06d}"]["20d"] == pytest.approx(-0.14)
    for i in range(3, 10):
        assert strength[f"{i:06d}"]["20d"] == pytest.approx(0.06)


def test_a_stock_without_history_has_no_relative_strength_rather_than_zero_return() -> None:
    """COALESCE(return, 0) handed a newly listed name the negative of the market.

    In a falling market that flipped to a positive excess return and screened the name
    in on the strength of history it does not have.
    """

    path = [
        {"ticker": "000001", "close": 100.0, "close_20d_ago": None, "close_60d_ago": None},
        {"ticker": "000002", "close": 80.0, "close_20d_ago": 100.0, "close_60d_ago": 100.0},
    ]

    strength, _ = _relative_strength(path)

    assert strength["000001"]["20d"] is None
    assert strength["000002"]["20d"] == pytest.approx(0.0)


def test_all_null_rsi_cannot_be_rescued_by_relaxation() -> None:
    """Why the as-of join above matters: widening rsi_max does nothing for NULL rows."""

    rows = [
        {
            "time": date(2026, 8, 3), "ticker": f"{i:06d}", "name": f"종목{i}",
            "market_segment": "KOSPI", "close": Decimal("10000"), "rsi": None,
            "prev_rsi": None, "volume_ratio_20": Decimal("1.0"),
            "relative_strength_20d": Decimal("0"), "relative_strength_60d": Decimal("0"),
            "high_252": Decimal("12000"), "sma20": Decimal("9900"), "sma200": Decimal("9000"),
        }
        for i in range(50)
    ]

    thresholds = ScreeningThresholds()
    for round_index in range(4):
        matcher = _screening_matcher("rsi_rebound", thresholds)
        assert [row for row in rows if matcher(row)] == []
        thresholds = _relaxed_thresholds(thresholds, round_index)

    # rsi_max really was being widened; the rows just cannot match.
    assert thresholds.rsi_max > ScreeningThresholds().rsi_max


def test_missing_capability_stops_before_the_screen_spends_relaxation_rounds() -> None:
    """A strategy whose data is not loaded must fail immediately, not slowly.

    mart.dart_financial_asof is empty on the common server, so every fundamental
    condition matched zero rows. The capability probe ran *after* screening, so the run
    still paid for the full screen plus three LLM relaxation rounds - each widening a
    threshold against columns that were NULL for every row and could never match - and
    then surfaced as "데이터 조회 시간이 초과되었습니다", naming neither the missing data
    nor the fact that waiting could not help.
    """

    connection = FakeScreeningConnection(unavailable_probes=("mart.dart_financial_asof",))

    class ProbingDataSource(PostgresPipelineDataSource):
        def _connect(self):
            return connection

    source = ProbingDataSource(DataSourceConfig(database_dsn="postgresql://example"))

    bundle = source.load("저PER 고ROE 부채비율 100% 이하 종목", "trace-capability")

    assert bundle.metadata["stopped_before_screening"] is True
    labels = [item["label"] for item in bundle.data_availability["unsupported_capabilities"]]
    assert any("재무" in label for label in labels)
    # No screen, and therefore no relaxation rounds, were run at all.
    assert connection.frame_reads == 0
    assert not any("WITH path AS" in query for query, _ in connection.calls)


def test_available_capabilities_do_not_stop_the_screen() -> None:
    connection = FakeScreeningConnection()

    class ProbingDataSource(PostgresPipelineDataSource):
        def _connect(self):
            return connection

    source = ProbingDataSource(DataSourceConfig(database_dsn="postgresql://example"))

    bundle = source.load("코스피 신고가 거래량 종목", "trace-capability-ok")

    assert "stopped_before_screening" not in bundle.metadata
    assert connection.frame_reads >= 1


def test_bollinger_reads_both_warehouse_key_spellings() -> None:
    """The Bollinger keys were renamed mid-pipeline and both spellings are live.

    Bars up to 2026-07-10 are keyed `BBU_20_2.0_2.0`, bars from 2025-08-28
    `BBU_20_2.0`. Reading only the current one left Bollinger populated on 13.5% of
    backtest bars while every other indicator sat at 99.9%, so a band strategy quietly
    stopped matching on older history.
    """

    sql = _mart_frame_sql(sector=False)

    assert "BBU_20_2.0_2.0" in sql
    assert "BBB_20_2.0_2.0" in sql
    assert "COALESCE" in sql
    # Keys that were never renamed must not grow a spurious fallback.
    assert "SMA_20_2.0" not in sql
    assert "RSI_14_2.0" not in sql


def test_legacy_bollinger_keys_flatten_onto_a_bar_under_the_canonical_name() -> None:
    row = {
        "as_of_date": AS_OF, "ticker": "000660",
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
        "trend_values": {}, "momentum_values": {},
        "volatility_values": {"BBU_20_2.0_2.0": 120.0, "BBB_20_2.0_2.0": 16.35},
        "volume_values": {}, "pattern_values": {},
    }

    price_row = _price_row_from_feature_frame_record(row)

    assert price_row["bb_upper"] == 120.0
    # pandas-ta reports bandwidth as a percentage; the thresholds are fractions.
    assert price_row["bb_width"] == pytest.approx(0.1635)


def test_macro_snapshot_labels_the_universe_proxy_rather_than_calling_it_the_kospi() -> None:
    """There is no index series in the warehouse, so the equity leg is a proxy.

    All three risk rules used to default to values no threshold could fire on and
    nothing ever assigned the snapshot, so they were dead while looking implemented.
    """

    from ai_graph.data_sources.db import _latest_universe_return

    rows = [
        {"ticker": "000660", "date": "2026-05-19", "close": 100.0},
        {"ticker": "000660", "date": "2026-05-20", "close": 110.0},
        {"ticker": "005930", "date": "2026-05-19", "close": 100.0},
        {"ticker": "005930", "date": "2026-05-20", "close": 90.0},
    ]

    assert _latest_universe_return(rows) == pytest.approx(0.0)
    assert _latest_universe_return([]) is None


def test_backtest_universe_caps_the_recommended_names_it_folds_in() -> None:
    """A screen that matches everything must not become the backtest universe.

    A query whose wording matches no profile falls to the baseline predicate
    `close > 0`, so every priced name matches - ~2,764 of them. Those were all unioned
    into the "KOSPI 200 plus the recommendations" universe, making it ~2,900 tickers and
    the price history ~3.6M rows, far past the statement budget. That was the reported
    "데이터 조회 시간이 초과되었습니다".
    """

    from ai_graph.data_sources.db import _backtest_ticker_pool

    everything = [
        {"ticker": f"{i:06d}", "relative_strength_20d": i / 1000.0}
        for i in range(2764)
    ]

    pool = _backtest_ticker_pool(everything, 20)

    assert len(pool) == 20
    # The cap keeps the strongest matches, not the lowest ticker codes.
    assert pool[0] == "002763"


def _universe_source():
    from ai_graph.data_sources.db import PostgresPipelineDataSource

    source = PostgresPipelineDataSource.__new__(PostgresPipelineDataSource)
    source.config = SimpleNamespace(backtest_lookback_days=2520)
    return source


def test_backtest_universe_is_ranked_as_of_the_start_not_today() -> None:
    """Today's market cap ranking applied to a ten-year-old start date is survivorship.

    Every name in a present-day top-200 is one that survived to be large today, so the
    strategy is only ever tested on winners. Measured against a universe selected as of
    the start, that overstated the same strategy's ten-year return by 22-44 percentage
    points. The ranking has to be rebuilt from bars that existed at the start.
    """

    conn = FakeScreeningConnection()

    universe, descriptor = _universe_source()._fetch_backtest_universe(conn, [])

    assert universe == ["000660"]
    assert descriptor["selection"] == "traded_value_as_of_backtest_start"
    assert descriptor["source"] == "feature.kis_adjusted_ohlcv_daily"

    ranking_query = next(
        query for query, _ in conn.calls if "WITH bounds AS" in query
    )
    # symbol_master's MKTCAP is a single present-day scalar with no history, so it
    # cannot be evaluated as of an earlier date and must not appear here.
    assert "MKTCAP" not in ranking_query
    assert "symbol_master" not in ranking_query
    # The window has to end at the backtest start, not at today.
    assert "CURRENT_DATE - make_interval(days => %s)" in ranking_query


def test_backtest_universe_clamps_an_as_of_date_that_predates_the_warehouse() -> None:
    """A ten-year lookback resolves to 2015-11 against data that starts 2016-05.

    Left alone that returns nothing and the backtest silently runs on the recommended
    names only. Falling back to today's ranking instead would reintroduce exactly the
    bias this replaces, so the as-of date is clamped forward to the first date with a
    full ranking window behind it.
    """

    conn = FakeScreeningConnection()

    _universe_source()._fetch_backtest_universe(conn, [])

    ranking_query = next(
        query for query, _ in conn.calls if "WITH bounds AS" in query
    )
    assert "GREATEST" in ranking_query
    assert f"SELECT min(time) FROM feature.kis_adjusted_ohlcv_daily" in ranking_query


def test_backtest_universe_unions_recommendations_without_duplicating_them() -> None:
    """A recommended name stays tradable, but never appears twice."""

    source = _universe_source()

    inside, inside_descriptor = source._fetch_backtest_universe(
        FakeScreeningConnection(), ["000660"]
    )
    outside, outside_descriptor = source._fetch_backtest_universe(
        FakeScreeningConnection(), ["999999"]
    )

    assert inside == ["000660"]
    assert inside_descriptor["recommended_unioned"] == 0
    assert outside == ["999999", "000660"]
    assert outside_descriptor["recommended_unioned"] == 1


def test_screening_frame_does_not_read_the_mart_view() -> None:
    """The one-date frame must not go through mart.kis_adjusted_feature_frame_asof.

    The view LEFT JOINs five indicator hypertables to the price table on `ta.time =
    a.time`. Restricting the view to one date restricts only the price side - PostgreSQL
    does not propagate that equality across an outer join to the nullable side - so every
    chunk of every ta_* table is locked before a row is read. Measured against production
    that is 8,582 lock entries for one screen, against a cluster whose entire lock table
    holds 6,400, which is the "out of shared memory" that killed analysis runs. The same
    read built here takes 48.
    """

    for sql in (_mart_frame_sql(sector=False), _mart_frame_sql(sector=True), _prev_rsi_sql()):
        assert "mart.kis_adjusted_feature_frame_asof" not in sql
        assert "mart.symbol_feature_frame_asof" not in sql


def test_every_indicator_table_carries_its_own_date_restriction() -> None:
    """Each ta_* table needs a prunable date qual, and it has to survive planning.

    MATERIALIZED is what makes it survive: an ordinary subquery is pulled up into the
    outer join and its WHERE degrades back into a join qual, which prunes nothing.
    Measured per table, 2,150 lock entries pulled up against 18 when blocked - so a plain
    subquery here would look correct and quietly restore the original failure.
    """

    sql = _mart_frame_sql(sector=False)
    indicator_tables = (
        "feature.ta_trend_ticker_daily",
        "feature.ta_momentum_ticker_daily",
        "feature.ta_volatility_ticker_daily",
        "feature.ta_volume_ticker_daily",
    )
    for table in indicator_tables:
        # ... AS MATERIALIZED ( SELECT ... FROM <table> WHERE time = %(as_of)s::date )
        # The qual is the first thing after the table name, so a short window is enough
        # and does not depend on how the statement is wrapped or indented.
        block = sql.split(table, 1)[1][:80]
        assert "WHERE time = %(as_of)s::date" in block, f"{table} has no prunable date qual"

    assert sql.count("AS MATERIALIZED") == len(indicator_tables) + 1  # + the price bars


def test_screening_date_bound_is_a_plan_time_constant() -> None:
    """CURRENT_DATE is STABLE, so chunks are excluded only after every one is locked.

    The scan reads the same handful of chunks either way, which is why this looked fixed
    when it was measured by runtime. By locks it is 2,142 against 62.
    """

    captured: list[tuple[str, object]] = []

    class RecordingConnection:
        def execute(self, query, params=None):
            captured.append((query, params))
            return FakeResult(row={"as_of_date": AS_OF})

    source = PostgresPipelineDataSource(DataSourceConfig(database_dsn="postgresql://example"))
    resolved = source._resolve_screening_date(RecordingConnection())

    assert resolved == AS_OF
    query, params = captured[0]
    assert "CURRENT_DATE" not in query
    assert "%(floor)s::date" in query
    assert isinstance(params["floor"], date)
