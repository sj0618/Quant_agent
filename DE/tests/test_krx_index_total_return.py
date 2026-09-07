"""Normalization and weight arithmetic for the official KRX TR benchmark inputs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.sources.base import SourceResponseError  # noqa: E402
from quant_agent.data.sources.krx_index import (  # noqa: E402
    INDEX_CODE_TO_KIS_SECTOR,
    MARKET_CAP_WEIGHT_BASIS,
    benchmark_weight_rows,
    normalize_ecos_market_caps,
    normalize_index_total_return,
)


def _chart_payload(rows: list[dict[str, str]]) -> dict:
    return {"rt_cd": "0", "output1": {"hts_kor_isnm": "코스피 TR"}, "output2": rows}


def test_contract_index_codes_are_total_return_only() -> None:
    # A price-return code here would silently lower the bar the acceptance gate uses.
    assert set(INDEX_CODE_TO_KIS_SECTOR) == {"KOSPI_TR", "KOSDAQ_TR"}


def test_normalize_orders_ascending_and_keeps_positive_levels() -> None:
    payload = _chart_payload(
        [
            {"stck_bsop_date": "20260904", "bstp_nmix_prpr": "8780.64"},
            {"stck_bsop_date": "20260903", "bstp_nmix_prpr": "8,640.12"},
            {"stck_bsop_date": "20260902", "bstp_nmix_prpr": "8600.00"},
        ]
    )
    rows = normalize_index_total_return(payload, index_code="KOSPI_TR")
    assert [row["trade_date"] for row in rows] == [
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    ]
    assert rows[1]["tr_value"] == Decimal("8640.12")
    assert {row["index_code"] for row in rows} == {"KOSPI_TR"}


@pytest.mark.parametrize("level", ["0", "-1", "", "-", "nan"])
def test_normalize_drops_non_positive_levels(level: str) -> None:
    payload = _chart_payload([{"stck_bsop_date": "20260904", "bstp_nmix_prpr": level}])
    assert normalize_index_total_return(payload, index_code="KOSPI_TR") == []


def test_normalize_clips_to_requested_window_and_ignores_junk_dates() -> None:
    payload = _chart_payload(
        [
            {"stck_bsop_date": "20260904", "bstp_nmix_prpr": "100"},
            {"stck_bsop_date": "20260101", "bstp_nmix_prpr": "90"},
            {"stck_bsop_date": "", "bstp_nmix_prpr": "80"},
            {"stck_bsop_date": "20260230", "bstp_nmix_prpr": "70"},
        ]
    )
    rows = normalize_index_total_return(
        payload,
        index_code="KOSDAQ_TR",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 9, 4),
    )
    assert [row["trade_date"] for row in rows] == [date(2026, 9, 4)]


def test_normalize_rejects_a_payload_without_rows() -> None:
    with pytest.raises(SourceResponseError):
        normalize_index_total_return({"rt_cd": "0"}, index_code="KOSPI_TR")


def test_normalize_ecos_market_caps_keeps_only_usable_monthly_observations() -> None:
    payload = {
        "StatisticSearch": {
            "row": [
                {"TIME": "202606", "DATA_VALUE": "5581868000"},
                {"TIME": "202607", "DATA_VALUE": "5,600,000,000"},
                {"TIME": "202608", "DATA_VALUE": ""},
                {"TIME": "2026", "DATA_VALUE": "1"},
            ]
        }
    }
    observations = normalize_ecos_market_caps(payload, market="KOSPI")
    assert set(observations) == {"202606", "202607"}
    assert observations["202607"] == Decimal("5600000000")


def test_normalize_ecos_market_caps_treats_no_data_as_empty_not_an_error() -> None:
    assert normalize_ecos_market_caps({"RESULT": {"CODE": "INFO-200"}}, market="KOSDAQ") == {}
    with pytest.raises(SourceResponseError):
        normalize_ecos_market_caps({"RESULT": {"CODE": "ERROR-100"}}, market="KOSDAQ")


def test_weight_rows_are_first_of_month_positive_and_sum_to_one() -> None:
    rows = benchmark_weight_rows(
        {"201604": Decimal("1290000"), "202607": Decimal("5600000")},
        {"201604": Decimal("210000"), "202607": Decimal("410000")},
    )
    assert [row["month"] for row in rows] == [date(2016, 4, 1), date(2026, 7, 1)]
    for row in rows:
        assert row["month"].day == 1
        assert row["kospi_weight"] > 0
        assert row["kosdaq_weight"] > 0
        # The warehouse CHECK constraint allows 1e-6 of slack; the pair is derived from
        # a single ratio, so it must be exact.
        assert row["kospi_weight"] + row["kosdaq_weight"] == Decimal(1)
        assert row["basis"] == MARKET_CAP_WEIGHT_BASIS
    assert rows[0]["kospi_weight"] == Decimal("1290000") / Decimal("1500000")


def test_weight_rows_need_both_markets_and_a_positive_total() -> None:
    assert benchmark_weight_rows({"202607": Decimal(1)}, {"202606": Decimal(1)}) == []
    assert benchmark_weight_rows({"202607": Decimal(0)}, {"202607": Decimal(0)}) == []


def test_weight_rows_record_a_substituted_basis() -> None:
    rows = benchmark_weight_rows(
        {"202608": Decimal(9)}, {"202608": Decimal(1)}, basis="warehouse_estimate"
    )
    assert rows[0]["basis"] == "warehouse_estimate"
    assert rows[0]["kospi_weight"] == Decimal("0.9")
