"""Legacy job rows stay readable in history but cannot weaken startup recovery."""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_graph.api import create_app
from ai_graph.job_repository_postgres import (
    PersistedJobReconciliationError,
    PostgresAnalysisJobRepository,
    _job_document,
)
from ai_graph.job_store_persistent import PersistentAnalysisJobStore
from ai_graph.jobs import InMemoryAnalysisJobStore, InterruptedJobReconciliationError
from ai_graph.schemas import Stage


class _Rows:
    def __init__(self, rows): self._rows = rows
    def fetchall(self): return self._rows
    def fetchone(self): return self._rows[0] if self._rows else None


class _Connection:
    def __init__(self, rows): self._rows = rows
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, *_a, **_k): return _Rows(self._rows)


def _legacy_document() -> dict:
    """What production actually holds: written before execution_manifest existed."""
    return {
        "job_id": "job_legacy01",
        "trace_id": "legacytrace",
        "query": "삼성전자 RSI 전략",
        "status": "running",
        "polling_stage": "interpreting",
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
        "stages": [],
        "fallback_reasons": [],
    }


def test_a_legacy_row_does_not_take_the_whole_list_down(caplog):
    store = InMemoryAnalysisJobStore()
    fresh = store.create_job("현재 빌드가 쓴 잡")
    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    repo._connector = lambda *a, **k: _Connection(
        [{"job_jsonb": _legacy_document()}, {"job_jsonb": _job_document(fresh)}]
    )

    with caplog.at_level(logging.WARNING):
        jobs = repo.list_jobs(limit=10)

    assert [job.job_id for job in jobs] == [fresh.job_id]
    # Dropped, but not quietly: the id and its status have to reach the operator.
    assert "job_legacy01" in caplog.text
    assert "status=running" in caplog.text


def test_an_active_legacy_row_is_reported_separately_from_the_ones_that_decode() -> None:
    """A restart must not hide an active row it cannot transition - but it can settle it.

    Refusing startup over these rows is not a policy that terminates: they are already in
    the database, so nothing the process does on boot makes them decodable. The read
    therefore hands them back by id instead of raising, and the reaper settles them.
    """

    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    repo._connector = lambda *a, **k: _Connection([{"job_jsonb": _legacy_document()}])

    batch = repo.list_jobs_for_reconciliation()

    assert batch.jobs == []
    assert batch.undecodable_job_ids == ["job_legacy01"]


def test_an_active_row_with_no_id_still_refuses() -> None:
    """Settling happens by id. Without one there is nothing to settle, so fail closed."""

    document = _legacy_document()
    del document["job_id"]
    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    repo._connector = lambda *a, **k: _Connection([{"job_jsonb": document}])

    with pytest.raises(PersistedJobReconciliationError):
        repo.list_jobs_for_reconciliation()


def test_startup_settles_an_undecodable_active_row_instead_of_refusing(caplog) -> None:
    """The deploy blocker: production holds these rows, so refusing never let the app up."""

    settled: list[str] = []

    class _Repo(PostgresAnalysisJobRepository):
        def __init__(self) -> None:
            self._dsn = "postgresql://example"
            self._connector = lambda *a, **k: _Connection([{"job_jsonb": _legacy_document()}])

        def force_fail_undecodable_job(self, job_id, *, error_message, reason):
            settled.append(job_id)
            return True

    with caplog.at_level(logging.WARNING), TestClient(
        create_app(PersistentAnalysisJobStore(_Repo()))
    ) as client:
        assert client.get("/health").status_code == 200

    assert settled == ["job_legacy01"]
    assert "job_legacy01" in caplog.text


def test_startup_still_refuses_when_an_undecodable_row_cannot_be_settled() -> None:
    """If even the direct write fails, the row really is stranded - say so loudly."""

    class _Repo(PostgresAnalysisJobRepository):
        def __init__(self) -> None:
            self._dsn = "postgresql://example"
            self._connector = lambda *a, **k: _Connection([{"job_jsonb": _legacy_document()}])

        def force_fail_undecodable_job(self, job_id, *, error_message, reason):
            raise RuntimeError("row is locked")

    with pytest.raises(InterruptedJobReconciliationError), TestClient(
        create_app(PersistentAnalysisJobStore(_Repo()))
    ):
        pass


def test_active_rows_over_reconciliation_limit_refuse_startup() -> None:
    """A bounded sweep must fail closed rather than strand the extra active job."""

    source = InMemoryAnalysisJobStore()
    first = source.create_job("첫 번째 재시작 검토 잡")
    second = source.create_job("두 번째 재시작 검토 잡")
    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    repo._connector = lambda *a, **k: _Connection(
        [{"job_jsonb": _job_document(first)}, {"job_jsonb": _job_document(second)}]
    )

    with pytest.raises(PersistedJobReconciliationError, match="exceed"):
        repo.list_jobs_for_reconciliation(limit=1)


