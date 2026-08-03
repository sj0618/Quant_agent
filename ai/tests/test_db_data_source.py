import os
from datetime import date
from decimal import Decimal

import pytest

from ai_graph.data_sources.db import (
    AI_DATABASE_DSN_ENV,
    DATABASE_URL_ENV,
    DEFAULT_BACKTEST_LOOKBACK_DAYS,
    DataSourceConfig,
    PostgresPipelineDataSource,
    QUANT_DB_DSN_ENV,
    RSI_OVERSOLD_THRESHOLD,
    SCREENING_BASELINE_PROFILE,
    ScreeningThresholds,
    _price_row_from_feature_frame_record,
    _relaxed_thresholds,
    _screening_matcher,
    _screening_sql,
    load_pipeline_data_from_env,
    resolve_database_dsn_from_env,
)
from ai_graph.data_sources.sectors import clear_sector_cache


def setup_function() -> None:
    clear_sector_cache()


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
                            # Momentum is now fetched for the whole backtest pool at once,
                            # so rows carry the ticker they belong to.
                            "base_ticker": "005930",
                            "time": date(2026, 5, 20),
                            "values_jsonb": {"RSI_14": Decimal("28.5")},
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
    assert bundle.metadata["timings"]["total_seconds"] >= 0
    assert bundle.metadata["timings"]["price_rows_seconds"] >= 0
    assert source.conn.calls[0] == (
        "SELECT set_config('statement_timeout', %s, true)",
        ["12345ms"],
    )
    price_query = next(
        query for query, _ in source.conn.calls if "PARTITION BY ticker" in query
    )
    assert "ORDER BY as_of_date, ticker" in price_query


def test_postgres_data_source_broad_screening_uses_screening_candidates() -> None:
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

    class ScreeningConnection:
        def __enter__(self) -> "ScreeningConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: str, params: list[object] | None = None) -> Result:
            if "FROM matched" in query:
                # Universe membership must come from actual OHLCV presence, not the
                # (currently broken upstream) meta.view_common_stock_universe view.
                assert "meta.view_common_stock_universe" not in query
                assert "technical_score" not in query
                assert "LEFT JOIN core.symbol_master sm" in query
                assert "sm.sector" in query
                return Result(
                    rows=[
                        {
                            "time": date(2026, 5, 20),
                            "ticker": "000660",
                            "name": "SK하이닉스",
                            "market_segment": "KOSPI",
                            "close": Decimal("200000"),
                            "volume_ratio_20": Decimal("1.8"),
                            "relative_strength_20d": Decimal("0.05"),
                            "relative_strength_60d": Decimal("0.1"),
                            "high_252": Decimal("200000"),
                            "sma20": Decimal("180000"),
                            "sma200": Decimal("150000"),
                        }
                    ]
                )
            if "feature.kis_adjusted_ohlcv_daily" in query:
                return Result(
                    rows=[
                        {
                            "as_of_date": date(2026, 5, 20),
                            "ticker": "000660",
                            "open": Decimal("190000"),
                            "high": Decimal("201000"),
                            "low": Decimal("189000"),
                            "close": Decimal("200000"),
                            "volume": Decimal("1000000"),
                        }
                    ]
                )
            if "feature.ta_momentum_ticker_daily" in query:
                return Result(rows=[])
            if "raw.analyst_report_summary" in query:
                return Result(rows=[])
            if "meta.view_common_stock_universe" in query:
                return Result(
                    row={
                        "symbol": "000660",
                        "name": "SK하이닉스",
                        "market_segment": "KOSPI",
                        "listing_status": "listed",
                    }
                )
            if "mart.bok_macro_asof" in query:
                return Result(row={"row_count": 0, "latest_effective_date": None})
            return Result()

    class ScreeningDataSource(PostgresPipelineDataSource):
        def _connect(self) -> ScreeningConnection:
            return ScreeningConnection()

    source = ScreeningDataSource(DataSourceConfig(database_dsn="postgresql://example"))

    bundle = source.load("최근 52주 신고가 거래량 150% 종목을 찾아줘", "trace-screening")

    assert bundle.metadata["ticker"] == "000660"
    assert bundle.screening_candidates[0]["ticker"] == "000660"
    assert "거래량 20일 평균 대비 150% 이상" in bundle.screening_candidates[0]["matched_rules"]
    assert bundle.data_availability["price_ta"] == "available"


