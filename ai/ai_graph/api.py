from __future__ import annotations

# pyright: reportUnannotatedClassAttribute=false, reportUnusedFunction=false
import asyncio
import json
import secrets
import uuid
from collections.abc import AsyncIterator, Callable
from os import environ
from typing import ClassVar, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_graph.audit import (
    AuditSession,
    AuditSink,
    NoOpAuditSink,
    bind_audit_context,
    create_audit_correlation,
    report_audit_failure,
)
from ai_graph.audit_postgres import resolve_audit_sink
from ai_graph.auth import RequireAuthenticatedUser, SessionResolver
from ai_graph.data_sources.db import (
    ANALYST_REPORT_TABLE,
    BOK_MACRO_VIEW,
    KIS_ADJUSTED_OHLCV_TABLE,
    SYMBOL_MASTER_TABLE,
    measure_research_runtime_facts_from_env,
    resolve_database_dsn_from_env,
)
from ai_graph.graph import run_analysis
from ai_graph.job_events import JobEventBuffer
from ai_graph.job_repository_postgres import PostgresAnalysisJobRepository
from ai_graph.job_store_persistent import PersistentAnalysisJobStore
from ai_graph.jobs import (
    AI_JOB_STORE_ENV,
    AnalysisJob,
    AnalysisJobStore,
    AnalysisRunner,
    CancellationRegistry,
    JobStoreRuntime,
    PERSISTENT_JOB_STORE_MODE,
    create_analysis_job_store_from_env,
    run_job_sync,
)
from ai_graph.llm.role_calls import generate_strategy_description
from ai_graph.preflight import (
    SCOPE_REFUSAL_REASON,
    UNSUPPORTED_SCOPE_REASON,
    ResearchRequestPreflight,
    classify_research_request,
)
from ai_graph.research_contract import (
    CanonicalRuleV1,
    DraftConflictV1,
    DraftTokenValidationError,
    InMemoryDraftNonceRegistry,
    ParseReviewV1,
    ResearchJobAcceptedV1,
    ResearchResultV1,
    RuleDraftSigner,
    ScopeRefusalV1,
    UnsupportedScopeV1,
    build_rule_draft,
    canonical_rule_execution_query,
    unavailable_result_for_unverified_job,
)
from ai_graph.research_eligibility import (
    EligiblePostgresEod,
    ResearchRuntimeFacts,
    evaluate_research_eligibility,
)
from ai_graph.schemas import (
    SCHEMA_VERSION,
    APIEnvelope,
    EnvelopeStatus,
    UserPayload,
)
from ai_graph.token_auth import (
    AccountTokenQuota,
    AccountTokenResolver,
    RequirePreflightIdentityReadOnly,
    RequireUserIdentity,
    RequireUserIdentityWithinQuota,
)

API_TITLE = "QuantAgent AI API"
API_VERSION = "0.1.0"
API_DESCRIPTION = "Local MVP API surface for QuantAgent analysis jobs."
DOCS_URL = "/docs"
OPENAPI_URL = "/openapi.json"
HEALTH_PATH = "/health"
READINESS_PATH = "/readiness"
API_STATUS_PATH = "/api-status"
ANALYSIS_JOBS_PATH = "/analysis-jobs"
ANALYSIS_JOB_DETAIL_PATH = f"{ANALYSIS_JOBS_PATH}/{{job_id}}"
ANALYSIS_JOB_EVENTS_PATH = f"{ANALYSIS_JOBS_PATH}/{{job_id}}/events"
ANALYSIS_JOB_CANCEL_PATH = f"{ANALYSIS_JOBS_PATH}/{{job_id}}/cancel"
# How long an idle SSE reader waits before checking for new provider activity.
ANALYSIS_EVENT_POLL_SECONDS = 0.25
# Idle gap after which a comment line is sent so intermediaries keep the stream open.
ANALYSIS_EVENT_KEEPALIVE_SECONDS = 15.0
SPEC_STRATEGY_PARSE_PATH = "/api/strategies/parse"
RESEARCH_JOB_CREATE_PATH = "/api/research/jobs"
RESEARCH_JOB_RESULT_PATH = f"{RESEARCH_JOB_CREATE_PATH}/{{job_id}}/result"
STRATEGY_DESCRIPTIONS_PATH = "/api/strategies/descriptions"
SPEC_ANALYSIS_JOB_DETAIL_PATH = "/api/analysis-jobs/{job_id}"
SPEC_BACKTEST_DETAIL_PATH = "/api/backtests/{strategy_id}"
SPEC_REPORT_DETAIL_PATH = "/api/reports/{report_id}"
DAILY_DIGEST_PATH = "/ai/daily-digest"
AI_CORS_ALLOW_ORIGINS_ENV = "AI_CORS_ALLOW_ORIGINS"
CORS_ALLOW_METHODS = ["GET", "POST", "OPTIONS"]
CORS_ALLOW_HEADERS = ["Authorization", "Content-Type"]
RESEARCH_EXECUTION_ENABLED_ENV = "AI_RESEARCH_EXECUTION_ENABLED"
DATA_EVIDENCE_PROBE_TOKEN_ENV = "AI_DATA_EVIDENCE_PROBE_TOKEN"
DATA_EVIDENCE_PROBE_PATH = "/_operator/research-data-evidence"
DEPLOYMENT_REVISION_ENV = "AI_AUDIT_GATE_B_DEPLOYMENT_REVISION"
READINESS_CONTRACT_VERSION = "ai-release-readiness.v1"
REQUIRED_AI_CONTRACT_VERSION = "ai-mvp.v1"
ANALYSIS_JOBS_MIGRATION_REVISION = "021_ai_analysis_jobs"
AI_LLM_PROVIDER_ENV = "AI_LLM_PROVIDER"
AI_AOAI_RESPONSES_URL_ENV = "AI_AOAI_RESPONSES_URL"
AI_AOAI_API_KEY_ENV = "AI_AOAI_API_KEY"
AI_AOAI_MODEL_ENV = "AI_AOAI_MODEL"


class CreateAnalysisJobRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "query": (
                        "KRX 상장 종목 중 RSI가 30 이하이고 거래량이 "
                        "20일 평균보다 큰 조건을 검토해 주세요."
                    )
                }
            ]
        },
    )

    query: str = Field(min_length=1)


class ConfirmedResearchExecutionRequest(BaseModel):
    """A signed canonical rule; raw natural-language input is never accepted here."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    canonical_rule: CanonicalRuleV1
    draft_token: str = Field(min_length=32)


class ParseStrategyRequest(BaseModel):
    # Ignore retired request keys from older frontends during the rolling deploy.
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    natural_language: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    market: str | None = None
    strategy_id: str | None = None
    selected_clarification_option_id: str | None = None
    client_request_id: str | None = None

    @model_validator(mode="after")
    def require_query_text(self) -> ParseStrategyRequest:
        if not self.request_text:
            raise ValueError("natural_language or query is required")
        return self

    @property
    def request_text(self) -> str:
        return (self.natural_language or self.query or "").strip()


class DataEvidenceProbeResponse(BaseModel):
    """Non-public, secret-free read-only measurement response for release evidence."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    decision: Literal["eligible", "ineligible"]
    reason_code: str | None = None
    facts: ResearchRuntimeFacts
    deployment_revision: str | None = None


PreflightRejectionResponse = ScopeRefusalV1 | UnsupportedScopeV1


def _preflight_rejection_response(
    decision: ResearchRequestPreflight,
) -> JSONResponse | None:
    if decision.allowed:
        return None
    if decision.reason_code == UNSUPPORTED_SCOPE_REASON:
        response: PreflightRejectionResponse = UnsupportedScopeV1(
            reason_code=UNSUPPORTED_SCOPE_REASON,
            explanation=decision.public_message,
            general_example=decision.public_example,
            guidance=decision.public_guidance,
        )
    else:
        response = ScopeRefusalV1(
            reason_code=SCOPE_REFUSAL_REASON,
            explanation=decision.public_message,
            general_example=decision.public_example,
            guidance=decision.public_guidance,
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=response.model_dump(),
    )


def _draft_conflict_response(code: str) -> JSONResponse:
    allowed_codes = {
        "draft_invalid",
        "draft_expired",
        "draft_user_mismatch",
        "draft_rule_mismatch",
        "draft_replayed",
    }
    reason_code = code if code in allowed_codes else "draft_invalid"
    response = DraftConflictV1(
        reason_code=reason_code,
        explanation="검토한 규칙 초안이 변경되었거나 더 이상 유효하지 않습니다.",
        guidance="규칙을 다시 검토한 뒤 새 초안으로 실행해 주세요.",
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=response.model_dump(),
    )


class StrategyDescriptionInput(BaseModel):
    # Ignore retired keys from older frontends during the rolling deploy.
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    strategy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    entry_summary: str = Field(min_length=1)
    exit_summary: str = Field(min_length=1)
    risk_summary: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list, max_length=8)


class StrategyDescriptionsRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    strategies: list[StrategyDescriptionInput] = Field(min_length=1, max_length=20)


class StrategyDescriptionItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    fallback_reasons: list[str] = Field(default_factory=list)


class StrategyDescriptionsResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    items: list[StrategyDescriptionItem] = Field(min_length=1)


class HealthResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    status: Literal["ok"]
    schema_version: str


class ReadinessCheck(BaseModel):
    """One non-secret release dependency result."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: Literal[
        "durable_job_store",
        "migration_revision",
        "live_provider_configuration",
        "ai_contract_version",
        "rule_draft_signer",
    ]
    ready: bool
    reason: str | None = None


class ReadinessResponse(BaseModel):
    """Fail-closed admission status for a deployable AI release."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    status: Literal["ready", "unavailable"]
    contract_version: str = READINESS_CONTRACT_VERSION
    migration_revision: str = ANALYSIS_JOBS_MIGRATION_REVISION
    ai_contract_version: str
    checks: list[ReadinessCheck]


