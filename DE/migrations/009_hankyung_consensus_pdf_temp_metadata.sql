-- Add deterministic report metadata to the temporary Hankyung Consensus PDF
-- landing table. This remains temp-scoped until the PDF evidence flow is
-- validated and a production report model is approved.

ALTER TABLE raw.hankyung_consensus_pdf_temp_files
    ADD COLUMN IF NOT EXISTS report_idx TEXT,
    ADD COLUMN IF NOT EXISTS report_title TEXT,
    ADD COLUMN IF NOT EXISTS company_name TEXT,
    ADD COLUMN IF NOT EXISTS ticker TEXT,
    ADD COLUMN IF NOT EXISTS broker TEXT,
    ADD COLUMN IF NOT EXISTS report_date DATE;

UPDATE raw.hankyung_consensus_pdf_temp_files
SET report_idx = substring(seed_id from '^hankyung-([0-9]+)$')
WHERE report_idx IS NULL
  AND seed_id ~ '^hankyung-[0-9]+$';

CREATE INDEX IF NOT EXISTS idx_hankyung_consensus_pdf_temp_files_report_idx
    ON raw.hankyung_consensus_pdf_temp_files (report_idx);

CREATE INDEX IF NOT EXISTS idx_hankyung_consensus_pdf_temp_files_ticker_report_date
    ON raw.hankyung_consensus_pdf_temp_files (ticker, report_date);
