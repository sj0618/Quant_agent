"""KIND listed-company directory source client and normalizer."""

from __future__ import annotations

from datetime import date
import html
import re
from typing import Any

from quant_agent.data.config import KindConfig
from quant_agent.data.sources.base import SourceConfigurationError, SourceResponseError, retry_call


DEFAULT_KIND_CORP_LIST_PAGE_SIZE = 3000
DEFAULT_KIND_CORP_LIST_ORDER_MODE = "3"
DEFAULT_KIND_CORP_LIST_ORDER_STAT = "D"
DEFAULT_KIND_CORP_LIST_SEARCH_TYPE = "13"

_KIND_CORP_LIST_PARAMS = {
    "method": "download",
    "pageIndex": "1",
    "currentPageSize": str(DEFAULT_KIND_CORP_LIST_PAGE_SIZE),
    "comAbbrv": "",
    "beginIndex": "",
    "orderMode": DEFAULT_KIND_CORP_LIST_ORDER_MODE,
    "orderStat": DEFAULT_KIND_CORP_LIST_ORDER_STAT,
    "isurCd": "",
    "repIsuSrtCd": "",
    "searchCodeType": "",
    "marketType": "",
    "searchType": DEFAULT_KIND_CORP_LIST_SEARCH_TYPE,
    "industry": "",
}

_KIND_MARKET_ALIASES = {
    "유가": "KOSPI",
    "유가증권": "KOSPI",
    "KOSPI": "KOSPI",
    "코스피": "KOSPI",
    "STK": "KOSPI",
    "KOSPI MAIN": "KOSPI",
    "코스닥": "KOSDAQ",
    "KOSDAQ": "KOSDAQ",
    "KSQ": "KOSDAQ",
    "코넥스": "KONEX",
    "KONEX": "KONEX",
    "KNX": "KONEX",
}


class KindListedCompanyClient:
    source_name = "KIND"

    def __init__(self, config: KindConfig) -> None:
        self.config = config

    def fetch_listed_company_rows(self) -> list[dict[str, Any]]:
        if not self.config.is_configured:
            raise SourceConfigurationError("KIND_CORP_LIST_URL is required for KIND sector ingestion.")

        def request_text() -> str:
            import requests

            response = requests.post(
                self.config.corp_list_url,
                data=_KIND_CORP_LIST_PARAMS,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            return response.content.decode("euc-kr", errors="replace")

        html_text = retry_call(request_text, self.config.retry)
        return normalize_kind_listed_companies(html_text)


def normalize_kind_listed_companies(html_text: str) -> list[dict[str, Any]]:
    table_match = re.search(r'<table[^>]*class="bbs_tb"[^>]*>(.*?)</table>', html_text, re.S | re.I)
    if table_match is None:
        raise SourceResponseError("KIND listed-company response does not include the expected table.")

    rows: list[dict[str, Any]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S | re.I)
        if len(cells) < 10:
            continue
        values = [_clean_text(cell) for cell in cells[:10]]
        symbol = values[2]
        sector = values[3]
        if not symbol or not sector:
            continue
        rows.append(
            {
                "symbol": symbol,
                "company_name": values[0],
                "market_segment_raw": values[1],
                "market_segment": normalize_kind_market_segment(values[1]),
                "sector": sector,
                "main_products": values[4],
                "listed_at": _parse_date(values[5]),
                "closing_month": _parse_month(values[6]),
                "representative_name": values[7],
                "homepage": values[8],
                "region": values[9],
            }
        )
    if not rows:
        raise SourceResponseError("KIND listed-company response did not yield any rows.")
    return rows


def normalize_kind_market_segment(value: str | None) -> str | None:
    if value is None:
        return None
    compact = _compact(value)
    if not compact:
        return None
    return _KIND_MARKET_ALIASES.get(compact.upper(), compact)


def _clean_text(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_month(value: str) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    if match is None:
        return None
    month = int(match.group(0))
    return month if 1 <= month <= 12 else None
