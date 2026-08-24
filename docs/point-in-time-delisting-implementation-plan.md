# Point-in-time 유니버스·상장폐지 계약 구현 변경 목록

작성일: 2026-08-20
기준 문서: `docs/point-in-time-delisting-data-contract.md`

## 1. 결론

문서의 계약을 적용하려면 DE 수집·DB 스키마·PIT 조회·백테스트 엔진·결과 저장·FE·테스트를 함께 수정해야 한다.

핵심 P0 변경은 다음과 같다.

1. 현재 PIT view를 덮어쓰는 migration 수정
2. OHLCV 누락만으로 상장폐지 처리하는 로직 제거
3. 공식 상장폐지 이벤트·회수가격 수집 추가
4. AI 가격·feature 조회에 날짜별 PIT membership 조인
5. 백테스트의 `20거래일 후 0원 상각`을 fallback으로 변경
6. 상장폐지 품질 metadata를 결과 끝까지 전달·저장
7. 기존 0원 상각 테스트를 새 계약 테스트로 교체

이번 문서는 구현 대상과 수정 범위를 정리한 계획서다. 작성 시점에는 코드를 변경하지 않았다.

## 2. DB 스키마 및 migration

| 우선순위 | 파일 | 변경 내용 |
|---|---|---|
| P0 | `DE/migrations/012_symbol_sector_metadata.sql:59-89` | `common_stock_feature_frame_asof`가 현재 `symbol_master`의 lifecycle이 아니라 PIT history를 사용하도록 변경 |
| P0 | `DE/migrations/012_symbol_sector_metadata.sql:123-140` | `mart.common_stock_universe_asof`가 가격 row와 현재 `symbol_master`를 기준으로 재정의되는 문제 제거 |
| P0 | 신규 `DE/migrations/013_point_in_time_delisting_contract.sql` | lifecycle event 테이블, PIT view, 제약조건, 인덱스 추가 |
| P1 | `DE/migrations/012_symbol_sector_metadata.sql:91-105` | `mart.full_universe_asof`의 PIT 기준을 명확히 하거나 비정식 view로 분리 |
| P1 | `DE/migrations/012_symbol_sector_metadata.sql:142-155` | 현재 목록용 `meta.view_common_stock_universe`와 백테스트용 PIT universe의 역할 분리 |

기존 `core.symbol_listing_history`에는 `valid_from`, `valid_to`, `event_type`만 있어 공식 회수 가격과 공시 정보를 표현하기 어렵다. 권장 구조는 별도 `core.symbol_lifecycle_event` 테이블을 추가하는 것이다.

필수 이벤트 필드:

| 필드 | 의미 |
|---|---|
| `event_id` | 이벤트 고유 ID |
| `symbol_id` | 안정적인 종목 식별자 |
| `event_type` | `delisted`, `merger`, `acquisition`, `bankruptcy`, `relisted` |
| `announced_at` | 공시 시점 |
| `last_trade_date` | 실제 마지막 거래일 |
| `effective_date` | 법적 효력일 |
| `recovery_price` | 공식 회수가격 |
| `recovery_price_type` | `official_settlement`, `final_close`, `zero_imputed` |
| `recovery_verified` | 공식 출처 검증 여부 |
| `source_id` | KRX/KIS/DART 등 원천 출처 |
| `source_url` 또는 `document_hash` | 원천 추적 정보 |
| `successor_symbol_id` | 합병·인수 승계 종목 |
| `exchange_ratio` | 교환비율 |
| `is_inferred` | 추정 이벤트 여부 |
| `run_id` | 수집 실행 추적 |

필요한 제약조건:

- `last_trade_date <= effective_date`
- 공식 이벤트에는 `source_id`와 검증 근거가 있어야 한다.
- `zero_imputed`는 공식 회수가격으로 저장하지 않는다.
- 동일 종목·이벤트·효력일의 중복을 방지한다.
- `valid_to`는 마지막 유효 거래일을 포함하는 폐구간으로 유지한다.

이미 적용된 migration을 직접 수정하기보다 새 migration으로 최종 view를 재정의하는 방식을 권장한다.

## 3. DE lifecycle 수집