def test_profile_screening_recovers_when_dynamic_sector_view_is_missing(monkeypatch) -> None:
    class Result:
        def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
            self.rows = rows or []

        def fetchall(self) -> list[dict[str, object]]:
            return self.rows

    class MissingSectorViewConnection:
        def __init__(self) -> None:
            self.aborted = False
            self.rollbacks = 0
            self.calls: list[str] = []

        def rollback(self) -> None:
            self.rollbacks += 1
            self.aborted = False

        def execute(
            self, query: str, params: list[object] | None = None
        ) -> Result:
            self.calls.append(query)
            if "FROM mart.common_stock_universe_asof u" in query:
                self.aborted = True
                raise RuntimeError('relation "mart.common_stock_universe_asof" does not exist')
            if self.aborted:
                raise RuntimeError("current transaction is aborted")
            if "set_config('statement_timeout'" in query:
                return Result()
            return Result(
                rows=[
                    {
                        "time": date(2026, 5, 20),
                        "ticker": "000660",
                        "name": "SK하이닉스",
                        "market_segment": "KOSPI",
                        "sector": "반도체",
                        "close": Decimal("200000"),
                        "volume_ratio_20": Decimal("1.8"),
                        "relative_strength_20d": Decimal("0.05"),
                        "relative_strength_60d": Decimal("0.1"),
                        "high_252": Decimal("200000"),
                        "sma20": Decimal("180000"),
                        "sma200": Decimal("150000"),
                    }
                ]
            )

    source = PostgresPipelineDataSource(DataSourceConfig(database_dsn="postgresql://example"))
    conn = MissingSectorViewConnection()
    monkeypatch.setattr(source, "_screen_via_llm", lambda _conn, _query: None)

    candidates, trace = source._screen_with_relaxation(
        conn, "최근 52주 신고가 거래량 종목을 찾아줘"
    )

    assert conn.rollbacks == 1
    assert any("set_config('statement_timeout'" in query for query in conn.calls)
    assert candidates[0]["ticker"] == "000660"
    assert trace["matched_count"] == 1


def test_postgres_data_source_filters_screening_by_sector() -> None:
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

    class SectorScreeningConnection:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[object] | None]] = []

        def __enter__(self) -> "SectorScreeningConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: str, params: list[object] | None = None) -> Result:
            self.calls.append((query, params))
            if "DISTINCT sm.sector" in query:
                return Result(rows=[{"sector": "반도체"}, {"sector": "화학"}])
            if "FROM matched" in query:
                assert "AND sm.sector = %s" in query
                # No universe cap by default: only the sector filter param, no LIMIT.
                assert params == ["반도체"]
                assert "LIMIT" not in query
                return Result(
                    rows=[
                        {
                            "time": date(2026, 5, 20),
                            "ticker": "000660",
                            "name": "SK하이닉스",
                            "market_segment": "KOSPI",
                            "sector": "반도체",
                            "close": Decimal("200000"),
                            "volume_ratio_20": Decimal("1.8"),
                            "relative_strength_20d": Decimal("0.05"),
                            "relative_strength_60d": Decimal("0.1"),
                            "high_252": Decimal("200000"),
                            "sma20": Decimal("180000"),
                            "sma200": Decimal("150000"),
                            # This query screens the rsi_rebound profile, so the row has to
                            # carry an oversold rsi to be a candidate at all - a NULL rsi
                            # would be filtered out by the profile's own predicate.
                            "rsi": Decimal("28"),
                            "prev_rsi": Decimal("25"),
                        }
                    ]
                )
            if "feature.kis_adjusted_ohlcv_daily" in query:
                return Result(
                    rows=[
                        {
                            "as_of_date": date(2026, 5, 20),
                            "ticker": "000660",
                            "open": Decimal("190000"),
                            "high": Decimal("201000"),
                            "low": Decimal("189000"),
                            "close": Decimal("200000"),
                            "volume": Decimal("1000000"),
                        }
                    ]
                )
            if "feature.ta_momentum_ticker_daily" in query:
                return Result(rows=[])
            if "raw.analyst_report_summary" in query:
                return Result(rows=[])
            if "meta.view_common_stock_universe" in query:
                return Result(
                    row={
                        "symbol": "000660",
                        "name": "SK하이닉스",
                        "market_segment": "KOSPI",
                        "listing_status": "listed",
                    }
                )
            if "mart.bok_macro_asof" in query:
                return Result(row={"row_count": 0, "latest_effective_date": None})
            return Result()

    class SectorScreeningDataSource(PostgresPipelineDataSource):
        def _connect(self) -> SectorScreeningConnection:
            return SectorScreeningConnection()

    source = SectorScreeningDataSource(DataSourceConfig(database_dsn="postgresql://example"))

    bundle = source.load("반도체 섹터에서 RSI 과매도 종목을 찾아줘", "trace-sector-screening")

    assert bundle.screening_candidates[0]["ticker"] == "000660"
    assert bundle.screening_candidates[0]["sector"] == "반도체"


