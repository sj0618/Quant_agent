-- Durable idempotency and scope-family leases for AI-generated backtests.
-- This migration is additive and safe to replay on an already-upgraded schema.

CREATE TABLE IF NOT EXISTS app.ai_backtest_request (
    request_id UUID PRIMARY KEY,
    scope_family_id UUID NOT NULL,
    client_request_key TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    fingerprint_version TEXT NOT NULL,
    session_hmac TEXT NOT NULL,
    session_hmac_version TEXT NOT NULL,
    trace_id UUID REFERENCES app.ai_trace(trace_id) ON DELETE SET NULL,
    execution_run_id UUID REFERENCES app.code_execution_run(execution_run_id) ON DELETE SET NULL,
    state TEXT NOT NULL DEFAULT 'claimed',
    safety_lease TEXT NOT NULL DEFAULT 'active',
    state_version INTEGER NOT NULL DEFAULT 1,
    terminal_response_jsonb JSONB,
    terminal_evidence_jsonb JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    terminal_at TIMESTAMPTZ,
    CONSTRAINT ck_ai_backtest_request_state CHECK (
        state IN (
            'claimed', 'generation_in_progress', 'execution_armed',
            'execution_outcome_unknown', 'execution_released',
            'succeeded', 'failed', 'abandoned'
        )
    ),
    CONSTRAINT ck_ai_backtest_request_safety_lease CHECK (
        safety_lease IN ('active', 'blocked_unknown', 'closed', 'superseded')
    ),
    CONSTRAINT ck_ai_backtest_request_state_version CHECK (state_version > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_backtest_request_scope_key
    ON app.ai_backtest_request (scope_family_id, client_request_key);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_backtest_request_active_scope_fingerprint
    ON app.ai_backtest_request (scope_family_id, fingerprint_version, payload_fingerprint)
    WHERE safety_lease IN ('active', 'blocked_unknown');

CREATE INDEX IF NOT EXISTS idx_ai_backtest_request_trace
    ON app.ai_backtest_request (trace_id)
    WHERE trace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ai_backtest_request_lease_created
    ON app.ai_backtest_request (safety_lease, created_at, request_id);

CREATE TABLE IF NOT EXISTS app.ai_backtest_replacement_approval (
    approval_id UUID PRIMARY KEY,
    source_request_id UUID NOT NULL REFERENCES app.ai_backtest_request(request_id),
    scope_family_id UUID NOT NULL,
    fingerprint_version TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    replacement_key_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'issued',
    issued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT ck_ai_backtest_replacement_approval_status CHECK (
        status IN ('issued', 'consumed', 'expired', 'revoked')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_backtest_replacement_live_source
    ON app.ai_backtest_replacement_approval (source_request_id)
    WHERE status = 'issued';

CREATE INDEX IF NOT EXISTS idx_ai_backtest_replacement_scope_fingerprint
    ON app.ai_backtest_replacement_approval (scope_family_id, fingerprint_version, payload_fingerprint);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_backtest_replacement_key_hash
    ON app.ai_backtest_replacement_approval (replacement_key_hash);
