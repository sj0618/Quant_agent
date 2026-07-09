-- Phase 2 quality, observability, and lineage additions.

ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS success BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE meta.api_request_log ADD COLUMN IF NOT EXISTS request_started_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE meta.lineage_event ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_api_request_log_run_source_created
    ON meta.api_request_log (run_id, source_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_lineage_event_target
    ON meta.lineage_event (target_table, target_key, created_at DESC);

CREATE TABLE IF NOT EXISTS feature.adjusted_ohlcv_daily (
    "time" DATE NOT NULL,
    ticker TEXT NOT NULL,
    base_ticker TEXT NOT NULL,
    segment_id INTEGER NOT NULL DEFAULT 1,
    open NUMERIC(20, 6),
    high NUMERIC(20, 6),
    low NUMERIC(20, 6),
    close NUMERIC(20, 6),
    volume NUMERIC(28, 6),
    adj_open NUMERIC(20, 6),
    adj_high NUMERIC(20, 6),
    adj_low NUMERIC(20, 6),
    adj_close NUMERIC(20, 6),
    adj_volume NUMERIC(28, 6),
    adjustment_factor NUMERIC(28, 12) NOT NULL DEFAULT 1,
    quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY ("time", ticker)
);
SELECT create_hypertable('feature.adjusted_ohlcv_daily', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_feature_adjusted_ohlcv_daily_base_ticker_time
    ON feature.adjusted_ohlcv_daily (base_ticker, "time" DESC);

CREATE TABLE IF NOT EXISTS feature.ta_trend_ticker_daily (
    "time" DATE NOT NULL,
    ticker TEXT NOT NULL,
    base_ticker TEXT NOT NULL,
    segment_id INTEGER NOT NULL DEFAULT 1,
    values_jsonb JSONB NOT NULL,
    quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY ("time", ticker)
);
CREATE TABLE IF NOT EXISTS feature.ta_momentum_ticker_daily (LIKE feature.ta_trend_ticker_daily INCLUDING ALL);
CREATE TABLE IF NOT EXISTS feature.ta_volatility_ticker_daily (LIKE feature.ta_trend_ticker_daily INCLUDING ALL);
CREATE TABLE IF NOT EXISTS feature.ta_volume_ticker_daily (LIKE feature.ta_trend_ticker_daily INCLUDING ALL);
CREATE TABLE IF NOT EXISTS feature.ta_pattern_ticker_daily (LIKE feature.ta_trend_ticker_daily INCLUDING ALL);

SELECT create_hypertable('feature.ta_trend_ticker_daily', 'time', if_not_exists => TRUE);
SELECT create_hypertable('feature.ta_momentum_ticker_daily', 'time', if_not_exists => TRUE);
SELECT create_hypertable('feature.ta_volatility_ticker_daily', 'time', if_not_exists => TRUE);
SELECT create_hypertable('feature.ta_volume_ticker_daily', 'time', if_not_exists => TRUE);
SELECT create_hypertable('feature.ta_pattern_ticker_daily', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_feature_ta_trend_ticker_daily_ticker_time
    ON feature.ta_trend_ticker_daily (ticker, "time" DESC);
CREATE INDEX IF NOT EXISTS idx_feature_ta_momentum_ticker_daily_ticker_time
    ON feature.ta_momentum_ticker_daily (ticker, "time" DESC);
CREATE INDEX IF NOT EXISTS idx_feature_ta_volatility_ticker_daily_ticker_time
    ON feature.ta_volatility_ticker_daily (ticker, "time" DESC);
CREATE INDEX IF NOT EXISTS idx_feature_ta_volume_ticker_daily_ticker_time
    ON feature.ta_volume_ticker_daily (ticker, "time" DESC);
CREATE INDEX IF NOT EXISTS idx_feature_ta_pattern_ticker_daily_ticker_time
    ON feature.ta_pattern_ticker_daily (ticker, "time" DESC);

CREATE OR REPLACE VIEW mart.kis_adjusted_feature_frame_asof AS
SELECT
    a."time" AS as_of_date,
    a.ticker,
    a.base_ticker,
    a.segment_id,
    a.adj_open,
    a.adj_high,
    a.adj_low,
    a.adj_close,
    a.adj_volume,
    a.quality_flags AS adjusted_ohlcv_quality_flags,
    tt.values_jsonb AS trend_values,
    tm.values_jsonb AS momentum_values,
    tv.values_jsonb AS volatility_values,
    tvol.values_jsonb AS volume_values,
    tp.values_jsonb AS pattern_values,
    a.run_id AS adjusted_ohlcv_run_id
FROM feature.adjusted_ohlcv_daily a
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
