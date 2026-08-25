from __future__ import annotations

from fastapi import APIRouter, Request

from app.dependencies import get_runtime_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings = get_runtime_settings(request)
    return {"status": "ok", "component": "backend", "config": settings.safe_summary()}
