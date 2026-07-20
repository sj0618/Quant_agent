# Quant-Agent 데이터 엔지니어링 파이프라인 구축 기록

LLM 기반 퀀트 전략을 **실제 데이터로 검증하고 서비스에서 조회할 수 있도록** 만든 데이터 엔지니어링 파이프라인입니다.
현재 저장소의 데이터 레이어는 KRX/KIS/SEIBro/BOK/DART 원천 데이터를 수집하고, TimescaleDB에 정규화한 뒤, TA 지표와 Mart/View까지 이어지는 흐름을 제공합니다.

---

## 1. Data Sources & Universe

### 핵심 데이터 출처

| 출처 | 수집 범위/역할 | 원본 Landing | 정규화/활용 테이블 | 주요 활용 |
|---|---|---|---|---|
| **KRX** | 국내 상장 종목의 10년치 OHLCV 원주가(최신 검증일 2026-07-03), 종목/시장 메타데이터 | `raw.ohlcv_response` | `core.ohlcv_daily`, `core.symbol_master`, `core.trading_calendar` | 기본 가격 이력, 거래일 캘린더, 원천 정합성 비교 |
| **KIS Open API** | 공식 수정주가 기준 일봉 OHLCV(최신 검증일 2026-07-06), 재개 가능한 증분 수집 | `meta.api_request_log`에 요청 단위 로그 적재 | `feature.adjusted_ohlcv_daily` | 백테스트 기준 가격, TA 지표 입력 |
| **TA-Lib** | 수정 OHLCV 기반 기술적 지표 계산. 정의 카탈로그 158개, mart 기본 선계산 key 45개 | - | `feature.ta_*_ticker_daily`, `mart.kis_adjusted_feature_frame_asof` | 팩터 생성, 백테스트 feature frame |
| **SEIBro** | 분석리포트 요약 데이터 백필/증분 수집 | `raw.analyst_report_summary` | `feature.seibro_report_summary`, `feature.seibro_sentiment`, `mart.seibro_universe_asof` | 리포트 기반 보조 시그널, 종목 관심도 |
| **BOK / DART** | BOK 금리/환율 12개 series와 월별 유가 3개 series(WTI/Dubai/Brent) 10년치 적재 완료. DART CFS 재무 데이터 2016~2026 period_end 구간 적재 완료 | `raw.bok_response`, `raw.dart_response` | `feature.bok_macro_daily`, `feature.dart_financial_quarterly` | macro/fundamental factor 결합 |

### 기본 퀀트 유니버스

전략 유니버스는 **코스피/코스닥 보통주** 중심으로 제한합니다. ETF, ETN, 우선주, SPAC, 리츠 등은 기본 백테스트 유니버스에서 제외합니다.

```sql
SELECT *
FROM meta.view_common_stock_universe
WHERE market_segment IN ('KOSPI', 'KOSDAQ')
  AND security_type = '보통주'
  AND listing_status = 'listed';
```

로컬 검증 기준으로 `core.symbol_master`의 `security_type`은 NULL 없이 분류되었고, `meta.view_common_stock_universe`는 백테스트용 기본 종목 후보를 제공합니다.

---

## 2. Database Schema & Key Tables

데이터는 `raw → core → feature → mart` 계층으로 흐르고, 실행/품질/관측성 메타데이터는 `meta`에 쌓입니다.

```text
KRX / KIS / SEIBro / BOK / DART
        │
        ▼
raw.*        원본 응답/비정형 landing
        │
        ▼
core.*       종목·거래일·원주가 canonical 데이터
        │
        ▼
feature.*    수정주가, TA, 리포트, 매크로/재무 feature
        │
        ▼
mart.*       백엔드/프론트/백테스트가 바로 읽는 조회용 view

meta.*       run, cursor, API request, QA issue, lineage 기록
```

### `raw` schema — 원본 보존 계층

