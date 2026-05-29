from __future__ import annotations

# pyright: reportUnannotatedClassAttribute=false

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from os import environ
from typing import ClassVar, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.schemas import APIEnvelope, EnvelopeStatus, Stage, StageStatus, UserPayload


AI_JOB_STORE_ENV = "AI_JOB_STORE"
BE_JOB_STORE_MODE_ENV = "BE_JOB_STORE_MODE"
AI_DATABASE_DSN_ENV = "AI_DATABASE_DSN"
MEMORY_JOB_STORE_MODE = "memory"
PERSISTENT_JOB_STORE_MODE = "persistent"


class AnalysisJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageProgress(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    stage: Stage
    status: StageStatus
    updated_at: datetime
    message: str | None = None


class AnalysisJob(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    # Storage-only fields are excluded to preserve the frozen public job response.
    user_id: str | None = Field(default=None, exclude=True)
    strategy_id: str | None = Field(default=None, exclude=True)
    run_id: str | None = Field(default=None, exclude=True)
    status: AnalysisJobStatus = Field(exclude=True)
    polling_stage: Stage = Field(exclude=True)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = Field(default=None, exclude=True)
    stages: list[StageProgress]
    result: APIEnvelope | None = None
    debug_ref: str | None = Field(default=None, exclude=True)
    fallback_reasons: list[str] = Field(default_factory=list, exclude=True)
    error_message: str | None = Field(default=None, exclude=True)


class AnalysisJobStore(Protocol):
    store_mode: str

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


AnalysisRunner = Callable[[str, str], APIEnvelope]
PersistentStoreFactory = Callable[[object], AnalysisJobStore]


class JobStoreConfigurationError(RuntimeError):
    """Raised when a requested job store mode cannot be configured safely."""


@dataclass(frozen=True)
class JobStoreRuntime:
    store: AnalysisJobStore
    requested_mode: str
    active_mode: str
    fallback: bool
    fallback_reason: str | None
    dsn_configured: bool
    dsn_env: str = AI_DATABASE_DSN_ENV
    mode_env: str = AI_JOB_STORE_ENV


@dataclass
class InMemoryAnalysisJobStore:
    jobs: dict[str, AnalysisJob] = field(default_factory=dict)
    store_mode: str = MEMORY_JOB_STORE_MODE

    def create_job(
        self,
        request_text: str,
        *,
        user_id: str | None = None,
        strategy_id: str | None = None,
        run_id: str | None = None,
        fallback_reasons: Sequence[str] | None = None,
    ) -> AnalysisJob:
        now = datetime.now(UTC)
        trace_id = sha256(f"{request_text}:{now.isoformat()}".encode("utf-8")).hexdigest()[:16]
        job = AnalysisJob(
            job_id=f"job_{uuid4().hex[:12]}",
            trace_id=trace_id,
            query=request_text,
            user_id=user_id,
            strategy_id=strategy_id,
            run_id=run_id,
            status=AnalysisJobStatus.QUEUED,
            polling_stage=Stage.INTERPRETING,
            created_at=now,
            updated_at=now,
            stages=_stage_progresses(Stage.INTERPRETING, AnalysisJobStatus.QUEUED, now),
            fallback_reasons=list(fallback_reasons or ()),
        )
        self.jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str) -> AnalysisJob | None:
        return self.jobs.get(job_id)

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
        job = self._require_job(job_id)
        normalized_status = AnalysisJobStatus(status)
        normalized_stage = Stage(polling_stage)
        now = datetime.now(UTC)
        update: dict[str, object] = {
            "status": normalized_status,
            "polling_stage": normalized_stage,
            "updated_at": now,
            "stages": _stage_progresses(
                normalized_stage,
                normalized_status,
                now,
                message=message,
            ),
        }
        if fallback_reasons is not None:
            update["fallback_reasons"] = list(fallback_reasons)
        if error_message is not None:
            update["error_message"] = error_message
        job = job.model_copy(update=update)
        self.jobs[job_id] = job
        return job

    def complete_job(
        self,
        job_id: str,
        result_envelope: APIEnvelope,
        *,
        fallback_reasons: Sequence[str] | None = None,
    ) -> AnalysisJob:
        job = self._require_job(job_id)
        completed_at = datetime.now(UTC)
        reasons = list(fallback_reasons) if fallback_reasons is not None else job.fallback_reasons
        strategy_id = job.strategy_id
        if strategy_id is None and result_envelope.strategy_spec is not None:
            strategy_id = result_envelope.strategy_spec.strategy_id
        job = job.model_copy(
            update={
                "strategy_id": strategy_id,
                "status": AnalysisJobStatus.COMPLETED,
                "polling_stage": Stage.FINALIZING,
                "updated_at": completed_at,
                "completed_at": completed_at,
                "stages": _stage_progresses(
                    Stage.FINALIZING,
                    AnalysisJobStatus.COMPLETED,
                    completed_at,
                ),
                "result": result_envelope,
                "debug_ref": result_envelope.debug_ref,
                "fallback_reasons": reasons,
                "error_message": None,
            }
        )
        self.jobs[job_id] = job
        return job

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        *,
        fallback_reasons: Sequence[str] | None = None,
        result_envelope: APIEnvelope | None = None,
    ) -> AnalysisJob:
        job = self._require_job(job_id)
        failed_at = datetime.now(UTC)
        reasons = list(fallback_reasons) if fallback_reasons is not None else job.fallback_reasons
        result = result_envelope or _failure_envelope(job, error_message)
        result = result.model_copy(update={"status": EnvelopeStatus.FAILED})
        job = job.model_copy(
            update={
                "status": AnalysisJobStatus.FAILED,
                "polling_stage": Stage.FINALIZING,
                "updated_at": failed_at,
                "completed_at": failed_at,
                "stages": _stage_progresses(
                    Stage.FINALIZING,
                    AnalysisJobStatus.FAILED,
                    failed_at,
                    message=error_message,
                ),
                "result": result,
                "debug_ref": result.debug_ref,
                "fallback_reasons": reasons,
                "error_message": error_message,
            }
        )
        self.jobs[job_id] = job
        return job

    def list_jobs(self, *, limit: int = 100) -> list[AnalysisJob]:
        return list(self.jobs.values())[-limit:]

    def create(self, query: str) -> AnalysisJob:
        return self.create_job(query)

    def get(self, job_id: str) -> AnalysisJob | None:
        return self.get_job(job_id)

    def run_sync(self, job_id: str, runner: AnalysisRunner) -> AnalysisJob:
        return run_job_sync(self, job_id, runner)

    def _require_job(self, job_id: str) -> AnalysisJob:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(f"analysis job not found: {job_id}")
        return job


