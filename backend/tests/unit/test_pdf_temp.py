from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import reports_pdf_temp
from app.core.errors import AppError
from app.core.errors import register_exception_handlers
from app.db.pdf_temp_repository import HankyungConsensusPdfTempSeedRecord, PdfTempFileRecord, PdfTempManifestRepository, utc_now_iso
from app.services.pdf_temp_seed_registry import PdfTempSeedRegistry
from app.services.session_store import AuthSessionStore
from tests.unit.test_hankyung_consensus_crawler import SAMPLE_ROW, crawler_response, install_fake_crawler_http
from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis


def make_pdf(path: Path, page_texts: list[str]) -> None:
    import pymupdf

    doc = pymupdf.open()
    try:
        for text in page_texts:
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), text)
        doc.save(path)
    finally:
        doc.close()


def pdf_bytes(tmp_path: Path, page_texts: list[str]) -> bytes:
    path = tmp_path / "source.pdf"
    make_pdf(path, page_texts)
    return path.read_bytes()


def pdf_settings(tmp_path: Path, seeds: list[dict], **overrides):
    seed_dir = tmp_path / "seeds"
    storage_dir = tmp_path / "storage"
    seed_dir.mkdir(parents=True, exist_ok=True)
    values = {
        "APP_ENV": "local",
        "PDF_TEMP_INGEST_ENABLED": True,
        "PDF_TEMP_SEED_DIR": str(seed_dir),
        "PDF_TEMP_STORAGE_DIR": str(storage_dir),
        "PDF_TEMP_MANIFEST_PATH": str(tmp_path / "manifest.json"),
        "PDF_TEMP_PERSISTENCE": "manifest",
        "PDF_TEMP_SEED_REGISTRY_JSON": json.dumps(seeds),
        "PDF_TEMP_URL_ALLOWED_HOSTS": "reports.example.com",
        "PDF_TEMP_MIN_TEXT_CHARS": 10,
        "PDF_TEMP_MAX_SEED_BATCH_SIZE": 3,
    }
    values.update(overrides)
    return valid_settings(**values)


class FakeStream:
    def __init__(self, response: httpx.Response | Exception):
        self.response = response

    async def __aenter__(self):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def __aexit__(self, *_exc):
        return None


class SequenceAsyncClient:
    requests: list[str] = []
    responses: list[httpx.Response | Exception] = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    def stream(self, method, url):
        assert method == "GET"
        self.__class__.requests.append(url)
        if not self.__class__.responses:
            raise AssertionError("No fake response configured")
        return FakeStream(self.__class__.responses.pop(0))


def fake_response(url: str, *, status_code: int = 200, content: bytes = b"", headers: dict[str, str] | None = None):
    return httpx.Response(
        status_code,
        content=content,
        headers=headers or {"content-type": "application/pdf"},
        request=httpx.Request("GET", url),
    )


def install_fake_http(monkeypatch, responses: list[httpx.Response | Exception]):
    SequenceAsyncClient.requests = []
    SequenceAsyncClient.responses = responses
    monkeypatch.setattr("app.services.pdf_temp_ingest.httpx.AsyncClient", SequenceAsyncClient)
    return SequenceAsyncClient


def make_client(settings):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(reports_pdf_temp.router)
    app.state.settings = settings
    app.state.redis_client = FakeRedis()
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    return TestClient(app, base_url="https://api.example.co.kr", headers={"Origin": "https://api.example.co.kr"}), app


class FakeCrawlerSeedRepository:
    def __init__(self, seeds: list[HankyungConsensusPdfTempSeedRecord] | None = None):
        self.seeds: dict[str, HankyungConsensusPdfTempSeedRecord] = {seed.seed_id: seed for seed in seeds or []}

    async def list_crawler_seeds(self, *, status: str | None = "active", ticker: str | None = None):
        values = list(self.seeds.values())
        if status is not None:
            values = [seed for seed in values if seed.status == status]
        if ticker:
            values = [seed for seed in values if seed.ticker == ticker]
        return values

    async def get_crawler_seed(self, seed_id: str):
        return self.seeds.get(seed_id)

    async def upsert_crawler_seed(self, record: HankyungConsensusPdfTempSeedRecord):
        self.seeds[record.seed_id] = record
        return record


