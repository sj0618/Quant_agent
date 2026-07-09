# 공용 서버 DB 테이블/뷰 전체 현황

작성일: 2026-06-04
대상 DB: 공용 서버 PostgreSQL/TimescaleDB `quant_agent` 및 로컬 동기화 DB
검증 기준: Docker 컨테이너 `quant-agent-db`의 실제 row count와 `information_schema.columns` 기준 스키마.

## 1. 결론

| 구분 | 상태 |
|---|---|
| KRX 기본 OHLCV | 10년 구간 적재 완료. |
| KIS 수정주가 | 10년 구간 적재 완료. |
| TA 지표 | 10년 구간 적재 완료. 정의 카탈로그는 158개, 현재 ticker 기반 백테스트 feature에 선계산 저장된 기본 지표 key는 45개. |
| SEIBro raw | 10년 구간 적재 완료. |
| SEIBro feature/mart | 스키마만 있고 데이터 미적재. raw → feature 변환 미실행 상태. |
| BOK | `rate-fx` preset 12개 series 10년치 로컬 적재 완료. `feature.bok_macro_daily`/`mart.bok_macro_asof` 기준 30,465건. |
| OpenDART | CFS 재무제표 2016~2026 period_end 구간 로컬 적재 완료. `raw.dart_response` 81,021건, `feature.dart_financial_quarterly`/`mart.dart_financial_asof` 73,342건, `2016-03-31 ~ 2026-03-31`. |

## 2. 먼저 볼 객체

| 목적 | 우선 객체 | 상태 |
|---|---|---|
| MVP 보통주 백테스트 입력 | `mart.common_stock_feature_frame_asof` | 공용 서버 DB에 생성 완료. |
| 날짜별 보통주 universe | `mart.common_stock_universe_asof` | 공용 서버 DB에 생성 완료. |
| 수정주가 백테스트 입력 | `mart.kis_adjusted_feature_frame_asof` | 정상 조회 가능함. |
| 일반 조정 OHLCV 백테스트 입력 | `mart.symbol_feature_frame_asof` | 정상 조회 가능함. |
| 투자 가능 universe | `mart.full_universe_asof` | 정상 조회 가능함. |
| 원천 일봉 검증 | `core.ohlcv_daily` | KRX 10년 데이터 있음. |
| KIS 수정주가 원천 검증 | `feature.kis_adjusted_ohlcv_daily` | KIS 10년 데이터 있음. |
| SEIBro 원천 검증 | `raw.analyst_report_summary` | SEIBro 분석리포트 요약 10년 데이터 있음. |
| OpenDART 적재 확인 | `raw.dart_response`, `feature.dart_*`, `mart.dart_financial_asof` | CFS 재무제표 `2016-03-31 ~ 2026-03-31` 구간 적재 완료. feature/mart row delta 0건. |
| BOK macro 확인 | `raw.bok_response`, `feature.bok_macro_daily`, `mart.bok_macro_asof` | `rate-fx` 12개 series 10년치 적재 완료. |

## 3. 전체 객체 row count

### 3.1 `core` 테이블

| 객체 | row 수 | 기간/범위 | 상태 |
|---|---:|---|---|
| `core.ohlcv_daily` | 5,943,964 | `2016-05-20 ~ 2026-05-20` | KRX 10년 OHLCV 적재 완료. |
| `core.ohlcv_quality_daily` | 281,974 | `2016-12-31 ~ 2026-05-21` | OHLCV 품질 결과 적재 완료. |
| `core.symbol_listing_history` | 3,682 | `2016-05-20 ~ 현재 유효 구간 포함` | 상장 이력 적재 완료. |
| `core.symbol_master` | 3,226 | 종목 마스터 | 적재 완료. |
| `core.symbol_name_history` | 3,226 | `2016-05-20 ~ 현재 유효 구간 포함` | 종목명 이력 적재 완료. |
| `core.trading_calendar` | 2,453 | `2016-05-20 ~ 2026-05-20` | 거래일 달력 적재 완료. |

### 3.2 `raw` 테이블

| 객체 | row 수 | 기간/범위 | 상태 |
|---|---:|---|---|
| `raw.analyst_report_summary` | 221,646 | `2016-05-20 ~ 2026-05-20` | SEIBro 분석리포트 요약 raw row 적재 완료. |
| `raw.bok_response` | 144 | BOK `rate-fx` 12개 series 요청 payload | BOK ECOS 원본 응답 적재 완료. |
| `raw.dart_response` | 81,021 | OpenDART 재무제표 API 응답 payload | DART CFS 재무제표 원본 payload 적재 완료. |
| `raw.ohlcv_response` | 6,107 | `2016-05-20 ~ 2026-05-21` 요청 | KRX raw 응답 적재 완료. |
| `raw.seibro_report_response` | 734 | SEIBro 요청 payload | SEIBro raw payload 적재 완료. |

### 3.3 `feature` 테이블

