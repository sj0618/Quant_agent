from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import redact_secrets
from app.core.errors import AppError

PdfTempStatus = Literal["extracted", "duplicate", "failed", "ocr_required"]
_FILE_COLUMNS = (
    "pdf_id",
    "seed_id",
    "source_type",
    "safe_source_label",
    "stored_artifact_key",
    "original_filename",
    "file_hash",
    "size_bytes",
    "page_count",
    "status",
    "failure_reason",
    "canonical_pdf_id",
    "report_idx",
    "report_title",
    "company_name",
    "ticker",
    "broker",
    "report_date",
    "created_at",
    "updated_at",
)
_SEED_COLUMNS = (
    "seed_id",
    "report_idx",
    "report_title",
    "company_name",
    "ticker",
    "broker",
    "report_date",
    "pdf_url",
    "source_page_url",
    "source_report_type",
    "source_writer",
    "source_payload_hash",
    "status",
    "last_error",
)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_pdf_id() -> str:
    return f"pdf_{uuid4().hex}"


def new_page_id() -> str:
    return f"page_{uuid4().hex}"


@dataclass(slots=True)
class PdfTempFileRecord:
    pdf_id: str
    seed_id: str
    source_type: str
    safe_source_label: str
    stored_artifact_key: str | None
    original_filename: str | None
    file_hash: str | None
    size_bytes: int
    page_count: int
    status: PdfTempStatus
    failure_reason: str | None
    canonical_pdf_id: str | None
    created_at: str
    updated_at: str
    report_idx: str | None = None
    report_title: str | None = None
    company_name: str | None = None
    ticker: str | None = None
    broker: str | None = None
    report_date: date | str | None = None

    def response_payload(self) -> dict[str, Any]:
        return {
            "pdfId": self.pdf_id,
            "seedId": self.seed_id,
            "sourceType": self.source_type,
            "safeSourceLabel": self.safe_source_label,
            "reportIdx": self.report_idx,
            "reportTitle": self.report_title,
            "companyName": self.company_name,
            "ticker": self.ticker,
            "broker": self.broker,
            "reportDate": _date_to_iso(self.report_date),
            "artifactKey": self.stored_artifact_key,
            "originalFilename": self.original_filename,
            "fileHash": self.file_hash,
            "sizeBytes": self.size_bytes,
            "pageCount": self.page_count,
            "status": self.status,
            "failureReason": self.failure_reason,
            "canonicalPdfId": self.canonical_pdf_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass(slots=True)
class PdfTempPageRecord:
    page_id: str
    pdf_id: str
    page_number: int
    text: str
    char_count: int
    created_at: str

    def response_payload(self) -> dict[str, Any]:
        return {
            "pageId": self.page_id,
            "pdfId": self.pdf_id,
            "pageNumber": self.page_number,
            "text": self.text,
            "charCount": self.char_count,
            "createdAt": self.created_at,
        }


@dataclass(slots=True)
class HankyungConsensusPdfTempSeedRecord:
    seed_id: str
    report_idx: str
    report_title: str | None
    company_name: str | None
    ticker: str | None
    broker: str | None
    report_date: date | str | None
    pdf_url: str
    source_page_url: str | None = None
    source_report_type: str | None = None
    source_writer: str | None = None
    source_payload_hash: str | None = None
    status: str = "active"
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    last_imported_at: str | None = None
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def response_payload(self) -> dict[str, Any]:
        return {
            "seedId": self.seed_id,
            "reportIdx": self.report_idx,
            "title": self.report_title,
            "company": self.company_name,
            "ticker": self.ticker,
            "broker": self.broker,
            "reportDate": _date_to_iso(self.report_date),
            "pdfUrl": self.pdf_url,
            "sourcePageUrl": self.source_page_url,
            "sourceReportType": self.source_report_type,
            "sourceWriter": self.source_writer,
            "status": self.status,
            "firstSeenAt": self.first_seen_at,
            "lastSeenAt": self.last_seen_at,
            "lastImportedAt": self.last_imported_at,
            "lastError": self.last_error,
        }


class PdfTempRepository(Protocol):
    async def list_files(self) -> list[PdfTempFileRecord]: ...

    async def get_file(self, pdf_id: str) -> PdfTempFileRecord | None: ...

    async def list_pages(self, pdf_id: str) -> list[PdfTempPageRecord]: ...

    async def find_latest_by_seed(self, seed_id: str) -> PdfTempFileRecord | None: ...

    async def find_canonical_by_hash(self, file_hash: str) -> PdfTempFileRecord | None: ...

    async def save_file(
        self,
        record: PdfTempFileRecord,
        pages: list[PdfTempPageRecord] | None = None,
    ) -> PdfTempFileRecord: ...


class PdfTempManifestRepository:
    """Prototype-only JSON persistence for the PDF temp pipeline.

    This intentionally avoids creating DB tables until the user explicitly
    approves temp/test migrations.
    """

    def __init__(self, manifest_path: str | Path):
        self.manifest_path = Path(manifest_path)

    async def list_files(self) -> list[PdfTempFileRecord]:
        files, _pages = self._read()
        return sorted(files, key=lambda item: item.created_at, reverse=True)

    async def get_file(self, pdf_id: str) -> PdfTempFileRecord | None:
        files, _pages = self._read()
        return next((item for item in files if item.pdf_id == pdf_id), None)

    async def list_pages(self, pdf_id: str) -> list[PdfTempPageRecord]:
        _files, pages = self._read()
        return sorted((page for page in pages if page.pdf_id == pdf_id), key=lambda item: item.page_number)

    async def find_latest_by_seed(self, seed_id: str) -> PdfTempFileRecord | None:
        files, _pages = self._read()
        matches = [item for item in files if item.seed_id == seed_id]
        if not matches:
            return None
        return sorted(matches, key=lambda item: item.created_at, reverse=True)[0]

    async def find_canonical_by_hash(self, file_hash: str) -> PdfTempFileRecord | None:
        files, _pages = self._read()
        candidates = [
            item
            for item in files
            if item.file_hash == file_hash and item.status in {"extracted", "ocr_required"} and item.canonical_pdf_id is None
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item.created_at)[0]

    async def save_file(
        self,
        record: PdfTempFileRecord,
        pages: list[PdfTempPageRecord] | None = None,
    ) -> PdfTempFileRecord:
        files, existing_pages = self._read()
        files = [item for item in files if item.pdf_id != record.pdf_id]
        existing_pages = [page for page in existing_pages if page.pdf_id != record.pdf_id]
        files.append(record)
        if pages:
            existing_pages.extend(pages)
        self._write(files, existing_pages)
        return record

    def _read(self) -> tuple[list[PdfTempFileRecord], list[PdfTempPageRecord]]:
        if not self.manifest_path.exists():
            return [], []
        with self.manifest_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        files = [_file_record_from_mapping(item) for item in payload.get("files", [])]
        pages = [PdfTempPageRecord(**item) for item in payload.get("pages", [])]
        return files, pages

    def _write(self, files: list[PdfTempFileRecord], pages: list[PdfTempPageRecord]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "persistence": "prototype_manifest_not_production",
            "files": [asdict(item) for item in files],
            "pages": [asdict(item) for item in pages],
        }
        tmp_path = self.manifest_path.with_suffix(self.manifest_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.manifest_path)


class PdfTempDbRepository:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def list_files(self) -> list[PdfTempFileRecord]:
        rows = await self._fetch_all(
            """
            SELECT *
            FROM raw.hankyung_consensus_pdf_temp_files
            ORDER BY created_at DESC
            """
        )
        return [_file_record_from_row(row) for row in rows]

    async def get_file(self, pdf_id: str) -> PdfTempFileRecord | None:
        row = await self._fetch_one(
            """
            SELECT *
            FROM raw.hankyung_consensus_pdf_temp_files
            WHERE pdf_id = :pdf_id
            """,
            {"pdf_id": pdf_id},
        )
        return _file_record_from_row(row) if row else None

    async def list_pages(self, pdf_id: str) -> list[PdfTempPageRecord]:
        rows = await self._fetch_all(
            """
            SELECT *
            FROM raw.hankyung_consensus_pdf_temp_pages
            WHERE pdf_id = :pdf_id
            ORDER BY page_number
            """,
            {"pdf_id": pdf_id},
        )
        return [_page_record_from_row(row) for row in rows]

    async def find_latest_by_seed(self, seed_id: str) -> PdfTempFileRecord | None:
        row = await self._fetch_one(
            """
            SELECT *
            FROM raw.hankyung_consensus_pdf_temp_files
            WHERE seed_id = :seed_id
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"seed_id": seed_id},
        )
        return _file_record_from_row(row) if row else None

    async def find_canonical_by_hash(self, file_hash: str) -> PdfTempFileRecord | None:
        row = await self._fetch_one(
            """
            SELECT *
            FROM raw.hankyung_consensus_pdf_temp_files
            WHERE file_hash = :file_hash
              AND status IN ('extracted', 'ocr_required')
              AND canonical_pdf_id IS NULL
            ORDER BY created_at ASC
            LIMIT 1
            """,
            {"file_hash": file_hash},
        )
        return _file_record_from_row(row) if row else None

    async def save_file(
        self,
        record: PdfTempFileRecord,
        pages: list[PdfTempPageRecord] | None = None,
    ) -> PdfTempFileRecord:
        try:
            async with self.engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM raw.hankyung_consensus_pdf_temp_pages WHERE pdf_id = :pdf_id"),
                    {"pdf_id": record.pdf_id},
                )
                await conn.execute(
                    text(
                        f"""
                        INSERT INTO raw.hankyung_consensus_pdf_temp_files ({", ".join(_FILE_COLUMNS)})
                        VALUES ({", ".join(f":{column}" for column in _FILE_COLUMNS)})
                        ON CONFLICT (pdf_id)
                        DO UPDATE SET
                            seed_id = EXCLUDED.seed_id,
                            source_type = EXCLUDED.source_type,
                            safe_source_label = EXCLUDED.safe_source_label,
                            stored_artifact_key = EXCLUDED.stored_artifact_key,
                            original_filename = EXCLUDED.original_filename,
                            file_hash = EXCLUDED.file_hash,
                            size_bytes = EXCLUDED.size_bytes,
                            page_count = EXCLUDED.page_count,
                            status = EXCLUDED.status,
                            failure_reason = EXCLUDED.failure_reason,
                            canonical_pdf_id = EXCLUDED.canonical_pdf_id,
                            report_idx = EXCLUDED.report_idx,
                            report_title = EXCLUDED.report_title,
                            company_name = EXCLUDED.company_name,
                            ticker = EXCLUDED.ticker,
                            broker = EXCLUDED.broker,
                            report_date = EXCLUDED.report_date,
                            updated_at = EXCLUDED.updated_at
                        """
                    ),
                    _file_params(record),
                )
                if pages:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO raw.hankyung_consensus_pdf_temp_pages (
                                page_id, pdf_id, page_number, text, char_count, created_at
                            )
                            VALUES (
                                :page_id, :pdf_id, :page_number, :text, :char_count, :created_at
                            )
                            ON CONFLICT (page_id)
                            DO UPDATE SET
                                pdf_id = EXCLUDED.pdf_id,
                                page_number = EXCLUDED.page_number,
                                text = EXCLUDED.text,
                                char_count = EXCLUDED.char_count
                            """
                        ),
                        [_page_params(page) for page in pages],
                    )
            return record
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="db",
                code="pdf_temp_db_write_failed",
                message="PDF temp DB write failed",
                details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
            ) from exc

    async def list_crawler_seeds(
        self,
        *,
        status: str | None = "active",
        ticker: str | None = None,
    ) -> list[HankyungConsensusPdfTempSeedRecord]:
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if status is not None:
            conditions.append("status = :status")
            params["status"] = status
        if ticker:
            conditions.append("ticker = :ticker")
            params["ticker"] = ticker
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await self._fetch_seed_all(
            f"""
            SELECT *
            FROM raw.hankyung_consensus_pdf_temp_seeds
            {where_clause}
            ORDER BY report_date DESC NULLS LAST, last_seen_at DESC
            """,
            params,
        )
        return [_seed_record_from_row(row) for row in rows]

    async def get_crawler_seed(self, seed_id: str) -> HankyungConsensusPdfTempSeedRecord | None:
        row = await self._fetch_seed_one(
            """
            SELECT *
            FROM raw.hankyung_consensus_pdf_temp_seeds
            WHERE seed_id = :seed_id
            """,
            {"seed_id": seed_id},
        )
        return _seed_record_from_row(row) if row else None

    async def upsert_crawler_seed(
        self,
        record: HankyungConsensusPdfTempSeedRecord,
    ) -> HankyungConsensusPdfTempSeedRecord:
        try:
            async with self.engine.begin() as conn:
                await conn.execute(
                    text(
                        f"""
                        INSERT INTO raw.hankyung_consensus_pdf_temp_seeds ({", ".join(_SEED_COLUMNS)})
                        VALUES ({", ".join(f":{column}" for column in _SEED_COLUMNS)})
                        ON CONFLICT (report_idx)
                        DO UPDATE SET
                            seed_id = EXCLUDED.seed_id,
                            report_title = EXCLUDED.report_title,
                            company_name = EXCLUDED.company_name,
                            ticker = EXCLUDED.ticker,
                            broker = EXCLUDED.broker,
                            report_date = EXCLUDED.report_date,
                            pdf_url = EXCLUDED.pdf_url,
                            source_page_url = EXCLUDED.source_page_url,
                            source_report_type = EXCLUDED.source_report_type,
                            source_writer = EXCLUDED.source_writer,
                            source_payload_hash = EXCLUDED.source_payload_hash,
                            status = CASE
                                WHEN raw.hankyung_consensus_pdf_temp_seeds.status = 'disabled'
                                    THEN raw.hankyung_consensus_pdf_temp_seeds.status
                                ELSE 'active'
                            END,
                            last_seen_at = now(),
                            last_imported_at = now(),
                            last_error = NULL,
                            updated_at = now()
                        """
                    ),
                    _seed_params(record),
                )
            saved = await self.get_crawler_seed(record.seed_id)
            if saved is None:
                raise AppError(
                    status_code=503,
                    component="db",
                    code="pdf_temp_seed_db_write_failed",
                    message="PDF temp crawler seed DB write failed",
                )
            return saved
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="db",
                code="pdf_temp_seed_db_write_failed",
                message="PDF temp crawler seed DB write failed",
                details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
            ) from exc

    async def _fetch_all(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            async with self.engine.connect() as conn:
                result = await conn.execute(text(sql), params or {})
                return [dict(row) for row in result.mappings().all()]
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="db",
                code="pdf_temp_db_query_failed",
                message="PDF temp DB query failed",
                details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
            ) from exc

    async def _fetch_one(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        rows = await self._fetch_all(sql, params)
        return rows[0] if rows else None

    async def _fetch_seed_all(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            async with self.engine.connect() as conn:
                result = await conn.execute(text(sql), params or {})
                return [dict(row) for row in result.mappings().all()]
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=503,
                component="db",
                code="pdf_temp_seed_db_unavailable",
                message="PDF temp crawler seed DB is unavailable",
                details={"error": redact_secrets(f"{type(exc).__name__}: {exc}")},
            ) from exc

    async def _fetch_seed_one(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        rows = await self._fetch_seed_all(sql, params)
        return rows[0] if rows else None


def _file_record_from_row(row: dict[str, Any]) -> PdfTempFileRecord:
    return PdfTempFileRecord(
        pdf_id=str(row["pdf_id"]),
        seed_id=str(row["seed_id"]),
        source_type=str(row["source_type"]),
        safe_source_label=str(row["safe_source_label"]),
        stored_artifact_key=_optional_string(row.get("stored_artifact_key")),
        original_filename=_optional_string(row.get("original_filename")),
        file_hash=_optional_string(row.get("file_hash")),
        size_bytes=int(row.get("size_bytes") or 0),
        page_count=int(row.get("page_count") or 0),
        status=str(row["status"]),  # type: ignore[arg-type]
        failure_reason=_optional_string(row.get("failure_reason")),
        canonical_pdf_id=_optional_string(row.get("canonical_pdf_id")),
        created_at=_timestamp_to_iso(row["created_at"]),
        updated_at=_timestamp_to_iso(row["updated_at"]),
        report_idx=_optional_string(row.get("report_idx")),
        report_title=_optional_string(row.get("report_title")),
        company_name=_optional_string(row.get("company_name")),
        ticker=_optional_string(row.get("ticker")),
        broker=_optional_string(row.get("broker")),
        report_date=_date_to_iso(row.get("report_date")),
    )


def _page_record_from_row(row: dict[str, Any]) -> PdfTempPageRecord:
    return PdfTempPageRecord(
        page_id=str(row["page_id"]),
        pdf_id=str(row["pdf_id"]),
        page_number=int(row["page_number"]),
        text=str(row.get("text") or ""),
        char_count=int(row.get("char_count") or 0),
        created_at=_timestamp_to_iso(row["created_at"]),
    )


def _seed_record_from_row(row: dict[str, Any]) -> HankyungConsensusPdfTempSeedRecord:
    return HankyungConsensusPdfTempSeedRecord(
        seed_id=str(row["seed_id"]),
        report_idx=str(row["report_idx"]),
        report_title=_optional_string(row.get("report_title")),
        company_name=_optional_string(row.get("company_name")),
        ticker=_optional_string(row.get("ticker")),
        broker=_optional_string(row.get("broker")),
        report_date=_date_to_iso(row.get("report_date")),
        pdf_url=str(row["pdf_url"]),
        source_page_url=_optional_string(row.get("source_page_url")),
        source_report_type=_optional_string(row.get("source_report_type")),
        source_writer=_optional_string(row.get("source_writer")),
        source_payload_hash=_optional_string(row.get("source_payload_hash")),
        status=str(row.get("status") or "active"),
        first_seen_at=_timestamp_to_iso(row["first_seen_at"]) if row.get("first_seen_at") is not None else None,
        last_seen_at=_timestamp_to_iso(row["last_seen_at"]) if row.get("last_seen_at") is not None else None,
        last_imported_at=_timestamp_to_iso(row["last_imported_at"]) if row.get("last_imported_at") is not None else None,
        last_error=_optional_string(row.get("last_error")),
        created_at=_timestamp_to_iso(row["created_at"]) if row.get("created_at") is not None else None,
        updated_at=_timestamp_to_iso(row["updated_at"]) if row.get("updated_at") is not None else None,
    )


def _file_params(record: PdfTempFileRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["created_at"] = _iso_to_datetime(record.created_at)
    payload["updated_at"] = _iso_to_datetime(record.updated_at)
    payload["report_date"] = _iso_to_date(record.report_date)
    return payload


def _page_params(page: PdfTempPageRecord) -> dict[str, Any]:
    payload = asdict(page)
    payload["created_at"] = _iso_to_datetime(page.created_at)
    return payload


def _seed_params(record: HankyungConsensusPdfTempSeedRecord) -> dict[str, Any]:
    return {
        "seed_id": record.seed_id,
        "report_idx": record.report_idx,
        "report_title": record.report_title,
        "company_name": record.company_name,
        "ticker": record.ticker,
        "broker": record.broker,
        "report_date": _iso_to_date(record.report_date),
        "pdf_url": record.pdf_url,
        "source_page_url": record.source_page_url,
        "source_report_type": record.source_report_type,
        "source_writer": record.source_writer,
        "source_payload_hash": record.source_payload_hash,
        "status": record.status,
        "last_error": record.last_error,
    }


def _timestamp_to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


def _date_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _iso_to_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _iso_to_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _file_record_from_mapping(item: Any) -> PdfTempFileRecord:
    if not isinstance(item, dict):
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="invalid_manifest",
            message="PDF temp manifest file entries must be objects",
        )
    normalized = {
        "report_idx": None,
        "report_title": None,
        "company_name": None,
        "ticker": None,
        "broker": None,
        "report_date": None,
        **item,
    }
    normalized["report_date"] = _date_to_iso(normalized.get("report_date"))
    return PdfTempFileRecord(**normalized)