def crawler_seed(seed_id: str = "hankyung-crawl-649784", **overrides) -> HankyungConsensusPdfTempSeedRecord:
    report_idx = seed_id.removeprefix("hankyung-crawl-")
    values = {
        "seed_id": seed_id,
        "report_idx": report_idx,
        "report_title": "아모레퍼시픽(090430) 1Q26 Review",
        "company_name": "아모레퍼시픽",
        "ticker": "090430",
        "broker": "유진투자증권",
        "report_date": "2026-05-29",
        "pdf_url": "https://reports.example.com/sample.pdf",
        "source_page_url": "https://markets.hankyung.com/consensus/report/649784",
        "source_report_type": "CO",
        "source_writer": "이해니",
        "source_payload_hash": "hash",
        "status": "active",
        "first_seen_at": "2026-05-30T00:00:00Z",
        "last_seen_at": "2026-05-30T00:00:00Z",
        "last_imported_at": "2026-05-30T00:00:00Z",
    }
    values.update(overrides)
    return HankyungConsensusPdfTempSeedRecord(**values)


def session_cookies(app: FastAPI) -> dict[str, str]:
    session_id, _csrf = asyncio.run(AuthSessionStore(app.state.redis_client, app.state.settings).create_session(user_id="user-1"))
    return {app.state.settings.auth_session_cookie_name: session_id}


def test_pdf_temp_ingest_rejects_missing_origin(tmp_path):
    settings = pdf_settings(tmp_path, [])
    _client, app = make_client(settings)
    client = TestClient(app, base_url="https://api.example.co.kr")
    response = client.post("/reports/pdf-temp/ingest", cookies=session_cookies(app))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_required"


def test_pdf_temp_ingest_requires_and_accepts_csrf_token_when_enabled(tmp_path):
    settings = pdf_settings(tmp_path, [], AUTH_CSRF_REQUIRED=True)
    client, app = make_client(settings)
    session_store = AuthSessionStore(app.state.redis_client, settings)
    session_id, csrf_token = asyncio.run(session_store.create_session(user_id="user-1"))
    cookies = {settings.auth_session_cookie_name: session_id}

    denied = client.post("/reports/pdf-temp/ingest", cookies=cookies)
    allowed = client.post("/reports/pdf-temp/ingest", cookies=cookies, headers={"X-CSRF-Token": csrf_token})

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "csrf_invalid"
    assert allowed.status_code == 200
    assert allowed.json() == {"results": []}


def test_pdf_temp_feature_flag_fails_closed(tmp_path):
    settings = pdf_settings(tmp_path, [], PDF_TEMP_INGEST_ENABLED=False)
    client, _app = make_client(settings)

    response = client.get("/reports/pdf-temp/seeds")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "pdf_temp_ingest_disabled"


def test_pdf_temp_crawler_feature_flag_fails_closed(tmp_path):
    settings = pdf_settings(tmp_path, [], HANKYUNG_CONSENSUS_CRAWLER_ENABLED=False)
    client, _app = make_client(settings)

    list_response = client.get("/reports/pdf-temp/crawler/seeds")
    import_response = client.post("/reports/pdf-temp/crawler/import", json={})

    assert list_response.status_code == 503
    assert list_response.json()["error"]["code"] == "hankyung_consensus_crawler_disabled"
    assert import_response.status_code == 503
    assert import_response.json()["error"]["code"] == "hankyung_consensus_crawler_disabled"


def test_pdf_temp_crawler_requires_authenticated_session(tmp_path):
    settings = pdf_settings(tmp_path, [], HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True)
    client, _app = make_client(settings)

    response = client.get("/reports/pdf-temp/crawler/seeds")

    assert response.status_code == 401

def test_pdf_temp_crawler_import_rejects_missing_and_foreign_origin(tmp_path):
    settings = pdf_settings(tmp_path, [], HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True)
    client, app = make_client(settings)
    cookies = session_cookies(app)
    missing_origin_client = TestClient(app, base_url="https://api.example.co.kr")

    missing_origin = missing_origin_client.post("/reports/pdf-temp/crawler/import", cookies=cookies, json={})
    foreign_origin = client.post(
        "/reports/pdf-temp/crawler/import",
        cookies=cookies,
        headers={"Origin": "https://attacker.example.com"},
        json={},
    )

    assert missing_origin.status_code == 403
    assert missing_origin.json()["error"]["code"] == "origin_required"
    assert foreign_origin.status_code == 403
    assert foreign_origin.json()["error"]["code"] == "origin_not_allowed"


def test_pdf_temp_crawler_import_rejects_missing_and_invalid_csrf_token_when_required(tmp_path):
    settings = pdf_settings(tmp_path, [], HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True, AUTH_CSRF_REQUIRED=True)
    client, app = make_client(settings)
    session_id, _csrf_token = asyncio.run(AuthSessionStore(app.state.redis_client, settings).create_session(user_id="user-1"))
    cookies = {settings.auth_session_cookie_name: session_id}

    missing_token = client.post("/reports/pdf-temp/crawler/import", cookies=cookies, json={})
    invalid_token = client.post(
        "/reports/pdf-temp/crawler/import",
        cookies=cookies,
        headers={"X-CSRF-Token": "invalid"},
        json={},
    )

    assert missing_token.status_code == 403
    assert missing_token.json()["error"]["code"] == "csrf_invalid"
    assert invalid_token.status_code == 403
    assert invalid_token.json()["error"]["code"] == "csrf_invalid"



