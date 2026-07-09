-- Quant-Agent data engineering runtime additions.

CREATE TABLE IF NOT EXISTS feature.dart_corp_symbol_map (
    corp_code TEXT PRIMARY KEY,
    corp_name TEXT,
    symbol TEXT NOT NULL,
    modify_date TEXT,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dart_corp_symbol_map_symbol
    ON feature.dart_corp_symbol_map (symbol);

CREATE OR REPLACE VIEW mart.symbol_feature_frame_asof AS
SELECT
    o.trade_date AS as_of_date,
    sm.symbol,
    sm.name,
    o.open,
    o.high,
    o.low,
    o.close,
    o.volume,
    o.is_tradable,
    o.quality_flags AS ohlcv_quality_flags,
    tt.values_jsonb AS trend_values,
    tm.values_jsonb AS momentum_values,
    tv.values_jsonb AS volatility_values,
    tvol.values_jsonb AS volume_values,
    tp.values_jsonb AS pattern_values
FROM core.ohlcv_daily o
JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
LEFT JOIN feature.ta_trend_daily tt
       ON tt.symbol_id = o.symbol_id AND tt.trade_date = o.trade_date
LEFT JOIN feature.ta_momentum_daily tm
       ON tm.symbol_id = o.symbol_id AND tm.trade_date = o.trade_date
LEFT JOIN feature.ta_volatility_daily tv
       ON tv.symbol_id = o.symbol_id AND tv.trade_date = o.trade_date
LEFT JOIN feature.ta_volume_daily tvol
       ON tvol.symbol_id = o.symbol_id AND tvol.trade_date = o.trade_date
LEFT JOIN feature.ta_pattern_daily tp
       ON tp.symbol_id = o.symbol_id AND tp.trade_date = o.trade_date;

CREATE OR REPLACE VIEW mart.bok_macro_asof AS
SELECT
    series_id,
    effective_date,
    COALESCE(published_at::date, effective_date) AS available_from,
    value,
    metadata_jsonb
FROM feature.bok_macro_daily;

CREATE OR REPLACE VIEW mart.dart_financial_asof AS
SELECT
    sm.symbol,
    f.corp_code,
    f.period_end,
    COALESCE(f.reported_at::date, f.period_end) AS available_from,
    f.report_code,
    f.fs_div,
    f.accounts_jsonb
FROM feature.dart_financial_quarterly f
JOIN core.symbol_master sm ON sm.symbol_id = f.symbol_id;

DO $$
BEGIN
    CREATE ROLE backtest_reader NOLOGIN;
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

GRANT USAGE ON SCHEMA mart TO backtest_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO backtest_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO backtest_reader;
