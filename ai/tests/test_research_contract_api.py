from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import ai_graph.api as api_module
from ai_graph.api import (
    ANALYSIS_JOBS_PATH,
    DATA_EVIDENCE_PROBE_PATH,
    DATA_EVIDENCE_PROBE_TOKEN_ENV,
    RESEARCH_JOB_CREATE_PATH,
    RESEARCH_JOB_RESULT_PATH,
    SPEC_STRATEGY_PARSE_PATH,
    create_app,
)
from ai_graph.auth import DisabledSessionResolver
from ai_graph.job_events import JobEventBuffer
from ai_graph.jobs import AnalysisJobStatus, CancellationRegistry, InMemoryAnalysisJobStore
from ai_graph.research_contract import RuleDraftSigner, build_rule_draft
from ai_graph.research_eligibility import ResearchRuntimeFacts
from ai_graph.schemas import APIEnvelope, EnvelopeStatus, UserPayload
from ai_graph.token_auth import ResolvedAccountToken


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


def _client(
    *,
    execution_enabled: bool,
    calls: list[str],
    store: InMemoryAnalysisJobStore | None = None,
    account_token_resolver=None,
    account_token_quota=None,
) -> tuple[TestClient, InMemoryAnalysisJobStore]:
    store = store or InMemoryAnalysisJobStore()
    app = create_app(
        store,
        analysis_runner=lambda query, trace_id: (calls.append(query), _ready_envelope(trace_id))[1],
        session_resolver=DisabledSessionResolver(),
        account_token_resolver=account_token_resolver,
        account_token_quota=account_token_quota,
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


def test_parse_executable_outcome_contains_the_versioned_spec_hash_and_bound_token() -> None:
    calls: list[str] = []
    client, _store = _client(execution_enabled=False, calls=calls)

    draft = _parse_executable_draft(client)

    assert draft["strategy_execution_spec"] == draft["canonical_rule"]
    assert draft["spec_version"] == "strategy-execution-spec.v1"
    assert len(draft["spec_hash"]) == 64
    assert draft["parse_token"] == draft["draft_token"]


def test_primary_analysis_job_accepts_only_the_verified_parse_contract() -> None:
    calls: list[str] = []
    client, store = _client(execution_enabled=False, calls=calls)
    draft = _parse_executable_draft(client)

    response = client.post(
        ANALYSIS_JOBS_PATH,
        json={
            "parse_token": draft["parse_token"],
            "client_idempotency_key": "32ecc88e-a50d-4b4d-9c5e-573d817b410a",
            "spec_version": draft["spec_version"],
            "spec_hash": draft["spec_hash"],
            "strategy_execution_spec": draft["strategy_execution_spec"],
        },
    )

    assert response.status_code == 201
    assert len(store.jobs) == 1
    assert len(calls) == 1
    assert "RSI가 30 이하이고" not in calls[0]
    stored = store.get_job(response.json()["job_id"])
    assert stored is not None
    assert stored.execution_spec_version == draft["spec_version"]
    assert stored.execution_spec_hash == draft["spec_hash"]
    assert stored.client_idempotency_key == "32ecc88e-a50d-4b4d-9c5e-573d817b410a"


def test_tampered_parse_spec_creates_no_primary_job_or_runner_side_effect() -> None:
    calls: list[str] = []
    client, store = _client(execution_enabled=False, calls=calls)
    draft = _parse_executable_draft(client)
    tampered = dict(draft["strategy_execution_spec"])
    tampered["entry_conditions"] = [
        {"metric": "rsi", "comparator": "lte", "value": 25, "role": "entry"}
    ]

    response = client.post(
        ANALYSIS_JOBS_PATH,
        json={
            "parse_token": draft["parse_token"],
            "client_idempotency_key": "32ecc88e-a50d-4b4d-9c5e-573d817b410a",
            "spec_version": draft["spec_version"],
            "spec_hash": draft["spec_hash"],
            "strategy_execution_spec": tampered,
        },
    )

    assert response.status_code == 409
    assert response.json()["reason_code"] == "draft_rule_mismatch"
    assert store.jobs == {}
    assert calls == []


def test_primary_parse_bound_job_retry_returns_the_original_job_without_replaying_token() -> None:
    calls: list[str] = []
    client, store = _client(execution_enabled=False, calls=calls)
    draft = _parse_executable_draft(client)
    payload = {
        "parse_token": draft["parse_token"],
        "client_idempotency_key": "32ecc88e-a50d-4b4d-9c5e-573d817b410a",
        "spec_version": draft["spec_version"],
        "spec_hash": draft["spec_hash"],
        "strategy_execution_spec": draft["strategy_execution_spec"],
    }

    first = client.post(ANALYSIS_JOBS_PATH, json=payload)
    retry = client.post(ANALYSIS_JOBS_PATH, json=payload)

    assert first.status_code == 201
    assert retry.status_code == 201
    assert retry.json()["job_id"] == first.json()["job_id"]
    assert len(store.jobs) == 1
    assert len(calls) == 1


def test_primary_parse_bound_retry_after_app_recreation_uses_the_durable_admission_record() -> None:
    """A new process has no local retry fence, so this exercises the store boundary."""

    calls: list[str] = []
    client, store = _client(execution_enabled=False, calls=calls)
    draft = _parse_executable_draft(client)
    payload = {
        "parse_token": draft["parse_token"],
        "client_idempotency_key": "32ecc88e-a50d-4b4d-9c5e-573d817b410a",
        "spec_version": draft["spec_version"],
        "spec_hash": draft["spec_hash"],
        "strategy_execution_spec": draft["strategy_execution_spec"],
    }

    first = client.post(ANALYSIS_JOBS_PATH, json=payload)
    recovered_client, _ = _client(
        execution_enabled=False,
        calls=calls,
        store=store,
    )
    retry = recovered_client.post(ANALYSIS_JOBS_PATH, json=payload)

    assert first.status_code == 201
    assert retry.status_code == 201
    assert retry.json()["job_id"] == first.json()["job_id"]
    assert len(store.jobs) == 1
    assert len(calls) == 1
    assert {state for _job_id, state, _claimed_at in store._analysis_job_outbox.values()} == {
        "delivered"
    }


def test_outbox_runner_escape_is_settled_as_a_terminal_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dispatch infrastructure bug may not leave a queued job without another request."""

    store = InMemoryAnalysisJobStore()
    store.register_parse_token(
        nonce_hash="a" * 64,
        user_id="local-dev-user",
        spec_version="strategy-execution-spec.v1",
        spec_hash="b" * 64,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    admission = store.admit_parse_bound_job(
        "market=KRX; timeframe=daily; entry=rsi<=30; exit=rsi>=70",
        nonce_hash="a" * 64,
        user_id="local-dev-user",
        spec_version="strategy-execution-spec.v1",
        spec_hash="b" * 64,
        client_idempotency_key="dispatch-escape-key",
    )

    def escaped_runner(*_args, **_kwargs):
        raise RuntimeError("injected dispatcher escape")

    monkeypatch.setattr(api_module, "run_job_sync", escaped_runner)
    asyncio.run(
        api_module._dispatch_analysis_job_outbox(
            store,
            analysis_runner=lambda _query, trace_id: _ready_envelope(trace_id),
            audit_sink=None,
            events=JobEventBuffer(),
            cancellations=CancellationRegistry(),
        )
    )

    job = store.get_job(admission.job.job_id)
    assert job is not None
    assert job.status is AnalysisJobStatus.FAILED
    assert {state for _job_id, state, _claimed_at in store._analysis_job_outbox.values()} == {
        "delivered"
    }


def test_primary_job_refuses_a_signed_parse_token_that_was_not_durably_registered() -> None:
    """A valid HMAC alone cannot bypass the parse-token admission ledger."""

    calls: list[str] = []
    client, store = _client(execution_enabled=False, calls=calls)
    signer = RuleDraftSigner("research-contract-test-secret", key_version="test-v1")
    draft = build_rule_draft(
        query="RSI가 30 이하이고 RSI가 70 이상인 일반 조건식을 검토해 주세요.",
        user_id="local-dev-user",
        signer=signer,
    )

    response = client.post(
        ANALYSIS_JOBS_PATH,
        json={
            "parse_token": draft.parse_token,
            "client_idempotency_key": "32ecc88e-a50d-4b4d-9c5e-573d817b410a",
            "spec_version": draft.spec_version,
            "spec_hash": draft.spec_hash,
            "strategy_execution_spec": draft.strategy_execution_spec.model_dump(),
        },
    )

    assert response.status_code == 409
    assert response.json()["reason_code"] == "draft_replayed"
    assert store.jobs == {}
    assert calls == []


def test_primary_parse_bound_job_rejects_an_idempotency_key_reused_for_another_spec() -> None:
    calls: list[str] = []
    client, store = _client(execution_enabled=False, calls=calls)
    draft = _parse_executable_draft(client)
    payload = {
        "parse_token": draft["parse_token"],
        "client_idempotency_key": "32ecc88e-a50d-4b4d-9c5e-573d817b410a",
        "spec_version": draft["spec_version"],
        "spec_hash": draft["spec_hash"],
        "strategy_execution_spec": draft["strategy_execution_spec"],
    }

    first = client.post(ANALYSIS_JOBS_PATH, json=payload)
    conflicting = client.post(ANALYSIS_JOBS_PATH, json={**payload, "spec_hash": "b" * 64})

    assert first.status_code == 201
    assert conflicting.status_code == 409
    assert conflicting.json()["reason_code"] == "idempotency_key_reused"
    assert len(store.jobs) == 1
    assert len(calls) == 1


def test_data_evidence_probe_is_hidden_token_gated_and_has_no_job_side_effects(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setenv(DATA_EVIDENCE_PROBE_TOKEN_ENV, "operator-only")
    monkeypatch.setattr(
        api_module,
        "measure_research_runtime_facts_from_env",
        lambda *_args: ResearchRuntimeFacts(
            dsn_configured=True,
            source="postgres",
            production_eligible=False,
        ),
    )
    client, store = _client(execution_enabled=True, calls=calls)

    assert client.get(DATA_EVIDENCE_PROBE_PATH).status_code == 404
    response = client.get(
        DATA_EVIDENCE_PROBE_PATH,
        headers={"X-AI-Evidence-Probe": "operator-only"},
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "ineligible"
    assert response.json()["reason_code"] == "not_production_eligible"
    assert store.jobs == {}
    assert calls == []


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


class _ReadOnlyTokenResolver:
    """Records the one identity read the preflight boundary is allowed to perform."""

    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, raw_token: str) -> ResolvedAccountToken | None:
        self.calls += 1
        return ResolvedAccountToken(
            token_id="preflight-token",
            user_id="preflight-user",
            quota_limit=1,
            quota_window_seconds=60,
        )


class _QuotaSpy:
    def __init__(self) -> None:
        self.calls = 0
        self.idempotency_keys: list[str | None] = []

    async def check_and_consume(
        self,
        token: ResolvedAccountToken,
        *,
        idempotency_key: str | None = None,
    ) -> None:
        self.calls += 1
        self.idempotency_keys.append(idempotency_key)


def test_durable_idempotent_retry_does_not_consume_bearer_quota_again() -> None:
    """A retry after process recreation reads admission before charging quota."""

    calls: list[str] = []
    quota = _QuotaSpy()
    first_client, store = _client(
        execution_enabled=False,
        calls=calls,
        account_token_resolver=_ReadOnlyTokenResolver(),
        account_token_quota=quota,
    )
    headers = {"Authorization": "Bearer retry-safe-token"}
    parse = first_client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={"natural_language": "RSI가 30 이하이고 RSI가 70 이상인 일반 조건식을 검토해 주세요."},
        headers=headers,
    )
    assert parse.status_code == 200
    draft = parse.json()
    payload = {
        "parse_token": draft["parse_token"],
        "client_idempotency_key": "quota-retry-key-123456",
        "spec_version": draft["spec_version"],
        "spec_hash": draft["spec_hash"],
        "strategy_execution_spec": draft["strategy_execution_spec"],
    }

    first = first_client.post(ANALYSIS_JOBS_PATH, json=payload, headers=headers)
    retry_client, _ = _client(
        execution_enabled=False,
        calls=calls,
        store=store,
        account_token_resolver=_ReadOnlyTokenResolver(),
        account_token_quota=quota,
    )
    retry = retry_client.post(ANALYSIS_JOBS_PATH, json=payload, headers=headers)

    assert first.status_code == 201
    assert retry.status_code == 201
    assert retry.json()["job_id"] == first.json()["job_id"]
    assert quota.calls == 1
    assert quota.idempotency_keys == ["quota-retry-key-123456"]


def test_scope_refusal_transport_performs_only_identity_read_before_all_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public 422 must be returned before every signer/job/audit/runner boundary.

    The token lookup is deliberately the lone permitted call: it is read-only and keeps
    refusal responses scoped to an authenticated caller without spending quota.
    """

    import ai_graph.api as api_module

    calls: list[str] = []
    store = InMemoryAnalysisJobStore()
    token_resolver = _ReadOnlyTokenResolver()
    quota = _QuotaSpy()

    def forbidden(name: str):
        def fail(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"refused request reached {name}")

        return fail

    monkeypatch.setattr(store, "create_job", forbidden("job_store"))
    monkeypatch.setattr(api_module, "build_rule_draft", forbidden("signer"))
    monkeypatch.setattr(api_module, "_build_analysis_runner_with_audit", forbidden("audit_runner"))

    app = create_app(
        store,
        analysis_runner=forbidden("runner"),
        session_resolver=DisabledSessionResolver(),
        account_token_resolver=token_resolver,
        account_token_quota=quota,
        rule_draft_signer=RuleDraftSigner("research-contract-test-secret", key_version="test-v1"),
        research_execution_enabled=True,
    )
    client = TestClient(app)

    response = client.post(
        SPEC_STRATEGY_PARSE_PATH,
        json={"natural_language": "내 계좌에 맞는 종목을 골라줘"},
        headers={"Authorization": "Bearer read-only-token"},
    )

    assert response.status_code == 422
    assert response.json()["kind"] == "scope_refusal"
    assert token_resolver.calls == 1
    assert quota.calls == 0
    assert calls == []
