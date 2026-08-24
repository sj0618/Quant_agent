from __future__ import annotations

# pyright: reportUnannotatedClassAttribute=false
import json
import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from os import environ, getpid
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ai_graph.analysis_capacity import (
    ANALYSIS_CAPACITY,
    CAPACITY_TIMEOUT_MESSAGE,
    AnalysisCapacityGate,
    AnalysisCapacityTimeout,
)
from ai_graph.data_sources.db import PipelineDataUnavailableError, resolve_database_dsn_from_env
from ai_graph.job_events import JobEventBuffer
from ai_graph.progress import (
    AnalysisCancelled,
    AnalysisDeadlineExceeded,
    activity_reporter,
    analysis_deadline,
    cancellation_check,
    stage_reporter,
)
from ai_graph.research_eligibility import PerformanceAvailable
from ai_graph.schemas import (
    APIEnvelope,
    EnvelopeStatus,
    FailureDiagnostic,
    Stage,
    StageStatus,
    UserPayload,
)

_logger = logging.getLogger(__name__)

# One value per process start. A job records the incarnation that owned it, so a job
# still marked RUNNING under a different incarnation belongs to a process that is gone.
# This is the ordinary case rather than an exotic one: every deploy stops uvicorn and
# starts it again, so every deploy strands whatever was in flight.
PROCESS_INCARNATION = f"{getpid()}:{uuid4().hex[:12]}"

AI_JOB_DEADLINE_SECONDS_ENV = "AI_JOB_DEADLINE_SECONDS"
# Generous on purpose. The backtest node alone is budgeted at 540s and a healthy run has
# been observed past 600s, so this is a ceiling for runs that are not coming back rather
# than a target: its job is to release the analysis slot a stuck run is holding.
DEFAULT_JOB_DEADLINE_SECONDS = 1_800.0
JOB_DEADLINE_MESSAGE = (
    "분석이 허용된 시간을 넘겨 중단되었습니다. 조건을 좁혀 다시 시도해 주세요."
)

INTERRUPTED_BY_RESTART_REASON = "interrupted_by_restart"
INTERRUPTED_BY_RESTART_MESSAGE = (
    "서버가 재시작되어 분석이 중단되었습니다. 같은 요청으로 다시 실행해 주세요."
)


class InterruptedJobReconciliationError(RuntimeError):
    """The process cannot safely serve jobs until restart reconciliation completes."""

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


MANIFEST_SCHEMA_VERSION = "1"
MANIFEST_CONTRACT_HASH = "3bb9a4727895b08f6d7a396e9179c2f7263bbea5d7a1d5130c7a079b9e808e0f"


