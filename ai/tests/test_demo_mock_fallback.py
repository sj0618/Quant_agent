"""시연 fallback: 트리거 문구가 실제 파이프라인을 끝까지 돌린 뒤 리포트만 고성과로 바뀌는지 고정.

TestClient는 인증 세션 없이도 create_app 앱에 POST할 수 있고(기존 raw-query 테스트와 동일),
background_tasks를 응답 직후 인라인 실행하므로, POST가 돌아온 시점엔 job이 이미 완료돼 있다.

이 파일이 지키는 계약은 세 가지다. (1) 트리거 문구여도 그래프를 건너뛰지 않는다 —
목업을 끄면 같은 질의가 실제 실행 결과를 그대로 돌려준다. (2) 교체는 실제 실행의 성패와
무관하다 — ready 든 need_clarification 이든 예외든 시연 화면은 항상 고성과 리포트다.
(3) 교체는 트리거 전용이며, 사용자 취소는 덮지 않는다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_graph.api import ANALYSIS_JOBS_PATH, create_app
from ai_graph.jobs import InMemoryAnalysisJobStore

TRIGGER = "거래량 기반 퀀트 전략"


def _completed_result(query: str) -> dict:
    store = InMemoryAnalysisJobStore()
    client = TestClient(create_app(store))

    created = client.post(ANALYSIS_JOBS_PATH, json={"query": query})
    assert created.status_code == 201, created.text
    job_id = created.json()["job_id"]

    fetched = client.get(f"{ANALYSIS_JOBS_PATH}/{job_id}")
    assert fetched.status_code == 200, fetched.text
    return fetched.json()


def test_trigger_query_completes_with_high_performance() -> None:
    job = _completed_result(TRIGGER)
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


def test_trigger_query_survives_extra_whitespace() -> None:
    job = _completed_result("  거래량 기반  퀀트 전략\n")
    result = job["result"]
    assert result is not None and result["status"] == "ready"
    assert result["user_payload"]["performance"]["performance"]["metrics"]["total_return"] == 1.63


def test_disabled_flag_turns_the_mock_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_graph.demo_mock import demo_mock_active

    monkeypatch.setenv("DEMO_MOCK_ENABLED", "0")
    assert demo_mock_active(TRIGGER) is False


def test_real_pipeline_runs_and_only_the_final_report_is_swapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """트리거 문구도 그래프를 건너뛰지 않는다.

    목업을 끄면 같은 질의가 실제 그래프의 산출물(전략명·수익률)을 그대로 돌려주고,
    켜면 같은 실행 뒤에 최종 결과만 목업으로 바뀐다. 두 결과가 같아지면 실제 실행이
    건너뛰어졌거나 목업이 실행 자체를 대체한 것이므로 이 테스트가 깨진다.
    """

    monkeypatch.setenv("DEMO_MOCK_ENABLED", "0")
    real = _completed_result(TRIGGER)["result"]
    assert real["status"] == "ready", "실제 그래프가 이 환경에서 ready로 끝나야 비교가 성립한다"
    real_name = real["strategy_spec"]["name"]
    real_return = real["user_payload"]["performance"]["performance"]["metrics"]["total_return"]

    monkeypatch.setenv("DEMO_MOCK_ENABLED", "1")
    swapped = _completed_result(TRIGGER)["result"]
    swapped_name = swapped["strategy_spec"]["name"]

    assert real_return != 1.63, "실제 실행이 우연히 목업과 같은 수치를 내면 이 테스트는 무의미하다"
    assert real_name != swapped_name
    assert swapped["user_payload"]["performance"]["performance"]["metrics"]["total_return"] == 1.63


def test_non_ready_real_run_is_still_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    """실제 실행이 재질문으로 끝나도 시연 화면은 고성과 리포트다.

    운영 스모크에서 같은 트리거 문구가 5회 중 3회 need_clarification 으로 끝났다.
    ready 일 때만 교체하면 시연이 확률적으로 실패하므로, 실행 결과와 무관하게 교체한다.
    """

    from ai_graph import graph as graph_module
    from ai_graph.schemas import APIEnvelope, EnvelopeStatus, UserPayload

    clarification = APIEnvelope(
        status=EnvelopeStatus.NEED_CLARIFICATION,
        trace_id="trace-real-run",
        user_payload=UserPayload(headline="추가 정보가 필요합니다.", message="기간을 알려주세요."),
        debug_ref="real:clarification",
        retryable=False,
    )

    class _StubGraph:
        def invoke(self, state: dict) -> dict:
            return {"envelope": clarification.model_dump(mode="json")}

    monkeypatch.setattr(graph_module, "build_graph", lambda **kwargs: _StubGraph())

    envelope = graph_module.run_analysis(TRIGGER)

    assert envelope.status is EnvelopeStatus.READY
    assert envelope.trace_id == "trace-real-run"
    metrics = envelope.user_payload.performance.performance["metrics"]
    assert metrics["total_return"] == 1.63


def test_graph_exception_still_yields_the_demo_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """그래프가 예외로 죽어도 시연 화면은 고성과 리포트다."""

    from ai_graph import graph as graph_module
    from ai_graph.schemas import EnvelopeStatus

    class _ExplodingGraph:
        def invoke(self, state: dict) -> dict:
            raise RuntimeError("backtest engine unavailable")

    monkeypatch.setattr(graph_module, "build_graph", lambda **kwargs: _ExplodingGraph())

    envelope = graph_module.run_analysis(TRIGGER)

    assert envelope.status is EnvelopeStatus.READY
    assert envelope.user_payload.performance.performance["metrics"]["total_return"] == 1.63


def test_cancellation_is_not_masked_by_the_demo_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """취소는 사용자 의도이므로 목업으로 덮지 않는다."""

    from ai_graph import graph as graph_module
    from ai_graph.progress import AnalysisCancelled

    class _CancelledGraph:
        def invoke(self, state: dict) -> dict:
            raise AnalysisCancelled("cancelled by user")

    monkeypatch.setattr(graph_module, "build_graph", lambda **kwargs: _CancelledGraph())

    with pytest.raises(AnalysisCancelled):
        graph_module.run_analysis(TRIGGER)


def test_untriggered_failure_is_not_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    """트리거 문구가 아니면 실패는 그대로 실패다 — 교체는 트리거 전용이다."""

    from ai_graph import graph as graph_module

    class _ExplodingGraph:
        def invoke(self, state: dict) -> dict:
            raise RuntimeError("backtest engine unavailable")

    monkeypatch.setattr(graph_module, "build_graph", lambda **kwargs: _ExplodingGraph())

    with pytest.raises(RuntimeError):
        graph_module.run_analysis("RSI 30 이하 매수 전략")
