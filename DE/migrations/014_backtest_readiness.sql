-- Backtest-readiness contracts: explicit availability, WICS history, and DART filing versions.

BEGIN;

-- A KRX request with no rows is not enough evidence that a weekday was closed:
-- late publication and network/source incidents are both possible. NULL means
-- unconfirmed and is excluded by all `is_open = TRUE` PIT joins.
ALTER TABLE core.trading_calendar
    ALTER COLUMN is_open DROP NOT NULL;
ALTER TABLE core.trading_calendar
    ADD COLUMN IF NOT EXISTS evidence_status TEXT NOT NULL DEFAULT 'unconfirmed';
UPDATE core.trading_calendar
   SET evidence_status = CASE
       WHEN EXTRACT(ISODOW FROM trade_date) IN (6, 7) THEN 'weekend'
       WHEN LOWER(COALESCE(reason, '')) LIKE '%holiday%' THEN 'official_holiday'
       WHEN reason = 'OPEN_OBSERVED' THEN 'observed'
       WHEN is_open IS TRUE THEN 'unconfirmed'
       ELSE 'unconfirmed'
   END;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = 'chk_trading_calendar_evidence_status'
           AND conrelid = 'core.trading_calendar'::regclass
    ) THEN
        ALTER TABLE core.trading_calendar
            ADD CONSTRAINT chk_trading_calendar_evidence_status
            CHECK (evidence_status IN ('observed', 'official_holiday', 'weekend', 'unconfirmed'));
    END IF;
END $$;

INSERT INTO meta.data_source (source_id, name, base_url_key, version, is_primary)
VALUES
    ('KRX', 'Korea Exchange', 'KRX_DAILY_MARKET_ENDPOINTS', 'v1', TRUE),
    ('WICS', 'FnGuide Company Guide WICS classification', 'WICS_COMPANY_INFO_URL', 'v1', FALSE),
    ('BOK', 'Bank of Korea ECOS', 'BOK_BASE_URL', 'v1', FALSE),
    ('DART', 'OpenDART Financial Supervisory Service', 'DART_BASE_URL', 'v1', FALSE)
ON CONFLICT (source_id) DO UPDATE SET
    name = EXCLUDED.name,
    base_url_key = EXCLUDED.base_url_key,
    version = EXCLUDED.version,
    is_primary = EXCLUDED.is_primary,
    updated_at = now();

CREATE TABLE IF NOT EXISTS raw.wics_company_info_response (
    raw_id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES meta.data_source(source_id),
    ticker TEXT NOT NULL,
    request_date DATE NOT NULL,
    source_url TEXT,
    payload_html TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, ticker, request_date, payload_hash)
);

CREATE INDEX IF NOT EXISTS idx_wics_company_info_response_ticker_date
    ON raw.wics_company_info_response (ticker, request_date DESC);

