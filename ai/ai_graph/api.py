from __future__ import annotations

# pyright: reportUnannotatedClassAttribute=false, reportUnusedFunction=false

from os import environ
from typing import Callable, ClassVar, Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_graph.audit import AuditSession, AuditSink, NoOpAuditSink, create_audit_correlation
from ai_graph.data_sources.db import (
    ANALYST_REPORT_TABLE,
    BOK_MACRO_VIEW,
    KIS_ADJUSTED_OHLCV_TABLE,
    UNIVERSE_VIEW,
    resolve_database_dsn_from_env,
)
from ai_graph.graph import run_analysis
from ai_graph.jobs import (
    AI_JOB_STORE_ENV,
    AnalysisJob,
    AnalysisJobStore,
    AnalysisRunner,
    JobStoreRuntime,
    create_analysis_job_store_from_env,
    run_job_sync,
)
from ai_graph.llm.role_calls import generate_strategy_description
from ai_graph.nodes.daily_digest import MAX_DIGEST_STRATEGIES, build_daily_digest
from ai_graph.schemas import SCHEMA_VERSION
from ai_graph.schemas import APIEnvelope, DailyDigestReport, DailyDigestStrategyInput, EnvelopeStatus, UserPayload

ReportResolver = Callable[[str], APIEnvelope | None]


API_TITLE = "QuantAgent AI API"
API_VERSION = "0.1.0"
API_DESCRIPTION = "Local MVP API surface for QuantAgent analysis jobs."
DOCS_URL = "/docs"
OPENAPI_URL = "/openapi.json"
HEALTH_PATH = "/health"
API_STATUS_PATH = "/api-status"
ANALYSIS_JOBS_PATH = "/analysis-jobs"
ANALYSIS_JOB_DETAIL_PATH = f"{ANALYSIS_JOBS_PATH}/{{job_id}}"
SPEC_STRATEGY_PARSE_PATH = "/api/strategies/parse"
STRATEGY_DESCRIPTIONS_PATH = "/api/strategies/descriptions"
SPEC_ANALYSIS_JOB_DETAIL_PATH = "/api/analysis-jobs/{job_id}"
SPEC_BACKTEST_DETAIL_PATH = "/api/backtests/{strategy_id}"
SPEC_REPORT_DETAIL_PATH = "/api/reports/{report_id}"
DAILY_DIGEST_PATH = "/ai/daily-digest"
AI_CORS_ALLOW_ORIGINS_ENV = "AI_CORS_ALLOW_ORIGINS"
CORS_ALLOW_METHODS = ["GET", "POST", "OPTIONS"]
CORS_ALLOW_HEADERS = ["Authorization", "Content-Type"]


class CreateAnalysisJobRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "query": (
                        "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, "
                        "70 이상이면 팔고 싶어"
                    )
                }
            ]
        },
    )

    query: str = Field(min_length=1)


class ParseStrategyRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    natural_language: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    market: str | None = None
    universe: str | None = None
    strategy_id: str | None = None
    selected_clarification_option_id: str | None = None
    client_request_id: str | None = None

    @model_validator(mode="after")
    def require_query_text(self) -> "ParseStrategyRequest":
        if not self.request_text:
            raise ValueError("natural_language or query is required")
        return self

    @property
    def request_text(self) -> str:
        return (self.natural_language or self.query or "").strip()


class CreateDailyDigestRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    user_name: str = Field(min_length=1)
    report_date: str = Field(min_length=1)
    strategies: list[DailyDigestStrategyInput] = Field(min_length=1, max_length=MAX_DIGEST_STRATEGIES)


class StrategyDescriptionInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    universe: str = Field(min_length=1)
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


