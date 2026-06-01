from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PdfTempSourceType = Literal["url", "file"]
PdfTempStatus = Literal["extracted", "duplicate", "failed", "ocr_required"]


class PdfTempSeedResponse(BaseModel):
    seedId: str
    sourceType: PdfTempSourceType
    label: str
    enabled: bool
    reportIdx: str | None = None
    title: str | None = None
    company: str | None = None
    ticker: str | None = None
    broker: str | None = None
    reportDate: str | None = None


class PdfTempIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seedIds: list[str] | None = Field(default=None, max_length=10)
    force: bool = False


class PdfTempFileResponse(BaseModel):
    pdfId: str
    seedId: str
    sourceType: PdfTempSourceType
    safeSourceLabel: str
    reportIdx: str | None = None
    reportTitle: str | None = None
    companyName: str | None = None
    ticker: str | None = None
    broker: str | None = None
    reportDate: str | None = None
    artifactKey: str | None = None
    originalFilename: str | None = None
    fileHash: str | None = None
    sizeBytes: int = 0
    pageCount: int = 0
    status: PdfTempStatus
    failureReason: str | None = None
    canonicalPdfId: str | None = None
    createdAt: str
    updatedAt: str


class PdfTempPageResponse(BaseModel):
    pageId: str
    pdfId: str
    pageNumber: int
    text: str
    charCount: int
    createdAt: str


class PdfTempSeedsResponse(BaseModel):
    seeds: list[PdfTempSeedResponse]


class PdfTempIngestResponse(BaseModel):
    results: list[PdfTempFileResponse]


class PdfTempListResponse(BaseModel):
    items: list[PdfTempFileResponse]


class PdfTempDetailResponse(BaseModel):
    item: PdfTempFileResponse


class PdfTempPagesResponse(BaseModel):
    pages: list[PdfTempPageResponse]


class HankyungConsensusCrawlerImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fromDate: str | None = None
    toDate: str | None = None
    reportType: str = "ALL"
    page: int = Field(default=1, ge=1)
    maxPages: int | None = Field(default=None, ge=1)
    maxReports: int | None = Field(default=None, ge=1)
    ticker: str | None = None
    businessCode: str | None = None
    searchWord: str | None = None
    searchType: str | None = None

    @field_validator("fromDate", "toDate")
    @classmethod
    def validate_optional_iso_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) != 10 or normalized[4] != "-" or normalized[7] != "-":
            raise ValueError("date must use YYYY-MM-DD")
        return date.fromisoformat(normalized).isoformat()


class HankyungConsensusCrawlerSeedResponse(BaseModel):
    seedId: str
    reportIdx: str
    title: str | None = None
    company: str | None = None
    ticker: str | None = None
    broker: str | None = None
    reportDate: str | None = None
    pdfUrl: str
    sourcePageUrl: str | None = None
    sourceReportType: str | None = None
    sourceWriter: str | None = None
    status: str
    firstSeenAt: str | None = None
    lastSeenAt: str | None = None
    lastImportedAt: str | None = None
    lastError: str | None = None


class HankyungConsensusCrawlerSeedsResponse(BaseModel):
    seeds: list[HankyungConsensusCrawlerSeedResponse]


class HankyungConsensusCrawlerImportResponse(BaseModel):
    fetched: int
    imported: int
    skipped: int
    failed: int
    seeds: list[HankyungConsensusCrawlerSeedResponse]
    errors: list[str] = Field(default_factory=list)


class HankyungConsensusCrawlerSeedDetailResponse(BaseModel):
    seed: HankyungConsensusCrawlerSeedResponse
