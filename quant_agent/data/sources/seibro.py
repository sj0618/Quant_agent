"""SEIBro report collection and sentiment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import html
import random
import re
import time
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from quant_agent.data.config import SeibroConfig
from quant_agent.data.models import AnalystReportSummary, ApiRequestLog, RawSourcePayload
from quant_agent.data.sources.base import SourceConfigurationError, SourceResponseError, retry_call


class SeibroCollectionPolicyError(RuntimeError):
    """Raised unless SEIBro collection is explicitly approved in runtime env."""


@dataclass(frozen=True)
class SeibroReport:
    symbol: str | None
    company_name: str
    report_date: date
    summary: str
    opinion: str | None
    target_price: Decimal | None
    close_price: Decimal | None
    institution: str | None
    author: str | None
    raw: dict[str, Any]


class SeibroReportClient:
    source_name = "SEIBRO"

    def __init__(self, config: SeibroConfig) -> None:
        self.config = config

    def fetch_report_payload(self, *, endpoint_path: str, params: dict[str, Any]) -> RawSourcePayload:
        if not self.config.collection_approved:
            raise SeibroCollectionPolicyError(
                "SEIBro collection is disabled. Set SEIBRO_COLLECTION_APPROVED=true only after legal/ToS approval."
            )
        safe_path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        def request_payload() -> dict[str, Any]:
            import requests

            response = requests.get(
                f"{self.config.base_url}{safe_path}",
                params=params,
                headers=headers,
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceResponseError("SEIBro response is not a JSON object.")
            return payload

        payload = retry_call(request_payload, self.config.retry)
        return RawSourcePayload(
            source=self.source_name,
            endpoint_key=safe_path,
            request_date=date.today(),
            request=params,
            payload=payload,
        )


class SeibroAnalystReportClient:
    source_name = "SEIBRO"

    def __init__(self, config: SeibroConfig) -> None:
        self.config = config
        self._session = None
        self._request_observer = None

    def set_request_observer(self, request_observer: Any | None) -> None:
        self._request_observer = request_observer

    def fetch_summary_page(
        self,
        *,
        start_date: date,
        end_date: date,
        start_row: int,
        end_row: int,
        company_code: str = "",
    ) -> RawSourcePayload:
        if not self.config.collection_approved:
            raise SeibroCollectionPolicyError(
                "SEIBro collection is disabled. Set SEIBRO_COLLECTION_APPROVED=true only after legal/ToS approval."
            )
        if start_row < 1 or end_row < start_row:
            raise ValueError("SEIBro analyst report page bounds must satisfy 1 <= start_row <= end_row.")

        request_payload = {
            "ISSUCO_CUSTNO": company_code,
            "STD_DT1": _format_yyyymmdd(start_date),
            "STD_DT2": _format_yyyymmdd(end_date),
            "START_PAGE": str(start_row),
            "END_PAGE": str(end_row),
        }
        xml_body = _analyst_report_request_xml(
            action=self.config.analyst_report_action,
            task=self.config.analyst_report_task,
            params=request_payload,
        )
        response_text = self._post_xml(xml_body=xml_body, request_payload=request_payload)
        rows, metadata = _parse_analyst_report_xml(response_text)
        return RawSourcePayload(
            source=self.source_name,
            endpoint_key=self.config.analyst_report_api_path,
            request_date=start_date,
            request={
                "action": self.config.analyst_report_action,
                "task": self.config.analyst_report_task,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "start_row": start_row,
                "end_row": end_row,
                "company_code": company_code,
            },
            payload={"rows": rows, "metadata": metadata},
        )

    def sleep_between_requests(self, minimum_seconds: float | None = None, maximum_seconds: float | None = None) -> None:
        minimum = self.config.request_sleep_min_seconds if minimum_seconds is None else minimum_seconds
        maximum = self.config.request_sleep_max_seconds if maximum_seconds is None else maximum_seconds
        if maximum <= 0:
            return
        if minimum < 0 or maximum < minimum:
            raise ValueError("SEIBro sleep bounds must satisfy 0 <= minimum <= maximum.")
        time.sleep(random.uniform(minimum, maximum))

    def _post_xml(self, *, xml_body: str, request_payload: dict[str, str]) -> str:
        import requests

        session = self._session or requests.Session()
        self._session = session
        page_url = urljoin(self.config.web_base_url, self.config.analyst_report_page_path)
        api_url = urljoin(self.config.web_base_url, self.config.analyst_report_api_path)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": page_url,
            "Content-Type": "application/xml; charset=UTF-8",
            "Accept": "application/xml, text/xml, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        last_error: Exception | None = None
        attempts = max(self.config.retry.attempts, 1)
        for attempt in range(1, attempts + 1):
            started = datetime.now(timezone.utc)
            started_monotonic = time.perf_counter()
            status_code = None
            try:
                response = session.post(
                    api_url,
                    data=xml_body.encode("utf-8"),
                    headers=headers,
                    timeout=self.config.request_timeout_seconds,
                )
                status_code = response.status_code
                response.raise_for_status()
                text = response.content.decode("utf-8", errors="replace")
                _raise_for_warning_response(text)
                self._emit_request_log(
                    request_payload=request_payload,
                    success=True,
                    status_code=status_code,
                    started=started,
                    elapsed_ms=_elapsed_ms(started_monotonic),
                    retry_count=attempt - 1,
                    response_text=text,
                    error_message=None,
                )
                return text
            except Exception as exc:
                last_error = exc
                self._emit_request_log(
                    request_payload=request_payload,
                    success=False,
                    status_code=status_code,
                    started=started,
                    elapsed_ms=_elapsed_ms(started_monotonic),
                    retry_count=attempt - 1,
                    response_text=None,
                    error_message=str(exc),
                )
                if attempt >= attempts:
                    break
                time.sleep(self.config.retry.backoff_seconds * attempt)
        raise SourceResponseError(f"SEIBro analyst report request failed: {last_error}") from last_error

    def _emit_request_log(
        self,
        *,
        request_payload: dict[str, str],
        success: bool,
        status_code: int | None,
        started: datetime,
        elapsed_ms: int,
        retry_count: int,
        response_text: str | None,
        error_message: str | None,
    ) -> None:
        if not self._request_observer:
            return
        response = None
        if response_text is not None:
            response = {"response_hash": hashlib.sha256(response_text.encode("utf-8")).hexdigest()}
        self._request_observer(
            ApiRequestLog(
                source_id=self.source_name,
                endpoint_key=self.config.analyst_report_api_path,
                request=request_payload,
                success=success,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                retry_count=retry_count,
                response=response,
                error_message=error_message,
                metadata={"api_style": "websquare_proworks", "action": self.config.analyst_report_action},
                request_started_at=started,
            )
        )


def normalize_analyst_report_summaries(raw_payload: RawSourcePayload) -> list[AnalystReportSummary]:
    payload_hash = _stable_hash(raw_payload.payload)
    reports: list[AnalystReportSummary] = []
    rows = raw_payload.payload.get("rows")
    if not isinstance(rows, list):
        return reports
    for row in rows:
        if not isinstance(row, dict):
            continue
        report = _analyst_report_from_row(row, payload_hash)
        if report is not None:
            reports.append(report)
    return reports


def normalize_seibro_reports(payload: dict[str, Any]) -> list[SeibroReport]:
    rows = _extract_rows(payload)
    reports = []
    for row in rows:
        report_date = _parse_date(_first(row, "report_date", "rpt_dt", "BASE_DT", "date"))
        company_name = _first(row, "company_name", "corp_name", "isu_nm", "ISU_NM", "name")
        summary = _first(row, "summary", "analyst_summary", "content", "SUMMARY")
        if not report_date or not company_name or not summary:
            continue
        reports.append(
            SeibroReport(
                symbol=_first(row, "symbol", "stock_code", "isu_cd", "SHOTN_ISIN"),
                company_name=company_name,
                report_date=report_date,
                summary=summary,
                opinion=_first(row, "opinion", "investment_opinion", "OPINION"),
                target_price=_decimal_or_none(_first(row, "target_price", "trgt_prc", "TARGET_PRICE")),
                close_price=_decimal_or_none(_first(row, "close_price", "close", "CLOSE_PRICE")),
                institution=_first(row, "institution", "broker", "ORG_NM"),
                author=_first(row, "author", "analyst", "AUTHOR"),
                raw=row,
            )
        )
    return reports


class LexiconSentimentScorer:
    """Deterministic baseline scorer for report summaries.

    Production can replace this with an AOAI scoring job, while this baseline
    keeps the data pipeline testable and versioned without external model
    credentials.
    """

    model_version = "lexicon-ko-en-v1"
    prompt_version = "deterministic-no-prompt"

    positive_terms = ("상향", "매수", "성장", "개선", "호조", "긍정", "증가", "buy", "outperform", "positive")
    negative_terms = ("하향", "매도", "부진", "악화", "둔화", "부정", "감소", "sell", "underperform", "negative")

    def score(self, text: str) -> float:
        lowered = text.lower()
        positive = sum(1 for term in self.positive_terms if term in lowered)
        negative = sum(1 for term in self.negative_terms if term in lowered)
        denominator = max(positive + negative, 1)
        return max(min((positive - negative) / denominator, 1.0), -1.0)


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("rows", "list", "data", "result", "OutBlock_1"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    for value in payload.values():
        if isinstance(value, dict):
            nested = _extract_rows(value)
            if nested:
                return nested
    return []


def _first(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.replace(".", "").replace("-", "").strip()
    if len(text) == 8:
        return date.fromisoformat(f"{text[0:4]}-{text[4:6]}-{text[6:8]}")
    return None


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = value.replace(",", "").strip()
    if text in {"", "-"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _analyst_report_from_row(row: dict[str, Any], payload_hash: str) -> AnalystReportSummary | None:
    report_date = _parse_date(_first(row, "STD_DT", "report_date", "rpt_dt"))
    company_value = _first(row, "REP_SECN", "company_name", "corp_name")
    ticker = extract_ticker(company_value) or _first(row, "SHOTN_ISIN", "symbol", "ticker")
    summary = _normalize_report_text(_first(row, "ENTR_SUMM_CONTENT", "summary"))
    if not report_date or not company_value or not ticker or not summary:
        return None
    return AnalystReportSummary(
        report_date=report_date,
        ticker=ticker,
        company_name=strip_ticker_suffix(company_value),
        summary=summary,
        opinion=_first(row, "INVST_OPINION_GRD_CONTENT", "opinion"),
        target_price=_decimal_or_none(_first(row, "TARGET_PRICE", "target_price")),
        close_price=_decimal_or_none(_first(row, "CPRI", "close_price")),
        institution=_first(row, "WROT_ORG_NM", "institution") or "",
        author=_first(row, "WRITER_NM", "author") or "",
        source_payload_hash=payload_hash,
        raw=row,
    )


def extract_ticker(company_name: str | None) -> str | None:
    if not company_name:
        return None
    match = re.search(r"\((\d{6})\)\s*$", company_name.strip())
    return match.group(1) if match else None


def strip_ticker_suffix(company_name: str) -> str:
    return re.sub(r"\s*\(\d{6}\)\s*$", "", company_name).strip()


def _analyst_report_request_xml(*, action: str, task: str, params: dict[str, str]) -> str:
    nodes = "".join(f'<{key} value="{html.escape(str(value), quote=True)}"/>' for key, value in params.items())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<reqParam action="{html.escape(action, quote=True)}" task="{html.escape(task, quote=True)}">{nodes}</reqParam>'
    )


def _parse_analyst_report_xml(response_text: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    try:
        root = ET.fromstring(response_text)
    except ET.ParseError as exc:
        raise SourceResponseError(f"SEIBro analyst report XML parse failed: {exc}") from exc
    if root.tag == "WARNING":
        message = _xml_value(root.find("msg")) or "unknown warning"
        raise SourceResponseError(f"SEIBro analyst report API returned warning: {message}")
    rows: list[dict[str, str]] = []
    for data_node in root.findall("./data"):
        result_node = data_node.find("result")
        if result_node is None:
            continue
        parsed = {}
        for child in result_node:
            value = _xml_value(child)
            if value is not None:
                parsed[child.tag] = value
        if parsed:
            rows.append(parsed)
    metadata = dict(root.attrib)
    return rows, metadata


def _xml_value(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    value = node.attrib.get("value")
    if value is None:
        return None
    return html.unescape(value).strip()


def _raise_for_warning_response(response_text: str) -> None:
    if "<WARNING>" not in response_text:
        return
    try:
        root = ET.fromstring(response_text)
    except ET.ParseError:
        raise SourceResponseError("SEIBro analyst report API returned a warning response.")
    message = _xml_value(root.find("msg")) or "unknown warning"
    raise SourceResponseError(f"SEIBro analyst report API returned warning: {message}")


def _normalize_report_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = html.unescape(value)
    text = text.replace("$$", "\n").replace("<br />", "\n").replace("<br/>", "\n")
    normalized = "\n".join(part.strip() for part in text.splitlines() if part.strip())
    return normalized or None


def _format_yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def _elapsed_ms(started_monotonic: float) -> int:
    return max(int((time.perf_counter() - started_monotonic) * 1000), 0)


def _stable_hash(value: Any) -> str:
    import json

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
