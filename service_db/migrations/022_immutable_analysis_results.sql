-- Immutable, owner-scoped analysis result manifests shared by jobs, runs, and reports.
-- The application supplies UUID values so this migration does not depend on pgcrypto.

BEGIN;

CREATE TABLE IF NOT EXISTS app.analysis_result (
    analysis_result_id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL,
    manifest_schema_version TEXT NOT NULL DEFAULT '1',
    manifest_hash TEXT NOT NULL,
    rule_manifest_jsonb JSONB NOT NULL,
    data_manifest_jsonb JSONB NOT NULL,
    execution_manifest_jsonb JSONB NOT NULL,
    report_manifest_jsonb JSONB NOT NULL,
    public_snapshot_jsonb JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_analysis_result_user
        FOREIGN KEY (user_id)
        REFERENCES app.users(user_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_analysis_result_schema_v1
        CHECK (manifest_schema_version = '1'),
    CONSTRAINT ck_analysis_result_hash_sha256
        CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_analysis_result_manifest_objects
        CHECK (
            jsonb_typeof(rule_manifest_jsonb) = 'object'
            AND jsonb_typeof(data_manifest_jsonb) = 'object'
            AND jsonb_typeof(execution_manifest_jsonb) = 'object'
            AND jsonb_typeof(report_manifest_jsonb) = 'object'
        ),
    CONSTRAINT ck_analysis_result_public_snapshot_object
        CHECK (jsonb_typeof(public_snapshot_jsonb) = 'object'),
    CONSTRAINT uq_analysis_result_owner_manifest_hash
        UNIQUE (user_id, manifest_hash)
);

CREATE INDEX IF NOT EXISTS idx_analysis_result_owner_created
    ON app.analysis_result (user_id, created_at DESC);

CREATE OR REPLACE FUNCTION app.reject_analysis_result_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'app.analysis_result is immutable';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_analysis_result_immutable'
          AND tgrelid = 'app.analysis_result'::regclass
    ) THEN
        CREATE TRIGGER trg_analysis_result_immutable
        BEFORE UPDATE OR DELETE ON app.analysis_result
        FOR EACH ROW
        EXECUTE FUNCTION app.reject_analysis_result_mutation();
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_analysis_result_no_truncate'
          AND tgrelid = 'app.analysis_result'::regclass
    ) THEN
        CREATE TRIGGER trg_analysis_result_no_truncate
        BEFORE TRUNCATE ON app.analysis_result
        FOR EACH STATEMENT
        EXECUTE FUNCTION app.reject_analysis_result_mutation();
    END IF;
END;
$$;

ALTER TABLE app.ai_analysis_job
    ADD COLUMN IF NOT EXISTS analysis_result_id UUID;
ALTER TABLE app.backtest_run
    ADD COLUMN IF NOT EXISTS analysis_result_id UUID;
ALTER TABLE app.ai_backtest_report
    ADD COLUMN IF NOT EXISTS analysis_result_id UUID;
ALTER TABLE app.strategy_email_report
    ADD COLUMN IF NOT EXISTS analysis_result_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_analysis_job_analysis_result'
          AND conrelid = 'app.ai_analysis_job'::regclass
    ) THEN
        ALTER TABLE app.ai_analysis_job
            ADD CONSTRAINT fk_ai_analysis_job_analysis_result
            FOREIGN KEY (analysis_result_id)
            REFERENCES app.analysis_result(analysis_result_id)
            ON DELETE RESTRICT
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_backtest_run_analysis_result'
          AND conrelid = 'app.backtest_run'::regclass
    ) THEN
        ALTER TABLE app.backtest_run
            ADD CONSTRAINT fk_backtest_run_analysis_result
            FOREIGN KEY (analysis_result_id)
            REFERENCES app.analysis_result(analysis_result_id)
            ON DELETE RESTRICT
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_backtest_report_analysis_result'
          AND conrelid = 'app.ai_backtest_report'::regclass
    ) THEN
        ALTER TABLE app.ai_backtest_report
            ADD CONSTRAINT fk_ai_backtest_report_analysis_result
            FOREIGN KEY (analysis_result_id)
            REFERENCES app.analysis_result(analysis_result_id)
            ON DELETE RESTRICT
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_strategy_email_report_analysis_result'
          AND conrelid = 'app.strategy_email_report'::regclass
    ) THEN
        ALTER TABLE app.strategy_email_report
            ADD CONSTRAINT fk_strategy_email_report_analysis_result
            FOREIGN KEY (analysis_result_id)
            REFERENCES app.analysis_result(analysis_result_id)
            ON DELETE RESTRICT
            NOT VALID;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_analysis_result
    ON app.ai_analysis_job (analysis_result_id);
CREATE INDEX IF NOT EXISTS idx_backtest_run_analysis_result
    ON app.backtest_run (analysis_result_id);
CREATE INDEX IF NOT EXISTS idx_ai_backtest_report_analysis_result
    ON app.ai_backtest_report (analysis_result_id);
CREATE INDEX IF NOT EXISTS idx_strategy_email_report_analysis_result
    ON app.strategy_email_report (analysis_result_id);

COMMENT ON TABLE app.analysis_result IS
    'Immutable owner-scoped rule/data/execution/report manifest envelope.';
COMMENT ON COLUMN app.analysis_result.public_snapshot_jsonb IS
    'Whitelisted public report snapshot; private/internal provenance is not stored here.';
COMMENT ON COLUMN app.ai_analysis_job.analysis_result_id IS
    'Immutable result identity shared with the completed run and report.';
COMMENT ON COLUMN app.backtest_run.analysis_result_id IS
    'Immutable result identity produced by this run.';
COMMENT ON COLUMN app.strategy_email_report.analysis_result_id IS
    'Immutable result identity used by report detail and download projections.';

COMMIT;