def test_postgres_data_source_screening_without_sector_has_no_sector_predicate() -> None:
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

    class NoSectorScreeningConnection:
        def __enter__(self) -> "NoSectorScreeningConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: str, params: list[object] | None = None) -> Result:
            if "DISTINCT sm.sector" in query:
                return Result(rows=[{"sector": "반도체"}, {"sector": "화학"}])
            if "FROM matched" in query:
                assert "AND sm.sector = %s" not in query
                # No universe cap by default: no sector predicate and no LIMIT param.
                assert params == []
                assert "LIMIT" not in query
                return Result(
                    rows=[
                        {
                            "time": date(2026, 5, 20),
                            "ticker": "000660",
                            "name": "SK하이닉스",
                            "market_segment": "KOSPI",
                            "sector": "반도체",
                            "close": Decimal("200000"),
                            "volume_ratio_20": Decimal("1.8"),
                            "relative_strength_20d": Decimal("0.05"),
                            "relative_strength_60d": Decimal("0.1"),
                            "high_252": Decimal("200000"),
                            "sma20": Decimal("180000"),
                            "sma200": Decimal("150000"),
                        }
                    ]
                )
            if "feature.kis_adjusted_ohlcv_daily" in query:
                return Result(
                    rows=[
                        {
                            "as_of_date": date(2026, 5, 20),
                            "ticker": "000660",
                            "open": Decimal("190000"),
                            "high": Decimal("201000"),
                            "low": Decimal("189000"),
                            "close": Decimal("200000"),
                            "volume": Decimal("1000000"),
                        }
                    ]
                )
            if "feature.ta_momentum_ticker_daily" in query:
                return Result(rows=[])
            if "raw.analyst_report_summary" in query:
                return Result(rows=[])
            if "meta.view_common_stock_universe" in query:
                return Result(
                    row={
                        "symbol": "000660",
                        "name": "SK하이닉스",
                        "market_segment": "KOSPI",
                        "listing_status": "listed",
                    }
                )
            if "mart.bok_macro_asof" in query:
                return Result(row={"row_count": 0, "latest_effective_date": None})
            return Result()

    class NoSectorScreeningDataSource(PostgresPipelineDataSource):
        def _connect(self) -> NoSectorScreeningConnection:
            return NoSectorScreeningConnection()

    source = NoSectorScreeningDataSource(DataSourceConfig(database_dsn="postgresql://example"))

    bundle = source.load("최근 52주 신고가 거래량 150% 종목을 찾아줘", "trace-no-sector-screening")

    assert bundle.screening_candidates[0]["ticker"] == "000660"
    assert bundle.screening_candidates[0]["sector"] == "반도체"


