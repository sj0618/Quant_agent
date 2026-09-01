-- PostgreSQL-owned exploration policy and durable asynchronous research appendix.

BEGIN;

CREATE TABLE IF NOT EXISTS app.ai_exploration_policy (
    policy_version TEXT PRIMARY KEY,
    market TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    policy_jsonb JSONB NOT NULL,
    publication_status TEXT NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_exploration_policy_market CHECK (market = 'KRX'),
    CONSTRAINT ck_ai_exploration_policy_hash CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_ai_exploration_policy_payload CHECK (jsonb_typeof(policy_jsonb) = 'object'),
    CONSTRAINT ck_ai_exploration_policy_published CHECK (publication_status = 'published')
);

CREATE TABLE IF NOT EXISTS app.ai_active_exploration_policy (
    market TEXT PRIMARY KEY,
    policy_version TEXT NOT NULL REFERENCES app.ai_exploration_policy(policy_version) ON DELETE RESTRICT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_active_exploration_policy_market CHECK (market = 'KRX')
);

CREATE OR REPLACE FUNCTION app.reject_ai_exploration_policy_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'app.ai_exploration_policy is immutable';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ai_exploration_policy_immutable'
          AND tgrelid = 'app.ai_exploration_policy'::regclass
    ) THEN
        CREATE TRIGGER trg_ai_exploration_policy_immutable
        BEFORE UPDATE OR DELETE ON app.ai_exploration_policy
        FOR EACH ROW EXECUTE FUNCTION app.reject_ai_exploration_policy_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ai_exploration_policy_no_truncate'
          AND tgrelid = 'app.ai_exploration_policy'::regclass
    ) THEN
        CREATE TRIGGER trg_ai_exploration_policy_no_truncate
        BEFORE TRUNCATE ON app.ai_exploration_policy
        FOR EACH STATEMENT EXECUTE FUNCTION app.reject_ai_exploration_policy_mutation();
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS app.ai_research_appendix_event (
    event_id UUID PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES app.ai_analysis_job(job_id) ON DELETE RESTRICT,
    status TEXT NOT NULL,
    payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ai_research_appendix_event_status
        CHECK (status IN ('pending', 'ready', 'unavailable')),
    CONSTRAINT ck_ai_research_appendix_event_payload
        CHECK (jsonb_typeof(payload_jsonb) = 'object'),
    CONSTRAINT uq_ai_research_appendix_event_status UNIQUE (job_id, status)
);

CREATE TABLE IF NOT EXISTS app.ai_research_appendix_outbox (
    outbox_id UUID PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES app.ai_analysis_job(job_id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    CONSTRAINT ck_ai_research_appendix_outbox_status
        CHECK (status IN ('pending', 'claimed', 'delivered', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_ai_research_appendix_event_job
    ON app.ai_research_appendix_event (job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_research_appendix_outbox_pending
    ON app.ai_research_appendix_outbox (status, created_at)
    WHERE status = 'pending';

CREATE OR REPLACE FUNCTION app.reject_ai_research_appendix_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'app.ai_research_appendix_event is append-only';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ai_research_appendix_event_immutable'
          AND tgrelid = 'app.ai_research_appendix_event'::regclass
    ) THEN
        CREATE TRIGGER trg_ai_research_appendix_event_immutable
        BEFORE UPDATE OR DELETE ON app.ai_research_appendix_event
        FOR EACH ROW EXECUTE FUNCTION app.reject_ai_research_appendix_event_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ai_research_appendix_event_no_truncate'
          AND tgrelid = 'app.ai_research_appendix_event'::regclass
    ) THEN
        CREATE TRIGGER trg_ai_research_appendix_event_no_truncate
        BEFORE TRUNCATE ON app.ai_research_appendix_event
        FOR EACH STATEMENT EXECUTE FUNCTION app.reject_ai_research_appendix_event_mutation();
    END IF;
END;
$$;

INSERT INTO app.ai_exploration_policy (
    policy_version, market, policy_hash, policy_jsonb, publication_status, effective_at
) VALUES (
    'exploration-policy-v2.krx.2026-09-01',
    'KRX',
    '054762617514ca4164fdf11fecdd66404e06ec84f0f04e23805ec47eac1d920f',
    '{"benchmark":"official_krx_total_return","candidate_count":3,"catalog_hash":"b8392766ea151cec5c7780ac26a9b09f6b6e863663be7dca93eeb30d922445e4","catalog_version":"quant-blueprints.v2","cost_model":{"commission_pct":0.00015,"slippage_pct":0.001,"tax_pct":0.0023},"history_years":5,"investment_horizon":"medium","long_only":true,"market":"KRX","max_positions":20,"policy_version":"exploration-policy-v2.krx.2026-09-01","publication_status":"published","rebalance_interval_days":21,"risk_style":"balanced","schema_version":"exploration-policy.v2","stop_loss_pct":0.2,"take_profit_pct":10.0,"timeframe":"daily","trailing_stop_pct":0.25,"validation":{"evaluation_months":1,"method":"rolling_walk_forward","minimum_evaluation_sessions":480,"roll_months":1,"train_months":12,"validation_months":3}}'::jsonb,
    'published',
    '2026-09-01T00:00:00+09:00'::timestamptz
) ON CONFLICT (policy_version) DO NOTHING;

INSERT INTO app.ai_active_exploration_policy (market, policy_version)
VALUES ('KRX', 'exploration-policy-v2.krx.2026-09-01')
ON CONFLICT (market) DO NOTHING;

COMMENT ON TABLE app.ai_exploration_policy IS
    'Immutable versioned policy sealed before exploratory performance is read.';
COMMENT ON TABLE app.ai_active_exploration_policy IS
    'Mutable market pointer to one published immutable exploration policy.';
COMMENT ON TABLE app.ai_research_appendix_event IS
    'Append-only deep research appendix status and result events.';

COMMIT;