def test_pdf_temp_seed_list_is_safe_and_ingest_schema_rejects_arbitrary_source_fields(tmp_path):
    seed_file = tmp_path / "seeds" / "sample.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(seed_file, ["safe sample text"])
    settings = pdf_settings(
        tmp_path,
        [{"seed_id": "sample-a", "source_type": "file", "label": "Sample A", "source_path": "sample.pdf"}],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    seeds = client.get("/reports/pdf-temp/seeds", cookies=cookies)
    assert seeds.status_code == 200
    assert seeds.json() == {
        "seeds": [
            {
                "seedId": "sample-a",
                "sourceType": "file",
                "label": "Sample A",
                "enabled": True,
                "reportIdx": None,
                "title": None,
                "company": None,
                "ticker": None,
                "broker": None,
                "reportDate": None,
            }
        ]
    }
    assert "sample.pdf" not in seeds.text

    response = client.post(
        "/reports/pdf-temp/ingest",
        cookies=cookies,
        json={"seedIds": ["sample-a"], "sourceUrl": "https://reports.example.com/sample.pdf"},
    )
    assert response.status_code == 422

    metadata_response = client.post(
        "/reports/pdf-temp/ingest",
        cookies=cookies,
        json={"seedIds": ["sample-a"], "ticker": "005930"},
    )
    assert metadata_response.status_code == 422


def test_pdf_temp_seed_metadata_is_safe_and_propagates_to_file_responses(tmp_path):
    seed_file = tmp_path / "seeds" / "sample.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(seed_file, ["metadata sample text"])
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "hankyung-628514",
                "source_type": "file",
                "label": "Hankyung Report",
                "source_path": "sample.pdf",
                "title": "  Samsung Electronics Update  ",
                "company": "  Samsung Electronics  ",
                "ticker": "005930",
                "broker": "Example Securities",
                "report_date": "2026-05-30",
            }
        ],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    seeds = client.get("/reports/pdf-temp/seeds", cookies=cookies)
    assert seeds.status_code == 200
    seed_payload = seeds.json()["seeds"][0]
    assert seed_payload["reportIdx"] == "628514"
    assert seed_payload["title"] == "Samsung Electronics Update"
    assert seed_payload["company"] == "Samsung Electronics"
    assert seed_payload["ticker"] == "005930"
    assert seed_payload["broker"] == "Example Securities"
    assert seed_payload["reportDate"] == "2026-05-30"
    assert "source_path" not in seeds.text
    assert "sample.pdf" not in seeds.text

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["hankyung-628514"]}).json()["results"][0]
    assert item["status"] == "extracted"
    assert item["reportIdx"] == "628514"
    assert item["reportTitle"] == "Samsung Electronics Update"
    assert item["companyName"] == "Samsung Electronics"
    assert item["ticker"] == "005930"
    assert item["broker"] == "Example Securities"
    assert item["reportDate"] == "2026-05-30"

    detail = client.get(f"/reports/pdf-temp/{item['pdfId']}", cookies=cookies).json()["item"]
    listing = client.get("/reports/pdf-temp", cookies=cookies).json()["items"][0]
    assert detail["reportIdx"] == "628514"
    assert listing["reportTitle"] == "Samsung Electronics Update"


def test_pdf_temp_crawler_seed_list_and_detail_return_safe_metadata(tmp_path, monkeypatch):
    repository = FakeCrawlerSeedRepository([crawler_seed()])
    monkeypatch.setattr(reports_pdf_temp, "get_pdf_temp_db_repository", lambda _request: repository)
    settings = pdf_settings(tmp_path, [], HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True)
    client, app = make_client(settings)
    cookies = session_cookies(app)

    listing = client.get("/reports/pdf-temp/crawler/seeds", cookies=cookies)
    detail = client.get("/reports/pdf-temp/crawler/seeds/hankyung-crawl-649784", cookies=cookies)

    assert listing.status_code == 200
    assert detail.status_code == 200
    seed_payload = listing.json()["seeds"][0]
    assert seed_payload["seedId"] == "hankyung-crawl-649784"
    assert seed_payload["reportIdx"] == "649784"
    assert seed_payload["title"] == "아모레퍼시픽(090430) 1Q26 Review"
    assert seed_payload["company"] == "아모레퍼시픽"
    assert seed_payload["ticker"] == "090430"
    assert seed_payload["broker"] == "유진투자증권"
    assert seed_payload["reportDate"] == "2026-05-29"
    assert seed_payload["pdfUrl"] == "https://reports.example.com/sample.pdf"
    assert "source_payload_hash" not in listing.text
    assert "Authorization" not in listing.text
    assert detail.json()["seed"]["seedId"] == "hankyung-crawl-649784"


