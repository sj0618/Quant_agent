-- Canonical natural-language strategy admission: no raw prompt is needed once parse
-- has issued a signed token.  The tables are additive so V1 job readers remain valid
-- during the expand phase.

BEGIN;

CREATE TABLE IF NOT EXISTS app.ai_parse_token (
    nonce_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    spec_version TEXT NOT NULL,
    spec_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_parse_token_nonce_hash_sha256
        CHECK (nonce_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_ai_parse_token_spec_hash_sha256
        CHECK (spec_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_ai_parse_token_version_not_blank
        CHECK (length(trim(spec_version)) > 0),
    CONSTRAINT ck_ai_parse_token_expiry_after_create
        CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_ai_parse_token_expiry
    ON app.ai_parse_token (expires_at)
    WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS app.ai_analysis_job_idempotency (
    user_id TEXT NOT NULL,
    client_idempotency_key TEXT NOT NULL,
    spec_hash TEXT NOT NULL,
    job_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, client_idempotency_key),
    CONSTRAINT fk_ai_analysis_job_idempotency_job
        FOREIGN KEY (job_id)
        REFERENCES app.ai_analysis_job(job_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_ai_analysis_job_idempotency_spec_hash_sha256
        CHECK (spec_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_ai_analysis_job_idempotency_key_not_blank
        CHECK (length(trim(client_idempotency_key)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_idempotency_job
    ON app.ai_analysis_job_idempotency (job_id);

CREATE TABLE IF NOT EXISTS app.ai_analysis_job_outbox (
    outbox_id UUID PRIMARY KEY,
    job_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_jsonb JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    CONSTRAINT fk_ai_analysis_job_outbox_job
        FOREIGN KEY (job_id)
        REFERENCES app.ai_analysis_job(job_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_ai_analysis_job_outbox_event_type
        CHECK (event_type = 'analysis_job.created.v1'),
    CONSTRAINT ck_ai_analysis_job_outbox_status
        CHECK (status IN ('pending', 'claimed', 'delivered', 'failed')),
    CONSTRAINT ck_ai_analysis_job_outbox_payload_object
        CHECK (jsonb_typeof(payload_jsonb) = 'object'),
    CONSTRAINT uq_ai_analysis_job_outbox_created_event
        UNIQUE (job_id, event_type)
);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_outbox_pending
    ON app.ai_analysis_job_outbox (status, created_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_outbox_claim_lease
    ON app.ai_analysis_job_outbox (status, claimed_at)
    WHERE status = 'claimed';

COMMENT ON TABLE app.ai_parse_token IS
    'Opaque parse nonce digests bound to one user and versioned execution spec; raw natural language is never stored here.';
COMMENT ON TABLE app.ai_analysis_job_idempotency IS
    'Per-user client retry key bound to one canonical spec hash and durable job.';
COMMENT ON TABLE app.ai_analysis_job_outbox IS
    'Transactional analysis-job dispatch records; payload is limited to identifiers and canonical spec identity.';

COMMIT;
