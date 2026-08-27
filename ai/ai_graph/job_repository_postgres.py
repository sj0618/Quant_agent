from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ai_graph.jobs import AnalysisJob, AnalysisJobStatus, InMemoryAnalysisJobStore
from ai_graph.schemas import APIEnvelope, Stage

_logger = logging.getLogger(__name__)


class PersistedJobReconciliationError(RuntimeError):
    """An active persisted job cannot be reconciled safely after a restart."""


@dataclass(frozen=True)
class ReconciliationBatch:
    """Active rows this build can load, and the ones it can only settle by id."""

    jobs: list[AnalysisJob]
    undecodable_job_ids: list[str]


def _job_document(job: AnalysisJob) -> dict[str, Any]:
    document = job.model_dump(mode="json")
    document.update(
        {
            "user_id": job.user_id,
            "strategy_id": job.strategy_id,
            "run_id": job.run_id,
            "report_id": job.report_id,
            "execution_spec_version": job.execution_spec_version,
            "execution_spec_hash": job.execution_spec_hash,
            "client_idempotency_key": job.client_idempotency_key,
            "status": job.status.value,
            "polling_stage": job.polling_stage.value,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "debug_ref": job.debug_ref,
            "fallback_reasons": job.fallback_reasons,
            "error_message": job.error_message,
            "owner_incarnation": job.owner_incarnation,
            "execution_manifest": job.execution_manifest.model_dump(mode="json"),
        }
    )
    return document