CREATE TABLE IF NOT EXISTS feature.wics_sector_definition (
    wics_code TEXT PRIMARY KEY,
    sector_level TEXT NOT NULL DEFAULT 'sector',
    sector_name TEXT NOT NULL,
    parent_wics_code TEXT,
    source_id TEXT REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feature.wics_symbol_sector_history (
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    wics_code TEXT NOT NULL REFERENCES feature.wics_sector_definition(wics_code),
    sector_name TEXT NOT NULL,
    market_segment TEXT,
    valid_from DATE NOT NULL,
    valid_to DATE,
    source_id TEXT NOT NULL REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol_id, wics_code, valid_from),
    CONSTRAINT chk_wics_symbol_sector_interval
        CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX IF NOT EXISTS idx_wics_symbol_sector_history_asof
    ON feature.wics_symbol_sector_history (symbol_id, valid_from DESC, valid_to);
CREATE INDEX IF NOT EXISTS idx_wics_symbol_sector_history_code_asof
    ON feature.wics_symbol_sector_history (wics_code, valid_from DESC, valid_to);
CREATE UNIQUE INDEX IF NOT EXISTS uq_wics_symbol_sector_history_symbol_date
    ON feature.wics_symbol_sector_history (symbol_id, valid_from);

-- Preserve the existing current WICS snapshot as the first historical interval.
INSERT INTO feature.wics_sector_definition
    (wics_code, sector_name, source_id, run_id, metadata_jsonb)
WITH current_wics AS (
    SELECT
        COALESCE(NULLIF(sm.metadata_jsonb->>'wics_sector_code', ''), sm.sector) AS wics_code,
        sm.sector AS sector_name,
        sm.sector_run_id AS run_id,
        sm.sector_as_of,
        sm.updated_at,
        sm.symbol_id
    FROM core.symbol_master sm
    WHERE sm.sector IS NOT NULL
      AND sm.sector_source = 'WICS'
      AND COALESCE(NULLIF(sm.metadata_jsonb->>'wics_sector_code', ''), sm.sector) IS NOT NULL
), canonical_wics AS (
    SELECT DISTINCT ON (wics_code)
        wics_code,
        sector_name,
        run_id
    FROM current_wics
    ORDER BY wics_code, sector_as_of DESC NULLS LAST, updated_at DESC, symbol_id
)
SELECT
    wics_code,
    sector_name,
    'WICS',
    run_id,
    jsonb_build_object('migration_source', 'core.symbol_master.sector')
FROM canonical_wics
ON CONFLICT (wics_code) DO UPDATE SET
    sector_name = EXCLUDED.sector_name,
    source_id = COALESCE(EXCLUDED.source_id, feature.wics_sector_definition.source_id),
    run_id = COALESCE(EXCLUDED.run_id, feature.wics_sector_definition.run_id),
    updated_at = now();

INSERT INTO feature.wics_symbol_sector_history
    (symbol_id, wics_code, sector_name, market_segment, valid_from, valid_to, source_id, run_id, metadata_jsonb)
SELECT
    sm.symbol_id,
    COALESCE(NULLIF(sm.metadata_jsonb->>'wics_sector_code', ''), sm.sector),
    sm.sector,
    sm.market_segment,
    sm.sector_as_of,
    NULL,
    'WICS',
    sm.sector_run_id,
    jsonb_build_object('migration_source', 'core.symbol_master.sector')
FROM core.symbol_master sm
WHERE sm.sector IS NOT NULL
  AND sm.sector_source = 'WICS'
  AND sm.sector_as_of IS NOT NULL
  AND COALESCE(NULLIF(sm.metadata_jsonb->>'wics_sector_code', ''), sm.sector) IS NOT NULL
ON CONFLICT (symbol_id, valid_from) DO UPDATE SET
    wics_code = EXCLUDED.wics_code,
    sector_name = EXCLUDED.sector_name,
    market_segment = EXCLUDED.market_segment,
    source_id = EXCLUDED.source_id,
    run_id = EXCLUDED.run_id,
    metadata_jsonb = feature.wics_symbol_sector_history.metadata_jsonb || EXCLUDED.metadata_jsonb;

-- Replace the 013 PIT universe projections after WICS history exists. The
-- current symbol_master.sector value is only a cache and must not leak into
-- historical backtests.
DROP VIEW IF EXISTS mart.common_stock_universe_asof;
DROP VIEW IF EXISTS mart.common_stock_feature_frame_asof;
DROP VIEW IF EXISTS mart.full_universe_asof;

CREATE VIEW mart.common_stock_feature_frame_asof AS
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
    w.sector_name AS sector
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
JOIN feature.wics_symbol_sector_history w
  ON w.symbol_id = sm.symbol_id
 AND w.valid_from <= f.as_of_date
 AND (w.valid_to IS NULL OR w.valid_to >= f.as_of_date)
WHERE h.market IN ('KOSPI', 'KOSDAQ')
  AND h.listing_status = 'listed'
  AND sh.security_type = '보통주';

CREATE VIEW mart.common_stock_universe_asof AS
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

CREATE VIEW mart.full_universe_asof AS
SELECT
    a."time" AS as_of_date,
    sm.symbol_id,
    sm.symbol,
    h.market AS market_segment,
    sh.security_type,
    h.listing_status,
    w.sector_name AS sector
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
JOIN feature.wics_symbol_sector_history w
  ON w.symbol_id = sm.symbol_id
 AND w.valid_from <= a."time"
 AND (w.valid_to IS NULL OR w.valid_to >= a."time")
LEFT JOIN core.ohlcv_quality_daily q
  ON q.symbol_id = sm.symbol_id
 AND q.as_of_date = a."time"
WHERE h.listing_status = 'listed'
  AND sh.security_type = '보통주'
  AND a.adj_close IS NOT NULL
  AND COALESCE(q.coverage_ratio, 1) >= 0.70;

-- BOK observation date and first safe backtest date are separate contracts.
ALTER TABLE feature.bok_macro_daily
    ADD COLUMN IF NOT EXISTS available_from DATE;
UPDATE feature.bok_macro_daily
   SET available_from = CASE
       WHEN series_id IN ('902Y003:010101', '902Y003:010102', '902Y003:010103')
           THEN (date_trunc('month', effective_date) + INTERVAL '1 month')::date
       ELSE effective_date + 1
   END
 WHERE available_from IS NULL;
ALTER TABLE feature.bok_macro_daily
    ALTER COLUMN available_from SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bok_macro_daily_available_from
    ON feature.bok_macro_daily (series_id, available_from DESC);

CREATE TABLE IF NOT EXISTS feature.kis_corporate_action_event (
    event_id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    effective_date DATE NOT NULL,
    event_type TEXT NOT NULL,
    mod_yn TEXT,
    revision_reason TEXT,
    raw_payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_id TEXT REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticker, effective_date, mod_yn, revision_reason)
);
UPDATE feature.kis_corporate_action_event
   SET mod_yn = COALESCE(mod_yn, ''),
       revision_reason = COALESCE(revision_reason, '');
