BEGIN;

  CREATE OR REPLACE VIEW mart.common_stock_feature_frame_asof AS
  SELECT f.*
  FROM mart.kis_adjusted_feature_frame_asof f
  JOIN core.symbol_master sm
    ON sm.symbol = f.symbol
  WHERE sm.security_type = '보통주'
    AND (sm.listed_at IS NULL OR f.as_of_date >= sm.listed_at)
    AND (sm.delisted_at IS NULL OR f.as_of_date <= sm.delisted_at);

  CREATE OR REPLACE VIEW mart.common_stock_universe_asof AS
  SELECT DISTINCT
      f.as_of_date,
      sm.symbol_id,
      f.symbol,
      sm.name,
      sm.market_segment,
      sm.security_type,
      sm.listing_status,
      sm.listed_at,
      sm.delisted_at
  FROM mart.kis_adjusted_feature_frame_asof f
  JOIN core.symbol_master sm
    ON sm.symbol = f.symbol
  WHERE sm.security_type = '보통주'
    AND (sm.listed_at IS NULL OR f.as_of_date >= sm.listed_at)
    AND (sm.delisted_at IS NULL OR f.as_of_date <= sm.delisted_at);

  COMMENT ON VIEW mart.common_stock_feature_frame_asof IS
  'MVP default backtest feature frame: KIS official adjusted OHLCV + TA, common stocks only.';

  COMMENT ON VIEW mart.common_stock_universe_asof IS
  'MVP default daily universe: common stocks only, derived from KIS adjusted feature frame.';

  COMMIT;