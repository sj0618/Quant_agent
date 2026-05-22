"""Data quality helpers for source pilot and OHLCV ingestion."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from quant_agent.data.models import OhlcvBar


def coverage_ratio(observed_dates: Iterable[date], expected_dates: Iterable[date]) -> float:
    expected = set(expected_dates)
    if not expected:
        return 0.0
    observed = set(observed_dates)
    return len(observed & expected) / len(expected)


def has_non_positive_price(bar: OhlcvBar) -> bool:
    prices = (bar.open, bar.high, bar.low, bar.close)
    return any(price is not None and price <= Decimal("0") for price in prices)


def has_ohlc_order_issue(bar: OhlcvBar) -> bool:
    if None in (bar.open, bar.high, bar.low, bar.close):
        return True
    assert bar.open is not None
    assert bar.high is not None
    assert bar.low is not None
    assert bar.close is not None
    return not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high)


def duplicate_keys(bars: Iterable[OhlcvBar]) -> set[tuple[str, date]]:
    seen: set[tuple[str, date]] = set()
    duplicates: set[tuple[str, date]] = set()
    for bar in bars:
        key = (bar.symbol, bar.trade_date)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return duplicates


def summarize_ohlcv_quality(bars: list[OhlcvBar]) -> dict[str, int]:
    return {
        "rows": len(bars),
        "non_positive_price_rows": sum(1 for bar in bars if has_non_positive_price(bar)),
        "ohlc_order_issue_rows": sum(1 for bar in bars if has_ohlc_order_issue(bar)),
        "duplicate_key_rows": len(duplicate_keys(bars)),
    }


def ohlcv_quality_flags(bar: OhlcvBar) -> dict[str, bool]:
    flags = {
        "missing_ohlc": None in (bar.open, bar.high, bar.low, bar.close),
        "non_positive_price": has_non_positive_price(bar),
        "ohlc_order_issue": has_ohlc_order_issue(bar),
        "non_positive_volume": bar.volume is not None and bar.volume <= Decimal("0"),
    }
    return {key: value for key, value in flags.items() if value}


def is_tradable_ohlcv(bar: OhlcvBar) -> bool:
    flags = ohlcv_quality_flags(bar)
    blocking_flags = {"missing_ohlc", "non_positive_price", "ohlc_order_issue"}
    return not any(flags.get(flag, False) for flag in blocking_flags)
