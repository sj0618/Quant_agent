from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AuthUser(BaseModel):
    id: str
    name: str | None = None
    email: str
    provider: str = "google"
    avatarUrl: str | None = None


class AuthMeResponse(BaseModel):
    user: AuthUser


class CsrfResponse(BaseModel):
    csrfToken: str


class GoogleAuthStartResponse(BaseModel):
    authorizationUrl: str


class GoogleAuthCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    state: str = Field(min_length=1)
    redirectUri: str = Field(min_length=1)


class AuthSessionResponse(BaseModel):
    user: AuthUser


class GoogleAuthCallbackResponse(BaseModel):
    session: AuthSessionResponse
    returnTo: str