def test_pdf_temp_crawler_import_accepts_valid_csrf_token_when_required(tmp_path, monkeypatch):
    repository = FakeCrawlerSeedRepository()
    monkeypatch.setattr(reports_pdf_temp, "get_pdf_temp_db_repository", lambda _request: repository)
    install_fake_crawler_http(monkeypatch, [crawler_response({"data": [SAMPLE_ROW]})])
    settings = pdf_settings(
        tmp_path,
        [],
        HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True,
        AUTH_CSRF_REQUIRED=True,
        PDF_TEMP_URL_ALLOWED_HOSTS="markets.hankyung.com",
        HANKYUNG_CONSENSUS_AUTH_HEADER="X-Hankyung-Auth: crawler-secret",
    )
    client, app = make_client(settings)
    session_id, csrf_token = asyncio.run(AuthSessionStore(app.state.redis_client, settings).create_session(user_id="user-1"))
    cookies = {settings.auth_session_cookie_name: session_id}

    response = client.post(
        "/reports/pdf-temp/crawler/import",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf_token},
        json={"maxPages": 1, "maxReports": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fetched"] == 1
    assert payload["imported"] == 1
    assert payload["skipped"] == 0
    assert payload["failed"] == 0
    assert payload["seeds"][0]["seedId"] == "hankyung-crawl-649784"
    assert "crawler-secret" not in response.text
    assert "Authorization" not in response.text


def test_pdf_temp_seed_metadata_allows_explicit_report_idx_and_rejects_invalid_dates(tmp_path):
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "hankyung-628514",
                "source_type": "file",
                "label": "Explicit",
                "source_path": "sample.pdf",
                "report_idx": "custom-1",
                "report_date": "2026-05-30",
            }
        ],
    )

    seed = PdfTempSeedRegistry.from_settings(settings).list()[0]
    assert seed.report_idx == "custom-1"
    assert seed.report_date == "2026-05-30"

    for bad_date in ["2026/05/30", "2026-02-30"]:
        bad_settings = pdf_settings(
            tmp_path,
            [
                {
                    "seed_id": "bad-date",
                    "source_type": "file",
                    "label": "Bad Date",
                    "source_path": "sample.pdf",
                    "report_date": bad_date,
                }
            ],
        )
        with pytest.raises(AppError) as exc_info:
            PdfTempSeedRegistry.from_settings(bad_settings)
        assert exc_info.value.code == "invalid_seed_registry"

    bad_metadata_settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "bad-metadata",
                "source_type": "file",
                "label": "Bad Metadata",
                "source_path": "sample.pdf",
                "ticker": 5930,
            }
        ],
    )
    with pytest.raises(AppError) as exc_info:
        PdfTempSeedRegistry.from_settings(bad_metadata_settings)
    assert exc_info.value.code == "invalid_seed_registry"


