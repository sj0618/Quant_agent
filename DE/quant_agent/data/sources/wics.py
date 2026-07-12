"""FnGuide Company Guide WICS sector source client."""

from __future__ import annotations

from datetime import date
import html
import re
from typing import Any

from quant_agent.data.config import WicsConfig
from quant_agent.data.sources.base import SourceConfigurationError, SourceResponseError, retry_call


WICS_SECTOR_LABEL_PATTERN = re.compile(
    r'<span[^>]*class="stxt stxt2"[^>]*>\s*(?P<label>WI\d+\s+[^<]+?)\s*</span>',
    re.IGNORECASE,
)
WICS_MARKET_TEXT_PATTERN = re.compile(
    r'<span[^>]*id="strMarketTxt"[^>]*>\s*(?P<label>[^<]+?)\s*</span>',
    re.IGNORECASE,
)


class WicsCompanyGuideClient:
    source_name = "WICS"

    def __init__(self, config: WicsConfig) -> None:
        self.config = config

    def fetch_sector_row(
        self,
        *,
        symbol: str,
        company_name: str | None = None,
        market_segment: str | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, Any]:
        page = self.fetch_company_info_page(symbol)
        row = normalize_wics_company_info(
            page["html_text"],
            symbol=symbol,
            company_name=company_name,
            market_segment=market_segment,
            source_url=page["source_url"],
            as_of_date=as_of_date,
        )
        return row

    def fetch_company_info_page(self, symbol: str) -> dict[str, Any]:
        if not self.config.is_configured:
            raise SourceConfigurationError("WICS_COMPANY_INFO_URL is required for WICS sector ingestion.")

        symbol_code = str(symbol).strip().zfill(6)

        def request_page() -> dict[str, Any]:
            import requests

            response = requests.get(
                self.config.company_info_url,
                params={"cmp_cd": symbol_code},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            html_text = response.content.decode("utf-8", errors="replace")
            if not html_text.strip():
                raise SourceResponseError("WICS Company Guide response is empty.")
            return {"html_text": html_text, "source_url": response.url}

        return retry_call(request_page, self.config.retry)


def normalize_wics_company_info(
    html_text: str,
    *,
    symbol: str,
    company_name: str | None = None,
    market_segment: str | None = None,
    source_url: str | None = None,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    sector_match = WICS_SECTOR_LABEL_PATTERN.search(html_text)
    if not sector_match:
        raise SourceResponseError("WICS sector label was not found in the Company Guide response.")
    sector_label = html.unescape(sector_match.group("label")).strip()
    sector_code, sector = _split_wics_sector_label(sector_label)
    market_segment_raw = _extract_market_segment_text(html_text)
    resolved_market_segment = normalize_wics_market_segment(market_segment or market_segment_raw)
    return {
        "symbol": str(symbol).strip().zfill(6),
        "company_name": company_name,
        "market_segment_raw": market_segment_raw,
        "market_segment": resolved_market_segment,
        "sector_code": sector_code,
        "sector": sector,
        "sector_label": sector_label,
        "source_url": source_url,
        "sector_as_of": as_of_date,
    }


def normalize_wics_market_segment(value: str | None) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value)).strip()
    if not text:
        return None
    candidate = text.split()[0].strip().upper()
    aliases = {
        "KOSPI": "KOSPI",
        "유가": "KOSPI",
        "유가증권": "KOSPI",
        "코스피": "KOSPI",
        "KOSDAQ": "KOSDAQ",
        "코스닥": "KOSDAQ",
        "KONEX": "KONEX",
        "코넥스": "KONEX",
    }
    return aliases.get(candidate, candidate or text)


def _split_wics_sector_label(label: str) -> tuple[str, str]:
    cleaned = html.unescape(label).strip()
    parts = cleaned.split(None, 1)
    if len(parts) != 2:
        raise SourceResponseError(f"Unexpected WICS sector label format: {label}")
    return parts[0].strip(), parts[1].strip()


def _extract_market_segment_text(html_text: str) -> str | None:
    match = WICS_MARKET_TEXT_PATTERN.search(html_text)
    if not match:
        return None
    return html.unescape(match.group("label")).strip() or None
