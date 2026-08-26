# DART/BOK 및 Airflow 데이터 엔지니어링 스크립트 정리

## 결론

| 파일 | 목적 | 실행 주기/방식 |
|---|---|---|
| `scripts/ingest_dart_bok_history.py` | OpenDART 재무제표와 BOK ECOS 매크로 시계열을 기존 PostgreSQL feature 테이블에 스키마 스캔 후 적재 | 수동 1달 테스트, 10년 백필, Airflow 일일 실행. BOK `rate-fx` 12개 series, 월별 유가 3개 series(WTI/Dubai/Brent), DART CFS 재무제표 2016~2026 period_end 구간은 적재 완료. |
| `DE/airflow/dags/quant_agent_data_engineering.py` | OHLCV, KIS 수정주가, TA, DQ, BOK, DART 일일 자동 수집 DAG | 기본 cron `0 4 * * *` |
| `scripts/ingest_ohlcv.py` | KRX 등 원천 OHLCV 적재 | DAG `ingest_ohlcv_daily` |
| `scripts/ingest_kis_adjusted_ohlcv.py` | KIS 공식 수정주가 OHLCV 적재 | DAG `ingest_kis_adjusted_ohlcv_daily` |
| `scripts/compute_technical_indicators_pipeline.py` | 수정주가 기반 TA 지표 계산 | DAG `compute_ta_indicators_daily` |
| `scripts/refresh_symbol_metadata.py` | 종목 메타데이터/분류 갱신 | DAG `refresh_symbol_metadata_daily` |
| `scripts/ingest_wics_sectors.py` | FnGuide Company Guide WICS 섹터 스냅샷을 로컬 DB의 `core.symbol_master` 섹터 컬럼들(`sector`/`sector_source`/`sector_as_of`/`sector_run_id`)에 1회 적재 | 별도 one-shot 실행 |
| `scripts/run_data_quality_checks.py` | 데이터 품질 검사 실행 | DAG `run_data_quality_checks_daily` |

## 1. `scripts/ingest_dart_bok_history.py`

### 핵심 원칙

| 원칙 | 구현 |
|---|---|
| API 키 하드코딩 금지 | `load_runtime_dotenv()`가 `QUANT_DOTENV_PATH` 또는 repo `.env`를 `python-dotenv`로 로드하고, 값은 출력하지 않는다. |
| DB 스키마 임의 변경 금지 | `scan_required_schemas()`와 `scan_table_schema()`가 `information_schema`에서 실제 컬럼/PK/UNIQUE를 읽는다. `CREATE`/`ALTER`는 없다. |
| 기존 테이블 구조 준수 | `validate_required_values()`가 non-null/no-default 컬럼 누락을 실패 처리한다. |
| 중복 방지 | `insert_rows()`가 모든 적재를 `ON CONFLICT DO NOTHING`으로 수행한다. |
| Rate Limit 고려 | `--bok-request-sleep-seconds`, `--dart-request-sleep-seconds`로 API 호출 사이 대기한다. |

### 주요 함수