ALTER TABLE feature.kis_corporate_action_event
    ALTER COLUMN mod_yn SET DEFAULT '',
    ALTER COLUMN revision_reason SET DEFAULT '',
    ALTER COLUMN mod_yn SET NOT NULL,
    ALTER COLUMN revision_reason SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_kis_corporate_action_event_ticker_date
    ON feature.kis_corporate_action_event (ticker, effective_date DESC);

-- Migration 002 exposed a different column layout. Drop before recreating so
-- PostgreSQL does not interpret the new availability columns as renames.
DROP VIEW IF EXISTS mart.bok_macro_asof;

CREATE VIEW mart.bok_macro_asof AS
SELECT
    series_id,
    effective_date,
    available_from,
    published_at,
    value,
    metadata_jsonb
FROM feature.bok_macro_daily;

-- Add non-destructive availability/version columns to the compatibility table.
ALTER TABLE feature.dart_financial_quarterly
    ADD COLUMN IF NOT EXISTS available_from DATE;
ALTER TABLE feature.dart_financial_quarterly
    ADD COLUMN IF NOT EXISTS filing_id TEXT;
ALTER TABLE feature.dart_financial_quarterly
    ADD COLUMN IF NOT EXISTS source_payload_hash TEXT;
ALTER TABLE feature.dart_financial_quarterly
    ADD COLUMN IF NOT EXISTS availability_policy TEXT;

UPDATE feature.dart_financial_quarterly
   SET available_from = CASE report_code
       WHEN '11013' THEN period_end + 45
       WHEN '11012' THEN period_end + 45
       WHEN '11014' THEN period_end + 45
       WHEN '11011' THEN make_date(EXTRACT(YEAR FROM period_end)::int + 1, 3, 31)
       ELSE period_end
   END,
       availability_policy = COALESCE(availability_policy, 'conservative_report_deadline'),
       source_payload_hash = COALESCE(
           source_payload_hash,
           md5(symbol_id::text || '|' || period_end::text || '|' || report_code || '|' || fs_div || '|' || accounts_jsonb::text)
       ),
       filing_id = COALESCE(
           filing_id,
           'legacy:' || md5(symbol_id::text || '|' || period_end::text || '|' || report_code || '|' || fs_div || '|' || accounts_jsonb::text)
       );

CREATE INDEX IF NOT EXISTS idx_dart_financial_quarterly_available_from
    ON feature.dart_financial_quarterly (symbol_id, available_from DESC, period_end DESC);

ALTER TABLE raw.dart_response
    ADD COLUMN IF NOT EXISTS business_year INTEGER;
ALTER TABLE raw.dart_response
    ADD COLUMN IF NOT EXISTS fs_div TEXT;
ALTER TABLE raw.dart_response
    ADD COLUMN IF NOT EXISTS request_date DATE;

CREATE TABLE IF NOT EXISTS feature.dart_financial_filing (
    filing_version_id BIGSERIAL PRIMARY KEY,
    symbol_id BIGINT NOT NULL REFERENCES core.symbol_master(symbol_id),
    corp_code TEXT NOT NULL,
    period_end DATE NOT NULL,
    available_from DATE NOT NULL,
    reported_at TIMESTAMPTZ,
    report_code TEXT NOT NULL,
    fs_div TEXT NOT NULL,
    filing_id TEXT NOT NULL,
    source_payload_hash TEXT NOT NULL,
    availability_policy TEXT NOT NULL,
    accounts_jsonb JSONB NOT NULL,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol_id, period_end, report_code, fs_div, source_payload_hash)
);

