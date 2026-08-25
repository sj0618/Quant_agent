"""Reader-safe response schemas for the archived-result browser endpoints.

These models are deliberately narrower than the persisted Track C report.  The
browser may inspect only stable identifiers, lifecycle metadata, and the two
allow-listed verification-evidence sections.  Internal persistence and
operator workflows continue to use the full report query contract.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ArchivedReportEvidenceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: str
    depth: int = Field(ge=0)
    description: str | None = None


class ArchivedReportEvidenceSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    note: str | None = None
    entries: list[ArchivedReportEvidenceEntry]


class ArchivedReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    runId: str | None = None
    date: str
    weekday: str
    sentAt: str
    status: str
    createdAt: str | None = None
    updatedAt: str | None = None
    publishedAt: str | None = None


class ArchivedReportDetail(ArchivedReportSummary):
    contentSections: list[ArchivedReportEvidenceSection] = Field(default_factory=list)


class ArchivedReportListMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(ge=1)
    hasMore: bool
    nextCursor: str | None = None


class ArchivedReportListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ArchivedReportSummary]
    meta: ArchivedReportListMeta