| 객체 | row 수 | 기간/범위 | 상태 |
|---|---:|---|---|
| `feature.adjusted_ohlcv_daily` | 6,409,656 | `2016-05-20 ~ 2026-05-20` | 조정 OHLCV feature 적재 완료. |
| `feature.bok_macro_daily` | 30,465 | `2016-01-01 ~ 2026-05-28`, 12개 series | BOK `rate-fx` 10년치 적재 완료. KOFR은 원천 제공 시작일 영향으로 `2021-11-25`부터 있음. |
| `feature.dart_corp_symbol_map` | 3,967 | DART corp code ↔ ticker 매핑 | corp-code 매핑 적재됨. |
| `feature.dart_financial_quarterly` | 73,342 | `2016-03-31 ~ 2026-03-31`, 2,506개 symbol | DART CFS 재무제표 적재 완료. |
| `feature.kis_adjusted_ohlcv_daily` | 5,997,018 | `2016-05-20 ~ 2026-05-20` | KIS 수정주가 적재 완료. |
| `feature.seibro_report_summary` | 0 | 없음 | SEIBro feature 변환 미실행으로 데이터 미적재. |
| `feature.seibro_sentiment` | 0 | 없음 | SEIBro sentiment 산출 미실행으로 데이터 미적재. |
| `feature.seibro_universe_daily` | 0 | 없음 | SEIBro universe 산출 미실행으로 데이터 미적재. |
| `feature.ta_indicator_definition` | 158 | 지표 정의 | TA 지표 정의 적재 완료. |
| `feature.ta_momentum_daily` | 68,455 | `2016-05-20 ~ 2026-05-20` | symbol_id 기준 모멘텀 지표 적재 완료. |
| `feature.ta_momentum_ticker_daily` | 6,372,926 | `2016-05-20 ~ 2026-05-20` | ticker 기준 모멘텀 지표 적재 완료. |
| `feature.ta_pattern_daily` | 68,455 | `2016-05-20 ~ 2026-05-20` | symbol_id 기준 패턴 지표 적재 완료. |
| `feature.ta_pattern_ticker_daily` | 6,409,656 | `2016-05-20 ~ 2026-05-20` | ticker 기준 패턴 지표 적재 완료. |
| `feature.ta_trend_daily` | 68,455 | `2016-05-20 ~ 2026-05-20` | symbol_id 기준 추세 지표 적재 완료. |
| `feature.ta_trend_ticker_daily` | 6,363,428 | `2016-05-20 ~ 2026-05-20` | ticker 기준 추세 지표 적재 완료. |
| `feature.ta_volatility_daily` | 68,424 | `2016-05-23 ~ 2026-05-20` | symbol_id 기준 변동성 지표 적재 완료. 일부 지표 warmup 영향 있음. |
| `feature.ta_volatility_ticker_daily` | 6,358,234 | `2016-05-20 ~ 2026-05-20` | ticker 기준 변동성 지표 적재 완료. |
| `feature.ta_volume_daily` | 68,455 | `2016-05-20 ~ 2026-05-20` | symbol_id 기준 거래량 지표 적재 완료. |
| `feature.ta_volume_ticker_daily` | 6,409,656 | `2016-05-20 ~ 2026-05-20` | ticker 기준 거래량 지표 적재 완료. |

### 3.4 `mart` / `meta` view

| 객체 | row 수 | 기간/범위 | 상태 |
|---|---:|---|---|
| `mart.bok_macro_asof` | 30,465 | `2016-01-01 ~ 2026-05-28`, 12개 series | BOK macro as-of view 정상 조회됨. |
| `mart.dart_financial_asof` | 73,342 | `2016-03-31 ~ 2026-03-31`, 2,506개 symbol | DART 재무제표 as-of view 정상 조회 가능. |
| `mart.data_coverage_report` | 281,974 | `2016-12-31 ~ 2026-05-21` | 품질 리포트 view 정상. |
| `mart.full_universe_asof` | 5,477,595 | `2016-05-20 ~ 2026-05-20` | universe view 정상. |
| `mart.kis_adjusted_feature_frame_asof` | 5,943,964 | `2016-05-20 ~ 2026-05-20` | KIS 수정주가 feature frame view 정상. |
| `mart.seibro_universe_asof` | 0 | 없음 | SEIBro universe feature 미적재로 비어 있음. |
| `mart.symbol_feature_frame_asof` | 6,409,656 | `2016-05-20 ~ 2026-05-20` | 조정 OHLCV feature frame view 정상. |
| `meta.view_common_stock_universe` | 2,554 | 종목 universe | 공통주 universe helper view 정상. |

### 3.5 `meta` 테이블

| 객체 | row 수 | 상태 |
|---|---:|---|
| `meta.api_request_log` | 739 | API 요청 로그 적재됨. |
| `meta.data_quality_issue` | 4,956,717 | 품질 점검 이슈 로그 적재됨. |
| `meta.data_source` | 7 | 데이터 소스 마스터 적재됨. |
| `meta.ingestion_cursor` | 2 | 증분 수집 커서 일부 있음. |
| `meta.ingestion_run` | 175 | 수집/처리 실행 이력 적재됨. |
| `meta.lineage_event` | 47,446,731 | lineage 이벤트 적재됨. |

## 4. 미적재/주의 목록

| 객체 | 현재 상태 | 해석 |
|---|---|---|
| `feature.seibro_report_summary` | 0건 | SEIBro raw → feature 변환 미실행. |
| `feature.seibro_sentiment` | 0건 | SEIBro sentiment 산출 미실행. |
| `feature.seibro_universe_daily` | 0건 | SEIBro universe 산출 미실행. |
| `mart.seibro_universe_asof` | 0건 | 하위 SEIBro universe feature 미적재로 비어 있음. |
| `meta.ingestion_run` | 실패 run 2건 존재 | DART 초반 timeout/network 실패 이력이 남아 있으나 연도별 재실행 후 feature/mart 정합성 검증은 통과. error_message는 API URL/키 포함 가능성이 있어 문서에 원문을 남기지 않는다. |

## 5. `core` 스키마 상세

### `core.symbol_master`

| 항목 | 내용 |
|---|---|
| 용도 | 종목 마스터 테이블. |
| row 수 | 3,226 |
| 상태 | 적재 완료. |
| 컬럼 | `symbol_id bigint`, `symbol text`, `name text`, `market text`, `security_type text`, `created_at timestamptz`, `updated_at timestamptz`, `market_segment text`, `listing_status text`, `listed_at date`, `delisted_at date`, `metadata_jsonb jsonb` |

### `core.symbol_listing_history`

| 항목 | 내용 |
|---|---|
| 용도 | 종목별 상장/상폐/상태 변경 이력 테이블. |
| row 수 | 3,682 |
| 상태 | 적재 완료. |
| 컬럼 | `symbol_id bigint`, `valid_from date`, `valid_to date`, `market text`, `listing_status text`, `source_id text`, `run_id uuid`, `event_type text`, `metadata_jsonb jsonb` |

### `core.symbol_name_history`

| 항목 | 내용 |
|---|---|
| 용도 | 종목명 변경 이력 테이블. |
| row 수 | 3,226 |
| 상태 | 적재 완료. |
| 컬럼 | `symbol_id bigint`, `valid_from date`, `valid_to date`, `name text`, `source_id text`, `run_id uuid`, `metadata_jsonb jsonb` |

### `core.trading_calendar`

| 항목 | 내용 |
|---|---|
| 용도 | 시장별 거래일/휴장일 달력 테이블. |
| row 수 | 2,453 |
| 상태 | `2016-05-20 ~ 2026-05-20` 적재 완료. |
| 컬럼 | `market text`, `trade_date date`, `is_open boolean`, `reason text`, `source_id text`, `run_id uuid` |