def test_a_store_that_cannot_be_read_still_raises():
    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    def boom(*a, **k): raise RuntimeError("connection refused")
    repo._connector = boom
    try:
        repo.list_jobs(limit=10)
    except RuntimeError as e:
        assert "connection refused" in str(e)
    else:
        raise AssertionError("a store outage must not look like an empty list")


def _legacy_failed_document(
    *, missing_diagnostic: bool = False, invalid_failure_stage: bool = True
) -> dict:
    source = InMemoryAnalysisJobStore()
    job = source.create_job("과거 실패 분석")
    failed = source.fail_job(job.job_id, "past failure")
    document = _job_document(failed)
    document.pop("execution_manifest")
    document.pop("execution_spec_version")
    document.pop("execution_spec_hash")
    assert document["result"] is not None
    if missing_diagnostic:
        document["result"].pop("failure_cause")
    elif invalid_failure_stage:
        document["result"]["failure_cause"]["failure_stage"] = "analyzing"
    return document


def _repository_for_single_document(document: dict) -> PostgresAnalysisJobRepository:
    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    repo._connector = lambda *a, **k: _Connection([{"job_jsonb": document}])
    return repo


def test_legacy_failed_row_with_free_form_stage_is_normalized_only_on_read() -> None:
    document = _legacy_failed_document()

    decoded = _repository_for_single_document(document).get_job(document["job_id"])

    assert decoded is not None
    assert decoded.result is not None
    assert decoded.result.failure_cause is not None
    assert decoded.result.failure_cause.failure_stage is Stage.FINALIZING
    assert "failure:legacy_stage_normalized" in decoded.result.failure_cause.evidence_refs
    assert document["result"]["failure_cause"]["failure_stage"] == "analyzing"


def test_legacy_failed_row_without_diagnostic_gets_safe_unknown_diagnostic() -> None:
    document = _legacy_failed_document(missing_diagnostic=True)

    decoded = _repository_for_single_document(document).get_job(document["job_id"])

    assert decoded is not None
    assert decoded.result is not None
    assert decoded.result.failure_cause is not None
    assert decoded.result.failure_cause.subcause == "unknown"
    assert decoded.result.failure_cause.failure_stage is Stage.FINALIZING
    assert decoded.result.failure_cause.evidence_refs == ["failure:legacy_missing_diagnostic"]


def test_legacy_failed_row_with_a_valid_typed_diagnostic_remains_readable() -> None:
    document = _legacy_failed_document(invalid_failure_stage=False)

    decoded = _repository_for_single_document(document).get_job(document["job_id"])

    assert decoded is not None
    assert decoded.result is not None
    assert decoded.result.failure_cause is not None
    assert decoded.result.failure_cause.failure_stage is Stage.FINALIZING
    assert decoded.execution_manifest.policy_hashes == {
        "legacy_execution_manifest_unavailable": decoded.execution_manifest.contract_hash
    }


def test_current_contract_row_with_invalid_failure_stage_still_fails_closed() -> None:
    source = InMemoryAnalysisJobStore()
    job = source.create_job("현재 계약 실패 분석")
    failed = source.fail_job(job.job_id, "current failure")
    document = _job_document(failed)
    document["execution_spec_version"] = "strategy-execution-spec.v1"
    document["execution_spec_hash"] = "a" * 64
    assert document["result"] is not None
    document["result"]["failure_cause"]["failure_stage"] = "analyzing"

    with pytest.raises(ValidationError) as exc_info:
        _repository_for_single_document(document).get_job(document["job_id"])

    assert ("result", "failure_cause", "failure_stage") in {
        tuple(error["loc"]) for error in exc_info.value.errors()
    }


def test_the_settle_statement_casts_every_parameter() -> None:
    """Postgres cannot infer a bare placeholder inside jsonb_build_object.

    Without an explicit cast the statement dies with IndeterminateDatatype at runtime -
    which, on the startup path, means the deploy never comes up. Nothing local exercises
    real Postgres, so the cast is pinned here.
    """

    captured: dict[str, object] = {}

    class _Recording(_Connection):
        def execute(self, query, params=None):
            captured["query"] = query
            captured["params"] = params
            return _Rows([])

    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    repo._connector = lambda *a, **k: _Recording([])

    repo.force_fail_undecodable_job("job_legacy01", error_message="중단됨", reason="restart")

    query = str(captured["query"])
    assert "%s::text" in query
    # No placeholder may be left uncast.
    assert "%s," not in query.replace("%s::text,", "")
    assert "job_id = %s::text" in query
    assert captured["params"] == ("중단됨", "restart", "job_legacy01")


