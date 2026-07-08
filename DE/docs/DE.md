# 데이터 엔지니어링 작업 설명 자료

## 0. 문서 목적

| 항목 | 내용 |
|---|---|
| 목적 | 데이터 엔지니어링 담당자가 지금까지 어떤 구조를 만들고, 어떤 스크립트로 10년치 데이터를 수집/가공/검증했는지 설명하기 위한 자료. |
| 범위 | DB 스키마 계층, 10년 OHLCV/KIS 수정주가/SEIBro/TA 처리 흐름, 운영·품질·lineage 구조 정리. |
| 상세 테이블 현황 | row count와 컬럼 상세는 `docs/public_server_db_tables.md`에서 별도 관리. 여기서는 전체 객체와 역할만 요약. |
| 말투 | 발표/인수인계용 요약체. “구현.”, “적재.”, “관리.” 방식으로 작성. |

## 1. 전체 구현 요약

| 영역 | 구현 내용 |
|---|---|
| DB 계층 | `meta`, `raw`, `core`, `feature`, `mart` 5개 스키마로 분리. 원본 보존 → 정규화 → feature 계산 → mart 조회 흐름 구현. |
| 10년 OHLCV | KRX 일별 전 종목 OHLCV를 `raw.ohlcv_response`와 `core.ohlcv_daily`에 적재. 종목 마스터, 상장 이력, 종목명 이력, 거래일 캘린더 동시 갱신 구현. |
| 10년 수정주가 | KIS 공식 수정주가를 `feature.kis_adjusted_ohlcv_daily`에 별도 적재. KIS API 제한을 고려해 종목×기간 window 분할, resume, 병렬 수집 구현. |
| TA 지표 | `feature.kis_adjusted_ohlcv_daily` 또는 `core.ohlcv_daily`를 입력으로 canonical `feature.adjusted_ohlcv_daily` 생성 후 5개 TA 카테고리 테이블 적재. `ProcessPoolExecutor` 기반 종목 단위 병렬 계산 구현. |
| SEIBro | SEIBro 분석리포트 요약을 월 단위 chunk, page 단위 pagination으로 수집. 원본 payload와 파싱 row를 각각 `raw.seibro_report_response`, `raw.analyst_report_summary`에 저장. |
| 품질/감사 | `meta.ingestion_run`, `meta.api_request_log`, `meta.data_quality_issue`, `meta.lineage_event`, `meta.ingestion_cursor`로 실행 이력, API 관측성, 품질 이슈, lineage, resume 상태 관리. |
| 운영 | Airflow DAG와 수동 backfill CLI 병행. full backfill, daily incremental, QA, 테스트까지 연결하는 wrapper 구현. |

## 2. DB 스키마 구조

### 2.1 계층 구조

```text
외부 API / 웹 응답
  ↓
raw        원본 payload, 원천 row 보존
  ↓
core       종목/거래일/OHLCV 정규화 canonical 데이터
  ↓
feature    수정주가, TA, BOK/DART/SEIBro feature 데이터
  ↓
mart       백테스트/팩터 엔진/조회용 as-of view

meta        위 전체 흐름의 실행 이력, API 로그, 품질 이슈, lineage, cursor 관리
```

| 스키마 | 역할 | 설계 의도 |
|---|---|---|
| `meta` | 운영 메타데이터 | 수집 run, API 요청, 품질 이슈, lineage, cursor를 한 곳에서 추적. 재현성과 장애 복구를 위해 구현. |
| `raw` | 원본 landing zone | API/웹 응답 payload와 원천 row 보존. 정규화 오류가 있어도 원본 재처리 가능하도록 구현. |
| `core` | canonical 정규화 계층 | 종목, 상장/상폐, 거래일, 원천 OHLCV를 정규화. 모든 feature 계산의 기준 데이터로 구현. |
| `feature` | 분석/모델 입력 계층 | 수정주가, 기술적 지표, BOK, DART, SEIBro 파생 데이터 저장. 계산 결과를 재사용할 수 있게 구현. |
| `mart` | 소비 계층 | 백테스트/팩터 엔진이 바로 읽는 as-of view 제공. join/필터/공식 수정주가 선택 로직을 DB view로 고정. |

### 2.2 `meta` 스키마

| 객체 | 역할 |
|---|---|
| `meta.data_source` | `KRX`, `KIS`, `SEIBRO`, `BOK`, `DART`, `TA`, `QA` 등 데이터 출처 마스터 관리. |
| `meta.ingestion_run` | 수집/계산/품질검사 실행 단위 기록. `run_id`, DAG/task, 파라미터, 성공/실패 상태 관리. |
| `meta.ingestion_cursor` | 증분 수집과 resume 상태 관리. KIS 수정주가 window 완료 여부, OHLCV 마지막 성공일 등 저장. |
| `meta.api_request_log` | API 요청별 성공 여부, status code, retry, elapsed time, response hash, error message 저장. |
| `meta.data_quality_issue` | 중복, 누락, stale price, volume anomaly, KIS/KRX 불일치 등 품질 이슈 저장. |
| `meta.lineage_event` | target table/key가 어떤 source table/key와 transform version에서 만들어졌는지 기록. |
| `meta.view_common_stock_universe` | KOSPI/KOSDAQ 상장 보통주 universe helper view. |

### 2.3 `raw` 스키마