class ExecutionRunIdentity(BaseModel):
    """Identifiers needed to join one execution ledger to its analysis request."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    strategy_id: str | None = None
    run_id: str | None = None


class ExecutionSession(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    requested_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ExecutionCapabilities(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    terminal_event_documents: bool = False
    corporate_action_events: bool = False


class ExecutionEvent(BaseModel):
    """One ledger event; cost and quantity fields permit deterministic reconstruction."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    occurred_at: datetime
    requested_qty: float = Field(ge=0)
    filled_qty: float = Field(ge=0)
    reason: str = Field(min_length=1)
    component_costs: dict[str, float] = Field(default_factory=dict)
    document: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ExecutionEvents(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    signals: list[ExecutionEvent] = Field(default_factory=list)
    orders: list[ExecutionEvent] = Field(default_factory=list)
    fills: list[ExecutionEvent] = Field(default_factory=list)
    positions: list[ExecutionEvent] = Field(default_factory=list)
    trades: list[ExecutionEvent] = Field(default_factory=list)
    equity: list[ExecutionEvent] = Field(default_factory=list)


class ExecutionManifest(BaseModel):
    """Versioned, secret-free execution ledger persisted inside canonical job JSONB."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = MANIFEST_SCHEMA_VERSION
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_identity: ExecutionRunIdentity
    policy_hashes: dict[str, str] = Field(min_length=1)
    session: ExecutionSession
    capabilities: ExecutionCapabilities = Field(default_factory=ExecutionCapabilities)
    events: ExecutionEvents = Field(default_factory=ExecutionEvents)
    ledger_event_count: int = Field(default=0, ge=0)
    ledger_event_hash: str = Field(default_factory=lambda: _stable_hash({}), pattern=r"^[0-9a-f]{64}$")


class AnalysisJob(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    # Storage-only fields are excluded to preserve the frozen public job response.
    user_id: str | None = Field(default=None, exclude=True)
    strategy_id: str | None = Field(default=None, exclude=True)
    run_id: str | None = Field(default=None, exclude=True)
    report_id: str | None = Field(default=None, exclude=True)
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
    # Which process incarnation owns this job. Storage-only, like the fields above; the
    # restart reaper reads it to tell "still running" from "nothing is running this".
    owner_incarnation: str | None = Field(default=None, exclude=True)
    # Canonical writer persists this versioned ledger in job_jsonb; it deliberately has
    # no DSN, credential, or arbitrary provider payload fields.
    execution_manifest: ExecutionManifest = Field(exclude=True)


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


@runtime_checkable
class RestartReconciliationStore(Protocol):
    """Optional strict active-job read used only during process startup."""

    def list_jobs_for_reconciliation(self, *, limit: int = 500) -> Any:
        ...

    def force_fail_undecodable_job(self, job_id: str, *, error_message: str, reason: str) -> bool:
        ...


AnalysisRunner = Callable[[str, str], APIEnvelope]
PersistentStoreFactory = Callable[[object], AnalysisJobStore]


class AnalysisHistoryReadOnlyError(RuntimeError):
    """Raised when a retired surface tried to add a row to the analysis history."""


class ReadOnlyAnalysisJobStore:
    """Keeps the analysis history readable while no surface may add to it.

    The legacy raw-analysis route and the confirmed-research route are the only two
    callers that create jobs, and both already refuse before they get here. This wrapper
    exists so that the guarantee is structural rather than a property of route review:
    a new consumer added later cannot quietly start writing history again.

    Only creation is refused. Reads pass through, and so does restart reconciliation,
    which moves rows a dead process left RUNNING into a terminal state. Blocking that
    would leave those rows spinning forever and make readiness fail, and it would be a
    different thing from what is being retired: reconciliation finishes existing history,
    it does not open new history. Nothing here deletes a stored result.
    """

    def __init__(self, store: AnalysisJobStore) -> None:
        self._store = store

    def create_job(self, *_args: Any, **_kwargs: Any) -> AnalysisJob:
        raise AnalysisHistoryReadOnlyError(
            "analysis history is read-only: no enabled surface may create an analysis job"
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


class JobStoreConfigurationError(RuntimeError):
    """Raised when a requested job store mode cannot be configured safely."""


class EmptyAnalysisResultError(ValueError):
    """The analysis runner returned no public result envelope."""


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
        job_id = f"job_{uuid4().hex[:12]}"
        trace_id = sha256(f"{request_text}:{now.isoformat()}".encode("utf-8")).hexdigest()[:16]
        job = AnalysisJob(
            job_id=job_id,
            trace_id=trace_id,
            query=request_text,
            user_id=user_id,
            strategy_id=strategy_id,
            run_id=run_id,
            status=AnalysisJobStatus.QUEUED,
            polling_stage=Stage.INTERPRETING,
            owner_incarnation=PROCESS_INCARNATION,
            created_at=now,
            updated_at=now,
            stages=_stage_progresses(Stage.INTERPRETING, AnalysisJobStatus.QUEUED, now),
            fallback_reasons=list(fallback_reasons or ()),
            execution_manifest=ExecutionManifest(
                contract_hash=MANIFEST_CONTRACT_HASH,
                run_identity=ExecutionRunIdentity(
                    job_id=job_id,
                    trace_id=trace_id,
                    strategy_id=strategy_id,
                    run_id=run_id,
                ),
                policy_hashes={"execution_contract": MANIFEST_CONTRACT_HASH},
                session=ExecutionSession(requested_at=now),
            ),
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
            "execution_manifest": _manifest_with_session_update(
                job.execution_manifest, normalized_status, now
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
        report_id = job.report_id
        if report_id is None and result_envelope.user_payload.report is not None:
            report_id = f"report_{job.job_id}"
        job = job.model_copy(
            update={
                "strategy_id": strategy_id,
                "report_id": report_id,
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
                "execution_manifest": _manifest_from_completion(
                    job.execution_manifest,
                    result_envelope,
                    completed_at,
                    strategy_id=strategy_id,
                ),
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
                "execution_manifest": _manifest_with_session_update(
                    job.execution_manifest, AnalysisJobStatus.FAILED, failed_at
                ),
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


class CancellationRegistry:
    """Job ids the user asked to stop.

    An in-flight provider call cannot be recalled, so cancelling does not undo what is
    already spent; it stops the run before it pays for the nodes that remain.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()

    def cancel(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.add(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.discard(job_id)


def run_job_sync(
    store: AnalysisJobStore,
    job_id: str,
    runner: AnalysisRunner,
    *,
    events: JobEventBuffer | None = None,
    cancellations: CancellationRegistry | None = None,
    capacity: AnalysisCapacityGate = ANALYSIS_CAPACITY,
) -> AnalysisJob:
    """Run one analysis, waiting for a capacity slot before it starts.

    The slot is taken before the job is marked RUNNING, so a job queued behind others
    still reads as queued. Saying RUNNING while nothing is running is what makes a busy
    service look hung, and it is also what an operator would have to disprove by hand.
    """

    try:
        with capacity.slot():
            return _run_analysis_job(
                store, job_id, runner, events=events, cancellations=cancellations
            )
    except AnalysisCapacityTimeout:
        _logger.warning(
            "analysis job %s gave up waiting for a capacity slot (limit=%d, waiting=%d)",
            job_id,
            capacity.max_concurrency,
            capacity.waiting,
        )
        return store.fail_job(job_id, CAPACITY_TIMEOUT_MESSAGE)


def _run_analysis_job(
    store: AnalysisJobStore,
    job_id: str,
    runner: AnalysisRunner,
    *,
    events: JobEventBuffer | None = None,
    cancellations: CancellationRegistry | None = None,
) -> AnalysisJob:
    job = store.get_job(job_id)
    if job is None:
        raise KeyError(f"analysis job not found: {job_id}")

    # Previously every stage was marked RUNNING up front, so a polling client saw the
    # job jump straight to the last stage and sit there for the entire run. Advance
    # the stage only as the graph actually reaches it.
    store.update_job_status(job_id, AnalysisJobStatus.RUNNING, Stage.INTERPRETING)

    def report_stage(stage_value: str) -> None:
        store.update_job_status(job_id, AnalysisJobStatus.RUNNING, Stage(stage_value))
        if events is not None:
            events.publish(job_id, {"kind": "stage", "stage": stage_value})

    try:
        with ExitStack() as scope:
            scope.enter_context(stage_reporter(report_stage))
            if events is not None:
                scope.enter_context(
                    activity_reporter(lambda event: events.publish(job_id, event))
                )
            if cancellations is not None:
                scope.enter_context(
                    cancellation_check(lambda: cancellations.is_cancelled(job_id))
                )
            scope.enter_context(analysis_deadline(job_deadline_seconds()))
            result = _require_analysis_envelope(runner(job.query, job.trace_id))
    except AnalysisDeadlineExceeded:
        _logger.warning(
            "analysis job exceeded its total time budget: job_id=%s budget=%ss",
            job_id,
            job_deadline_seconds(),
        )
        return store.fail_job(
            job_id,
            JOB_DEADLINE_MESSAGE,
            result_envelope=_failure_envelope(
                job,
                JOB_DEADLINE_MESSAGE,
                failure_cause=FailureDiagnostic(
                    category="cancelled",
                    subcause="job_deadline_exceeded",
                    failure_stage=Stage.FINALIZING.value,
                    owner="ai_graph",
                    retryable=True,
                    safe_message=JOB_DEADLINE_MESSAGE,
                    evidence_refs=["failure:job_deadline"],
                ),
            ),
        )
    except AnalysisCancelled:
        _logger.info("analysis job cancelled: job_id=%s", job_id)
        message = "사용자가 분석을 중단했습니다."
        return store.fail_job(
            job_id,
            message,
            result_envelope=_failure_envelope(
                job,
                message,
                failure_cause=FailureDiagnostic(
                    category="cancelled",
                    subcause="user_cancelled",
                    failure_stage=Stage.FINALIZING.value,
                    owner="user",
                    retryable=True,
                    safe_message=message,
                    evidence_refs=["failure:cancelled"],
                ),
            ),
        )
    except Exception as exc:
        # The stage the graph had actually reached, not FINALIZING. `job` was read before
        # the run and never advances, so reporting its stage said every failure happened
        # while finalizing - including ones that died in the Data node minutes earlier,
        # which sent anyone reading the envelope to the wrong end of the pipeline.
        failed_job = store.get_job(job_id) or job
        diagnostic = classify_failure(exc, stage=failed_job.polling_stage.value)
        # The public envelope deliberately hides the original error behind debug_ref,
        # so this is the only place it is ever recorded. Without it a failure is
        # untraceable - doubly so now that jobs run as a background task, where the
        # exception never reaches a request handler either.
        _logger.exception(
            "analysis job failed: job_id=%s trace_id=%s debug_ref=job-error:%s category=%s",
            job_id,
            job.trace_id,
            job_id,
            diagnostic.category,
        )
        try:
            envelope = _failure_envelope(job, diagnostic.safe_message, failure_cause=diagnostic)
        except Exception:
            # Building the rich failure envelope must never itself leave the job stuck in
            # RUNNING - that is exactly what makes the UI spin forever. fail_job builds its
            # own minimal envelope when none is passed, so fall back to that.
            _logger.exception("failed to build failure envelope: job_id=%s", job_id)
            envelope = None
        return store.fail_job(job_id, diagnostic.safe_message, result_envelope=envelope)
    finally:
        # Readers must be released whether the analysis succeeded or failed, otherwise
        # an SSE connection hangs until its own timeout.
        if events is not None:
            events.close(job_id)
    return store.complete_job(job_id, result)


def create_analysis_job_store_from_env(
    env: Mapping[str, str] | None = None,
    *,
    repository: object | None = None,
    persistent_store_factory: PersistentStoreFactory | None = None,
) -> JobStoreRuntime:
    source = environ if env is None else env
    requested_mode = _requested_job_store_mode(source)
    dsn_value, dsn_env = resolve_database_dsn_from_env(source)
    dsn_configured = bool(dsn_value)
    if requested_mode == MEMORY_JOB_STORE_MODE:
        store = InMemoryAnalysisJobStore()
        return JobStoreRuntime(
            store=store,
            requested_mode=requested_mode,
            active_mode=store.store_mode,
            fallback=False,
            fallback_reason=None,
            dsn_configured=dsn_configured,
            dsn_env=dsn_env,
        )
    if requested_mode == PERSISTENT_JOB_STORE_MODE:
        if repository is None:
            if not dsn_configured:
                raise JobStoreConfigurationError(
                    "AI_JOB_STORE=persistent requires a configured database DSN in "
                    "AI_DATABASE_DSN/QUANT_DB_DSN/DATABASE_URL and a repository adapter."
                )
            raise JobStoreConfigurationError(
                "AI_JOB_STORE=persistent requires the DB-team repository adapter."
            )
        if persistent_store_factory is None:
            raise JobStoreConfigurationError(
                "persistent_store_factory is required when a persistent repository is provided."
            )
        store = persistent_store_factory(repository)
        if store.store_mode != PERSISTENT_JOB_STORE_MODE:
            raise JobStoreConfigurationError(
                "AI_JOB_STORE=persistent requires a persistent store; memory fallback is forbidden."
            )
        return JobStoreRuntime(
            store=store,
            requested_mode=requested_mode,
            active_mode=store.store_mode,
            fallback=False,
            fallback_reason=None,
            dsn_configured=dsn_configured,
            dsn_env=dsn_env,
        )
    message = (
        f"Unsupported {AI_JOB_STORE_ENV} value: {requested_mode!r}. Expected "
        f"{MEMORY_JOB_STORE_MODE!r} or {PERSISTENT_JOB_STORE_MODE!r}."
    )
    raise JobStoreConfigurationError(message)


def _manifest_with_session_update(
    manifest: ExecutionManifest,
    status: AnalysisJobStatus,
    timestamp: datetime,
    *,
    strategy_id: str | None = None,
) -> ExecutionManifest:
    session = manifest.session
    if status == AnalysisJobStatus.RUNNING and session.started_at is None:
        session = session.model_copy(update={"started_at": timestamp})
    elif status in {AnalysisJobStatus.COMPLETED, AnalysisJobStatus.FAILED}:
        session = session.model_copy(update={"ended_at": timestamp})
    identity = manifest.run_identity
    if strategy_id is not None and identity.strategy_id != strategy_id:
        identity = identity.model_copy(update={"strategy_id": strategy_id})
    return manifest.model_copy(update={"session": session, "run_identity": identity})


def _manifest_from_completion(manifest: ExecutionManifest, result_envelope: APIEnvelope, completed_at: datetime, *, strategy_id: str | None) -> ExecutionManifest:
    manifest = _manifest_with_session_update(manifest, AnalysisJobStatus.COMPLETED, completed_at, strategy_id=strategy_id)
    performance = result_envelope.user_payload.performance
    if not isinstance(performance, PerformanceAvailable):
        return manifest
    ledger = _storage_ledger(result_envelope)
    if ledger is None:
        # The public projection intentionally omits engine_summary.  A ledger may be
        # recovered from the internal debug store, but a missing one must not make the
        # public serializer reach back into its hidden metrics payload.
        return manifest
    events = _events_from_storage_ledger(ledger, completed_at)
    source_count = int(ledger.get("source_event_count", -1))
    source_hash = str(ledger.get("source_event_hash", ""))
    if source_count != _event_count(events) or source_hash != _stable_hash(_ledger_source(ledger)):
        raise JobStoreConfigurationError("storage execution ledger count/hash reconciliation failed.")
    return manifest.model_copy(update={"events": events, "ledger_event_count": source_count, "ledger_event_hash": source_hash, "policy_hashes": _policy_hashes(result_envelope, {}, ledger.get("order_audit", []), strategy_id=manifest.run_identity.strategy_id)})


def _storage_ledger(result_envelope: APIEnvelope) -> Mapping[str, Any] | None:
    try:
        from ai_graph.graph import DEBUG_STORE

        payload = DEBUG_STORE.get(result_envelope.debug_ref)
    except (ImportError, AttributeError):
        payload = None
    ledger = payload.backtest_artifacts.get("engine_summary", {}).get("_storage_execution_ledger") if payload else None
    return ledger if isinstance(ledger, Mapping) else None


def _events_from_storage_ledger(ledger: Mapping[str, Any], occurred_at: datetime) -> ExecutionEvents:
    def records(name: str) -> list[Mapping[str, Any]]:
        value = ledger.get(name, [])
        return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []

    def mapped(name: str, prefix: str) -> list[ExecutionEvent]:
        return [_audit_execution_event(event, f"{prefix}:{index}", _event_timestamp(event.get("exit_date", event.get("date")), occurred_at)) for index, event in enumerate(records(name))]

    return ExecutionEvents(signals=mapped("signals", "signal"), orders=mapped("order_audit", "order"), fills=mapped("fills", "fill"), positions=mapped("positions", "position"), trades=mapped("trades", "trade"), equity=mapped("equity", "equity"))


def _event_count(events: ExecutionEvents) -> int:
    return sum(len(getattr(events, name)) for name in ("signals", "orders", "fills", "positions", "trades", "equity"))


def _ledger_source(ledger: Mapping[str, Any]) -> dict[str, Any]:
    return {key: ledger.get(key, []) for key in ("signals", "order_audit", "fills", "positions", "trades", "equity")}

def _execution_events_from_backtest(audit_events: Sequence[Mapping[str, Any]], equity_curve: Sequence[Any], occurred_at: datetime) -> ExecutionEvents:
    signals: list[ExecutionEvent] = []
    orders: list[ExecutionEvent] = []
    fills: list[ExecutionEvent] = []
    positions: list[ExecutionEvent] = []
    trades: list[ExecutionEvent] = []
    for index, event in enumerate(audit_events):
        status = str(event.get("status") or "unknown")
        execution_event = _audit_execution_event(event, f"audit:{index}", _event_timestamp(event.get("date"), occurred_at))
        if status == "submitted":
            signals.append(execution_event)
            orders.append(execution_event)
        if status == "executed":
            fills.append(execution_event)
            positions.append(execution_event)
            trades.append(execution_event)
    equity = [
        ExecutionEvent(event_id=f"equity:{index}", occurred_at=_event_timestamp(getattr(point, "date", None), occurred_at), requested_qty=0, filled_qty=0, reason="equity_mark", document=_safe_document(point.model_dump(mode="json") if hasattr(point, "model_dump") else {}))
        for index, point in enumerate(equity_curve)
    ]
    return ExecutionEvents(signals=signals, orders=orders, fills=fills, positions=positions, trades=trades, equity=equity)


def _audit_execution_event(event: Mapping[str, Any], event_id: str, occurred_at: datetime) -> ExecutionEvent:
    requested = _nonnegative_float(event.get("requested_quantity", event.get("quantity")))
    filled = _nonnegative_float(event.get("filled_quantity"))
    if str(event.get("status")) == "executed" and filled == 0:
        filled = requested
    costs = {name: _nonnegative_float(event.get(name)) for name in ("commission_cost", "tax_cost", "slippage_cost") if event.get(name) is not None}
    return ExecutionEvent(event_id=event_id, occurred_at=occurred_at, requested_qty=requested, filled_qty=filled, reason=str(event.get("reason") or event.get("status") or "engine_execution"), component_costs=costs, document=_safe_document(event))



def _policy_hashes(
    result_envelope: APIEnvelope,
    engine_summary: Mapping[str, Any],
    audit_events: Sequence[Mapping[str, Any]],
    *,
    strategy_id: str | None,
) -> dict[str, str]:
    strategy = (
        result_envelope.strategy_spec.model_dump(mode="json")
        if result_envelope.strategy_spec
        else {"strategy_id": strategy_id}
    )
    performance = result_envelope.user_payload.performance
    return {
        "execution_contract": MANIFEST_CONTRACT_HASH,
        "strategy": _stable_hash(strategy),
        "data": _stable_hash({"method_manifest": performance.method_manifest.model_dump(mode="json") if isinstance(performance, PerformanceAvailable) else None}),
        "cost": _stable_hash({"cost_policy_ids": sorted(str(event["cost_policy_id"]) for event in audit_events if event.get("cost_policy_id")), "cost_components": [_safe_document(event) for event in audit_events if event.get("cost") is not None]}),
        "sizing": _stable_hash(engine_summary.get("ai_backtest_context", {})),
        "benchmark": _stable_hash({"benchmark_method": performance.method_manifest.benchmark_method if isinstance(performance, PerformanceAvailable) else None, "provenance": engine_summary.get("benchmark_provenance", {})}),
    }


def _stable_hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")).hexdigest()


def _safe_document(value: Mapping[str, Any]) -> dict[str, str | int | float | bool | None]:
    allowed = {"date", "exit_date", "signal_date", "ticker", "side", "status", "reason", "price", "quantity", "fill_quantity", "requested_quantity", "filled_quantity", "fill_rate", "notional", "cost", "cost_policy_id", "commission_cost", "tax_cost", "slippage_cost", "cash", "positions_value", "total_equity", "daily_return", "cumulative_return", "gross_pnl", "net_pnl", "return_pct", "entry_cost", "exit_cost"}
    return {key: normalized for key, raw in value.items() if key in allowed and (normalized := _scalar_document_value(raw)) is not None}


def _scalar_document_value(value: Any) -> str | int | float | bool | None:
    return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)


def _nonnegative_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _event_timestamp(value: Any, default: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError:
            pass
    return default

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


def classify_failure(exc: Exception, *, stage: str) -> FailureDiagnostic:
    if isinstance(exc, EmptyAnalysisResultError):
        return FailureDiagnostic(
            category="data_gap",
            subcause="empty_analysis_result",
            failure_stage=stage,
            owner="ai_graph",
            retryable=False,
            safe_message=(
                "분석 결과를 생성하지 못했습니다. 같은 결과를 재사용하지 않고 중단했습니다. "
                "조건을 조정해 다시 시도해 주세요."
            ),
            evidence_refs=["failure:empty_analysis_result"],
        )
    # Matched on the exception type before any of the message heuristics below, and by
    # name rather than by import so this module stays free of the llm package. A queued
    # request that never got a provider slot is a capacity problem, not the generic
    # unknown failure its message would otherwise be sorted into.
    if type(exc).__name__ == "AOAIGateBusyError":
        return FailureDiagnostic(
            category="infrastructure_failure",
            subcause="aoai_capacity_exhausted",
            failure_stage=stage,
            owner="ai_graph",
            retryable=True,
            safe_message="현재 AI 분석 요청이 몰려 대기 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
            evidence_refs=["failure:aoai_capacity_exhausted"],
        )
    exception_chain = _exception_chain(exc)
    provider_failure = any(
        type(error).__name__ in {"LLMClientError", "LLMTimeoutError"}
        for error in exception_chain
    )
    if provider_failure:
        provider_timeout = next(
            (error for error in exception_chain if isinstance(error, httpx.TimeoutException)),
            None,
        )
        if provider_timeout is not None:
            return _aoai_failure_diagnostic(
                subcause="aoai_response_timeout",
                stage=stage,
                retryable=True,
                safe_message=(
                    "AI 응답이 제한 시간 안에 도착하지 않았습니다. 잠시 후 다시 시도해 주세요."
                ),
            )
        provider_connection_error = next(
            (error for error in exception_chain if isinstance(error, httpx.ConnectError)),
            None,
        )
        if provider_connection_error is not None:
            return _aoai_failure_diagnostic(
                subcause="aoai_connection_error",
                stage=stage,
                retryable=True,
                safe_message=(
                    "AI 제공자 연결에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."
                ),
            )
        provider_http_error = next(
            (error for error in exception_chain if isinstance(error, httpx.HTTPStatusError)),
            None,
        )
        if provider_http_error is not None:
            status_code = provider_http_error.response.status_code
            if status_code >= 500:
                subcause = "aoai_http_5xx"
            elif status_code >= 400:
                subcause = "aoai_http_4xx"
            else:
                subcause = "aoai_http_error"
            return _aoai_failure_diagnostic(
                subcause=subcause,
                stage=stage,
                retryable=status_code >= 500 or status_code in {408, 409, 429},
                safe_message="AI 제공자 응답을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            )
    # The provider accepted the request and then stopped producing, so retries burned the
    # budget without a usable answer. Some callers raise LLMTimeoutError directly, with
    # no httpx cause to inspect, so retain this compatible fallback after the causal
    # classification above.
    if provider_failure and "timed out" in str(exc).lower():
        return FailureDiagnostic(
            category="infrastructure_failure",
            subcause="aoai_response_timeout",
            failure_stage=stage,
            owner="ai_graph",
            retryable=True,
            safe_message=(
                "AI 응답이 제한 시간 안에 도착하지 않았습니다. 잠시 후 다시 시도해 주세요."
            ),
            evidence_refs=["failure:aoai_response_timeout"],
        )
    # psycopg raises OutOfMemory for the server's "out of shared memory", which here has
    # only ever meant the lock table filled up: a query touched more partitions than
    # max_locks_per_transaction x max_connections leaves room for. Matched by type name
    # rather than message because the message heuristics below never caught it - it
    # contains none of "timeout", "validation" or "schema", so a run that died this way
    # was reported as "분류되지 않은 오류", which told the user nothing and hid a
    # warehouse-side cause behind a message that reads like an AI bug.
    if type(exc).__name__ == "OutOfMemory" or "out of shared memory" in str(exc).lower():
        return FailureDiagnostic(
            category="infrastructure_failure",
            subcause="db_lock_capacity_exhausted",
            failure_stage=stage,
            owner="data_source_config",
            retryable=True,
            safe_message=(
                "데이터 조회가 서버 자원 한도에 걸려 중단했습니다. "
                "일시적인 부하일 수 있으니 잠시 후 다시 시도해 주세요."
            ),
            evidence_refs=["failure:db_lock_capacity_exhausted"],
        )
    # The warehouse answered, it just had nothing to run this strategy on. That is an
    # answer for the user, not a crash: sorted into unknown_failure it produced "분류되지
    # 않은 오류" with no indication that the screen simply matched nothing, and the run
    # looked indistinguishable from one that had hung.
    if isinstance(exc, PipelineDataUnavailableError):
        no_matches = exc.reason == "no_screening_matches"
        return FailureDiagnostic(
            category="data_gap",
            subcause=exc.reason,
            failure_stage=Stage.INTERPRETING.value,
            owner="data_source_config",
            retryable=False,
            safe_message=(
                "조건에 맞는 종목을 찾지 못했습니다. 조건을 완화해 다시 시도해 주세요."
                if no_matches
                else "선정된 종목의 가격 데이터가 적재되어 있지 않아 백테스트를 진행할 수 없습니다."
            ),
            evidence_refs=[f"failure:{exc.reason}"],
        )
    if any(_is_postgres_connection_failure(error) for error in exception_chain):
        return FailureDiagnostic(
            category="infrastructure_failure",
            subcause="db_connection_unavailable",
            failure_stage=stage,
            owner="data_source_config",
            retryable=True,
            safe_message="운영 데이터 소스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            evidence_refs=["failure:db_connection_unavailable"],
        )
    raw = str(exc).lower()
    if "connection timeout" in raw or "connect timeout" in raw or "connection timed out" in raw:
        return FailureDiagnostic(
            category="infrastructure_failure",
            subcause="db_connect_timeout",
            failure_stage=stage,
            owner="data_source_config",
            retryable=True,
            safe_message="데이터 소스 연결 시간이 초과되었습니다. 잠시 후 다시 시도하거나 데이터 소스 설정을 확인해 주세요.",
            evidence_refs=["failure:db_connect_timeout"],
        )
    if "statement timeout" in raw or "query timeout" in raw:
        return FailureDiagnostic(
            category="infrastructure_failure",
            subcause="db_statement_timeout",
            failure_stage=stage,
            owner="data_source_config",
            retryable=True,
            # Deliberately does not tell the user to narrow their conditions. The
            # timeout that prompted this was our own backtest history query asking for
            # twenty years of date partitions per indicator table; no wording of the
            # user's strategy would have changed it, and the advice sent people editing
            # a request that was never the problem.
            safe_message=(
                "데이터 조회가 제한 시간을 넘겨 중단했습니다. "
                "일시적인 부하일 수 있으니 잠시 후 다시 시도해 주세요."
            ),
            evidence_refs=["failure:db_statement_timeout"],
        )
    if "validation" in raw or "contract" in raw or "schema" in raw:
        return FailureDiagnostic(
            category="semantic_failure",
            subcause="contract_shape_error",
            failure_stage=stage,
            owner="ai_graph",
            retryable=False,
            safe_message="AI 파이프라인 계약 검증에 실패했습니다. 지원팀이 추적할 수 있도록 debug_ref를 보존했습니다.",
            evidence_refs=["failure:contract_shape_error"],
        )
    return FailureDiagnostic(
        category="unknown_failure",
        subcause="unknown",
        failure_stage=stage,
        owner="unknown",
        retryable=True,
        safe_message="AI 분석 중 분류되지 않은 오류가 발생했습니다. 원문 오류는 공개 응답에 노출하지 않고 debug_ref로 추적합니다.",
        evidence_refs=["failure:unknown"],
    )


def _require_analysis_envelope(value: object) -> APIEnvelope:
    """Accept only a non-empty, schema-valid terminal result from a runner.

    ``AnalysisRunner`` is a typing protocol, not a runtime boundary.  A runner can
    therefore return an empty mapping or ``None`` after an upstream empty response.
    Validate it before `complete_job` so an AttributeError cannot strand the job in
    RUNNING or let a caller reuse a prior successful payload.
    """

    if value is None or (isinstance(value, Mapping) and not value):
        raise EmptyAnalysisResultError("analysis runner returned no result envelope")
    if isinstance(value, APIEnvelope):
        return value
    return APIEnvelope.model_validate(value)


def _exception_chain(exc: Exception) -> tuple[BaseException, ...]:
    """Return a finite explicit-cause chain without relying on provider messages."""

    chain: list[BaseException] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        cause = current.__cause__
        current = cause if isinstance(cause, BaseException) else None
    return tuple(chain)


def _is_postgres_connection_failure(error: BaseException) -> bool:
    """Recognize driver connection failures without importing a database driver here.

    Jobs intentionally stay usable in non-PostgreSQL test/runtime modes.  The driver
    nevertheless preserves a stable module/type identity for connection-establishment
    failures, including the direct ``psycopg.OperationalError`` emitted by ``connect``
    before a SQLSTATE exists.  SQLSTATE class 08 is the PostgreSQL-defined connection
    family; other database errors remain subject to their more specific classifiers.
    """

    error_type = type(error)
    module = error_type.__module__
    sqlstate = getattr(error, "sqlstate", None)
    if isinstance(sqlstate, str) and sqlstate.startswith("08"):
        return module.startswith("psycopg")
    return module == "psycopg" and error_type.__name__ in {
        "OperationalError",
        "InterfaceError",
    }


def _aoai_failure_diagnostic(
    *,
    subcause: Literal[
        "aoai_response_timeout",
        "aoai_connection_error",
        "aoai_http_4xx",
        "aoai_http_5xx",
        "aoai_http_error",
    ],
    stage: str,
    retryable: bool,
    safe_message: str,
) -> FailureDiagnostic:
    return FailureDiagnostic(
        category="infrastructure_failure",
        subcause=subcause,
        failure_stage=stage,
        owner="ai_graph",
        retryable=retryable,
        safe_message=safe_message,
        evidence_refs=[f"failure:{subcause}"],
    )


def _failure_envelope(
    job: AnalysisJob,
    error_message: str,
    *,
    failure_cause: FailureDiagnostic | None = None,
) -> APIEnvelope:
    diagnostic = failure_cause or classify_failure(RuntimeError(error_message), stage=Stage.FINALIZING.value)
    return APIEnvelope(
        status=EnvelopeStatus.FAILED,
        trace_id=job.trace_id,
        user_payload=UserPayload(
            headline="AI 분석을 완료하지 못했습니다.",
            message=diagnostic.safe_message,
            next_actions=["조건을 좁혀 재시도", "문제가 반복되면 debug_ref 공유"],
        ),
        strategy_spec=None,
        debug_ref=f"job-error:{job.job_id}",
        retryable=diagnostic.retryable,
        failure_cause=diagnostic,
    )


def job_deadline_seconds(environ_map: Mapping[str, str] | None = None) -> float | None:
    """The ceiling for one whole request, or None when it is not bounded.

    An explicit `0` disables the ceiling, which is what the per-phase budgets alone did.
    An unparseable value falls back to the default rather than removing the ceiling: a
    typo should not be the thing that lets a run hold an analysis slot indefinitely.
    """

    resolved = environ if environ_map is None else environ_map
    raw = str(resolved.get(AI_JOB_DEADLINE_SECONDS_ENV, "")).strip()
    if not raw:
        return DEFAULT_JOB_DEADLINE_SECONDS
    try:
        value = float(raw)
    except ValueError:
        _logger.warning(
            "%s=%r is not a number; using %s",
            AI_JOB_DEADLINE_SECONDS_ENV,
            raw,
            DEFAULT_JOB_DEADLINE_SECONDS,
        )
        return DEFAULT_JOB_DEADLINE_SECONDS
    return value if value > 0 else None


_REAPABLE_STATUSES = frozenset({AnalysisJobStatus.QUEUED, AnalysisJobStatus.RUNNING})


def reap_interrupted_jobs(
    store: AnalysisJobStore,
    *,
    incarnation: str = PROCESS_INCARNATION,
    limit: int = 500,
) -> list[str]:
    """Fail the jobs a previous process left mid-flight, and return their ids.

    Without this a restart leaves rows that say RUNNING forever: the client polls a
    spinner that will never resolve, and an operator cannot tell a stuck job apart from
    a slow one. Because the work lives in this process's background tasks, a job whose
    recorded incarnation is not ours has nothing working on it - the run did not pause,
    it ended.

    A job with no recorded incarnation predates the field, which means an earlier process
    wrote it, so it is reaped for the same reason.  A partial reconciliation is not safe:
    any row that cannot be transitioned can still spin forever, so startup must stop and
    expose the dependency failure rather than serving a misleading job API.
    """

    try:
        reconciliation_store = store if isinstance(store, RestartReconciliationStore) else None
        batch = (
            reconciliation_store.list_jobs_for_reconciliation(limit=limit)
            if reconciliation_store is not None
            else store.list_jobs(limit=limit)
        )
    except Exception as error:
        raise InterruptedJobReconciliationError(
            "analysis job restart reconciliation could not inspect the job store"
        ) from error

    jobs = list(getattr(batch, "jobs", batch))
    # Active rows this build cannot load at all. They are settled by id rather than
    # skipped, and rather than refusing to start: they are already in the database, so a
    # policy of refusing over them is an outage with no way out of it.
    undecodable = list(getattr(batch, "undecodable_job_ids", ()))
    reaped: list[str] = []
    for job_id in undecodable:
        try:
            settled = reconciliation_store.force_fail_undecodable_job(
                job_id,
                error_message=INTERRUPTED_BY_RESTART_MESSAGE,
                reason=INTERRUPTED_BY_RESTART_REASON,
            )
        except Exception as error:
            _logger.exception("could not settle undecodable analysis job %s", job_id)
            raise InterruptedJobReconciliationError(
                "analysis job restart reconciliation could not settle an undecodable job"
            ) from error
        if settled:
            _logger.warning(
                "settled analysis job %s written by an older build; it could not be decoded",
                job_id,
            )
            reaped.append(job_id)

    for job in jobs:
        if job.status not in _REAPABLE_STATUSES or job.owner_incarnation == incarnation:
            continue
        try:
            store.fail_job(
                job.job_id,
                INTERRUPTED_BY_RESTART_MESSAGE,
                fallback_reasons=[*job.fallback_reasons, INTERRUPTED_BY_RESTART_REASON],
            )
        except Exception as error:
            _logger.exception("could not reap interrupted analysis job %s", job.job_id)
            raise InterruptedJobReconciliationError(
                "analysis job restart reconciliation could not settle an interrupted job"
            ) from error
        reaped.append(job.job_id)
    return reaped
