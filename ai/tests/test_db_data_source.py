import os
from datetime import date
from decimal import Decimal

import pytest

from ai_graph.data_sources.db import (
    AI_DATABASE_DSN_ENV,
    DEFAULT_BACKTEST_LOOKBACK_DAYS,
    DataSourceConfig,
    PostgresPipelineDataSource,
    RSI_OVERSOLD_THRESHOLD,
    _price_row_from_feature_frame_record,
    load_pipeline_data_from_env,
)


def test_pipeline_data_source_uses_fixture_boundary_without_dsn(monkeypatch) -> None:
    monkeypatch.delenv(AI_DATABASE_DSN_ENV, raising=False)

    bundle = load_pipeline_data_from_env("RSI가 30 이하인 KOSPI200", "trace-db")

    assert bundle.price_rows == []
    assert bundle.l4_evidence == []
    assert bundle.metadata["source"] == "fixture"
    assert "mart.kis_adjusted_feature_frame_asof" in bundle.metadata["available_db_objects"]


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
