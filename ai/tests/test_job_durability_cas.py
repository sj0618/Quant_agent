"""CORE-JOB-01: the job row is written with compare-and-swap, a lease, and an outbox.

These drive a recording fake rather than a live server. They prove the statements the
repository issues carry the predicates that make concurrent writes safe; replaying them
against a real PostgreSQL is a separate, server-side evidence axis and is not claimed
here.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from ai_graph.job_repository_postgres import PostgresAnalysisJobRepository, _job_document
from ai_graph.jobs import InMemoryAnalysisJobStore, JobConcurrentUpdateError


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row else []


class _Connection:
    """Records every statement and answers each one from a scripted queue."""

    def __init__(self, answers):
        self.statements: list[tuple[str, tuple]] = []
        self._answers = list(answers)
        self.transactions = 0

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield self

    def execute(self, sql, params=()):
        self.statements.append((" ".join(sql.split()), tuple(params)))
        return _Result(self._answers.pop(0) if self._answers else None)


def _repo(connection) -> PostgresAnalysisJobRepository:
    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    repo._connector = lambda *_a, **_k: connection
    return repo


def _job(version: int = 1):
    job = InMemoryAnalysisJobStore().create_job("RSI가 30 이하인 KOSPI200")
    return job.model_copy(update={"version": version})


def test_an_update_carries_the_version_it_read() -> None:
    connection = _Connection([{"version": 8}])
    saved = _repo(connection)._save(_job(version=7))

    sql, params = connection.statements[0]
    assert "UPDATE app.ai_analysis_job" in sql
    assert "version = version + 1" in sql
    assert "WHERE job_id = %s AND version = %s" in sql
    assert params[-1] == 7
    assert saved.version == 8


def test_a_lost_race_raises_instead_of_overwriting() -> None:
    """Zero rows updated means another writer moved the row between read and write."""

    connection = _Connection([None])
    with pytest.raises(JobConcurrentUpdateError):
        _repo(connection)._save(_job(version=7))


def test_the_read_carries_the_row_version_onto_the_job() -> None:
    job = _job()
    connection = _Connection([{"job_jsonb": _job_document(job), "version": 12}])

    assert _repo(connection).get_job(job.job_id).version == 12


def test_the_version_is_not_written_into_the_job_document() -> None:
    """It describes the row. In the document, every write would change what it guards."""

    assert "version" not in _job_document(_job(version=5))


def test_create_writes_the_job_and_its_outbox_event_in_one_transaction() -> None:
    connection = _Connection([None, None])
    _repo(connection)._insert(_job(), idempotency_key="idem-1")

    assert connection.transactions == 1
    job_sql, job_params = connection.statements[0]
    outbox_sql, outbox_params = connection.statements[1]
    assert "INSERT INTO app.ai_analysis_job" in job_sql
    assert "idempotency_key" in job_sql
    assert job_params[-1] == "idem-1"
    assert "INSERT INTO app.ai_analysis_job_outbox" in outbox_sql
    assert outbox_params[1] == "analysis_job_created"


def test_a_claim_only_takes_a_lease_nobody_holds() -> None:
    connection = _Connection([{"fencing_token": 4}])
    token = _repo(connection).claim_job("job_1", owner="worker-a", lease_seconds=30)

    sql, _ = connection.statements[0]
    assert "lease_expires_at IS NULL OR lease_expires_at < now()" in sql
    assert "fencing_token = fencing_token + 1" in sql
    assert token == 4


def test_a_second_worker_gets_nothing_while_the_lease_is_live() -> None:
    connection = _Connection([None])

    assert _repo(connection).claim_job("job_1", owner="worker-b", lease_seconds=30) is None


def test_renewing_requires_being_the_holder_and_not_being_expired() -> None:
    connection = _Connection([{"job_id": "job_1"}])
    assert _repo(connection).renew_lease("job_1", owner="worker-a", lease_seconds=30) is True

    sql, params = connection.statements[0]
    assert "lease_owner = %s" in sql
    assert "lease_expires_at >= now()" in sql
    assert "worker-a" in params


def test_a_worker_cannot_renew_a_lease_it_does_not_hold() -> None:
    assert _repo(_Connection([None])).renew_lease("job_1", owner="worker-b", lease_seconds=30) is False


def test_releasing_clears_both_lease_fields_together() -> None:
    """A lease owner without an expiry never expires - the failure the lease prevents."""

    connection = _Connection([{"job_id": "job_1"}])
    _repo(connection).release_lease("job_1", owner="worker-a")

    sql, _ = connection.statements[0]
    assert "lease_owner = NULL, lease_expires_at = NULL" in sql