class PostgresAnalysisJobRepository:
    """Small JSONB-backed implementation of the existing job repository contract."""

    def __init__(self, dsn: str, *, connector: Callable[..., Any] = psycopg.connect) -> None:
        self._dsn = dsn
        self._connector = connector

    def create_job(
        self,
        request_text: str,
        *,
        user_id: str | None = None,
        strategy_id: str | None = None,
        run_id: str | None = None,
        fallback_reasons: Sequence[str] | None = None,
        execution_spec_version: str | None = None,
        execution_spec_hash: str | None = None,
        client_idempotency_key: str | None = None,
    ) -> AnalysisJob:
        job = InMemoryAnalysisJobStore().create_job(
            request_text,
            user_id=user_id,
            strategy_id=strategy_id,
            run_id=run_id,
            fallback_reasons=fallback_reasons,
            execution_spec_version=execution_spec_version,
            execution_spec_hash=execution_spec_hash,
            client_idempotency_key=client_idempotency_key,
        )
        self._save(job)
        return job

    def get_job(self, job_id: str) -> AnalysisJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT job_jsonb FROM app.ai_analysis_job WHERE job_id = %s",
                (job_id,),
            ).fetchone()
        return AnalysisJob.model_validate(row["job_jsonb"]) if row else None

    def update_job_status(
        self,
        job_id: str,
        status: AnalysisJobStatus | str,
        polling_stage: Stage | str,
        *,
        fallback_reasons: Sequence[str] | None = None,
        error_message: str | None = None,
        message: str | None = None,
    ) -> AnalysisJob:
        store = self._loaded_store(job_id)
        job = store.update_job_status(
            job_id,
            status,
            polling_stage,
            fallback_reasons=fallback_reasons,
            error_message=error_message,
            message=message,
        )
        self._save(job)
        return job

    def complete_job(
        self,
        job_id: str,
        result_envelope: APIEnvelope,
        *,
        fallback_reasons: Sequence[str] | None = None,
    ) -> AnalysisJob:
        store = self._loaded_store(job_id)
        job = store.complete_job(
            job_id,
            result_envelope,
            fallback_reasons=fallback_reasons,
        )
        self._save(job)
        return job

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        *,
        fallback_reasons: Sequence[str] | None = None,
        result_envelope: APIEnvelope | None = None,
    ) -> AnalysisJob:
        store = self._loaded_store(job_id)
        job = store.fail_job(
            job_id,
            error_message,
            fallback_reasons=fallback_reasons,
            result_envelope=result_envelope,
        )
        self._save(job)
        return job

    def list_jobs(self, *, limit: int = 100) -> list[AnalysisJob]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT job_jsonb
                FROM (
                    SELECT job_jsonb, updated_at
                    FROM app.ai_analysis_job
                    ORDER BY updated_at DESC
                    LIMIT %s
                ) AS recent_jobs
                ORDER BY updated_at ASC
                """,
                (limit,),
            ).fetchall()
        return self._decode_rows(rows)

    def list_jobs_for_reconciliation(self, *, limit: int = 500) -> ReconciliationBatch:
        """Read every active job that startup must either settle or reject.

        The ordinary history view is deliberately best-effort so one pre-contract
        terminal row cannot hide all later results.  Startup is a different boundary:
        a queued or running row omitted from this read would remain visibly in-flight
        forever after its owning process has stopped.  Read one extra row so a bounded
        sweep never silently leaves active work behind, then decode the active subset
        strictly.
        """

        if limit < 1:
            raise ValueError("reconciliation job limit must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT job_jsonb
                FROM app.ai_analysis_job
                WHERE job_jsonb ->> 'status' IN ('queued', 'running')
                ORDER BY updated_at ASC
                LIMIT %s
                """,
                (limit + 1,),
            ).fetchall()
        if len(rows) > limit:
            raise PersistedJobReconciliationError(
                "active persisted analysis jobs exceed the restart reconciliation limit"
            )
        decoded, undecodable = self._decode_rows_reporting_failures(rows)
        return ReconciliationBatch(jobs=decoded, undecodable_job_ids=undecodable)

    def force_fail_undecodable_job(self, job_id: str, *, error_message: str, reason: str) -> bool:
        """Settle an active row that cannot be loaded as an `AnalysisJob`.

        Rows written before `execution_manifest` and the performance `availability` tag
        existed cannot be validated, so `fail_job` - which has to read the job first -
        cannot touch them. Refusing startup over them is not an option either: they are
        already in the database, so that policy is an outage with no way out. This writes
        the terminal state straight onto the stored document instead.

        Deliberately narrow: it only moves `queued`/`running` to `failed`, and only sets
        the fields a reader needs to stop waiting. It does not try to reconstruct the
        envelope the current schema would have produced - inventing one from a document
        this build cannot parse would be a guess presented as a record.
        """

        with self._connect() as connection:
            result = connection.execute(
                """
                UPDATE app.ai_analysis_job
                SET job_jsonb = job_jsonb
                        || jsonb_build_object(
                            'status', 'failed',
                            -- Every parameter is cast: inside jsonb_build_object the
                            -- planner has no column to infer a bare placeholder from and
                            -- fails with IndeterminateDatatype.
                            'error_message', %s::text,
                            'completed_at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                            'fallback_reasons',
                            COALESCE(job_jsonb -> 'fallback_reasons', '[]'::jsonb) || to_jsonb(%s::text)
                        ),
                    updated_at = now()
                WHERE job_id = %s::text
                  AND job_jsonb ->> 'status' IN ('queued', 'running')
                """,
                (error_message, reason, job_id),
            )
        return getattr(result, "rowcount", 0) > 0

    def _decode_rows_reporting_failures(
        self, rows: Sequence[Any]
    ) -> tuple[list[AnalysisJob], list[str]]:
        decoded: list[AnalysisJob] = []
        undecodable: list[str] = []
        for row in rows:
            document = row["job_jsonb"]
            try:
                decoded.append(AnalysisJob.model_validate(document))
            except ValidationError:
                job_id = None
                if isinstance(document, dict):
                    job_id = document.get("job_id")
                if not job_id:
                    raise PersistedJobReconciliationError(
                        "an active persisted analysis job has no id to settle it by"
                    ) from None
                undecodable.append(str(job_id))
        return decoded, undecodable

    def _decode_rows(self, rows: Sequence[Any], *, strict: bool = False) -> list[AnalysisJob]:
        """Decode what this table can still be read as, and say what it cannot.

        Fields have been added to the job document without a backfill - `execution_manifest`,
        and the `availability` tag the public performance union now discriminates on - so
        rows written by an older build no longer validate. One such row used to take down
        the whole call: `GET /analysis-jobs` returned 500 for any user whose history
        contained one, and once startup began reconciling interrupted jobs it stopped the
        deploy outright.

        A history list that is already limit-truncated is the wrong place to be
        all-or-nothing, so its undecodable rows are dropped with an operator warning.
        Reconciliation passes ``strict=True`` after selecting only active rows: it must
        refuse startup instead of hiding a queued/running row that it cannot settle.
        """

        decoded: list[AnalysisJob] = []
        undecodable: list[str] = []
        for row in rows:
            document = row["job_jsonb"]
            try:
                decoded.append(AnalysisJob.model_validate(document))
            except ValidationError:
                job_id = "unknown"
                if isinstance(document, dict):
                    job_id = str(document.get("job_id") or "unknown")
                    status = str(document.get("status") or "unknown")
                    job_id = f"{job_id}(status={status})"
                undecodable.append(job_id)
        if undecodable:
            if strict:
                raise PersistedJobReconciliationError(
                    "an active persisted analysis job could not be decoded for restart reconciliation"
                )
            _logger.warning(
                "skipped %d analysis job row(s) written by an older build: %s",
                len(undecodable),
                ", ".join(undecodable),
            )
        return decoded

    def _connect(self):
        return self._connector(
            self._dsn,
            row_factory=dict_row,
            connect_timeout=5,
        )

    def _loaded_store(self, job_id: str) -> InMemoryAnalysisJobStore:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(f"analysis job not found: {job_id}")
        return InMemoryAnalysisJobStore(jobs={job_id: job})

    def _save(self, job: AnalysisJob) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app.ai_analysis_job (
                    job_id, user_id, job_jsonb, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    job_jsonb = EXCLUDED.job_jsonb,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    job.job_id,
                    job.user_id,
                    Jsonb(_job_document(job)),
                    job.created_at,
                    job.updated_at,
                ),
            )
