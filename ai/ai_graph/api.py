from __future__ import annotations

# pyright: reportUnannotatedClassAttribute=false, reportUnusedFunction=false

from os import environ
from typing import ClassVar, Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from ai_graph.data_sources.db import (
    ANALYST_REPORT_TABLE,
    AI_DATABASE_DSN_ENV,
    BOK_MACRO_VIEW,
    DataSourceConfig,
    KIS_FEATURE_FRAME_VIEW,
    UNIVERSE_VIEW,
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
from ai_graph.schemas import SCHEMA_VERSION


API_TITLE = "QuantAgent AI API"
API_VERSION = "0.1.0"
API_DESCRIPTION = "Local MVP API surface for QuantAgent analysis jobs."
DOCS_URL = "/docs"
OPENAPI_URL = "/openapi.json"
HEALTH_PATH = "/health"
API_STATUS_PATH = "/api-status"
ANALYSIS_JOBS_PATH = "/analysis-jobs"
ANALYSIS_JOB_DETAIL_PATH = f"{ANALYSIS_JOBS_PATH}/{{job_id}}"
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


def create_app(
    job_store: AnalysisJobStore | None = None,
    *,
    analysis_runner: AnalysisRunner = run_analysis,
    job_store_runtime: JobStoreRuntime | None = None,
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
        return run_job_sync(store, job.job_id, analysis_runner)

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
    ]


def _cors_allow_origins() -> list[str]:
    raw_origins = environ.get(AI_CORS_ALLOW_ORIGINS_ENV, "")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def _data_source_status() -> DataSourceStatus:
    config = DataSourceConfig.from_env()
    return DataSourceStatus(
        configured=config.database_dsn is not None,
        dsn_env=AI_DATABASE_DSN_ENV,
        price_source=KIS_FEATURE_FRAME_VIEW,
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


app = create_app()
