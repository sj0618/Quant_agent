"""Legacy job rows stay readable in history but cannot weaken startup recovery."""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from ai_graph.api import create_app
from ai_graph.job_repository_postgres import (
    PersistedJobReconciliationError,
    PostgresAnalysisJobRepository,
    _job_document,
)
from ai_graph.job_store_persistent import PersistentAnalysisJobStore
from ai_graph.jobs import InMemoryAnalysisJobStore, InterruptedJobReconciliationError


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


def test_active_legacy_row_refuses_restart_reconciliation() -> None:
    """A restart must not hide an active row that cannot be transitioned terminal."""

    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    repo._connector = lambda *a, **k: _Connection([{"job_jsonb": _legacy_document()}])

    with pytest.raises(PersistedJobReconciliationError):
        repo.list_jobs_for_reconciliation()


def test_active_legacy_row_refuses_application_startup() -> None:
    """The strict persistent read reaches the lifespan before any route can serve."""

    repo = PostgresAnalysisJobRepository.__new__(PostgresAnalysisJobRepository)
    repo._dsn = "postgresql://example"
    repo._connector = lambda *a, **k: _Connection([{"job_jsonb": _legacy_document()}])

    with pytest.raises(InterruptedJobReconciliationError), TestClient(
        create_app(PersistentAnalysisJobStore(repo))
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