| 테이블 | 데이터 내용 | 주요 활용처 |
|---|---|---|
| `raw.ohlcv_response` | KRX 등 OHLCV 원본 응답 payload | 원천 재처리, 장애 분석, 수집 감사 |
| `raw.analyst_report_summary` | SEIBro 분석리포트 요약 원본성 데이터. `(report_date, ticker, institution, author)` 기준 중복 방지 | 리포트 원문 확인, feature 재생성 |
| `raw.seibro_report_response` | SEIBro 일반 리포트/외부 응답 payload | SEIBro 수집 디버깅, 재파싱 |
| `raw.bok_response` | BOK API 원본 응답 | 매크로 데이터 재정규화 |
| `raw.dart_response` | DART API 원본 응답 | 재무/공시 데이터 재정규화 |

### `core` schema — 정규화된 기준 데이터

| 테이블 | 데이터 내용 | 주요 활용처 |
|---|---|---|
| `core.symbol_master` | 종목 마스터. ticker, 종목명, 시장 구분, 상장 상태, `security_type` 포함 | 유니버스 필터, 종목명/시장 조회 |
| `core.symbol_listing_history` | 상장, 상폐, 재상장 등 종목 lifecycle 이벤트 | 과거 백테스트 survivorship bias 완화 |
| `core.symbol_name_history` | 종목명 변경 이력 | 과거 리포트/가격 데이터 매칭 |
| `core.trading_calendar` | 거래일 캘린더 | 누락일 QA, 증분 수집 범위 산정 |
| `core.ohlcv_daily` | 10년치 OHLCV 원주가(최신 검증일 2026-07-03) | KRX 기준 가격 조회, KIS 수정주가 정합성 비교 |
| `core.ohlcv_quality_daily` | 일별 OHLCV 품질 요약 | 커버리지 모니터링, QA 리포트 |

### `feature` schema — 분석/모델 입력 feature

| 테이블 | 데이터 내용 | 주요 활용처 |
|---|---|---|
| `feature.adjusted_ohlcv_daily` | KIS 공식 수정주가 기반 canonical OHLCV | 백테스트 기준 가격, TA 입력 |
| `feature.ta_trend_ticker_daily` | 이동평균, MACD 등 trend 계열 지표. 현재 선계산 key 16개 | 전략 feature, 종목 스크리닝 |
| `feature.ta_momentum_ticker_daily` | RSI 등 momentum 계열 지표. 현재 선계산 key 8개 | 모멘텀/역추세 전략 |
| `feature.ta_volatility_ticker_daily` | ATR, 변동성 등 volatility 지표. 현재 선계산 key 7개 | 리스크 관리, 포지션 사이징 |
| `feature.ta_volume_ticker_daily` | 거래량 기반 지표. 현재 선계산 key 4개 | 수급/유동성 필터 |
| `feature.ta_pattern_ticker_daily` | 캔들 패턴 지표. 현재 선계산 key 10개 | 패턴 기반 보조 시그널 |
| `feature.ta_indicator_definition` | 계산 가능한 TA 지표 정의/카탈로그 158개 | 프론트 지표 목록, 계산 메타데이터 |
| `feature.seibro_report_summary` | SEIBro 리포트 요약을 feature 계층으로 정규화한 데이터 | 리포트 이벤트 feature |
| `feature.seibro_sentiment` | 리포트 텍스트/투자의견 기반 sentiment 확장 영역 | 텍스트 기반 시그널 |
| `feature.seibro_universe_daily` | SEIBro 리포트 기반 일별 관심 종목 universe | 리포트 커버리지 필터 |
| `feature.bok_macro_daily` | BOK `rate-fx` 12개 series와 월별 유가 3개 series를 포함한 macro feature 30,825건. 유가 series는 `902Y003:010101`(WTI), `902Y003:010102`(Dubai Fateh), `902Y003:010103`(Brent) 월평균값 | 시장 regime/거시 변수 결합 |
| `feature.dart_financial_quarterly` | 분기 재무 feature. 73,342건, `2016-03-31 ~ 2026-03-31` period_end 구간 적재 완료 | fundamental factor |
| `feature.dart_corp_symbol_map` | DART corp_code와 ticker 매핑 | DART 재무 데이터 종목 연결 |