| 객체 | 역할 |
|---|---|
| `raw.ohlcv_response` | KRX/KIS OHLCV API 원본 payload 저장. `request_hash`, `payload_hash`로 중복 수집 방지. |
| `raw.seibro_report_response` | SEIBro WebSquare/API 원본 XML/JSON성 payload 저장. |
| `raw.analyst_report_summary` | SEIBro 분석리포트 요약 row를 원천성 컬럼으로 파싱해 저장. AI 요약 결과가 아니라 SEIBro 응답 row. |
| `raw.bok_response` | BOK ECOS 원본 응답 payload 저장. |
| `raw.dart_response` | OpenDART 원본 응답 payload 저장. |

### 2.4 `core` 스키마

| 객체 | 역할 |
|---|---|
| `core.symbol_master` | 종목 마스터. symbol, 종목명, 시장, 시장 구분, 상장 상태, 상장/상폐일, 종목 유형, sector/sector_source/sector_as_of/sector_run_id 관리. |
| `core.symbol_listing_history` | 종목별 상장/상폐/재상장 구간 이력 관리. |
| `core.symbol_name_history` | 종목명 변경 이력 관리. |
| `core.trading_calendar` | 시장별 거래일/휴장일 캘린더 관리. |
| `core.ohlcv_daily` | KRX 기본 일봉 OHLCV canonical 테이블. TimescaleDB hypertable로 구현. |
| `core.ohlcv_quality_daily` | 종목×일자 coverage, expected/observed day, issue count 등 품질 집계 저장. |

### 2.5 `feature` 스키마

| 객체 | 역할 |
|---|---|
| `feature.kis_adjusted_ohlcv_daily` | KIS 공식 수정주가 OHLCV 저장. `FID_ORG_ADJ_PRC=0` 기준. |
| `feature.adjusted_ohlcv_daily` | TA 계산과 mart join을 위한 canonical adjusted OHLCV. KIS 공식 수정주가 또는 core 기반 continuity 보정 결과 저장. |
| `feature.ta_indicator_definition` | TA 지표 정의, 파라미터, warmup, output schema, transform version 저장. |
| `feature.ta_trend_daily` | 초기 symbol_id 기준 추세 지표 저장. |
| `feature.ta_momentum_daily` | 초기 symbol_id 기준 모멘텀 지표 저장. |
| `feature.ta_volatility_daily` | 초기 symbol_id 기준 변동성 지표 저장. |
| `feature.ta_volume_daily` | 초기 symbol_id 기준 거래량 지표 저장. |
| `feature.ta_pattern_daily` | 초기 symbol_id 기준 캔들 패턴 지표 저장. |
| `feature.ta_trend_ticker_daily` | ticker/base_ticker/segment_id 기준 추세 지표 저장. |
| `feature.ta_momentum_ticker_daily` | ticker/base_ticker/segment_id 기준 모멘텀 지표 저장. |
| `feature.ta_volatility_ticker_daily` | ticker/base_ticker/segment_id 기준 변동성 지표 저장. |
| `feature.ta_volume_ticker_daily` | ticker/base_ticker/segment_id 기준 거래량 지표 저장. |
| `feature.ta_pattern_ticker_daily` | ticker/base_ticker/segment_id 기준 캔들 패턴 지표 저장. |
| `feature.seibro_report_summary` | SEIBro 분석리포트 raw를 feature 계층으로 정규화할 대상 테이블. |
| `feature.seibro_sentiment` | SEIBro 리포트 기반 sentiment score 저장 대상 테이블. |
| `feature.seibro_universe_daily` | SEIBro 리포트 기반 일별 universe 저장 대상 테이블. |
| `feature.bok_macro_daily` | BOK ECOS 거시지표 feature 저장. 금리/환율 `rate-fx` 12개 series와 월별 유가 3개 series(`902Y003:010101` WTI, `902Y003:010102` Dubai Fateh, `902Y003:010103` Brent)를 동일 테이블에 적재. |
| `feature.dart_corp_symbol_map` | OpenDART corp code와 DB symbol 매핑 저장. |
| `feature.dart_financial_quarterly` | OpenDART 분기/사업보고서 재무 feature 저장. |

### 2.6 `mart` 스키마

| 객체 | 역할 |
|---|---|
| `mart.symbol_feature_frame_asof` | `feature.adjusted_ohlcv_daily`와 ticker TA 5개 카테고리를 결합한 백테스트용 feature frame. |
| `mart.kis_adjusted_feature_frame_asof` | KIS 공식 수정주가 행만 필터링한 feature frame. 백테스트 1순위 입력으로 사용. |
| `mart.common_stock_feature_frame_asof` | KIS 공식 수정주가 feature frame에서 KOSPI/KOSDAQ 상장 보통주만 남긴 MVP 백테스트 기본 view. migration 007 대상. |
| `mart.common_stock_universe_asof` | 날짜별 KOSPI/KOSDAQ 상장 보통주 universe view. KIS 수정주가 feature frame에 존재하는 종목만 universe로 인정. migration 007 대상. |
| `mart.full_universe_asof` | 날짜별 투자 가능 universe view. |
| `mart.data_coverage_report` | OHLCV coverage/품질 요약 view. |
| `mart.bok_macro_asof` | BOK macro feature as-of 조회 view. 월별 유가처럼 발표 지연이 있는 series는 `available_from` 또는 별도 lag policy 기준으로 백테스트에 조인. |
| `mart.dart_financial_asof` | DART 재무 feature as-of 조회 view. |
| `mart.seibro_universe_asof` | SEIBro sentiment/universe feature as-of 조회 view. |