def test_parse_bound_admission_writes_job_idempotency_and_outbox_in_one_transaction() -> None:
    """Pin the transaction shape locally; isolated PostgreSQL is still an R/O gate."""

    class _Transaction:
        def __init__(self, connection) -> None:
            self.connection = connection

        def __enter__(self):
            self.connection.transaction_count += 1
            return self

        def __exit__(self, *_args):
            return False

    class _AdmissionConnection:
        def __init__(self):
            self.queries: list[tuple[str, object]] = []
            self.transaction_count = 0
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return _Transaction(self)

        def execute(self, query, params=None):
            self.queries.append((str(query), params))
            if "SELECT spec_hash, job_id" in query:
                return _Rows([])
            if "UPDATE app.ai_parse_token" in query:
                return _Rows([{"nonce_hash": "a" * 64}])
            return _Rows([])

    connection = _AdmissionConnection()
    repo = PostgresAnalysisJobRepository(
        "postgresql://example",
        connector=lambda *_args, **_kwargs: connection,
    )

    admission = repo.admit_parse_bound_job(
        "market=KRX; timeframe=daily; entry=rsi<=30; exit=rsi>=70",
        nonce_hash="a" * 64,
        user_id="user-1",
        spec_version="strategy-execution-spec.v1",
        spec_hash="b" * 64,
        client_idempotency_key="retry-key-123456",
    )

    statements = "\n".join(query for query, _params in connection.queries)
    assert admission.created is True
    assert admission.outbox_id is not None
    assert connection.transaction_count == 1
    assert "UPDATE app.ai_parse_token" in statements
    assert "INSERT INTO app.ai_analysis_job" in statements
    assert "INSERT INTO app.ai_analysis_job_idempotency" in statements
    assert "INSERT INTO app.ai_analysis_job_outbox" in statements
    assert "request_text" not in statements


def test_outbox_claim_leases_only_queued_jobs_with_skip_locked() -> None:
    captured: dict[str, object] = {}

    class _Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class _ClaimConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return _Transaction()

        def execute(self, query, params=None):
            captured["query"] = str(query)
            captured["params"] = params
            return _Rows([{"outbox_id": "outbox-1", "job_id": "job-1"}])

    repo = PostgresAnalysisJobRepository(
        "postgresql://example",
        connector=lambda *_args, **_kwargs: _ClaimConnection(),
    )

    messages = repo.claim_analysis_job_outbox(limit=3)

    assert [(message.outbox_id, message.job_id) for message in messages] == [("outbox-1", "job-1")]
    assert captured["params"] == (3,)
    assert "FOR UPDATE OF outbox SKIP LOCKED" in str(captured["query"])
    assert "job.job_jsonb ->> 'status' = 'queued'" in str(captured["query"])


def test_admission_rereads_idempotency_after_a_concurrent_nonce_consume() -> None:
    """The losing concurrent retry returns the winner instead of a misleading replay."""

    winner = InMemoryAnalysisJobStore().create_job("canonical execution query", user_id="user-1")

    class _Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class _RaceConnection:
        def __init__(self) -> None:
            self.idempotency_reads = 0
            self.queries: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def transaction(self):
            return _Transaction()

        def execute(self, query, _params=None):
            query = str(query)
            self.queries.append(query)
            if "SELECT spec_hash, job_id" in query:
                self.idempotency_reads += 1
                if self.idempotency_reads == 1:
                    return _Rows([])
                return _Rows([{"spec_hash": "b" * 64, "job_id": winner.job_id}])
            if "UPDATE app.ai_parse_token" in query:
                return _Rows([])
            if "SELECT job_jsonb" in query:
                return _Rows([{"job_jsonb": _job_document(winner)}])
            raise AssertionError(f"unexpected write after concurrent winner: {query}")

    connection = _RaceConnection()
    repo = PostgresAnalysisJobRepository(
        "postgresql://example",
        connector=lambda *_args, **_kwargs: connection,
    )

    admission = repo.admit_parse_bound_job(
        "canonical execution query",
        nonce_hash="a" * 64,
        user_id="user-1",
        spec_version="strategy-execution-spec.v1",
        spec_hash="b" * 64,
        client_idempotency_key="retry-key-123456",
    )

    assert admission.created is False
    assert admission.job.job_id == winner.job_id
    assert connection.idempotency_reads == 2
    assert not any("INSERT INTO app.ai_analysis_job" in query for query in connection.queries)