CREATE INDEX IF NOT EXISTS idx_dart_financial_filing_asof
    ON feature.dart_financial_filing (symbol_id, available_from DESC, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_dart_financial_filing_period
    ON feature.dart_financial_filing (symbol_id, period_end, report_code, fs_div, available_from DESC);

INSERT INTO feature.dart_financial_filing
    (symbol_id, corp_code, period_end, available_from, reported_at, report_code, fs_div,
     filing_id, source_payload_hash, availability_policy, accounts_jsonb, run_id)
SELECT
    symbol_id,
    corp_code,
    period_end,
    COALESCE(available_from, period_end),
    NULL,
    report_code,
    fs_div,
    COALESCE(filing_id, 'legacy:' || source_payload_hash),
    COALESCE(source_payload_hash, md5(accounts_jsonb::text)),
    COALESCE(availability_policy, 'conservative_report_deadline'),
    accounts_jsonb,
    run_id
FROM feature.dart_financial_quarterly
WHERE source_payload_hash IS NOT NULL
ON CONFLICT (symbol_id, period_end, report_code, fs_div, source_payload_hash) DO NOTHING;

CREATE TABLE IF NOT EXISTS feature.dart_financial_account_value (
    filing_version_id BIGINT NOT NULL REFERENCES feature.dart_financial_filing(filing_version_id),
    account_id TEXT NOT NULL,
    account_name TEXT,
    statement_code TEXT,
    amount NUMERIC,
    current_cumulative_amount NUMERIC,
    prior_quarter_amount NUMERIC,
    prior_amount NUMERIC,
    prior_year_amount NUMERIC,
    currency TEXT,
    raw_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (filing_version_id, account_id)
);

INSERT INTO feature.dart_financial_account_value
    (filing_version_id, account_id, account_name, statement_code, amount, raw_jsonb)
SELECT
    f.filing_version_id,
    item.key,
    item.value->>'account_name',
    item.value->>'sj_nm',
    CASE
        WHEN item.value->>'amount' ~ '^-?[0-9]+(\.[0-9]+)?$'
            THEN (item.value->>'amount')::numeric
        ELSE NULL
    END,
    COALESCE(item.value->'raw', '{}'::jsonb)
FROM feature.dart_financial_filing f
CROSS JOIN LATERAL jsonb_each(f.accounts_jsonb) item
ON CONFLICT (filing_version_id, account_id) DO NOTHING;

-- Some installations contain a table under the legacy compatibility name.
-- Preserve non-view objects under a legacy name before creating the canonical view.
DO $$
DECLARE
    object_kind TEXT;
BEGIN
    SELECT c.relkind::text
      INTO object_kind
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'mart'
       AND c.relname = 'dart_financial_asof';

    IF object_kind = 'v' THEN
        EXECUTE 'DROP VIEW mart.dart_financial_asof';
    ELSIF object_kind = 'm' THEN
        IF EXISTS (
            SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'mart'
               AND c.relname = 'dart_financial_asof_legacy'
        ) THEN
            RAISE EXCEPTION 'mart.dart_financial_asof_legacy already exists';
        END IF;
        EXECUTE 'ALTER MATERIALIZED VIEW mart.dart_financial_asof RENAME TO dart_financial_asof_legacy';
    ELSIF object_kind IN ('r', 'p', 'f') THEN
        IF EXISTS (
            SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'mart'
               AND c.relname = 'dart_financial_asof_legacy'
        ) THEN
            RAISE EXCEPTION 'mart.dart_financial_asof_legacy already exists';
        END IF;
        EXECUTE 'ALTER TABLE mart.dart_financial_asof RENAME TO dart_financial_asof_legacy';
    ELSIF object_kind IS NOT NULL THEN
        RAISE EXCEPTION 'mart.dart_financial_asof has unsupported relation kind %', object_kind;
    END IF;
END $$;

CREATE VIEW mart.dart_financial_asof AS
SELECT
    sm.symbol,
    f.corp_code,
    f.period_end,
    f.available_from,
    f.report_code,
    f.fs_div,
    f.accounts_jsonb,
    f.filing_id,
    f.source_payload_hash,
    f.filing_version_id
FROM feature.dart_financial_filing f
JOIN core.symbol_master sm ON sm.symbol_id = f.symbol_id;

CREATE OR REPLACE VIEW mart.dart_financial_latest AS
SELECT DISTINCT ON (symbol_id, period_end, report_code, fs_div)
    symbol_id,
    corp_code,
    period_end,
    available_from,
    reported_at,
    report_code,
    fs_div,
    filing_id,
    source_payload_hash,
    accounts_jsonb,
    filing_version_id
FROM feature.dart_financial_filing
ORDER BY symbol_id, period_end, report_code, fs_div, available_from DESC, filing_version_id DESC;

-- Migration 002 creates this reader role, but existing databases may have
-- skipped that role-only block while retaining the data-engineering schema.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'backtest_reader') THEN
        EXECUTE 'CREATE ROLE backtest_reader NOLOGIN';
    END IF;
END $$;

GRANT SELECT ON mart.dart_financial_latest TO backtest_reader;

COMMENT ON COLUMN feature.bok_macro_daily.available_from IS
    'First safe backtest date. It is deliberately conservative when ECOS release time is unavailable.';
COMMENT ON TABLE feature.wics_symbol_sector_history IS
    'Point-in-time WICS membership intervals; current symbol_master.sector is only a cache.';
COMMENT ON TABLE feature.dart_financial_filing IS
    'Versioned OpenDART CFS filings. Each distinct source payload is retained for as-of selection.';
COMMENT ON VIEW mart.dart_financial_asof IS
    'All DART filing versions with available_from; consumers must filter available_from <= as_of_date and select the latest period version.';

COMMIT;
