-- QuantAgent service DB app schema
-- Generated from current PostgreSQL app schema.
-- Review before applying to a fresh environment.

CREATE SCHEMA IF NOT EXISTS app;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SEQUENCE IF NOT EXISTS app.users_user_id_seq;
CREATE SEQUENCE IF NOT EXISTS app.backtest_trade_trade_id_seq;
CREATE SEQUENCE IF NOT EXISTS app.backtest_signal_signal_id_seq;

CREATE TABLE IF NOT EXISTS app."users" (
    "user_id" bigint DEFAULT nextval('app.users_user_id_seq'::regclass) NOT NULL,
    "email" text,
    "name" text,
    "profile_image_url" text,
    "password_hash" text,
    "auth_provider" text,
    "provider_user_id" text,
    "created_at" timestamptz DEFAULT now() NOT NULL,
    "updated_at" timestamptz DEFAULT now() NOT NULL,
    "last_login_at" timestamptz,
    PRIMARY KEY ("user_id")
);

CREATE TABLE IF NOT EXISTS app."strategy" (
    "strategy_id" text NOT NULL,
    "schema_version" text DEFAULT '1.0.0'::text NOT NULL,
    "strategy_name" text NOT NULL,
    "description" text,
    "user_id" bigint,
    "market" text DEFAULT 'KRX'::text NOT NULL,
    "asset_type" text DEFAULT 'equity'::text NOT NULL,
    "lifecycle" text DEFAULT 'provisional'::text NOT NULL,
    "fit_confidence" numeric(4,3),
    "spec_jsonb" jsonb NOT NULL,
    "created_at" timestamptz DEFAULT now() NOT NULL,
    "updated_at" timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY ("strategy_id")
);

CREATE TABLE IF NOT EXISTS app."backtest_run" (
    "run_id" uuid DEFAULT gen_random_uuid() NOT NULL,
    "strategy_id" text NOT NULL,
    "user_id" bigint,
    "initial_capital" numeric(20,6) DEFAULT 100000000 NOT NULL,
    "max_tickers" integer,
    "talib_mode" text DEFAULT 'required'::text,
    "config_jsonb" jsonb,
    "status" text DEFAULT 'pending'::text NOT NULL,
    "started_at" timestamptz,
    "ended_at" timestamptz,
    "error_message" text,
    "output_paths_jsonb" jsonb,
    "created_at" timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY ("run_id")
);

CREATE TABLE IF NOT EXISTS app."backtest_equity_point" (
    "run_id" uuid NOT NULL,
    "trade_date" date NOT NULL,
    "cash" numeric(20,6) NOT NULL,
    "positions_value" numeric(20,6) NOT NULL,
    "total_equity" numeric(20,6) NOT NULL,
    "daily_return" numeric(20,10),
    PRIMARY KEY ("run_id", "trade_date")
);

CREATE TABLE IF NOT EXISTS app."backtest_trade" (
    "trade_id" bigint DEFAULT nextval('app.backtest_trade_trade_id_seq'::regclass) NOT NULL,
    "run_id" uuid NOT NULL,
    "ticker" text NOT NULL,
    "entry_date" date NOT NULL,
    "exit_date" date NOT NULL,
    "entry_price" numeric(20,6) NOT NULL,
    "exit_price" numeric(20,6) NOT NULL,
    "quantity" bigint NOT NULL,
    "entry_cost" numeric(20,6) DEFAULT 0 NOT NULL,
    "exit_cost" numeric(20,6) DEFAULT 0 NOT NULL,
    "gross_pnl" numeric(20,6) NOT NULL,
    "net_pnl" numeric(20,6) NOT NULL,
    "return_pct" numeric(20,10),
    "reason" text NOT NULL,
    "created_at" timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY ("trade_id")
);

CREATE TABLE IF NOT EXISTS app."backtest_signal" (
    "signal_id" bigint DEFAULT nextval('app.backtest_signal_signal_id_seq'::regclass) NOT NULL,
    "run_id" uuid NOT NULL,
    "signal_date" date NOT NULL,
    "ticker" text NOT NULL,
    "action" text NOT NULL,
    "reasons" jsonb DEFAULT '[]'::jsonb NOT NULL,
    "matching_entry_rules" jsonb DEFAULT '[]'::jsonb NOT NULL,
    "matching_exit_rules" jsonb DEFAULT '[]'::jsonb NOT NULL,
    "created_at" timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY ("signal_id")
);

CREATE TABLE IF NOT EXISTS app."backtest_summary" (
    "run_id" uuid NOT NULL,
    "final_equity" numeric(20,6) NOT NULL,
    "final_cash" numeric(20,6) NOT NULL,
    "open_positions" integer DEFAULT 0 NOT NULL,
    "period_return" numeric(20,10),
    "max_drawdown" numeric(20,10),
    "sharpe_ratio" numeric(20,10),
    "win_rate" numeric(20,10),
    "trade_count" integer DEFAULT 0 NOT NULL,
    "signal_count" integer DEFAULT 0 NOT NULL,
    "avg_holding_days" numeric(10,2),
    "excluded_ticker_count" integer DEFAULT 0 NOT NULL,
    "excluded_tickers_jsonb" jsonb DEFAULT '[]'::jsonb,
    "indicator_report_jsonb" jsonb,
    "cost_model_jsonb" jsonb,
    "position_sizing_jsonb" jsonb,
    "created_at" timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY ("run_id")
);