### `core.ohlcv_daily`

| 항목 | 내용 |
|---|---|
| 용도 | KRX 기본 일봉 OHLCV 원천 테이블. |
| row 수 | 5,943,964 |
| 상태 | `2016-05-20 ~ 2026-05-20` 10년 구간 적재 완료. |
| 컬럼 | `symbol_id bigint`, `trade_date date`, `open numeric`, `high numeric`, `low numeric`, `close numeric`, `volume numeric`, `source_id text`, `run_id uuid`, `is_tradable boolean`, `quality_flags jsonb`, `created_at timestamptz`, `updated_at timestamptz` |

### `core.ohlcv_quality_daily`

| 항목 | 내용 |
|---|---|
| 용도 | OHLCV coverage/누락/품질 집계 테이블. |
| row 수 | 281,974 |
| 상태 | 품질 점검 결과 적재 완료. |
| 컬럼 | `symbol_id bigint`, `as_of_date date`, `expected_days integer`, `observed_days integer`, `coverage_ratio numeric`, `missing_days integer`, `issue_count integer`, `run_id uuid` |

## 6. `raw` 스키마 상세

### `raw.ohlcv_response`

| 항목 | 내용 |
|---|---|
| 용도 | OHLCV 수집 API 원본 응답 payload 저장 테이블. |
| row 수 | 6,107 |
| 상태 | KRX raw 응답 적재 완료. |
| 컬럼 | `raw_id bigint`, `source_id text`, `request_date date`, `request_hash text`, `payload_hash text`, `payload_jsonb jsonb`, `run_id uuid`, `created_at timestamptz` |

### `raw.seibro_report_response`

| 항목 | 내용 |
|---|---|
| 용도 | SEIBro WebSquare/API 원본 payload 저장 테이블. |
| row 수 | 734 |
| 상태 | SEIBro 수집 payload 적재 완료. |
| 비고 | `raw.analyst_report_summary`의 source raw payload 역할. |
| 컬럼 | `raw_id bigint`, `query_window text`, `payload_hash text`, `payload_jsonb jsonb`, `run_id uuid`, `created_at timestamptz` |

### `raw.analyst_report_summary`

| 항목 | 내용 |
|---|---|
| 용도 | SEIBro 분석리포트 요약 API row를 컬럼화한 raw landing 테이블. |
| row 수 | 221,646 |
| 상태 | `2016-05-20 ~ 2026-05-20` 10년 구간 적재 완료. |
| 비고 | AI 요약 테이블이 아님. SEIBro 응답 안의 `ENTR_SUMM_CONTENT` 등 원천 row를 파싱한 결과. |
| 컬럼 | `report_date date`, `ticker text`, `company_name text`, `summary text`, `opinion text`, `target_price numeric`, `close_price numeric`, `institution text`, `author text`, `source_payload_hash text`, `raw_jsonb jsonb`, `run_id uuid`, `created_at timestamptz`, `updated_at timestamptz` |

### `raw.bok_response`

| 항목 | 내용 |
|---|---|
| 용도 | BOK ECOS 원본 응답 payload 저장 테이블. |
| row 수 | 144 |
| 상태 | `rate-fx` preset 12개 series 원본 응답 적재 완료. |
| 컬럼 | `raw_id bigint`, `stat_code text`, `item_code text`, `payload_hash text`, `payload_jsonb jsonb`, `run_id uuid`, `created_at timestamptz` |

### `raw.dart_response`

| 항목 | 내용 |
|---|---|
| 용도 | OpenDART 원본 응답 payload 저장 테이블. |
| row 수 | 81,021 |
| 상태 | OpenDART CFS 재무제표 수집 payload 적재 완료. feature 변환 기준 `2016-03-31 ~ 2026-03-31` period_end 구간을 커버. |
| 컬럼 | `raw_id bigint`, `corp_code text`, `report_code text`, `payload_hash text`, `payload_jsonb jsonb`, `run_id uuid`, `created_at timestamptz` |

## 7. `feature` 스키마 상세

### 가격 feature

#### `feature.adjusted_ohlcv_daily`

| 항목 | 내용 |
|---|---|
| 용도 | 기본 OHLCV를 조정계수 기반으로 보정한 일봉 feature 테이블. |
| row 수 | 6,409,656 |
| 상태 | `2016-05-20 ~ 2026-05-20` 적재 완료. |
| 컬럼 | `time date`, `ticker text`, `base_ticker text`, `segment_id integer`, `open numeric`, `high numeric`, `low numeric`, `close numeric`, `volume numeric`, `adj_open numeric`, `adj_high numeric`, `adj_low numeric`, `adj_close numeric`, `adj_volume numeric`, `adjustment_factor numeric`, `quality_flags jsonb`, `run_id uuid`, `created_at timestamptz`, `updated_at timestamptz` |

#### `feature.kis_adjusted_ohlcv_daily`

| 항목 | 내용 |
|---|---|
| 용도 | KIS 수정주가 기준 OHLCV 테이블. |
| row 수 | 5,997,018 |
| 상태 | `2016-05-20 ~ 2026-05-20` 적재 완료. |
| 컬럼 | `time date`, `ticker text`, `adj_open numeric`, `adj_high numeric`, `adj_low numeric`, `adj_close numeric`, `adj_volume numeric`, `mod_yn text`, `revision_reason text`, `raw_payload_jsonb jsonb`, `quality_flags jsonb`, `run_id uuid`, `created_at timestamptz`, `updated_at timestamptz` |

### BOK/OpenDART/SEIBro feature

#### `feature.bok_macro_daily`

| 항목 | 내용 |
|---|---|
| 용도 | BOK ECOS 거시지표 일자별 feature 테이블. |
| row 수 | 30,465 |
| 상태 | `rate-fx` 12개 series 기준 `2016-01-01 ~ 2026-05-28` 적재 완료. KOFR(`817Y002:010901000`)은 BOK 원천 제공 시작 영향으로 `2021-11-25 ~ 2026-05-26` 구간만 있음. |
| 컬럼 | `series_id text`, `effective_date date`, `published_at timestamptz`, `value numeric`, `metadata_jsonb jsonb`, `run_id uuid` |

