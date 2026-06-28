-- Add sector snapshot columns sourced from the official KIND listed-company directory.

ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS sector TEXT;
ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS sector_source TEXT;
ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS sector_as_of DATE;
ALTER TABLE core.symbol_master ADD COLUMN IF NOT EXISTS sector_run_id UUID REFERENCES meta.ingestion_run(run_id);

CREATE INDEX IF NOT EXISTS idx_symbol_master_sector_market
    ON core.symbol_master (sector, market_segment, listing_status);

COMMENT ON COLUMN core.symbol_master.sector IS 'KRX KIND listed-company directory 업종.';
COMMENT ON COLUMN core.symbol_master.sector_source IS '업종 원천 데이터 소스 ID. 기본값은 KIND.';
COMMENT ON COLUMN core.symbol_master.sector_as_of IS '업종 스냅샷 기준일.';
COMMENT ON COLUMN core.symbol_master.sector_run_id IS '업종 컬럼을 마지막으로 갱신한 ingestion run_id.';

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
    a.run_id AS adjusted_ohlcv_run_id,
    sm.sector
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
    sm.listing_status,
    sm.sector
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
    q.issue_count,
    sm.sector
FROM core.ohlcv_quality_daily q
JOIN core.symbol_master sm ON sm.symbol_id = q.symbol_id;

CREATE OR REPLACE VIEW mart.common_stock_universe_asof AS
SELECT DISTINCT
    f.as_of_date,
    sm.symbol_id,
    f.symbol,
    sm.name,
    sm.market_segment,
    sm.security_type,
    sm.listing_status,
    sm.listed_at,
    sm.delisted_at,
    sm.sector
FROM mart.kis_adjusted_feature_frame_asof f
JOIN core.symbol_master sm
  ON sm.symbol = f.symbol
WHERE sm.security_type = '보통주'
  AND (sm.listed_at IS NULL OR f.as_of_date >= sm.listed_at)
  AND (sm.delisted_at IS NULL OR f.as_of_date <= sm.delisted_at);

CREATE OR REPLACE VIEW meta.view_common_stock_universe AS
SELECT
    symbol_id,
    symbol,
    name,
    market,
    market_segment,
    security_type,
    listing_status,
    listed_at,
    delisted_at,
    metadata_jsonb,
    sector
FROM core.symbol_master
WHERE market_segment IN ('KOSPI', 'KOSDAQ')
  AND security_type = '보통주'
  AND listing_status = 'listed';