TA 지표는 `feature.ta_indicator_definition`의 **계산 가능 카탈로그 158개**와 `feature.ta_*_ticker_daily.values_jsonb`의 **현재 백테스트 기본 선계산 key 45개**를 구분합니다. 45개 key 구성은 Trend 16, Momentum 8, Volatility 7, Volume 4, Pattern 10입니다. 정의 1개가 여러 output key를 만들 수 있으므로 정의 수와 저장 key 수는 1:1이 아닙니다.

### `mart` schema — 서비스/백테스트 조회용 view

| View | 데이터 내용 | 주요 활용처 |
|---|---|---|
| `mart.kis_adjusted_feature_frame_asof` | KIS 수정 OHLCV + ticker 기반 TA 지표 통합 view | **백테스트/팩터 엔진 1순위 조회 대상** |
| `mart.symbol_feature_frame_asof` | 종목 메타 + 수정 OHLCV + 주요 feature frame | 백엔드 API, 종목 상세 화면 |
| `mart.full_universe_asof` | listed/coverage 조건을 반영한 전체 tradable universe | 기본 universe 조회 |
| `mart.seibro_universe_asof` | SEIBro 리포트 기반 universe view | 리포트 기반 탐색/랭킹 |
| `mart.data_coverage_report` | 종목별 데이터 커버리지/최근 일자 요약 | 운영 대시보드, 누락 점검 |
| `mart.bok_macro_asof` | BOK macro as-of view. 15개 series 30,825건. 월별 유가 사용 시 실제 발표일이 아닌 수집 시각이 `published_at`에 들어가므로 보수적 lag 기준 as-of join 필요 | 거시 지표 조회 |
| `mart.dart_financial_asof` | DART financial as-of view. 73,342건, `2016-03-31 ~ 2026-03-31` | 재무 지표 조회 |

### `meta` schema — 실행·품질·관측성 메타데이터

| 테이블/View | 데이터 내용 | 주요 활용처 |
|---|---|---|
| `meta.data_source` | 데이터 출처와 source key 관리 | 출처별 run 추적 |
| `meta.ingestion_run` | 수집/계산 작업 단위 run 이력 | Airflow/CLI 실행 결과 추적 |
| `meta.ingestion_cursor` | 증분 수집 resume cursor | 중단 복구, incremental update |
| `meta.api_request_log` | KIS 등 외부 API 요청 단위 성공/실패, HTTP 코드, retry, latency | API 관측성, rate limit/장애 분석 |
| `meta.data_quality_issue` | 누락일, stale price, volume anomaly, 정합성 오류 등 품질 이슈 | QA 대시보드, 배치 실패 원인 |
| `meta.lineage_event` | source → target 변환 의존성, run id, metadata | 데이터 lineage, 재처리 범위 산정 |
| `meta.view_common_stock_universe` | KOSPI/KOSDAQ 현재 상장 보통주만 노출하는 helper view | 현재 상장 보통주 조회. 상폐 포함 백테스트는 as-of mart view 사용 |

### 자주 쓰는 조회 대상

| 보고 싶은 데이터 | 조회 대상 |
|---|---|
| 10년치 OHLCV 원주가(최신 검증일 2026-07-03) | `core.ohlcv_daily` |
| KIS 공식 수정주가 | `feature.adjusted_ohlcv_daily` |
| 기술적 지표 기본 선계산 값 45개 | `feature.ta_trend_ticker_daily`, `feature.ta_momentum_ticker_daily`, `feature.ta_volatility_ticker_daily`, `feature.ta_volume_ticker_daily`, `feature.ta_pattern_ticker_daily` |
| 수정주가 + TA 통합 feature frame | `mart.kis_adjusted_feature_frame_asof` |
| SEIBro 분석리포트 원본 | `raw.analyst_report_summary` |
| 현재 상장 KOSPI/KOSDAQ 보통주 helper | `meta.view_common_stock_universe` |

