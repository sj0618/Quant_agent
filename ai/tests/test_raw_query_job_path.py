"""The production path for a bare natural-language submission.

The browser posts a query with no parse token; the job resolves and seals the
execution contract itself and hands it to the graph.  These pin the boundary
between ``ai_graph.research_contract``'s spec classes and ``ai_graph.schemas``'
identically shaped ones, which previously killed every explicit-rule job about a
second after it started.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_graph.api import (
    ANALYSIS_JOBS_PATH,
    SPEC_STRATEGY_PARSE_PATH,
    _build_analysis_runner_with_audit,
    create_app,
)
from ai_graph.graph import run_analysis
from ai_graph.jobs import AnalysisJobStatus, InMemoryAnalysisJobStore, run_job_sync
from ai_graph.research_contract import RuleDraftSigner, RuleDraftV1, build_rule_draft
from ai_graph.schemas import EnvelopeStatus, Stage

RSI_QUERY = "RSI 30 이하일때 매수하고 70 이상일때 매도"


def _signer() -> RuleDraftSigner:
    return RuleDraftSigner(secret="0123456789abcdef0123456789abcdef", key_version="test")


def _sealed_rsi_draft() -> RuleDraftV1:
    draft = build_rule_draft(query=RSI_QUERY, user_id="u1", signer=_signer(), use_llm=True)
    assert draft.is_executable
    return draft


def _runner(resolver):
    return _build_analysis_runner_with_audit(
        run_analysis,
        audit_sink=None,
        trace_id="trace-raw-query",
        entrypoint="api.analysis_jobs",
        feature="analysis_job",
        user_id="u1",
        rule_draft_resolver=resolver,
    )


def test_sealed_research_contract_reaches_the_graph() -> None:
    draft = _sealed_rsi_draft()

    envelope = _runner(lambda query, trace_id: draft)(RSI_QUERY, "trace-raw-query")

    assert envelope.status == EnvelopeStatus.READY
    assert envelope.user_payload.report is not None


def test_job_for_a_bare_query_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    draft = _sealed_rsi_draft()
    store = InMemoryAnalysisJobStore()
    job = store.create_job(RSI_QUERY, user_id="u1")

    finished = run_job_sync(store, job.job_id, _runner(lambda query, trace_id: draft))

    assert finished.status == AnalysisJobStatus.COMPLETED
    assert finished.result is not None
    assert finished.result.status == EnvelopeStatus.READY


def test_non_executable_outcome_asks_instead_of_failing() -> None:
    outcome = build_rule_draft(query="안녕", user_id="u1", signer=_signer(), use_llm=False)
    assert not outcome.is_executable
    store = InMemoryAnalysisJobStore()
    job = store.create_job("안녕", user_id="u1")

    finished = run_job_sync(store, job.job_id, _runner(lambda query, trace_id: outcome))

    assert finished.status == AnalysisJobStatus.COMPLETED
    assert finished.result is not None
    payload = finished.result.user_payload
    assert finished.result.status == EnvelopeStatus.NEED_CLARIFICATION
    # A greeting is answered by asking what to analyse. It used to be answered with
    # "먼저 어떤 후보 전략으로 구체화할까요?" and three generic strategy options, which
    # is a question about nothing the user said.
    assert payload.question == "어떤 투자 전략이나 매매 조건을 분석할까요?"
    assert payload.options == []
    assert payload.candidate_cards == []
    assert payload.report is None
    assert payload.performance is None


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_blank_query_is_rejected_before_a_job_exists(blank: str) -> None:
    store = InMemoryAnalysisJobStore()
    client = TestClient(create_app(store))

    response = client.post(ANALYSIS_JOBS_PATH, json={"query": blank})

    assert response.status_code == 422
    assert store.list_jobs() == []


def test_query_is_length_bounded() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    assert client.post(ANALYSIS_JOBS_PATH, json={"query": "가" * 2001}).status_code == 422
    assert client.post(SPEC_STRATEGY_PARSE_PATH, json={"query": "가" * 2001}).status_code == 422


def test_failed_job_reports_the_stage_it_actually_reached() -> None:
    store = InMemoryAnalysisJobStore()
    job = store.create_job(RSI_QUERY, user_id="u1")

    def die_in_interpreting(query: str, trace_id: str):
        raise RuntimeError("interpreter exploded")

    finished = run_job_sync(store, job.job_id, die_in_interpreting)

    assert finished.status == AnalysisJobStatus.FAILED
    stages = {progress.stage: progress.status.value for progress in finished.stages}
    assert stages[Stage.INTERPRETING] == "failed"
    assert stages[Stage.FINALIZING] == "queued"
