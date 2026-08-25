from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EmailStrategySubscriptionItem(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    strategyId: str
    displayName: str | None = None
    enabled: bool
    createdAt: datetime
    updatedAt: datetime


class EmailStrategySubscriptionsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    items: list[EmailStrategySubscriptionItem]
    subscriptionCount: int
    maxSubscriptions: int = Field(default=3, ge=1)


class EmailStrategySubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    strategyId: str = Field(min_length=1)
    displayName: str | None = None
