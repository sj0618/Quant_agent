-- Store strategy report pages, email report details, delivery history,
-- and daily email digest strategy subscriptions used by the FE report routes.

BEGIN;

CREATE TABLE IF NOT EXISTS app.strategy_report_profile (
    strategy_id text NOT NULL,
    name text NOT NULL,
    description text,
    universe text,
    timeframe text DEFAULT 'daily'::text NOT NULL,
    entry_summary text,
    exit_summary text,
    risk_summary text,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY (strategy_id),
    CONSTRAINT strategy_report_profile_strategy_id_fkey
        FOREIGN KEY (strategy_id)
        REFERENCES app.strategy(strategy_id)
        ON DELETE CASCADE,
    CONSTRAINT strategy_report_profile_tags_array_check
        CHECK (jsonb_typeof(tags) = 'array')
);

CREATE TABLE IF NOT EXISTS app.strategy_email_report (
    report_id text NOT NULL,
    strategy_id text NOT NULL,
    backtest_run_id uuid,
    ai_report_id uuid,
    report_date date NOT NULL,
    weekday text,
    sent_at timestamptz,
    title text NOT NULL,
    summary text,
    status text DEFAULT 'draft'::text NOT NULL,
    recommendation_score numeric(4,2),
    buy_count integer DEFAULT 0 NOT NULL,
    hold_count integer DEFAULT 0 NOT NULL,
    drop_count integer DEFAULT 0 NOT NULL,
    market_snapshot jsonb DEFAULT '[]'::jsonb NOT NULL,
    recipient text,
    market_brief text,
    market_context text,
    risk_manager_override text,
    conclusion text,
    warning_note text,
    signal_axes_jsonb jsonb DEFAULT '[]'::jsonb NOT NULL,
    performance_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    cost_notes jsonb DEFAULT '[]'::jsonb NOT NULL,
    content_md text,
    content_html text,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY (report_id),
    CONSTRAINT strategy_email_report_strategy_id_fkey
        FOREIGN KEY (strategy_id)
        REFERENCES app.strategy_report_profile(strategy_id)
        ON DELETE CASCADE,
    CONSTRAINT strategy_email_report_backtest_run_id_fkey
        FOREIGN KEY (backtest_run_id)
        REFERENCES app.backtest_run(run_id)
        ON DELETE SET NULL,
    CONSTRAINT strategy_email_report_ai_report_id_fkey
        FOREIGN KEY (ai_report_id)
        REFERENCES app.ai_backtest_report(report_id)
        ON DELETE SET NULL,
    CONSTRAINT strategy_email_report_status_check
        CHECK (status = ANY (ARRAY['sent'::text, 'draft'::text, 'failed'::text, 'resent'::text])),
    CONSTRAINT strategy_email_report_recommendation_score_check
        CHECK (recommendation_score IS NULL OR (recommendation_score >= 0::numeric AND recommendation_score <= 10::numeric)),
    CONSTRAINT strategy_email_report_signal_counts_check
        CHECK (buy_count >= 0 AND hold_count >= 0 AND drop_count >= 0),
    CONSTRAINT strategy_email_report_market_snapshot_array_check
        CHECK (jsonb_typeof(market_snapshot) = 'array'),
    CONSTRAINT strategy_email_report_signal_axes_array_check
        CHECK (jsonb_typeof(signal_axes_jsonb) = 'array'),
    CONSTRAINT strategy_email_report_performance_object_check
        CHECK (jsonb_typeof(performance_jsonb) = 'object'),
    CONSTRAINT strategy_email_report_cost_notes_array_check
        CHECK (jsonb_typeof(cost_notes) = 'array')
);