def run_job_sync(store: AnalysisJobStore, job_id: str, runner: AnalysisRunner) -> AnalysisJob:
    job = store.get_job(job_id)
    if job is None:
        raise KeyError(f"analysis job not found: {job_id}")
    for stage in Stage:
        job = store.update_job_status(job_id, AnalysisJobStatus.RUNNING, stage)
    try:
        result = runner(job.query, job.trace_id)
    except Exception as exc:
        return store.fail_job(job_id, str(exc))
    return store.complete_job(job_id, result)


def create_analysis_job_store_from_env(
    env: Mapping[str, str] | None = None,
    *,
    repository: object | None = None,
    persistent_store_factory: PersistentStoreFactory | None = None,
) -> JobStoreRuntime:
    source = environ if env is None else env
    requested_mode = _requested_job_store_mode(source)
    dsn_configured = bool(source.get(AI_DATABASE_DSN_ENV))
    if requested_mode == MEMORY_JOB_STORE_MODE:
        store = InMemoryAnalysisJobStore()
        return JobStoreRuntime(
            store=store,
            requested_mode=requested_mode,
            active_mode=store.store_mode,
            fallback=False,
            fallback_reason=None,
            dsn_configured=dsn_configured,
        )
    if requested_mode == PERSISTENT_JOB_STORE_MODE:
        if repository is None:
            reason = (
                "AI_JOB_STORE=persistent requires the DB-team repository adapter; "
                "falling back to in-memory job store."
            )
            if not dsn_configured:
                reason = (
                    f"{AI_DATABASE_DSN_ENV} is not set for AI_JOB_STORE=persistent; "
                    "falling back to in-memory job store."
                )
            store = InMemoryAnalysisJobStore()
            return JobStoreRuntime(
                store=store,
                requested_mode=requested_mode,
                active_mode=store.store_mode,
                fallback=True,
                fallback_reason=reason,
                dsn_configured=dsn_configured,
            )
        if persistent_store_factory is None:
            raise JobStoreConfigurationError(
                "persistent_store_factory is required when a persistent repository is provided."
            )
        store = persistent_store_factory(repository)
        return JobStoreRuntime(
            store=store,
            requested_mode=requested_mode,
            active_mode=store.store_mode,
            fallback=False,
            fallback_reason=None,
            dsn_configured=dsn_configured,
        )
    message = (
        f"Unsupported {AI_JOB_STORE_ENV} value: {requested_mode!r}. Expected "
        f"{MEMORY_JOB_STORE_MODE!r} or {PERSISTENT_JOB_STORE_MODE!r}."
    )
    raise JobStoreConfigurationError(message)


def _requested_job_store_mode(env: Mapping[str, str]) -> str:
    raw_mode = env.get(AI_JOB_STORE_ENV) or env.get(BE_JOB_STORE_MODE_ENV) or MEMORY_JOB_STORE_MODE
    return raw_mode.strip().lower() or MEMORY_JOB_STORE_MODE


def _stage_progresses(
    polling_stage: Stage,
    status: AnalysisJobStatus,
    updated_at: datetime,
    *,
    message: str | None = None,
) -> list[StageProgress]:
    stage_order = list(Stage)
    current_index = stage_order.index(polling_stage)
    progresses: list[StageProgress] = []
    for index, stage in enumerate(stage_order):
        stage_status = _stage_status_for(index, current_index, status)
        progresses.append(
            StageProgress(
                stage=stage,
                status=stage_status,
                updated_at=updated_at,
                message=message if stage == polling_stage else None,
            )
        )
    return progresses


def _stage_status_for(
    index: int,
    current_index: int,
    status: AnalysisJobStatus,
) -> StageStatus:
    if status == AnalysisJobStatus.QUEUED:
        return StageStatus.QUEUED
    if status == AnalysisJobStatus.RUNNING:
        if index < current_index:
            return StageStatus.SUCCEEDED
        if index == current_index:
            return StageStatus.RUNNING
        return StageStatus.QUEUED
    if status == AnalysisJobStatus.COMPLETED:
        return StageStatus.SUCCEEDED
    if index < current_index:
        return StageStatus.SUCCEEDED
    if index == current_index:
        return StageStatus.FAILED
    return StageStatus.QUEUED


def _failure_envelope(
    job: AnalysisJob,
    error_message: str,
) -> APIEnvelope:
    return APIEnvelope(
        status=EnvelopeStatus.FAILED,
        trace_id=job.trace_id,
        user_payload=UserPayload(
            headline="Analysis job failed",
            message=error_message,
            next_actions=["Check the request and retry after the service issue is resolved."],
        ),
        strategy_spec=None,
        debug_ref=f"job-error:{job.job_id}",
        retryable=True,
    )
