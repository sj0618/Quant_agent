-- Reverse of 024. Purely additive migration, so the reversal only drops what it added.
-- The outbox table is dropped rather than emptied: an event nobody published is not
-- history worth keeping, and leaving the table would leave its foreign key pointing at
-- a job table that no longer has the columns the executor needed.

DROP INDEX IF EXISTS app.idx_ai_analysis_job_outbox_unpublished;
DROP TABLE IF EXISTS app.ai_analysis_job_outbox;

DROP INDEX IF EXISTS app.idx_ai_analysis_job_lease_expiry;
DROP INDEX IF EXISTS app.uq_ai_analysis_job_owner_idempotency;

ALTER TABLE app.ai_analysis_job
    DROP CONSTRAINT IF EXISTS ck_ai_analysis_job_spec_hash_sha256,
    DROP CONSTRAINT IF EXISTS ck_ai_analysis_job_lease_pairing,
    DROP CONSTRAINT IF EXISTS ck_ai_analysis_job_fencing_token_monotonic,
    DROP CONSTRAINT IF EXISTS ck_ai_analysis_job_version_positive;

ALTER TABLE app.ai_analysis_job
    DROP COLUMN IF EXISTS spec_hash,
    DROP COLUMN IF EXISTS idempotency_key,
    DROP COLUMN IF EXISTS fencing_token,
    DROP COLUMN IF EXISTS lease_expires_at,
    DROP COLUMN IF EXISTS lease_owner,
    DROP COLUMN IF EXISTS version;