| 함수 | 동작 |
|---|---|
| `main()` | CLI 인자를 파싱하고 `.env` 로드 → DB 접속 → 대상/보조 테이블 스키마 스캔 → BOK/DART 수집 실행 → JSON 결과 파일 저장. |
| `parse_args()` | `--scope test-1m/full-10y/daily/custom`, `--sources both/bok/dart`, DART/BOK sleep, DART 종목 제한, DART 보고서 모드 등을 정의한다. |
| `load_runtime_dotenv()` | `python-dotenv`로 런타임 환경변수를 채운다. 비밀값을 로그로 남기지 않는다. |
| `connect_db()` | `QUANT_DB_DSN`/`DATABASE_URL` 또는 `QUANT_DB_HOST/PORT/NAME/USER/PASSWORD` 계열 환경변수로 psycopg 연결을 만든다. |
| `scan_required_schemas()` | `feature.bok_macro_daily`, `feature.dart_financial_quarterly`를 필수 스캔하고, raw/meta/map 테이블은 있으면 스캔한다. |
| `scan_table_schema()` | 컬럼명, 타입, nullable, default, identity, primary key, unique constraints를 조회한다. |
| `assert_target_columns()` | 수집 매핑에 반드시 필요한 컬럼이 없으면 스키마 불일치로 중단한다. |
| `resolve_date_window()` | `test-1m`은 최근 30일, `full-10y`는 기본 `2016-01-01`부터 오늘까지, `daily`는 일일 lookback, `custom`은 명시 날짜를 사용한다. |
| `start_ingestion_run()` / `finish_ingestion_run()` | `meta.ingestion_run`에 실행 이력을 남긴다. 중복 source는 `ON CONFLICT DO NOTHING`으로 처리한다. |
| `ingest_bok_history()` | `BOK_SERIES_JSON`/`BOK_DAILY_SERIES_JSON`의 통계코드 목록을 기간 chunk로 호출하고 `feature.bok_macro_daily`에 적재한다. |
| `load_bok_series_configs()` | BOK 수집 대상 JSON을 검증해 `BokSeriesConfig`로 변환한다. |
| `ingest_dart_history()` | OpenDART corp code를 가져와 DB의 `core.symbol_master`와 매핑하고, 보고서 기간별 재무제표를 `feature.dart_financial_quarterly`에 적재한다. |
| `resolve_dart_universe()` | DART `stock_code`와 DB `symbol_id`를 연결해 적재 가능한 종목 universe를 만든다. |
| `resolve_dart_report_periods()` | `period-end` 또는 `filing-window` 모드로 DART 보고서 연도/코드를 결정한다. |
| `insert_rows()` | 스캔된 컬럼만 대상으로 INSERT를 생성하고 `ON CONFLICT DO NOTHING`을 적용한다. |
| `convert_value_for_column()` | PostgreSQL 타입에 맞춰 `date`, `timestamptz`, `numeric`, `uuid`, `jsonb` 값을 변환한다. |

### 필수 환경변수

| 구분 | 변수 |
|---|---|
| DART | `FSS_API_KEY`, `FSS_API_KEY_2`, `FSS_API_KEY_3` 권장. 기존 `.env` 호환을 위해 `DART_API_KEY`, `OPENDART_API_KEY`도 인식한다. |
| BOK | `BOK_API_KEY`, `BOK_SERIES_JSON` 또는 `BOK_DAILY_SERIES_JSON` |
| WICS | `WICS_COMPANY_INFO_URL`, 선택: `WICS_REQUEST_WORKERS` |
| DB | 권장: `QUANT_DB_DSN` 또는 `DATABASE_URL`; 또는 `QUANT_DB_HOST`, `QUANT_DB_PORT`, `QUANT_DB_NAME`, `QUANT_DB_USER`, `QUANT_DB_PASSWORD` |
| 선택 | `DART_SYMBOLS`, `DART_MAX_COMPANIES`, `DART_REFRESH_CORP_CODES`, `DART_REQUEST_SLEEP_SECONDS`, `BOK_REQUEST_SLEEP_SECONDS` |

공용 DB를 서버에 넣을 때는 `QUANT_DB_DSN`/`DATABASE_URL`를 Airflow worker 또는 실행 셸 환경변수로 주입하는 것을 권장한다. host/user/password 방식도 가능하지만, 배포 표준은 DSN 1개가 가장 단순하다. `QUANT_DB_EXECUTION_MODE=psycopg`를 함께 두면 KIS 수정주가/TA/품질 단계도 같은 공용 DB로 바로 쓴다.

### 실행 예시

```powershell
# 1달 테스트
.\.venv\Scripts\python.exe scripts\ingest_dart_bok_history.py `
  --scope test-1m `
  --sources both `
  --output .omx\logs\dart-bok-1m-test.json

# 2016~2026 백필. BOK 금리/환율 기본 묶음은 --bok-series-preset rate-fx 사용
.\.venv\Scripts\python.exe scripts\ingest_dart_bok_history.py `
  --scope full-10y `
  --sources both `
  --bok-series-preset rate-fx `
  --output .omx\logs\dart-bok-full-10y.json

# BOK 월별 유가 3개 series(WTI/Dubai/Brent) 백필 예시
.\.venv\Scripts\python.exe scripts\ingest_dart_bok_history.py `
  --scope custom `
  --sources bok `
  --start-date 2016-06-01 `
  --end-date 2026-06-24 `
  --bok-series-json '[{"stat_code":"902Y003","cycle":"M","item_code1":"010101","language":"en"},{"stat_code":"902Y003","cycle":"M","item_code1":"010102","language":"en"},{"stat_code":"902Y003","cycle":"M","item_code1":"010103","language":"en"}]' `
  --output .omx\logs\bok-oil-monthly-full-10y-20260624.json
