-- Re-seal the KRX exploration policy after the strategy blueprint catalog gained
-- value/quality/growth/multi-factor rows (per/roe/operating_margin/debt_to_equity and
-- the fundamental up-streaks) alongside the existing price-only technical rows.
--
-- The sealed exploration policy pins the catalog fingerprint, and the runtime rejects a
-- stale seal (exploration_catalog_hash_stale) whenever the seeded catalog_hash no longer
-- equals strategy_blueprint_catalog_fingerprint().  Migration 025 sealed the 56-row
-- catalog (b8392766...); the catalog now fingerprints as a3694022... , so this migration
-- publishes a new immutable policy version carrying the current fingerprint and repoints
-- the KRX active pointer to it.
--
-- Additive and immutable-safe: app.ai_exploration_policy has a BEFORE UPDATE/DELETE
-- reject trigger (see 025), so the prior 2026-09-01 row is left untouched and a new
-- version row is inserted; only the mutable app.ai_active_exploration_policy pointer is
-- updated.  No schema objects are created or altered, so the fixed-replay catalog-union
-- fingerprint is unchanged.

BEGIN;

INSERT INTO app.ai_exploration_policy (
    policy_version, market, policy_hash, policy_jsonb, publication_status, effective_at
) VALUES (
    'exploration-policy-v2.krx.2026-09-03',
    'KRX',
    '86971de4ac92b1c6177ef64c3446a2f75881a587e6d07c38fc67329972b1bf1f',
    '{"benchmark":"official_krx_total_return","candidate_count":3,"catalog_hash":"a36940228b4b6a4000ba3bae7bf2ffec274850e074896f308b35ccd06a084329","catalog_version":"quant-blueprints.v2","cost_model":{"commission_pct":0.00015,"slippage_pct":0.001,"tax_pct":0.0023},"history_years":5,"investment_horizon":"medium","long_only":true,"market":"KRX","max_positions":20,"policy_version":"exploration-policy-v2.krx.2026-09-03","publication_status":"published","rebalance_interval_days":21,"risk_style":"balanced","schema_version":"exploration-policy.v2","stop_loss_pct":0.2,"take_profit_pct":10.0,"timeframe":"daily","trailing_stop_pct":0.25,"validation":{"evaluation_months":1,"method":"rolling_walk_forward","minimum_evaluation_sessions":480,"roll_months":1,"train_months":12,"validation_months":3}}'::jsonb,
    'published',
    '2026-09-03T00:00:00+09:00'::timestamptz
) ON CONFLICT (policy_version) DO NOTHING;

INSERT INTO app.ai_active_exploration_policy (market, policy_version)
VALUES ('KRX', 'exploration-policy-v2.krx.2026-09-03')
ON CONFLICT (market) DO UPDATE
    SET policy_version = EXCLUDED.policy_version,
        updated_at = now();

COMMIT;
