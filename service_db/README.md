# Service DB

QuantAgent 서비스 내부에서 생성되는 운영 데이터를 PostgreSQL `app` 스키마로 관리한다.

이 폴더는 주식 원천 데이터나 외부 수집 데이터를 관리하는 영역이 아니라, 서비스 사용 과정에서 발생하는 사용자, 전략, 백테스트 실행/결과, 리포트, 이메일 발송 이력, AI 처리 결과, trace/log 데이터를 저장하기 위한 DB migration과 문서를 관리한다.

현재는 백테스트 결과 저장 구조와 이메일 리포트 저장 구조를 우선 정리한 상태이며, AI 채팅/전략 파싱/검증/trace/log 저장 구조는 팀 논의 후 후속 migration으로 확장한다.

## 관리 대상

현재 포함 또는 우선 관리 대상으로 보는 데이터는 다음과 같다.

- 사용자 정보
- 전략 정보
- 백테스트 실행 이력
- 백테스트 일별 자산곡선
- 백테스트 거래내역
- 백테스트 매매신호
- 백테스트 요약 성과 및 상세 지표
- 전략 리포트 목록 및 상세 리포트
- 이메일 리포트 본문
- 이메일 리포트 내 뉴스 및 후보 종목
- 이메일 구독 설정
- 이메일 발송 이력

향후 확장 대상으로 보는 데이터는 다음과 같다.

- AI 채팅 세션 및 메시지
- 자연어 전략 파싱 결과
- 전략 검증 결과
- AI 생성 코드 저장
- AI 생성 코드 검증 결과
- 샌드박스 코드 실행 이력
- AI 백테스트 리포트
- AI 모델 호출 로그
- 프롬프트 로그
- agent 실행 trace/log
- 에러 로그
- AI 전략 파싱 결과와 백테스트 실행 간 연결 정보
- 백테스트 결과 저장용 adapter/writer 구현 기준
- 이메일 발송 writer 구현 기준

## 폴더 구조

```text
service_db/
├── README.md
├── docs/
│   ├── backtest_result_mapping.md
│   ├── report_email_storage.md
│   └── service_db_erd.md
└── migrations/
    ├── 001_app_schema.sql
    ├── 002_extend_backtest_results.sql
    └── 003_create_report_email_tables.sql
```

## Migration

`001_app_schema.sql`은 현재 운영 DB에 직접 생성되어 있는 `app` 스키마를 Git에서 재현 가능하도록 정리한 baseline이다.

`002_extend_backtest_results.sql`은 백테스트 성과 지표를 `app.backtest_summary`에 추가하고, JSON·시계열 지표를 저장하는 `app.backtest_metric_detail`을 생성한다. 기간·거래 기준과 연율화 여부는 컬럼명에 반영하고, 아직 계산되지 않는 지표는 `NULL`로 유지한다.

`003_create_report_email_tables.sql`은 `/reports`, `/reports/strategies/:strategyId`, `/reports/:reportId`, `/me` 이메일 이력 화면을 DB로 전환할 때 필요한 전략 리포트, 이메일 리포트, 구독 전략, 발송 이력 저장 구조를 추가한다.

현재 포함된 주요 테이블은 다음과 같다.

- `app.users`
- `app.strategy`
- `app.backtest_run`
- `app.backtest_equity_point`
- `app.backtest_trade`
- `app.backtest_signal`
- `app.backtest_summary`
- `app.backtest_metric_detail`
- `app.strategy_report_profile`
- `app.strategy_email_report`
- `app.strategy_email_report_news`
- `app.strategy_email_report_candidate`
- `app.email_digest_subscription`
- `app.email_delivery_history`

현재 포함된 주요 view는 다음과 같다.

- `app.strategy_report_summary_v`
- `app.email_digest_history_v`

## 백테스트 결과 저장 기준

백테스트 결과 저장 구조는 현재 `backtest_module`의 출력 구조를 기준으로 설계한다.

주의해야 할 대표 매핑은 다음과 같다.

- 백테스트 코드의 `summary["win_rate"]` 및 `summary["trade_win_rate"]`는 거래 승률이며, `app.backtest_summary.win_rate`에 저장한다.
- 백테스트 코드의 `summary["return_win_rate"]`는 기간 수익률 승률이며, `app.backtest_summary.period_win_rate`에 저장한다.
- 백테스트 코드의 `summary["daily_sharpe_like"]` 또는 `summary["sharpe_ratio"]`는 `app.backtest_summary.sharpe_ratio`에 저장한다.
- `SignalRecord`의 `reasons`, `matching_entry_rules`, `matching_exit_rules`는 코드에서 문자열로 관리될 수 있으므로 DB 저장 시 JSON 배열 형태로 변환하는 adapter가 필요하다.

