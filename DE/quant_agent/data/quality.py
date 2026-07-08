"""Data quality helpers and rule framework for OHLCV pipelines."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from statistics import median

from quant_agent.data.models import DataQualityIssue, OhlcvBar


DEFAULT_STALE_PRICE_DAYS = 5
DEFAULT_VOLUME_ANOMALY_MULTIPLIER = Decimal("10")
DEFAULT_MIN_VOLUME_SAMPLE_COUNT = 5
DEFAULT_PRICE_MISMATCH_TOLERANCE_RATIO = Decimal("0.03")


@dataclass(frozen=True)
class OhlcvQualityConfig:
    stale_price_days: int = DEFAULT_STALE_PRICE_DAYS
    volume_anomaly_multiplier: Decimal = DEFAULT_VOLUME_ANOMALY_MULTIPLIER
    min_volume_sample_count: int = DEFAULT_MIN_VOLUME_SAMPLE_COUNT
    price_mismatch_tolerance_ratio: Decimal = DEFAULT_PRICE_MISMATCH_TOLERANCE_RATIO

    def __post_init__(self) -> None:
        if self.stale_price_days < 2:
            raise ValueError("stale_price_days must be >= 2.")
        if self.volume_anomaly_multiplier <= Decimal("1"):
            raise ValueError("volume_anomaly_multiplier must be > 1.")
        if self.min_volume_sample_count < 1:
            raise ValueError("min_volume_sample_count must be >= 1.")
        if self.price_mismatch_tolerance_ratio < Decimal("0"):
            raise ValueError("price_mismatch_tolerance_ratio must be >= 0.")


class OhlcvQualityFramework:
    """Composable OHLCV quality framework shared by in-memory tests and SQL QA jobs."""

    def __init__(self, config: OhlcvQualityConfig | None = None) -> None:
        self.config = config or OhlcvQualityConfig()

    def validate_symbol_dates(self, bars: Iterable[OhlcvBar], expected_dates: Iterable[date]) -> list[DataQualityIssue]:
        expected = set(expected_dates)
        observed_by_symbol: dict[str, set[date]] = {}
        for bar in bars:
            observed_by_symbol.setdefault(bar.symbol, set()).add(bar.trade_date)

        issues: list[DataQualityIssue] = []
        for symbol, observed in sorted(observed_by_symbol.items()):
            for missing_date in sorted(expected - observed):
                issues.append(
                    DataQualityIssue(
                        dataset="core.ohlcv_daily",
                        severity="warning",
                        rule_code="MISSING_SYMBOL_DATE",
                        message="Expected trading date is missing for symbol.",
                        symbol=symbol,
                        trade_date=missing_date,
                    )
                )
        return issues

    def detect_stale_prices(self, bars: Iterable[OhlcvBar]) -> list[DataQualityIssue]:
        grouped = _bars_by_symbol(bars)
        issues: list[DataQualityIssue] = []
        for symbol, symbol_bars in sorted(grouped.items()):
            previous_close: Decimal | None = None
            run_length = 0
            for bar in sorted(symbol_bars, key=lambda item: item.trade_date):
                if bar.close is not None and bar.close == previous_close:
                    run_length += 1
                else:
                    run_length = 1
                previous_close = bar.close
                if bar.close is not None and run_length >= self.config.stale_price_days:
                    issues.append(
                        DataQualityIssue(
                            dataset="core.ohlcv_daily",
                            severity="warning",
                            rule_code="STALE_PRICE",
                            message=f"Close price unchanged for {run_length} consecutive observations.",
                            symbol=symbol,
                            trade_date=bar.trade_date,
                        )
                    )
        return issues

    def detect_volume_anomalies(self, bars: Iterable[OhlcvBar]) -> list[DataQualityIssue]:
        grouped = _bars_by_symbol(bars)
        issues: list[DataQualityIssue] = []
        for symbol, symbol_bars in sorted(grouped.items()):
            positive_volumes = [bar.volume for bar in symbol_bars if bar.volume is not None and bar.volume > 0]
            if len(positive_volumes) < self.config.min_volume_sample_count:
                continue
            baseline = Decimal(str(median(positive_volumes)))
            if baseline <= 0:
                continue
            high_threshold = baseline * self.config.volume_anomaly_multiplier
            low_threshold = baseline / self.config.volume_anomaly_multiplier
            for bar in sorted(symbol_bars, key=lambda item: item.trade_date):
                if bar.volume is None or bar.volume <= 0:
                    continue
                if bar.volume >= high_threshold:
                    issues.append(
                        DataQualityIssue(
                            dataset="core.ohlcv_daily",
                            severity="warning",
                            rule_code="HIGH_VOLUME_ANOMALY",
                            message=f"Volume {bar.volume} is above anomaly threshold {high_threshold}.",
                            symbol=symbol,
                            trade_date=bar.trade_date,
                        )
                    )
                elif bar.volume <= low_threshold:
                    issues.append(
                        DataQualityIssue(
                            dataset="core.ohlcv_daily",
                            severity="warning",
                            rule_code="LOW_VOLUME_ANOMALY",
                            message=f"Volume {bar.volume} is below anomaly threshold {low_threshold}.",
                            symbol=symbol,
                            trade_date=bar.trade_date,
                        )
                    )
        return issues

    def compare_kis_krx_rows(
        self,
        *,
        kis_rows: Iterable[dict[str, object]],
        krx_rows: Iterable[dict[str, object]],
    ) -> list[DataQualityIssue]:
        kis_by_key = {_row_key(row, symbol_keys=("ticker", "symbol"), date_keys=("time", "trade_date")): row for row in kis_rows}
        krx_by_key = {_row_key(row, symbol_keys=("symbol", "ticker"), date_keys=("trade_date", "time")): row for row in krx_rows}
        issues: list[DataQualityIssue] = []
        for key in sorted(set(kis_by_key) | set(krx_by_key)):
            symbol, trade_date = key
            kis_row = kis_by_key.get(key)
            krx_row = krx_by_key.get(key)
            if kis_row is None:
                issues.append(
                    DataQualityIssue(
                        dataset="feature.kis_adjusted_ohlcv_daily",
                        severity="warning",
                        rule_code="KRX_MISSING_KIS_ADJUSTED",
                        message="KRX row has no KIS adjusted counterpart.",
                        symbol=symbol,
                        trade_date=trade_date,
                    )
                )
                continue
            if krx_row is None:
                issues.append(
                    DataQualityIssue(
                        dataset="feature.kis_adjusted_ohlcv_daily",
                        severity="warning",
                        rule_code="KIS_MISSING_KRX_REFERENCE",
                        message="KIS adjusted row has no KRX reference counterpart.",
                        symbol=symbol,
                        trade_date=trade_date,
                    )
                )
                continue
            kis_close = _decimal_from_row(kis_row, "adj_close", "close")
            krx_close = _decimal_from_row(krx_row, "close", "adj_close")
            if kis_close is None or krx_close in (None, Decimal("0")):
                continue
            mismatch = abs(kis_close - krx_close) / abs(krx_close)
            if mismatch > self.config.price_mismatch_tolerance_ratio:
                issues.append(
                    DataQualityIssue(
                        dataset="feature.kis_adjusted_ohlcv_daily",
                        severity="warning",
                        rule_code="KIS_KRX_CLOSE_MISMATCH",
                        message=(
                            "KIS adjusted close differs from KRX close by "
                            f"{mismatch:.6f}, over tolerance {self.config.price_mismatch_tolerance_ratio}."
                        ),
                        symbol=symbol,
                        trade_date=trade_date,
                    )
                )
        return issues


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


def _bars_by_symbol(bars: Iterable[OhlcvBar]) -> dict[str, list[OhlcvBar]]:
    grouped: dict[str, list[OhlcvBar]] = {}
    for bar in bars:
        grouped.setdefault(bar.symbol, []).append(bar)
    return grouped


def _row_key(
    row: dict[str, object],
    *,
    symbol_keys: tuple[str, ...],
    date_keys: tuple[str, ...],
) -> tuple[str, date]:
    symbol = next((row[key] for key in symbol_keys if row.get(key) is not None), None)
    raw_date = next((row[key] for key in date_keys if row.get(key) is not None), None)
    if symbol is None or raw_date is None:
        raise ValueError(f"Row is missing symbol/date key: {row}")
    if isinstance(raw_date, date):
        trade_date = raw_date
    else:
        trade_date = date.fromisoformat(str(raw_date)[:10])
    return str(symbol).zfill(6) if str(symbol).isdigit() and len(str(symbol)) < 6 else str(symbol), trade_date


def _decimal_from_row(row: dict[str, object], *keys: str) -> Decimal | None:
    raw = next((row[key] for key in keys if row.get(key) is not None), None)
    if raw is None:
        return None
    try:
        return Decimal(str(raw).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
