-- Persist subprocess ownership before the child receives its release byte.
ALTER TABLE IF EXISTS app.code_execution_run
    ADD COLUMN IF NOT EXISTS attempt_id UUID,
    ADD COLUMN IF NOT EXISTS worker_host TEXT,
    ADD COLUMN IF NOT EXISTS worker_pid INTEGER,
    ADD COLUMN IF NOT EXISTS worker_pgid INTEGER,
    ADD COLUMN IF NOT EXISTS worker_started_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_code_execution_run_attempt
    ON app.code_execution_run (attempt_id)
    WHERE attempt_id IS NOT NULL;
