-- Durable AI job state. The full public job envelope lives in one JSONB document so
-- the AI API and report completion path share one authoritative result.

CREATE TABLE IF NOT EXISTS app.ai_analysis_job (
    job_id TEXT PRIMARY KEY,
    user_id TEXT,
    job_jsonb JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_job_user_updated
    ON app.ai_analysis_job (user_id, updated_at DESC);
