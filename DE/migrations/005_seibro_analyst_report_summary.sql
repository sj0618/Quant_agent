-- SEIBro analyst report summary raw landing table.

CREATE TABLE IF NOT EXISTS raw.analyst_report_summary (
    report_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    company_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    opinion TEXT,
    target_price NUMERIC(20, 6),
    close_price NUMERIC(20, 6),
    institution TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    source_payload_hash TEXT NOT NULL,
    raw_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (report_date, ticker, institution, author)
);

CREATE INDEX IF NOT EXISTS idx_raw_analyst_report_summary_ticker_date
    ON raw.analyst_report_summary (ticker, report_date DESC);

CREATE INDEX IF NOT EXISTS idx_raw_analyst_report_summary_payload
    ON raw.analyst_report_summary USING GIN (raw_jsonb);
