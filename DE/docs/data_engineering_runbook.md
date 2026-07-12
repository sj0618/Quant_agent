# Data Engineering Runbook

## 결론

데이터 엔지니어링 실행 경로는 `KRX/KIS 파일럿 → KRX primary OHLCV 적재 → TA-Lib 선계산 → BOK/OpenDART 외부 데이터 적재 → WICS one-shot 섹터 적재 → mart/as-of 조회 → Airflow 운영` 순서다. MVP에서는 SEIBro를 사용하지 않는다. 2026-07-09 기준 OHLCV 일일 수집 목표는 오늘 날짜까지이며, 최신 검증 결과는 `core.ohlcv_daily=2026-07-03`, `core.ohlcv_quality_daily=2026-07-05`, `feature.adjusted_ohlcv_daily=2026-07-03`, `feature.kis_adjusted_ohlcv_daily=2026-07-06`이다. 2026-06-24 기준 BOK `rate-fx` 12개 series, BOK 월별 유가 3개 series(WTI/Dubai/Brent), DART CFS 재무제표 2016~2026 period_end 구간은 백필이 완료되어 증분 운영 대상으로 전환한다. 2026-06-28 기준 WICS Company Guide 기반 섹터 스냅샷을 로컬 DB에 1회 적재해 `core.symbol_master.sector`를 갱신한다. BOK 월별 유가는 `902Y003` 월간 series로 저장하며 실제 ECOS 발표일이 별도 컬럼으로 저장되지 않으므로 백테스트 조인 시 보수적 lag를 적용한다.

## 주요 명령

| 목적 | 명령 |
|---|---|
| Source pilot | `python scripts/run_source_pilot.py --source both --symbol 005930 --krx-trade-date 2026-05-15 --start-date 2026-05-14 --end-date 2026-05-15` |
| OHLCV daily/backfill | `python scripts/ingest_ohlcv.py --source KRX --start-date 2026-07-03 --end-date 2026-07-09 --db-mode docker` |
| TA-Lib 계산 | `python scripts/compute_ta_indicators.py --start-date 2026-07-03 --end-date 2026-07-09 --symbols 005930 --db-mode docker` |
| BOK rate-fx 10년 백필/재개 | `python scripts/ingest_dart_bok_history.py --scope full-10y --sources bok --bok-series-preset rate-fx --bok-request-sleep-seconds 0.2 --output .omx/logs/bok-rate-fx-full-10y.json` |
| BOK 월별 유가 10년 백필 | `python scripts/ingest_dart_bok_history.py --scope custom --sources bok --start-date 2016-06-01 --end-date 2026-06-24 --bok-series-json '[{"stat_code":"902Y003","cycle":"M","item_code1":"010101","language":"en"},{"stat_code":"902Y003","cycle":"M","item_code1":"010102","language":"en"},{"stat_code":"902Y003","cycle":"M","item_code1":"010103","language":"en"}]' --output .omx/logs/bok-oil-monthly-full-10y-20260624.json` |
| DART CFS 2016~2026 백필/재개 | `python scripts/ingest_dart_bok_history.py --scope full-10y --sources dart --dart-refresh-corp-codes --dart-fs-div CFS --dart-request-sleep-seconds 0.5 --output .omx/logs/dart-financial-full-10y.json` |
| BOK 단일 series 점검 | `python scripts/ingest_external_data.py --job bok-series --stat-code 722Y001 --cycle D --start-period 20260514 --end-period 20260515 --item-code1 0101000 --db-mode docker` |
| BOK 유가 단일 series 점검 | `python scripts/ingest_external_data.py --job bok-series --stat-code 902Y003 --cycle M --start-period 202601 --end-period 202605 --item-code1 010102 --db-mode docker` |
| OpenDART corp code | `python scripts/ingest_external_data.py --job dart-corp-codes --db-mode docker` |
| OpenDART financial | `python scripts/ingest_external_data.py --job dart-financial --symbol 005930 --corp-code <corp_code> --business-year 2025 --report-code 11011 --db-mode docker` |
| WICS 섹터 스냅샷(1회) | `python scripts/ingest_wics_sectors.py --as-of-date 2026-06-28 --db-mode docker` |
| KIS official adjusted full + TA | `python scripts/run_kis_adjusted_full_pipeline.py --run-mode full --start-date 2016-05-20 --end-date 2026-07-09 --resume` |
| KIS official adjusted daily incremental + TA | `python scripts/run_kis_adjusted_full_pipeline.py --run-mode daily-incremental --target-date 2026-07-09 --resume` |

