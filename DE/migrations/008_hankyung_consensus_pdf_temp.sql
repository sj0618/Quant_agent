-- Temporary Hankyung Consensus PDF extraction landing tables.
-- This schema is intentionally temp-scoped until the PDF evidence flow is
-- validated and a production model is approved.

CREATE TABLE IF NOT EXISTS raw.hankyung_consensus_pdf_temp_files (
    pdf_id TEXT PRIMARY KEY,
    seed_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('url', 'file')),
    safe_source_label TEXT NOT NULL,
    stored_artifact_key TEXT,
    original_filename TEXT,
    file_hash TEXT,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    page_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('extracted', 'duplicate', 'failed', 'ocr_required')),
    failure_reason TEXT,
    canonical_pdf_id TEXT REFERENCES raw.hankyung_consensus_pdf_temp_files(pdf_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.hankyung_consensus_pdf_temp_pages (
    page_id TEXT PRIMARY KEY,
    pdf_id TEXT NOT NULL REFERENCES raw.hankyung_consensus_pdf_temp_files(pdf_id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL CHECK (page_number >= 1),
    text TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pdf_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_hankyung_consensus_pdf_temp_files_seed
    ON raw.hankyung_consensus_pdf_temp_files (seed_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hankyung_consensus_pdf_temp_files_hash
    ON raw.hankyung_consensus_pdf_temp_files (file_hash)
    WHERE file_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_hankyung_consensus_pdf_temp_files_status
    ON raw.hankyung_consensus_pdf_temp_files (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hankyung_consensus_pdf_temp_pages_pdf
    ON raw.hankyung_consensus_pdf_temp_pages (pdf_id, page_number);
