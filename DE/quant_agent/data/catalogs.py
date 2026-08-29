"""Versioned source contracts shared by ingestion jobs and Airflow."""

from __future__ import annotations

from datetime import date
from typing import Any


BOK_RATE_FX_SERIES: tuple[dict[str, str], ...] = (
    {"stat_code": "722Y001", "cycle": "D", "item_code1": "0101000"},
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010101000"},
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010901000"},
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010502000"},
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010190000"},
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010200000"},
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010210000"},
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010300000"},
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010320000"},
    {"stat_code": "731Y003", "cycle": "D", "item_code1": "0000003"},
    {"stat_code": "731Y003", "cycle": "D", "item_code1": "0000006"},
    {"stat_code": "731Y003", "cycle": "D", "item_code1": "0000010"},
)

BOK_MONTHLY_OIL_SERIES: tuple[dict[str, str], ...] = (
    {"stat_code": "902Y003", "cycle": "M", "item_code1": "010101", "language": "en"},
    {"stat_code": "902Y003", "cycle": "M", "item_code1": "010102", "language": "en"},
    {"stat_code": "902Y003", "cycle": "M", "item_code1": "010103", "language": "en"},
)

BOK_SERIES_PRESETS: dict[str, tuple[dict[str, str], ...]] = {
    "rate-fx": BOK_RATE_FX_SERIES,
    "all-macro": (*BOK_RATE_FX_SERIES, *BOK_MONTHLY_OIL_SERIES),
}

BOK_MONTHLY_OIL_SERIES_IDS = frozenset(
    f"{item['stat_code']}:{item['item_code1']}" for item in BOK_MONTHLY_OIL_SERIES
)

DART_REPORT_CODE_PERIOD_END: dict[str, tuple[int, int]] = {
    "11013": (3, 31),
    "11012": (6, 30),
    "11014": (9, 30),
    "11011": (12, 31),
}

# Statutory disclosure deadlines used only as a conservative fallback when the
# statement endpoint does not expose the actual filing receipt date.
DART_REPORT_DISCLOSURE_MONTH_DAY: dict[str, tuple[int, int, int]] = {
    "11013": (0, 5, 15),
    "11012": (0, 8, 14),
    "11014": (0, 11, 14),
    "11011": (1, 3, 31),
}


def dart_conservative_available_from(business_year: int, report_code: str) -> date:
    """Return the latest statutory disclosure deadline for a report period."""

    year_offset, month, day = DART_REPORT_DISCLOSURE_MONTH_DAY[report_code]
    return date(business_year + year_offset, month, day)


def bok_series_id(item: dict[str, Any]) -> str:
    return f"{item['stat_code']}:{item['item_code1']}"