2026-06-28 검증 결과, WICS 적재는 listed common-stock 2,536개 중 2,535개를 매칭했고 `230980`은 FnGuide Company Guide가 `InvalidCompany`를 반환해 `sector`가 `NULL`로 남았다.

섹터 저장 방식:
- 별도 섹터 테이블은 만들지 않고, WICS/KIND 섹터 스냅샷을 `core.symbol_master`의 `sector` 컬럼에 저장한다.
- 출처와 스냅샷 시점은 각각 `sector_source`, `sector_as_of`, `sector_run_id`로 추적한다.
- `mart.common_stock_feature_frame_asof`는 `mart.kis_adjusted_feature_frame_asof`를 기반으로 하지만, 섹터는 `core.symbol_master.sm.sector`를 **명시적으로** 다시 뽑는다. 그래서 섹터를 백테스트 기본 view까지 전파하려면 이 뷰도 `migrations/008_symbol_sector_metadata.sql`에서 함께 재생성해야 한다.
- 2026-06-28 기준 WICS distinct sector 예시(현재 DB, 26개): `IT가전`, `IT하드웨어`, `건강관리`, `건설,건축관련`, `기계`, `디스플레이`, `미디어,교육`, `반도체`, `보험`, `비철,목재등`, `상사,자본재`, `소매(유통)`, `소프트웨어`, `에너지`, `운송`, `유틸리티`, `은행`, `자동차`, `조선`, `증권`, `철강`, `통신서비스`, `필수소비재`, `호텔,레저서비스`, `화장품,의류,완구`, `화학`.

## 환경변수

| 영역 | 키 |
|---|---|
| DB | 권장: `QUANT_DB_DSN` 또는 `DATABASE_URL`; 대안: `QUANT_DB_HOST`, `QUANT_DB_PORT`, `QUANT_DB_NAME`, `QUANT_DB_USER`, `QUANT_DB_PASSWORD` |
| DB 실행 모드 | `QUANT_DB_EXECUTION_MODE=psycopg` 또는 `docker`. DB 정보가 있으면 스크립트가 `psycopg`를 자동 선택하고, 없으면 로컬 Docker를 사용한다. |
| 로컬 Docker DB | `QUANT_DB_CONTAINER=quant-agent-db` |
| KRX | `KRX_API_KEY`, 선택: `KRX_DAILY_MARKET_ENDPOINTS` |
| KIS | `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_TRADING_ENV` |
| BOK | `BOK_API_KEY`, 선택: `BOK_BASE_URL` |
| OpenDART | `DART_API_KEY` 또는 `OPENDART_API_KEY` |
| WICS | `WICS_COMPANY_INFO_URL`, 선택: `WICS_REQUEST_WORKERS` |
| Airflow | `BOK_API_KEY`, `BOK_SERIES_JSON` 또는 `BOK_DAILY_SERIES_JSON`, `DART_REFRESH_CORP_CODES`, `QUANT_AIRFLOW_DAILY_SCHEDULE` |

공용 DB 정보를 서버에 넣을 때는 아래 위치 중 하나를 쓰면 된다.

| 입력 위치 | 권장 용도 |
|---|---|
| Airflow worker/container 환경변수 | 운영에서 가장 단순한 방법. `QUANT_DB_DSN` 또는 host/user/password 조합을 주입한다. |
| Airflow Connection / Secret Backend | 클라우드/관리형 Airflow에서 권장. Connection 값이 환경으로 주입되면 스크립트가 그대로 사용한다. |
| 셸 환경변수 | 수동 실행과 로컬 검증용. `.env`를 쓰지 않고 `export`/프로파일 스크립트로 주입한다. |

공용 DB만 쓰려면 서버에서는 `QUANT_AIRFLOW_LOAD_DOTENV=false`로 두어 repo 루트 `.env`를 읽지 않게 하는 편이 안전하다.

### BOK 유가 series

| series_id | 의미 | 주기 | 백테스트 사용 기준 |
|---|---|---|---|
| `902Y003:010101` | WTI 원유, `$/bbl` | 월간 | 월평균값이므로 기준일에 이미 공개된 마지막 월 값만 사용 |
| `902Y003:010102` | Dubai Fateh 원유, `$/bbl` | 월간 | 일봉 백테스트에는 `effective_date` 월초값을 그대로 쓰지 않고 다음 달 이후로 lag 적용 |
| `902Y003:010103` | Brent 원유, `$/bbl` | 월간 | 섹터/시장 regime 보조 feature로 사용 |