class EndpointStatus(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    method: Literal["GET", "POST"]
    path: str
    state: Literal["available", "local_sync", "job_store", "readiness", "retired"]
    summary: str


class DataSourceStatus(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    configured: bool
    dsn_env: str
    price_source: str
    candidate_pool_source: str
    l4_evidence_source: str
    macro_source: str
    macro_usable: bool
    fallback_when_unset: str


class JobStoreStatus(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    requested_mode: str
    active_mode: str
    mode_env: str
    dsn_env: str
    dsn_configured: bool
    fallback: bool
    fallback_reason: str | None


class APIStatusResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    service: str
    schema_version: str
    docs_url: str
    openapi_url: str
    data_source: DataSourceStatus
    job_store: JobStoreStatus
    endpoints: list[EndpointStatus]


def _build_analysis_runner_with_audit(
    analysis_runner: AnalysisRunner,
    *,
    audit_sink: AuditSink | None,
    trace_id: str,
    entrypoint: str,
    feature: str,
    strategy_id: str | None = None,
    client_request_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> AnalysisRunner:
    def runner(query: str, trace_id: str) -> APIEnvelope:
        session = _open_request_audit_session(
            audit_sink,
            trace_id=trace_id,
            entrypoint=entrypoint,
            feature=feature,
            strategy_id=strategy_id,
            client_request_id=client_request_id,
            user_id=user_id,
            session_id=session_id,
        )
        _record_step(session, "job_dispatched", message="analysis request dispatched")
        with bind_audit_context(session):
            if analysis_runner is run_analysis:
                return run_analysis(
                    query,
                    trace_id,
                    audit_session=session,
                    audit_entrypoint=entrypoint,
                    audit_feature=feature,
                    strategy_id=strategy_id,
                    client_request_id=client_request_id,
                    user_id=user_id,
                    session_id=session_id,
                )
            _record_step(session, "analysis_started", message="analysis runner execution started")
            try:
                envelope = analysis_runner(query, trace_id)
            except Exception as exc:
                _record_error(
                    session,
                    "analysis_execution",
                    error_type=type(exc).__name__,
                    message=f"{type(exc).__name__} raised during analysis runner execution",
                )
                _record_finalization(session, "failed", message="analysis runner execution failed")
                raise
            status_label = envelope.status.value
            _record_step(
                session,
                "analysis_completed",
                message=f"analysis runner returned status={status_label}",
            )
            _record_finalization(
                session,
                "failed" if envelope.status == EnvelopeStatus.FAILED else "completed",
                message=f"analysis runner completed with status={status_label}",
                metadata_jsonb={
                    "debug_ref": envelope.debug_ref,
                    "public_trace_id": envelope.trace_id,
                },
            )
            return envelope

    return runner


def _open_request_audit_session(
    audit_sink: AuditSink | None,
    *,
    trace_id: str | None,
    entrypoint: str,
    feature: str,
    strategy_id: str | None = None,
    client_request_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> AuditSession:
    correlation = create_audit_correlation(
        trace_id=trace_id,
        debug_ref=None,
        entrypoint=entrypoint,
        feature=feature,
        strategy_id=strategy_id,
        client_request_id=client_request_id,
        user_id=user_id,
        session_id=session_id,
    )
    sink = resolve_audit_sink(audit_sink)
    try:
        return sink.open_session(correlation)
    except Exception:
        report_audit_failure("open_session")
        return NoOpAuditSink().open_session(correlation)


def _record_step(session: AuditSession, step: str, *, message: str | None = None) -> None:
    try:
        session.record_step(step, message=message)
    except Exception:
        report_audit_failure("record_step")


def _record_error(
    session: AuditSession,
    step: str,
    *,
    error_type: str,
    message: str,
) -> None:
    try:
        session.record_error(step, error_type=error_type, message=message)
    except Exception:
        report_audit_failure("record_error")


def _record_finalization(
    session: AuditSession,
    status: str,
    *,
    message: str | None = None,
    metadata_jsonb: dict[str, object] | None = None,
) -> None:
    try:
        session.record_finalization(status, message=message, metadata_jsonb=metadata_jsonb)
    except Exception:
        report_audit_failure("record_finalization")


def create_app(
    job_store: AnalysisJobStore | None = None,
    *,
    analysis_runner: AnalysisRunner = run_analysis,
    job_store_runtime: JobStoreRuntime | None = None,
    audit_sink: AuditSink | None = None,
    session_resolver: SessionResolver | None = None,
    account_token_resolver: AccountTokenResolver | None = None,
    account_token_quota: AccountTokenQuota | None = None,
    rule_draft_signer: RuleDraftSigner | None = None,
    draft_nonce_registry: InMemoryDraftNonceRegistry | None = None,
    research_execution_enabled: bool | None = None,
    readiness_migration_probe: Callable[[], bool] | None = None,
) -> FastAPI:
    runtime = job_store_runtime or _job_store_runtime(job_store)
    store = runtime.store
    # Identity accepts either a bearer API token or the browser session cookie. Routes
    # that spend AOAI capacity use the quota-enforcing variant instead, so a token's
    # allowance is charged exactly where the provider cost is incurred - listing or
    # cancelling a job consumes none, and is not counted against it.
    require_user = RequireUserIdentity(
        session_requirement=RequireAuthenticatedUser(session_resolver),
        token_resolver=account_token_resolver,
    )
    require_user_within_quota = RequireUserIdentityWithinQuota(
        require_user, quota=account_token_quota
    )
    require_preflight_user = RequirePreflightIdentityReadOnly(
        session_requirement=RequireAuthenticatedUser(session_resolver),
        token_resolver=account_token_resolver,
        quota=account_token_quota,
    )
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        docs_url=DOCS_URL,
        openapi_url=OPENAPI_URL,
    )
    cors_allow_origins = _cors_allow_origins()
    if cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_allow_origins,
            allow_credentials=True,
            allow_methods=CORS_ALLOW_METHODS,
            allow_headers=CORS_ALLOW_HEADERS,
        )
    app.state.job_store = store
    app.state.job_store_runtime = runtime
    app.state.job_events = JobEventBuffer()
    app.state.job_cancellations = CancellationRegistry()
    app.state.audit_sink = resolve_audit_sink(audit_sink)
    app.state.rule_draft_signer = rule_draft_signer or RuleDraftSigner.from_env()
    app.state.draft_nonce_registry = draft_nonce_registry or InMemoryDraftNonceRegistry()
    app.state.research_execution_enabled = (
        research_execution_enabled
        if research_execution_enabled is not None
        else _research_execution_enabled()
    )
    migration_probe = readiness_migration_probe or _analysis_jobs_migration_is_current

    probe_token = (environ.get(DATA_EVIDENCE_PROBE_TOKEN_ENV) or "").strip()
    if probe_token:
        @app.get(
            DATA_EVIDENCE_PROBE_PATH,
            response_model=DataEvidenceProbeResponse,
            include_in_schema=False,
        )
        def research_data_evidence_probe(
            x_ai_evidence_probe: str | None = Header(default=None),
        ) -> DataEvidenceProbeResponse:
            """Execute only the bounded DB adapter and policy; never create a job.

            The route is absent unless a separate operator secret is configured. It
            deliberately bypasses normal token/session resolvers because those can
            update usage/cache state; the probe must remain read-only end-to-end.
            """

            if not x_ai_evidence_probe or not secrets.compare_digest(
                x_ai_evidence_probe, probe_token
            ):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
            trace_id = f"evidence-{uuid.uuid4()}"
            facts = measure_research_runtime_facts_from_env(
                "KRX 상장 종목의 RSI 조건을 검토",
                trace_id,
            )
            decision = evaluate_research_eligibility(facts)
            return DataEvidenceProbeResponse(
                decision=decision.kind,
                reason_code=None if isinstance(decision, EligiblePostgresEod) else decision.reason_code,
                facts=facts,
                deployment_revision=(environ.get(DEPLOYMENT_REVISION_ENV) or "").strip() or None,
            )

    @app.get(HEALTH_PATH, response_model=HealthResponse, tags=["System"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", schema_version=SCHEMA_VERSION)

    @app.get(
        READINESS_PATH,
        response_model=ReadinessResponse,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
        tags=["System"],
    )
    def readiness(response: Response) -> ReadinessResponse:
        result = _release_readiness(
            runtime,
            migration_probe=migration_probe,
            rule_draft_signer=app.state.rule_draft_signer,
            provider_ready=_live_provider_configuration_is_ready(),
        )
        if result.status == "unavailable":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return result

    @app.get(API_STATUS_PATH, response_model=APIStatusResponse, tags=["System"])
    def api_status() -> APIStatusResponse:
        return APIStatusResponse(
            service=API_TITLE,
            schema_version=SCHEMA_VERSION,
            docs_url=DOCS_URL,
            openapi_url=OPENAPI_URL,
            data_source=_data_source_status(),
            job_store=_job_store_status(runtime),
            endpoints=_endpoint_statuses(),
        )

    @app.post(
        ANALYSIS_JOBS_PATH,
        response_model=AnalysisJob,
        status_code=status.HTTP_201_CREATED,
        tags=["Analysis Jobs"],
        responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": PreflightRejectionResponse}},
    )
    async def create_analysis_job(
        request: CreateAnalysisJobRequest,
        background_tasks: BackgroundTasks,
        http_request: Request,
        user_id: str = Depends(require_preflight_user),
    ) -> AnalysisJob | JSONResponse:
        """Queue the analysis and return the job immediately.

        Against a live provider the graph runs for minutes - far past any reverse
        proxy's read timeout - so running it inside the request turned every real
        analysis into a 504. The job store, the per-stage progress on AnalysisJob and
        GET /analysis-jobs/{job_id} already exist for exactly this shape: the client
        polls the queued job instead of holding one long request open.
        """

        scope_response = _preflight_rejection_response(classify_research_request(request.query))
        if scope_response is not None:
            return scope_response
        await require_preflight_user.consume_quota_after_preflight(http_request)
        job = store.create_job(request.query, user_id=user_id)
        background_tasks.add_task(
            run_job_sync,
            store,
            job.job_id,
            _build_analysis_runner_with_audit(
                analysis_runner,
                audit_sink=app.state.audit_sink,
                trace_id=job.trace_id,
                entrypoint="api.analysis_jobs",
                feature="analysis_job",
                user_id=user_id,
            ),
            events=app.state.job_events,
            cancellations=app.state.job_cancellations,
        )
        return job

    @app.post(
        ANALYSIS_JOB_CANCEL_PATH,
        response_model=AnalysisJob,
        tags=["Analysis Jobs"],
    )
    def cancel_analysis_job(
        job_id: str,
        user_id: str = Depends(require_user),
    ) -> AnalysisJob:
        """Ask a running analysis to stop at its next node boundary.

        Requests already sent to the provider cannot be recalled, so this does not undo
        what the run has already spent - it stops it before paying for the rest.
        """

        job = _owned_job(store, job_id, user_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="analysis job not found",
            )
        if job.result is not None:
            # Already finished - nothing to stop, and the result stands.
            return job
        app.state.job_cancellations.cancel(job_id)
        return job

    @app.get(ANALYSIS_JOB_EVENTS_PATH, tags=["Analysis Jobs"])
    async def stream_analysis_job_events(
        job_id: str,
        user_id: str = Depends(require_user),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """Stream the running analysis's provider activity as Server-Sent Events.

        Ownership is checked once up front: the job must exist and belong to the
        caller before any events are handed out.

        Every event carries its cursor as the SSE id, so a browser that reconnects
        sends Last-Event-ID and resumes where it left off. Without that a reconnect
        would replay the whole run - megabytes into a long analysis - which is enough
        traffic to trigger the next drop.
        """

        if _owned_job(store, job_id, user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="analysis job not found",
            )

        try:
            cursor = max(int(last_event_id), 0) if last_event_id else 0
        except ValueError:
            cursor = 0

        async def event_source() -> AsyncIterator[str]:
            nonlocal cursor
            idle_polls = 0
            while True:
                events, cursor, closed = app.state.job_events.read_since(job_id, cursor)
                first_id = cursor - len(events) + 1
                for offset, event in enumerate(events):
                    payload = json.dumps(event, ensure_ascii=False)
                    yield f"id: {first_id + offset}\ndata: {payload}\n\n"
                if closed and not events:
                    yield "event: done\ndata: {}\n\n"
                    return
                if not events:
                    idle_polls += 1
                    # A quiet stream looks dead to intermediaries; a comment line keeps
                    # the connection warm without reaching the EventSource consumer.
                    if idle_polls * ANALYSIS_EVENT_POLL_SECONDS >= ANALYSIS_EVENT_KEEPALIVE_SECONDS:
                        idle_polls = 0
                        yield ": keepalive\n\n"
                    await asyncio.sleep(ANALYSIS_EVENT_POLL_SECONDS)
                else:
                    idle_polls = 0

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                # Reverse proxies buffer by default, which would hold the whole stream
                # until the analysis finished and defeat the point of streaming.
                "X-Accel-Buffering": "no",
            },
        )

    @app.get(
        ANALYSIS_JOBS_PATH,
        response_model=list[AnalysisJob],
        tags=["Analysis Jobs"],
    )
    def list_analysis_jobs(
        limit: int = Query(default=100, ge=1, le=100),
        user_id: str = Depends(require_user),
    ) -> list[AnalysisJob]:
        owned_jobs = (job for job in store.list_jobs(limit=100) if job.user_id == user_id)
        return sorted(owned_jobs, key=lambda job: job.updated_at, reverse=True)[:limit]

    @app.post(
        SPEC_STRATEGY_PARSE_PATH,
        response_model=ParseReviewV1,
        status_code=status.HTTP_200_OK,
        tags=["Research Rule Review"],
        responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": PreflightRejectionResponse}},
    )
    async def parse_strategy(
        request: ParseStrategyRequest,
        user_id: str = Depends(require_preflight_user),
    ) -> ParseReviewV1 | JSONResponse:
        scope_response = _preflight_rejection_response(classify_research_request(request.request_text))
        if scope_response is not None:
            return scope_response
        signer = app.state.rule_draft_signer
        if signer is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Research rule review is temporarily unavailable.",
            )
        return build_rule_draft(
            query=request.request_text,
            user_id=user_id,
            signer=signer,
        )

    @app.post(
        RESEARCH_JOB_CREATE_PATH,
        response_model=ResearchJobAcceptedV1,
        status_code=status.HTTP_201_CREATED,
        tags=["Research Execution"],
        responses={
            status.HTTP_409_CONFLICT: {"model": DraftConflictV1},
        },
    )
    async def create_confirmed_research_job(
        request: ConfirmedResearchExecutionRequest,
        background_tasks: BackgroundTasks,
        http_request: Request,
        user_id: str = Depends(require_preflight_user),
    ) -> ResearchJobAcceptedV1 | JSONResponse:
        signer = app.state.rule_draft_signer
        if signer is None or not app.state.research_execution_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Research execution is not activated until operational evidence is available.",
            )
        if not request.canonical_rule.is_executable:
            return _draft_conflict_response("draft_rule_mismatch")
        try:
            nonce = signer.verify(
                token=request.draft_token,
                rule=request.canonical_rule,
                user_id=user_id,
            )
        except DraftTokenValidationError as exc:
            return _draft_conflict_response(exc.code)
        if not app.state.draft_nonce_registry.consume(user_id=user_id, nonce=nonce):
            return _draft_conflict_response("draft_replayed")
        await require_preflight_user.consume_quota_after_preflight(http_request)
        job = store.create_job(
            canonical_rule_execution_query(request.canonical_rule),
            user_id=user_id,
        )
        background_tasks.add_task(
            run_job_sync,
            store,
            job.job_id,
            _build_analysis_runner_with_audit(
                analysis_runner,
                audit_sink=app.state.audit_sink,
                trace_id=job.trace_id,
                entrypoint="api.research_jobs",
                feature="research_job",
                user_id=user_id,
            ),
            events=app.state.job_events,
            cancellations=app.state.job_cancellations,
        )
        return ResearchJobAcceptedV1(job_id=job.job_id)

    @app.get(
        RESEARCH_JOB_RESULT_PATH,
        response_model=ResearchResultV1,
        tags=["Research Execution"],
    )
    def get_research_job_result(
        job_id: str,
        user_id: str = Depends(require_user),
    ) -> ResearchResultV1:
        if _owned_job(store, job_id, user_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="research job not found")
        # This remains unavailable until result/lifecycle owners attach a durable result
        # identity and verified PostgreSQL EOD provenance to the completed job.
        return unavailable_result_for_unverified_job(job_id=job_id)

    @app.post(
        STRATEGY_DESCRIPTIONS_PATH,
        response_model=StrategyDescriptionsResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Strategy"],
    )
    def describe_strategies(
        request: StrategyDescriptionsRequest,
        user_id: str = Depends(require_user_within_quota),
    ) -> StrategyDescriptionsResponse:
        session = _open_request_audit_session(
            app.state.audit_sink,
            trace_id=None,
            entrypoint="api.strategy_descriptions",
            feature="strategy_descriptions",
            user_id=user_id,
        )
        _record_step(session, "descriptions_started", message=f"strategy_count={len(request.strategies)}")
        try:
            with bind_audit_context(session):
                items: list[StrategyDescriptionItem] = []
                for strategy in request.strategies:
                    payload = generate_strategy_description(
                        strategy_id=strategy.strategy_id,
                        name=strategy.name,
                        timeframe=strategy.timeframe,
                        entry_summary=strategy.entry_summary,
                        exit_summary=strategy.exit_summary,
                        risk_summary=strategy.risk_summary,
                        tags=strategy.tags,
                        fallback=(
                            f"{strategy.entry_summary} 조건이 맞는 종목을 선별하고 "
                            f"{strategy.exit_summary} 기준으로 정리하는 전략입니다."
                        ),
                    )
                    items.append(
                        StrategyDescriptionItem(
                            strategy_id=payload.strategy_id,
                            description=payload.description,
                            fallback_reasons=payload.fallback_reasons,
                        )
                    )
                    _record_step(
                        session,
                        "description_generated",
                        message=(
                            f"strategy_id={payload.strategy_id} "
                            f"fallback_used={'true' if payload.fallback_reasons else 'false'}"
                        ),
                    )
        except Exception as exc:
            _record_error(
                session,
                "description_generation",
                error_type=type(exc).__name__,
                message=f"{type(exc).__name__} raised during strategy description generation",
            )
            _record_finalization(session, "failed", message="strategy description generation failed")
            raise
        _record_finalization(session, "completed", message=f"generated {len(items)} strategy descriptions")
        return StrategyDescriptionsResponse(items=items)

    @app.get(
        ANALYSIS_JOB_DETAIL_PATH,
        response_model=AnalysisJob,
        tags=["Analysis Jobs"],
    )
    def get_analysis_job(job_id: str, user_id: str = Depends(require_user)) -> AnalysisJob:
        job = _owned_job(store, job_id, user_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="analysis job not found",
            )
        return job

    @app.get(
        SPEC_ANALYSIS_JOB_DETAIL_PATH,
        response_model=AnalysisJob,
        tags=["Spec Compatibility"],
    )
    def get_spec_analysis_job(job_id: str, user_id: str = Depends(require_user)) -> AnalysisJob:
        return get_analysis_job(job_id, user_id)

    @app.get(
        SPEC_BACKTEST_DETAIL_PATH,
        response_model=APIEnvelope,
        tags=["Spec Compatibility"],
    )
    def get_backtest(strategy_id: str, user_id: str = Depends(require_user)) -> APIEnvelope:
        job = _find_job_by_strategy(store, strategy_id, user_id)
        if job and job.result and job.result.user_payload.performance is not None:
            return job.result
        return _not_found_envelope(
            resource_type="backtest",
            resource_id=strategy_id,
            message="No completed analysis job with backtest performance was found.",
        )

    @app.get(
        SPEC_REPORT_DETAIL_PATH,
        tags=["Retired"],
    )
    def get_report(report_id: str) -> None:
        """Keep public report delivery on the backend-owned immutable snapshot path."""

        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "code": "mutable_ai_report_projection_retired",
                "message": "요청형 리포트는 보관된 읽기 전용 스냅샷에서만 제공합니다.",
                "read_only_alternative": "/api/v1/reports",
            },
        )

    @app.post(
        DAILY_DIGEST_PATH,
        tags=["Retired"],
    )
    def create_daily_digest() -> None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "code": "daily_digest_retired",
                "message": "정기 다이제스트 생성은 현재 제공하지 않습니다.",
            },
        )

    return app


