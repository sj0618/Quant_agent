-- Phase 3 mart/view and symbol lifecycle metadata additions.

ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS market_segment TEXT;
ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS listing_status TEXT NOT NULL DEFAULT 'listed';
ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS listed_at DATE;
ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS delisted_at DATE;
ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE core.symbol_listing_history ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'listed';
ALTER TABLE core.symbol_listing_history ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS core.symbol_name_history (
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    valid_from DATE NOT NULL,
    valid_to DATE,
    name TEXT NOT NULL,
    source_id TEXT REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (symbol_id, valid_from, name)
);

CREATE INDEX IF NOT EXISTS idx_symbol_master_market_status
    ON core.symbol_master (market_segment, listing_status);
CREATE INDEX IF NOT EXISTS idx_symbol_listing_history_symbol_validity
    ON core.symbol_listing_history (symbol_id, valid_from DESC, valid_to);
CREATE INDEX IF NOT EXISTS idx_symbol_name_history_symbol_validity
    ON core.symbol_name_history (symbol_id, valid_from DESC, valid_to);

UPDATE core.symbol_master
   SET market_segment = UPPER(market)
 WHERE market_segment IS NULL
   AND market IS NOT NULL
   AND UPPER(market) IN ('KOSPI', 'KOSDAQ', 'KONEX');

DROP VIEW IF EXISTS mart.kis_adjusted_feature_frame_asof;
DROP VIEW IF EXISTS mart.symbol_feature_frame_asof;
DROP VIEW IF EXISTS mart.full_universe_asof;
DROP VIEW IF EXISTS mart.data_coverage_report;

CREATE OR REPLACE VIEW mart.symbol_feature_frame_asof AS
SELECT
    a."time" AS as_of_date,
    sm.symbol,
    sm.name,
    sm.market_segment,
    sm.listing_status,
    sm.listed_at,
    sm.delisted_at,
    a.ticker,
    a.base_ticker,
    a.segment_id,
    a.adj_open AS open,
    a.adj_high AS high,
    a.adj_low AS low,
    a.adj_close AS close,
    a.adj_volume AS volume,
    a.quality_flags AS adjusted_ohlcv_quality_flags,
    tt.values_jsonb AS trend_values,
    tm.values_jsonb AS momentum_values,
    tv.values_jsonb AS volatility_values,
    tvol.values_jsonb AS volume_values,
    tp.values_jsonb AS pattern_values,
    a.run_id AS adjusted_ohlcv_run_id
FROM feature.adjusted_ohlcv_daily a
JOIN core.symbol_master sm ON sm.symbol = a.base_ticker
LEFT JOIN feature.ta_trend_ticker_daily tt
       ON tt.ticker = a.ticker AND tt."time" = a."time"
LEFT JOIN feature.ta_momentum_ticker_daily tm
       ON tm.ticker = a.ticker AND tm."time" = a."time"
LEFT JOIN feature.ta_volatility_ticker_daily tv
       ON tv.ticker = a.ticker AND tv."time" = a."time"
LEFT JOIN feature.ta_volume_ticker_daily tvol
       ON tvol.ticker = a.ticker AND tvol."time" = a."time"
LEFT JOIN feature.ta_pattern_ticker_daily tp
       ON tp.ticker = a.ticker AND tp."time" = a."time";

CREATE OR REPLACE VIEW mart.kis_adjusted_feature_frame_asof AS
SELECT *
FROM mart.symbol_feature_frame_asof
WHERE adjusted_ohlcv_quality_flags->>'adjusted_price_method' = 'kis_official_adjusted';

CREATE OR REPLACE VIEW mart.full_universe_asof AS
SELECT
    a."time" AS as_of_date,
    sm.symbol_id,
    sm.symbol,
    sm.market_segment,
    sm.listing_status
FROM feature.adjusted_ohlcv_daily a
JOIN core.symbol_master sm ON sm.symbol = a.base_ticker
LEFT JOIN core.ohlcv_quality_daily q
       ON q.symbol_id = sm.symbol_id AND q.as_of_date = a."time"
WHERE sm.listing_status = 'listed'
  AND a.adj_close IS NOT NULL
  AND COALESCE(q.coverage_ratio, 1) >= 0.70;

CREATE OR REPLACE VIEW mart.data_coverage_report AS
SELECT
    q.as_of_date,
    sm.symbol,
    sm.name,
    sm.market_segment,
    sm.listing_status,
    q.expected_days,
    q.observed_days,
    q.coverage_ratio,
    q.missing_days,
    q.issue_count
FROM core.ohlcv_quality_daily q
JOIN core.symbol_master sm ON sm.symbol_id = q.symbol_id;