BOK 월별 유가의 `TIME=YYYYMM`은 `feature.bok_macro_daily.effective_date = YYYY-MM-01`로 정규화된다. 월평균 유가를 해당 월 초부터 알고 있었다고 처리하면 look-ahead bias가 생기므로, 백테스트 조인에서는 `available_from` 또는 별도 lag policy를 사용한다. 현재 백필 경로는 `published_at`에 실제 ECOS 발표일이 아니라 수집 시각을 넣을 수 있으므로, 보수적 기본값은 `effective_date + INTERVAL '1 month'` 이후 사용이다.

## 적재 계층

| 계층 | 테이블/뷰 |
|---|---|
| Raw | `raw.ohlcv_response`, `raw.bok_response`, `raw.dart_response` |
| Core | `core.symbol_master`, `core.ohlcv_daily`, `core.ohlcv_quality_daily`, `core.trading_calendar` |
| Feature | `feature.ta_*_daily`, `feature.ta_*_ticker_daily`, `feature.bok_macro_daily`, `feature.dart_*` |
| Mart | `mart.full_universe_asof`, `mart.symbol_feature_frame_asof`, `mart.bok_macro_asof`, `mart.dart_financial_asof` |

MVP에서는 SEIBro 계층을 사용하지 않는다. 위 SEIBro 관련 raw/feature/mart 항목은 기존 적재 이력 또는 후속 과제용으로만 남겨둔다.

## 검증 쿼리

```sql
SELECT count(*) FROM core.ohlcv_daily WHERE trade_date = '2026-07-03';
SELECT category, count(*) FROM feature.ta_indicator_definition GROUP BY category ORDER BY category;
SELECT * FROM mart.symbol_feature_frame_asof WHERE symbol = '005930' ORDER BY as_of_date DESC LIMIT 5;
SELECT count(*) AS rows,
       count(DISTINCT series_id) AS series_count,
       min(effective_date) AS min_date,
       max(effective_date) AS max_date
FROM feature.bok_macro_daily;

SELECT count(*) AS rows,
       count(DISTINCT symbol_id) AS symbol_count,
       min(period_end) AS min_period_end,
       max(period_end) AS max_period_end
FROM feature.dart_financial_quarterly;

SELECT 'duplicate_feature_pk_groups' AS check_name, count(*) AS issue_count
FROM (
  SELECT symbol_id, period_end, report_code, fs_div
  FROM feature.dart_financial_quarterly
  GROUP BY 1,2,3,4
  HAVING count(*) > 1
) d
UNION ALL
SELECT 'empty_or_null_accounts_jsonb', count(*)
FROM feature.dart_financial_quarterly
WHERE accounts_jsonb IS NULL OR accounts_jsonb = '{}'::jsonb
UNION ALL
SELECT 'feature_mart_row_delta',
       (SELECT count(*) FROM feature.dart_financial_quarterly)
     - (SELECT count(*) FROM mart.dart_financial_asof)
UNION ALL
SELECT 'feature_rows_without_corp_map', count(*)
FROM feature.dart_financial_quarterly f
LEFT JOIN feature.dart_corp_symbol_map m ON m.corp_code = f.corp_code
WHERE m.corp_code IS NULL;

WITH key_counts AS (
  SELECT 'Trend'::text AS category, count(*) AS current_precomputed_keys
  FROM (SELECT values_jsonb FROM feature.ta_trend_ticker_daily WHERE values_jsonb <> '{}'::jsonb LIMIT 1) s
  CROSS JOIN LATERAL jsonb_object_keys(s.values_jsonb) AS k
  UNION ALL
  SELECT 'Momentum', count(*)
  FROM (SELECT values_jsonb FROM feature.ta_momentum_ticker_daily WHERE values_jsonb <> '{}'::jsonb LIMIT 1) s
  CROSS JOIN LATERAL jsonb_object_keys(s.values_jsonb) AS k
  UNION ALL
  SELECT 'Volatility', count(*)
  FROM (SELECT values_jsonb FROM feature.ta_volatility_ticker_daily WHERE values_jsonb <> '{}'::jsonb LIMIT 1) s
  CROSS JOIN LATERAL jsonb_object_keys(s.values_jsonb) AS k
  UNION ALL
  SELECT 'Volume', count(*)
  FROM (SELECT values_jsonb FROM feature.ta_volume_ticker_daily WHERE values_jsonb <> '{}'::jsonb LIMIT 1) s
  CROSS JOIN LATERAL jsonb_object_keys(s.values_jsonb) AS k
  UNION ALL
  SELECT 'Pattern', count(*)
  FROM (SELECT values_jsonb FROM feature.ta_pattern_ticker_daily WHERE values_jsonb <> '{}'::jsonb LIMIT 1) s
  CROSS JOIN LATERAL jsonb_object_keys(s.values_jsonb) AS k
)
SELECT * FROM key_counts ORDER BY category;
```

