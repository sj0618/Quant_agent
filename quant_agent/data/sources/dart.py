"""OpenDART source client and normalizers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from quant_agent.data.config import DartConfig
from quant_agent.data.models import RawSourcePayload
from quant_agent.data.sources.base import SourceConfigurationError, SourceResponseError, retry_call


class OpenDartClient:
    source_name = "DART"

    def __init__(self, config: DartConfig) -> None:
        self.config = config

    def fetch_corp_codes(self) -> bytes:
        if not self.config.is_configured:
            raise SourceConfigurationError("DART_API_KEY or OPENDART_API_KEY is required for OpenDART ingestion.")

        def request_bytes() -> bytes:
            import requests

            response = requests.get(
                f"{self.config.base_url}/corpCode.xml",
                params={"crtfc_key": self.config.api_key},
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            return response.content

        return retry_call(request_bytes, self.config.retry)

    def fetch_financial_statement(
        self,
        *,
        corp_code: str,
        business_year: int,
        report_code: str,
        fs_div: str = "CFS",
    ) -> RawSourcePayload:
        if not self.config.is_configured:
            raise SourceConfigurationError("DART_API_KEY or OPENDART_API_KEY is required for OpenDART ingestion.")
        params = {
            "crtfc_key": self.config.api_key,
            "corp_code": corp_code,
            "bsns_year": str(business_year),
            "reprt_code": report_code,
            "fs_div": fs_div,
        }

        def request_payload() -> dict[str, Any]:
            import requests

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

        payload = retry_call(request_payload, self.config.retry)
        safe_request = {key: value for key, value in params.items() if key != "crtfc_key"}
        return RawSourcePayload(
            source=self.source_name,
            endpoint_key="fnlttSinglAcntAll",
            request_date=date.today(),
            request=safe_request,
            payload=payload,
        )


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
    accounts = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        account_id = str(row.get("account_id") or row.get("account_nm") or "").strip()
        if not account_id:
            continue
        accounts[account_id] = {
            "account_name": row.get("account_nm"),
            "fs_nm": row.get("fs_nm"),
            "sj_nm": row.get("sj_nm"),
            "amount": _decimal_or_none(row.get("thstrm_amount")),
            "raw": row,
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
    }.get(report_code, (12, 31))
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