def test_postgres_data_source_ambiguous_query_falls_back_to_screening_not_default_ticker() -> None:
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

    class AmbiguousConnection:
        def __enter__(self) -> "AmbiguousConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: str, params: list[object] | None = None) -> Result:
            if "FROM matched" in query:
                return Result(
                    rows=[
                        {
                            "time": date(2026, 5, 20),
                            "ticker": "000660",
                            "name": "SK하이닉스",
                            "market_segment": "KOSPI",
                            "close": Decimal("200000"),
                            "volume_ratio_20": Decimal("1.8"),
                            "relative_strength_20d": Decimal("0.05"),
                            "relative_strength_60d": Decimal("0.1"),
                            "high_252": Decimal("200000"),
                            "sma20": Decimal("180000"),
                            "sma200": Decimal("150000"),
                        }
                    ]
                )
            if "feature.kis_adjusted_ohlcv_daily" in query:
                return Result(
                    rows=[
                        {
                            "as_of_date": date(2026, 5, 20),
                            "ticker": "000660",
                            "open": Decimal("190000"),
                            "high": Decimal("201000"),
                            "low": Decimal("189000"),
                            "close": Decimal("200000"),
                            "volume": Decimal("1000000"),
                        }
                    ]
                )
            if "feature.ta_momentum_ticker_daily" in query:
                return Result(rows=[])
            if "raw.analyst_report_summary" in query:
                return Result(rows=[])
            if "meta.view_common_stock_universe" in query:
                # No explicit ticker/name in the query text, so name-matching
                # over the universe listing finds nothing either.
                return Result(
                    rows=[
                        {"symbol": "000660", "name": "SK하이닉스"},
                    ]
                )
            if "mart.bok_macro_asof" in query:
                return Result(row={"row_count": 0, "latest_effective_date": None})
            return Result()

    class AmbiguousDataSource(PostgresPipelineDataSource):
        def _connect(self) -> AmbiguousConnection:
            return AmbiguousConnection()

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
def test_postgres_screening_sql_plans_against_common_server() -> None:
    source = PostgresPipelineDataSource(DataSourceConfig.from_env())

    with source._connect() as conn:
        source._set_statement_timeout(conn)
        plan = conn.execute(f"EXPLAIN {_screening_sql('technical_proxy')}").fetchall()

    assert plan


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

        def execute(self, query: str, params: list[object] | None = None) -> Result:
            if "FROM matched" in query:
                self.baseline_screens += 1
            return Result([])

    class EmptyScreenDataSource(PostgresPipelineDataSource):
        def _connect(self) -> CountingConnection:
            return connection

        def _fetch_backtest_universe(
            self, _conn: object, recommended: list[str]
        ) -> list[str]:
            assert recommended == []
            return ["000660"]

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


def test_screening_joins_momentum_as_of_not_on_an_exact_date_match() -> None:
    """RSI must survive the TA feature table lagging the price table by a day.

    `as_of_date` is max(time) from feature.kis_adjusted_ohlcv_daily, but RSI comes from
    feature.ta_momentum_ticker_daily, which a *different* DE task populates. Joining the
    two on exact date equality meant one late TA run left every rsi NULL - and an
    all-NULL rsi is the single screen no relaxation round can rescue, because the
    rsi_rebound predicate rejects a NULL row no matter how far rsi_max is widened. The
    run then dies with "no screening candidates".
    """

    sql = _screening_sql(SCREENING_BASELINE_PROFILE, sector=None)

    assert "momentum_as_of AS" in sql
    assert "LEFT JOIN momentum_as_of mwp" in sql
    assert "mwp.ticker = f.ticker AND mwp.time = f.time" not in sql
    # Bounded, so a genuinely dead feed screens as missing instead of quietly
    # trading a month-old RSI.
    assert "INTERVAL '7 days'" in sql


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