def _endpoint_statuses() -> list[EndpointStatus]:
    return [
        EndpointStatus(
            method="GET",
            path=HEALTH_PATH,
            state="available",
            summary="Service health and schema version.",
        ),
        EndpointStatus(
            method="GET",
            path=READINESS_PATH,
            state="readiness",
            summary="Fail-closed durable store, migration, and AI contract admission.",
        ),
        EndpointStatus(
            method="GET",
            path=API_STATUS_PATH,
            state="available",
            summary="Swagger-visible API surface summary.",
        ),
        EndpointStatus(
            method="POST",
            path=ANALYSIS_JOBS_PATH,
            state="local_sync",
            summary="Create and run an analysis job through the local graph.",
        ),
        EndpointStatus(
            method="GET",
            path=ANALYSIS_JOBS_PATH,
            state="job_store",
            summary="List the authenticated user's analysis job history.",
        ),
        EndpointStatus(
            method="GET",
            path=ANALYSIS_JOB_DETAIL_PATH,
            state="job_store",
            summary="Read an analysis job from the configured job store.",
        ),
        EndpointStatus(
            method="POST",
            path=SPEC_STRATEGY_PARSE_PATH,
            state="available",
            summary="Deterministic research-rule review; it never creates an analysis job.",
        ),
        EndpointStatus(
            method="POST",
            path=RESEARCH_JOB_CREATE_PATH,
            state="local_sync",
            summary="Create a job only from a signed research rule when activation is explicitly enabled.",
        ),
        EndpointStatus(
            method="GET",
            path=RESEARCH_JOB_RESULT_PATH,
            state="job_store",
            summary="Read the safe ResearchResultV1 projection for an owned research job.",
        ),
        EndpointStatus(
            method="POST",
            path=STRATEGY_DESCRIPTIONS_PATH,
            state="local_sync",
            summary="Generate concise strategy-only descriptions for FE strategy cards.",
        ),
        EndpointStatus(
            method="GET",
            path=SPEC_ANALYSIS_JOB_DETAIL_PATH,
            state="job_store",
            summary="Compatibility adapter for polling analysis jobs.",
        ),
        EndpointStatus(
            method="GET",
            path=SPEC_BACKTEST_DETAIL_PATH,
            state="job_store",
            summary="MVP adapter returning the latest matching job envelope with backtest performance.",
        ),
        EndpointStatus(
            method="GET",
            path=SPEC_REPORT_DETAIL_PATH,
            state="retired",
            summary="Retired mutable report projection; use backend-owned read-only report snapshots.",
        ),
        EndpointStatus(
            method="POST",
            path=DAILY_DIGEST_PATH,
            state="retired",
            summary="Retired daily digest endpoint; no audit, LLM, or subscription work is available.",
        ),
    ]


