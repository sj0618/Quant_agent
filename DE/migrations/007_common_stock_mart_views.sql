BEGIN;

  -- Membership starts with KRX sessions and lifecycle segments, not observed prices.
  -- Market/lifecycle status is as-of history; common-stock classification is the
  -- canonical security classification and never substitutes current market status.
  CREATE OR REPLACE VIEW mart.common_stock_universe_asof AS
  SELECT DISTINCT
      c.trade_date AS as_of_date,
      sm.symbol_id,
      sm.symbol,
      sm.name,
      lh.market AS market_segment,
      sm.security_type,
      lh.listing_status,
      lh.valid_from AS listed_at,
      lh.valid_to AS delisted_at
  FROM core.trading_calendar c
  JOIN core.symbol_listing_history lh
    ON lh.listing_status = 'listed'
   AND c.trade_date >= lh.valid_from
   AND (lh.valid_to IS NULL OR c.trade_date <= lh.valid_to)
  JOIN core.symbol_master sm
    ON sm.symbol_id = lh.symbol_id
  WHERE c.is_open
    AND lh.market IN ('KOSPI', 'KOSDAQ')
    AND sm.security_type = '보통주';

  CREATE OR REPLACE VIEW mart.common_stock_feature_frame_asof AS
  SELECT f.*
  FROM mart.common_stock_universe_asof u
  JOIN mart.kis_adjusted_feature_frame_asof f
    ON f.as_of_date = u.as_of_date
   AND f.symbol = u.symbol;

  COMMENT ON VIEW mart.common_stock_feature_frame_asof IS
  'PIT KOSPI/KOSDAQ common-stock feature rows; missing features do not remove membership.';
  COMMENT ON VIEW mart.common_stock_universe_asof IS
  'PIT KRX session x lifecycle universe. Lifecycle controls market eligibility; canonical common-stock classification controls security type.';

  COMMIT;