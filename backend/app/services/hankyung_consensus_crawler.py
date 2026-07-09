from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import Settings, redact_secrets
from app.core.errors import AppError
from app.db.pdf_temp_repository import HankyungConsensusPdfTempSeedRecord, PdfTempDbRepository

_SECRET_KEY_PARTS = ("authorization", "cookie", "token", "secret", "password", "session")


@dataclass(frozen=True, slots=True)
class HankyungConsensusCrawlRequest:
    from_date: str | None = None
    to_date: str | None = None
    report_type: str = "ALL"
    page: int = 1
    max_pages: int | None = None
    max_reports: int | None = None
    business_code: str | None = None
    search_word: str | None = None
    search_type: str | None = None


@dataclass(frozen=True, slots=True)
class HankyungConsensusImportResult:
    fetched: int
    imported: int
    skipped: int
    failed: int
    seeds: list[HankyungConsensusPdfTempSeedRecord]
    errors: list[str]


def normalize_hankyung_report_row(
    row: dict[str, Any],
    *,
    base_url: str,
    allowed_pdf_hosts: list[str] | None = None,
) -> HankyungConsensusPdfTempSeedRecord | None:
    report_idx = _clean_str(row.get("REPORT_IDX"))
    if not report_idx:
        return None
    pdf_url = _pdf_url_from_row(row, base_url=base_url)
    if not pdf_url:
        return None
    if allowed_pdf_hosts is not None and not _is_allowed_pdf_url(pdf_url, allowed_pdf_hosts):
        return None
    report_date = _optional_iso_date(row.get("REPORT_DATE"))
    if row.get("REPORT_DATE") is not None and report_date is None:
        return None
    return HankyungConsensusPdfTempSeedRecord(
        seed_id=f"hankyung-crawl-{report_idx}",
        report_idx=report_idx,
        report_title=_clean_str(row.get("REPORT_TITLE")),
        company_name=_clean_str(row.get("BUSINESS_NAME")),
        ticker=_clean_str(row.get("BUSINESS_CODE")),
        broker=_clean_str(row.get("OFFICE_NAME")),
        report_date=report_date,
        pdf_url=pdf_url,
        source_page_url=urljoin(base_url.rstrip("/") + "/", f"consensus/report/{report_idx}"),
        source_report_type=_clean_str(row.get("REPORT_TYPE")),
        source_writer=_clean_str(row.get("REPORT_WRITER")),
        source_payload_hash=source_payload_hash(row),
        status="active",
    )


