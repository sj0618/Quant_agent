from __future__ import annotations

import httpx
import pytest

from app.core.errors import AppError
from app.services.hankyung_consensus_crawler import (
    HankyungConsensusCrawlRequest,
    HankyungConsensusCrawler,
    normalize_hankyung_report_row,
    source_payload_hash,
)
from tests.unit.test_auth_config import valid_settings


SAMPLE_ROW = {
    "REPORT_IDX": 649784,
    "REPORT_TITLE": "아모레퍼시픽(090430) 1Q26 Review",
    "BUSINESS_NAME": "아모레퍼시픽",
    "BUSINESS_CODE": "090430",
    "OFFICE_NAME": "유진투자증권",
    "REPORT_DATE": "2026-05-29",
    "REPORT_FILEPATH": "https://markets.hankyung.com/pdf/2026/05/abc",
    "REPORT_FILENAME": "20260529_090430_hnlee_266.pdf",
    "REPORT_TYPE": "CO",
    "REPORT_WRITER": "이해니",
}


class FakeCrawlerAsyncClient:
    calls: list[dict] = []
    responses: list[httpx.Response] = []
    init_kwargs: dict = {}

    def __init__(self, **kwargs):
        self.__class__.init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def get(self, url, params=None):
        self.__class__.calls.append({"url": url, "params": dict(params or {})})
        if not self.__class__.responses:
            raise AssertionError("No crawler fake response configured")
        return self.__class__.responses.pop(0)


def install_fake_crawler_http(monkeypatch, responses: list[httpx.Response]):
    FakeCrawlerAsyncClient.calls = []
    FakeCrawlerAsyncClient.responses = responses
    FakeCrawlerAsyncClient.init_kwargs = {}
    monkeypatch.setattr("app.services.hankyung_consensus_crawler.httpx.AsyncClient", FakeCrawlerAsyncClient)
    return FakeCrawlerAsyncClient


def crawler_response(payload, status_code: int = 200):
    return httpx.Response(status_code, json=payload, request=httpx.Request("GET", "https://markets.hankyung.com/api/consensus/search/report"))


def test_hankyung_crawler_normalizes_report_row_to_temp_seed():
    seed = normalize_hankyung_report_row(SAMPLE_ROW, base_url="https://markets.hankyung.com")

    assert seed is not None
    assert seed.seed_id == "hankyung-crawl-649784"
    assert seed.report_idx == "649784"
    assert seed.report_title == "아모레퍼시픽(090430) 1Q26 Review"
    assert seed.company_name == "아모레퍼시픽"
    assert seed.ticker == "090430"
    assert seed.broker == "유진투자증권"
    assert seed.report_date == "2026-05-29"
    assert seed.pdf_url.endswith("/20260529_090430_hnlee_266.pdf")
    assert seed.source_report_type == "CO"
    assert seed.source_writer == "이해니"


def test_hankyung_crawler_uses_pdf_filepath_when_it_already_ends_with_pdf():
    row = {**SAMPLE_ROW, "REPORT_FILEPATH": "https://markets.hankyung.com/pdf/report.pdf", "REPORT_FILENAME": "ignored.pdf"}

    seed = normalize_hankyung_report_row(row, base_url="https://markets.hankyung.com")

    assert seed is not None
    assert seed.pdf_url == "https://markets.hankyung.com/pdf/report.pdf"


def test_hankyung_crawler_rejects_disallowed_pdf_host_when_hosts_are_configured():
    seed = normalize_hankyung_report_row(
        SAMPLE_ROW,
        base_url="https://markets.hankyung.com",
        allowed_pdf_hosts=["reports.example.com"],
    )

    assert seed is None


@pytest.mark.parametrize(
    "override",
    [
        {"REPORT_IDX": None},
        {"REPORT_FILEPATH": None},
        {"REPORT_FILEPATH": "https://markets.hankyung.com/pdf/dir", "REPORT_FILENAME": None},
        {"REPORT_DATE": "2026-02-30"},
    ],
)
def test_hankyung_crawler_skips_unusable_rows(override):
    assert normalize_hankyung_report_row({**SAMPLE_ROW, **override}, base_url="https://markets.hankyung.com") is None


def test_hankyung_crawler_payload_hash_is_stable_and_excludes_secret_fields():
    left = {"b": 2, "a": 1, "access_token": "secret", "nested": {"session_id": "secret", "x": "safe"}}
    right = {"nested": {"x": "safe"}, "a": 1, "b": 2}

    assert source_payload_hash(left) == source_payload_hash(right)


async def test_hankyung_crawler_sends_user_agent_auth_header_and_enforces_bounds(monkeypatch):
    fake_client = install_fake_crawler_http(
        monkeypatch,
        [
            crawler_response({"data": [SAMPLE_ROW, {**SAMPLE_ROW, "REPORT_IDX": 649785}]}),
            crawler_response({"data": [{**SAMPLE_ROW, "REPORT_IDX": 649786}]}),
        ],
    )
    settings = valid_settings(
        HANKYUNG_CONSENSUS_CRAWL_MAX_PAGES=2,
        HANKYUNG_CONSENSUS_CRAWL_MAX_REPORTS=2,
        PDF_TEMP_URL_ALLOWED_HOSTS="markets.hankyung.com",
        HANKYUNG_CONSENSUS_AUTH_HEADER="X-Hankyung-Auth: crawler-secret",
    )

    rows = await HankyungConsensusCrawler(settings).fetch_report_rows(HankyungConsensusCrawlRequest(max_pages=5, max_reports=5))

    assert len(rows) == 2
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["url"] == "/api/consensus/search/report"
    assert fake_client.calls[0]["params"]["page"] == 1
    assert fake_client.calls[0]["params"]["reportType"] == "ALL"
    assert fake_client.calls[0]["params"]["fromDate"]
    assert fake_client.calls[0]["params"]["toDate"]
    assert fake_client.init_kwargs["headers"]["User-Agent"] == settings.hankyung_consensus_crawl_user_agent
    assert fake_client.init_kwargs["headers"]["X-Hankyung-Auth"] == "crawler-secret"


async def test_hankyung_crawler_handles_403_as_safe_error_without_secret(monkeypatch):
    install_fake_crawler_http(monkeypatch, [crawler_response({"error": "forbidden"}, status_code=403)])
    settings = valid_settings(HANKYUNG_CONSENSUS_API_BEARER_TOKEN="crawler-secret")

    with pytest.raises(AppError) as exc_info:
        await HankyungConsensusCrawler(settings).fetch_report_rows(HankyungConsensusCrawlRequest())

    assert exc_info.value.code == "crawler_fetch_failed"
    assert "crawler-secret" not in str(exc_info.value.payload())


async def test_hankyung_crawler_returns_safe_error_for_unexpected_json_shape(monkeypatch):
    install_fake_crawler_http(monkeypatch, [crawler_response({"unexpected": {"shape": True}})])

    with pytest.raises(AppError) as exc_info:
        await HankyungConsensusCrawler(valid_settings()).fetch_report_rows(HankyungConsensusCrawlRequest())

    assert exc_info.value.code == "crawler_unexpected_payload"
