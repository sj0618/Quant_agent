from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from ai_graph.schemas import APIEnvelope, ExecutionSpecV1OrV2, Stage

from .jobs import (
    PERSISTENT_JOB_STORE_MODE,
    AnalysisJob,
    AnalysisJobOutboxMessage,
    AnalysisJobOutboxStore,
    AnalysisJobStatus,
    JobStoreConfigurationError,
    ParseBoundJobAdmission,
    ParseBoundJobAdmissionStore,
    ResearchAppendixOutboxMessage,
    ResearchAppendixStore,
)


@runtime_checkable
class AnalysisJobRepository(Protocol):
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
        ...

    def get_job(self, job_id: str) -> AnalysisJob | None:
        ...

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
        ...

    def complete_job(
        self,
        job_id: str,
        result_envelope: APIEnvelope,
        *,
        fallback_reasons: Sequence[str] | None = None,
    ) -> AnalysisJob:
        ...

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        *,
        fallback_reasons: Sequence[str] | None = None,
        result_envelope: APIEnvelope | None = None,
    ) -> AnalysisJob:
        ...

    def list_jobs(self, *, limit: int = 100, user_id: str | None = None) -> list[AnalysisJob]:
        ...


@runtime_checkable
class RestartReconciliationRepository(Protocol):
    """Persistent repositories need a strict active-row startup read."""

    def list_jobs_for_reconciliation(self, *, limit: int = 500) -> Any:
        ...

    def force_fail_undecodable_job(self, job_id: str, *, error_message: str, reason: str) -> bool:
        ...


@runtime_checkable
class ImmutableResultEvidenceRepository(Protocol):
    def immutable_result_evidence(self, job_id: str) -> Any | None:
        """Return the safe operator evidence projection for a completed job."""

        ...


