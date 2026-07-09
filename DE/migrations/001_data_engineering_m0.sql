-- Quant-Agent data engineering M0 schema.
-- Requires PostgreSQL with TimescaleDB installed in the target database.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS feature;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS meta.data_source (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_url_key TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT 'v1',
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta.ingestion_run (
    run_id UUID PRIMARY KEY,
    dag_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    source_id TEXT REFERENCES meta.data_source(source_id),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    params_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS meta.ingestion_cursor (
    source_id TEXT NOT NULL REFERENCES meta.data_source(source_id),
    dataset TEXT NOT NULL,
    cursor_key TEXT NOT NULL,
    cursor_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, dataset, cursor_key)
);

CREATE TABLE IF NOT EXISTS meta.api_request_log (
    request_id BIGSERIAL PRIMARY KEY,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    source_id TEXT REFERENCES meta.data_source(source_id),
    endpoint_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    status_code INTEGER,
    elapsed_ms INTEGER,
    retry_count INTEGER NOT NULL DEFAULT 0,
    response_hash TEXT,
    error_message TEXT,
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    request_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta.data_quality_issue (
    issue_id BIGSERIAL PRIMARY KEY,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    dataset TEXT NOT NULL,
    symbol TEXT,
    trade_date DATE,
    severity TEXT NOT NULL,
    rule_code TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta.lineage_event (
    lineage_id BIGSERIAL PRIMARY KEY,
    target_table TEXT NOT NULL,
    target_key TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_key TEXT NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    transform_version TEXT NOT NULL,
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.ohlcv_response (
    raw_id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES meta.data_source(source_id),
    request_date DATE NOT NULL,
    request_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_jsonb JSONB NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, request_hash, payload_hash)
);

CREATE TABLE IF NOT EXISTS raw.seibro_report_response (
    raw_id BIGSERIAL PRIMARY KEY,
    query_window TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_jsonb JSONB NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (query_window, payload_hash)
);

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

CREATE TABLE IF NOT EXISTS raw.bok_response (
    raw_id BIGSERIAL PRIMARY KEY,
    stat_code TEXT NOT NULL,
    item_code TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_jsonb JSONB NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (stat_code, item_code, payload_hash)
);

CREATE TABLE IF NOT EXISTS raw.dart_response (
    raw_id BIGSERIAL PRIMARY KEY,
    corp_code TEXT NOT NULL,
    report_code TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_jsonb JSONB NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (corp_code, report_code, payload_hash)
);

CREATE TABLE IF NOT EXISTS core.symbol_master (
    symbol_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    market TEXT,
    market_segment TEXT,
    security_type TEXT,
    listing_status TEXT NOT NULL DEFAULT 'listed',
    listed_at DATE,
    delisted_at DATE,
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.symbol_listing_history (
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    valid_from DATE NOT NULL,
    valid_to DATE,
    market TEXT,
    listing_status TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'listed',
    source_id TEXT REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (symbol_id, valid_from)
);

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

CREATE TABLE IF NOT EXISTS core.trading_calendar (
    market TEXT NOT NULL,
    trade_date DATE NOT NULL,
    is_open BOOLEAN NOT NULL,
    reason TEXT,
    source_id TEXT REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    PRIMARY KEY (market, trade_date)
);

CREATE TABLE IF NOT EXISTS core.ohlcv_daily (
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    trade_date DATE NOT NULL,
    open NUMERIC(20, 6),
    high NUMERIC(20, 6),
    low NUMERIC(20, 6),
    close NUMERIC(20, 6),
    volume NUMERIC(28, 0),
    source_id TEXT NOT NULL REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    is_tradable BOOLEAN NOT NULL DEFAULT TRUE,
    quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, symbol_id)
);

SELECT create_hypertable('core.ohlcv_daily', 'trade_date', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS core.ohlcv_quality_daily (
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    as_of_date DATE NOT NULL,
    expected_days INTEGER NOT NULL,
    observed_days INTEGER NOT NULL,
    coverage_ratio NUMERIC(8, 6) NOT NULL,
    missing_days INTEGER NOT NULL,
    issue_count INTEGER NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    PRIMARY KEY (symbol_id, as_of_date)
);

CREATE TABLE IF NOT EXISTS feature.ta_indicator_definition (
    indicator_id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    parameters_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    warmup_days INTEGER NOT NULL DEFAULT 0,
    output_schema_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    transform_version TEXT NOT NULL,
    UNIQUE (category, name, parameters_jsonb)
);

CREATE TABLE IF NOT EXISTS feature.ta_trend_daily (
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    trade_date DATE NOT NULL,
    values_jsonb JSONB NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (trade_date, symbol_id)
);

CREATE TABLE IF NOT EXISTS feature.ta_momentum_daily (LIKE feature.ta_trend_daily INCLUDING ALL);
CREATE TABLE IF NOT EXISTS feature.ta_volatility_daily (LIKE feature.ta_trend_daily INCLUDING ALL);
CREATE TABLE IF NOT EXISTS feature.ta_volume_daily (LIKE feature.ta_trend_daily INCLUDING ALL);
CREATE TABLE IF NOT EXISTS feature.ta_pattern_daily (LIKE feature.ta_trend_daily INCLUDING ALL);

SELECT create_hypertable('feature.ta_trend_daily', 'trade_date', if_not_exists => TRUE);
SELECT create_hypertable('feature.ta_momentum_daily', 'trade_date', if_not_exists => TRUE);
SELECT create_hypertable('feature.ta_volatility_daily', 'trade_date', if_not_exists => TRUE);
SELECT create_hypertable('feature.ta_volume_daily', 'trade_date', if_not_exists => TRUE);
SELECT create_hypertable('feature.ta_pattern_daily', 'trade_date', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS feature.seibro_report_summary (
    report_id BIGSERIAL PRIMARY KEY,
    symbol_id BIGINT REFERENCES core.symbol_master(symbol_id),
    report_date DATE NOT NULL,
    company_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    opinion TEXT,
    target_price NUMERIC(20, 6),
    close_price NUMERIC(20, 6),
    institution TEXT,
    author TEXT,
    source_payload_hash TEXT,
    run_id UUID REFERENCES meta.ingestion_run(run_id)
);

CREATE TABLE IF NOT EXISTS feature.seibro_sentiment (
    report_id BIGINT PRIMARY KEY REFERENCES feature.seibro_report_summary(report_id),
    sentiment_score NUMERIC(6, 4) NOT NULL,
    model_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id UUID REFERENCES meta.ingestion_run(run_id)
);

CREATE TABLE IF NOT EXISTS feature.seibro_universe_daily (
    as_of_date DATE NOT NULL,
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    avg_sentiment_score NUMERIC(6, 4) NOT NULL,
    report_count INTEGER NOT NULL,
    included BOOLEAN NOT NULL,
    exclusion_reason TEXT,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    PRIMARY KEY (as_of_date, symbol_id)
);

CREATE TABLE IF NOT EXISTS feature.bok_macro_daily (
    series_id TEXT NOT NULL,
    effective_date DATE NOT NULL,
    published_at TIMESTAMPTZ,
    value NUMERIC(28, 10),
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    PRIMARY KEY (series_id, effective_date)
);

CREATE TABLE IF NOT EXISTS feature.dart_financial_quarterly (
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    corp_code TEXT NOT NULL,
    period_end DATE NOT NULL,
    reported_at TIMESTAMPTZ,
    report_code TEXT NOT NULL,
    fs_div TEXT NOT NULL,
    accounts_jsonb JSONB NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    PRIMARY KEY (symbol_id, period_end, report_code, fs_div)
);

CREATE OR REPLACE VIEW mart.full_universe_asof AS
SELECT
    o.trade_date AS as_of_date,
    o.symbol_id
FROM core.ohlcv_daily o
JOIN core.ohlcv_quality_daily q
  ON q.symbol_id = o.symbol_id
 AND q.as_of_date = o.trade_date
WHERE o.is_tradable = TRUE
  AND q.coverage_ratio >= 0.70;

CREATE OR REPLACE VIEW mart.seibro_universe_asof AS
SELECT
    as_of_date,
    symbol_id,
    avg_sentiment_score,
    report_count
FROM feature.seibro_universe_daily
WHERE included = TRUE;

CREATE OR REPLACE VIEW mart.data_coverage_report AS
SELECT
    q.as_of_date,
    sm.symbol,
    sm.name,
    q.expected_days,
    q.observed_days,
    q.coverage_ratio,
    q.missing_days,
    q.issue_count
FROM core.ohlcv_quality_daily q
JOIN core.symbol_master sm ON sm.symbol_id = q.symbol_id;

CREATE INDEX IF NOT EXISTS idx_ohlcv_daily_symbol_date ON core.ohlcv_daily (symbol_id, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_payload ON raw.ohlcv_response USING GIN (payload_jsonb);
CREATE INDEX IF NOT EXISTS idx_raw_analyst_report_summary_ticker_date
    ON raw.analyst_report_summary (ticker, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_analyst_report_summary_payload
    ON raw.analyst_report_summary USING GIN (raw_jsonb);
CREATE INDEX IF NOT EXISTS idx_dq_issue_dataset ON meta.data_quality_issue (dataset, severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_request_log_run_source_created ON meta.api_request_log (run_id, source_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lineage_event_target ON meta.lineage_event (target_table, target_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_symbol_master_market_status ON core.symbol_master (market_segment, listing_status);
CREATE INDEX IF NOT EXISTS idx_symbol_listing_history_symbol_validity ON core.symbol_listing_history (symbol_id, valid_from DESC, valid_to);
CREATE INDEX IF NOT EXISTS idx_symbol_name_history_symbol_validity ON core.symbol_name_history (symbol_id, valid_from DESC, valid_to);
CREATE INDEX IF NOT EXISTS idx_seibro_report_symbol_date ON feature.seibro_report_summary (symbol_id, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_bok_macro_series_date ON feature.bok_macro_daily (series_id, effective_date DESC);
CREATE INDEX IF NOT EXISTS idx_dart_financial_symbol_period ON feature.dart_financial_quarterly (symbol_id, period_end DESC);
