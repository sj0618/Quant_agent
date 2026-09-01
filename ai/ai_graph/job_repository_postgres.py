from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ai_graph.jobs import (
    AnalysisJob,
    AnalysisJobOutboxMessage,
    AnalysisJobStatus,
    InMemoryAnalysisJobStore,
    ParseBoundAdmissionError,
    ParseBoundJobAdmission,
    ResearchAppendixOutboxMessage,
)
from ai_graph.immutable_results import ImmutableResultEvidence, read_immutable_result_evidence
from ai_graph.schemas import APIEnvelope, ExecutionSpecV1OrV2, ExplorationExecutionSpecV2, Stage
from ai_graph.exploration_policy import (
    load_active_exploration_policy,
    validate_exploration_spec_against_policy,
)

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
            "execution_spec": (
                job.execution_spec.model_dump(mode="json")
                if job.execution_spec is not None
                else None
            ),
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


_VALID_STAGES = frozenset(stage.value for stage in Stage)
_LEGACY_FAILURE_SAFE_MESSAGE = (
    "과거 분석 결과의 상세 실패 원인을 확인할 수 없습니다. "
    "debug_ref로 추적해 주세요."
)
_LEGACY_MANIFEST_HASH = sha256(b"legacy_execution_manifest_unavailable.v1").hexdigest()
_LEGACY_EMPTY_LEDGER_HASH = sha256(b"{}").hexdigest()


def _legacy_execution_manifest(document: Mapping[str, Any]) -> dict[str, Any]:
    """Represent unavailable old execution evidence without inventing executions."""

    return {
        "schema_version": "1",
        # This is intentionally not the current contract hash: the manifest did not
        # exist when this row was written.
        "contract_hash": _LEGACY_MANIFEST_HASH,
        "run_identity": {
            "job_id": document.get("job_id"),
            "trace_id": document.get("trace_id"),
            "strategy_id": document.get("strategy_id"),
            "run_id": document.get("run_id"),
        },
        "policy_hashes": {"legacy_execution_manifest_unavailable": _LEGACY_MANIFEST_HASH},
        "session": {
            "requested_at": document.get("created_at"),
            "started_at": None,
            "ended_at": document.get("completed_at"),
        },
        "capabilities": {
            "terminal_event_documents": False,
            "corporate_action_events": False,
        },
        "events": {},
        "ledger_event_count": 0,
        "ledger_event_hash": _LEGACY_EMPTY_LEDGER_HASH,
    }


def _decode_persisted_job_document(document: Any) -> AnalysisJob:
    """Read old terminal failures without weakening the current write contract.

    The first durable job format predates both the execution manifest and the
    parse-bound execution identity. Its failed envelopes can contain a free-form
    stage or no diagnostic at all, which a current ``APIEnvelope`` correctly rejects.
    Normalize only that unmistakably pre-contract shape at the storage-read boundary.
    Rows written by the current format continue through strict model validation.
    """

    if not isinstance(document, Mapping):
        return AnalysisJob.model_validate(document)
    if (
        document.get("execution_manifest") is not None
        or document.get("execution_spec_version") is not None
        or document.get("execution_spec_hash") is not None
    ):
        return AnalysisJob.model_validate(document)

    result = document.get("result")
    if not isinstance(result, Mapping) or result.get("status") != "failed":
        return AnalysisJob.model_validate(document)

    normalized_document = dict(document)
    normalized_document["execution_manifest"] = _legacy_execution_manifest(document)
    normalized_result = dict(result)
    failure_cause = normalized_result.get("failure_cause")
    if not isinstance(failure_cause, Mapping):
        normalized_result["failure_cause"] = {
            "category": "unknown_failure",
            "subcause": "unknown",
            "failure_stage": Stage.FINALIZING.value,
            "owner": "unknown",
            "retryable": bool(normalized_result.get("retryable", False)),
            "safe_message": _LEGACY_FAILURE_SAFE_MESSAGE,
            "evidence_refs": ["failure:legacy_missing_diagnostic"],
        }
    elif failure_cause.get("failure_stage") not in _VALID_STAGES:
        normalized_cause = dict(failure_cause)
        normalized_cause["failure_stage"] = Stage.FINALIZING.value
        evidence_refs = normalized_cause.get("evidence_refs")
        normalized_cause["evidence_refs"] = (
            [*evidence_refs, "failure:legacy_stage_normalized"]
            if isinstance(evidence_refs, list) and all(isinstance(ref, str) for ref in evidence_refs)
            else ["failure:legacy_stage_normalized"]
        )
        normalized_result["failure_cause"] = normalized_cause

    normalized_document["result"] = normalized_result
    return AnalysisJob.model_validate(normalized_document)


