ALTER TABLE app.ai_prompt_log
    ADD COLUMN IF NOT EXISTS assistant_response_summary TEXT;
