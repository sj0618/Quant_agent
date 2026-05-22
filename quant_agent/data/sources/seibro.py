"""SEIBro report collection and sentiment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from quant_agent.data.config import SeibroConfig
from quant_agent.data.models import RawSourcePayload
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
