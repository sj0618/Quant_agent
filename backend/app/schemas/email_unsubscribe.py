from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class UnsubscribeInspectionResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    status: Literal["ready", "already_unsubscribed"]
    actionEmails: bool


class UnsubscribeMutationResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    status: Literal["unsubscribed", "already_unsubscribed"]
    actionEmails: bool = False
