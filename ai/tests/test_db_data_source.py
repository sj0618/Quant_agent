import os
from datetime import date
from decimal import Decimal

import pytest

from ai_graph.data_sources.db import (
    AI_REQUIRE_LIVE_DATA_ENV,
    AI_DATABASE_DSN_ENV,
    DATABASE_URL_ENV,
    DEFAULT_BACKTEST_LOOKBACK_DAYS,
    DataSourceConfig,
    PostgresPipelineDataSource,
    QUANT_DB_DSN_ENV,
    RSI_OVERSOLD_THRESHOLD,
    _price_row_from_feature_frame_record,
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


def test_pipeline_data_source_rejects_missing_dsn_in_live_mode(monkeypatch) -> None:
    monkeypatch.delenv(AI_DATABASE_DSN_ENV, raising=False)
    monkeypatch.delenv(QUANT_DB_DSN_ENV, raising=False)
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    monkeypatch.setenv(AI_REQUIRE_LIVE_DATA_ENV, "1")

    with pytest.raises(RuntimeError, match="requires a configured PostgreSQL DSN"):
        load_pipeline_data_from_env("RSI가 30 이하인 KOSPI200", "trace-live")


def test_data_source_config_uses_quant_db_dsn_alias() -> None:
    config = DataSourceConfig.from_env({QUANT_DB_DSN_ENV: "postgresql://example"})

    assert config.database_dsn == "postgresql://example"
    assert config.database_dsn_env == QUANT_DB_DSN_ENV


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
                        "listing_status": "LISTED",
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
            if "FROM scored" in query:
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
                            "technical_score": Decimal("7"),
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
                        "listing_status": "LISTED",
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
            if "DISTINCT sector" in query:
                return Result(rows=[{"sector": "반도체"}, {"sector": "화학"}])
            if "FROM scored" in query:
                assert "AND u.sector = %s" in query
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
                            "technical_score": Decimal("7"),
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
                        "listing_status": "LISTED",
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
            if "DISTINCT sector" in query:
                return Result(rows=[{"sector": "반도체"}, {"sector": "화학"}])
            if "FROM scored" in query:
                assert "AND u.sector = %s" not in query
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
                            "technical_score": Decimal("7"),
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
                        "listing_status": "LISTED",
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
            if "FROM scored" in query:
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
                            "technical_score": Decimal("7"),
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
    not os.environ.get(AI_DATABASE_DSN_ENV),
    reason=f"{AI_DATABASE_DSN_ENV} is required for common-server DB integration test.",
)
def test_postgres_data_source_loads_common_server_pipeline_inputs() -> None:
    source = PostgresPipelineDataSource(DataSourceConfig.from_env())

    bundle = source.load("005930 RSI가 30 이하인 KOSPI200", "trace-db-live")

    assert bundle.metadata["source"] == "postgres"
    assert bundle.price_rows
    assert bundle.metadata["price_source"] == "feature.kis_adjusted_ohlcv_daily"
    assert bundle.metadata["indicator_sources"] == ["feature.ta_momentum_ticker_daily"]
    assert bundle.metadata["l4_evidence_source"] == "raw.analyst_report_summary"
    assert bundle.metadata["backtest_lookback_days"] >= DEFAULT_BACKTEST_LOOKBACK_DAYS
    assert any(row.get("rsi", 100) <= RSI_OVERSOLD_THRESHOLD for row in bundle.price_rows)
