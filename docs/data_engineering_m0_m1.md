# Data Engineering M0 → M1 실행 가이드

## 범위

| 단계 | 목표 |
|---|---|
| M0 | 데이터 패키지, 설정 계층, PostgreSQL/TimescaleDB SQL 마이그레이션 |
| M1 | KRX/KIS OHLCV source pilot 실행 코드 |
| M2 | KRX primary OHLCV raw/core/mart 적재 |
| M3 | TA-Lib 5개 카테고리 선계산 |
| M4 | SEIBro/BOK/OpenDART 수집 골격과 as-of 저장 |
| M5 | Airflow DAG 운영 골격 |

## 보안/설정 원칙

- `.env` 파일을 읽지 않는다.
- API 키는 프로세스 환경변수, Airflow Connection, Secret Backend에서 주입한다.
- URL, batch size, retry, threshold는 `quant_agent.data.config`의 설정 키로만 관리한다.

## 주요 파일

| 파일 | 역할 |
|---|---|
| `migrations/001_data_engineering_m0.sql` | M0 DB 스키마 |
| `quant_agent/data/config.py` | 환경 기반 설정 |
| `quant_agent/data/sources/krx.py` | KRX 일자별 전 종목 OHLCV pilot client |
| `quant_agent/data/sources/kis.py` | KIS 일봉 pilot client |
| `quant_agent/data/pilot.py` | KRX/KIS 평가 및 primary source 추천 |
| `scripts/run_source_pilot.py` | M1 pilot CLI |
| `scripts/ingest_ohlcv.py` | M2 OHLCV backfill/daily CLI |
| `scripts/compute_ta_indicators.py` | M3 TA-Lib 계산 CLI |
| `scripts/ingest_external_data.py` | M4 BOK/OpenDART/SEIBro CLI |
| `airflow/dags/quant_agent_data_engineering.py` | M5 Airflow DAG |

## DB 마이그레이션

TimescaleDB가 설치된 PostgreSQL에서 실행한다.

```powershell
psql "$env:DATABASE_URL" -f migrations/001_data_engineering_m0.sql
psql "$env:DATABASE_URL" -f migrations/002_data_engineering_runtime.sql
```

검증 포인트:

1. `meta`, `raw`, `core`, `feature`, `mart` schema 생성.
2. `core.ohlcv_daily`와 TA category tables가 hypertable로 변환.
3. `mart.full_universe_asof`, `mart.seibro_universe_asof`, `mart.data_coverage_report` view 생성.
4. `mart.symbol_feature_frame_asof`, `mart.bok_macro_asof`, `mart.dart_financial_asof` view 생성.

## Source pilot 실행

### KRX

```powershell
$env:KRX_API_KEY = "<secret>"
python scripts/run_source_pilot.py --source krx --krx-trade-date 2026-05-15 --output .omx/artifacts/source-pilot-krx.json
```

기본 KRX endpoint는 KOSPI `sto/stk_bydd_trd`와 KOSDAQ `sto/ksq_bydd_trd`를 모두 호출한다. 권한이 일부 endpoint에만 있으면 pilot이 실패하거나 breadth 기준을 통과하지 못해야 한다.

### KIS

```powershell
$env:KIS_APP_KEY = "<secret>"
$env:KIS_APP_SECRET = "<secret>"
$env:KIS_TRADING_ENV = "virtual"
python scripts/run_source_pilot.py --source kis --symbol 005930 --start-date 2026-04-15 --end-date 2026-05-15 --output .omx/artifacts/source-pilot-kis.json
```

### 둘 다 비교

```powershell
python scripts/run_source_pilot.py --source both --symbol 005930 --krx-trade-date 2026-05-15 --start-date 2026-04-15 --end-date 2026-05-15
```

## Primary Source 결정 기준

| 후보 | 합격 조건 |
|---|---|
| KRX | 전 종목 시장 breadth, OHLCV 정상화, 중복 없음, 가격/순서 검증 통과 |
| KIS | 대표 종목 일봉 조회, OHLCV 정상화, 중복 없음, 가격/순서 검증 통과 |

운영 결정은 `.omx/plans/prd-data-engineering-quant-agent.md`의 Phase 1 기준에 따라 10년 커버리지, 수정주가, 상폐/신규상장, 호출 제한, 일일 업데이트 가능성을 추가 파일럿한 뒤 확정한다.