class PostgresAnalysisJobRepository:
    """Small JSONB-backed implementation of the existing job repository contract."""

    def __init__(self, dsn: str, *, connector: Callable[..., Any] = psycopg.connect) -> None:
        self._dsn = dsn
        self._connector = connector

    def immutable_result_evidence(self, job_id: str) -> ImmutableResultEvidence | None:
        with self._connect() as connection:
            return read_immutable_result_evidence(connection, job_id)

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
        execution_spec: ExecutionSpecV1OrV2 | None = None,
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
            execution_spec=execution_spec,
            client_idempotency_key=client_idempotency_key,
        )
        self._save(job)
        return job

    def register_parse_token(
        self,
        *,
        nonce_hash: str,
        user_id: str,
        spec_version: str,
        spec_hash: str,
        expires_at: datetime,
    ) -> None:
        """Persist only an opaque nonce digest and the canonical spec identity."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app.ai_parse_token (
                    nonce_hash, user_id, spec_version, spec_hash, expires_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (nonce_hash) DO NOTHING
                """,
                (nonce_hash, user_id, spec_version, spec_hash, expires_at),
            )

    def admit_parse_bound_job(
        self,
        request_text: str,
        *,
        nonce_hash: str,
        user_id: str,
        spec_version: str,
        spec_hash: str,
        execution_spec: ExecutionSpecV1OrV2 | None = None,
        client_idempotency_key: str,
    ) -> ParseBoundJobAdmission:
        """Atomically consume one parse nonce, persist the job, and enqueue its outbox row."""

        job = InMemoryAnalysisJobStore().create_job(
            request_text,
            user_id=user_id,
            execution_spec_version=spec_version,
            execution_spec_hash=spec_hash,
            execution_spec=execution_spec,
            client_idempotency_key=client_idempotency_key,
        )
        with self._connect() as connection, connection.transaction():
            if isinstance(execution_spec, ExplorationExecutionSpecV2):
                validate_exploration_spec_against_policy(
                    execution_spec,
                    load_active_exploration_policy(connection, for_update=True),
                )
            existing = connection.execute(
                """
                SELECT spec_hash, job_id
                FROM app.ai_analysis_job_idempotency
                WHERE user_id = %s AND client_idempotency_key = %s
                FOR UPDATE
                """,
                (user_id, client_idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["spec_hash"] != spec_hash:
                    raise ParseBoundAdmissionError("idempotency_key_reused")
                stored = connection.execute(
                    "SELECT job_jsonb FROM app.ai_analysis_job WHERE job_id = %s",
                    (existing["job_id"],),
                ).fetchone()
                if stored is None:
                    raise ParseBoundAdmissionError("parse_token_unavailable")
                return ParseBoundJobAdmission(
                    job=_decode_persisted_job_document(stored["job_jsonb"]),
                    created=False,
                )

            consumed = connection.execute(
                """
                UPDATE app.ai_parse_token
                SET consumed_at = now()
                WHERE nonce_hash = %s
                  AND user_id = %s
                  AND spec_version = %s
                  AND spec_hash = %s
                  AND consumed_at IS NULL
                  AND expires_at > now()
                RETURNING nonce_hash
                """,
                (nonce_hash, user_id, spec_version, spec_hash),
            ).fetchone()
            if consumed is None:
                # A concurrent identical request can observe no idempotency row before
                # it waits on the nonce-row update. Re-read after that wait so its
                # retry returns the winner's job instead of looking like a replay.
                winner = connection.execute(
                    """
                    SELECT spec_hash, job_id
                    FROM app.ai_analysis_job_idempotency
                    WHERE user_id = %s AND client_idempotency_key = %s
                    """,
                    (user_id, client_idempotency_key),
                ).fetchone()
                if winner is not None:
                    if winner["spec_hash"] != spec_hash:
                        raise ParseBoundAdmissionError("idempotency_key_reused")
                    stored = connection.execute(
                        "SELECT job_jsonb FROM app.ai_analysis_job WHERE job_id = %s",
                        (winner["job_id"],),
                    ).fetchone()
                    if stored is not None:
                        return ParseBoundJobAdmission(
                            job=_decode_persisted_job_document(stored["job_jsonb"]),
                            created=False,
                        )
                raise ParseBoundAdmissionError("parse_token_unavailable")

            outbox_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO app.ai_analysis_job (
                    job_id, user_id, job_jsonb, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    job.job_id,
                    job.user_id,
                    Jsonb(_job_document(job)),
                    job.created_at,
                    job.updated_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO app.ai_analysis_job_idempotency (
                    user_id, client_idempotency_key, spec_hash, job_id
                ) VALUES (%s, %s, %s, %s)
                """,
                (user_id, client_idempotency_key, spec_hash, job.job_id),
            )
            connection.execute(
                """
                INSERT INTO app.ai_analysis_job_outbox (
                    outbox_id, job_id, event_type, payload_jsonb
                ) VALUES (%s, %s, %s, %s)
                """,
                (
                    outbox_id,
                    job.job_id,
                    "analysis_job.created.v1",
                    Jsonb(
                        {
                            "job_id": job.job_id,
                            "spec_hash": spec_hash,
                            "spec_version": spec_version,
                        }
                    ),
                ),
            )
            if isinstance(execution_spec, ExplorationExecutionSpecV2):
                connection.execute(
                    """
                    INSERT INTO app.ai_research_appendix_event (
                        event_id, job_id, status, payload_jsonb
                    ) VALUES (%s, %s, 'pending', %s)
                    """,
                    (
                        str(uuid4()),
                        job.job_id,
                        Jsonb({"policy_version": execution_spec.policy_version}),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO app.ai_research_appendix_outbox (outbox_id, job_id)
                    VALUES (%s, %s)
                    """,
                    (str(uuid4()), job.job_id),
                )
        return ParseBoundJobAdmission(job=job, created=True, outbox_id=outbox_id)

    def find_parse_bound_job(
        self,
        *,
        user_id: str,
        spec_hash: str,
        client_idempotency_key: str,
    ) -> AnalysisJob | None:
        """Read an idempotent admission before a retry spends another quota unit."""

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT spec_hash, job_id
                FROM app.ai_analysis_job_idempotency
                WHERE user_id = %s AND client_idempotency_key = %s
                """,
                (user_id, client_idempotency_key),
            ).fetchone()
            if existing is None:
                return None
            if existing["spec_hash"] != spec_hash:
                raise ParseBoundAdmissionError("idempotency_key_reused")
            stored = connection.execute(
                "SELECT job_jsonb FROM app.ai_analysis_job WHERE job_id = %s",
                (existing["job_id"],),
            ).fetchone()
            if stored is None:
                raise ParseBoundAdmissionError("parse_token_unavailable")
            return _decode_persisted_job_document(stored["job_jsonb"])

    def claim_analysis_job_outbox(self, *, limit: int = 1) -> list[AnalysisJobOutboxMessage]:
        """Lease queued jobs for the single process that is allowed to execute them."""

        if limit < 1:
            return []
        with self._connect() as connection, connection.transaction():
            rows = connection.execute(
                """
                WITH candidates AS (
                    SELECT outbox.outbox_id
                    FROM app.ai_analysis_job_outbox AS outbox
                    JOIN app.ai_analysis_job AS job ON job.job_id = outbox.job_id
                    WHERE job.job_jsonb ->> 'status' = 'queued'
                      AND (
                        outbox.status = 'pending'
                        OR (
                            outbox.status = 'claimed'
                            AND outbox.claimed_at < now() - interval '5 minutes'
                        )
                      )
                    ORDER BY outbox.created_at
                    FOR UPDATE OF outbox SKIP LOCKED
                    LIMIT %s
                )
                UPDATE app.ai_analysis_job_outbox AS outbox
                SET status = 'claimed', claimed_at = now()
                FROM candidates
                WHERE outbox.outbox_id = candidates.outbox_id
                RETURNING outbox.outbox_id::text AS outbox_id, outbox.job_id
                """,
                (limit,),
            ).fetchall()
        return [
            AnalysisJobOutboxMessage(outbox_id=row["outbox_id"], job_id=row["job_id"])
            for row in rows
        ]

    def mark_analysis_job_outbox_delivered(self, outbox_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE app.ai_analysis_job_outbox
                SET status = 'delivered', delivered_at = now()
                WHERE outbox_id = %s::uuid AND status = 'claimed'
                """,
                (outbox_id,),
            )

    def release_analysis_job_outbox(self, outbox_id: str) -> None:
        """Make an unstarted claim retryable after an infrastructure-side failure."""

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE app.ai_analysis_job_outbox
                SET status = 'pending', claimed_at = NULL
                WHERE outbox_id = %s::uuid AND status = 'claimed'
                """,
                (outbox_id,),
            )

    def has_recoverable_analysis_job_outbox(self, job_id: str) -> bool:
        """Keep a queued outbox job eligible for startup dispatch after a restart."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM app.ai_analysis_job_outbox
                    WHERE job_id = %s
                      AND status IN ('pending', 'claimed')
                ) AS recoverable
                """,
                (job_id,),
            ).fetchone()
        return bool(row and row["recoverable"])

    def claim_research_appendix_outbox(
        self, *, limit: int = 1
    ) -> list[ResearchAppendixOutboxMessage]:
        if limit < 1:
            return []
        with self._connect() as connection, connection.transaction():
            rows = connection.execute(
                """
                WITH candidates AS (
                    SELECT outbox.outbox_id
                    FROM app.ai_research_appendix_outbox AS outbox
                    JOIN app.ai_analysis_job AS job ON job.job_id = outbox.job_id
                    WHERE job.job_jsonb ->> 'status' IN ('completed', 'failed')
                      AND (
                        outbox.status = 'pending'
                        OR (
                            outbox.status = 'claimed'
                            AND outbox.claimed_at < now() - interval '5 minutes'
                        )
                      )
                    ORDER BY outbox.created_at
                    FOR UPDATE OF outbox SKIP LOCKED
                    LIMIT %s
                )
                UPDATE app.ai_research_appendix_outbox AS outbox
                SET status = 'claimed', claimed_at = now()
                FROM candidates
                WHERE outbox.outbox_id = candidates.outbox_id
                RETURNING outbox.outbox_id::text AS outbox_id, outbox.job_id
                """,
                (limit,),
            ).fetchall()
        return [
            ResearchAppendixOutboxMessage(row["outbox_id"], row["job_id"])
            for row in rows
        ]

    def complete_research_appendix(
        self, outbox_id: str, job_id: str, payload: Mapping[str, Any]
    ) -> None:
        self._settle_research_appendix(outbox_id, job_id, "ready", payload)

    def mark_research_appendix_unavailable(
        self, outbox_id: str, job_id: str, reason: str
    ) -> None:
        self._settle_research_appendix(
            outbox_id, job_id, "unavailable", {"reason": reason}
        )

    def _settle_research_appendix(
        self,
        outbox_id: str,
        job_id: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> None:
        with self._connect() as connection, connection.transaction():
            connection.execute(
                """
                INSERT INTO app.ai_research_appendix_event (
                    event_id, job_id, status, payload_jsonb
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (job_id, status) DO NOTHING
                """,
                (str(uuid4()), job_id, status, Jsonb(dict(payload))),
            )
            connection.execute(
                """
                UPDATE app.ai_research_appendix_outbox
                SET status = 'delivered', delivered_at = now()
                WHERE outbox_id = %s::uuid AND job_id = %s AND status = 'claimed'
                """,
                (outbox_id, job_id),
            )

    def get_research_appendix(self, job_id: str) -> Mapping[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status, payload_jsonb AS payload, created_at
                FROM app.ai_research_appendix_event
                WHERE job_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_job(self, job_id: str) -> AnalysisJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT job_jsonb FROM app.ai_analysis_job WHERE job_id = %s",
                (job_id,),
            ).fetchone()
        return _decode_persisted_job_document(row["job_jsonb"]) if row else None

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
                decoded.append(_decode_persisted_job_document(document))
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
                decoded.append(_decode_persisted_job_document(document))
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
