from __future__ import annotations

from pydantic import BaseModel


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
