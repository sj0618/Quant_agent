-- Add the minimal runtime relationships and indexes required by AI logging.

ALTER TABLE app.ai_model_call_log
    ADD COLUMN IF NOT EXISTS execution_id UUID;

ALTER TABLE app.ai_model_call_log
    ADD COLUMN IF NOT EXISTS response_schema_name TEXT;

ALTER TABLE app.ai_model_call_log
    ADD COLUMN IF NOT EXISTS web_search_used BOOLEAN NOT NULL DEFAULT FALSE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_ai_model_call_log_execution'
          AND conrelid = 'app.ai_model_call_log'::regclass
    ) THEN
        ALTER TABLE app.ai_model_call_log
            ADD CONSTRAINT fk_ai_model_call_log_execution
            FOREIGN KEY (execution_id)
            REFERENCES app.ai_agent_execution_log(execution_id)
            ON DELETE SET NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_ai_model_call_log_execution_created
    ON app.ai_model_call_log (execution_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_prompt_log_retention
    ON app.ai_prompt_log (created_at, prompt_log_id);