| series_id | 의미 | row 수 | 기간 |
|---|---|---:|---|
| `722Y001:0101000` | 한국은행 기준금리 | 3,801 | `2016-01-01 ~ 2026-05-28` |
| `731Y003:0000003` | 원/달러 종가 15:30 | 2,549 | `2016-01-04 ~ 2026-05-27` |
| `731Y003:0000006` | 원/100엔 | 2,549 | `2016-01-04 ~ 2026-05-27` |
| `731Y003:0000010` | 원/위안 종가 | 2,549 | `2016-01-04 ~ 2026-05-27` |
| `817Y002:010101000` | 콜금리(1일, 전체거래) | 2,559 | `2016-01-04 ~ 2026-05-27` |
| `817Y002:010190000` | 국고채(1년) | 2,559 | `2016-01-04 ~ 2026-05-27` |
| `817Y002:010200000` | 국고채(3년) | 2,559 | `2016-01-04 ~ 2026-05-27` |
| `817Y002:010210000` | 국고채(10년) | 2,559 | `2016-01-04 ~ 2026-05-27` |
| `817Y002:010300000` | 회사채(3년, AA-) | 2,559 | `2016-01-04 ~ 2026-05-27` |
| `817Y002:010320000` | 회사채(3년, BBB-) | 2,559 | `2016-01-04 ~ 2026-05-27` |
| `817Y002:010502000` | CD(91일) | 2,559 | `2016-01-04 ~ 2026-05-27` |
| `817Y002:010901000` | KOFR | 1,104 | `2021-11-25 ~ 2026-05-26` |

#### `feature.dart_corp_symbol_map`

| 항목 | 내용 |
|---|---|
| 용도 | OpenDART corp code와 종목코드 매핑 테이블. |
| row 수 | 3,967 |
| 상태 | corp code ↔ ticker 매핑 적재됨. |
| 컬럼 | `corp_code text`, `corp_name text`, `symbol text`, `modify_date text`, `run_id uuid`, `created_at timestamptz`, `updated_at timestamptz` |

#### `feature.dart_financial_quarterly`

| 항목 | 내용 |
|---|---|
| 용도 | OpenDART 분기/사업보고서 재무제표 feature 테이블. |
| row 수 | 73,342 |
| 상태 | CFS 기준 `2016-03-31 ~ 2026-03-31` period_end 구간 적재 완료. 2,506개 symbol 연결. |
| 컬럼 | `symbol_id bigint`, `corp_code text`, `period_end date`, `reported_at timestamptz`, `report_code text`, `fs_div text`, `accounts_jsonb jsonb`, `run_id uuid` |

#### `feature.seibro_report_summary`

| 항목 | 내용 |
|---|---|
| 용도 | SEIBro 분석리포트 요약 raw를 feature 계층으로 정규화할 대상 테이블. |
| row 수 | 0 |
| 상태 | 스키마만 있고 데이터 미적재. raw → feature 변환 미실행. |
| 컬럼 | `report_id bigint`, `symbol_id bigint`, `report_date date`, `company_name text`, `summary text`, `opinion text`, `target_price numeric`, `close_price numeric`, `institution text`, `author text`, `source_payload_hash text`, `run_id uuid` |

#### `feature.seibro_sentiment`

| 항목 | 내용 |
|---|---|
| 용도 | SEIBro 리포트 summary/opinion 기반 sentiment score 저장 테이블. |
| row 수 | 0 |
| 상태 | 스키마만 있고 데이터 미적재. sentiment 산출 미실행. |
| 컬럼 | `report_id bigint`, `sentiment_score numeric`, `model_version text`, `prompt_version text`, `scored_at timestamptz`, `run_id uuid` |

#### `feature.seibro_universe_daily`

| 항목 | 내용 |
|---|---|
| 용도 | SEIBro 리포트 기반 일별 관심 종목 universe 테이블. |
| row 수 | 0 |
| 상태 | 스키마만 있고 데이터 미적재. universe 산출 미실행. |
| 컬럼 | `as_of_date date`, `symbol_id bigint`, `avg_sentiment_score numeric`, `report_count integer`, `included boolean`, `exclusion_reason text`, `run_id uuid` |

### TA 정의/지표 feature

#### `feature.ta_indicator_definition`

| 항목 | 내용 |
|---|---|
| 용도 | TA 지표 정의, 파라미터, warmup, output schema 저장 테이블. |
| row 수 | 158 |
| 상태 | 적재 완료. |
| 컬럼 | `indicator_id bigint`, `category text`, `name text`, `parameters_jsonb jsonb`, `warmup_days integer`, `output_schema_jsonb jsonb`, `transform_version text` |

| 카테고리 | 정의 수 |
|---|---:|
| `Trend` | 56 |
| `Momentum` | 35 |
| `Volatility` | 3 |
| `Volume` | 3 |
| `Pattern` | 61 |
| **합계** | **158** |

> `feature.ta_indicator_definition`의 158개는 “계산 가능한 지표 카탈로그/정의”이다. 현재 mart 백테스트 경로가 실제로 읽는 ticker 기반 선계산 지표값은 아래 `feature.ta_*_ticker_daily.values_jsonb`에 저장된 기본 45개 key다. 정의 1개가 여러 output key를 만들 수 있어 `Volatility`는 정의 3개에서 `BBL/BBM/BBU/BBB/BBP` 등 7개 저장 key가 나온다.

#### `feature.ta_*_daily` 공통

| 테이블 | row 수 | 기간 | 저장 정보 |
|---|---:|---|---|
| `feature.ta_trend_daily` | 68,455 | `2016-05-20 ~ 2026-05-20` | symbol_id 기준 추세 지표. |
| `feature.ta_momentum_daily` | 68,455 | `2016-05-20 ~ 2026-05-20` | symbol_id 기준 모멘텀 지표. |
| `feature.ta_volatility_daily` | 68,424 | `2016-05-23 ~ 2026-05-20` | symbol_id 기준 변동성 지표. warmup 영향 있음. |
| `feature.ta_volume_daily` | 68,455 | `2016-05-20 ~ 2026-05-20` | symbol_id 기준 거래량 지표. |
| `feature.ta_pattern_daily` | 68,455 | `2016-05-20 ~ 2026-05-20` | symbol_id 기준 캔들 패턴 지표. |