def source_payload_hash(row: dict[str, Any]) -> str:
    safe_row = _strip_secret_fields(row)
    canonical = json.dumps(safe_row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class HankyungConsensusCrawler:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch_report_rows(self, request: HankyungConsensusCrawlRequest) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        bounds = self._bounded_request(request)
        async with httpx.AsyncClient(
            base_url=self.settings.hankyung_consensus_api_base_url,
            headers=self._headers(),
            timeout=self.settings.hankyung_consensus_crawl_timeout_seconds,
            follow_redirects=False,
        ) as client:
            for page_offset in range(bounds.max_pages):
                page = bounds.page + page_offset
                try:
                    response = await client.get("/api/consensus/search/report", params=self._params(bounds, page))
                except httpx.HTTPError as exc:
                    raise AppError(
                        status_code=502,
                        component="hankyung_consensus_crawler",
                        code="crawler_fetch_failed",
                        message="Hankyung consensus crawler fetch failed",
                        details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
                    ) from exc
                if response.status_code >= 400:
                    raise AppError(
                        status_code=502,
                        component="hankyung_consensus_crawler",
                        code="crawler_fetch_failed",
                        message="Hankyung consensus crawler fetch failed",
                        details={"status_code": response.status_code},
                    )
                try:
                    page_rows = _extract_rows(response.json())
                except ValueError as exc:
                    raise AppError(
                        status_code=502,
                        component="hankyung_consensus_crawler",
                        code="crawler_unexpected_payload",
                        message="Hankyung consensus crawler returned an unexpected payload",
                    ) from exc
                rows.extend(page_rows[: max(bounds.max_reports - len(rows), 0)])
                if len(rows) >= bounds.max_reports or not page_rows:
                    break
        return rows

    async def import_reports(
        self,
        request: HankyungConsensusCrawlRequest,
        repository: PdfTempDbRepository,
    ) -> HankyungConsensusImportResult:
        errors: list[str] = []
        try:
            rows = await self.fetch_report_rows(request)
        except AppError as exc:
            return HankyungConsensusImportResult(
                fetched=0,
                imported=0,
                skipped=0,
                failed=1,
                seeds=[],
                errors=[str(redact_secrets(exc.message))],
            )
        imported: list[HankyungConsensusPdfTempSeedRecord] = []
        skipped = 0
        failed = 0
        for row in rows:
            seed = normalize_hankyung_report_row(
                row,
                base_url=self.settings.hankyung_consensus_api_base_url,
                allowed_pdf_hosts=self.settings.pdf_temp_allowed_hosts,
            )
            if seed is None:
                skipped += 1
                continue
            try:
                imported.append(await repository.upsert_crawler_seed(seed))
            except AppError as exc:
                failed += 1
                errors.append(str(redact_secrets(exc.message)))
        return HankyungConsensusImportResult(
            fetched=len(rows),
            imported=len(imported),
            skipped=skipped,
            failed=failed,
            seeds=imported,
            errors=errors,
        )

    def _bounded_request(self, request: HankyungConsensusCrawlRequest) -> HankyungConsensusCrawlRequest:
        today = date.today()
        from_date = request.from_date or (today - timedelta(days=30)).isoformat()
        to_date = request.to_date or today.isoformat()
        max_pages = min(request.max_pages or self.settings.hankyung_consensus_crawl_max_pages, self.settings.hankyung_consensus_crawl_max_pages)
        max_reports = min(
            request.max_reports or self.settings.hankyung_consensus_crawl_max_reports,
            self.settings.hankyung_consensus_crawl_max_reports,
        )
        return HankyungConsensusCrawlRequest(
            from_date=from_date,
            to_date=to_date,
            report_type=request.report_type or "ALL",
            page=max(request.page, 1),
            max_pages=max_pages,
            max_reports=max_reports,
            business_code=request.business_code,
            search_word=request.search_word,
            search_type=request.search_type,
        )

    def _params(self, request: HankyungConsensusCrawlRequest, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "page": page,
            "reportType": request.report_type,
            "fromDate": request.from_date,
            "toDate": request.to_date,
        }
        if request.business_code:
            params["businessCode"] = request.business_code
        if request.search_word:
            params["searchWord"] = request.search_word
        if request.search_type:
            params["searchType"] = request.search_type
        return {key: value for key, value in params.items() if value is not None}

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.settings.hankyung_consensus_crawl_user_agent}
        if self.settings.hankyung_consensus_auth_header_value:
            name, _, value = self.settings.hankyung_consensus_auth_header_value.partition(":")
            if value:
                headers[name.strip()] = value.strip()
            else:
                headers["Authorization"] = self.settings.hankyung_consensus_auth_header_value.strip()
        elif self.settings.hankyung_consensus_api_bearer_token_value:
            headers["Authorization"] = f"Bearer {self.settings.hankyung_consensus_api_bearer_token_value}"
        return headers


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise AppError(
            status_code=502,
            component="hankyung_consensus_crawler",
            code="crawler_unexpected_payload",
            message="Hankyung consensus crawler returned an unexpected payload",
        )
    for key in ("data", "list", "items", "reports", "rows", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_rows(value)
            if nested:
                return nested
    for value in payload.values():
        if isinstance(value, list) and any(isinstance(item, dict) and "REPORT_IDX" in item for item in value):
            return [item for item in value if isinstance(item, dict)]
    raise AppError(
        status_code=502,
        component="hankyung_consensus_crawler",
        code="crawler_unexpected_payload",
        message="Hankyung consensus crawler returned an unexpected payload",
    )


def _pdf_url_from_row(row: dict[str, Any], *, base_url: str) -> str | None:
    filepath = _clean_str(row.get("REPORT_FILEPATH"))
    filename = _clean_str(row.get("REPORT_FILENAME"))
    if not filepath:
        return None
    if filepath.lower().endswith(".pdf"):
        candidate = filepath
    elif filename:
        candidate = urljoin(filepath.rstrip("/") + "/", filename)
    else:
        return None
    if candidate.startswith("/"):
        candidate = urljoin(base_url.rstrip("/") + "/", candidate.lstrip("/"))
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def _is_allowed_pdf_url(url: str, allowed_hosts: list[str]) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and bool(host) and host in {item.lower() for item in allowed_hosts}


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_iso_date(value: Any) -> str | None:
    raw = _clean_str(value)
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def _strip_secret_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_secret_fields(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in _SECRET_KEY_PARTS)
        }
    if isinstance(value, list):
        return [_strip_secret_fields(item) for item in value]
    return value
