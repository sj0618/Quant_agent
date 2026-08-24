-- Official KRX total-return benchmark inputs for the AI backtest.
--
-- The AI acceptance gate for automatic strategies compares a run against the official
-- KOSPI/KOSDAQ total-return benchmark. Two facts are needed and neither existed in this
-- warehouse: the daily total-return index levels, and the monthly KOSPI/KOSDAQ split the
-- benchmark rebalances to. Price-return indices are deliberately not part of the contract
-- - a dividend-stripped index understates what a strategy has to beat.
--
-- Reader contract: ai/docs/official-krx-tr-benchmark-contract.md.

CREATE TABLE IF NOT EXISTS core.index_total_return_daily (
    index_code TEXT NOT NULL,
    trade_date DATE NOT NULL,
    tr_value NUMERIC(20, 6) NOT NULL,
    source_id TEXT REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (index_code, trade_date),
    CONSTRAINT index_total_return_daily_value_positive CHECK (tr_value > 0)
);

CREATE INDEX IF NOT EXISTS idx_index_total_return_daily_date
    ON core.index_total_return_daily (trade_date, index_code);

COMMENT ON TABLE core.index_total_return_daily IS
  'Official KRX total-return index closes (dividends reinvested). index_code is KRX''s published code: KOSPI_TR, KOSDAQ_TR.';
COMMENT ON COLUMN core.index_total_return_daily.tr_value IS
  'Index level, not a return. Only ratios between two sessions are read, so the base value of the series is free.';
COMMENT ON COLUMN core.index_total_return_daily.trade_date IS
  'KRX session date. Must line up with core.trading_calendar; a session with no row lowers benchmark coverage.';

-- One row per calendar month, holding the split observed over that month. The one-month
-- lag is applied by the reader, not stored here: storing an already-lagged number would
-- hide which month the observation came from and make a re-lag impossible to audit.
CREATE TABLE IF NOT EXISTS core.index_benchmark_weight_monthly (
    month DATE NOT NULL,
    kospi_weight NUMERIC(12, 10) NOT NULL,
    kosdaq_weight NUMERIC(12, 10) NOT NULL,
    basis TEXT NOT NULL DEFAULT 'month_end_market_capitalization',
    source_id TEXT REFERENCES meta.data_source(source_id),
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (month),
    CONSTRAINT index_benchmark_weight_monthly_month_is_first_day
        CHECK (EXTRACT(DAY FROM month) = 1),
    CONSTRAINT index_benchmark_weight_monthly_non_negative
        CHECK (kospi_weight >= 0 AND kosdaq_weight >= 0),
    CONSTRAINT index_benchmark_weight_monthly_sums_to_one
        CHECK (abs(kospi_weight + kosdaq_weight - 1) <= 0.000001)
);

COMMENT ON TABLE core.index_benchmark_weight_monthly IS
  'Monthly KOSPI/KOSDAQ benchmark split, stored unlagged. The AI reader rebalances month M on month M-1''s row.';
COMMENT ON COLUMN core.index_benchmark_weight_monthly.month IS
  'First calendar day of the observed month. The weights are the split as of that month''s last session.';
COMMENT ON COLUMN core.index_benchmark_weight_monthly.basis IS
  'How the split was measured, e.g. month_end_market_capitalization. Recorded so a basis change is visible.';

CREATE OR REPLACE VIEW mart.krx_index_total_return_daily AS
SELECT
    index_code,
    trade_date,
    tr_value
FROM core.index_total_return_daily;

CREATE OR REPLACE VIEW mart.krx_benchmark_monthly_weights AS
SELECT
    month,
    kospi_weight,
    kosdaq_weight,
    basis
FROM core.index_benchmark_weight_monthly;

COMMENT ON VIEW mart.krx_index_total_return_daily IS
  'Read contract for the AI backtest primary benchmark: official KOSPI_TR/KOSDAQ_TR daily levels.';
COMMENT ON VIEW mart.krx_benchmark_monthly_weights IS
  'Read contract for the AI backtest primary benchmark: unlagged monthly KOSPI/KOSDAQ split.';