백테스트 출력과 DB 컬럼 간 변환 규칙은 [`docs/backtest_result_mapping.md`](docs/backtest_result_mapping.md)에서 관리한다.

백테스트 저장 구조의 물리 ERD와 상세 지표 컬럼은 [`docs/service_db_erd.md`](docs/service_db_erd.md)에서 확인한다.

## 이메일 리포트 저장 기준

이메일 리포트 저장 구조는 프론트엔드의 전략 리포트 및 이메일 리포트 화면에서 필요한 데이터를 우선 저장하는 것을 목표로 한다.

주요 화면과 DB 매핑은 [`docs/report_email_storage.md`](docs/report_email_storage.md)에서 관리한다.

현재 기준으로 대응하는 주요 화면은 다음과 같다.

- `/reports`: 전략 리포트 목록
- `/reports/strategies/:strategyId`: 전략 상세 리포트
- `/reports/:reportId`: 이메일 리포트
- `/me`: 이메일 발송 이력 및 구독 정보

## DE migration과의 관계

현재 `DE/migrations/011_app_ai_backtest_erd.sql`에는 `app` 스키마의 AI 백테스트 실행, 코드 생성/검증, trace/log 관련 테이블 초안이 포함되어 있다.

해당 SQL은 백엔드의 AI-generated backtest flow와 직접 연결되는 구조이며, `DE/tests/test_sql_migration.py`에서도 해당 테이블과 컬럼 존재를 검증한다.

다만 `app` 스키마는 서비스 내부 운영 데이터에 해당하므로, 장기적으로는 `service_db`에서 관리하는 것이 자연스럽다. 이번 PR에서는 `DE/migrations/011_app_ai_backtest_erd.sql`을 이동하거나 수정하지 않고, 이메일 리포트 저장 구조만 추가한다.

`DE/migrations/011_app_ai_backtest_erd.sql` 이후 `DE/migrations/012_symbol_sector_metadata.sql`가 이미 추가되어 있으므로, `011`을 단순 이동하거나 삭제하지 않는다. 기존 DE migration 번호와 적용 이력을 보존하기 위해 `011`은 historical migration으로 남기고, 향후 `app` 스키마 공식 관리는 팀 합의 후 `service_db` 후속 migration에서 흡수/정렬한다.

## Migration 적용 방식

현재 `DE/migrations`와 `service_db/migrations`는 자동으로 통합 적용되지 않는다.

DE migration은 `DE/scripts/apply_migrations.ps1`가 `DE/migrations`를 파일명 순서대로 적용한다. `service_db/migrations`는 현재 아래 `psql -f` 명령으로 별도 적용한다.

동일 DB에 DE migration 전체와 service_db migration을 모두 적용할 경우, `DE/migrations/011_app_ai_backtest_erd.sql`도 `app` 스키마를 생성하므로 `app` 스키마 중복 정의가 발생할 수 있다. 향후 `app` 스키마 소유권과 통합 적용 순서를 팀에서 확정해야 한다.

이미 `DE/migrations/011_app_ai_backtest_erd.sql`이 적용된 DB에는 `service_db/migrations/001_app_schema.sql`과 `002_extend_backtest_results.sql`을 무작정 재적용하지 않는다. 두 경로는 `app.users`, `app.strategy`, `app.backtest_*` 테이블을 일부 중복 정의하므로, 기존 DB 상태를 확인한 뒤 필요한 후속 정렬 migration만 적용한다.

현재 백엔드 AI 백테스트 저장 로직은 `DE/migrations/011_app_ai_backtest_erd.sql` 기준 컬럼을 사용한다. 따라서 공용 DB나 개발 DB의 `app` 스키마가 `service_db/001` 기준으로만 생성되어 있다면, AI 백테스트 저장 로직을 실행하기 전에 `DE 011` 또는 후속 정렬 migration 기준으로 스키마를 맞춰야 한다.

로컬 또는 개발 DB에서 service_db migration을 적용할 때는 번호 순서대로 실행한다. 이미 `001` baseline이 적용된 DB에서는 이후 번호의 migration만 실행한다.

