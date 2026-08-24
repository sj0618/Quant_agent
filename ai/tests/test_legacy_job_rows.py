"""A job row from an older build must not take down the list or the startup sweep."""
from __future__ import annotations

import logging

from ai_graph.job_repository_postgres import PostgresAnalysisJobRepository, _job_document
from ai_graph.jobs import InMemoryAnalysisJobStore


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