```

### 현재 BOK 적재 상태

| 항목 | 값 |
|---|---:|
| raw 원본 payload | `raw.bok_response` 147건 |
| feature 적재 row | `feature.bok_macro_daily` 30,825건 |
| mart 조회 row | `mart.bok_macro_asof` 30,825건 |
| series 수 | 15개 |
| 전체 기간 | `2016-01-01 ~ 2026-05-28` |
| KOFR 기간 | `2021-11-25 ~ 2026-05-26` |
| 월별 유가 기간 | `2016-06-01 ~ 2026-05-01`, 3개 series × 120개월 = 360건 |

`rate-fx` preset은 기준금리, 콜금리, KOFR, CD(91일), 국고채 1/3/10년, 회사채 AA-/BBB-, 원/달러, 원/100엔, 원/위안 series를 포함한다. KOFR은 BOK 원천 제공 시작일이 늦어 2016년부터 값이 존재하지 않는 것이 정상이다.

### BOK 월별 유가 적재 기준

| 유가 항목 | ECOS 통계코드 | item_code1 | 주기 | 단위 | 저장 series_id |
|---|---|---:|---|---|---|
| WTI 원유 | `902Y003` | `010101` | `M` | `$/bbl` | `902Y003:010101` |
| Dubai Fateh 원유 | `902Y003` | `010102` | `M` | `$/bbl` | `902Y003:010102` |
| Brent 원유 | `902Y003` | `010103` | `M` | `$/bbl` | `902Y003:010103` |

월별 유가는 `feature.bok_macro_daily`에 기존 BOK macro와 동일하게 저장한다. 2026-06-24 기준 WTI/Dubai Fateh/Brent 3개 series는 `2016-06-01 ~ 2026-05-01` 구간 360건이 공용 DB와 로컬 동기화 DB에 적재되어 있다. `normalize_bok_observations()`는 `TIME=YYYYMM` 값을 해당 월 1일 `effective_date`로 변환하므로, 일봉 백테스트에서 사용할 때는 `effective_date`를 그대로 월초 공개값으로 취급하지 않는다. 현재 정규화 기본값은 `published_at`을 실제 ECOS 발표일이 아니라 수집 시각으로 넣고 `mart.bok_macro_asof.available_from = COALESCE(published_at::date, effective_date)`로 계산하므로, 과거 백필 자료를 백테스트에 붙일 때는 view 값을 그대로 신뢰하기보다 조인 SQL에서 `effective_date + INTERVAL '1 month'` 같은 보수적 lag를 명시한다.

### 현재 DART 적재 상태

| 항목 | 값 |
|---|---:|
| raw 원본 payload | `raw.dart_response` 81,021건 |
| corp-code 매핑 | `feature.dart_corp_symbol_map` 3,967건 |
| feature 적재 row | `feature.dart_financial_quarterly` 73,342건 |
| mart 조회 row | `mart.dart_financial_asof` 73,342건 |
| 연결 symbol 수 | 2,506개 |
| period_end 범위 | `2016-03-31 ~ 2026-03-31` |

DART 수집은 연도 단위로 나눠 재개했고, `feature.dart_financial_quarterly` 기본키 `(symbol_id, period_end, report_code, fs_div)` 기준 `ON CONFLICT DO NOTHING`으로 재실행 중복을 방지한다. 현재 스크립트는 `--dart-skip-existing`를 켜면 `feature.dart_financial_quarterly`에 이미 존재하는 `(symbol_id, period_end, report_code, fs_div)` 조합을 API 호출 전에 건너뛴다. 또한 `FSS_API_KEY` 계열 키를 순환 사용하고, 사용한도 응답을 반환한 키는 같은 실행에서 비활성화해 나머지 키로 계속 진행한다. 완료 후 검증에서 중복 PK 그룹, 빈 `accounts_jsonb`, feature/mart row delta, corp-map 미연결 row가 모두 0건이었다. 검증 산출물은 `.omx/logs/dart-validation-20260604-095618.md`와 `.omx/logs/dart-validation-20260604-095618.json`에 저장했다.

## 2. `DE/airflow/dags/quant_agent_data_engineering.py`

### DAG 설정

| 항목 | 값/동작 |
|---|---|
| DAG ID | `quant_agent_daily_data_engineering` |
| 기본 스케줄 | `0 10 * * *` (다음 영업일 오전 10시 실행, 직전 영업일 기준 적재) |
| 재시도 | `QUANT_AIRFLOW_RETRIES` 기본값 `3` |
| retry delay | 5분 |
| `.env` 매핑 | `QUANT_AIRFLOW_LOAD_DOTENV=true` 기본. `QUANT_AIRFLOW_DOTENV_PATH`로 경로 재정의 가능. |
| Python 실행 파일 | `QUANT_AIRFLOW_PYTHON` 또는 현재 인터프리터 |

### 일일 태스크

| 태스크 | 호출 대상 | 설명 |
|---|---|---|
| `ingest_ohlcv_daily` | `OhlcvIngestionService` | KRX 등 원천 OHLCV 일일 적재 |
| `refresh_symbol_metadata_daily` | `scripts/refresh_symbol_metadata.py` | 종목 메타데이터 갱신 |
| `ingest_wics_sector_snapshot` | `scripts/ingest_wics_sectors.py` | FnGuide Company Guide WICS 섹터 스냅샷 1회 적재 |
| `ingest_kis_adjusted_ohlcv_daily` | `scripts/ingest_kis_adjusted_ohlcv.py` | KIS 수정주가 적재 |
| `compute_ta_indicators_daily` | `scripts/compute_technical_indicators_pipeline.py` | TA 지표 계산 |
| `run_data_quality_checks_daily` | `scripts/run_data_quality_checks.py` | 품질 검사 |
| `ingest_bok_daily` | `scripts/ingest_dart_bok_history.py --sources bok` | BOK 일일 macro 수집 |
| `ingest_dart_financials_daily` | `scripts/ingest_dart_bok_history.py --sources dart` | OpenDART 재무제표 수집 및 corp-code 선택 갱신 |

### 의존성

```text
ingest_ohlcv_daily
  ├─ refresh_symbol_metadata_daily ─┬─ run_data_quality_checks_daily
  │                                  └─ ingest_dart_financials_daily
  ├─ ingest_kis_adjusted_ohlcv_daily → compute_ta_indicators_daily → run_data_quality_checks_daily
  ├─ ingest_bok_daily