```powershell
psql -d <database_name> -v ON_ERROR_STOP=1 -f service_db/migrations/001_app_schema.sql
psql -d <database_name> -v ON_ERROR_STOP=1 -f service_db/migrations/002_extend_backtest_results.sql
psql -d <database_name> -v ON_ERROR_STOP=1 -f service_db/migrations/003_create_report_email_tables.sql
```

이번 PR은 migration 파일 추가 범위이며, 공용 DB에는 아직 적용하지 않는다. 리뷰 및 merge 후 대상 개발 DB 또는 공용 DB에 번호 순서대로 적용해야 한다.

실제 데이터, DB 접속 정보, 비밀번호, API key, `.env` 값은 포함하지 않는다.

## 아직 정리되지 않은 연결 관계

현재 migration은 백테스트 결과와 이메일 리포트 저장을 우선 구현한 상태다. 전체 서비스 흐름 기준으로는 다음 FK 및 연결 관계를 후속 migration에서 정리해야 한다.

- `strategy.source_parse_id` → AI 전략 파싱 결과
- `backtest_run.session_id` → AI 채팅 세션
- `backtest_run.source_parse_id` → AI 전략 파싱 결과
- `backtest_run.trace_id` → 전체 실행 trace
- AI 생성 코드 및 코드 실행 이력 → 백테스트 실행
- AI 백테스트 리포트 → 백테스트 실행
- 이메일 리포트 → AI 리포트 또는 전략 리포트
- 이메일 발송 이력 → 사용자, 이메일 리포트, 구독 설정
- 에러/agent/model call 로그 → trace, session, run, report

따라서 현재 schema는 최종 전체 서비스 DB가 아니라, 우선순위가 높은 저장 구조부터 쌓아가는 중간 단계다.

## 팀 논의 필요 사항

다음 항목은 백엔드, AI, 백테스트, DE 담당자와 합의가 필요하다.

- 공용 PostgreSQL DB는 하나를 같이 쓰고, `meta/raw/core/feature/mart`는 DE가, `app`은 service_db가 관리하는 방향으로 나눌지 여부
- `DE/migrations/011_app_ai_backtest_erd.sql`의 `app` 스키마 초안을 service_db 후속 migration의 기준으로 사용할지 여부
- `DE/migrations/011_app_ai_backtest_erd.sql`은 historical migration으로 유지하고, 후속 `app` 스키마 관리는 service_db에서 할지 여부
- DE migration과 service_db migration을 같은 DB에 적용할 때의 적용 순서
- service_db 전용 적용 스크립트 또는 통합 migration 적용 방식 추가 여부
- AI 전략 파싱 결과의 식별자를 `parse_id`로 관리하고 `strategy` 및 `backtest_run`에서 참조할지 여부
- `backtest_signal.action` 값을 현재 코드 기준 `buy/sell/hold`로 유지할지, ERD 기준 `entry/exit/rebalance/hold`로 변경할지 여부
- `backtest_trade`가 종료된 거래만 저장할지, 미청산 포지션까지 nullable exit 필드로 저장할지 여부
- `order_audit.csv`로 생성되는 주문 감사 로그를 별도 DB 테이블로 저장할지 여부
- `rolling_volatility`, `rolling_sharpe`, `rolling_sortino`, `montecarlo_mean`, `metric_warnings` 저장 위치
- AI 리포트와 이메일 리포트를 같은 report 계열로 볼지, 별도 도메인으로 분리할지 여부
- 사용자 알림 설정 및 이메일 수신 설정을 별도 테이블로 둘지 여부

## 후속 작업 계획

우선순위는 다음과 같다.

1. 이메일 리포트 저장 구조 리뷰 및 PR 반영
2. `app` 스키마 migration 소유권과 DE migration과의 관계 정리
3. service_db 적용 방식 또는 적용 스크립트 추가 여부 결정
4. AI 채팅 세션 및 메시지 저장 migration 추가
5. AI 전략 파싱 및 검증 결과 저장 migration 추가
6. AI 생성 코드, 코드 검증 결과, 코드 실행 이력 저장 migration 추가
7. AI trace/model call/prompt/agent/error log 저장 migration 추가
8. AI 백테스트 리포트 저장 migration 추가
9. 백테스트 실행과 AI 전략 파싱 결과 간 FK 정리
10. 백테스트 결과 adapter/writer 구현 기준 문서화
11. 이메일 발송 writer 구현 기준 문서화
12. 전체 service DB ERD 갱신
