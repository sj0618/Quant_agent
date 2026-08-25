-- Retire the analysis-job rows this build can no longer read, and stop the table
-- from accepting another one.
--
-- `execution_manifest` and the `availability` tag the public performance union
-- discriminates on were added to the job document without backfilling the rows already
-- in the table, so a row written by an older build never validates again.  Migration 021
-- grandfathered them: it added its manifest CHECK `NOT VALID`, which leaves existing rows
-- unchecked.  The application then had to carry the damage at runtime - the history list
-- drops undecodable rows with a warning, and restart reconciliation force-settles
-- undecodable active rows - and those tolerances kept three separate deploys from dying,
-- but they never repaired anything.  The rows are still there and still unreadable.
--
-- Their provenance cannot be reconstructed: the manifest CHECK wants a contract hash, run
-- identity, policy hashes, and six event arrays that were never recorded for these jobs.
-- Synthesizing them would put fiction in an audit ledger.  So the rows are moved to an
-- unconstrained archive instead, and the live table is closed against new ones.
--
-- This migration therefore DELETEs, unlike its additive predecessors.  Every deleted row
-- is inserted into app.ai_analysis_job_legacy by the same statement that deletes it, so
-- the two cannot diverge.
--
-- Every jsonb_typeof test below is COALESCEd. A missing key makes `jsonb_typeof` return
-- SQL NULL, an `= 'object'` test on it returns NULL rather than false, and both a CHECK
-- and a plain `NOT` treat NULL as acceptable.  That is precisely how 021's constraint came
-- to admit the manifest-less rows it was written to forbid: it still accepts one today,
-- not only historically.  Two-valued predicates here, plus `IS TRUE` / `IS NOT TRUE` at
-- the boundary, so neither the move nor the constraint can be fooled by an absent key.

CREATE TABLE IF NOT EXISTS app.ai_analysis_job_legacy (
    job_id TEXT PRIMARY KEY,
    user_id TEXT,
    job_jsonb JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    archived_at TIMESTAMPTZ NOT NULL,
    archive_reason TEXT NOT NULL
);

COMMENT ON TABLE app.ai_analysis_job_legacy IS
    'Analysis job documents written before the execution-manifest and performance-availability '
    'contracts. Deliberately unconstrained: these documents are kept verbatim as written and are '
    'never decoded, repaired, or served.';

-- The predicate below is the exact negation of the CHECK added further down, so a row can
-- never both survive the move and fail the constraint.
WITH moved AS (
    DELETE FROM app.ai_analysis_job
    WHERE (
        COALESCE(jsonb_typeof(job_jsonb -> 'execution_manifest'), 'absent') = 'object'
        AND job_jsonb #>> '{execution_manifest,schema_version}' = '1'
        AND job_jsonb #>> '{execution_manifest,contract_hash}' ~ '^[0-9a-f]{64}$'
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,run_identity}'), 'absent') = 'object'
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,policy_hashes}'), 'absent') = 'object'
        AND job_jsonb #> '{execution_manifest,policy_hashes}' <> '{}'::jsonb
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,session}'), 'absent') = 'object'
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,capabilities}'), 'absent') = 'object'
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,signals}'), 'absent') = 'array'
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,orders}'), 'absent') = 'array'
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,fills}'), 'absent') = 'array'
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,positions}'), 'absent') = 'array'
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,trades}'), 'absent') = 'array'
        AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,equity}'), 'absent') = 'array'
        AND (
            COALESCE(jsonb_typeof(job_jsonb #> '{result,performance}'), 'absent') <> 'object'
            OR job_jsonb #>> '{result,performance,availability}' IN ('available', 'unavailable')
        )
    ) IS NOT TRUE
    RETURNING job_id, user_id, job_jsonb, created_at, updated_at
)
INSERT INTO app.ai_analysis_job_legacy AS legacy (
    job_id, user_id, job_jsonb, created_at, updated_at, archived_at, archive_reason
)
SELECT
    job_id,
    user_id,
    job_jsonb,
    created_at,
    updated_at,
    now(),
    CASE
        WHEN COALESCE(jsonb_typeof(job_jsonb -> 'execution_manifest'), 'absent') <> 'object'
            THEN 'missing_execution_manifest'
        WHEN COALESCE(jsonb_typeof(job_jsonb #> '{result,performance}'), 'absent') = 'object'
            AND COALESCE(job_jsonb #>> '{result,performance,availability}', '')
                NOT IN ('available', 'unavailable')
            THEN 'missing_performance_availability'
        ELSE 'incomplete_execution_manifest'
    END
FROM moved
-- A re-run finds nothing to move, so this fires only if a job id were archived and then
-- written again. Keep the newer document rather than discarding either one.
ON CONFLICT (job_id) DO UPDATE
    SET job_jsonb = EXCLUDED.job_jsonb,
        user_id = EXCLUDED.user_id,
        updated_at = EXCLUDED.updated_at,
        archived_at = EXCLUDED.archived_at,
        archive_reason = EXCLUDED.archive_reason
    WHERE legacy.updated_at <= EXCLUDED.updated_at;

-- Close the table. This CHECK is created VALID: it scans what is left, so the migration
-- fails here rather than silently leaving behind a row the application cannot read.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ai_analysis_job_decodable_document_check'
          AND conrelid = 'app.ai_analysis_job'::regclass
    ) THEN
        ALTER TABLE app.ai_analysis_job
            ADD CONSTRAINT ai_analysis_job_decodable_document_check CHECK ((
                COALESCE(jsonb_typeof(job_jsonb -> 'execution_manifest'), 'absent') = 'object'
                AND job_jsonb #>> '{execution_manifest,schema_version}' = '1'
                AND job_jsonb #>> '{execution_manifest,contract_hash}' ~ '^[0-9a-f]{64}$'
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,run_identity}'), 'absent') = 'object'
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,policy_hashes}'), 'absent') = 'object'
                AND job_jsonb #> '{execution_manifest,policy_hashes}' <> '{}'::jsonb
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,session}'), 'absent') = 'object'
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,capabilities}'), 'absent') = 'object'
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,signals}'), 'absent') = 'array'
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,orders}'), 'absent') = 'array'
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,fills}'), 'absent') = 'array'
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,positions}'), 'absent') = 'array'
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,trades}'), 'absent') = 'array'
                AND COALESCE(jsonb_typeof(job_jsonb #> '{execution_manifest,events,equity}'), 'absent') = 'array'
                AND (
                    COALESCE(jsonb_typeof(job_jsonb #> '{result,performance}'), 'absent') <> 'object'
                    OR job_jsonb #>> '{result,performance,availability}' IN ('available', 'unavailable')
                )
            ) IS TRUE);
    END IF;
END $$;

-- End 021's grandfathering now that nothing is left for it to grandfather.
ALTER TABLE app.ai_analysis_job
    VALIDATE CONSTRAINT ai_analysis_job_execution_manifest_v1_check;
