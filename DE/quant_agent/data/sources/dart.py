"""OpenDART source client and normalizers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from zipfile import BadZipFile, ZipFile

from quant_agent.data.config import DartConfig
from quant_agent.data.models import RawSourcePayload
from quant_agent.data.sources.base import (
    SourceConfigurationError,
    SourceResponseError,
    retry_call,
)

# OpenDART reuses these account IDs across multiple statement blocks.
# Downstream consumers expect the canonical total row, so prefer the statement
# and row shape most likely to carry the aggregate number.
DART_ACCOUNT_STATEMENT_PREFERENCES: dict[str, tuple[str, ...]] = {
    "ifrs-full_Equity": ("BS",),
    "ifrs-full_Liabilities": ("BS",),
    "ifrs-full_ProfitLoss": ("IS", "CIS"),
    "ifrs-full_Revenue": ("IS", "CIS"),
    "dart_OperatingIncomeLoss": ("IS", "CIS"),
    "ifrs-full_BasicEarningsLossPerShare": ("IS", "CIS"),
}
DART_QUOTA_STATUS_CODES = frozenset({"020"})
DART_QUOTA_MESSAGE_HINTS = ("사용한도", "quota", "usage limit", "too many requests")


@dataclass
class DartApiKeyPool:
    keys: tuple[str, ...]
    cursor: int = 0
    disabled_keys: set[str] = field(default_factory=set)

    @property
    def size(self) -> int:
        return len(self.keys)

    @property
    def active_size(self) -> int:
        return sum(1 for key in self.keys if key not in self.disabled_keys)

    def next(self) -> str:
        if not self.keys:
            raise SourceConfigurationError(
                "DART_API_KEY, OPENDART_API_KEY, FSS_API_KEY, FSS_API_KEY_2, or FSS_API_KEY_3 is required for OpenDART ingestion."
            )
        if self.active_size == 0:
            raise SourceResponseError("OpenDART API keys are exhausted for this run.")

        attempts = 0
        while attempts < len(self.keys):
            key = self.keys[self.cursor]
            self.cursor = (self.cursor + 1) % len(self.keys)
            attempts += 1
            if key not in self.disabled_keys:
                return key
        raise SourceResponseError("OpenDART API keys are exhausted for this run.")

    def disable(self, key: str) -> None:
        self.disabled_keys.add(key)


class OpenDartClient:
    source_name = "DART"

    def __init__(self, config: DartConfig) -> None:
        self.config = config
        self._api_key_pool = DartApiKeyPool(config.api_keys)

    def fetch_corp_codes(self) -> bytes:
        if not self.config.is_configured:
            raise SourceConfigurationError(
                "DART_API_KEY, OPENDART_API_KEY, FSS_API_KEY, FSS_API_KEY_2, or FSS_API_KEY_3 is required for OpenDART ingestion."
            )

        last_error: Exception | None = None
        while self._api_key_pool.active_size > 0:
            api_key = self._api_key_pool.next()
            archive_bytes = b""
            try:
                archive_bytes = retry_call(
                    lambda: self._fetch_corp_codes_once(api_key),
                    self.config.retry,
                )
                normalize_corp_code_zip(archive_bytes)
            except (BadZipFile, SourceResponseError) as exc:
                last_error = exc
                if self._is_quota_text(archive_bytes.decode("utf-8", errors="ignore")):
                    self._api_key_pool.disable(api_key)
                continue
            except Exception as exc:  # noqa: BLE001 - preserve underlying source failure
                last_error = exc
                continue
            return archive_bytes

        if last_error is not None:
            raise last_error
        raise SourceResponseError("OpenDART corpCode request failed for all configured API keys.")

    def fetch_financial_statement(
        self,
        *,
        corp_code: str,
        business_year: int,
        report_code: str,
        fs_div: str = "CFS",
    ) -> RawSourcePayload:
        if not self.config.is_configured:
            raise SourceConfigurationError(
                "DART_API_KEY, OPENDART_API_KEY, FSS_API_KEY, FSS_API_KEY_2, or FSS_API_KEY_3 is required for OpenDART ingestion."
            )

        last_error: Exception | None = None
        while self._api_key_pool.active_size > 0:
            api_key = self._api_key_pool.next()
            try:
                payload = retry_call(
                    lambda: self._fetch_financial_payload_once(
                        api_key=api_key,
                        corp_code=corp_code,
                        business_year=business_year,
                        report_code=report_code,
                        fs_div=fs_div,
                    ),
                    self.config.retry,
                )
            except Exception as exc:  # noqa: BLE001 - preserve underlying source failure
                last_error = exc
                continue

            status = str(payload.get("status", "")).strip()
            message = str(payload.get("message", "")).strip()
            if self._is_quota_payload(status, message):
                self._api_key_pool.disable(api_key)
                last_error = SourceResponseError(
                    f"OpenDART financial response status={status}: {message or 'API quota exhausted'}"
                )
                continue

            safe_request = {
                "corp_code": corp_code,
                "bsns_year": str(business_year),
                "reprt_code": report_code,
                "fs_div": fs_div,
            }
            return RawSourcePayload(
                source=self.source_name,
                endpoint_key="fnlttSinglAcntAll",
                request_date=date.today(),
                request=safe_request,
                payload=payload,
            )

        if last_error is not None:
            raise last_error
        raise SourceResponseError("OpenDART financial request failed for all configured API keys.")

    def _fetch_corp_codes_once(self, api_key: str) -> bytes:
        import requests

        response = requests.get(
            f"{self.config.base_url}/corpCode.xml",
            params={"crtfc_key": api_key},
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.content

    def _fetch_financial_payload_once(
        self,
        *,
        api_key: str,
        corp_code: str,
        business_year: int,
        report_code: str,
        fs_div: str,
    ) -> dict[str, Any]:
        import requests

        params = {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": str(business_year),
            "reprt_code": report_code,
            "fs_div": fs_div,
        }
        response = requests.get(
            f"{self.config.base_url}/fnlttSinglAcntAll.json",
            params=params,
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise SourceResponseError("OpenDART financial response is not a JSON object.")
        return payload

    @staticmethod
    def _is_quota_payload(status: str, message: str) -> bool:
        if status in DART_QUOTA_STATUS_CODES:
            return True
        normalized_message = message.casefold()
        return any(hint in normalized_message for hint in DART_QUOTA_MESSAGE_HINTS)

    @staticmethod
    def _is_quota_text(text: str) -> bool:
        normalized_text = text.casefold()
        return any(hint in normalized_text for hint in DART_QUOTA_MESSAGE_HINTS)


def normalize_corp_code_zip(zip_bytes: bytes) -> list[dict[str, str]]:
    with ZipFile(BytesIO(zip_bytes)) as archive:
        xml_name = next((name for name in archive.namelist() if name.lower().endswith(".xml")), None)
        if xml_name is None:
            raise SourceResponseError("OpenDART corpCode archive does not include XML.")
        xml_bytes = archive.read(xml_name)
    root = ET.fromstring(xml_bytes)
    rows = []
    for item in root.findall(".//list"):
        rows.append(
            {
                "corp_code": _xml_text(item, "corp_code"),
                "corp_name": _xml_text(item, "corp_name"),
                "stock_code": _xml_text(item, "stock_code"),
                "modify_date": _xml_text(item, "modify_date"),
            }
        )
    return rows


def normalize_financial_statement(raw_payload: RawSourcePayload, *, symbol: str, period_end: date | None = None) -> list[dict[str, Any]]:
    status = str(raw_payload.payload.get("status", "")).strip()
    if status and status != "000":
        raise SourceResponseError(f"OpenDART financial response status={status}: {raw_payload.payload.get('message')}")
    rows = raw_payload.payload.get("list") or []
    if not isinstance(rows, list):
        raise SourceResponseError("OpenDART financial response list is not a list.")
    request = raw_payload.request
    business_year = int(request["bsns_year"])
    report_code = str(request["reprt_code"])
    fs_div = str(request["fs_div"])
    normalized_period_end = period_end or _period_end_from_report_code(business_year, report_code)
    reported_at = datetime.now(timezone.utc).isoformat()
    account_candidates: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        account_id = str(row.get("account_id") or row.get("account_nm") or "").strip()
        if not account_id:
            continue
        account_candidates.setdefault(account_id, []).append((index, row))

    accounts = {}
    for account_id, candidates in account_candidates.items():
        selected_row = _select_financial_statement_row(account_id, candidates)
        accounts[account_id] = {
            "account_name": selected_row.get("account_nm"),
            "fs_nm": selected_row.get("fs_nm"),
            "sj_nm": selected_row.get("sj_nm"),
            "amount": _decimal_or_none(selected_row.get("thstrm_amount")),
            "raw": selected_row,
        }
    return [
        {
            "symbol": symbol,
            "corp_code": str(request["corp_code"]),
            "period_end": normalized_period_end,
            "reported_at": reported_at,
            "report_code": report_code,
            "fs_div": fs_div,
            "accounts": accounts,
        }
    ]


def _xml_text(item: ET.Element, tag: str) -> str:
    child = item.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _period_end_from_report_code(business_year: int, report_code: str) -> date:
    month_day = {
        "11013": (3, 31),
        "11012": (6, 30),
        "11014": (9, 30),
        "11011": (12, 31),
    }.get(report_code)
    if month_day is None:
        raise SourceResponseError(f"Unsupported OpenDART report code: {report_code}")
    return date(business_year, month_day[0], month_day[1])


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text in {"", "-"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _select_financial_statement_row(account_id: str, candidates: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    preferred_sj_divs = DART_ACCOUNT_STATEMENT_PREFERENCES.get(account_id)
    if preferred_sj_divs:
        for sj_div in preferred_sj_divs:
            statement_candidates = [item for item in candidates if _statement_div(item[1]) == sj_div]
            total_candidates = [item for item in statement_candidates if not _is_expanded_account_detail(item[1].get("account_detail"))]
            if total_candidates:
                return min(total_candidates, key=lambda item: item[0])[1]
        for sj_div in preferred_sj_divs:
            statement_candidates = [item for item in candidates if _statement_div(item[1]) == sj_div]
            if statement_candidates:
                return min(statement_candidates, key=lambda item: item[0])[1]

    total_candidates = [item for item in candidates if not _is_expanded_account_detail(item[1].get("account_detail"))]
    if total_candidates:
        return min(total_candidates, key=lambda item: item[0])[1]
    return min(candidates, key=lambda item: item[0])[1]


def _statement_div(row: dict[str, Any]) -> str:
    return str(row.get("sj_div") or "").strip().upper()


def _is_expanded_account_detail(account_detail: Any) -> bool:
    detail = str(account_detail or "").strip()
    if not detail or detail == "-":
        return False
    lowered = detail.casefold()
    return "[member]" in lowered or "[component]" in lowered or "구성요소" in detail or "component" in lowered
