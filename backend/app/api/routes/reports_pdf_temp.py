from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import csrf_token_required, require_csrf_token, validate_unsafe_request_origin
from app.db.pdf_temp_repository import PdfTempDbRepository, PdfTempManifestRepository, PdfTempRepository
from app.dependencies import get_db_engine, get_redis_client, get_runtime_settings
from app.schemas.pdf_temp import (
    HankyungConsensusCrawlerImportRequest,
    HankyungConsensusCrawlerImportResponse,
    HankyungConsensusCrawlerSeedDetailResponse,
    HankyungConsensusCrawlerSeedsResponse,
    PdfTempDetailResponse,
    PdfTempIngestRequest,
    PdfTempIngestResponse,
    PdfTempListResponse,
    PdfTempPagesResponse,
    PdfTempSeedsResponse,
)
from app.services.hankyung_consensus_crawler import HankyungConsensusCrawler, HankyungConsensusCrawlRequest
from app.services.pdf_temp_ingest import PdfTempIngestService
from app.services.pdf_temp_seed_registry import CombinedPdfTempSeedProvider, DbPdfTempSeedProvider, EnvPdfTempSeedProvider
from app.services.session_store import AuthSessionStore

router = APIRouter(prefix="/reports/pdf-temp", tags=["reports"])


async def require_pdf_temp_access(request: Request) -> Settings:
    settings = get_runtime_settings(request)
    _require_pdf_temp_enabled(settings)
    await _require_authenticated_session(request, settings)
    return settings


async def require_pdf_temp_ingest_access(request: Request) -> Settings:
    settings = await require_pdf_temp_access(request)
    validate_unsafe_request_origin(request, settings)
    if csrf_token_required(settings):
        session_id = request.cookies.get(settings.auth_session_cookie_name)
        store = AuthSessionStore(get_redis_client(request), settings)
        require_csrf_token(request.headers.get("X-CSRF-Token"), await store.get_csrf_token(session_id))
    return settings


async def require_pdf_temp_crawler_access(request: Request) -> Settings:
    settings = get_runtime_settings(request)
    _require_pdf_temp_enabled(settings)
    if not settings.hankyung_consensus_crawler_enabled:
        raise AppError(
            status_code=503,
            component="hankyung_consensus_crawler",
            code="hankyung_consensus_crawler_disabled",
            message="Hankyung consensus crawler is disabled",
        )
    await _require_authenticated_session(request, settings)
    return settings


def _require_pdf_temp_enabled(settings: Settings) -> None:
    if not settings.pdf_temp_ingest_enabled:
        raise AppError(
            status_code=503,
            component="pdf_temp",
            code="pdf_temp_ingest_disabled",
            message="PDF temp ingest is disabled",
        )


async def _require_authenticated_session(request: Request, settings: Settings) -> None:
    session_id = request.cookies.get(settings.auth_session_cookie_name)
    store = AuthSessionStore(get_redis_client(request), settings)
    user_id = await store.get_session_user_id(session_id)
    if not user_id:
        raise AppError(status_code=401, component="auth", code="not_authenticated", message="Authentication required")


def get_pdf_temp_repository(request: Request, settings: Settings) -> PdfTempRepository:
    if settings.pdf_temp_persistence == "db":
        return PdfTempDbRepository(get_db_engine(request))
    return PdfTempManifestRepository(settings.pdf_temp_manifest_path)


def get_pdf_temp_db_repository(request: Request) -> PdfTempDbRepository:
    return PdfTempDbRepository(get_db_engine(request))


def get_seed_provider(request: Request, settings: Settings):
    env_provider = EnvPdfTempSeedProvider.from_settings(settings)
    db_provider = DbPdfTempSeedProvider(get_pdf_temp_db_repository(request)) if settings.pdf_temp_persistence == "db" else None
    return CombinedPdfTempSeedProvider(env_provider, db_provider)


@router.get("/seeds", response_model=PdfTempSeedsResponse)
async def list_pdf_temp_seeds(request: Request) -> dict[str, object]:
    settings = await require_pdf_temp_access(request)
    provider = get_seed_provider(request, settings)
    return {"seeds": [seed.safe_payload() for seed in await provider.list()]}