### 2.7 보통주 universe 구조

| 객체 | 기준 | 공용 DB 기준 현황 |
|---|---|---|
| `meta.view_common_stock_universe` | `core.symbol_master`에서 `market_segment IN ('KOSPI', 'KOSDAQ')`, `security_type = '보통주'`, `listing_status = 'listed'` 필터. | KOSPI/KOSDAQ 상장 보통주 합계 **2,554개**. 종목 단위 helper view. |
| `mart.common_stock_feature_frame_asof` | `mart.kis_adjusted_feature_frame_asof`에서 보통주만 필터. | MVP 백테스트 기본 feature frame으로 사용하도록 migration 007에서 정의할 대상. |
| `mart.common_stock_universe_asof` | `mart.kis_adjusted_feature_frame_asof`에 실제 가격 row가 있는 날짜×보통주만 추출. | 날짜별 투자 가능 보통주 universe로 사용하도록 migration 007에서 정의할 대상. |

중요 구분:

| 구분 | 설명 |
|---|---|
| `meta.view_common_stock_universe` | 날짜 차원이 없는 현재 상장 보통주 목록. KOSPI/KOSDAQ 합계 2,554개. |
| `mart.common_stock_universe_asof` | 날짜별 universe. 특정 `as_of_date`에 KIS 수정주가 row가 있어야 포함. |
| `mart.common_stock_feature_frame_asof` | 가격·TA·종목 메타까지 포함한 백테스트 입력 view. |

## 3. DB 마이그레이션 구성

| 파일 | 핵심 구현 |
|---|---|
| `migrations/001_data_engineering_m0.sql` | `meta`, `raw`, `core`, `feature`, `mart` 기본 스키마와 핵심 테이블/view 생성. `core.ohlcv_daily`, 초기 TA 테이블 hypertable 구성. |
| `migrations/002_data_engineering_runtime.sql` | DART corp-code 매핑 테이블과 runtime mart view 추가. |
| `migrations/003_quality_observability_lineage.sql` | API 관측성 컬럼, lineage metadata, `feature.adjusted_ohlcv_daily`, ticker 기반 TA 테이블, KIS adjusted mart view 추가. |
| `migrations/004_mart_symbol_metadata.sql` | 종목 메타데이터 보강, ticker TA 기준 mart view 재작성. |
| `migrations/005_seibro_analyst_report_summary.sql` | SEIBro 분석리포트 요약 raw landing table 보장. |
| `migrations/006_symbol_security_type_classification.sql` | 보통주/우선주/SPAC/리츠/ETF/ETN/인프라펀드/기타 분류 함수와 common-stock universe helper view 추가. |
| `migrations/007_common_stock_mart_views.sql` | 보통주 전용 `mart.common_stock_feature_frame_asof`, `mart.common_stock_universe_asof` 정의 대상. |

적용 순서:

```text
001 → 002 → 003 → 004 → 005 → 006 → 007
```

## 4. 10년 데이터 수집·가공 스크립트

### 4.1 전체 흐름

```text
1. KRX OHLCV 적재
   scripts/ingest_ohlcv.py
   → raw.ohlcv_response
   → core.symbol_master / core.symbol_listing_history / core.symbol_name_history
   → core.trading_calendar / core.ohlcv_daily
   → meta.data_quality_issue / meta.lineage_event

2. KIS 공식 수정주가 적재
   scripts/ingest_kis_adjusted_ohlcv.py
   → feature.kis_adjusted_ohlcv_daily
   → meta.api_request_log / meta.ingestion_cursor / meta.lineage_event

3. TA 계산 및 canonical adjusted OHLCV 생성
   scripts/compute_technical_indicators_pipeline.py
   → feature.adjusted_ohlcv_daily
   → feature.ta_*_ticker_daily
   → mart.symbol_feature_frame_asof / mart.kis_adjusted_feature_frame_asof

4. SEIBro 분석리포트 백필
   scripts/backfill_seibro_analyst_reports.py
   → raw.seibro_report_response
   → raw.analyst_report_summary

5. 품질 검사/메타데이터/유니버스 보강
   scripts/run_data_quality_checks.py
   scripts/refresh_symbol_metadata.py
   scripts/classify_symbol_security_types.py

6. 보통주 전용 mart view 보강
   migrations/007_common_stock_mart_views.sql
   → mart.common_stock_feature_frame_asof
   → mart.common_stock_universe_asof
```

### 4.2 `scripts/ingest_ohlcv.py`

| 항목 | 내용 |
|---|---|
| 목적 | KRX 또는 KIS OHLCV를 지정 기간 기준으로 수집해 raw/core 계층에 적재. 10년 KRX 기본 OHLCV backfill과 daily update에 사용. |
| 입력 | `--source`, `--start-date`, `--end-date`, `--symbols`, `--db-mode`, `--db-container`, `--output`. |
| 핵심 클래스 | `OhlcvIngestionService`. |
| 저장 대상 | `raw.ohlcv_response`, `core.symbol_master`, `core.symbol_listing_history`, `core.symbol_name_history`, `core.trading_calendar`, `core.ohlcv_daily`, `meta.lineage_event`, `meta.data_quality_issue`, `meta.ingestion_cursor`. |