| 우선순위 | 파일 | 변경 내용 |
|---|---|---|
| P0 | `DE/quant_agent/data/repository.py:271-277` | OHLCV bar가 들어올 때마다 상장 상태를 `listed`로 기록하는 동작 제거 |
| P0 | `DE/quant_agent/data/repository.py:335-346` | 매일 OHLCV 수집 시 `delisted_at = NULL`로 되돌리는 동작 제거 |
| P0 | `DE/quant_agent/data/repository.py:393-468` | 가격 관측값 기반 lifecycle 추정을 공식 lifecycle 입력 중심으로 변경 |
| P0 | `DE/quant_agent/data/repository.py:494-518` | 하루 가격 누락을 상장폐지로 확정하는 로직 제거 |
| P0 | `DE/quant_agent/data/repository.py:541-563` | `valid_to`를 현재 날짜가 아니라 실제 마지막 거래일로 기록 |
| P0 | `DE/quant_agent/data/repository.py:1169-1220` | lifecycle upsert SQL에 event·마지막 거래일·출처·추정 여부 반영 |
| P0 | `DE/scripts/refresh_symbol_metadata.py:1-45` | OHLCV 기반 metadata refresh를 공식 이벤트 refresh로 변경 |
| P1 | 신규 `DE/scripts/ingest_symbol_lifecycle.py` | 공식 상장·상장폐지·재상장·합병 이벤트 수집 스크립트 추가 |
| P1 | `DE/quant_agent/data/models.py` | `SymbolLifecycleEvent` 또는 `DelistingEvent` 모델 추가 |
| P1 | `DE/quant_agent/data/config.py` | lifecycle source endpoint, retry, lookback, 정책 설정을 환경변수로 추가 |
| P1 | `DE/quant_agent/data/sources/krx.py` 또는 신규 source | 공식 lifecycle·회수가격 API adapter 추가 |
| P1 | `DE/quant_agent/data/external.py` | lifecycle 수집 서비스 연결 |

현재 `DE/quant_agent/data/sources/krx.py`는 일별 OHLCV 수집기다. 공식 lifecycle 데이터가 같은 API에서 제공되는지 확인한 뒤 기존 source 확장 또는 별도 source 추가를 결정해야 한다.

## 4. Airflow DAG

| 파일 | 변경 내용 |
|---|---|
| `DE/airflow/dags/quant_agent_data_engineering.py:81-83` | lifecycle 수집 스크립트 경로 설정 추가 |
| `DE/airflow/dags/quant_agent_data_engineering.py:192-202` | 기존 metadata refresh를 공식 lifecycle ingest task로 교체 또는 분리 |
| `DE/airflow/dags/quant_agent_data_engineering.py:254-265` | `OHLCV → 공식 lifecycle → PIT metadata → TA → QA` 순서로 변경 |
| `DE/airflow/dags/quant_agent_data_engineering.py:301-329` | OHLCV repair DAG에도 동일 정책 적용 |
| Airflow Connections/Variables | API credential, endpoint, 정책 버전, 추정 세션 수 설정 |
| 운영 QA | 공식 lifecycle 수집 실패 시 성공으로 처리하지 않고 실패 또는 degraded 상태 기록 |

20거래일 fallback은 calendar day가 아니라 `core.trading_calendar.is_open` 기준으로 계산해야 한다.

## 5. TA 및 feature pipeline

| 파일 | 변경 내용 |
|---|---|
| `DE/scripts/compute_technical_indicators_pipeline.py:941-958` | 공식 `symbol_listing_history`를 canonical lifecycle 입력으로 고정 |
| `DE/scripts/compute_technical_indicators_pipeline.py:1047-1095` | 가격 누락이 membership 제거로 연결되지 않도록 수정 |
| `DE/scripts/compute_technical_indicators_pipeline.py:1099-1127` | 가격 간격으로 재상장 구간을 자동 생성하는 fallback 제거 또는 `inferred`로 명시 |
| `DE/scripts/compute_technical_indicators_pipeline.py:1130-1158` | `halt_filled` row를 실제 체결 가능 가격과 구분 |
| `DE/scripts/compute_technical_indicators_pipeline.py:1290-1377` | `price_available`, `tradable_for_signal`, `stale_valuation`, `lifecycle_source` 품질 정보 추가 |

