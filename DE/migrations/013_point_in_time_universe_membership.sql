-- Point-in-time universe membership for backtest-facing mart views.
--
-- `core.symbol_master` describes the latest known state.  It must not decide whether
-- a security belonged to a historical universe.  Each view below instead uses the
-- listing and security-type intervals that contain the row's as-of date.  Missing
-- lifecycle or classification history is intentionally excluded: a result with
-- unknown membership is not a valid backtest input.

BEGIN;

CREATE TABLE IF NOT EXISTS core.symbol_security_type_history (
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    valid_from DATE NOT NULL,
    valid_to DATE,
    security_type TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    source_version TEXT NOT NULL,
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol_id, valid_from),
    CONSTRAINT chk_symbol_security_type_history_value
        CHECK (security_type IN ('보통주', '우선주', 'SPAC', '리츠(REITs)', 'ETF', 'ETN', '인프라펀드', '기타')),
    CONSTRAINT chk_symbol_security_type_history_interval
        CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT chk_symbol_security_type_history_evidence
        CHECK (
            jsonb_typeof(metadata_jsonb) = 'object'
            AND metadata_jsonb ? 'classification_evidence'
        )
);

CREATE INDEX IF NOT EXISTS idx_symbol_security_type_history_asof
    ON core.symbol_security_type_history (symbol_id, valid_from DESC, valid_to);

CREATE OR REPLACE VIEW mart.common_stock_feature_frame_asof AS
SELECT
    f.as_of_date,
    f.symbol,
    f.name,
    h.market AS market_segment,
    sh.security_type,
    h.listing_status,
    h.valid_from AS listed_at,
    h.valid_to AS delisted_at,
    f.ticker,
    f.base_ticker,
    f.segment_id,
    f.open,
    f.high,
    f.low,
    f.close,
    f.volume,
    f.adjusted_ohlcv_quality_flags,
    f.trend_values,
    f.momentum_values,
    f.volatility_values,
    f.volume_values,
    f.pattern_values,
    f.adjusted_ohlcv_run_id,
    f.sector
FROM mart.kis_adjusted_feature_frame_asof f
JOIN core.symbol_master sm
  ON sm.symbol = f.symbol
JOIN core.symbol_listing_history h
  ON h.symbol_id = sm.symbol_id
 AND h.valid_from <= f.as_of_date
 AND (h.valid_to IS NULL OR h.valid_to >= f.as_of_date)
JOIN core.symbol_security_type_history sh
  ON sh.symbol_id = sm.symbol_id
 AND sh.valid_from <= f.as_of_date
 AND (sh.valid_to IS NULL OR sh.valid_to >= f.as_of_date)
WHERE h.market IN ('KOSPI', 'KOSDAQ')
  AND h.listing_status = 'listed'
  AND sh.security_type = '보통주';

CREATE OR REPLACE VIEW mart.common_stock_universe_asof AS
SELECT DISTINCT
    f.as_of_date,
    sm.symbol_id,
    f.symbol,
    f.name,
    f.market_segment,
    f.security_type,
    f.listing_status,
    f.listed_at,
    f.delisted_at,
    f.sector
FROM mart.common_stock_feature_frame_asof f
JOIN core.symbol_master sm
  ON sm.symbol = f.symbol;

CREATE OR REPLACE VIEW mart.full_universe_asof AS
SELECT
    a."time" AS as_of_date,
    sm.symbol_id,
    sm.symbol,
    h.market AS market_segment,
    sh.security_type,
    h.listing_status,
    sm.sector
FROM feature.adjusted_ohlcv_daily a
JOIN core.symbol_master sm
  ON sm.symbol = a.base_ticker
JOIN core.symbol_listing_history h
  ON h.symbol_id = sm.symbol_id
 AND h.valid_from <= a."time"
 AND (h.valid_to IS NULL OR h.valid_to >= a."time")
JOIN core.symbol_security_type_history sh
  ON sh.symbol_id = sm.symbol_id
 AND sh.valid_from <= a."time"
 AND (sh.valid_to IS NULL OR sh.valid_to >= a."time")
LEFT JOIN core.ohlcv_quality_daily q
  ON q.symbol_id = sm.symbol_id
 AND q.as_of_date = a."time"
WHERE h.listing_status = 'listed'
  AND sh.security_type = '보통주'
  AND a.adj_close IS NOT NULL
  AND COALESCE(q.coverage_ratio, 1) >= 0.70;

COMMENT ON TABLE core.symbol_security_type_history IS
  'Historical source-backed security classification. No current symbol_master fallback is allowed for PIT membership.';

COMMENT ON VIEW mart.common_stock_feature_frame_asof IS
  'PIT KOSPI/KOSDAQ common-stock frame. Listing and security-type intervals must both contain as_of_date.';

COMMENT ON VIEW mart.common_stock_universe_asof IS
  'PIT common-stock membership is unavailable when listing or security-type history is missing.';

COMMENT ON VIEW mart.full_universe_asof IS
  'PIT tradable membership requires listed lifecycle and source-backed common-stock classification at as_of_date.';

COMMIT;