def test_pdf_temp_manifest_preserves_metadata_and_reads_legacy_records(tmp_path):
    now = utc_now_iso()
    repository = PdfTempManifestRepository(tmp_path / "manifest.json")
    record = PdfTempFileRecord(
        pdf_id="pdf-1",
        seed_id="hankyung-628514",
        source_type="file",
        safe_source_label="Hankyung Report",
        stored_artifact_key="sample.pdf",
        original_filename="sample.pdf",
        file_hash="abc123",
        size_bytes=10,
        page_count=1,
        status="extracted",
        failure_reason=None,
        canonical_pdf_id=None,
        created_at=now,
        updated_at=now,
        report_idx="628514",
        report_title="Samsung Electronics Update",
        company_name="Samsung Electronics",
        ticker="005930",
        broker="Example Securities",
        report_date="2026-05-30",
    )

    asyncio.run(repository.save_file(record, []))
    saved = asyncio.run(repository.get_file("pdf-1"))
    assert saved is not None
    assert saved.response_payload()["reportDate"] == "2026-05-30"
    assert saved.response_payload()["ticker"] == "005930"

    date_record = PdfTempFileRecord(
        pdf_id="pdf-date",
        seed_id="seed-date",
        source_type="file",
        safe_source_label="Date",
        stored_artifact_key=None,
        original_filename=None,
        file_hash=None,
        size_bytes=0,
        page_count=0,
        status="failed",
        failure_reason=None,
        canonical_pdf_id=None,
        created_at=now,
        updated_at=now,
        report_date=date(2026, 5, 30),  # type: ignore[arg-type]
    )
    assert date_record.response_payload()["reportDate"] == "2026-05-30"

    legacy_payload = {
        "persistence": "prototype_manifest_not_production",
        "files": [
            {
                "pdf_id": "pdf-legacy",
                "seed_id": "legacy",
                "source_type": "file",
                "safe_source_label": "Legacy",
                "stored_artifact_key": None,
                "original_filename": None,
                "file_hash": None,
                "size_bytes": 0,
                "page_count": 0,
                "status": "failed",
                "failure_reason": None,
                "canonical_pdf_id": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
        "pages": [],
    }
    (tmp_path / "legacy.json").write_text(json.dumps(legacy_payload), encoding="utf-8")
    legacy_repository = PdfTempManifestRepository(tmp_path / "legacy.json")
    legacy = asyncio.run(legacy_repository.get_file("pdf-legacy"))
    assert legacy is not None
    assert legacy.report_idx is None
    assert legacy.response_payload()["reportDate"] is None


def test_pdf_temp_file_seed_ingest_extracts_pages_and_returns_safe_metadata(tmp_path):
    seed_file = tmp_path / "seeds" / "sample.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(seed_file, ["first page sample text", "second page sample text"])
    settings = pdf_settings(
        tmp_path,
        [{"seed_id": "sample-a", "source_type": "file", "label": "Sample A", "source_path": "sample.pdf"}],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    response = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["sample-a"]})

    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["status"] == "extracted"
    assert item["seedId"] == "sample-a"
    assert item["safeSourceLabel"] == "Sample A"
    assert item["artifactKey"].endswith(".pdf")
    assert str(tmp_path) not in response.text
    pdf_id = item["pdfId"]

    pages = client.get(f"/reports/pdf-temp/{pdf_id}/pages", cookies=cookies)
    assert pages.status_code == 200
    assert [page["pageNumber"] for page in pages.json()["pages"]] == [1, 2]
    assert "first page sample text" in pages.json()["pages"][0]["text"]
    assert pages.json()["pages"][0]["charCount"] > 0

    listing = client.get("/reports/pdf-temp", cookies=cookies)
    assert listing.status_code == 200
    assert listing.json()["items"][0]["pdfId"] == pdf_id


def test_pdf_temp_duplicate_hash_references_canonical_without_duplicate_pages(tmp_path):
    seed_file = tmp_path / "seeds" / "sample.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(seed_file, ["same document text for duplicate check"])
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "sample-a",
                "source_type": "file",
                "label": "Sample A",
                "source_path": "sample.pdf",
                "report_idx": "report-a",
                "title": "Report A",
            },
            {
                "seed_id": "sample-b",
                "source_type": "file",
                "label": "Sample B",
                "source_path": "sample.pdf",
                "report_idx": "report-b",
                "title": "Report B",
            },
        ],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    first = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["sample-a"]}).json()["results"][0]
    second = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["sample-b"]}).json()["results"][0]

    assert first["status"] == "extracted"
    assert second["status"] == "duplicate"
    assert second["canonicalPdfId"] == first["pdfId"]
    assert second["fileHash"] == first["fileHash"]
    assert first["reportIdx"] == "report-a"
    assert second["reportIdx"] == "report-b"
    assert second["reportTitle"] == "Report B"
    duplicate_pages = client.get(f"/reports/pdf-temp/{second['pdfId']}/pages", cookies=cookies)
    assert duplicate_pages.status_code == 200
    assert duplicate_pages.json()["pages"] == []


def test_pdf_temp_blank_pdf_is_marked_ocr_required(tmp_path):
    seed_file = tmp_path / "seeds" / "blank.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(seed_file, [""])
    settings = pdf_settings(
        tmp_path,
        [{"seed_id": "blank", "source_type": "file", "label": "Blank", "source_path": "blank.pdf"}],
        PDF_TEMP_MIN_TEXT_CHARS=5,
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["blank"]}).json()["results"][0]

    assert item["status"] == "ocr_required"
    assert "below threshold" in item["failureReason"]
    pages = client.get(f"/reports/pdf-temp/{item['pdfId']}/pages", cookies=cookies)
    assert pages.json()["pages"] == []


