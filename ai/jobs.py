from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ai_graph.graph import public_response, run_quantagent
from ai_graph.schemas import JobRecord, JobStatus


class InMemoryJobStore:
    def __init__(self) -> None:
        self._records: dict[str, JobRecord] = {}

    def submit(self, user_input: str) -> JobRecord:
        job_id = f"job_{uuid4().hex}"
        running = JobRecord(
            job_id=job_id,
            status=JobStatus.RUNNING,
            trace_id=f"trc_{uuid4().hex}",
            debug_ref=f"dbg_{job_id[-12:]}",
        )
        self._records[job_id] = running

        try:
            state = run_quantagent(user_input)
            completed = running.model_copy(
                update={
                    "status": JobStatus.SUCCEEDED,
                    "trace_id": state["trace_id"],
                    "debug_ref": state["debug_ref"],
                    "updated_at": datetime.now(UTC),
                    "result": public_response(state),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive job boundary
            completed = running.model_copy(
                update={
                    "status": JobStatus.FAILED,
                    "updated_at": datetime.now(UTC),
                    "error": str(exc),
                }
            )
        self._records[job_id] = completed
        return completed

    def get(self, job_id: str) -> JobRecord | None:
        return self._records.get(job_id)


DEFAULT_JOB_STORE = InMemoryJobStore()


def submit_job(user_input: str, store: InMemoryJobStore | None = None) -> JobRecord:
    return (store or DEFAULT_JOB_STORE).submit(user_input)


def get_job(job_id: str, store: InMemoryJobStore | None = None) -> JobRecord | None:
    return (store or DEFAULT_JOB_STORE).get(job_id)