---

## 3. Migration Scripts Flow

`migrations/`는 **데이터 자체가 아니라 DB 구조를 만드는 파일**입니다. 새 서버나 로컬 DB를 만들 때는 파일명 순서대로 적용해야 의존성이 맞습니다.

```text
001 기본 스키마/테이블 뼈대
  └─ 002 런타임 mart view와 DART 보조 매핑
      └─ 003 KIS 수정주가 + ticker TA + QA/관측성/lineage 확장
          └─ 004 종목 lifecycle 메타데이터 + mart view 재작성
              └─ 005 SEIBro 분석리포트 raw landing 보장
                  └─ 006 security_type 분류 + 보통주 universe view
```

| 순서 | 파일 | 목적 | 왜 이 순서인가 |
|---:|---|---|---|
| 1 | `001_data_engineering_m0.sql` | TimescaleDB extension, `meta/raw/core/feature/mart` 스키마, 기본 테이블과 초기 mart view 생성 | 모든 후속 migration이 참조하는 최상위 뼈대 |
| 2 | `002_data_engineering_runtime.sql` | DART corp-code 매핑, `mart.symbol_feature_frame_asof`, BOK/DART as-of view, 읽기 role 추가 | 001의 core/feature 테이블이 있어야 view 생성 가능 |
| 3 | `003_quality_observability_lineage.sql` | `feature.adjusted_ohlcv_daily`, ticker 기반 TA 테이블, KIS adjusted mart view, API request log/lineage metadata 확장 | Phase 2의 수정주가·TA·관측성 핵심 구조 |
| 4 | `004_mart_symbol_metadata.sql` | `core.symbol_master`에 시장/상장상태/상장일/상폐일/metadata 보강, mart view를 수정주가+TA 기준으로 재작성 | 003의 adjusted/TA 테이블을 기준으로 최종 조회 view를 다시 묶음 |
| 5 | `005_seibro_analyst_report_summary.sql` | `raw.analyst_report_summary` landing table과 인덱스 보장 | SEIBro 크롤링 결과를 idempotent하게 적재 |
| 6 | `006_symbol_security_type_classification.sql` | 보통주/우선주/SPAC/ETF/ETN/리츠 등 `security_type` 분류 함수와 `meta.view_common_stock_universe` 생성 | 004에서 보강된 시장/상장 메타를 활용해 최종 universe filter 생성 |

> 실무 적용 원칙: 서버 이관 시에는 일부만 고르기보다 **001 → 006을 순서대로 전부 적용**한 뒤 dump/restore 또는 수집 스크립트로 데이터를 채우는 방식을 권장합니다.

---

## 4. Data Quality & Observability

### QA 로직

기본 row count 검증을 넘어, 가격 데이터가 전략에 안전하게 쓰일 수 있는지 아래 항목을 점검합니다.

| QA 항목 | 점검 내용 | 기록 위치 |
|---|---|---|
| Row count / coverage | 종목별 기대 거래일 대비 적재 row 수 확인 | `meta.data_quality_issue`, `core.ohlcv_quality_daily` |
| 누락 거래일 | `core.trading_calendar` 기준으로 종목별 누락일 탐지 | `meta.data_quality_issue` |
| Stale price | 여러 거래일 동안 가격이 비정상적으로 멈춘 구간 감지 | `meta.data_quality_issue` |
| Volume anomaly | 거래량 급증/급감, 0 거래량 지속 등 이상치 탐지 | `meta.data_quality_issue` |
| KIS ↔ KRX 정합성 | KIS 수정주가와 KRX 원주가 간 비정상 괴리/결측 비교 | `meta.data_quality_issue` |

실행 진입점:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_data_quality_checks.py `
  --start-date 2016-05-20 `
  --end-date 2026-07-09 `
  --checks all
```

### KIS API 관측성

KIS 수집은 run summary만 남기지 않고, **요청 1건 단위**로 관측 데이터를 저장합니다.

