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


def _result_with_runner(query: str, runner) -> dict:
    """주입한 러너로 잡을 끝까지 돌리고 결과를 돌려준다.

    잡 실행 경계(_run_analysis_job)를 실제로 통과시키는 것이 요점이다. run_analysis 를
    monkeypatch 하는 방식은 운영에서 재질문이 실제로 나는 층을 건드리지 못한다 —
    api.py 의 리서치 리졸버는 run_analysis 를 호출조차 하지 않고 반환하기 때문이다.
    """

    store = InMemoryAnalysisJobStore()
    client = TestClient(create_app(store, analysis_runner=runner))
    created = client.post(ANALYSIS_JOBS_PATH, json={"query": query})
    assert created.status_code == 201, created.text
    fetched = client.get(f"{ANALYSIS_JOBS_PATH}/{created.json()['job_id']}")
    assert fetched.status_code == 200, fetched.text
    return fetched.json()["result"]


def _clarification_runner(query: str, trace_id: str | None):
    """api.py 의 리서치 리졸버가 실행 불가 판정을 내렸을 때 내는 것과 같은 응답."""

    from ai_graph.schemas import APIEnvelope, EnvelopeStatus, UserPayload

    return APIEnvelope(
        status=EnvelopeStatus.NEED_CLARIFICATION,
        trace_id=trace_id or "trace-real-run",
        user_payload=UserPayload(
            headline="추가 확인이 필요합니다.",
            message="전략 의미는 조사했지만 현재 서버가 같은 규칙으로 백테스트할 수 없습니다.",
        ),
        debug_ref="real:clarification",
        retryable=False,
    )


def test_resolver_clarification_still_yields_the_demo_report() -> None:
    """운영에서 실제로 나던 재질문도 시연 화면에서는 고성과 리포트다.

    운영 스모크 5회 중 3회가 이 표면에서 need_clarification 으로 끝났다. 교체를
    run_analysis 안에 두었을 때는 이 경로가 덮이지 않았다.
    """

    result = _result_with_runner(TRIGGER, _clarification_runner)

    assert result["status"] == "ready"
    metrics = result["user_payload"]["performance"]["performance"]["metrics"]
    assert metrics["total_return"] == 1.63


def test_runner_exception_still_yields_the_demo_report() -> None:
    """러너가 예외로 죽어도 시연 화면은 고성과 리포트다."""

    def _exploding(query: str, trace_id: str | None):
        raise RuntimeError("backtest engine unavailable")

    result = _result_with_runner(TRIGGER, _exploding)

    assert result["status"] == "ready"
    assert result["user_payload"]["performance"]["performance"]["metrics"]["total_return"] == 1.63


def test_cancellation_is_not_masked_by_the_demo_report() -> None:
    """취소는 사용자 의도이므로 목업으로 덮지 않는다."""

    from ai_graph.progress import AnalysisCancelled

    def _cancelled(query: str, trace_id: str | None):
        raise AnalysisCancelled("cancelled by user")

    result = _result_with_runner(TRIGGER, _cancelled)

    assert result["status"] != "ready"
    assert result["user_payload"].get("performance") in (None, {})


def test_untriggered_failure_is_not_replaced() -> None:
    """트리거 문구가 아니면 실패는 그대로 실패다 — 교체는 트리거 전용이다."""

    def _exploding(query: str, trace_id: str | None):
        raise RuntimeError("backtest engine unavailable")

    result = _result_with_runner("RSI 30 이하 매수 전략", _exploding)

    assert result["status"] != "ready"


def test_exclusion_marker_disables_the_trigger() -> None:
    """트리거 문구 뒤에 배제 표현이 오면 다른 요청이므로 목업을 띄우지 않는다."""

    from ai_graph.demo_mock import demo_mock_active

    assert demo_mock_active("거래량 기반 퀀트 전략 만들어줘") is True
    assert demo_mock_active("거래량 기반 퀀트 전략 말고 RSI로 해줘") is False
    assert demo_mock_active("거래량 기반 퀀트 전략은 빼고 배당주로") is False

    def _exploding(query: str, trace_id: str | None):
        raise RuntimeError("backtest engine unavailable")

    result = _result_with_runner("거래량 기반 퀀트 전략 말고 RSI로 해줘", _exploding)
    assert result["status"] != "ready"


def test_capacity_timeout_still_yields_the_demo_report() -> None:
    """용량 대기 초과도 시연 화면은 고성과 리포트다.

    이 실패는 _run_analysis_job 바깥(run_job_sync)에서 끝나므로 그 안의 교체를 지나치지
    못한다. 앞선 잡이 물려 있을 때만 시연이 실패하는 구멍이 남지 않게 고정한다.
    """

    from ai_graph.analysis_capacity import AnalysisCapacityGate
    from ai_graph.jobs import run_job_sync

    store = InMemoryAnalysisJobStore()
    job = store.create_job(TRIGGER)
    gate = AnalysisCapacityGate(max_concurrency=1, queue_wait_seconds=0.01)

    def _never_called(query: str, trace_id: str | None):  # pragma: no cover - 호출되면 실패
        raise AssertionError("capacity gate should have rejected before the runner ran")

    with gate.slot():  # 슬롯을 미리 점유해 대기 초과를 강제한다
        result = run_job_sync(store, job.job_id, _never_called, capacity=gate)

    envelope = result.result
    assert envelope is not None
    assert envelope.status.value == "ready"
    metrics = envelope.user_payload.performance.performance["metrics"]
    assert metrics["total_return"] == 1.63


def test_refinement_words_do_not_disable_the_trigger() -> None:
    """조건을 다듬는 말은 트리거를 물리지 않는다.

    배제 판정을 처음 넣었을 때 "제외"·"대신"까지 마커로 잡아, 시연자가 그 전략을 원하는
    문장 넷이 전부 꺼졌다. 배제 표현이 트리거 바로 뒤에 붙은 경우만 물린다.
    """

    from ai_graph.demo_mock import demo_mock_active

    for query in (
        "거래량 기반 퀀트 전략, KOSPI 대신 KOSDAQ으로 해줘",
        "거래량 기반 퀀트 전략 짜줘. 우선주는 제외해줘",
        "거래량 기반 퀀트 전략 만들어줘. 손절은 -5% 대신 -7%로",
        "거래량 기반 퀀트 전략 만들어줘. 우선주 빼고",
        "거래량 기반 퀀트 전략인데 단순 이평선이 아니라 거래량 급증 기준으로",
    ):
        assert demo_mock_active(query) is True, query

    for query in (
        "거래량 기반 퀀트 전략 말고 RSI로 해줘",
        "거래량 기반 퀀트 전략은 빼고 배당주로",
    ):
        assert demo_mock_active(query) is False, query