CREATE TABLE IF NOT EXISTS app.strategy_email_report_news (
    report_id text NOT NULL,
    rank integer NOT NULL,
    title text NOT NULL,
    source text,
    tone text DEFAULT 'neutral'::text NOT NULL,
    url text,
    published_at timestamptz,
    summary text,
    created_at timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY (report_id, rank),
    CONSTRAINT strategy_email_report_news_report_id_fkey
        FOREIGN KEY (report_id)
        REFERENCES app.strategy_email_report(report_id)
        ON DELETE CASCADE,
    CONSTRAINT strategy_email_report_news_rank_check
        CHECK (rank > 0),
    CONSTRAINT strategy_email_report_news_tone_check
        CHECK (tone = ANY (ARRAY['positive'::text, 'warning'::text, 'negative'::text, 'neutral'::text, 'info'::text]))
);

CREATE TABLE IF NOT EXISTS app.strategy_email_report_candidate (
    report_id text NOT NULL,
    ticker text NOT NULL,
    name text,
    sector text,
    signal text NOT NULL,
    confidence numeric(8,4),
    score numeric(8,4),
    price text,
    change_percent text,
    rationale text,
    evidence_jsonb jsonb DEFAULT '[]'::jsonb NOT NULL,
    risk_reasons_jsonb jsonb DEFAULT '[]'::jsonb NOT NULL,
    risk_manager_override text,
    web_projection text,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY (report_id, ticker),
    CONSTRAINT strategy_email_report_candidate_report_id_fkey
        FOREIGN KEY (report_id)
        REFERENCES app.strategy_email_report(report_id)
        ON DELETE CASCADE,
    CONSTRAINT strategy_email_report_candidate_signal_check
        CHECK (signal = ANY (ARRAY['BUY'::text, 'HOLD'::text, 'DROP'::text])),
    CONSTRAINT strategy_email_report_candidate_confidence_check
        CHECK (confidence IS NULL OR (confidence >= 0::numeric AND confidence <= 1::numeric)),
    CONSTRAINT strategy_email_report_candidate_evidence_array_check
        CHECK (jsonb_typeof(evidence_jsonb) = 'array'),
    CONSTRAINT strategy_email_report_candidate_risk_reasons_array_check
        CHECK (jsonb_typeof(risk_reasons_jsonb) = 'array')
);

CREATE TABLE IF NOT EXISTS app.email_digest_subscription (
    user_id bigint NOT NULL,
    strategy_id text NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY (user_id, strategy_id),
    CONSTRAINT email_digest_subscription_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES app.users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT email_digest_subscription_strategy_id_fkey
        FOREIGN KEY (strategy_id)
        REFERENCES app.strategy_report_profile(strategy_id)
        ON DELETE CASCADE
);