| 항목 | 내용 |
|---|---|
| 공통 컬럼 | `symbol_id bigint`, `trade_date date`, `values_jsonb jsonb`, `run_id uuid`, `quality_flags jsonb` |
| 상태 | 위 5개 테이블 모두 적재 완료. |

#### `feature.ta_*_ticker_daily` 공통

| 테이블 | row 수 | 기간 | 저장 정보 |
|---|---:|---|---|
| `feature.ta_trend_ticker_daily` | 6,363,428 | `2016-05-20 ~ 2026-05-20` | ticker 기준 추세 지표. |
| `feature.ta_momentum_ticker_daily` | 6,372,926 | `2016-05-20 ~ 2026-05-20` | ticker 기준 모멘텀 지표. |
| `feature.ta_volatility_ticker_daily` | 6,358,234 | `2016-05-20 ~ 2026-05-20` | ticker 기준 변동성 지표. |
| `feature.ta_volume_ticker_daily` | 6,409,656 | `2016-05-20 ~ 2026-05-20` | ticker 기준 거래량 지표. |
| `feature.ta_pattern_ticker_daily` | 6,409,656 | `2016-05-20 ~ 2026-05-20` | ticker 기준 캔들 패턴 지표. |

| 항목 | 내용 |
|---|---|
| 공통 컬럼 | `time date`, `ticker text`, `base_ticker text`, `segment_id integer`, `values_jsonb jsonb`, `quality_flags jsonb`, `run_id uuid`, `created_at timestamptz`, `updated_at timestamptz` |
| 상태 | 위 5개 테이블 모두 적재 완료. `mart.symbol_feature_frame_asof`/`mart.kis_adjusted_feature_frame_asof`가 이 ticker 기반 TA 테이블을 join한다. |

| 카테고리 | ticker_daily 테이블 | 현재 선계산 key 수 | 선계산 key |
|---|---|---:|---|
| `Trend` | `feature.ta_trend_ticker_daily` | 16 | `ADXR_14_2`, `ADX_14`, `AROOND_25`, `AROONOSC_25`, `AROONU_25`, `DMN_14`, `DMP_14`, `EMA_20`, `EMA_200`, `EMA_50`, `MACD_12_26_9`, `MACDh_12_26_9`, `MACDs_12_26_9`, `SMA_20`, `SMA_200`, `SMA_50` |
| `Momentum` | `feature.ta_momentum_ticker_daily` | 8 | `CCI_20_0.015`, `MFI_14`, `ROC_10`, `RSI_14`, `STOCHd_14_3_3`, `STOCHh_14_3_3`, `STOCHk_14_3_3`, `WILLR_14` |
| `Volatility` | `feature.ta_volatility_ticker_daily` | 7 | `ATRr_14`, `BBB_20_2.0_2.0`, `BBL_20_2.0_2.0`, `BBM_20_2.0_2.0`, `BBP_20_2.0_2.0`, `BBU_20_2.0_2.0`, `NATR_14` |
| `Volume` | `feature.ta_volume_ticker_daily` | 4 | `AD`, `ADOSC_3_10`, `CMF_20`, `OBV` |
| `Pattern` | `feature.ta_pattern_ticker_daily` | 10 | `CDL_DARKCLOUDCOVER`, `CDL_DOJI_10_0.1`, `CDL_ENGULFING`, `CDL_EVENINGSTAR`, `CDL_HAMMER`, `CDL_HANGINGMAN`, `CDL_HARAMI`, `CDL_MORNINGSTAR`, `CDL_PIERCING`, `CDL_SHOOTINGSTAR` |
| **합계** | 5개 ticker_daily 테이블 | **45** | 현재 백테스트 mart 기본 입력 지표 |

## 8. `mart` view 상세

### `mart.symbol_feature_frame_asof`

| 항목 | 내용 |
|---|---|
| 용도 | `feature.adjusted_ohlcv_daily`와 TA ticker feature를 결합한 백테스트용 feature frame view. |
| row 수 | 6,409,656 |
| 상태 | 정상 조회 가능함. |
| 컬럼 | `as_of_date date`, `symbol text`, `name text`, `market_segment text`, `listing_status text`, `listed_at date`, `delisted_at date`, `ticker text`, `base_ticker text`, `segment_id integer`, `open numeric`, `high numeric`, `low numeric`, `close numeric`, `volume numeric`, `adjusted_ohlcv_quality_flags jsonb`, `trend_values jsonb`, `momentum_values jsonb`, `volatility_values jsonb`, `volume_values jsonb`, `pattern_values jsonb`, `adjusted_ohlcv_run_id uuid` |

### `mart.kis_adjusted_feature_frame_asof`

| 항목 | 내용 |
|---|---|
| 용도 | KIS 수정주가와 TA ticker feature를 결합한 백테스트용 feature frame view. |
| row 수 | 5,943,964 |
| 상태 | 정상 조회 가능함. |
| 컬럼 | `as_of_date date`, `symbol text`, `name text`, `market_segment text`, `listing_status text`, `listed_at date`, `delisted_at date`, `ticker text`, `base_ticker text`, `segment_id integer`, `open numeric`, `high numeric`, `low numeric`, `close numeric`, `volume numeric`, `adjusted_ohlcv_quality_flags jsonb`, `trend_values jsonb`, `momentum_values jsonb`, `volatility_values jsonb`, `volume_values jsonb`, `pattern_values jsonb`, `adjusted_ohlcv_run_id uuid` |

### `mart.symbol_feature_frame_asof` vs `mart.kis_adjusted_feature_frame_asof`

| 항목 | `mart.symbol_feature_frame_asof` | `mart.kis_adjusted_feature_frame_asof` |
|---|---|---|
| 관계 | 원본 통합 view | `mart.symbol_feature_frame_asof`의 부분집합 |
| 가격 소스 | `feature.adjusted_ohlcv_daily` 전체 | KIS 공식 수정주가 행만 |
| 필터 | 없음 | `adjusted_ohlcv_quality_flags->>'adjusted_price_method' = 'kis_official_adjusted'` |
| 포함 가능 보정 방식 | `kis_official_adjusted`, `close_ratio_back_adjustment` 등 | `kis_official_adjusted`만 |
| 권장 사용처 | 커버리지 진단, fallback 보정 데이터 확인, 백엔드 종목 상세 | 일반 백테스트/팩터 엔진 1순위 입력 |

