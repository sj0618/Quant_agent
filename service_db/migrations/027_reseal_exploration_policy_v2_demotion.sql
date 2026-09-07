-- Re-seal the KRX exploration policy after ten catalogue rows were demoted.
--
-- Two non-overlapping five-year walk-forward measurements on the production evaluator
-- (2016-09-05..2021-09-03 and 2021-09-06..2026-09-04, KOSPI/KOSDAQ top-100 traded
-- universe, 45 folds each; 진행상황-수익률검증-수정-2026-09-07.md §8) put ten rows in the
-- bottom third of the catalogue in BOTH windows. Their default_priority was lowered by
-- 40 and a caveat added; formulas and parameters are untouched. The sealed policy pins
-- the catalogue fingerprint, so the runtime rejects the 2026-09-03 seal
-- (exploration_catalog_hash_stale) until this row is published and the KRX pointer moves.
--
-- Additive and immutable-safe, exactly like 025/026: a new version row is inserted and
-- only the mutable app.ai_active_exploration_policy pointer is updated. No schema objects
-- are created or altered.

BEGIN;

INSERT INTO app.ai_exploration_policy (
    policy_version, market, policy_hash, policy_jsonb, publication_status, effective_at
) VALUES (
    'exploration-policy-v2.krx.2026-09-07',
    'KRX',
    'bbd4828b8e1cc1fe38973aab51de81c57283bc14205d121e8a1e223ce177ea61',
    '{"benchmark":"official_krx_total_return","candidate_count":3,"catalog_hash":"7b0707f928425ffcadefb4ec7e6ca215fc36a7b612f7f6b399e0a525d27a226e","catalog_version":"quant-blueprints.v2","cost_model":{"commission_pct":0.00015,"slippage_pct":0.001,"tax_pct":0.0023},"history_years":5,"investment_horizon":"medium","long_only":true,"market":"KRX","max_positions":20,"policy_version":"exploration-policy-v2.krx.2026-09-07","publication_status":"published","rebalance_interval_days":21,"risk_style":"balanced","schema_version":"exploration-policy.v2","stop_loss_pct":0.2,"take_profit_pct":10.0,"timeframe":"daily","trailing_stop_pct":0.25,"validation":{"evaluation_months":1,"method":"rolling_walk_forward","minimum_evaluation_sessions":480,"roll_months":1,"train_months":12,"validation_months":3}}'::jsonb,
    'published',
    '2026-09-07T00:00:00+09:00'::timestamptz
) ON CONFLICT (policy_version) DO NOTHING;

INSERT INTO app.ai_active_exploration_policy (market, policy_version)
VALUES ('KRX', 'exploration-policy-v2.krx.2026-09-07')
ON CONFLICT (market) DO UPDATE
    SET policy_version = EXCLUDED.policy_version,
        updated_at = now();

COMMIT;
