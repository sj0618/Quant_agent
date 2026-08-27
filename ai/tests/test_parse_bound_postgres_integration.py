"""Isolated PostgreSQL evidence for parse-bound durable admission.

Set ``AI_PARSE_ADMISSION_TEST_DSN`` only to a disposable database.  This test resets
its ``app`` schema and must never point at a shared or production database.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from ai_graph.job_repository_postgres import PostgresAnalysisJobRepository
from ai_graph.jobs import AnalysisJobStatus, reap_interrupted_jobs


POSTGRES_TEST_DSN_ENV = "AI_PARSE_ADMISSION_TEST_DSN"
SERVICE_DB_ROOT = Path(__file__).resolve().parents[2] / "service_db"
_DISPOSABLE_DSN = os.getenv(POSTGRES_TEST_DSN_ENV)

pytestmark = pytest.mark.skipif(
    not _DISPOSABLE_DSN,
    reason=f"{POSTGRES_TEST_DSN_ENV} is required for isolated PostgreSQL integration tests",
)


def _reset_disposable_schema(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS app CASCADE")
        connection.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        for path in sorted((SERVICE_DB_ROOT / "migrations").glob("*.sql")):
            connection.execute(path.read_text(encoding="utf-8"))


def _admit(repository: PostgresAnalysisJobRepository):
    return repository.admit_parse_bound_job(
        "market=KRX; timeframe=daily; entry=rsi<=30; exit=rsi>=70",
        nonce_hash="a" * 64,
        user_id="integration-user",
        spec_version="strategy-execution-spec.v1",
        spec_hash="b" * 64,
        client_idempotency_key="integration-retry-key",
    )


def test_postgres_parse_admission_is_atomic_restart_safe_and_lease_recoverable() -> None:
    """Verify migration 024 against a real disposable PostgreSQL database."""

    assert _DISPOSABLE_DSN is not None
    _reset_disposable_schema(_DISPOSABLE_DSN)
    repository = PostgresAnalysisJobRepository(_DISPOSABLE_DSN)
    repository.register_parse_token(
        nonce_hash="a" * 64,
        user_id="integration-user",
        spec_version="strategy-execution-spec.v1",
        spec_hash="b" * 64,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        admissions = list(pool.map(lambda _unused: _admit(repository), range(2)))

    assert sorted(admission.created for admission in admissions) == [False, True]
    assert len({admission.job.job_id for admission in admissions}) == 1
    job = admissions[0].job

    with psycopg.connect(_DISPOSABLE_DSN) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM app.ai_analysis_job),
                (SELECT count(*) FROM app.ai_analysis_job_idempotency),
                (SELECT count(*) FROM app.ai_analysis_job_outbox)
            """
        ).fetchone()
        stored_document = connection.execute(
            "SELECT job_jsonb::text FROM app.ai_analysis_job WHERE job_id = %s", (job.job_id,)
        ).fetchone()[0]
    assert counts == (1, 1, 1)
    assert "RSI가 30 이하" not in stored_document

    # A restart may reap RUNNING work, but it must preserve this queued durable outbox
    # dispatch so the new process can claim it.
    assert reap_interrupted_jobs(repository, incarnation="new-process") == []
    assert repository.get_job(job.job_id).status is AnalysisJobStatus.QUEUED
    first_claim = repository.claim_analysis_job_outbox()
    assert [message.job_id for message in first_claim] == [job.job_id]

    # A killed claimant is lease-recoverable.  This is a disposable-only clock jump,
    # not a production retry or data operation.
    with psycopg.connect(_DISPOSABLE_DSN, autocommit=True) as connection:
        connection.execute(
            """
            UPDATE app.ai_analysis_job_outbox
            SET claimed_at = now() - interval '6 minutes'
            WHERE outbox_id = %s::uuid
            """,
            (first_claim[0].outbox_id,),
        )
    reclaimed = repository.claim_analysis_job_outbox()
    assert [message.outbox_id for message in reclaimed] == [first_claim[0].outbox_id]

    repository.fail_job(job.job_id, "disposable terminal test")
    repository.mark_analysis_job_outbox_delivered(reclaimed[0].outbox_id)
    assert repository.claim_analysis_job_outbox() == []
