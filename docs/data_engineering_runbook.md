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
| SEIBro analyst report summary backfill | `python scripts/backfill_seibro_analyst_reports.py --start-date 2016-05-20 --end-date 2026-05-20 --chunk-months 1 --db-mode docker` |
| KIS official adjusted full + TA | `python scripts/run_kis_adjusted_full_pipeline.py --run-mode full --start-date 2016-05-20 --end-date 2026-05-20 --resume` |
| KIS official adjusted daily incremental + TA | `python scripts/run_kis_adjusted_full_pipeline.py --run-mode daily-incremental --target-date 2026-05-21 --resume` |

## 환경변수

| 영역 | 키 |
|---|---|
| DB | `QUANT_DB_DSN` 또는 `QUANT_DB_HOST`, `QUANT_DB_PORT`, `QUANT_DB_NAME`, `QUANT_DB_USER`, `QUANT_DB_PASSWORD` |
| 로컬 Docker DB | `QUANT_DB_EXECUTION_MODE=docker`, `QUANT_DB_CONTAINER=quant-agent-db` |
| KRX | `KRX_API_KEY`, 선택: `KRX_DAILY_MARKET_ENDPOINTS` |
| KIS | `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_TRADING_ENV` |
| BOK | `BOK_API_KEY`, 선택: `BOK_BASE_URL` |
| OpenDART | `DART_API_KEY` 또는 `OPENDART_API_KEY` |
| SEIBro | `SEIBRO_COLLECTION_APPROVED=true`, `SEIBRO_REPORT_ENDPOINT`, 선택: `SEIBRO_API_KEY`; 분석리포트 WebSquare 수집 선택: `SEIBRO_WEB_BASE_URL`, `SEIBRO_ANALYST_REPORT_*`, `SEIBRO_REQUEST_SLEEP_*` |
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

## KIS official adjusted OHLCV + TA 운영

`scripts/run_kis_adjusted_full_pipeline.py`는 `.env` 파일을 로드하지 않고, 이미 프로세스 환경에 주입된 KIS/DB 자격증명만 사용한다. 운영자는 장기 backfill과 일일 증분을 같은 wrapper로 실행한다.

| 실행 유형 | 권장 명령 | 산출물 |
|---|---|---|
| 장기 full/backfill | `python scripts/run_kis_adjusted_full_pipeline.py --run-mode full --start-date 2016-05-20 --end-date <YYYY-MM-DD> --resume` | `.omx/artifacts/kis-adjusted-full.json`, `.omx/artifacts/technical-indicators-kis-adjusted-full.json` |
| 일일 증분 | `python scripts/run_kis_adjusted_full_pipeline.py --run-mode daily-incremental --target-date <YYYY-MM-DD> --resume` | `.omx/artifacts/kis-adjusted-daily-<YYYY-MM-DD>.json`, `.omx/artifacts/technical-indicators-kis-adjusted-daily-<YYYY-MM-DD>.json` |

Resume 규칙은 JSON summary 기준이다. `--resume` 사용 시 요청 기간(`start_date`, `end_date`)이 일치하고 실패 목록(`failed_windows`, `failed_tickers`)이 비어 있는 단계만 건너뛴다. 예를 들어 KIS 적재 summary가 성공이고 TA summary가 없으면 KIS는 스킵하고 TA부터 재개한다. 실패 window/ticker가 남아 있거나 기간이 다르면 해당 단계는 다시 실행한다.

wrapper 내부 검증은 KIS 적재 후 `failed_windows`가 비어 있을 때만 TA recomputation으로 진행한다. KIS 실패가 남으면 TA 이전에 중단하고 `stopped_before_ta` summary를 출력한다.

## Airflow

`airflow/dags/quant_agent_data_engineering.py`는 다음 DAG를 제공한다.

| DAG | 역할 |
|---|---|
| `quant_agent_daily_data_engineering` | 일일 OHLCV, TA-Lib, BOK, DART corp code, SEIBro report refresh |
| `quant_agent_backfill_ohlcv_10y` | 설정된 primary source 기준 10년 OHLCV backfill |

Airflow task는 credentials를 코드/파일에서 읽지 않고 런타임 환경, Airflow Connection, Secret Backend에 의존한다.
