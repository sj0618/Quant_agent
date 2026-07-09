-- Classify Korean listed symbols and expose the KOSPI/KOSDAQ common-stock universe.

CREATE OR REPLACE FUNCTION meta.classify_krx_security_type(
    p_symbol TEXT,
    p_name TEXT,
    p_market_segment TEXT,
    p_metadata JSONB,
    p_existing_security_type TEXT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
WITH normalized AS (
    SELECT
        regexp_replace(
            COALESCE(
                NULLIF(btrim(p_name), ''),
                NULLIF(btrim(p_metadata->>'ISU_ABBRV'), ''),
                NULLIF(btrim(p_metadata->>'isu_abbrv'), ''),
                NULLIF(btrim(p_metadata->>'ISU_NM'), ''),
                NULLIF(btrim(p_metadata->>'isu_nm'), ''),
                ''
            ),
            '\s+',
            '',
            'g'
        ) AS compact_name,
        UPPER(regexp_replace(COALESCE(p_market_segment, p_metadata->>'MKT_NM', p_metadata->>'mkt_nm', p_metadata->>'market', ''), '\s+', '', 'g')) AS market_code,
        CONCAT_WS(
            ' ',
            p_metadata->>'security_type',
            p_metadata->>'SECUGRP_NM',
            p_metadata->>'secugrp_nm',
            p_metadata->>'SECT_TP_NM',
            p_metadata->>'sect_tp_nm',
            p_metadata->>'MKT_TP_NM',
            p_metadata->>'mkt_tp_nm',
            p_metadata->>'ISU_ABBRV',
            p_metadata->>'isu_abbrv',
            p_metadata->>'ISU_NM',
            p_metadata->>'isu_nm',
            p_name
        ) AS metadata_text
)
SELECT CASE
    WHEN UPPER(metadata_text) LIKE '%ETN%' OR metadata_text LIKE '%상장지수증권%' THEN 'ETN'
    WHEN UPPER(metadata_text) LIKE '%ETF%' OR metadata_text LIKE '%상장지수펀드%' OR metadata_text LIKE '%상장지수집합투자기구%' THEN 'ETF'
    WHEN UPPER(metadata_text) LIKE '%SPAC%' OR metadata_text LIKE '%스팩%' OR metadata_text LIKE '%기업인수목적%' THEN 'SPAC'
    WHEN UPPER(metadata_text) LIKE '%REIT%'
      OR metadata_text LIKE '%부동산투자회사%'
      OR (
          (compact_name LIKE '%리츠' OR compact_name LIKE '이리츠%')
          AND compact_name NOT LIKE '%메리츠%'
          AND compact_name NOT LIKE '블리츠%'
      )
        THEN '리츠(REITs)'
    WHEN UPPER(COALESCE(p_symbol, '')) IN ('088980', '415640')
      OR compact_name IN ('맥쿼리인프라', 'KB발해인프라')
        THEN '인프라펀드'
    WHEN metadata_text LIKE '%우선주%'
      OR metadata_text LIKE '%종류주%'
      OR compact_name ~ '(우선주|[0-9]*우(B|C)?(\(전환\))?)$'
      OR (compact_name = '' AND UPPER(COALESCE(p_symbol, '')) ~ '^[0-9]{5}[57KLM]$')
        THEN '우선주'
    WHEN metadata_text LIKE '%보통주%'
      OR metadata_text LIKE '%주권%'
      OR market_code IN ('KOSPI', '유가증권', 'STK', 'KOSDAQ', '코스닥', 'KSQ', 'KONEX', '코넥스', 'KNX')
        THEN '보통주'
    ELSE '기타'
END
FROM normalized;
$$;

ALTER TABLE core.symbol_master
    DROP CONSTRAINT IF EXISTS chk_symbol_master_security_type;

UPDATE core.symbol_master
   SET security_type = meta.classify_krx_security_type(symbol, name, market_segment, metadata_jsonb, security_type),
       updated_at = now();

ALTER TABLE core.symbol_master
    ALTER COLUMN security_type SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = 'chk_symbol_master_security_type'
           AND conrelid = 'core.symbol_master'::regclass
    ) THEN
        ALTER TABLE core.symbol_master
            ADD CONSTRAINT chk_symbol_master_security_type
            CHECK (security_type IN ('보통주', '우선주', 'SPAC', '리츠(REITs)', 'ETF', 'ETN', '인프라펀드', '기타'));
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_symbol_master_security_type_market
    ON core.symbol_master (security_type, market_segment, listing_status);

CREATE OR REPLACE VIEW meta.view_common_stock_universe AS
SELECT
    symbol_id,
    symbol,
    name,
    market,
    market_segment,
    security_type,
    listing_status,
    listed_at,
    delisted_at,
    metadata_jsonb
FROM core.symbol_master
WHERE market_segment IN ('KOSPI', 'KOSDAQ')
  AND security_type = '보통주'
  AND listing_status = 'listed';
