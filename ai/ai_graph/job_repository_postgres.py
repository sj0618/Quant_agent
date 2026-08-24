from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ai_graph.jobs import AnalysisJob, AnalysisJobStatus, InMemoryAnalysisJobStore
from ai_graph.schemas import APIEnvelope, Stage

_logger = logging.getLogger(__name__)


def _job_document(job: AnalysisJob) -> dict[str, Any]:
    document = job.model_dump(mode="json")
    document.update(
        {
            "user_id": job.user_id,
            "strategy_id": job.strategy_id,
            "run_id": job.run_id,
            "report_id": job.report_id,
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
    ) -> AnalysisJob:
        job = InMemoryAnalysisJobStore().create_job(
            request_text,
            user_id=user_id,
            strategy_id=strategy_id,
            run_id=run_id,
            fallback_reasons=fallback_reasons,
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

    def _decode_rows(self, rows: Sequence[Any]) -> list[AnalysisJob]:
        """Decode what this table can still be read as, and say what it cannot.

        Fields have been added to the job document without a backfill - `execution_manifest`,
        and the `availability` tag the public performance union now discriminates on - so
        rows written by an older build no longer validate. One such row used to take down
        the whole call: `GET /analysis-jobs` returned 500 for any user whose history
        contained one, and once startup began reconciling interrupted jobs it stopped the
        deploy outright.

        A list that is already limit-truncated is the wrong place to be all-or-nothing, so
        undecodable rows are dropped from the result. They are not dropped quietly: each is
        logged with its job id, because a row that cannot be decoded is also a row the
        restart reaper cannot transition, and one stuck in `running` will spin forever
        until someone acts on it.
        """

        decoded: list[AnalysisJob] = []
        undecodable: list[str] = []
        for row in rows:
            document = row["job_jsonb"]
            try:
                decoded.append(AnalysisJob.model_validate(document))
            except Exception:
                job_id = "unknown"
                if isinstance(document, dict):
                    job_id = str(document.get("job_id") or "unknown")
                    status = str(document.get("status") or "unknown")
                    job_id = f"{job_id}(status={status})"
                undecodable.append(job_id)
        if undecodable:
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