ALTER TABLE app."backtest_equity_point" ADD CONSTRAINT "backtest_equity_point_run_id_fkey" FOREIGN KEY (run_id) REFERENCES app.backtest_run(run_id) ON DELETE CASCADE;
ALTER TABLE app."backtest_run" ADD CONSTRAINT "backtest_run_status_check" CHECK (status = ANY (ARRAY['pending'::text, 'running'::text, 'done'::text, 'failed'::text]));
ALTER TABLE app."backtest_run" ADD CONSTRAINT "backtest_run_talib_mode_check" CHECK (talib_mode = ANY (ARRAY['required'::text, 'all'::text, 'none'::text]));
ALTER TABLE app."backtest_run" ADD CONSTRAINT "backtest_run_strategy_id_fkey" FOREIGN KEY (strategy_id) REFERENCES app.strategy(strategy_id) ON DELETE CASCADE;
ALTER TABLE app."backtest_run" ADD CONSTRAINT "backtest_run_user_id_fkey" FOREIGN KEY (user_id) REFERENCES app.users(user_id) ON DELETE SET NULL;
ALTER TABLE app."backtest_signal" ADD CONSTRAINT "backtest_signal_action_check" CHECK (action = ANY (ARRAY['buy'::text, 'sell'::text, 'hold'::text, 'watch'::text, 'filtered_out'::text]));
ALTER TABLE app."backtest_signal" ADD CONSTRAINT "backtest_signal_run_id_fkey" FOREIGN KEY (run_id) REFERENCES app.backtest_run(run_id) ON DELETE CASCADE;
ALTER TABLE app."backtest_summary" ADD CONSTRAINT "backtest_summary_run_id_fkey" FOREIGN KEY (run_id) REFERENCES app.backtest_run(run_id) ON DELETE CASCADE;
ALTER TABLE app."backtest_trade" ADD CONSTRAINT "backtest_trade_quantity_check" CHECK (quantity > 0);
ALTER TABLE app."backtest_trade" ADD CONSTRAINT "backtest_trade_run_id_fkey" FOREIGN KEY (run_id) REFERENCES app.backtest_run(run_id) ON DELETE CASCADE;
ALTER TABLE app."strategy" ADD CONSTRAINT "strategy_asset_type_check" CHECK (asset_type = ANY (ARRAY['equity'::text, 'etf'::text, 'sector'::text, 'index'::text]));
ALTER TABLE app."strategy" ADD CONSTRAINT "strategy_fit_confidence_check" CHECK (fit_confidence >= 0::numeric AND fit_confidence <= 1::numeric);
ALTER TABLE app."strategy" ADD CONSTRAINT "strategy_lifecycle_check" CHECK (lifecycle = ANY (ARRAY['confirmed'::text, 'provisional'::text, 'rejected'::text]));
ALTER TABLE app."strategy" ADD CONSTRAINT "strategy_market_check" CHECK (market = 'KRX'::text);
ALTER TABLE app."strategy" ADD CONSTRAINT "strategy_user_id_fkey" FOREIGN KEY (user_id) REFERENCES app.users(user_id) ON DELETE CASCADE;
ALTER TABLE app."users" ADD CONSTRAINT "users_auth_provider_check" CHECK (auth_provider IS NULL OR (auth_provider = ANY (ARRAY['kakao'::text, 'google'::text, 'naver'::text, 'apple'::text])));
ALTER TABLE app."users" ADD CONSTRAINT "users_check" CHECK (password_hash IS NOT NULL OR auth_provider IS NOT NULL);
ALTER TABLE app."users" ADD CONSTRAINT "users_auth_provider_provider_user_id_key" UNIQUE (auth_provider, provider_user_id);

CREATE INDEX IF NOT EXISTS idx_equity_point_run_date ON app.backtest_equity_point USING btree (run_id, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_run_status ON app.backtest_run USING btree (status);
CREATE INDEX IF NOT EXISTS idx_backtest_run_strategy ON app.backtest_run USING btree (strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_signal_run ON app.backtest_signal USING btree (run_id, signal_date);
CREATE INDEX IF NOT EXISTS idx_backtest_signal_ticker ON app.backtest_signal USING btree (ticker, signal_date);
CREATE INDEX IF NOT EXISTS idx_backtest_trade_run ON app.backtest_trade USING btree (run_id, exit_date);
CREATE INDEX IF NOT EXISTS idx_backtest_trade_ticker ON app.backtest_trade USING btree (ticker, exit_date);
CREATE INDEX IF NOT EXISTS idx_strategy_lifecycle ON app.strategy USING btree (lifecycle);
CREATE INDEX IF NOT EXISTS idx_strategy_user ON app.strategy USING btree (user_id, created_at DESC);
