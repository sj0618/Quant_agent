# Service DB

QuantAgent 서비스 과정에서 생성되는 운영 데이터를 PostgreSQL `app` 스키마로 관리한다.

외부 데이터 수집·정제·가공용 `meta/raw/core/feature/mart` 스키마는 `DE/migrations`가 소유하고, 사용자·전략·AI 실행·백테스트·리포트·이메일 데이터가 속한 `app` 스키마는 이 폴더가 소유한다.

## 관리 범위

- 사용자와 전략
- AI 채팅, 전략 파싱, 코드 생성·검증·실행
- trace, 모델 호출, prompt, agent 실행 및 오류 로그
- 백테스트 실행, 자산곡선, 신호, 거래, 성과지표
- AI 백테스트 리포트
- 이메일 리포트, 뉴스, 추천 후보 종목
- 이메일 구독과 수신자별 발송 이력

## 구조

```text
service_db/
├── migrations/
│   ├── 011_app_ai_backtest_erd.sql
│   ├── 013_ai_runtime_logging.sql
│   └── 014_create_report_email_tables.sql
├── scripts/
│   └── apply_migrations.ps1
├── tests/
│   └── test_sql_migration.py
└── docs/
    ├── backtest_result_mapping.md
    ├── report_email_storage.md
    └── service_db_erd.md
```

## Migration 기준

### `011_app_ai_backtest_erd.sql`

`app` 스키마의 기준 migration이다. 기존 `DE/migrations/011_app_ai_backtest_erd.sql`을 이동한 파일이며, 현재 백엔드의 AI 백테스트 writer가 사용하는 컬럼 계약을 유지한다.

공용 서버 `qt_db`에는 이동 전 DE 011이 적용되지 않은 것을 확인했으므로, 공용 DB에 대한 rollback 없이 관리 위치만 변경한다.

### `013_ai_runtime_logging.sql`

모델 호출 로그에 agent 실행 연결, 응답 스키마 이름, 웹 검색 사용 여부를 추가하고 prompt 보존 기간 정리용 인덱스를 생성한다. 원격 main에서 공식 경로와 번호가 확정된 migration을 그대로 사용한다.

### `014_create_report_email_tables.sql`

다음 화면과 이메일 발송 기능을 위한 저장 구조를 추가한다.

- `/reports`
- `/reports/strategies/:strategyId`
- `/reports/:reportId`
- `/me` 이메일 이력 및 구독 정보

이메일 리포트는 `strategy_id`를 필수로 참조하고, 생성 근거를 추적할 수 있도록 `backtest_run_id`와 `ai_report_id`를 선택적으로 참조한다. 화면 재현을 위한 `performance_jsonb`는 당시 표시값의 snapshot으로 유지한다.

## 로컬 실행

로컬 TimescaleDB는 기존 `DE/compose.yaml`의 `db` 서비스를 재사용한다. service_db가 별도 DB 컨테이너를 만들지는 않는다.

사전 조건:

- Docker Desktop이 설치되고 실행 중이어야 한다.
- `QUANT_DB_PASSWORD`를 현재 PowerShell 세션에 설정해야 한다.
- 이 스크립트는 현재 migration history를 관리하지 않으므로 빈 로컬 DB 검증 용도로 사용한다.

service_db만 적용:

```powershell
$env:QUANT_DB_PASSWORD = "<local-password>"
./service_db/scripts/apply_migrations.ps1
```

## 확인

```sql
SELECT
    to_regclass('app.backtest_run'),
    to_regclass('app.ai_model_call_log'),
    to_regclass('app.strategy_email_report'),
    to_regclass('app.email_delivery_history');
```

테이블이 생성되어 있으면 각 열에 정규화된 테이블 이름이 표시되고, 없으면 `NULL`이 표시된다.

정적 계약 테스트:

```powershell
python -m unittest discover -s service_db/tests -p "test_*.py"
```

## 적용 시 주의사항

- PR merge만으로 공용 서버 DB에 migration을 자동 적용하지 않는다.
- 서버 적용 전 대상 DB, 백업, 적용 파일과 시간을 팀에서 합의한다.
- 로컬에서 기존 DE 011을 이미 적용한 경우 `001`을 다시 실행하지 말고 적용 완료 baseline으로 취급한다.
- migration 파일명만이 아니라 `DE/...` 또는 `service_db/...` 전체 경로를 적용 이력의 식별자로 사용해야 한다.
- 비밀번호, DSN, API key와 `.env` 값은 저장소에 커밋하지 않는다.
- 운영 로그 저장 활성화 전 서버 DB의 TLS 연결을 구성하고 검증한다.

## 관련 문서

- [백테스트 결과 매핑](docs/backtest_result_mapping.md)
- [이메일 리포트 저장 매핑](docs/report_email_storage.md)
- [Service DB ERD](docs/service_db_erd.md)
