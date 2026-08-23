from __future__ import annotations

from fastapi.testclient import TestClient

from ai_graph.api import (
    RESEARCH_JOB_CREATE_PATH,
    RESEARCH_JOB_RESULT_PATH,
    SPEC_STRATEGY_PARSE_PATH,
    create_app,
)
from ai_graph.auth import DisabledSessionResolver
from ai_graph.jobs import InMemoryAnalysisJobStore
from ai_graph.research_contract import RuleDraftSigner
from ai_graph.schemas import APIEnvelope, EnvelopeStatus, UserPayload


def _ready_envelope(trace_id: str) -> APIEnvelope:
    return APIEnvelope(
        status=EnvelopeStatus.READY,
        trace_id=trace_id,
        user_payload=UserPayload(
            headline="analysis complete",
            message="analysis complete",
            next_actions=[],
        ),
        strategy_spec=None,
        debug_ref=f"debug:{trace_id}",
        retryable=False,
    )


def _client(*, execution_enabled: bool, calls: list[str]) -> tuple[TestClient, InMemoryAnalysisJobStore]:
    store = InMemoryAnalysisJobStore()
    app = create_app(
        store,
        analysis_runner=lambda query, trace_id: (calls.append(query), _ready_envelope(trace_id))[1],
        session_resolver=DisabledSessionResolver(),
        rule_draft_signer=RuleDraftSigner("research-contract-test-secret", key_version="test-v1"),
        research_execution_enabled=execution_enabled,
    )
    return TestClient(app), store


def _parse_executable_draft(client: TestClient) -> dict:
    response = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={"natural_language": "RSI가 30 이하이고 RSI가 70 이상인 일반 조건식을 검토해 주세요."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "rule_draft"
    assert payload["is_executable"] is True
    return payload


def test_parse_returns_rule_review_without_job_quota_or_runner_side_effects() -> None:
    calls: list[str] = []
    client, store = _client(execution_enabled=False, calls=calls)

    draft = _parse_executable_draft(client)

    assert store.jobs == {}
    assert calls == []
    serialized = str(draft)
    assert "매수" not in serialized
    assert "매도" not in serialized
    assert "RSI가 30 이하이고" not in serialized


def test_confirmed_rule_executes_only_when_activation_is_explicit_and_then_projects_unavailable() -> None:
    calls: list[str] = []
    client, store = _client(execution_enabled=True, calls=calls)
    draft = _parse_executable_draft(client)

    response = client.post(
        RESEARCH_JOB_CREATE_PATH,
        json={"canonical_rule": draft["canonical_rule"], "draft_token": draft["draft_token"]},
    )

    assert response.status_code == 201
    accepted = response.json()
    assert accepted == {"kind": "research_job_accepted", "job_id": accepted["job_id"], "status": "queued"}
    assert len(store.jobs) == 1
    assert len(calls) == 1
    assert "RSI가 30 이하이고" not in calls[0]

    result = client.get(RESEARCH_JOB_RESULT_PATH.format(job_id=accepted["job_id"]))
    assert result.status_code == 200
    assert result.json()["status"] == "unavailable"
    assert result.json()["reason_code"] == "operational_data_provenance_required"

    replay = client.post(
        RESEARCH_JOB_CREATE_PATH,
        json={"canonical_rule": draft["canonical_rule"], "draft_token": draft["draft_token"]},
    )
    assert replay.status_code == 409
    assert replay.json()["reason_code"] == "draft_replayed"


def test_execution_remains_fail_closed_until_explicit_activation() -> None:
    calls: list[str] = []
    client, store = _client(execution_enabled=False, calls=calls)
    draft = _parse_executable_draft(client)

    response = client.post(
        RESEARCH_JOB_CREATE_PATH,
        json={"canonical_rule": draft["canonical_rule"], "draft_token": draft["draft_token"]},
    )

    assert response.status_code == 503
    assert store.jobs == {}
    assert calls == []


def test_scope_refusal_stays_before_signing_or_execution() -> None:
    calls: list[str] = []
    client, store = _client(execution_enabled=True, calls=calls)

    response = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={"natural_language": "내 보유 종목을 지금 팔아줘"},
    )

    assert response.status_code == 422
    assert response.json()["kind"] == "scope_refusal"
    assert "내 보유" not in response.text
    assert store.jobs == {}
    assert calls == []