핵심 동작:

| 단계 | 구현 |
|---|---|
| 실행 run 생성 | `meta.ingestion_run`에 source, 기간, symbol 파라미터 저장. |
| 기간 분할 | `OhlcvIngestionConfig.batch_days` 기준으로 날짜 범위 chunk 분할. 기본값 1일. |
| KRX 수집 | 날짜별로 KRX KOSPI/KOSDAQ 일별 endpoint 호출. 응답 payload를 보존하고 `normalize_krx_market_day()`로 OHLCV row 변환. |
| KIS 수집 | symbol-scoped API 구조라 명시 symbol 목록이 있을 때만 수집. `normalize_kis_daily_price()`로 변환. |
| raw 저장 | `request_hash`, `payload_hash` 기준 `raw.ohlcv_response`에 `ON CONFLICT DO NOTHING` 저장. |
| core upsert | 중복 symbol/date는 마지막 row 기준 dedupe. 종목 마스터, 상장 이력, 종목명 이력, 거래일, OHLCV를 한 transaction으로 upsert. |
| 품질 flags | OHLCV 가격/거래량 이상, 중복 row 등 즉시 탐지한 품질 이슈를 `meta.data_quality_issue`에 기록. |
| 품질 framework | 수집 후 expected trading date 대비 누락, stale close, 거래량 anomaly 검사 실행. |
| cursor | 성공한 chunk의 마지막 거래일을 `meta.ingestion_cursor`에 저장. |

10년 backfill 예시:

```powershell
python scripts/ingest_ohlcv.py `
  --source KRX `
  --start-date 2016-05-20 `
  --end-date 2026-05-20 `
  --db-mode docker `
  --output .omx/artifacts/ohlcv-10y.json
```

### 4.3 `scripts/ingest_kis_adjusted_ohlcv.py`

| 항목 | 내용 |
|---|---|
| 목적 | KIS 공식 수정주가 OHLCV를 수집해 `feature.kis_adjusted_ohlcv_daily`에 저장. |
| 핵심 전제 | KIS `inquire-daily-itemchartprice`에서 `FID_ORG_ADJ_PRC=0`을 사용해 수정주가 요청. |
| 저장 대상 | `feature.kis_adjusted_ohlcv_daily`, `meta.api_request_log`, `meta.lineage_event`, `meta.ingestion_cursor`, `meta.ingestion_run`. |
| 기본 window | `DEFAULT_REQUEST_WINDOW_DAYS = 120`. 긴 기간을 종목×120일 window로 분할. |
| 기본 flush | `DEFAULT_FLUSH_ROWS = 10_000`. row buffer가 threshold 이상이면 DB COPY/upsert 수행. |
| 병렬 처리 | `--workers` 지정 시 `ThreadPoolExecutor`로 KIS 요청 병렬화. |

핵심 동작:

| 단계 | 구현 |
|---|---|
| 종목 universe 선택 | `core.ohlcv_daily`와 `core.symbol_master`를 조인해 기간 내 거래 row가 있는 ticker 목록 선택. |
| 기간 window 분할 | `iter_windows()`로 start/end를 120일 단위로 분할. |
| resume | `--skip-existing` 사용 시 `feature.kis_adjusted_ohlcv_daily` row 수와 `meta.ingestion_cursor` 완료 window를 확인해 이미 끝난 window skip. |
| API 호출 | ticker/window별 KIS 수정주가 API 호출. 403 토큰 오류는 대기 후 1회 재시도. |
| recursive split | 큰 window 요청 실패 시 기간을 반으로 나눠 재귀 재시도. 단일 날짜까지 실패하면 failed window로 기록. |
| 병렬 요청 | pending job을 worker 수의 4배까지 유지. 완료된 future부터 row buffer에 병합. |
| row 변환 | `payload_to_adjusted_rows()`에서 `adj_open/high/low/close/volume`, `mod_yn`, `revision_reason`, `quality_flags` 생성. |
| DB 적재 | temp table + `COPY` 후 `ON CONFLICT ("time", ticker) DO UPDATE`로 upsert. |
| API 관측성 | 요청별 success/status/retry/elapsed/response hash를 `meta.api_request_log`에 저장. |
| lineage | `feature.kis_adjusted_ohlcv_daily` target key와 KIS API source key 연결. `adjusted_price_method='kis_official_adjusted'` 기록. |

10년 backfill 예시:

```powershell
python scripts/ingest_kis_adjusted_ohlcv.py `
  --start-date 2016-05-20 `
  --end-date 2026-05-20 `
  --workers 4 `
  --request-window-days 120 `
  --skip-existing `
  --db-mode docker `
  --output .omx/artifacts/kis-adjusted-10y.json
```

### 4.4 `scripts/compute_technical_indicators_pipeline.py`

