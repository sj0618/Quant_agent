-- Durable AI job state. The full public job envelope lives in one JSONB document so
-- the AI API and report completion path share one authoritative result.

CREATE TABLE IF NOT EXISTS app.ai_analysis_job (
    job_id TEXT PRIMARY KEY,
    user_id TEXT,
    job_jsonb JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

-- The canonical job document is also the atomic execution ledger.  Its versioned
-- manifest intentionally contains only identifiers, policy hashes, timestamps,
-- quantities, reasons, and cost components: never DSNs, credentials, or provider secrets.
ALTER TABLE app.ai_analysis_job
    ADD COLUMN IF NOT EXISTS execution_manifest_schema_version TEXT
        GENERATED ALWAYS AS (job_jsonb #>> '{execution_manifest,schema_version}') STORED;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ai_analysis_job_execution_manifest_v1_check'
          AND conrelid = 'app.ai_analysis_job'::regclass
    ) THEN
        ALTER TABLE app.ai_analysis_job
            ADD CONSTRAINT ai_analysis_job_execution_manifest_v1_check CHECK (
                jsonb_typeof(job_jsonb -> 'execution_manifest') = 'object'
                AND job_jsonb #>> '{execution_manifest,schema_version}' = '1'
                AND job_jsonb #>> '{execution_manifest,contract_hash}' ~ '^[0-9a-f]{64}$'
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,run_identity}') = 'object'
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,policy_hashes}') = 'object'
                AND job_jsonb #> '{execution_manifest,policy_hashes}' <> '{}'::jsonb
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,session}') = 'object'
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,capabilities}') = 'object'
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,events,signals}') = 'array'
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,events,orders}') = 'array'
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,events,fills}') = 'array'
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,events,positions}') = 'array'
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,events,trades}') = 'array'
                AND jsonb_typeof(job_jsonb #> '{execution_manifest,events,equity}') = 'array'
            ) NOT VALID;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_execution_manifest_schema
    ON app.ai_analysis_job (execution_manifest_schema_version);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_user_updated
    ON app.ai_analysis_job (user_id, updated_at DESC);