기존 `halt_filled` 플래그는 유지할 수 있지만, 백테스트에서 실제 OHLCV bar처럼 체결에 사용되지 않도록 연결해야 한다.

## 6. AI PostgreSQL data source

### `db.py`

| 파일/라인 | 변경 내용 |
|---|---|
| `ai/ai_graph/data_sources/db.py:344-386` | PIT·상장폐지 품질 metadata 추가 |
| `ai/ai_graph/data_sources/db.py:389-412` | 전체 기간의 종목 union이 아니라 날짜별 membership을 보존 |
| `ai/ai_graph/data_sources/db.py:630-669` | 최신일·이전일을 가격 테이블이 아닌 `core.trading_calendar` 기준으로 결정 |
| `ai/ai_graph/data_sources/db.py:711-721` | 현재 `symbol_master.listing_status` 우회 로직 제거 |
| `ai/ai_graph/data_sources/db.py:742-764` | 가격 조회에 날짜별 PIT universe 조인 |
| `ai/ai_graph/data_sources/db.py:1845-1920` | feature frame SQL에 PIT lifecycle 조인 |
| `ai/ai_graph/data_sources/db.py:1923-1954` | screening frame도 같은 PIT 기준 적용 |
| lookback/path feature SQL | lifecycle 밖의 가격 row가 feature 계산에 들어가지 않도록 날짜별 필터 적용 |
| price row 변환 함수 | `price_available`, `halt_filled`, lifecycle 상태, recovery 정보 전달 |

현재 가격 조회는 `core.symbol_master`만 조인한다. 따라서 과거 lifecycle 밖의 가격 row가 들어갈 수 있다.

### `db_split.py`

`AI_DATA_SOURCE_VARIANT`에서 사용될 수 있으므로 `db.py`와 병행 수정해야 한다.

| 파일/라인 | 변경 내용 |
|---|---|
| `ai/ai_graph/data_sources/db_split.py:75-85` | 현재 `listing_status` 우회 정책 수정 |
| `ai/ai_graph/data_sources/db_split.py:489-520` | PIT universe 조회 적용 |
| `ai/ai_graph/data_sources/db_split.py:830-941` | 가격 row에 날짜별 PIT 조인 |
| `ai/ai_graph/data_sources/db_split.py:1176-1217` | symbol info를 현재 상태가 아닌 as-of 상태로 반환 |

`db_test.py`와 `profile_aware.py`는 운영 데이터 소스로 사용하지 않으며, fixture는 반드시 `source='fixture'`로 남겨야 한다.

## 7. 결과 metadata 전달

`ai/ai_graph/data_sources/db.py`에서 다음 필드를 생성해야 한다.

```json
{
  "pit_universe_source": "mart.common_stock_universe_asof",
  "pit_universe_start": "...",
  "pit_universe_end": "...",
  "pit_member_count": 0,
  "price_missing_member_count": 0,
  "official_delisting_count": 0,
  "inferred_delisting_count": 0,
  "official_recovery_count": 0,
  "final_close_proxy_count": 0,
  "zero_imputed_count": 0,
  "delisting_policy_version": "v1"
}
```

| 파일 | 변경 내용 |
|---|---|
| `ai/ai_graph/graph.py:625-651` | 기존 metadata 전달 과정에서 새 필드가 누락되지 않는지 확인 |
| `ai/ai_graph/nodes/report.py:106-149` | 상장폐지 데이터 품질 경고를 report context에 포함 |
| `ai/ai_graph/quant_performance.py:121-211` | inferred·zero-imputed 발생 시 reliability를 `limited` 또는 `insufficient`로 조정 |
| `ai/ai_graph/schemas.py` | 외부 API에서 typed field가 필요하면 schema 추가 |
| `ai/ai_graph/nodes/backtest.py:779-793` | lifecycle/event/policy를 engine config에 전달 |
| `ai/ai_graph/nodes/backtest.py:1706, 2086` | 후보 평가·walk-forward 경로에도 동일 정책 전달 |
| `ai/ai_graph/nodes/backtest.py:1429-1491` | engine summary의 delisting metadata 보존 |

## 8. 백테스트 엔진

### 모델

