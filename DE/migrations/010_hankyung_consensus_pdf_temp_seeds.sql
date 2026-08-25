-- Store Hankyung Consensus crawler-discovered PDF temp seeds.
-- This table remains temp-scoped until the PDF evidence flow graduates to a
-- production report/source model.

CREATE TABLE IF NOT EXISTS raw.hankyung_consensus_pdf_temp_seeds (
    seed_id TEXT PRIMARY KEY,
    report_idx TEXT NOT NULL,
    report_title TEXT,
    company_name TEXT,
    ticker TEXT,
    broker TEXT,
    report_date DATE,
    pdf_url TEXT NOT NULL,
    source_page_url TEXT,
    source_report_type TEXT,
    source_writer TEXT,
    source_payload_hash TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'error', 'disabled')),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_idx)
);

CREATE INDEX IF NOT EXISTS idx_hankyung_consensus_pdf_temp_seeds_report_idx
    ON raw.hankyung_consensus_pdf_temp_seeds (report_idx);

CREATE INDEX IF NOT EXISTS idx_hankyung_consensus_pdf_temp_seeds_ticker_report_date
    ON raw.hankyung_consensus_pdf_temp_seeds (ticker, report_date);

CREATE INDEX IF NOT EXISTS idx_hankyung_consensus_pdf_temp_seeds_status_seen
    ON raw.hankyung_consensus_pdf_temp_seeds (status, last_seen_at DESC);