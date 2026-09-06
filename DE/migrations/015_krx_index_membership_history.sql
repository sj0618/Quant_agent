-- Point-in-time KRX index constituents (KOSPI200, KOSDAQ150) as membership intervals.
--
-- The AI research node offers an index universe only when this table holds rows for
-- it (ai/ai_graph/data_sources/index_universes.py), and the PIT backtest universe is
-- then restricted with the same interval-overlap test the WICS sector filter uses
-- (ai/ai_graph/data_sources/db.py::_fetch_backtest_universe). Until an ingestion
-- fills it, a request such as "KOSPI200 종목" is refused with that fact as the reason
-- instead of being widened to the whole market.

CREATE TABLE IF NOT EXISTS feature.krx_index_membership_history (
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    index_code TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    source_id TEXT NOT NULL REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol_id, index_code, valid_from),
    CONSTRAINT chk_krx_index_membership_interval
        CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX IF NOT EXISTS idx_krx_index_membership_history_code_asof
    ON feature.krx_index_membership_history (index_code, valid_from DESC, valid_to);

COMMENT ON TABLE feature.krx_index_membership_history IS
  'PIT index constituent intervals. index_code is the KRX index name the AI grammar uses: KOSPI200, KOSDAQ150. valid_to NULL = still a constituent.';
COMMENT ON COLUMN feature.krx_index_membership_history.valid_from IS
  'First session the symbol was a constituent (inclusive).';
COMMENT ON COLUMN feature.krx_index_membership_history.valid_to IS
  'Last session the symbol was a constituent (inclusive); NULL while current.';
