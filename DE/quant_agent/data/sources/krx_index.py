"""Official KRX total-return index levels and the KOSPI/KOSDAQ benchmark split.

Two facts feed ``ai/docs/official-krx-tr-benchmark-contract.md``:

* daily levels of the KRX-published total-return indices 코스피 TR / 코스닥 TR, and
* the month-end KOSPI vs KOSDAQ market-capitalisation split the benchmark rebalances to.

Neither is reachable from the sources this repository already used. KRX's own
``data.krx.co.kr`` became the membership-gated "KRX Data Marketplace" on 2025-12-27 and
now answers ``LOGOUT`` to every ``dbms/MDC/STAT/*`` query, and the KRX Open API key in
``DE/.env`` returns ``Unauthorized Key`` on every endpoint. So the levels are read from
KIS, which redistributes the KRX index series under licence, and the split is read from
the Bank of Korea's ECOS table 901Y014, which republishes KRX's month-end market
capitalisation per market.

Only total-return codes are exposed here. A dividend-stripped price index would quietly
lower the bar the AI acceptance gate compares a strategy against, and the reader contract
rejects it.
"""

from __future__ import annotations

from datetime import date, timedelta
import time
from decimal import Decimal
from typing import Any, Mapping

from quant_agent.data.config import KisConfig
from quant_agent.data.models import RawSourcePayload
from quant_agent.data.sources.base import (
    SourceConfigurationError,
    SourceResponseError,
    decimal_or_none,
    retry_call,
)
from quant_agent.data.sources.kis import KisOhlcvClient


# Warehouse index_code -> KIS 업종코드 (from KIS's own idxcode.mst master file:
# "00195코스피 TR", "11196코스닥 TR").  The warehouse code is the contract's name;
# the KIS code is a vendor detail that must not leak into the warehouse.
INDEX_CODE_TO_KIS_SECTOR = {
    "KOSPI_TR": "0195",
    "KOSDAQ_TR": "1196",
}

# KIS returns at most this many sessions per call, anchored on the end date.
KIS_INDEX_CHART_MAX_ROWS = 50
KIS_INDEX_CHART_TR_ID = "FHKUP03500100"
KIS_INDEX_CHART_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"

# ECOS 901Y014 "1.5.1.2. 주식시장(월,년)", monthly, unit 천원. Both items are KRX-sourced
# month-end market capitalisation, which is exactly the contract's default weight basis.
ECOS_MARKET_CAP_STAT_CODE = "901Y014"
ECOS_MARKET_CAP_ITEMS = {"KOSPI": "1040000", "KOSDAQ": "2040000"}
MARKET_CAP_WEIGHT_BASIS = "month_end_market_capitalization"


class KrxIndexTotalReturnClient:
    """Daily KRX total-return index levels, read through KIS's index chart endpoint."""

    source_name = "KRX"

    def __init__(self, config: KisConfig, *, page_sleep_seconds: float = 0.0) -> None:
        self.config = config
        self._auth = KisOhlcvClient(config)
        # KIS throttles per second; a full backfill is ~50 pages per index.
        self.page_sleep_seconds = page_sleep_seconds

    def fetch_index_payloads(
        self, index_code: str, start_date: date, end_date: date
    ) -> list[RawSourcePayload]:
        """Walk the window backwards in ``KIS_INDEX_CHART_MAX_ROWS``-session pages."""

        sector_code = INDEX_CODE_TO_KIS_SECTOR.get(index_code)
        if sector_code is None:
            raise SourceConfigurationError(
                f"{index_code} is not a known KRX total-return index code."
            )
        if not self.config.is_configured:
            raise SourceConfigurationError(
                "KIS_APP_KEY and KIS_APP_SECRET are required for KRX index ingestion."
            )

        payloads: list[RawSourcePayload] = []
        cursor = end_date
        while cursor >= start_date:
            payload = self._fetch_page(sector_code, start_date, cursor)
            payloads.append(
                RawSourcePayload(
                    source=self.source_name,
                    endpoint_key=KIS_INDEX_CHART_PATH,
                    request_date=cursor,
                    request={
                        "index_code": index_code,
                        "kis_sector_code": sector_code,
                        "start_date": start_date.isoformat(),
                        "end_date": cursor.isoformat(),
                    },
                    payload=payload,
                )
            )
            oldest = _oldest_session(payload)
            # No progress means the series has no more history in this window; stopping
            # here rather than on a row count keeps a short final page from looping.
            if oldest is None or oldest <= start_date:
                break
            cursor = oldest - timedelta(days=1)
            if self.page_sleep_seconds > 0:
                time.sleep(self.page_sleep_seconds)
        return payloads

    def _fetch_page(self, sector_code: str, start_date: date, end_date: date) -> dict[str, Any]:
        token = self._auth.issue_access_token()
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": sector_code,
            "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
        }

        def request_payload() -> dict[str, Any]:
            import requests

            response = requests.get(
                f"{self.config.base_url}{KIS_INDEX_CHART_PATH}",
                params=params,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "authorization": f"Bearer {token}",
                    "appkey": self.config.app_key or "",
                    "appsecret": self.config.app_secret or "",
                    "tr_id": KIS_INDEX_CHART_TR_ID,
                    "custtype": "P",
                },
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceResponseError("KIS index response is not a JSON object.")
            if str(payload.get("rt_cd", "0")) != "0":
                raise SourceResponseError(
                    f"KIS index response returned rt_cd={payload.get('rt_cd')}: {payload.get('msg1')}"
                )
            return payload

        return retry_call(request_payload, self.config.retry)


