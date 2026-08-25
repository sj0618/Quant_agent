-- Roll back only RMP-RESULT-01 objects, in reverse dependency order.

BEGIN;

ALTER TABLE IF EXISTS app.strategy_email_report
    DROP CONSTRAINT IF EXISTS fk_strategy_email_report_analysis_result,
    DROP COLUMN IF EXISTS analysis_result_id;
ALTER TABLE IF EXISTS app.ai_backtest_report
    DROP CONSTRAINT IF EXISTS fk_ai_backtest_report_analysis_result,
    DROP COLUMN IF EXISTS analysis_result_id;
ALTER TABLE IF EXISTS app.backtest_run
    DROP CONSTRAINT IF EXISTS fk_backtest_run_analysis_result,
    DROP COLUMN IF EXISTS analysis_result_id;
ALTER TABLE IF EXISTS app.ai_analysis_job
    DROP CONSTRAINT IF EXISTS fk_ai_analysis_job_analysis_result,
    DROP COLUMN IF EXISTS analysis_result_id;

DO $$
BEGIN
    IF to_regclass('app.analysis_result') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS trg_analysis_result_no_truncate ON app.analysis_result;
        DROP TRIGGER IF EXISTS trg_analysis_result_immutable ON app.analysis_result;
    END IF;
END;
$$;
DROP FUNCTION IF EXISTS app.reject_analysis_result_mutation();
DROP TABLE IF EXISTS app.analysis_result;
COMMIT;