| 항목 | 내용 |
|---|---|
| 목적 | DB에 적재된 OHLCV에서 canonical adjusted OHLCV와 5개 카테고리 TA 지표를 계산해 feature/mart 계층에 적재. |
| 입력 source | `--input-price-source core` 또는 `--input-price-source kis-adjusted`. |
| 저장 대상 | `feature.adjusted_ohlcv_daily`, `feature.ta_trend_ticker_daily`, `feature.ta_momentum_ticker_daily`, `feature.ta_volatility_ticker_daily`, `feature.ta_volume_ticker_daily`, `feature.ta_pattern_ticker_daily`. |
| mart 출력 | `mart.symbol_feature_frame_asof`, `mart.kis_adjusted_feature_frame_asof`. |
| 기본 batch | ticker batch 64개, flush 50,000 rows. |
| 병렬 처리 | `ProcessPoolExecutor(max_workers=args.workers)`로 종목 단위 CPU 병렬 계산. |

전처리 구현:

| 단계 | 구현 |
|---|---|
| ticker별 DataFrame 구성 | DB에서 기간 내 OHLCV를 ticker별로 읽고 `time` 기준 정렬·중복 제거. |
| 거래일 캘린더 reindex | 전체 거래일 calendar에 맞춰 ticker별 frame 재색인. 누락일/휴장/거래정지 구간을 명시적으로 다룰 수 있게 구성. |
| 상장 구간 반영 | `core.symbol_listing_history`가 있으면 valid_from/valid_to 기준 segment 생성. 없으면 관측 row 간 gap이 `relist_gap_days` 초과일 때 재상장 segment 추론. 기본 30일. |
| effective ticker | 재상장 segment가 여러 개면 `종목코드#S01` 형식의 segment-aware ticker 생성. |
| 거래정지 보정 | 5 거래일 이하 짧은 공백/거래불가/0거래량 구간은 직전 가격으로 forward-fill하고 `halt_filled=true` 기록. |
| 수정주가 처리 | `kis-adjusted` 입력이면 KIS 수정주가를 그대로 `adj_*`로 사용하고 `adjustment_factor=1`. `core` 입력이면 close ratio 급변 규칙으로 과거 가격을 후방 보정. |
| 품질 flags | base_ticker, segment_id, halt_filled, adjustment_factor, adjusted_price_method를 JSONB로 저장. |

TA 계산 구현:

| 카테고리 | 계산 지표 |
|---|---|
| Trend | SMA 20/50/200, EMA 20/50/200, MACD, ADX, AROON. |
| Momentum | RSI, STOCH, CCI, ROC, WILLR, MFI. |
| Volatility | ATR, NATR, Bollinger Bands. |
| Volume | OBV, AD, ADOSC, CMF. |
| Pattern | doji, hammer, hangingman, engulfing, morningstar, eveningstar, shootingstar, harami, darkcloudcover, piercing. |

적재 방식:

| 항목 | 구현 |
|---|---|
| adjusted OHLCV | ticker/date별 `feature.adjusted_ohlcv_daily`에 upsert. |
| TA row | category별 `values_jsonb` 하나에 해당 일자의 지표 결과 저장. |
| infinity 처리 | `np.inf`, `-np.inf`는 `NaN`으로 치환 후 JSON 저장에서 제외. |
| warmup 처리 | 지표 warmup으로 값이 없는 row는 저장 제외. |
| DB write | temp table + `COPY` + `ON CONFLICT ("time", ticker) DO UPDATE`. |
| lineage | adjusted OHLCV와 각 TA table row에 source table/key, transform version 기록. |
| mart view | adjusted OHLCV + 5개 TA table + symbol metadata를 view로 결합. KIS 공식 수정주가는 quality flag 필터로 별도 view 제공. |

KIS 공식 수정주가 기반 10년 TA 계산 예시:

```powershell
python scripts/compute_technical_indicators_pipeline.py `
  --db-mode docker `
  --start-date 2016-05-20 `
  --end-date 2026-05-20 `
  --input-price-source kis-adjusted `
  --workers 8 `
  --ticker-batch-size 32 `
  --flush-rows 25000 `
  --output .omx/artifacts/technical-indicators-kis-adjusted-10y.json
```

### 4.5 `scripts/run_kis_adjusted_full_pipeline.py`

| 항목 | 내용 |
|---|---|
| 목적 | KIS 공식 수정주가 수집 → KIS 기반 TA 재계산 → 품질 검사 → 로컬 테스트를 순차 실행하는 wrapper. |
| full 기본 시작일 | `2016-05-20`. |
| 기본 worker | KIS 4 workers, TA 8 workers. |
| 주요 옵션 | `--run-mode full/daily-incremental`, `--resume`, `--target-date`, `--artifact-dir`. |

실행 순서:

```text
1. scripts/ingest_kis_adjusted_ohlcv.py
2. scripts/compute_technical_indicators_pipeline.py --input-price-source kis-adjusted
3. scripts/run_data_quality_checks.py --checks all
4. python -m py_compile ...
5. python -m pytest tests
```

사용 이유:

| 이유 | 내용 |
|---|---|
| 재현성 | 각 단계 summary JSON을 artifact로 남김. |
| 안전한 resume | `--resume`이면 성공 summary가 있는 KIS/TA/QA 단계 skip. |
| 실패 차단 | KIS failed window가 있으면 TA 단계로 진행하지 않음. |
| 운영 연결 | full backfill과 daily incremental을 같은 wrapper에서 처리. |

### 4.6 `scripts/backfill_seibro_analyst_reports.py`

