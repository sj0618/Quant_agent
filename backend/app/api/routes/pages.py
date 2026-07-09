from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from app.dependencies import get_redis_client, get_runtime_settings
from app.services.session_store import AuthSessionStore

router = APIRouter(tags=["pages"])
STATIC_AUTH_DIR = Path(__file__).resolve().parents[2] / "static" / "auth"


async def _has_valid_session(request: Request) -> bool:
    settings = get_runtime_settings(request)
    session_id = request.cookies.get(settings.auth_session_cookie_name)
    if not session_id:
        return False
    store = AuthSessionStore(get_redis_client(request), settings)
    return await store.get_session_user_id(session_id) is not None


@router.get("/login", include_in_schema=False)
async def login_page(request: Request):
    if await _has_valid_session(request):
        return RedirectResponse("/app", status_code=303)
    return FileResponse(STATIC_AUTH_DIR / "login.html", media_type="text/html; charset=utf-8")


@router.get("/app", include_in_schema=False)
async def app_page(request: Request):
    if not await _has_valid_session(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC_AUTH_DIR / "app.html", media_type="text/html; charset=utf-8")