| 파일 | 변경 내용 |
|---|---|
| `backtest_module/backtest_module/models.py:184-205` | `CorporateActionEvent`에 공식 이벤트 필드 추가 |
| event type | `merger`, `acquisition`, `bankruptcy`, `relisted` 추가 또는 lifecycle event와 분리 |
| recovery validation | 공식 가격이 없어도 이벤트를 허용하고 `final_close` proxy로 구분 |
| 추가 필드 | `last_trade_date`, `announced_at`, `recovery_price_type`, `source_id`, `successor_symbol_id`, `exchange_ratio`, `is_inferred` |

### 실행 로직

| 파일/라인 | 변경 내용 |
|---|---|
| `backtest_module/backtest_module/backtest.py:202-222` | `delisting_grace_days`를 거래 세션 기반 설정으로 변경 |
| `backtest_module/backtest_module/backtest.py:202-222` | `delisting_recovery_rate=0.0`을 정상 기본값에서 제거 |
| `backtest_module/backtest_module/backtest.py:760-840` | 공식 lifecycle event를 먼저 처리하고 신규 주문·신호 차단 |
| `backtest_module/backtest_module/backtest.py:983-1064` | 공식 event → 공식 recovery → final close proxy → inferred fallback 순서 적용 |
| `backtest_module/backtest_module/backtest.py:1066-1098` | `effective_date`뿐 아니라 `last_trade_date`, recovery type, successor mapping 반영 |
| `backtest_module/backtest_module/backtest.py:1545-1597` | 공식·추정·0원 회수 건수와 reliability reason 기록 |

권장 처리 순서:

```text
공식 상장폐지 이벤트
→ 공식 회수 가격
→ 마지막 실제 거래일 종가 proxy
→ 20거래 세션 무가격 inferred
→ 0원 회수는 stress run에서만
```

추가로 확정해야 할 엔진 계약:

- 회수 현금을 `last_trade_date`에 반영할지 `effective_date`에 반영할지
- 공식 정산가격에 슬리피지를 적용할지 여부
- 합병 승계 시 보유수량·원가를 어느 날짜에 이전할지

## 9. 백엔드 저장 및 API

| 파일 | 변경 내용 |
|---|---|
| `backend/app/services/ai_backtest_subprocess_runner.py:90-193` | engine에 lifecycle/event/policy 전달 및 결과 metadata 추출 |
| `backend/app/schemas/ai_backtest.py:166-201` | `delisting_jsonb` 또는 관련 typed field 추가 |
| `backend/app/schemas/ai_backtest.py:221-260` | run config에 정책 버전·source 정보 추가 |
| 신규 `service_db/migrations/022_*.sql` | `app.backtest_summary`에 상장폐지 품질 JSON 또는 counter 추가 |
| `backend/app/db/ai_backtest_repository.py:1194-1219` | 새 summary 필드 insert |
| `backend/app/db/ai_backtest_repository.py:1630-1633` | JSON serialization 추가 |
| `backend/app/db/existing_report_queries.py:836-867` | report 조회 시 delisting metadata 반환 |
| `backend/app/services/fe_contract_store.py:1615-1688` | FE용 결과에 metadata 보존 |
| `service_db/docs/backtest_result_mapping.md` | 저장 매핑 문서 갱신 |

기존 JSON 구조와 맞추려면 `app.backtest_summary.delisting_jsonb`에 관련 정보를 저장하는 방식을 권장한다.

## 10. FE 표시

| 파일 | 변경 내용 |
|---|---|
| `fe/src/types/quantagent.ts:277-279` | delisting metadata 타입 추가 |
| `fe/src/features/app/PerformanceTab.tsx:70-90` | 공식·proxy·inferred·zero-imputed 품질 표시 |
| `fe/src/features/app/OverviewTab.tsx:66-72` | degraded 결과 경고 표시 |
| `fe/scripts/quant-performance-source.test.mts` | inferred·zero-imputed 표시 테스트 추가 |

## 11. 테스트

### 기존 테스트 수정