| 항목 | 내용 |
|---|---|
| 목적 | SEIBro 분석리포트 요약을 장기간 backfill해 raw 계층에 적재. |
| 입력 | `--start-date`, `--end-date`, `--chunk-months`, `--page-size`, `--sleep-min-seconds`, `--sleep-max-seconds`, `--company-code`. |
| 핵심 서비스 | `ExternalDataIngestionService.backfill_seibro_analyst_report_summaries()`. |
| 저장 대상 | `raw.seibro_report_response`, `raw.analyst_report_summary`, `meta.api_request_log`, `meta.lineage_event`, `meta.ingestion_run`. |

핵심 동작:

| 단계 | 구현 |
|---|---|
| 기간 chunk | `month_chunks()`로 기간을 월 단위 chunk로 분할. 기본 chunk 1개월. |
| page 수집 | chunk마다 `start_row/end_row` pagination 수행. 기본 page size 500. |
| WebSquare 호출 | SEIBro WebSquare ProWorks 형식 XML 요청으로 분석리포트 요약 page 호출. |
| raw payload 저장 | page 응답 전체를 `raw.seibro_report_response`에 저장. |
| row 정규화 | `normalize_analyst_report_summaries()`로 report_date, ticker, company_name, summary, opinion, target_price, close_price, institution, author 파싱. |
| raw landing upsert | `(report_date, ticker, institution, author)` PK 기준 `raw.analyst_report_summary`에 upsert. |
| rate limit 완화 | page/chunk 사이 sleep 수행. 기본 sleep 범위는 설정값 기반. |
| 종료 조건 | page row 수가 page size보다 작으면 해당 chunk 종료. |
| lineage | `raw.analyst_report_summary` target range와 `raw.seibro_report_response` source hash 연결. |

10년 backfill 예시:

```powershell
python scripts/backfill_seibro_analyst_reports.py `
  --start-date 2016-05-20 `
  --end-date 2026-05-20 `
  --chunk-months 1 `
  --page-size 500 `
  --db-mode docker `
  --output .omx/artifacts/seibro-analyst-report-10y.json
```

### 4.7 보조 운영 스크립트

| 스크립트 | 역할 |
|---|---|
| `scripts/run_data_quality_checks.py` | OHLCV coverage, missing symbol/date, stale price, volume anomaly, KIS/KRX consistency 검사 실행. 결과를 `meta.data_quality_issue`에 저장. |
| `scripts/refresh_symbol_metadata.py` | 이미 적재된 OHLCV 관측치를 기준으로 종목 상장/재상장/상폐 구간과 종목 메타데이터 갱신. 외부 API 호출 없음. |
| `scripts/classify_symbol_security_types.py` | `006_symbol_security_type_classification.sql` 적용 또는 검증. 보통주/우선주/SPAC/리츠/ETF/ETN/인프라펀드/기타 분류와 common-stock universe 검증. |
| `scripts/ingest_dart_bok_history.py` | BOK ECOS와 OpenDART 장기 수집용 schema-first 적재 스크립트. 실제 DB 컬럼/PK/UNIQUE를 먼저 스캔하고 존재하는 컬럼만 적재. BOK 월별 유가는 `--bok-series-json`으로 `902Y003`의 WTI/Dubai/Brent 항목을 지정해 수집. |
| `scripts/ingest_external_data.py` | BOK/DART/SEIBro 단건성 운영 CLI. `bok-series`, `dart-corp-codes`, `dart-financial`, `seibro-reports` job 실행. |
| `scripts/compute_ta_indicators.py` | 초기 symbol_id 기반 TA-Lib 계산 CLI. 이후 ticker/segment 기반 `compute_technical_indicators_pipeline.py`가 주 경로로 전환. |
| `scripts/run_source_pilot.py` | KRX/KIS source pilot 실행. primary source 결정 전 API 정상화와 품질 기준 확인용. |
| `scripts/apply_migrations.ps1` | SQL migration 적용 보조 PowerShell 스크립트. |

## 5. 공용 DB 객체 요약

> 상세 row count와 컬럼은 `docs/public_server_db_tables.md` 기준. 여기서는 전체 객체와 한 줄 역할만 기록.

### 5.1 `meta`

| 객체 | 한 줄 설명 |
|---|---|
| `meta.data_source` | 데이터 출처 마스터. |
| `meta.ingestion_run` | 수집/계산/검증 실행 이력. |
| `meta.ingestion_cursor` | 증분 수집·resume cursor. |
| `meta.api_request_log` | 외부 API 요청 관측성 로그. |
| `meta.data_quality_issue` | 데이터 품질 이슈 로그. |
| `meta.lineage_event` | source→target lineage 이벤트. |
| `meta.view_common_stock_universe` | KOSPI/KOSDAQ 상장 보통주 helper view. |

### 5.2 `raw`

| 객체 | 한 줄 설명 |
|---|---|
| `raw.ohlcv_response` | OHLCV API 원본 응답 payload. |
| `raw.seibro_report_response` | SEIBro 원본 payload. |
| `raw.analyst_report_summary` | SEIBro 분석리포트 요약 raw landing row. |
| `raw.bok_response` | BOK ECOS 원본 payload. |
| `raw.dart_response` | OpenDART 원본 payload. |

### 5.3 `core`