실제 view 정의상 `mart.kis_adjusted_feature_frame_asof`는 아래와 같은 필터 view다.

```sql
CREATE OR REPLACE VIEW mart.kis_adjusted_feature_frame_asof AS
SELECT *
FROM mart.symbol_feature_frame_asof
WHERE adjusted_ohlcv_quality_flags->>'adjusted_price_method' = 'kis_official_adjusted';
```

#### 보통주 포함 여부

두 view는 **보통주 전용 view가 아니다.** `core.symbol_master.security_type`을 직접 필터링하지 않기 때문에 보통주 외에 우선주, SPAC, 리츠(REITs), 인프라펀드가 함께 포함될 수 있다.

최근 구간(`as_of_date >= '2026-05-01'`) 기준 로컬 DB 확인 결과:

| view | 보통주 | 우선주 | SPAC | 리츠(REITs) | 인프라펀드 |
|---|---:|---:|---:|---:|---:|
| `mart.symbol_feature_frame_asof` | 2,825 | 143 | 231 | 25 | 2 |
| `mart.kis_adjusted_feature_frame_asof` | 2,556 | 116 | 76 | 25 | 2 |

기존 view에서 보통주만 직접 조회하려면 반드시 `core.symbol_master`와 조인해서 `security_type = '보통주'` 조건을 추가한다.

```sql
SELECT f.*
FROM mart.kis_adjusted_feature_frame_asof f
JOIN core.symbol_master sm
  ON sm.symbol = f.symbol
WHERE sm.security_type = '보통주';
```

### `mart.common_stock_feature_frame_asof`

| 항목 | 내용 |
|---|---|
| 용도 | MVP 백테스트 기본 feature frame. `mart.kis_adjusted_feature_frame_asof`에서 보통주만 남긴 view. |
| 포함 universe | **보통주만 포함** |
| 가격 소스 | KIS 공식 수정주가(`adjusted_price_method = 'kis_official_adjusted'`) |
| 상태 | 공용 서버 DB에 생성 완료. MVP 백테스트 기본 조회 대상. |
| 컬럼 | `mart.kis_adjusted_feature_frame_asof`와 동일 |

MVP 백테스트/팩터 엔진은 기본적으로 이 view를 사용한다.

### `mart.common_stock_universe_asof`

| 항목 | 내용 |
|---|---|
| 용도 | MVP 날짜별 투자 가능 보통주 universe view. |
| 포함 universe | **보통주만 포함** |
| 가격 소스 | `mart.kis_adjusted_feature_frame_asof`에 존재하는 날짜/종목만 universe로 인정 |
| 상태 | 공용 서버 DB에 생성 완료. 보통주 universe 조회 기본 대상. |
| 컬럼 | `as_of_date date`, `symbol_id bigint`, `symbol text`, `name text`, `market_segment text`, `security_type text`, `listing_status text`, `listed_at date`, `delisted_at date` |

보통주 universe만 필요하면 이 view를 조회한다.

### `mart.full_universe_asof`

| 항목 | 내용 |
|---|---|
| 용도 | 날짜별 투자 가능 universe view. |
| row 수 | 5,477,595 |
| 상태 | 정상 조회 가능함. |
| 컬럼 | `as_of_date date`, `symbol_id bigint`, `symbol text`, `market_segment text`, `listing_status text` |

### `mart.data_coverage_report`

| 항목 | 내용 |
|---|---|
| 용도 | OHLCV coverage/품질 요약 view. |
| row 수 | 281,974 |
| 상태 | 정상 조회 가능함. |
| 컬럼 | `as_of_date date`, `symbol text`, `name text`, `market_segment text`, `listing_status text`, `expected_days integer`, `observed_days integer`, `coverage_ratio numeric`, `missing_days integer`, `issue_count integer` |

### `mart.bok_macro_asof`

| 항목 | 내용 |
|---|---|
| 용도 | BOK macro feature의 as-of 조회 view. |
| row 수 | 30,465 |
| 상태 | `rate-fx` 12개 series 기준 `2016-01-01 ~ 2026-05-28` 조회 가능. KOFR은 `2021-11-25`부터 조회됨. |
| 컬럼 | `series_id text`, `effective_date date`, `available_from date`, `value numeric`, `metadata_jsonb jsonb` |

### `mart.dart_financial_asof`

| 항목 | 내용 |
|---|---|
| 용도 | OpenDART 재무제표 as-of 조회 view. |
| row 수 | 73,342 |
| 상태 | `feature.dart_financial_quarterly` 전체 적재분(`2016-03-31 ~ 2026-03-31`) 조회 가능. feature/mart row delta 0건. |
| 컬럼 | `symbol text`, `corp_code text`, `period_end date`, `available_from date`, `report_code text`, `fs_div text`, `accounts_jsonb jsonb` |

### `mart.seibro_universe_asof`

| 항목 | 내용 |
|---|---|
| 용도 | SEIBro 리포트 기반 universe as-of 조회 view. |
| row 수 | 0 |
| 상태 | 하위 SEIBro universe feature 미적재로 비어 있음. |
| 컬럼 | `as_of_date date`, `symbol_id bigint`, `avg_sentiment_score numeric`, `report_count integer` |

## 9. `meta` 스키마 상세

### `meta.data_source`

| 항목 | 내용 |
|---|---|
| 용도 | 데이터 소스 마스터 테이블. |
| row 수 | 7 |
| 상태 | `BOK`, `DART`, `KIS`, `KRX`, `QA`, `SEIBRO`, `TA` 등록됨. |
| 컬럼 | `source_id text`, `name text`, `base_url_key text`, `version text`, `is_primary boolean`, `created_at timestamptz`, `updated_at timestamptz` |

### `meta.ingestion_run`

| 항목 | 내용 |
|---|---|
| 용도 | 수집/처리 실행 이력 테이블. |
| row 수 | 175 |
| 상태 | 실행 이력 적재됨. BOK `rate-fx` 10년치 적재 이력과 DART 2016~2026 연도별 재무제표 적재 이력이 반영됨. DART 초반 실패 run 2건은 재실행으로 데이터 정합성 검증 통과. |
| 컬럼 | `run_id uuid`, `dag_id text`, `task_id text`, `source_id text`, `started_at timestamptz`, `ended_at timestamptz`, `status text`, `params_jsonb jsonb`, `error_message text` |

