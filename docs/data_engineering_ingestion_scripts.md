# DART/BOK 및 Airflow 데이터 엔지니어링 스크립트 정리

## 결론

| 파일 | 목적 | 실행 주기/방식 |
|---|---|---|
| `scripts/ingest_dart_bok_history.py` | OpenDART 재무제표와 BOK ECOS 매크로 시계열을 기존 PostgreSQL feature 테이블에 스키마 스캔 후 적재 | 수동 1달 테스트, 10년 백필, Airflow 일일 실행 |
| `airflow/dags/quant_agent_data_engineering.py` | OHLCV, KIS 수정주가, TA, DQ, SEIBro, BOK, DART 일일 자동 수집 DAG | 기본 cron `0 4 * * *` |
| `scripts/ingest_ohlcv.py` | KRX 등 원천 OHLCV 적재 | DAG `ingest_ohlcv_daily` |
| `scripts/ingest_kis_adjusted_ohlcv.py` | KIS 공식 수정주가 OHLCV 적재 | DAG `ingest_kis_adjusted_ohlcv_daily` |
| `scripts/compute_technical_indicators_pipeline.py` | 수정주가 기반 TA 지표 계산 | DAG `compute_ta_indicators_daily` |
| `scripts/refresh_symbol_metadata.py` | 종목 메타데이터/분류 갱신 | DAG `refresh_symbol_metadata_daily` |
| `scripts/run_data_quality_checks.py` | 데이터 품질 검사 실행 | DAG `run_data_quality_checks_daily` |
| `scripts/backfill_seibro_analyst_reports.py` | SEIBro 애널리스트 리포트 백필 | 별도 백필/운영 작업 |

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
| DART | `DART_API_KEY` 권장. 기존 `.env` 호환을 위해 `OPENDART_API_KEY`, `FSS_API_KEY`도 인식한다. |
| BOK | `BOK_API_KEY`, `BOK_SERIES_JSON` 또는 `BOK_DAILY_SERIES_JSON` |
| DB | 권장: `QUANT_DB_DSN`; 또는 `QUANT_DB_HOST`, `QUANT_DB_PORT`, `QUANT_DB_NAME`, `QUANT_DB_USER`, `QUANT_DB_PASSWORD` |
| 선택 | `DART_SYMBOLS`, `DART_MAX_COMPANIES`, `DART_REFRESH_CORP_CODES`, `DART_REQUEST_SLEEP_SECONDS`, `BOK_REQUEST_SLEEP_SECONDS` |

### 실행 예시

```powershell
# 1달 테스트
.\.venv\Scripts\python.exe scripts\ingest_dart_bok_history.py `
  --scope test-1m `
  --sources both `
  --output .omx\logs\dart-bok-1m-test.json

# 2016~2026 백필
.\.venv\Scripts\python.exe scripts\ingest_dart_bok_history.py `
  --scope full-10y `
  --sources both `
  --output .omx\logs\dart-bok-full-10y.json
```

## 2. `airflow/dags/quant_agent_data_engineering.py`

### DAG 설정

| 항목 | 값/동작 |
|---|---|
| DAG ID | `quant_agent_daily_data_engineering` |
| 기본 스케줄 | `0 4 * * *` |
| 재시도 | `QUANT_AIRFLOW_RETRIES` 기본값 `3` |
| retry delay | 5분 |
| `.env` 매핑 | `QUANT_AIRFLOW_LOAD_DOTENV=true` 기본. `QUANT_AIRFLOW_DOTENV_PATH`로 경로 재정의 가능. |
| Python 실행 파일 | `QUANT_AIRFLOW_PYTHON` 또는 현재 인터프리터 |

### 일일 태스크

| 태스크 | 호출 대상 | 설명 |
|---|---|---|
| `ingest_ohlcv_daily` | `OhlcvIngestionService` | KRX 등 원천 OHLCV 일일 적재 |
| `refresh_symbol_metadata_daily` | `scripts/refresh_symbol_metadata.py` | 종목 메타데이터 갱신 |
| `ingest_kis_adjusted_ohlcv_daily` | `scripts/ingest_kis_adjusted_ohlcv.py` | KIS 수정주가 적재 |
| `compute_ta_indicators_daily` | `scripts/compute_technical_indicators_pipeline.py` | TA 지표 계산 |
| `run_data_quality_checks_daily` | `scripts/run_data_quality_checks.py` | 품질 검사 |
| `ingest_bok_daily` | `scripts/ingest_dart_bok_history.py --sources bok` | BOK 일일 macro 수집 |
| `ingest_dart_financials_daily` | `scripts/ingest_dart_bok_history.py --sources dart` | OpenDART 재무제표 수집 및 corp-code 선택 갱신 |
| `ingest_seibro_reports_daily` | `ExternalDataIngestionService.ingest_seibro_reports()` | SEIBro 리포트 기반 보조 feature 수집 |

### 의존성

```text
ingest_ohlcv_daily
  ├─ refresh_symbol_metadata_daily ─┬─ run_data_quality_checks_daily
  │                                  └─ ingest_dart_financials_daily
  ├─ ingest_kis_adjusted_ohlcv_daily → compute_ta_indicators_daily → run_data_quality_checks_daily
  ├─ ingest_bok_daily
  └─ ingest_seibro_reports_daily
```

## 3. 운영자가 팀에 설명할 핵심 포인트

| 주제 | 설명 |
|---|---|
| 왜 스키마 스캔을 먼저 하나 | 로컬/서버 DB 스키마 drift가 있으면 잘못된 컬럼에 넣지 않기 위해 실제 DB 컬럼과 제약을 먼저 확인한다. |
| 왜 `DO NOTHING`인가 | 백필/재시도/일일 DAG 재실행에서 동일 PK/UNIQUE 데이터가 들어와도 기존 데이터를 덮어쓰지 않는다. |
| DART 1달 테스트의 의미 | 재무제표는 일봉이 아니므로 `test-1m`/`daily`는 `filing-window` 모드로 최근 공시 예상 윈도우에 해당하는 보고서 코드를 가져온다. |
| BOK 수집 대상 | BOK는 통계코드/항목코드가 전략마다 달라 `BOK_SERIES_JSON`으로 명시한다. |
| 서버 이전 시 필요한 것 | 서버의 Airflow 환경에 `.env` 또는 Secret Backend로 `DART_API_KEY`, `BOK_API_KEY`, DB DSN/비밀번호, BOK series JSON을 주입한다. |
| 실패 시 확인 순서 | DB 자격증명 → 대상 테이블 스키마 → BOK series JSON → DART/BOK API 키 → API rate limit/응답 status 순서로 확인한다. |