| 객체 | 한 줄 설명 |
|---|---|
| `core.symbol_master` | 종목 마스터. |
| `core.symbol_listing_history` | 상장/상폐/재상장 이력. |
| `core.symbol_name_history` | 종목명 변경 이력. |
| `core.trading_calendar` | 거래일 캘린더. |
| `core.ohlcv_daily` | KRX 기본 일봉 OHLCV canonical table. |
| `core.ohlcv_quality_daily` | OHLCV coverage/품질 집계. |

### 5.4 `feature`

| 객체 | 한 줄 설명 |
|---|---|
| `feature.adjusted_ohlcv_daily` | canonical adjusted OHLCV. |
| `feature.kis_adjusted_ohlcv_daily` | KIS 공식 수정주가 OHLCV. |
| `feature.ta_indicator_definition` | TA 지표 정의/파라미터/출력 스키마. |
| `feature.ta_trend_daily` | 초기 symbol_id 기준 추세 지표. |
| `feature.ta_momentum_daily` | 초기 symbol_id 기준 모멘텀 지표. |
| `feature.ta_volatility_daily` | 초기 symbol_id 기준 변동성 지표. |
| `feature.ta_volume_daily` | 초기 symbol_id 기준 거래량 지표. |
| `feature.ta_pattern_daily` | 초기 symbol_id 기준 캔들 패턴 지표. |
| `feature.ta_trend_ticker_daily` | ticker/segment 기준 추세 지표. |
| `feature.ta_momentum_ticker_daily` | ticker/segment 기준 모멘텀 지표. |
| `feature.ta_volatility_ticker_daily` | ticker/segment 기준 변동성 지표. |
| `feature.ta_volume_ticker_daily` | ticker/segment 기준 거래량 지표. |
| `feature.ta_pattern_ticker_daily` | ticker/segment 기준 캔들 패턴 지표. |
| `feature.seibro_report_summary` | SEIBro 리포트 feature 정규화 대상. |
| `feature.seibro_sentiment` | SEIBro sentiment score 대상. |
| `feature.seibro_universe_daily` | SEIBro 기반 일별 universe 대상. |
| `feature.bok_macro_daily` | BOK macro daily feature. |
| `feature.dart_corp_symbol_map` | DART corp code ↔ symbol 매핑. |
| `feature.dart_financial_quarterly` | DART 재무제표 quarterly feature. |

### 5.5 `mart`

| 객체 | 한 줄 설명 |
|---|---|
| `mart.symbol_feature_frame_asof` | adjusted OHLCV + TA + 종목 메타 통합 feature frame. |
| `mart.kis_adjusted_feature_frame_asof` | KIS 공식 수정주가 기준 feature frame. |
| `mart.common_stock_feature_frame_asof` | KIS 공식 수정주가 feature frame에서 KOSPI/KOSDAQ 상장 보통주만 남긴 MVP 백테스트 기본 view. |
| `mart.common_stock_universe_asof` | 날짜별 KOSPI/KOSDAQ 상장 보통주 universe view. |
| `mart.full_universe_asof` | 날짜별 투자 가능 universe. |
| `mart.data_coverage_report` | coverage/품질 요약 report view. |
| `mart.bok_macro_asof` | BOK macro as-of view. |
| `mart.dart_financial_asof` | DART financial as-of view. |
| `mart.seibro_universe_asof` | SEIBro universe as-of view. |

## 6. 품질·관측성·lineage 구현 포인트

| 포인트 | 구현 |
|---|---|
| 원본 보존 | raw 계층에 API/WebSquare payload 저장. request/payload hash로 중복 방지. |
| idempotent 적재 | 대부분 `ON CONFLICT DO NOTHING` 또는 `ON CONFLICT DO UPDATE`로 재실행 가능하게 구현. |
| run 추적 | 모든 수집/계산/검증 작업은 `meta.ingestion_run`의 `run_id` 기준으로 추적. |
| API 관측성 | KIS/SEIBro/BOK/DART 요청 단위로 success, status, retry, elapsed, error, metadata 기록. |
| cursor/resume | KIS window 완료 상태와 OHLCV 마지막 성공일을 cursor로 관리. 장기 backfill 중단 후 재개 가능. |
| 품질 검사 | 수집 중 즉시 flags + 별도 QA stage 병행. missing, stale, volume anomaly, KIS/KRX consistency 검사. |
| lineage | raw→core, KIS API→feature, adjusted OHLCV→TA, feature→mart view 관계 기록. transform version 포함. |
| mart 안정성 | 백테스트 쪽은 여러 테이블을 직접 join하지 않고 mart view를 조회하도록 설계. |

## 7. 발표/인수인계 시 설명 포인트

