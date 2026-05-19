from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.schemas import APIEnvelope, Stage, StageStatus


class StageProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Stage
    status: StageStatus
    updated_at: datetime
    message: str | None = None


class AnalysisJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    stages: list[StageProgress]
    result: APIEnvelope | None = None


@dataclass
class InMemoryAnalysisJobStore:
    jobs: dict[str, AnalysisJob] = field(default_factory=dict)

    def create(self, query: str) -> AnalysisJob:
        now = datetime.now(UTC)
        trace_id = sha256(f"{query}:{now.isoformat()}".encode("utf-8")).hexdigest()[:16]
        job = AnalysisJob(
            job_id=f"job_{uuid4().hex[:12]}",
            trace_id=trace_id,
            query=query,
            created_at=now,
            updated_at=now,
            stages=[
                StageProgress(stage=stage, status=StageStatus.QUEUED, updated_at=now)
                for stage in Stage
            ],
        )
        self.jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> AnalysisJob | None:
        return self.jobs.get(job_id)

    def run_sync(self, job_id: str, runner: Callable[[str, str], APIEnvelope]) -> AnalysisJob:
        job = self.jobs[job_id]
        now = datetime.now(UTC)
        running = [
            StageProgress(stage=stage.stage, status=StageStatus.RUNNING, updated_at=now)
            for stage in job.stages
        ]
        job = job.model_copy(update={"stages": running, "updated_at": now})
        self.jobs[job_id] = job
        result = runner(job.query, job.trace_id)
        finished_at = datetime.now(UTC)
        succeeded = [
            StageProgress(stage=stage.stage, status=StageStatus.SUCCEEDED, updated_at=finished_at)
            for stage in job.stages
        ]
        job = job.model_copy(
            update={"stages": succeeded, "updated_at": finished_at, "result": result}
        )
        self.jobs[job_id] = job
        return job