def test_pdf_temp_file_seed_path_traversal_records_safe_failure(tmp_path):
    settings = pdf_settings(
        tmp_path,
        [{"seed_id": "escape", "source_type": "file", "label": "Escape", "source_path": "../outside.pdf"}],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["escape"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "escaped" in item["failureReason"]
    assert str(tmp_path) not in item["failureReason"]


def test_pdf_temp_missing_file_seed_records_safe_failure(tmp_path):
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "missing",
                "source_type": "file",
                "label": "Missing",
                "source_path": "missing.pdf",
                "report_idx": "missing-report",
                "company": "Missing Co",
                "ticker": "000001",
            }
        ],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["missing"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "unavailable" in item["failureReason"]
    assert item["reportIdx"] == "missing-report"
    assert item["companyName"] == "Missing Co"
    assert item["ticker"] == "000001"


def test_pdf_temp_oversized_file_seed_records_safe_failure(tmp_path):
    seed_file = tmp_path / "seeds" / "large.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    seed_file.write_bytes(b"%PDF-" + (b"x" * 2048))
    settings = pdf_settings(
        tmp_path,
        [{"seed_id": "large", "source_type": "file", "label": "Large", "source_path": "large.pdf"}],
        PDF_TEMP_MAX_BYTES=1024,
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["large"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "maximum size" in item["failureReason"]


def test_pdf_temp_invalid_pdf_signature_records_safe_failure(tmp_path):
    seed_file = tmp_path / "seeds" / "not-pdf.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    seed_file.write_text("not actually a pdf", encoding="utf-8")
    settings = pdf_settings(
        tmp_path,
        [{"seed_id": "not-pdf", "source_type": "file", "label": "Not PDF", "source_path": "not-pdf.pdf"}],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["not-pdf"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "signature" in item["failureReason"]


def test_pdf_temp_malformed_pdf_records_extraction_failure(tmp_path):
    seed_file = tmp_path / "seeds" / "malformed.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    seed_file.write_bytes(b"%PDF- malformed content")
    settings = pdf_settings(
        tmp_path,
        [{"seed_id": "malformed", "source_type": "file", "label": "Malformed", "source_path": "malformed.pdf"}],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["malformed"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "text extraction failed" in item["failureReason"]


def test_pdf_temp_url_seed_uses_mocked_http_and_extracts_text(tmp_path, monkeypatch):
    content = pdf_bytes(tmp_path, ["downloaded pdf text"])
    install_fake_http(monkeypatch, [fake_response("https://reports.example.com/sample.pdf", content=content)])
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "url-a",
                "source_type": "url",
                "label": "URL A",
                "source_url": "https://reports.example.com/sample.pdf",
            }
        ],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["url-a"]}).json()["results"][0]

    assert item["status"] == "extracted"
    pages = client.get(f"/reports/pdf-temp/{item['pdfId']}/pages", cookies=cookies).json()["pages"]
    assert "downloaded pdf text" in pages[0]["text"]


def test_pdf_temp_url_redirect_to_disallowed_host_is_blocked_before_second_request(tmp_path, monkeypatch):
    fake_client = install_fake_http(
        monkeypatch,
        [
            fake_response(
                "https://reports.example.com/sample.pdf",
                status_code=302,
                headers={"location": "https://evil.example.com/sample.pdf"},
            )
        ],
    )
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "url-a",
                "source_type": "url",
                "label": "URL A",
                "source_url": "https://reports.example.com/sample.pdf",
            }
        ],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["url-a"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "host is not allowed" in item["failureReason"]
    assert fake_client.requests == ["https://reports.example.com/sample.pdf"]


def test_pdf_temp_url_redirect_limit_records_failure(tmp_path, monkeypatch):
    install_fake_http(
        monkeypatch,
        [
            fake_response(
                "https://reports.example.com/a.pdf",
                status_code=302,
                headers={"location": "https://reports.example.com/b.pdf"},
            ),
            fake_response(
                "https://reports.example.com/b.pdf",
                status_code=302,
                headers={"location": "https://reports.example.com/c.pdf"},
            ),
        ],
    )
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "url-a",
                "source_type": "url",
                "label": "URL A",
                "source_url": "https://reports.example.com/a.pdf",
            }
        ],
        PDF_TEMP_URL_MAX_REDIRECTS=1,
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["url-a"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "redirect limit" in item["failureReason"]


def test_pdf_temp_url_timeout_records_failure(tmp_path, monkeypatch):
    install_fake_http(monkeypatch, [httpx.TimeoutException("timeout")])
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "url-a",
                "source_type": "url",
                "label": "URL A",
                "source_url": "https://reports.example.com/a.pdf",
            }
        ],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["url-a"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "timed out" in item["failureReason"]


def test_pdf_temp_url_max_bytes_records_failure_and_cleans_staging(tmp_path, monkeypatch):
    install_fake_http(
        monkeypatch,
        [fake_response("https://reports.example.com/large.pdf", content=b"%PDF-" + (b"x" * 2048))],
    )
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "url-a",
                "source_type": "url",
                "label": "URL A",
                "source_url": "https://reports.example.com/large.pdf",
            }
        ],
        PDF_TEMP_MAX_BYTES=1024,
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["url-a"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "maximum size" in item["failureReason"]
    staging = Path(settings.pdf_temp_storage_dir) / "_staging"
    assert not any(staging.glob("*")) if staging.exists() else True


def test_pdf_temp_url_non_pdf_payload_records_failure(tmp_path, monkeypatch):
    install_fake_http(
        monkeypatch,
        [fake_response("https://reports.example.com/not-pdf.pdf", content=b"hello", headers={"content-type": "text/html"})],
    )
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "url-a",
                "source_type": "url",
                "label": "URL A",
                "source_url": "https://reports.example.com/not-pdf.pdf",
            }
        ],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["url-a"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "signature" in item["failureReason"]


def test_pdf_temp_db_backed_crawler_seed_ingests_by_seed_id(tmp_path, monkeypatch):
    content = pdf_bytes(tmp_path, ["db backed crawler seed text"])
    install_fake_http(monkeypatch, [fake_response("https://reports.example.com/sample.pdf", content=content)])
    seed_repository = FakeCrawlerSeedRepository([crawler_seed()])
    file_repository = PdfTempManifestRepository(tmp_path / "manifest.json")
    monkeypatch.setattr(reports_pdf_temp, "get_pdf_temp_db_repository", lambda _request: seed_repository)
    monkeypatch.setattr(reports_pdf_temp, "get_pdf_temp_repository", lambda _request, _settings: file_repository)
    settings = pdf_settings(
        tmp_path,
        [],
        PDF_TEMP_PERSISTENCE="db",
        HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True,
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    response = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["hankyung-crawl-649784"]})

    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["status"] == "extracted"
    assert item["seedId"] == "hankyung-crawl-649784"
    assert item["reportIdx"] == "649784"
    assert item["reportTitle"] == "아모레퍼시픽(090430) 1Q26 Review"
    assert item["ticker"] == "090430"


