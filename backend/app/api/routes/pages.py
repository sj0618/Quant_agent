from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from app.dependencies import get_redis_client, get_runtime_settings
from app.services.session_store import AuthSessionStore

router = APIRouter(tags=["pages"])
FE_DIST_DIR = Path(__file__).resolve().parents[4] / "fe" / "dist"
STATIC_AUTH_DIR = Path(__file__).resolve().parents[2] / "static" / "auth"


async def _has_valid_session(request: Request) -> bool:
    settings = get_runtime_settings(request)
    session_id = request.cookies.get(settings.auth_session_cookie_name)
    if not session_id:
        return False
    store = AuthSessionStore(get_redis_client(request), settings)
    return await store.get_session_user_id(session_id) is not None


def _frontend_index_path() -> Path | None:
    index_path = FE_DIST_DIR / "index.html"
    return index_path if index_path.is_file() else None


def _resolve_frontend_asset(full_path: str) -> Path | None:
    if not full_path:
        return None
    frontend_root = FE_DIST_DIR.resolve()
    candidate = (FE_DIST_DIR / full_path).resolve()
    try:
        candidate.relative_to(frontend_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _frontend_index_response() -> FileResponse:
    index_path = _frontend_index_path()
    if index_path is None:
        raise HTTPException(status_code=503, detail="frontend build is not available")
    return FileResponse(index_path, media_type="text/html; charset=utf-8")


@router.get("/login", include_in_schema=False)
async def login_page(request: Request):
    if await _has_valid_session(request):
        return RedirectResponse("/app", status_code=303)
    index_path = _frontend_index_path()
    if index_path is not None:
        return FileResponse(index_path, media_type="text/html; charset=utf-8")
    return FileResponse(STATIC_AUTH_DIR / "login.html", media_type="text/html; charset=utf-8")


@router.get("/app", include_in_schema=False)
async def app_page(request: Request):
    if not await _has_valid_session(request):
        return RedirectResponse("/login", status_code=303)
    index_path = _frontend_index_path()
    if index_path is not None:
        return FileResponse(index_path, media_type="text/html; charset=utf-8")
    return FileResponse(STATIC_AUTH_DIR / "app.html", media_type="text/html; charset=utf-8")


@router.get("/", include_in_schema=False)
async def frontend_root():
    return _frontend_index_response()


@router.get("/{full_path:path}", include_in_schema=False)
async def frontend_spa_fallback(full_path: str):
    if full_path.startswith(
        (
            "api/",
            "ai-api/",
            "auth/",
            "analysis-jobs",
            "api-status",
            "static/",
            "health",
            "combined-health",
            "docs",
            "redoc",
            "openapi.json",
        )
    ):
        raise HTTPException(status_code=404)
    asset_path = _resolve_frontend_asset(full_path)
    if asset_path is not None:
        return FileResponse(asset_path)
    return _frontend_index_response()
