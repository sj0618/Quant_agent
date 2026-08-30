from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from ai_graph.schemas import APIEnvelope, Stage

from .jobs import (
    PERSISTENT_JOB_STORE_MODE,
    AnalysisJob,
    AnalysisJobStatus,
    JobStoreConfigurationError,
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

    def list_jobs(self, *, limit: int = 100) -> list[AnalysisJob]:
        ...


@runtime_checkable
class RestartReconciliationRepository(Protocol):
    """Persistent repositories need a strict active-row startup read."""

    def list_jobs_for_reconciliation(self, *, limit: int = 500) -> Any:
        ...

    def force_fail_undecodable_job(self, job_id: str, *, error_message: str, reason: str) -> bool:
        ...


@runtime_checkable
class LeasedJobRepository(Protocol):
    """A repository that can arbitrate between two workers claiming the same job."""

    def claim_job(self, job_id: str, *, owner: str, lease_seconds: int) -> int | None:
        ...

    def renew_lease(self, job_id: str, *, owner: str, lease_seconds: int) -> bool:
        ...

    def release_lease(self, job_id: str, *, owner: str) -> bool:
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
    ) -> AnalysisJob:
        return self._repository.create_job(
            request_text,
            user_id=user_id,
            strategy_id=strategy_id,
            run_id=run_id,
            fallback_reasons=fallback_reasons,
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

    def list_jobs(self, *, limit: int = 100) -> list[AnalysisJob]:
        return self._repository.list_jobs(limit=limit)

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

    def claim_job(self, job_id: str, *, owner: str, lease_seconds: int) -> int | None:
        """Take the lease, or return None because a live holder already has it.

        Refuses rather than silently succeeding when the repository has no lease
        support: a claim that always succeeds is worse than no claim at all, because
        callers would treat it as arbitration that never happened.
        """

        return self._leased().claim_job(job_id, owner=owner, lease_seconds=lease_seconds)

    def renew_lease(self, job_id: str, *, owner: str, lease_seconds: int) -> bool:
        return self._leased().renew_lease(job_id, owner=owner, lease_seconds=lease_seconds)

    def release_lease(self, job_id: str, *, owner: str) -> bool:
        return self._leased().release_lease(job_id, owner=owner)

    def _leased(self) -> LeasedJobRepository:
        if not isinstance(self._repository, LeasedJobRepository):
            raise JobStoreConfigurationError(
                "PersistentAnalysisJobStore requires lease support for job claims."
            )
        return self._repository