| 질문 | 답변 요지 |
|---|---|
| raw와 core를 왜 나눴는가 | raw는 증거 보관, core는 분석 가능한 canonical 데이터. 원본 재처리와 정규화 책임 분리를 위해 구현. |
| KRX와 KIS를 왜 둘 다 저장했는가 | KRX는 전 종목 기본 OHLCV 커버리지, KIS는 공식 수정주가 확보 목적. 백테스트 가격 기준은 KIS adjusted mart view 우선 사용. |
| TA를 왜 미리 계산했는가 | 백테스트 시 매번 대량 지표를 계산하지 않도록 feature table에 선계산. 종목 단위 병렬 처리로 10년치 대량 계산 시간을 줄임. |
| ticker 기반 TA로 왜 전환했는가 | symbol_id만 쓰면 재상장/종목 변경/segment 처리가 약함. ticker/base_ticker/segment_id 기준으로 상장 구간과 재상장 구간을 분리하기 위해 전환. |
| SEIBro raw와 feature가 왜 분리됐는가 | 현재 10년치 요약 raw row는 적재 완료. sentiment/universe feature는 후속 모델링 단계에서 별도 변환 가능하도록 분리. |
| 품질 이슈 row가 많은 이유 | 누락일, stale, volume anomaly 등 규칙 기반 이슈를 모두 이벤트로 남기는 구조. 데이터 삭제가 아니라 진단용 로그. |
| 보통주만 모은 객체는 무엇인가 | `meta.view_common_stock_universe`가 KOSPI/KOSDAQ 상장 보통주 helper view. 공용 DB 기준 합계 2,554개. 백테스트 입력은 migration 007의 `mart.common_stock_feature_frame_asof`로 고정 예정. |
| 서버 이관 시 필요한 것 | migration 001~007 적용 후 data dump/restore. mart view는 데이터가 아니라 migration으로 재생성. 단, 현재 repo의 007 파일은 비어 있어 SQL 보강 필요. |

## 8. 향후 보강하면 좋은 항목

| 우선순위 | 보강 항목 | 이유 |
|---|---|---|
| 높음 | `migrations/007_common_stock_mart_views.sql` SQL 작성/적용 | 파일은 존재하지만 현재 내용이 비어 있음. `mart.common_stock_feature_frame_asof`, `mart.common_stock_universe_asof`를 실제 DB에 생성해야 MVP 보통주 백테스트 입력 고정 가능. |
| 높음 | SEIBro raw → `feature.seibro_report_summary` 변환 job 추가 | raw 10년치는 있지만 feature/mart SEIBro 계층은 후속 변환 필요. |
| 중간 | BOK/DART 증분 운영 표준화 | BOK `rate-fx`, BOK 월별 유가(`902Y003:010101`, `902Y003:010102`, `902Y003:010103`), DART CFS 장기 백필은 완료. 이후에는 신규 월/분기 데이터 증분 수집, 실제 발표일 부재 series의 보수적 as-of lag 정책, 실패 run 정리와 서버/로컬 동일 검증 자동화가 필요하다. |
| 중간 | mart view별 권장 사용처 문서화 | 백테스트 입력 혼동 방지. `kis_adjusted_feature_frame_asof`와 common-stock view 구분 필요. |
| 중간 | Airflow runbook에 장애 복구 절차 추가 | KIS token/rate limit, SEIBro page 실패, TA worker 실패 시 재개 절차 표준화 가능. |
| 낮음 | TA indicator catalog와 실제 ticker TA output 매핑 문서화 | 지표 추가/삭제 시 백테스트 feature schema 이해도 개선. |

## 9. 주요 근거 파일

| 주장 | 근거 |
|---|---|
| 5개 스키마 생성 | `migrations/001_data_engineering_m0.sql:6-10` |
| raw/core/feature/mart 기본 테이블 생성 | `migrations/001_data_engineering_m0.sql:84-314` |
| `feature.adjusted_ohlcv_daily`와 ticker TA 테이블 생성 | `migrations/003_quality_observability_lineage.sql:17-64` |
| KIS adjusted mart view 생성 | `migrations/003_quality_observability_lineage.sql:77` |
| mart feature frame 재작성 | `migrations/004_mart_symbol_metadata.sql:41-83` |
| security type 분류와 common-stock universe helper | `migrations/006_symbol_security_type_classification.sql:3-103` |
| KOSPI/KOSDAQ 상장 보통주 2,554개 현황 | `docs/public_server_db_tables.md:90`, `docs/public_server_db_tables.md:574` |
| 보통주 전용 mart view 정의 대상 | `docs/public_server_db_tables.md:402-470`, `migrations/007_common_stock_mart_views.sql` |
| OHLCV CLI와 service 연결 | `scripts/ingest_ohlcv.py:22`, `scripts/ingest_ohlcv.py:53` |
| OHLCV chunk 수집, raw 저장, core upsert, 품질 검사 | `quant_agent/data/ingestion.py:39-82`, `quant_agent/data/repository.py:154-358`, `quant_agent/data/repository.py:624` |
| KIS 수정주가 flag/window/병렬/resume/row 변환 | `scripts/ingest_kis_adjusted_ohlcv.py:3-46`, `scripts/ingest_kis_adjusted_ohlcv.py:223-236`, `scripts/ingest_kis_adjusted_ohlcv.py:548-804` |
| TA 병렬 처리와 전처리/지표 계산 | `scripts/compute_technical_indicators_pipeline.py:43-61`, `scripts/compute_technical_indicators_pipeline.py:390`, `scripts/compute_technical_indicators_pipeline.py:812-1082` |
| SEIBro backfill chunk/page/upsert/lineage | `scripts/backfill_seibro_analyst_reports.py:25-47`, `quant_agent/data/external.py:197-302` |
| KIS adjusted full pipeline 순서와 테스트 | `scripts/run_kis_adjusted_full_pipeline.py:27-29`, `scripts/run_kis_adjusted_full_pipeline.py:85-174` |
| 공용 서버 DB row count와 객체 현황 | `docs/public_server_db_tables.md` |