### `meta.api_request_log`

| 항목 | 내용 |
|---|---|
| 용도 | API 요청/응답 상태 로그 테이블. |
| row 수 | 739 |
| 상태 | 요청 로그 적재됨. |
| 컬럼 | `request_id bigint`, `run_id uuid`, `source_id text`, `endpoint_key text`, `request_hash text`, `status_code integer`, `elapsed_ms integer`, `response_hash text`, `created_at timestamptz`, `success boolean`, `retry_count integer`, `error_message text`, `metadata_jsonb jsonb`, `request_started_at timestamptz` |

### `meta.ingestion_cursor`

| 항목 | 내용 |
|---|---|
| 용도 | 증분 수집 커서 테이블. |
| row 수 | 2 |
| 상태 | 일부 source/dataset 커서만 있음. |
| 컬럼 | `source_id text`, `dataset text`, `cursor_key text`, `cursor_value text`, `updated_at timestamptz` |

### `meta.lineage_event`

| 항목 | 내용 |
|---|---|
| 용도 | source → target 변환 lineage 이벤트 테이블. |
| row 수 | 47,446,731 |
| 상태 | 대량 lineage 로그 적재됨. |
| 컬럼 | `lineage_id bigint`, `target_table text`, `target_key text`, `source_table text`, `source_key text`, `run_id uuid`, `transform_version text`, `created_at timestamptz`, `metadata_jsonb jsonb` |

### `meta.data_quality_issue`

| 항목 | 내용 |
|---|---|
| 용도 | 데이터 품질 점검 이슈 저장 테이블. |
| row 수 | 4,956,717 |
| 상태 | 품질 점검 결과 적재됨. |
| 컬럼 | `issue_id bigint`, `run_id uuid`, `dataset text`, `symbol text`, `trade_date date`, `severity text`, `rule_code text`, `message text`, `created_at timestamptz` |

### `meta.view_common_stock_universe`

| 항목 | 내용 |
|---|---|
| 용도 | 공통주 universe helper view. |
| row 수 | 2,554 |
| 상태 | 정상 조회 가능함. |
| 컬럼 | `symbol_id bigint`, `symbol text`, `name text`, `market text`, `market_segment text`, `security_type text`, `listing_status text`, `listed_at date`, `delisted_at date`, `metadata_jsonb jsonb` |

## 10. 검증 SQL

아래 SQL은 row count 재검증용.

```sql
SELECT 'core.ohlcv_daily' AS object_name, count(*) FROM core.ohlcv_daily
UNION ALL SELECT 'core.ohlcv_quality_daily', count(*) FROM core.ohlcv_quality_daily
UNION ALL SELECT 'core.symbol_listing_history', count(*) FROM core.symbol_listing_history
UNION ALL SELECT 'core.symbol_master', count(*) FROM core.symbol_master
UNION ALL SELECT 'core.symbol_name_history', count(*) FROM core.symbol_name_history
UNION ALL SELECT 'core.trading_calendar', count(*) FROM core.trading_calendar
UNION ALL SELECT 'raw.analyst_report_summary', count(*) FROM raw.analyst_report_summary
UNION ALL SELECT 'raw.bok_response', count(*) FROM raw.bok_response
UNION ALL SELECT 'raw.dart_response', count(*) FROM raw.dart_response
UNION ALL SELECT 'raw.ohlcv_response', count(*) FROM raw.ohlcv_response
UNION ALL SELECT 'raw.seibro_report_response', count(*) FROM raw.seibro_report_response
UNION ALL SELECT 'feature.adjusted_ohlcv_daily', count(*) FROM feature.adjusted_ohlcv_daily
UNION ALL SELECT 'feature.bok_macro_daily', count(*) FROM feature.bok_macro_daily
UNION ALL SELECT 'feature.dart_corp_symbol_map', count(*) FROM feature.dart_corp_symbol_map
UNION ALL SELECT 'feature.dart_financial_quarterly', count(*) FROM feature.dart_financial_quarterly
UNION ALL SELECT 'feature.kis_adjusted_ohlcv_daily', count(*) FROM feature.kis_adjusted_ohlcv_daily
UNION ALL SELECT 'feature.seibro_report_summary', count(*) FROM feature.seibro_report_summary
UNION ALL SELECT 'feature.seibro_sentiment', count(*) FROM feature.seibro_sentiment
UNION ALL SELECT 'feature.seibro_universe_daily', count(*) FROM feature.seibro_universe_daily
UNION ALL SELECT 'feature.ta_indicator_definition', count(*) FROM feature.ta_indicator_definition
UNION ALL SELECT 'feature.ta_momentum_daily', count(*) FROM feature.ta_momentum_daily
UNION ALL SELECT 'feature.ta_momentum_ticker_daily', count(*) FROM feature.ta_momentum_ticker_daily
UNION ALL SELECT 'feature.ta_pattern_daily', count(*) FROM feature.ta_pattern_daily
UNION ALL SELECT 'feature.ta_pattern_ticker_daily', count(*) FROM feature.ta_pattern_ticker_daily
UNION ALL SELECT 'feature.ta_trend_daily', count(*) FROM feature.ta_trend_daily
UNION ALL SELECT 'feature.ta_trend_ticker_daily', count(*) FROM feature.ta_trend_ticker_daily
UNION ALL SELECT 'feature.ta_volatility_daily', count(*) FROM feature.ta_volatility_daily
UNION ALL SELECT 'feature.ta_volatility_ticker_daily', count(*) FROM feature.ta_volatility_ticker_daily
UNION ALL SELECT 'feature.ta_volume_daily', count(*) FROM feature.ta_volume_daily
UNION ALL SELECT 'feature.ta_volume_ticker_daily', count(*) FROM feature.ta_volume_ticker_daily
UNION ALL SELECT 'mart.bok_macro_asof', count(*) FROM mart.bok_macro_asof
UNION ALL SELECT 'mart.dart_financial_asof', count(*) FROM mart.dart_financial_asof
UNION ALL SELECT 'mart.data_coverage_report', count(*) FROM mart.data_coverage_report
UNION ALL SELECT 'mart.full_universe_asof', count(*) FROM mart.full_universe_asof
UNION ALL SELECT 'mart.kis_adjusted_feature_frame_asof', count(*) FROM mart.kis_adjusted_feature_frame_asof
UNION ALL SELECT 'mart.seibro_universe_asof', count(*) FROM mart.seibro_universe_asof
UNION ALL SELECT 'mart.symbol_feature_frame_asof', count(*) FROM mart.symbol_feature_frame_asof
UNION ALL SELECT 'meta.api_request_log', count(*) FROM meta.api_request_log
UNION ALL SELECT 'meta.data_quality_issue', count(*) FROM meta.data_quality_issue
UNION ALL SELECT 'meta.data_source', count(*) FROM meta.data_source
UNION ALL SELECT 'meta.ingestion_cursor', count(*) FROM meta.ingestion_cursor
UNION ALL SELECT 'meta.ingestion_run', count(*) FROM meta.ingestion_run
UNION ALL SELECT 'meta.lineage_event', count(*) FROM meta.lineage_event
UNION ALL SELECT 'meta.view_common_stock_universe', count(*) FROM meta.view_common_stock_universe;
```