class EndpointStatus(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    method: Literal["GET", "POST"]
    path: str
    state: Literal["available", "local_sync", "job_store"]
    summary: str


class DataSourceStatus(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    configured: bool
    dsn_env: str
    price_source: str
    universe_source: str
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

    def runner(query: str, trace_id: str) -> APIEnvelope:
        _record_step(session, "job_dispatched", message="analysis request dispatched")
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
        _record_step(session, "analysis_completed", message=f"analysis runner returned status={status_label}")
        _record_finalization(
            session,
            "failed" if envelope.status == EnvelopeStatus.FAILED else "completed",
            message=f"analysis runner completed with status={status_label}",
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
    sink = audit_sink or NoOpAuditSink()
    try:
        return sink.open_session(correlation)
    except Exception:
        return NoOpAuditSink().open_session(correlation)


def _record_step(session: AuditSession, step: str, *, message: str | None = None) -> None:
    try:
        session.record_step(step, message=message)
    except Exception:
        return None


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
        return None


def _record_finalization(session: AuditSession, status: str, *, message: str | None = None) -> None:
    try:
        session.record_finalization(status, message=message)
    except Exception:
        return None


def create_app(
    job_store: AnalysisJobStore | None = None,
    *,
    analysis_runner: AnalysisRunner = run_analysis,
    job_store_runtime: JobStoreRuntime | None = None,
    audit_sink: AuditSink | None = None,
    report_resolver: ReportResolver | None = None,
) -> FastAPI:
    runtime = job_store_runtime or _job_store_runtime(job_store)
    store = runtime.store
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
    app.state.audit_sink = audit_sink or NoOpAuditSink()
    app.state.report_resolver = report_resolver

    @app.get(HEALTH_PATH, response_model=HealthResponse, tags=["System"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", schema_version=SCHEMA_VERSION)

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
    )
    def create_analysis_job(request: CreateAnalysisJobRequest) -> AnalysisJob:
        job = store.create_job(request.query)
        return run_job_sync(
            store,
            job.job_id,
            _build_analysis_runner_with_audit(
                analysis_runner,
                audit_sink=app.state.audit_sink,
                trace_id=job.trace_id,
                entrypoint="api.analysis_jobs",
                feature="analysis_job",
            ),
        )

    @app.post(
        SPEC_STRATEGY_PARSE_PATH,
        response_model=AnalysisJob,
        status_code=status.HTTP_201_CREATED,
        tags=["Spec Compatibility"],
    )
    def parse_strategy(request: ParseStrategyRequest) -> AnalysisJob:
        job = store.create_job(
            request.request_text,
            strategy_id=request.strategy_id,
            run_id=request.client_request_id,
        )
        return run_job_sync(
            store,
            job.job_id,
            _build_analysis_runner_with_audit(
                analysis_runner,
                audit_sink=app.state.audit_sink,
                trace_id=job.trace_id,
                entrypoint="api.strategy_parse",
                feature="strategy_parse",
                strategy_id=request.strategy_id,
                client_request_id=request.client_request_id,
            ),
        )

    @app.post(
        STRATEGY_DESCRIPTIONS_PATH,
        response_model=StrategyDescriptionsResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Strategy"],
    )
    def describe_strategies(request: StrategyDescriptionsRequest) -> StrategyDescriptionsResponse:
        session = _open_request_audit_session(
            app.state.audit_sink,
            trace_id=None,
            entrypoint="api.strategy_descriptions",
            feature="strategy_descriptions",
        )
        _record_step(session, "descriptions_started", message=f"strategy_count={len(request.strategies)}")
        try:
            items: list[StrategyDescriptionItem] = []
            for strategy in request.strategies:
                payload = generate_strategy_description(
                    strategy_id=strategy.strategy_id,
                    name=strategy.name,
                    universe=strategy.universe,
                    timeframe=strategy.timeframe,
                    entry_summary=strategy.entry_summary,
                    exit_summary=strategy.exit_summary,
                    risk_summary=strategy.risk_summary,
                    tags=strategy.tags,
                    fallback=(
                        f"{strategy.universe} 내에서 {strategy.entry_summary} 조건이 맞는 종목을 선별하고 "
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
    def get_analysis_job(job_id: str) -> AnalysisJob:
        job = store.get_job(job_id)
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
    def get_spec_analysis_job(job_id: str) -> AnalysisJob:
        return get_analysis_job(job_id)

    @app.get(
        SPEC_BACKTEST_DETAIL_PATH,
        response_model=APIEnvelope,
        tags=["Spec Compatibility"],
    )
    def get_backtest(strategy_id: str) -> APIEnvelope:
        job = _find_job_by_strategy(store, strategy_id)
        if job and job.result and job.result.user_payload.performance is not None:
            return job.result
        return _not_found_envelope(
            resource_type="backtest",
            resource_id=strategy_id,
            message="No completed analysis job with backtest performance was found.",
        )

    @app.get(
        SPEC_REPORT_DETAIL_PATH,
        response_model=APIEnvelope,
        tags=["Spec Compatibility"],
    )
    def get_report(report_id: str) -> APIEnvelope:
        job = (
            store.get_job(report_id)
            or _find_job_by_report_id(store, report_id)
            or _find_job_by_trace_or_debug_ref(store, report_id)
        )
        if job and job.result and job.result.user_payload.report is not None:
            return job.result
        resolver = app.state.report_resolver
        if resolver is not None:
            resolved = resolver(report_id)
            if resolved is not None and resolved.user_payload.report is not None:
                return resolved
        return _not_found_envelope(
            resource_type="report",
            resource_id=report_id,
            message="No completed analysis job with report projection was found.",
        )

    @app.post(
        DAILY_DIGEST_PATH,
        response_model=DailyDigestReport,
        status_code=status.HTTP_201_CREATED,
        tags=["Daily Digest"],
    )
    def create_daily_digest(request: CreateDailyDigestRequest) -> DailyDigestReport:
        session = _open_request_audit_session(
            app.state.audit_sink,
            trace_id=None,
            entrypoint="api.daily_digest",
            feature="daily_digest",
        )
        _record_step(session, "daily_digest_started", message=f"strategy_count={len(request.strategies)}")
        try:
            report = build_daily_digest(
                request.strategies,
                user_name=request.user_name,
                report_date=request.report_date,
            )
        except ValueError as exc:
            _record_error(
                session,
                "daily_digest_validation",
                error_type="ValueError",
                message="ValueError raised during daily digest generation",
            )
            _record_finalization(session, "failed", message="daily digest generation failed")
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except Exception as exc:
            _record_error(
                session,
                "daily_digest_generation",
                error_type=type(exc).__name__,
                message=f"{type(exc).__name__} raised during daily digest generation",
            )
            _record_finalization(session, "failed", message="daily digest generation failed")
            raise
        for card in report.strategy_cards:
            _record_step(
                session,
                "daily_digest_card_ready",
                message=f"strategy_id={card.strategy_id} today_signal={card.today_signal}",
            )
        _record_step(
            session,
            "daily_digest_market_brief",
            message=f"fallback_used={'true' if report.market_brief.fallback_reasons else 'false'}",
        )
        _record_finalization(session, "completed", message=f"generated daily digest for {len(report.strategy_cards)} strategies")
        return report

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
            path=ANALYSIS_JOB_DETAIL_PATH,
            state="job_store",
            summary="Read an analysis job from the configured job store.",
        ),
        EndpointStatus(
            method="POST",
            path=SPEC_STRATEGY_PARSE_PATH,
            state="local_sync",
            summary="Compatibility adapter for POST /api/strategies/parse.",
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
            state="job_store",
            summary="MVP adapter returning the latest matching job envelope with report projection.",
        ),
        EndpointStatus(
            method="POST",
            path=DAILY_DIGEST_PATH,
            state="local_sync",
            summary="Compose the up-to-3-strategy daily email digest (comparison table, cards, AI comment, market brief).",
        ),
    ]


def _cors_allow_origins() -> list[str]:
    raw_origins = environ.get(AI_CORS_ALLOW_ORIGINS_ENV, "")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def _data_source_status() -> DataSourceStatus:
    dsn_value, dsn_env = resolve_database_dsn_from_env()
    return DataSourceStatus(
        configured=dsn_value is not None,
        dsn_env=dsn_env,
        price_source=KIS_ADJUSTED_OHLCV_TABLE,
        universe_source=UNIVERSE_VIEW,
        l4_evidence_source=ANALYST_REPORT_TABLE,
        macro_source=BOK_MACRO_VIEW,
        macro_usable=False,
        fallback_when_unset="fixture",
    )


def _job_store_runtime(job_store: AnalysisJobStore | None) -> JobStoreRuntime:
    if job_store is None:
        return create_analysis_job_store_from_env()
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


def _find_job_by_strategy(store: AnalysisJobStore, strategy_id: str) -> AnalysisJob | None:
    normalized = strategy_id.strip().lower()
    for job in reversed(store.list_jobs()):
        if not job.result or not job.result.strategy_spec:
            continue
        result_strategy_id = job.result.strategy_spec.strategy_id
        if result_strategy_id == normalized or result_strategy_id.startswith(normalized):
            return job
    return None


def _find_job_by_trace_or_debug_ref(store: AnalysisJobStore, value: str) -> AnalysisJob | None:
    normalized = value.strip()
    for job in reversed(store.list_jobs()):
        if job.job_id == normalized or job.trace_id == normalized:
            return job
        if job.result and job.result.debug_ref == normalized:
            return job
    return None


def _find_job_by_report_id(store: AnalysisJobStore, report_id: str) -> AnalysisJob | None:
    normalized = report_id.strip()
    for job in reversed(store.list_jobs()):
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