CREATE OR REPLACE FUNCTION app.enforce_email_digest_subscription_limit()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF (
        SELECT count(*)
        FROM app.email_digest_subscription
        WHERE user_id = NEW.user_id
    ) >= 3 THEN
        RAISE EXCEPTION 'email digest subscription limit exceeded for user_id %', NEW.user_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_email_digest_subscription_limit'
    ) THEN
        CREATE TRIGGER trg_email_digest_subscription_limit
        BEFORE INSERT ON app.email_digest_subscription
        FOR EACH ROW
        EXECUTE FUNCTION app.enforce_email_digest_subscription_limit();
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS app.email_delivery_history (
    delivery_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id bigint,
    report_id text,
    strategy_id text,
    recipient_email text NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    sent_at timestamptz,
    provider text,
    provider_message_id text,
    error_message text,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    PRIMARY KEY (delivery_id),
    CONSTRAINT email_delivery_history_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES app.users(user_id)
        ON DELETE SET NULL,
    CONSTRAINT email_delivery_history_report_id_fkey
        FOREIGN KEY (report_id)
        REFERENCES app.strategy_email_report(report_id)
        ON DELETE SET NULL,
    CONSTRAINT email_delivery_history_strategy_id_fkey
        FOREIGN KEY (strategy_id)
        REFERENCES app.strategy_report_profile(strategy_id)
        ON DELETE SET NULL,
    CONSTRAINT email_delivery_history_status_check
        CHECK (status = ANY (ARRAY['sent'::text, 'draft'::text, 'failed'::text, 'resent'::text])),
    CONSTRAINT email_delivery_history_metadata_object_check
        CHECK (jsonb_typeof(metadata_jsonb) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_strategy_report_profile_updated
    ON app.strategy_report_profile USING btree (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_email_report_strategy_date
    ON app.strategy_email_report USING btree (strategy_id, report_date DESC, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_email_report_status
    ON app.strategy_email_report USING btree (status);
CREATE INDEX IF NOT EXISTS idx_strategy_email_report_backtest_run
    ON app.strategy_email_report USING btree (backtest_run_id);
CREATE INDEX IF NOT EXISTS idx_strategy_email_report_ai_report
    ON app.strategy_email_report USING btree (ai_report_id);
CREATE INDEX IF NOT EXISTS idx_strategy_email_report_news_report
    ON app.strategy_email_report_news USING btree (report_id, rank);
CREATE INDEX IF NOT EXISTS idx_strategy_email_report_candidate_report
    ON app.strategy_email_report_candidate USING btree (report_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_email_digest_subscription_user
    ON app.email_digest_subscription USING btree (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_delivery_history_user_sent
    ON app.email_delivery_history USING btree (user_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_delivery_history_report
    ON app.email_delivery_history USING btree (report_id);

CREATE OR REPLACE VIEW app.strategy_report_summary_v AS
SELECT DISTINCT ON (profile.strategy_id)
    profile.strategy_id AS id,
    profile.name,
    profile.description,
    profile.universe,
    profile.timeframe,
    profile.entry_summary,
    profile.exit_summary,
    profile.risk_summary,
    latest.sent_at AS latest_sent_at,
    latest.report_date AS latest_report_date,
    latest.status AS latest_status,
    latest.report_id AS latest_email_report_id,
    latest.recommendation_score,
    jsonb_build_object(
        'BUY', COALESCE(latest.buy_count, 0),
        'HOLD', COALESCE(latest.hold_count, 0),
        'DROP', COALESCE(latest.drop_count, 0)
    ) AS signals,
    latest.summary,
    profile.tags
FROM app.strategy_report_profile profile
LEFT JOIN app.strategy_email_report latest
    ON latest.strategy_id = profile.strategy_id
ORDER BY profile.strategy_id, latest.report_date DESC NULLS LAST, latest.sent_at DESC NULLS LAST;

CREATE OR REPLACE VIEW app.email_digest_history_v AS
SELECT
    ('history:'::text || delivery.delivery_id::text) AS id,
    report.report_id,
    COALESCE(report.strategy_id, delivery.strategy_id) AS strategy_id,
    profile.name AS strategy_name,
    report.report_date,
    delivery.sent_at,
    delivery.status,
    report.title,
    delivery.user_id,
    delivery.recipient_email
FROM app.email_delivery_history delivery
LEFT JOIN app.strategy_email_report report
    ON report.report_id = delivery.report_id
LEFT JOIN app.strategy_report_profile profile
    ON profile.strategy_id = COALESCE(report.strategy_id, delivery.strategy_id);

COMMENT ON TABLE app.strategy_report_profile IS
    'Display profile for strategy report list and strategy detail pages.';
COMMENT ON TABLE app.strategy_email_report IS
    'Generated email report content and summary for a strategy on one report date.';
COMMENT ON COLUMN app.strategy_email_report.backtest_run_id IS
    'Optional source backtest run used to generate this immutable report snapshot.';
COMMENT ON COLUMN app.strategy_email_report.ai_report_id IS
    'Optional source AI backtest report used to generate this email report.';
COMMENT ON TABLE app.strategy_email_report_news IS
    'Ranked news and market context items embedded in one email report.';
COMMENT ON TABLE app.strategy_email_report_candidate IS
    'Ticker-level candidates embedded in one email report.';
COMMENT ON TABLE app.email_digest_subscription IS
    'User-selected strategies for the daily email digest; application must enforce max three strategies per user.';
COMMENT ON TABLE app.email_delivery_history IS
    'Per-recipient email delivery audit trail for /me email history.';

COMMIT;