def test_pdf_temp_db_seed_html_login_payload_records_invalid_signature_failure(tmp_path, monkeypatch):
    install_fake_http(
        monkeypatch,
        [fake_response("https://reports.example.com/sample.pdf", content=b"<html>login</html>", headers={"content-type": "text/html"})],
    )
    seed_repository = FakeCrawlerSeedRepository([crawler_seed()])
    file_repository = PdfTempManifestRepository(tmp_path / "manifest.json")
    monkeypatch.setattr(reports_pdf_temp, "get_pdf_temp_db_repository", lambda _request: seed_repository)
    monkeypatch.setattr(reports_pdf_temp, "get_pdf_temp_repository", lambda _request, _settings: file_repository)
    settings = pdf_settings(tmp_path, [], PDF_TEMP_PERSISTENCE="db", HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True)
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["hankyung-crawl-649784"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "signature" in item["failureReason"]
    assert item["reportIdx"] == "649784"


def test_pdf_temp_env_seed_still_ingests_when_db_provider_is_added(tmp_path, monkeypatch):
    seed_file = tmp_path / "seeds" / "sample.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(seed_file, ["env seed still works"])

    class FailingSeedRepository(FakeCrawlerSeedRepository):
        async def get_crawler_seed(self, seed_id: str):  # pragma: no cover - fails if called
            raise AssertionError(f"DB seed provider should not be called for {seed_id}")

    monkeypatch.setattr(reports_pdf_temp, "get_pdf_temp_db_repository", lambda _request: FailingSeedRepository())
    monkeypatch.setattr(
        reports_pdf_temp,
        "get_pdf_temp_repository",
        lambda _request, _settings: PdfTempManifestRepository(tmp_path / "manifest.json"),
    )
    settings = pdf_settings(
        tmp_path,
        [{"seed_id": "env-seed", "source_type": "file", "label": "Env Seed", "source_path": "sample.pdf"}],
        PDF_TEMP_PERSISTENCE="db",
        HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True,
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    response = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["env-seed"]})

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "extracted"


def test_pdf_temp_env_db_seed_collision_fails_safely_on_list_and_ingest(tmp_path, monkeypatch):
    seed_repository = FakeCrawlerSeedRepository([crawler_seed()])
    monkeypatch.setattr(reports_pdf_temp, "get_pdf_temp_db_repository", lambda _request: seed_repository)
    monkeypatch.setattr(
        reports_pdf_temp,
        "get_pdf_temp_repository",
        lambda _request, _settings: PdfTempManifestRepository(tmp_path / "manifest.json"),
    )
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "hankyung-crawl-649784",
                "source_type": "url",
                "label": "Collision",
                "source_url": "https://reports.example.com/sample.pdf",
            }
        ],
        PDF_TEMP_PERSISTENCE="db",
        HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True,
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    listing = client.get("/reports/pdf-temp/seeds", cookies=cookies)
    ingest = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["hankyung-crawl-649784"]})

    assert listing.status_code == 503
    assert listing.json()["error"]["code"] == "seed_provider_collision"
    assert ingest.status_code == 503
    assert ingest.json()["error"]["code"] == "seed_provider_collision"


