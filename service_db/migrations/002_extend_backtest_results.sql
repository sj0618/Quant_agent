-- Extend backtest result storage for planned performance metrics.
-- Scalar metrics live on app.backtest_summary; structured and time-series
-- metrics live in app.backtest_metric_detail.

BEGIN;

ALTER TABLE app.backtest_summary
    ADD COLUMN IF NOT EXISTS avg_negative_period_return numeric(20,10),
    ADD COLUMN IF NOT EXISTS avg_period_return numeric(20,10),
    ADD COLUMN IF NOT EXISTS avg_positive_period_return numeric(20,10),
    ADD COLUMN IF NOT EXISTS best_period_return numeric(20,10),
    ADD COLUMN IF NOT EXISTS worst_period_return numeric(20,10),
    ADD COLUMN IF NOT EXISTS cagr numeric(20,10),
    ADD COLUMN IF NOT EXISTS calmar_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS common_sense_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS expected_return numeric(20,10),
    ADD COLUMN IF NOT EXISTS geometric_mean numeric(20,10),
    ADD COLUMN IF NOT EXISTS gain_to_pain_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS recovery_factor numeric(20,10),
    ADD COLUMN IF NOT EXISTS rar numeric(20,10),
    ADD COLUMN IF NOT EXISTS conditional_value_at_risk numeric(20,10),
    ADD COLUMN IF NOT EXISTS value_at_risk numeric(20,10),
    ADD COLUMN IF NOT EXISTS annualized_volatility numeric(20,10),
    ADD COLUMN IF NOT EXISTS kurtosis numeric(20,10),
    ADD COLUMN IF NOT EXISTS skew numeric(20,10),
    ADD COLUMN IF NOT EXISTS risk_of_ruin numeric(20,10),
    ADD COLUMN IF NOT EXISTS risk_return_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS tail_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS ulcer_index numeric(20,10),
    ADD COLUMN IF NOT EXISTS ulcer_performance_index numeric(20,10),
    ADD COLUMN IF NOT EXISTS consecutive_negative_periods integer,
    ADD COLUMN IF NOT EXISTS consecutive_positive_periods integer,
    ADD COLUMN IF NOT EXISTS cpc_index numeric(20,10),
    ADD COLUMN IF NOT EXISTS exposure numeric(20,10),
    ADD COLUMN IF NOT EXISTS kelly_criterion numeric(20,10),
    ADD COLUMN IF NOT EXISTS outlier_loss_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS outlier_win_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS payoff_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS profit_factor numeric(20,10),
    ADD COLUMN IF NOT EXISTS period_win_rate numeric(20,10),
    ADD COLUMN IF NOT EXISTS information_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS r_squared numeric(20,10),
    ADD COLUMN IF NOT EXISTS sortino_ratio numeric(20,10),
    ADD COLUMN IF NOT EXISTS adjusted_sortino_ratio numeric(20,10);

CREATE TABLE IF NOT EXISTS app.backtest_metric_detail (
    run_id uuid NOT NULL,
    compare_jsonb jsonb,
    compsum_jsonb jsonb,
    drawdown_details_jsonb jsonb,
    drawdown_series_jsonb jsonb,
    greeks_jsonb jsonb,
    rolling_greeks_jsonb jsonb,
    monthly_returns_jsonb jsonb,
    montecarlo_jsonb jsonb,
    montecarlo_cagr_jsonb jsonb,
    montecarlo_drawdown_jsonb jsonb,
    montecarlo_sharpe_jsonb jsonb,
    outliers_jsonb jsonb,
    created_at timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY (run_id),
    CONSTRAINT backtest_metric_detail_run_id_fkey
        FOREIGN KEY (run_id)
        REFERENCES app.backtest_run(run_id)
        ON DELETE CASCADE
);

COMMENT ON COLUMN app.backtest_summary.win_rate IS
    'Profitable closed trades divided by total closed trades.';
COMMENT ON COLUMN app.backtest_summary.period_win_rate IS
    'Positive return periods divided by total observed return periods.';
COMMENT ON COLUMN app.backtest_summary.sharpe_ratio IS
    'Annualized Sharpe ratio calculated from daily portfolio returns.';
COMMENT ON COLUMN app.backtest_summary.period_return IS
    'Total compounded return over the complete backtest period.';
COMMENT ON TABLE app.backtest_metric_detail IS
    'Structured, array, matrix, and time-series metrics for one backtest run.';

COMMIT;