| 컬럼 예시 | 의미 |
|---|---|
| `source_id` | API 출처 식별자. 예: `KIS` |
| `endpoint_key` | 호출 endpoint/path key |
| `status_code` | HTTP 응답 코드 |
| `success` | 요청 성공 여부 |
| `retry_count` | 재시도 횟수 |
| `elapsed_ms` | 요청 지연 시간 |
| `request_started_at` | 요청 시작 시각 |
| `error_message` | 실패 원인 |
| `metadata_jsonb` | ticker, window, response metadata 등 확장 정보 |

운영 중 API 장애를 볼 때는 아래처럼 확인합니다.

```sql
SELECT request_started_at, endpoint_key, status_code, success, retry_count, elapsed_ms, error_message
FROM meta.api_request_log
WHERE source_id = 'KIS'
ORDER BY request_started_at DESC
LIMIT 50;
```

### Data Lineage

수집/가공 흐름은 `meta.lineage_event`로 남겨 재처리 범위와 의존성을 추적합니다.

```text
KIS adjusted 수집
  → feature.adjusted_ohlcv_daily
  → feature.ta_*_ticker_daily
  → mart.kis_adjusted_feature_frame_asof
  → 백테스트/서비스 조회
```

예시 조회:

```sql
SELECT event_time, run_id, source_object, target_object, transform_name, metadata_jsonb
FROM meta.lineage_event
ORDER BY event_time DESC
LIMIT 50;
```

---

## 5. Getting Started

### 5.1 사전 준비

| 도구 | 용도 |
|---|---|
| Docker Desktop | TimescaleDB 로컬 실행 |
| Python 3.11+ | 수집/QA/TA 스크립트 실행 |
| PowerShell | Windows 기준 migration helper 실행 |

> 보안 원칙: DB 비밀번호와 API key는 저장소에 커밋하지 않습니다. `.env`에 의존하지 말고 현재 shell/CI secret에서 주입합니다.

### 5.2 로컬 TimescaleDB 실행 및 migration 적용

```powershell
# 1) 로컬 세션에만 DB 비밀번호 주입
$env:QUANT_DB_PASSWORD = "<your-local-password>"

# 선택: 기본값을 바꾸고 싶을 때만 지정
$env:QUANT_DB_NAME = "quant_agent"
$env:QUANT_DB_USER = "quant_agent"
$env:QUANT_DB_PORT = "5432"

# 2) DB 시작 + migrations/001~006 순차 적용
.\scripts\apply_migrations.ps1
```

`scripts/apply_migrations.ps1`는 다음을 수행합니다.

1. `docker compose up -d db`
2. PostgreSQL readiness 확인
3. `migrations/*.sql`을 파일명 순서대로 `psql -v ON_ERROR_STOP=1`로 적용

DB 컨테이너 기본값:

| 항목 | 기본값 |
|---|---|
| Compose service | `db` |
| Container | `quant-agent-db` |
| Database | `quant_agent` |
| User | `quant_agent` |
| Port | `127.0.0.1:5432` |

### 5.3 Python 환경 구성

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 5.4 데이터 수집/계산 스크립트

환경 변수로 DB 연결 정보와 외부 API 인증 정보를 주입한 뒤 필요한 스크립트를 실행합니다. 실제 credential은 README나 git에 남기지 않습니다.

| 목적 | 스크립트 |
|---|---|
| KRX/OHLCV 기본 수집 | `scripts/ingest_ohlcv.py` |
| KIS 수정주가 수집 | `scripts/ingest_kis_adjusted_ohlcv.py` |
| KIS 수정주가 + TA wrapper | `scripts/run_kis_adjusted_full_pipeline.py` |
| TA 지표 계산 | `scripts/compute_technical_indicators_pipeline.py` |
| QA 실행 | `scripts/run_data_quality_checks.py` |
| 종목 메타데이터 갱신 | `scripts/refresh_symbol_metadata.py` |
| 종목 `security_type` 분류 | `scripts/classify_symbol_security_types.py` |
| SEIBro 분석리포트 백필 | `scripts/backfill_seibro_analyst_reports.py` |
| BOK 월별 유가 수집 | `scripts/ingest_dart_bok_history.py --scope custom --sources bok --start-date 2016-06-01 --end-date 2026-06-24 --bok-series-json '[{"stat_code":"902Y003","cycle":"M","item_code1":"010101","language":"en"},{"stat_code":"902Y003","cycle":"M","item_code1":"010102","language":"en"},{"stat_code":"902Y003","cycle":"M","item_code1":"010103","language":"en"}]'` |