@router.post("/ingest", response_model=PdfTempIngestResponse)
async def ingest_pdf_temp_seeds(request: Request, payload: PdfTempIngestRequest | None = None) -> dict[str, object]:
    settings = await require_pdf_temp_ingest_access(request)
    repository = get_pdf_temp_repository(request, settings)
    service = PdfTempIngestService(settings, repository, get_seed_provider(request, settings))
    results = await service.ingest(payload.seedIds if payload else None, force=payload.force if payload else False)
    return {"results": [item.response_payload() for item in results]}


@router.get("/crawler/seeds", response_model=HankyungConsensusCrawlerSeedsResponse)
async def list_hankyung_consensus_crawler_seeds(request: Request) -> dict[str, object]:
    await require_pdf_temp_crawler_access(request)
    repository = get_pdf_temp_db_repository(request)
    return {"seeds": [item.response_payload() for item in await repository.list_crawler_seeds(status="active")]}


@router.post("/crawler/import", response_model=HankyungConsensusCrawlerImportResponse)
async def import_hankyung_consensus_crawler_seeds(
    request: Request,
    payload: HankyungConsensusCrawlerImportRequest | None = None,
) -> dict[str, object]:
    settings = await require_pdf_temp_crawler_access(request)
    validate_unsafe_request_origin(request, settings)
    if csrf_token_required(settings):
        session_id = request.cookies.get(settings.auth_session_cookie_name)
        store = AuthSessionStore(get_redis_client(request), settings)
        require_csrf_token(request.headers.get("X-CSRF-Token"), await store.get_csrf_token(session_id))
    request_payload = payload or HankyungConsensusCrawlerImportRequest()
    business_code = request_payload.businessCode or request_payload.ticker
    result = await HankyungConsensusCrawler(settings).import_reports(
        HankyungConsensusCrawlRequest(
            from_date=request_payload.fromDate,
            to_date=request_payload.toDate,
            report_type=request_payload.reportType,
            page=request_payload.page,
            max_pages=request_payload.maxPages,
            max_reports=request_payload.maxReports,
            business_code=business_code,
            search_word=request_payload.searchWord,
            search_type=request_payload.searchType,
        ),
        get_pdf_temp_db_repository(request),
    )
    return {
        "fetched": result.fetched,
        "imported": result.imported,
        "skipped": result.skipped,
        "failed": result.failed,
        "seeds": [item.response_payload() for item in result.seeds],
        "errors": result.errors,
    }


@router.get("/crawler/seeds/{seed_id}", response_model=HankyungConsensusCrawlerSeedDetailResponse)
async def get_hankyung_consensus_crawler_seed(request: Request, seed_id: str) -> dict[str, object]:
    await require_pdf_temp_crawler_access(request)
    repository = get_pdf_temp_db_repository(request)
    item = await repository.get_crawler_seed(seed_id)
    if item is None:
        raise AppError(
            status_code=404,
            component="hankyung_consensus_crawler",
            code="crawler_seed_not_found",
            message="Hankyung consensus crawler seed was not found",
        )
    return {"seed": item.response_payload()}


@router.get("", response_model=PdfTempListResponse)
async def list_pdf_temp_files(request: Request) -> dict[str, object]:
    settings = await require_pdf_temp_access(request)
    repository = get_pdf_temp_repository(request, settings)
    return {"items": [item.response_payload() for item in await repository.list_files()]}


@router.get("/{pdf_id}", response_model=PdfTempDetailResponse)
async def get_pdf_temp_file(request: Request, pdf_id: str) -> dict[str, object]:
    settings = await require_pdf_temp_access(request)
    repository = get_pdf_temp_repository(request, settings)
    item = await repository.get_file(pdf_id)
    if item is None:
        raise AppError(status_code=404, component="pdf_temp", code="pdf_not_found", message="PDF temp record was not found")
    return {"item": item.response_payload()}


@router.get("/{pdf_id}/pages", response_model=PdfTempPagesResponse)
async def list_pdf_temp_pages(request: Request, pdf_id: str) -> dict[str, object]:
    settings = await require_pdf_temp_access(request)
    repository = get_pdf_temp_repository(request, settings)
    item = await repository.get_file(pdf_id)
    if item is None:
        raise AppError(status_code=404, component="pdf_temp", code="pdf_not_found", message="PDF temp record was not found")
    return {"pages": [page.response_payload() for page in await repository.list_pages(pdf_id)]}