TA 검증은 두 층으로 본다. `feature.ta_indicator_definition`은 계산 가능한 지표 정의 카탈로그 158개이고, `feature.ta_*_ticker_daily.values_jsonb`의 현재 mart 기본 입력은 Trend 16, Momentum 8, Volatility 7, Volume 4, Pattern 10으로 총 45개 key다. `bbands`처럼 정의 1개가 여러 output key를 만들 수 있어 정의 수와 저장 key 수는 1:1이 아니다. DART 완료 검증 산출물은 `.omx/logs/dart-validation-20260604-095618.md`와 `.omx/logs/dart-validation-20260604-095618.json`에 저장되어 있다.

## KIS official adjusted OHLCV + TA 운영

`scripts/run_kis_adjusted_full_pipeline.py`는 `.env` 파일을 로드하지 않고, 이미 프로세스 환경에 주입된 KIS/DB 자격증명만 사용한다. 운영자는 장기 backfill과 일일 증분을 같은 wrapper로 실행한다.

공용 DB 적재까지 자동화하려면 서버/워크플로우 환경에 `QUANT_DB_DSN`(권장) 또는 `DATABASE_URL`, 혹은 host/user/password를 넣는다. 그러면 KIS 수정주가, TA 재계산, 품질 검사 단계가 모두 같은 DB를 사용한다. `QUANT_DB_EXECUTION_MODE=psycopg`를 명시하면 직접 DB 적재 경로를 강제로 선택할 수 있다.

| 실행 유형 | 권장 명령 | 산출물 |
|---|---|---|
| 장기 full/backfill | `python scripts/run_kis_adjusted_full_pipeline.py --run-mode full --start-date 2016-05-20 --end-date <YYYY-MM-DD> --resume` | `.omx/artifacts/kis-adjusted-full.json`, `.omx/artifacts/technical-indicators-kis-adjusted-full.json` |
| 일일 증분 | `python scripts/run_kis_adjusted_full_pipeline.py --run-mode daily-incremental --target-date <YYYY-MM-DD> --resume` | `.omx/artifacts/kis-adjusted-daily-<YYYY-MM-DD>.json`, `.omx/artifacts/technical-indicators-kis-adjusted-daily-<YYYY-MM-DD>.json` |

Resume 규칙은 JSON summary 기준이다. `--resume` 사용 시 요청 기간(`start_date`, `end_date`)이 일치하고 실패 목록(`failed_windows`, `failed_tickers`)이 비어 있는 단계만 건너뛴다. 예를 들어 KIS 적재 summary가 성공이고 TA summary가 없으면 KIS는 스킵하고 TA부터 재개한다. 실패 window/ticker가 남아 있거나 기간이 다르면 해당 단계는 다시 실행한다.

wrapper 내부 검증은 KIS 적재 후 `failed_windows`가 비어 있을 때만 TA recomputation으로 진행한다. KIS 실패가 남으면 TA 이전에 중단하고 `stopped_before_ta` summary를 출력한다.

## Airflow

`DE/airflow/dags/quant_agent_data_engineering.py`는 다음 DAG를 제공한다. 일일 DAG에는 섹터 스냅샷 태스크가 없고, WICS 섹터 수집은 `scripts/ingest_wics_sectors.py`로 한 번만 실행한다.

| DAG | 역할 |
|---|---|
| `quant_agent_daily_data_engineering` | 일일 OHLCV, TA-Lib, BOK, DART corp code refresh |
| `quant_agent_backfill_ohlcv_10y` | 설정된 primary source 기준 10년 OHLCV backfill |

Airflow task는 credentials를 코드/파일에서 읽지 않고 런타임 환경, Airflow Connection, Secret Backend에 의존한다. WICS 섹터 수집은 Airflow가 아닌 별도 one-shot 스크립트로만 실행한다. KIS TA/품질 스크립트는 DB 정보가 주입되면 `psycopg`를 자동 선택하고, 그렇지 않으면 로컬 Docker DB 경로를 따른다.
