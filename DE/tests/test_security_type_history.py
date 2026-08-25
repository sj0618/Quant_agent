from datetime import date
from decimal import Decimal
from uuid import uuid4

from quant_agent.data.models import OhlcvBar
from quant_agent.data.repository import DataRepository, _security_type_history_metadata


class _CaptureExecutor:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def execute_script(self, script: str) -> None:
        self.scripts.append(script)


def _bar(raw: dict[str, str], *, trade_date: date = date(2024, 1, 2)) -> OhlcvBar:
    return OhlcvBar(
        source="KRX",
        symbol="000001",
        trade_date=trade_date,
        open=Decimal(100),
        high=Decimal(101),
        low=Decimal(99),
        close=Decimal(100),
        volume=Decimal(1000),
        name="Historical Corp",
        raw=raw,
    )


def test_security_type_history_requires_an_explicit_source_classification() -> None:
    assert _security_type_history_metadata({"MKT_NM": "KOSPI"}) is None
    assert _security_type_history_metadata({"SECUGRP_NM": "주권"}) == {
        "classification_evidence": {"SECUGRP_NM": "주권"}
    }


def test_ingestion_does_not_backfill_historical_security_type_from_current_market() -> None:
    executor = _CaptureExecutor()
    repository = DataRepository(executor=executor)

    repository.upsert_ohlcv_bars([_bar({"MKT_NM": "KOSPI"})], uuid4(), "KRX")

    assert len(executor.scripts) == 1
    assert "core.symbol_security_type_history" not in executor.scripts[0]


def test_ingestion_records_explicit_source_classification_as_an_asof_interval() -> None:
    executor = _CaptureExecutor()
    repository = DataRepository(executor=executor)

    repository.upsert_ohlcv_bars(
        [_bar({"MKT_NM": "KOSPI", "SECUGRP_NM": "주권"})],
        uuid4(),
        "KRX",
    )

    script = executor.scripts[0]
    assert "INSERT INTO core.symbol_security_type_history" in script
    assert "classification_evidence" in script
    assert "security-type-source-payload-v1" in script
    assert "core.symbol_master.security_type" not in script[
        script.index("INSERT INTO core.symbol_security_type_history") :
    ]


def test_ingestion_preserves_each_symbol_date_source_classification_transition() -> None:
    executor = _CaptureExecutor()
    repository = DataRepository(executor=executor)

    repository.upsert_ohlcv_bars(
        [
            _bar(
                {"MKT_NM": "KOSPI", "SECUGRP_NM": "주권"},
                trade_date=date(2024, 1, 2),
            ),
            _bar(
                {"MKT_NM": "KOSPI", "SECUGRP_NM": "상장지수펀드"},
                trade_date=date(2024, 1, 3),
            ),
        ],
        uuid4(),
        "KRX",
    )

    script = executor.scripts[0]
    history_sql = script[script.index("WITH incoming(symbol, valid_from, security_type") :]
    assert "'2024-01-02'" in history_sql
    assert "'2024-01-03'" in history_sql
    assert "'보통주'" in history_sql
    assert "'ETF'" in history_sql
    assert "LEAD(valid_from) OVER" in history_sql
