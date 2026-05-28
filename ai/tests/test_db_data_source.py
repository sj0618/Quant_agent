import os
from datetime import date
from decimal import Decimal

import pytest

from ai_graph.data_sources.db import (
    AI_DATABASE_DSN_ENV,
    DataSourceConfig,
    PostgresPipelineDataSource,
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


@pytest.mark.skipif(
    not os.environ.get(AI_DATABASE_DSN_ENV),
    reason=f"{AI_DATABASE_DSN_ENV} is required for common-server DB integration test.",
)
def test_postgres_data_source_loads_common_server_pipeline_inputs() -> None:
    source = PostgresPipelineDataSource(DataSourceConfig.from_env())

    bundle = source.load("005930 RSI가 30 이하인 KOSPI200", "trace-db-live")

    assert bundle.metadata["source"] == "postgres"
    assert bundle.price_rows
    assert bundle.metadata["price_source"] == "mart.kis_adjusted_feature_frame_asof"
    assert bundle.metadata["l4_evidence_source"] == "raw.analyst_report_summary"
