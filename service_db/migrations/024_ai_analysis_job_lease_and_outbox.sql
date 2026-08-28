-- Give the analysis job table the columns a durable, restart-safe executor needs:
-- an optimistic version for compare-and-swap, a lease so a dead owner can be told from
-- a busy one, a fencing token so a late writer cannot overwrite a newer one, an
-- idempotency key, and a transactional outbox.
--
-- Why CAS. Every write path in PostgresAnalysisJobRepository is read-modify-write:
-- it loads the row, applies the transition in memory, then INSERT ... ON CONFLICT DO
-- UPDATE with no predicate. Two writers therefore silently lose one of the two
-- transitions. `version` turns that into a detectable conflict.
--
-- Why the lease is separate from owner_incarnation. The existing claim rule is
-- `owner_incarnation != mine`, which has no way to distinguish a dead owner from a
-- live sibling: the reaper would settle a job another worker is actively running.
-- That is safe today only because enforce_single_process refuses a second worker.
-- A lease with an expiry makes the distinction explicit instead of implicit.
--
-- Why idempotency_key is not spec_hash. Running the same strategy twice on purpose is
-- ordinary use, so the content of the request must never be what suppresses the second
-- run. Only an explicit client-supplied key does. Both are stored; only the key is
-- unique.
--
-- Additive and idempotent. No row is deleted and no existing column changes type.

ALTER TABLE app.ai_analysis_job
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS lease_owner TEXT,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS fencing_token BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
    ADD COLUMN IF NOT EXISTS spec_hash TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_ai_analysis_job_version_positive'
          AND conrelid = 'app.ai_analysis_job'::regclass
    ) THEN
        ALTER TABLE app.ai_analysis_job
            ADD CONSTRAINT ck_ai_analysis_job_version_positive CHECK (version >= 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_ai_analysis_job_fencing_token_monotonic'
          AND conrelid = 'app.ai_analysis_job'::regclass
    ) THEN
        ALTER TABLE app.ai_analysis_job
            ADD CONSTRAINT ck_ai_analysis_job_fencing_token_monotonic CHECK (fencing_token >= 0);
    END IF;

    -- A lease owner without an expiry never expires, which is the exact failure the
    -- lease exists to prevent. Both fields move together or not at all.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_ai_analysis_job_lease_pairing'
          AND conrelid = 'app.ai_analysis_job'::regclass
    ) THEN
        ALTER TABLE app.ai_analysis_job
            ADD CONSTRAINT ck_ai_analysis_job_lease_pairing CHECK (
                (lease_owner IS NULL AND lease_expires_at IS NULL)
                OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_ai_analysis_job_spec_hash_sha256'
          AND conrelid = 'app.ai_analysis_job'::regclass
    ) THEN
        ALTER TABLE app.ai_analysis_job
            ADD CONSTRAINT ck_ai_analysis_job_spec_hash_sha256 CHECK (
                spec_hash IS NULL OR spec_hash ~ '^[0-9a-f]{64}$'
            );
    END IF;
END $$;

-- Partial so the pre-existing rows, which have no key, do not all collide on NULL.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_analysis_job_owner_idempotency
    ON app.ai_analysis_job (user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_lease_expiry
    ON app.ai_analysis_job (lease_expires_at)
    WHERE lease_expires_at IS NOT NULL;

-- Transactional outbox. A row is written in the same transaction that creates or
-- settles the job, so an observer can never see a job without its event or an event
-- without its job.
CREATE TABLE IF NOT EXISTS app.ai_analysis_job_outbox (
    outbox_id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_jsonb JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_analysis_job_outbox_job'
          AND conrelid = 'app.ai_analysis_job_outbox'::regclass
    ) THEN
        ALTER TABLE app.ai_analysis_job_outbox
            ADD CONSTRAINT fk_ai_analysis_job_outbox_job
            FOREIGN KEY (job_id) REFERENCES app.ai_analysis_job (job_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_ai_analysis_job_outbox_payload_object'
          AND conrelid = 'app.ai_analysis_job_outbox'::regclass
    ) THEN
        ALTER TABLE app.ai_analysis_job_outbox
            ADD CONSTRAINT ck_ai_analysis_job_outbox_payload_object CHECK (
                jsonb_typeof(payload_jsonb) = 'object'
            );
    END IF;
END $$;

-- The publisher reads only what it has not published yet.
CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_outbox_unpublished
    ON app.ai_analysis_job_outbox (created_at)
    WHERE published_at IS NULL;
