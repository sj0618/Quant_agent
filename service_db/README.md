# Service DB

QuantAgent 서비스 운영에 필요한 PostgreSQL `app` 스키마를 관리한다.

## 관리 대상

- 사용자 정보
- 전략 정보
- 백테스트 실행 이력
- 백테스트 일별 자산곡선
- 백테스트 거래내역
- 백테스트 매매신호
- 백테스트 요약 성과 및 상세 지표
- 향후 서비스 실행 trace/log
- 향후 리포트 및 이메일 발송 이력

## 폴더 구조

```text
service_db/
├── README.md
├── docs/
│   ├── backtest_result_mapping.md
│   └── service_db_erd.md
└── migrations/
    ├── 001_app_schema.sql
    └── 002_extend_backtest_results.sql
```

## Migration

`001_app_schema.sql`은 현재 운영 DB에 직접 생성되어 있는 `app` 스키마를 Git에서 재현 가능하도록 정리한 baseline이다.

`002_extend_backtest_results.sql`은 향후 백테스트 엔진에 구현될 단일 숫자 성과 지표를 `app.backtest_summary`에 추가하고, JSON·시계열 지표를 저장하는 `app.backtest_metric_detail`을 생성한다. 기간·거래 기준과 연율화 여부는 컬럼명에 반영하고, 아직 계산되지 않는 지표는 `NULL`로 유지한다.

`app.backtest_metric_detail`은 한 백테스트 실행에 대해 복합·시계열 지표 12개를 nullable JSONB 컬럼으로 저장한다.

백테스트 출력과 DB 컬럼 간 변환 규칙은 [`docs/backtest_result_mapping.md`](docs/backtest_result_mapping.md)에서 관리한다.

백테스트 저장 구조의 물리 ERD와 상세 지표 컬럼은 [`docs/service_db_erd.md`](docs/service_db_erd.md)에서 확인한다.

현재 포함된 테이블은 다음과 같다.

- `app.users`
- `app.strategy`
- `app.backtest_run`
- `app.backtest_equity_point`
- `app.backtest_trade`
- `app.backtest_signal`
- `app.backtest_summary`
- `app.backtest_metric_detail`

## 적용 방법

로컬 또는 개발 DB에서 migration을 번호 순서대로 적용한다. 이미 `001` baseline이 적용된 DB에서는 `002`만 실행한다.

```powershell
psql -d <database_name> -v ON_ERROR_STOP=1 -f service_db/migrations/001_app_schema.sql
psql -d <database_name> -v ON_ERROR_STOP=1 -f service_db/migrations/002_extend_backtest_results.sql
```

`002` migration은 저장 구조만 추가한다. 실제 백테스트 결과를 DB에 넣으려면 `BacktestResult`를 각 테이블 행으로 변환하는 adapter/writer가 별도로 필요하다.

실제 데이터, DB 접속 정보, 비밀번호, API key, `.env` 값은 포함하지 않는다.

## 향후 확장 예정

- AI 채팅 세션 및 메시지 저장
- 자연어 전략 파싱 결과 저장
- 전략 검증 결과 저장
- AI 백테스트 리포트 저장
- 이메일 발송 이력 및 실패 로그 저장
- AI/Backend/Backtest 실행 trace 및 error log 저장
- 백테스트 결과 저장용 adapter/writer 구현
