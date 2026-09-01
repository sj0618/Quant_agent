"""Allow-listed immutable-result evidence for isolated staging acceptance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ImmutableResultEvidence:
    """Small operator projection; prompt, response, and credential bodies stay in the DB."""

    job_id: str
    execution_spec_version: str
    execution_spec_hash: str
    analysis_result_id: str
    manifest_hash: str
    source: str
    as_of: str
    observations: int
    candidate_count: int
    successful_aoai_calls: int
    immutable_trigger_present: bool


def read_immutable_result_evidence(
    connection: Any, job_id: str
) -> ImmutableResultEvidence | None:
    """Read only the immutable result link and audit count required by the staging gate."""

    row = connection.execute(
        """
        SELECT
            job.job_id,
            job.job_jsonb ->> 'execution_spec_version' AS execution_spec_version,
            job.job_jsonb ->> 'execution_spec_hash' AS execution_spec_hash,
            job.analysis_result_id::text AS analysis_result_id,
            result.manifest_hash,
            result.data_manifest_jsonb #>> '{freshnessEvidence,source}' AS source,
            result.data_manifest_jsonb #>> '{freshnessEvidence,as_of}' AS as_of,
            result.data_manifest_jsonb #>> '{methodManifest,observations}' AS observations,
            result.data_manifest_jsonb #>> '{candidateCount}' AS candidate_count,
            (
                SELECT COUNT(*)
                FROM app.ai_model_call_log AS model_call
                JOIN app.ai_trace AS audit_trace ON audit_trace.trace_id = model_call.trace_id
                WHERE audit_trace.metadata_jsonb ->> 'public_trace_id' = job.job_jsonb ->> 'trace_id'
                  AND lower(model_call.provider) = 'aoai'
                  AND model_call.status = 'succeeded'
            ) AS successful_aoai_calls,
            EXISTS (
                SELECT 1
                FROM pg_trigger
                WHERE tgname = 'trg_analysis_result_immutable'
                  AND tgrelid = 'app.analysis_result'::regclass
            ) AS immutable_trigger_present
        FROM app.ai_analysis_job AS job
        JOIN app.analysis_result AS result ON result.analysis_result_id = job.analysis_result_id
        WHERE job.job_id = %s
        LIMIT 1
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return ImmutableResultEvidence(
            job_id=str(row["job_id"]),
            execution_spec_version=str(row["execution_spec_version"]),
            execution_spec_hash=str(row["execution_spec_hash"]),
            analysis_result_id=str(row["analysis_result_id"]),
            manifest_hash=str(row["manifest_hash"]),
            source=str(row["source"]),
            as_of=str(row["as_of"]),
            observations=int(row["observations"]),
            candidate_count=int(row["candidate_count"]),
            successful_aoai_calls=int(row["successful_aoai_calls"]),
            immutable_trigger_present=bool(row["immutable_trigger_present"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("immutable result evidence has an invalid shape") from exc