### 5.5 Airflow DAG

Airflow 환경에서는 `DE/airflow/dags/quant_agent_data_engineering.py`가 일일 파이프라인을 정의합니다.

```text
ingest_ohlcv_daily
  ├─ refresh_symbol_metadata_daily ─┐
  ├─ ingest_kis_adjusted_ohlcv_daily → compute_ta_indicators_daily ─┐
  ├─ ingest_bok_daily                                                  ├─ run_data_quality_checks_daily
  └─ ingest_seibro_reports_daily                                      ┘

ingest_dart_corp_codes_daily  # 독립 실행
```

### 5.6 바로 조회해 보기

PowerShell에서 `psql`이 컨테이너 안에서 실행되므로 로컬에 PostgreSQL client가 없어도 됩니다.

```powershell
# 최근 적재 run 확인
docker compose exec -T db psql -U quant_agent -d quant_agent -c "
SELECT run_id, dag_id, task_id, source_id, status, started_at, ended_at, error_message
FROM meta.ingestion_run
ORDER BY started_at DESC
LIMIT 10;
"

# KOSPI/KOSDAQ 보통주 universe 확인
docker compose exec -T db psql -U quant_agent -d quant_agent -c "
SELECT market_segment, COUNT(*) AS symbols
FROM meta.view_common_stock_universe
GROUP BY market_segment
ORDER BY market_segment;
"

# 삼성전자 예시: 수정주가 + TA feature frame
docker compose exec -T db psql -U quant_agent -d quant_agent -c "
SELECT as_of_date, ticker, close, volume, trend_values, momentum_values, volatility_values
FROM mart.kis_adjusted_feature_frame_asof
WHERE ticker = '005930'
ORDER BY as_of_date DESC
LIMIT 20;
"

# SEIBro 분석리포트 원본 확인
docker compose exec -T db psql -U quant_agent -d quant_agent -c "
SELECT report_date, ticker, company_name, institution, author, opinion, target_price, close_price
FROM raw.analyst_report_summary
ORDER BY report_date DESC
LIMIT 20;
"
```

### 5.7 테스트

문서 변경만 했더라도 파이프라인 회귀 여부를 확인할 때는 pytest를 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

선택적 통합 테스트는 Docker DB와 실제 KIS 호출 환경 변수가 준비된 경우에만 실행되도록 설계되어 있습니다.

---

## 운영 체크리스트

| 체크 | 확인 쿼리/위치 |
|---|---|
| DB schema가 최신인가 | `migrations/001` → `006` 적용 여부 |
| 최근 수집 run이 성공했는가 | `meta.ingestion_run` |
| KIS API 장애/지연이 있는가 | `meta.api_request_log` |
| 품질 이슈가 남아 있는가 | `meta.data_quality_issue` |
| TA 계산이 최신인가 | `mart.kis_adjusted_feature_frame_asof` 최근 `as_of_date` |
| 기본 universe가 의도대로 제한됐는가 | `meta.view_common_stock_universe` |
| 데이터 의존성을 추적할 수 있는가 | `meta.lineage_event` |

---

## 참고 문서

- Migration 상세 설명: `docs/DE.md`
- Local DB setup: `docs/local_db_setup.md`
- Data engineering runbook: `docs/data_engineering_runbook.md`
- Airflow DAG: `DE/airflow/dags/quant_agent_data_engineering.py`
