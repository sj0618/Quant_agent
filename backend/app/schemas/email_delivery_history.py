from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmailDeliveryHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    deliveryId: str
    reportId: str | None = None
    reportTitle: str | None = None
    strategyId: str | None = None
    strategyName: str | None = None
    triggerType: str
    templateName: str
    submissionStatus: str
    providerSubmissionStatus: str | None = None
    providerDeliveryStatus: str | None = None
    providerStatusCheckedAt: datetime | None = None
    providerEventAt: datetime | None = None
    providerStatusSource: str | None = None
    status: str
    reportDate: str | None = None
    createdAt: datetime
    sentAt: datetime | None = None
    deliveredAt: datetime | None = None
    failedAt: datetime | None = None
    lastEventAt: datetime | None = None
    attemptCount: int = 0
    maxAttempts: int = 0
    safeFailureCategory: str | None = None


class EmailDeliveryHistoryMeta(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    limit: int
    hasMore: bool
    nextCursor: str | None = None


class EmailDeliveryHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    items: list[EmailDeliveryHistoryEntry]
    meta: EmailDeliveryHistoryMeta