| 파일 | 변경 내용 |
|---|---|
| `DE/tests/test_sql_migration.py` | 최종 migration 이후 PIT view가 canonical인지 검증 |
| `ai/tests/test_db_data_source.py:1165-1176` | migration 007뿐 아니라 최종 view 정의 검증 |
| `ai/tests/test_db_data_source.py:1214-1223` | PIT join이 반드시 존재하도록 기대값 변경 |
| `backtest_module/tests/test_backtest.py:515-595` | 20일 후 0원 상각을 기본 동작으로 검증하는 테스트 제거 |
| `backtest_module/tests/test_backtest.py:749-763` | recovery price 필수 조건을 proxy 정책에 맞게 수정 |
| `ai/tests/test_quant_performance.py` | inferred·zero-imputed 발생 시 reliability 저하 검증 |
| `backend/tests/unit/test_ai_backtest_flow.py:420` | 새 summary metadata 검증 |
| `service_db/tests/test_sql_migration.py` | 새 summary migration 검증 |
| `DE/tests/test_airflow_dag_import.py` | lifecycle task와 dependency 검증 |

### 신규 필수 시나리오

1. 상장 전 날짜에는 PIT universe에서 제외
2. `valid_from`과 `valid_to` 당일은 포함
3. `valid_to` 다음 거래일은 제외
4. 가격 bar가 없어도 PIT membership 유지
5. 하루 거래정지는 상장폐지로 처리하지 않음
6. 공식 상장폐지와 공식 recovery price 처리
7. 공식 recovery price 없음 → final close proxy
8. 이벤트 없음 + 20거래 세션 무가격 → `delisting_inferred`
9. inferred 결과에 degraded 품질 표시
10. 0원 회수는 stress policy에서만 동작
11. 합병 승계 종목과 교환비율 매핑
12. 승계 정보 불완전 시 `corporate_action_unresolved`
13. 현재 `symbol_master.listing_status`가 잘못되어도 과거 PIT 결과 불변
14. fixture 데이터가 `source='postgres'`로 위장하지 않음

## 12. 문서 및 운영 기록

| 파일 | 변경 내용 |
|---|---|
| `DE/docs/DE.md:114,127-147` | 가격 row가 있어야 universe에 포함된다는 설명 수정 |
| `DE/README.md` | PIT universe와 현재 상장 helper view를 구분 |
| `DE/docs/data_engineering_runbook.md` | lifecycle 수집·backfill·검증 절차 추가 |
| `DE/docs/data_engineering_ingestion_scripts.md` | 공식 이벤트 수집 스크립트 추가 |
| `DE/docs/public_server_db_tables.md:141-150,463-471` | 실제 schema와 view 정의 갱신 |
| `DE/공용_서버_DB_현황.md:144-153,450-479` | 서버 migration 적용 후 실제 결과로 갱신 |
| `ai/README_AI.md`, `ai/docs/ai-api-contract.md` | PIT source와 delisting metadata 명시 |
| `service_db/docs/backtest_result_mapping.md` | 저장 필드 매핑 추가 |
| `docs/point-in-time-delisting-data-contract.md` | 구현 후 계약 버전과 실제 source 상태 갱신 |

서버 현황 문서는 실제 PostgreSQL을 확인한 뒤에만 숫자와 상태를 갱신해야 한다. 로컬 fixture나 테스트 출력으로 서버 상태를 채우면 안 된다.

## 13. 구현 전 외부 확인사항

| 확인사항 | 이유 |
|---|---|
| 공식 상장폐지 원천 API | 현재 공식 lifecycle source client가 없음 |
| 공식 회수가격 제공 여부 | KRX/KIS/DART별 필드 확인 필요 |
| `effective_date`와 `last_trade_date` 관계 | 서버 적재 데이터 의미 검증 필요 |
| 합병 승계 종목·교환비율 source | 별도 corporate action source 필요 |
| 회수금 반영 시점 | 백테스트 엔진 계약 추가 필요 |
| 서버 기존 lifecycle 데이터 품질 | 실제 PostgreSQL 표본 검증 필요 |

## 14. 권장 구현 순서

1. 공식 source 필드와 서버 데이터 품질 확인
2. lifecycle event schema migration 추가
3. 공식 lifecycle backfill 및 수집기 구현
4. DE repository와 PIT view 수정
5. AI price/feature query에 PIT 조인
6. 백테스트 event/recovery 정책 구현
7. backend 저장·API·FE 전파
8. 기존 테스트 수정 및 신규 시나리오 검증
9. 실제 서버 PostgreSQL 기준 replay와 metadata 검증