```

## 3. 운영자가 팀에 설명할 핵심 포인트

| 주제 | 설명 |
|---|---|
| 왜 스키마 스캔을 먼저 하나 | 로컬/서버 DB 스키마 drift가 있으면 잘못된 컬럼에 넣지 않기 위해 실제 DB 컬럼과 제약을 먼저 확인한다. |
| 왜 `DO NOTHING`인가 | 백필/재시도/일일 DAG 재실행에서 동일 PK/UNIQUE 데이터가 들어와도 기존 데이터를 덮어쓰지 않는다. |
| DART 1달 테스트의 의미 | 재무제표는 일봉이 아니므로 `test-1m`/`daily`는 `filing-window` 모드로 최근 공시 예상 윈도우에 해당하는 보고서 코드를 가져온다. |
| BOK 수집 대상 | Airflow 기본값은 `rate-fx` 12개 금리/환율 series에 월별 유가(WTI/Dubai/Brent) 3개 series를 더한 구성이다. `BOK_SERIES_JSON` 또는 `BOK_DAILY_SERIES_JSON`이 있으면 해당 값으로 오버라이드한다. |
| DART 완료 후 남은 운영 작업 | 2016~2026 CFS 재무제표 백필은 완료. 이후에는 신규 분기/사업보고서 증분 수집, 초반 timeout/network 실패 run의 상태 분리, 서버 DB 이관 후 동일 검증 자동화가 남는다. |
| 서버 이전 시 필요한 것 | 서버의 Airflow 환경 또는 Secret Backend에 `FSS_API_KEY`, `FSS_API_KEY_2`, `FSS_API_KEY_3`, `BOK_API_KEY`, `QUANT_DB_DSN`(권장) 또는 host/user/password, BOK series JSON을 주입한다. 공용 DB 적재까지 자동화하려면 `QUANT_DB_EXECUTION_MODE=psycopg`를 함께 두는 편이 명시적이다. |
| 실패 시 확인 순서 | DB 자격증명 → 대상 테이블 스키마 → BOK series JSON → DART/BOK API 키 → API rate limit/응답 status 순서로 확인한다. |