def _cors_allow_origins() -> list[str]:
    raw_origins = environ.get(AI_CORS_ALLOW_ORIGINS_ENV, "")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def _research_execution_enabled() -> bool:
    raw = (environ.get(RESEARCH_EXECUTION_ENABLED_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _data_source_status() -> DataSourceStatus:
    dsn_value, dsn_env = resolve_database_dsn_from_env()
    return DataSourceStatus(
        configured=dsn_value is not None,
        dsn_env=dsn_env,
        price_source=KIS_ADJUSTED_OHLCV_TABLE,
        candidate_pool_source=SYMBOL_MASTER_TABLE,
        l4_evidence_source=ANALYST_REPORT_TABLE,
        macro_source=BOK_MACRO_VIEW,
        macro_usable=False,
        fallback_when_unset="fixture",
    )


def _release_readiness(
    runtime: JobStoreRuntime,
    *,
    migration_probe: Callable[[], bool],
    rule_draft_signer: RuleDraftSigner | None,
    provider_ready: bool,
) -> ReadinessResponse:
    durable_store_ready = (
        runtime.requested_mode == PERSISTENT_JOB_STORE_MODE
        and runtime.active_mode == PERSISTENT_JOB_STORE_MODE
        and not runtime.fallback
        and runtime.dsn_configured
    )
    migration_ready = False
    if durable_store_ready:
        try:
            migration_ready = bool(migration_probe())
        except Exception:  # noqa: BLE001 - readiness must not leak dependency internals.
            migration_ready = False
    contract_ready = SCHEMA_VERSION == REQUIRED_AI_CONTRACT_VERSION
    rule_draft_signer_ready = rule_draft_signer is not None
    checks = [
        ReadinessCheck(
            name="durable_job_store",
            ready=durable_store_ready,
            reason=None if durable_store_ready else "durable_job_store_required",
        ),
        ReadinessCheck(
            name="migration_revision",
            ready=migration_ready,
            reason=None if migration_ready else "migration_revision_required",
        ),
        ReadinessCheck(
            name="live_provider_configuration",
            ready=provider_ready,
            reason=None if provider_ready else "live_provider_configuration_required",
        ),
        ReadinessCheck(
            name="ai_contract_version",
            ready=contract_ready,
            reason=None if contract_ready else "ai_contract_version_mismatch",
        ),
        ReadinessCheck(
            name="rule_draft_signer",
            ready=rule_draft_signer_ready,
            reason=None if rule_draft_signer_ready else "rule_draft_signer_required",
        ),
    ]
    return ReadinessResponse(
        status="ready" if all(check.ready for check in checks) else "unavailable",
        ai_contract_version=SCHEMA_VERSION,
        checks=checks,
    )


def _live_provider_configuration_is_ready() -> bool:
    """Check only the presence of the production AOAI configuration.

    Readiness must not instantiate an HTTP client or expose a credential.  The graph's
    live provider factory requires this global fallback trio whenever a role does not
    have a dedicated override, so requiring all three protects every role from silently
    falling back to the local mock provider in a release profile.
    """

    provider = (environ.get(AI_LLM_PROVIDER_ENV) or "mock").strip().lower()
    if provider != "aoai":
        return False
    return all(
        bool((environ.get(key) or "").strip())
        for key in (
            AI_AOAI_RESPONSES_URL_ENV,
            AI_AOAI_API_KEY_ENV,
            AI_AOAI_MODEL_ENV,
        )
    )


def _analysis_jobs_migration_is_current() -> bool:
    """Check the durable-job schema signature without returning connection details."""

    dsn, _ = resolve_database_dsn_from_env()
    if dsn is None:
        return False
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=3) as connection:
            row = connection.execute(
                """
                SELECT
                    to_regclass('app.ai_analysis_job') IS NOT NULL,
                    EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'app'
                          AND table_name = 'ai_analysis_job'
                          AND column_name = 'execution_manifest_schema_version'
                    ),
                    EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'ai_analysis_job_execution_manifest_v1_check'
                          AND conrelid = 'app.ai_analysis_job'::regclass
                    ),
                    EXISTS (
                        SELECT 1
                        FROM pg_class
                        WHERE relname = 'idx_ai_analysis_job_execution_manifest_schema'
                    )
                """
            ).fetchone()
    except Exception:  # noqa: BLE001 - readiness intentionally exposes only a bounded reason.
        return False
    return bool(row and all(row))


def _job_store_runtime(job_store: AnalysisJobStore | None) -> JobStoreRuntime:
    if job_store is None:
        dsn, _ = resolve_database_dsn_from_env()
        repository = PostgresAnalysisJobRepository(dsn) if dsn else None
        return create_analysis_job_store_from_env(
            repository=repository,
            persistent_store_factory=PersistentAnalysisJobStore,
        )
    return JobStoreRuntime(
        store=job_store,
        requested_mode="injected",
        active_mode=getattr(job_store, "store_mode", "injected"),
        fallback=False,
        fallback_reason=None,
        dsn_configured=False,
        mode_env=AI_JOB_STORE_ENV,
    )


def _job_store_status(runtime: JobStoreRuntime) -> JobStoreStatus:
    return JobStoreStatus(
        requested_mode=runtime.requested_mode,
        active_mode=runtime.active_mode,
        mode_env=runtime.mode_env,
        dsn_env=runtime.dsn_env,
        dsn_configured=runtime.dsn_configured,
        fallback=runtime.fallback,
        fallback_reason=runtime.fallback_reason,
    )


def _owned_job(store: AnalysisJobStore, job_id: str, user_id: str) -> AnalysisJob | None:
    job = store.get_job(job_id)
    return job if job is not None and job.user_id == user_id else None


def _find_job_by_strategy(store: AnalysisJobStore, strategy_id: str, user_id: str) -> AnalysisJob | None:
    normalized = strategy_id.strip().lower()
    for job in reversed(store.list_jobs()):
        if job.user_id != user_id:
            continue
        if not job.result or not job.result.strategy_spec:
            continue
        result_strategy_id = job.result.strategy_spec.strategy_id
        if result_strategy_id == normalized or result_strategy_id.startswith(normalized):
            return job
    return None


def _find_job_by_trace_or_debug_ref(store: AnalysisJobStore, value: str, user_id: str) -> AnalysisJob | None:
    normalized = value.strip()
    for job in reversed(store.list_jobs()):
        if job.user_id != user_id:
            continue
        if job.job_id == normalized or job.trace_id == normalized:
            return job
        if job.result and job.result.debug_ref == normalized:
            return job
    return None


def _find_job_by_report_id(store: AnalysisJobStore, report_id: str, user_id: str) -> AnalysisJob | None:
    normalized = report_id.strip()
    for job in reversed(store.list_jobs()):
        if job.user_id != user_id:
            continue
        if getattr(job, "report_id", None) == normalized:
            return job
    return None


def _not_found_envelope(
    *,
    resource_type: str,
    resource_id: str,
    message: str,
) -> APIEnvelope:
    trace_id = f"not-found-{resource_type}"
    return APIEnvelope(
        status=EnvelopeStatus.FAILED,
        trace_id=trace_id,
        user_payload=UserPayload(
            headline=f"{resource_type} not found",
            message=f"{message} resource_id={resource_id}",
            next_actions=["Run POST /api/strategies/parse first.", "Poll the returned analysis job."],
        ),
        strategy_spec=None,
        debug_ref=f"not_found:{resource_type}:{resource_id}",
        retryable=True,
    )


app = create_app()