def test_pdf_temp_db_seed_resolution_fails_closed_when_table_missing(tmp_path, monkeypatch):
    class MissingSeedTableRepository(FakeCrawlerSeedRepository):
        async def get_crawler_seed(self, seed_id: str):
            raise AppError(
                status_code=503,
                component="db",
                code="pdf_temp_seed_db_unavailable",
                message="PDF temp crawler seed DB is unavailable",
            )

    monkeypatch.setattr(reports_pdf_temp, "get_pdf_temp_db_repository", lambda _request: MissingSeedTableRepository())
    monkeypatch.setattr(
        reports_pdf_temp,
        "get_pdf_temp_repository",
        lambda _request, _settings: PdfTempManifestRepository(tmp_path / "manifest.json"),
    )
    settings = pdf_settings(tmp_path, [], PDF_TEMP_PERSISTENCE="db", HANKYUNG_CONSENSUS_CRAWLER_ENABLED=True)
    client, app = make_client(settings)
    cookies = session_cookies(app)

    response = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["hankyung-crawl-649784"]})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "pdf_temp_seed_db_unavailable"


def test_pdf_temp_url_seed_disallowed_host_records_failure(tmp_path):
    settings = pdf_settings(
        tmp_path,
        [
            {
                "seed_id": "url-a",
                "source_type": "url",
                "label": "URL A",
                "source_url": "https://evil.example.com/sample.pdf",
            }
        ],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    item = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["url-a"]}).json()["results"][0]

    assert item["status"] == "failed"
    assert "host is not allowed" in item["failureReason"]


def test_pdf_temp_empty_body_ingests_all_enabled_seeds_and_enforces_cap(tmp_path):
    for name in ["a.pdf", "b.pdf"]:
        seed_file = tmp_path / "seeds" / name
        seed_file.parent.mkdir(parents=True, exist_ok=True)
        make_pdf(seed_file, [f"{name} text"])
    settings = pdf_settings(
        tmp_path,
        [
            {"seed_id": "a", "source_type": "file", "label": "A", "source_path": "a.pdf"},
            {"seed_id": "b", "source_type": "file", "label": "B", "source_path": "b.pdf"},
        ],
        PDF_TEMP_MAX_SEED_BATCH_SIZE=1,
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    capped = client.post("/reports/pdf-temp/ingest", cookies=cookies)
    assert capped.status_code == 400
    assert capped.json()["error"]["code"] == "too_many_pdf_seeds"

    app.state.settings = pdf_settings(
        tmp_path,
        [
            {"seed_id": "a", "source_type": "file", "label": "A", "source_path": "a.pdf"},
            {"seed_id": "b", "source_type": "file", "label": "B", "source_path": "b.pdf"},
        ],
        PDF_TEMP_MAX_SEED_BATCH_SIZE=2,
    )
    cookies = session_cookies(app)
    all_enabled = client.post("/reports/pdf-temp/ingest", cookies=cookies)
    assert all_enabled.status_code == 200
    assert {item["seedId"] for item in all_enabled.json()["results"]} == {"a", "b"}


def test_pdf_temp_force_false_reuses_seed_result_and_force_true_refetches_but_dedupes_same_hash(tmp_path):
    seed_file = tmp_path / "seeds" / "sample.pdf"
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    make_pdf(seed_file, ["force sample text"])
    settings = pdf_settings(
        tmp_path,
        [{"seed_id": "sample", "source_type": "file", "label": "Sample", "source_path": "sample.pdf"}],
    )
    client, app = make_client(settings)
    cookies = session_cookies(app)

    first = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["sample"]}).json()["results"][0]
    reused = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["sample"], "force": False}).json()["results"][0]
    forced = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["sample"], "force": True}).json()["results"][0]

    assert reused["pdfId"] == first["pdfId"]
    assert forced["status"] == "duplicate"
    assert forced["canonicalPdfId"] == first["pdfId"]


def test_pdf_temp_unknown_seed_returns_safe_error(tmp_path):
    settings = pdf_settings(tmp_path, [])
    client, app = make_client(settings)
    cookies = session_cookies(app)

    response = client.post("/reports/pdf-temp/ingest", cookies=cookies, json={"seedIds": ["missing"]})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_seed_id"


def test_pdf_temp_requires_authenticated_session(tmp_path):
    settings = pdf_settings(tmp_path, [])
    client, _app = make_client(settings)

    response = client.get("/reports/pdf-temp/seeds")

    assert response.status_code == 401