def _oldest_session(payload: Mapping[str, Any]) -> date | None:
    sessions = [
        parsed
        for row in payload.get("output2") or ()
        if isinstance(row, Mapping)
        for parsed in (_compact_date(row.get("stck_bsop_date")),)
        if parsed is not None
    ]
    return min(sessions) if sessions else None


def _compact_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def normalize_index_total_return(
    payload: Mapping[str, Any],
    *,
    index_code: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    """Map one KIS index-chart payload to ``(index_code, trade_date, tr_value)`` rows.

    Non-positive or unparsable levels are dropped rather than stored: the contract's
    CHECK constraint rejects them anyway, and a dropped session simply lowers the
    coverage ratio the AI reader already reports.
    """

    rows = payload.get("output2")
    if not isinstance(rows, list):
        raise SourceResponseError("KIS index response does not contain an output2 list.")

    normalized: dict[date, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        trade_date = _compact_date(row.get("stck_bsop_date"))
        if trade_date is None:
            continue
        if start_date is not None and trade_date < start_date:
            continue
        if end_date is not None and trade_date > end_date:
            continue
        tr_value = decimal_or_none(row.get("bstp_nmix_prpr"))
        if tr_value is None or tr_value <= 0:
            continue
        normalized[trade_date] = {
            "index_code": index_code,
            "trade_date": trade_date,
            "tr_value": tr_value,
        }
    return [normalized[key] for key in sorted(normalized)]


def normalize_ecos_market_caps(
    payload: Mapping[str, Any], *, market: str
) -> dict[str, Decimal]:
    """Map an ECOS ``StatisticSearch`` payload to ``{"YYYYMM": market_cap}``."""

    search = payload.get("StatisticSearch")
    if not isinstance(search, Mapping):
        error = payload.get("RESULT")
        if isinstance(error, Mapping) and error.get("CODE") == "INFO-200":
            return {}
        raise SourceResponseError(
            f"ECOS response for {market} market capitalisation is unusable: {error or payload}"
        )
    observations: dict[str, Decimal] = {}
    for row in search.get("row") or ():
        if not isinstance(row, Mapping):
            continue
        period = str(row.get("TIME") or "").strip()
        value = decimal_or_none(row.get("DATA_VALUE"))
        if len(period) == 6 and period.isdigit() and value is not None and value > 0:
            observations[period] = value
    return observations


def benchmark_weight_rows(
    kospi_market_caps: Mapping[str, Decimal],
    kosdaq_market_caps: Mapping[str, Decimal],
    *,
    basis: str = MARKET_CAP_WEIGHT_BASIS,
) -> list[dict[str, Any]]:
    """Turn month-end market caps into unlagged weight rows keyed on the month's 1st.

    Stored unlagged on purpose: the AI reader applies the one-month lag, and storing an
    already-lagged number would erase which month the observation came from.
    """

    rows: list[dict[str, Any]] = []
    for period in sorted(set(kospi_market_caps) & set(kosdaq_market_caps)):
        kospi = Decimal(kospi_market_caps[period])
        kosdaq = Decimal(kosdaq_market_caps[period])
        total = kospi + kosdaq
        if total <= 0:
            continue
        kospi_weight = kospi / total
        rows.append(
            {
                "month": date(int(period[:4]), int(period[4:6]), 1),
                # The pair is derived from one ratio so the two always sum to exactly 1,
                # which the warehouse CHECK constraint enforces to 1e-6.
                "kospi_weight": kospi_weight,
                "kosdaq_weight": Decimal(1) - kospi_weight,
                "basis": basis,
            }
        )
    return rows