아래 SQL은 BOK 10년치 적재 범위, DART 재무제표 적재 범위, TA 지표 개수 재검증용.

```sql
SELECT 'feature.bok_macro_daily' AS object_name,
       count(*) AS rows,
       count(DISTINCT series_id) AS series_count,
       min(effective_date) AS min_date,
       max(effective_date) AS max_date
FROM feature.bok_macro_daily
UNION ALL
SELECT 'mart.bok_macro_asof',
       count(*),
       count(DISTINCT series_id),
       min(effective_date),
       max(effective_date)
FROM mart.bok_macro_asof;

SELECT 'feature.dart_financial_quarterly' AS object_name,
       count(*) AS rows,
       count(DISTINCT symbol_id) AS symbol_count,
       min(period_end) AS min_period_end,
       max(period_end) AS max_period_end
FROM feature.dart_financial_quarterly
UNION ALL
SELECT 'mart.dart_financial_asof',
       count(*),
       count(DISTINCT symbol),
       min(period_end),
       max(period_end)
FROM mart.dart_financial_asof;

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

SELECT category, count(*) AS catalog_definitions
FROM feature.ta_indicator_definition
GROUP BY category
ORDER BY category;
```

## 11. 운영 메모

- `mart.*`는 view. 하위 `core.*`, `feature.*` 데이터가 없으면 row도 비어 있음.
- `feature.*` 중 TimescaleDB hypertable은 부모 테이블만 덤프하면 빈 COPY가 생길 수 있음. 이관 시 `COPY (SELECT * FROM feature.<table>) TO STDOUT` 방식 권장.
- `raw.analyst_report_summary`는 SEIBro 분석리포트 요약 raw row. `raw.seibro_report_response`를 AI가 요약한 결과가 아님.
- OpenDART는 CFS 재무제표 기준 `raw.dart_response` 81,021건, `feature.dart_financial_quarterly`/`mart.dart_financial_asof` 73,342건 적재 완료. `duplicate_feature_pk_groups`, `empty_or_null_accounts_jsonb`, `feature_mart_row_delta`, `feature_rows_without_corp_map` 검증값은 모두 0건이다.
- BOK는 `rate-fx` 12개 series 기준 `raw.bok_response` 144건, `feature.bok_macro_daily`/`mart.bok_macro_asof` 30,465건 적재 완료. KOFR은 원천 제공 시작일 때문에 2016년부터 존재하지 않는다.
- TA는 정의 카탈로그 158개와 현재 백테스트 mart 기본 입력 45개를 구분해야 한다. `feature.ta_indicator_definition`은 “정의”, `feature.ta_*_ticker_daily.values_jsonb`는 실제 선계산 값이다.
- SEIBro는 raw 10년치 적재 완료이나 `feature.seibro_*`와 `mart.seibro_universe_asof`는 미적재.

<!-- DART_BOK_LOCAL_STATUS:START -->
## 부록. 로컬 DB DART/BOK 적재 현황

갱신 시각: `2026-06-04T04:58:36.5479+00:00`

| 객체 | rows | 범위/비고 |
|---|---:|---|
| `feature.bok_macro_daily` | 30,465 | 12 series, `2016-01-01 ~ 2026-05-28` |
| `feature.dart_corp_symbol_map` | 3,967 | stock-code mapping symbols 3,967개 |
| `feature.dart_financial_quarterly` | 73,342 | symbols 2,506개, `2016-03-31 ~ 2026-03-31` |

DART 재무제표 연도별 적재 현황:

| year | rows | symbols | period range |
|---:|---:|---:|---|
| 2016 | 5,652 | 1,494 | `2016-03-31 ~ 2016-12-31` |
| 2017 | 5,987 | 1,573 | `2017-03-31 ~ 2017-12-31` |
| 2018 | 6,357 | 1,669 | `2018-03-31 ~ 2018-12-31` |
| 2019 | 6,647 | 1,733 | `2019-03-31 ~ 2019-12-31` |
| 2020 | 6,959 | 1,821 | `2020-03-31 ~ 2020-12-31` |
| 2021 | 7,246 | 1,897 | `2021-03-31 ~ 2021-12-31` |
| 2022 | 7,531 | 1,960 | `2022-03-31 ~ 2022-12-31` |
| 2023 | 7,939 | 2,099 | `2023-03-31 ~ 2023-12-31` |
| 2024 | 8,312 | 2,167 | `2024-03-31 ~ 2024-12-31` |
| 2025 | 8,574 | 2,218 | `2025-03-31 ~ 2025-12-31` |
| 2026 | 2,138 | 2,138 | `2026-03-31 ~ 2026-03-31` |

운영 메모:

- DART 재무제표는 연도 단위로 분할 적재한다.
- `feature.dart_financial_quarterly` 기본키는 `(symbol_id, period_end, report_code, fs_div)`이므로 같은 연도 재실행 시 중복 row는 삽입되지 않는다.
- OpenDART `013` 응답은 해당 회사/보고서 데이터 없음으로 간주해 raw 응답만 보존하고 feature row는 생성하지 않는다.
- 검증 산출물은 `.omx/logs/dart-validation-20260604-095618.md`와 `.omx/logs/dart-validation-20260604-095618.json`에 저장되어 있다.
<!-- DART_BOK_LOCAL_STATUS:END -->
