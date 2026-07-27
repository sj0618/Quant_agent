-- Queue state for asynchronous email delivery.
-- Completed delivery results continue to be stored in
-- app.email_delivery_history.

BEGIN;

CREATE TABLE IF NOT EXISTS app.email_delivery_outbox (
    delivery_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id bigint NOT NULL,
    report_id text NOT NULL,
    strategy_id text,
    recipient_email text NOT NULL,
    template_key text NOT NULL,
    template_version text DEFAULT 'v1'::text NOT NULL,
    payload_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    idempotency_key text NOT NULL,
    status text DEFAULT 'PENDING'::text NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    next_attempt_at timestamptz DEFAULT now() NOT NULL,
    claimed_by text,
    claim_token uuid,
    claim_expires_at timestamptz,
    provider text,
    provider_message_id text,
    last_error_code text,
    last_error_message text,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    sent_at timestamptz,
    cancelled_at timestamptz,
    PRIMARY KEY (delivery_id),
    CONSTRAINT email_delivery_outbox_idempotency_key_key
        UNIQUE (idempotency_key),
    CONSTRAINT email_delivery_outbox_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES app.users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT email_delivery_outbox_report_id_fkey
        FOREIGN KEY (report_id)
        REFERENCES app.strategy_email_report(report_id)
        ON DELETE CASCADE,
    CONSTRAINT email_delivery_outbox_strategy_id_fkey
        FOREIGN KEY (strategy_id)
        REFERENCES app.strategy_report_profile(strategy_id)
        ON DELETE SET NULL,
    CONSTRAINT email_delivery_outbox_status_check
        CHECK (
            status = ANY (
                ARRAY[
                    'PENDING'::text,
                    'PROCESSING'::text,
                    'RETRY_PENDING'::text,
                    'SENT'::text,
                    'FAILED'::text,
                    'CANCELLED'::text
                ]
            )
        ),
    CONSTRAINT email_delivery_outbox_attempt_count_check
        CHECK (
            attempt_count >= 0
            AND max_attempts > 0
            AND attempt_count <= max_attempts
        ),
    CONSTRAINT email_delivery_outbox_payload_object_check
        CHECK (jsonb_typeof(payload_jsonb) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_email_delivery_outbox_due
    ON app.email_delivery_outbox (status, next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY_PENDING');

CREATE INDEX IF NOT EXISTS idx_email_delivery_outbox_claim_expiry
    ON app.email_delivery_outbox (claim_expires_at)
    WHERE status = 'PROCESSING';

CREATE INDEX IF NOT EXISTS idx_email_delivery_outbox_user_created
    ON app.email_delivery_outbox (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_delivery_outbox_report
    ON app.email_delivery_outbox (report_id);

COMMENT ON TABLE app.email_delivery_outbox IS
    'Worker queue for email delivery claim, retry, and terminal processing state.';

COMMIT;
