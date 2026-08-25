from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.errors import AppError
from app.db.pdf_temp_repository import PdfTempPageRecord, new_page_id, utc_now_iso

PdfTextExtractionStatus = Literal["extracted", "ocr_required"]


@dataclass(frozen=True, slots=True)
class PdfTextExtractionResult:
    status: PdfTextExtractionStatus
    page_count: int
    total_chars: int
    pages: list[PdfTempPageRecord]
    failure_reason: str | None = None


def extract_pdf_text(pdf_id: str, pdf_path: str | Path, min_text_chars: int) -> PdfTextExtractionResult:
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="pdf_dependency_missing",
            message="PyMuPDF is required for PDF text extraction",
            details={"error": type(exc).__name__},
        ) from exc

    doc = None
    try:
        doc = pymupdf.open(str(pdf_path))
        page_count = int(getattr(doc, "page_count", len(doc)))
        pages: list[PdfTempPageRecord] = []
        created_at = utc_now_iso()
        for index, page in enumerate(doc, start=1):
            text = page.get_text() or ""
            pages.append(
                PdfTempPageRecord(
                    page_id=new_page_id(),
                    pdf_id=pdf_id,
                    page_number=index,
                    text=text,
                    char_count=len(text),
                    created_at=created_at,
                )
            )
        total_chars = sum(page.char_count for page in pages)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=400,
            component="pdf_temp",
            code="pdf_text_extraction_failed",
            message="PDF text extraction failed",
            details={"error": type(exc).__name__},
        ) from exc
    finally:
        if doc is not None:
            doc.close()

    if total_chars < min_text_chars:
        return PdfTextExtractionResult(
            status="ocr_required",
            page_count=page_count,
            total_chars=total_chars,
            pages=[],
            failure_reason=f"embedded text below threshold: {total_chars} chars",
        )
    return PdfTextExtractionResult(status="extracted", page_count=page_count, total_chars=total_chars, pages=pages)
