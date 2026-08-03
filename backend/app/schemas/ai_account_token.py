from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IssueAccountTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Only a human-readable name is accepted. Quota fields are assigned by the server -
    # a caller who could pick their own allowance could opt out of the limit entirely.
    label: str | None = Field(default=None, max_length=100)


class IssueAccountTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_id: str
    # Returned by this endpoint and nowhere else: only the digest is stored, so a token
    # that is not saved now cannot be recovered later, only replaced.
    raw_token: str
    token_prefix: str
    label: str | None
    quota_limit: int
    quota_window_seconds: int
    created_at: datetime


class AccountTokenSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_id: str
    label: str | None
    token_prefix: str
    quota_limit: int
    quota_window_seconds: int
    status: str
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class ListAccountTokensResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tokens: list[AccountTokenSummary]