class PersistentAnalysisJobStore:
    """Adapter over the DB-team-owned analysis job repository contract."""

    store_mode: str = PERSISTENT_JOB_STORE_MODE

    def __init__(self, repository: object) -> None:
        # DB schema and migration are owned by DB team.
        if not isinstance(repository, AnalysisJobRepository):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires an AnalysisJobRepository-compatible object."
            )
        self._repository: AnalysisJobRepository = repository

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
        kwargs: dict[str, object] = {
            "user_id": user_id,
            "strategy_id": strategy_id,
            "run_id": run_id,
            "fallback_reasons": fallback_reasons,
        }
        if any(
            value is not None
            for value in (
                execution_spec_version,
                execution_spec_hash,
                execution_spec,
                client_idempotency_key,
            )
        ):
            kwargs.update(
                {
                    "execution_spec_version": execution_spec_version,
                    "execution_spec_hash": execution_spec_hash,
                    "execution_spec": execution_spec,
                    "client_idempotency_key": client_idempotency_key,
                }
            )
        return self._repository.create_job(
            request_text,
            **kwargs,
        )

    def get_job(self, job_id: str) -> AnalysisJob | None:
        return self._repository.get_job(job_id)

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
        return self._repository.update_job_status(
            job_id,
            status,
            polling_stage,
            fallback_reasons=fallback_reasons,
            error_message=error_message,
            message=message,
        )

    def complete_job(
        self,
        job_id: str,
        result_envelope: APIEnvelope,
        *,
        fallback_reasons: Sequence[str] | None = None,
    ) -> AnalysisJob:
        return self._repository.complete_job(
            job_id,
            result_envelope,
            fallback_reasons=fallback_reasons,
        )

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        *,
        fallback_reasons: Sequence[str] | None = None,
        result_envelope: APIEnvelope | None = None,
    ) -> AnalysisJob:
        return self._repository.fail_job(
            job_id,
            error_message,
            fallback_reasons=fallback_reasons,
            result_envelope=result_envelope,
        )

    def list_jobs(self, *, limit: int = 100, user_id: str | None = None) -> list[AnalysisJob]:
        return self._repository.list_jobs(limit=limit, user_id=user_id)

    def immutable_result_evidence(self, job_id: str) -> Any | None:
        if not isinstance(self._repository, ImmutableResultEvidenceRepository):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires immutable-result evidence support."
            )
        return self._repository.immutable_result_evidence(job_id)

    def register_parse_token(
        self,
        *,
        nonce_hash: str,
        user_id: str,
        spec_version: str,
        spec_hash: str,
        expires_at: datetime,
    ) -> None:
        if not isinstance(self._repository, ParseBoundJobAdmissionStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires parse-bound admission support."
            )
        self._repository.register_parse_token(
            nonce_hash=nonce_hash,
            user_id=user_id,
            spec_version=spec_version,
            spec_hash=spec_hash,
            expires_at=expires_at,
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
        if not isinstance(self._repository, ParseBoundJobAdmissionStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires parse-bound admission support."
            )
        return self._repository.admit_parse_bound_job(
            request_text,
            nonce_hash=nonce_hash,
            user_id=user_id,
            spec_version=spec_version,
            spec_hash=spec_hash,
            execution_spec=execution_spec,
            client_idempotency_key=client_idempotency_key,
        )

    def find_parse_bound_job(
        self,
        *,
        user_id: str,
        spec_hash: str,
        client_idempotency_key: str,
    ) -> AnalysisJob | None:
        if not isinstance(self._repository, ParseBoundJobAdmissionStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires parse-bound admission support."
            )
        return self._repository.find_parse_bound_job(
            user_id=user_id,
            spec_hash=spec_hash,
            client_idempotency_key=client_idempotency_key,
        )

    def claim_analysis_job_outbox(self, *, limit: int = 1) -> list[AnalysisJobOutboxMessage]:
        if not isinstance(self._repository, AnalysisJobOutboxStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires analysis-job outbox support."
            )
        return self._repository.claim_analysis_job_outbox(limit=limit)

    def mark_analysis_job_outbox_delivered(self, outbox_id: str) -> None:
        if not isinstance(self._repository, AnalysisJobOutboxStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires analysis-job outbox support."
            )
        self._repository.mark_analysis_job_outbox_delivered(outbox_id)

    def release_analysis_job_outbox(self, outbox_id: str) -> None:
        if not isinstance(self._repository, AnalysisJobOutboxStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires analysis-job outbox support."
            )
        self._repository.release_analysis_job_outbox(outbox_id)

    def has_recoverable_analysis_job_outbox(self, job_id: str) -> bool:
        if not isinstance(self._repository, AnalysisJobOutboxStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires analysis-job outbox support."
            )
        return self._repository.has_recoverable_analysis_job_outbox(job_id)

    def claim_research_appendix_outbox(
        self, *, limit: int = 1
    ) -> list[ResearchAppendixOutboxMessage]:
        if not isinstance(self._repository, ResearchAppendixStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires research-appendix support."
            )
        return self._repository.claim_research_appendix_outbox(limit=limit)

    def complete_research_appendix(
        self, outbox_id: str, job_id: str, payload: Mapping[str, Any]
    ) -> None:
        if not isinstance(self._repository, ResearchAppendixStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires research-appendix support."
            )
        self._repository.complete_research_appendix(outbox_id, job_id, payload)

    def mark_research_appendix_unavailable(
        self, outbox_id: str, job_id: str, reason: str
    ) -> None:
        if not isinstance(self._repository, ResearchAppendixStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires research-appendix support."
            )
        self._repository.mark_research_appendix_unavailable(outbox_id, job_id, reason)

    def get_research_appendix(self, job_id: str) -> Mapping[str, Any] | None:
        if not isinstance(self._repository, ResearchAppendixStore):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires research-appendix support."
            )
        return self._repository.get_research_appendix(job_id)

    def list_jobs_for_reconciliation(self, *, limit: int = 500) -> Any:
        """Do not let compatibility history reads weaken restart recovery."""

        if not isinstance(self._repository, RestartReconciliationRepository):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires strict restart reconciliation support."
            )
        return self._repository.list_jobs_for_reconciliation(limit=limit)

    def force_fail_undecodable_job(self, job_id: str, *, error_message: str, reason: str) -> bool:
        """Settle an active row this build cannot load, so startup is not held hostage."""

        if not isinstance(self._repository, RestartReconciliationRepository):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires strict restart reconciliation support."
            )
        return self._repository.force_fail_undecodable_job(
            job_id, error_message=error_message, reason=reason
        )
