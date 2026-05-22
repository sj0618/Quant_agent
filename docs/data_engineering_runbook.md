# Data Engineering Runbook

## 결론

데이터 엔지니어링 실행 경로는 `KRX/KIS 파일럿 → KRX primary OHLCV 적재 → TA-Lib 선계산 → BOK/OpenDART/SEIBro 외부 데이터 적재 → mart/as-of 조회 → Airflow 운영` 순서다.

## 주요 명령

| 목적 | 명령 |
|---|---|
| Source pilot | `python scripts/run_source_pilot.py --source both --symbol 005930 --krx-trade-date 2026-05-15 --start-date 2026-05-14 --end-date 2026-05-15` |
| OHLCV daily/backfill | `python scripts/ingest_ohlcv.py --source KRX --start-date 2026-05-15 --end-date 2026-05-15 --db-mode docker` |
| TA-Lib 계산 | `python scripts/compute_ta_indicators.py --start-date 2026-05-14 --end-date 2026-05-15 --symbols 005930 --db-mode docker` |
| BOK series | `python scripts/ingest_external_data.py --job bok-series --stat-code 722Y001 --cycle D --start-period 20260514 --end-period 20260515 --item-code1 0101000 --db-mode docker` |
| OpenDART corp code | `python scripts/ingest_external_data.py --job dart-corp-codes --db-mode docker` |
| OpenDART financial | `python scripts/ingest_external_data.py --job dart-financial --symbol 005930 --corp-code <corp_code> --business-year 2025 --report-code 11011 --db-mode docker` |
| SEIBro reports | `python scripts/ingest_external_data.py --job seibro-reports --seibro-endpoint <approved_endpoint> --as-of-date 2026-05-15 --db-mode docker` |

## 환경변수

| 영역 | 키 |
|---|---|
| DB | `QUANT_DB_DSN` 또는 `QUANT_DB_HOST`, `QUANT_DB_PORT`, `QUANT_DB_NAME`, `QUANT_DB_USER`, `QUANT_DB_PASSWORD` |
| 로컬 Docker DB | `QUANT_DB_EXECUTION_MODE=docker`, `QUANT_DB_CONTAINER=quant-agent-db` |
| KRX | `KRX_API_KEY`, 선택: `KRX_DAILY_MARKET_ENDPOINTS` |
| KIS | `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_TRADING_ENV` |
| BOK | `BOK_API_KEY`, 선택: `BOK_BASE_URL` |
| OpenDART | `DART_API_KEY` 또는 `OPENDART_API_KEY` |
| SEIBro | `SEIBRO_COLLECTION_APPROVED=true`, `SEIBRO_REPORT_ENDPOINT`, 선택: `SEIBRO_API_KEY` |
| Airflow | `BOK_DAILY_SERIES_JSON`, `DART_REFRESH_CORP_CODES`, `SEIBRO_REPORT_PARAMS_JSON`, `QUANT_AIRFLOW_DAILY_SCHEDULE` |

## 적재 계층

| 계층 | 테이블/뷰 |
|---|---|
| Raw | `raw.ohlcv_response`, `raw.bok_response`, `raw.dart_response`, `raw.seibro_report_response` |
| Core | `core.symbol_master`, `core.ohlcv_daily`, `core.ohlcv_quality_daily`, `core.trading_calendar` |
| Feature | `feature.ta_*_daily`, `feature.seibro_*`, `feature.bok_macro_daily`, `feature.dart_*` |
| Mart | `mart.full_universe_asof`, `mart.seibro_universe_asof`, `mart.symbol_feature_frame_asof`, `mart.bok_macro_asof`, `mart.dart_financial_asof` |

## 검증 쿼리

```sql
SELECT count(*) FROM core.ohlcv_daily WHERE trade_date = '2026-05-15';
SELECT category, count(*) FROM feature.ta_indicator_definition GROUP BY category ORDER BY category;
SELECT * FROM mart.symbol_feature_frame_asof WHERE symbol = '005930' ORDER BY as_of_date DESC LIMIT 5;
SELECT * FROM mart.bok_macro_asof ORDER BY effective_date DESC LIMIT 5;
```

## Airflow

`airflow/dags/quant_agent_data_engineering.py`는 다음 DAG를 제공한다.

| DAG | 역할 |
|---|---|
| `quant_agent_daily_data_engineering` | 일일 OHLCV, TA-Lib, BOK, DART corp code, SEIBro report refresh |
| `quant_agent_backfill_ohlcv_10y` | 설정된 primary source 기준 10년 OHLCV backfill |

Airflow task는 credentials를 코드/파일에서 읽지 않고 런타임 환경, Airflow Connection, Secret Backend에 의존한다.
