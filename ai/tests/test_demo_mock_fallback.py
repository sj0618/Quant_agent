"""시연 fallback: 트리거 문구가 실제 HTTP 경로 전체를 통과해 고성과 리포트로 완료되는지 고정.

TestClient는 인증 세션 없이도 create_app 앱에 POST할 수 있고(기존 raw-query 테스트와 동일),
background_tasks를 응답 직후 인라인 실행하므로, POST가 돌아온 시점엔 job이 이미 완료돼 있다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_graph.api import ANALYSIS_JOBS_PATH, create_app
from ai_graph.jobs import InMemoryAnalysisJobStore

TRIGGER = "거래량 기반 퀀트 전략"


def _completed_result(monkeypatch: pytest.MonkeyPatch, query: str) -> dict:
    monkeypatch.setenv("DEMO_MOCK_PACE_SECONDS", "0")  # 테스트에서는 연출 지연 제거
    store = InMemoryAnalysisJobStore()
    client = TestClient(create_app(store))

    created = client.post(ANALYSIS_JOBS_PATH, json={"query": query})
    assert created.status_code == 201, created.text
    job_id = created.json()["job_id"]

    fetched = client.get(f"{ANALYSIS_JOBS_PATH}/{job_id}")
    assert fetched.status_code == 200, fetched.text
    return fetched.json()


def test_trigger_query_completes_with_high_performance(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _completed_result(monkeypatch, TRIGGER)
    result = job["result"]
    assert result is not None, "background job did not complete with a result"
    assert result["status"] == "ready"

    payload = result["user_payload"]
    perf = payload["performance"]
    assert perf["availability"] == "available"

    metrics = perf["performance"]["metrics"]
    assert metrics["total_return"] == 1.63  # +163%
    assert metrics["sharpe_ratio"] == 2.18
    assert metrics["max_drawdown"] == -0.098
    assert metrics["win_rate"] == 0.64
    assert perf["performance"]["reliability"]["status"] == "sufficient"

    assert payload["recommendation_gate"]["validated"] is True
    assert result["strategy_spec"]["confidence"] == 0.87

    signal = next(s for s in payload["report"]["web_projection"]["sections"] if s["id"] == "signal")
    assert signal["items"]["action"] == "BUY"


def test_trigger_query_survives_extra_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _completed_result(monkeypatch, "  거래량 기반  퀀트 전략\n")
    result = job["result"]
    assert result is not None and result["status"] == "ready"
    assert result["user_payload"]["performance"]["performance"]["metrics"]["total_return"] == 1.63


def test_disabled_flag_turns_the_mock_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_graph.demo_mock import demo_mock_active

    monkeypatch.setenv("DEMO_MOCK_ENABLED", "0")
    assert demo_mock_active(TRIGGER) is False
