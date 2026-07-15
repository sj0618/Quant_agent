# BE 로깅 미해결 해결 보고서

작성일: 2026-07-14

## 결과
기존 BE 로깅 계획의 미해결 blocker를 구현하고 검증했다.

- subprocess release barrier와 process identity/CAS recovery
- scope-family 기반 idempotency 및 outcome-unknown/replacement approval
- backend raw prompt/response signed admission
- ai_graph persistent sink signed Gate B admission 및 direct ingress 차단
- 백테스트 route 전용 sanitized error envelope
- `backend.app.main` 앱 조립 import 복구

## 주요 변경

### 실행 안전성
- `backend/app/services/ai_backtest_subprocess_runner.py`
  - 정확히 1바이트 release 신호와 EOF를 확인한 뒤에만 입력 파일을 읽고 실행한다.
  - EOF, 짧은 입력, 잘못된 바이트는 side effect 없이 종료한다.
- `backend/app/services/ai_backtest_runtime.py`
  - PID/PGID/host/attempt identity를 기록하고 release 전 ownership CAS를 수행한다.
- `service_db/migrations/015_ai_backtest_execution_process_identity.sql`
  - 실행 attempt 및 process identity 컬럼/index를 추가한다.

### Idempotency와 복구
- `service_db/migrations/016_ai_backtest_idempotency.sql`
  - scope-family/fingerprint lease, outcome-unknown, replacement approval 테이블과 인덱스를 추가한다.
- `backend/app/db/ai_backtest_repository.py`
  - 동일 fingerprint의 다른 key 중복 실행을 차단한다.
  - replacement approval은 scope/fingerprint/evidence/만료/단회 소비를 원자적으로 검증한다.
- `backend/app/services/session_store.py`, `backend/app/core/config.py`
  - opaque 세션 호환성을 유지하면서 scope family와 HMAC rotation 설정을 제공한다.

### Gate B와 원문 로그
- `backend/app/services/raw_audit_admission.py`
  - 전용 HMAC secret, key version, evidence, audience, deployment revision, issued/expiry를 검증한 signed admission만 발급한다.
- `backend/app/db/ai_backtest_repository.py`
  - raw admission 없이는 model/prompt INSERT를 수행하지 않는다.
- `ai/ai_graph/audit_postgres.py`
  - persistent sink를 signed Gate B admission 뒤에만 생성한다.
  - production에서 직접 주입된 미승인 sink/session은 NoOp으로 차단한다.
  - production 모듈의 공개 persistent test factory를 제거하고 테스트 전용 helper로 이동했다.

### API 오류 계약
- `backend/app/api/routes/ai_backtest.py`
  - 백테스트 route에만 400/202/409/422/502/503/504 응답과 sanitized envelope를 적용한다.
  - 전역 legacy 오류 envelope는 다른 route에서 유지한다.
- `backend/app/schemas/ai_backtest.py`
  - running/replay/error response 모델을 명시한다.

### 앱 조립
- `backend/app/main.py`
  - `fe_contract` router import 누락을 복구했다.
- `backend/tests/unit/test_main_smoke.py`
  - 외부 credential 없이 app import/create smoke를 검증한다.

## 검증 결과

| 영역 | 명령 | 결과 |
|---|---|---:|
| Backend | `cd backend && python -m pytest -q tests/unit/test_main_smoke.py tests/unit/test_ai_backtest_subprocess_runner.py tests/unit/test_ai_backtest_runtime.py tests/unit/test_ai_backtest_flow.py tests/unit/test_ai_backtest_repository.py tests/unit/test_ai_backtest_route.py tests/unit/test_auth_config.py` | 76 passed, 6 warnings |
| AI audit | `cd ai && python -m pytest -q tests/test_audit.py tests/test_audit_postgres.py tests/test_api.py tests/test_graph_e2e.py` | 67 passed, 1 skipped, 2 warnings |
| Service DB | `cd service_db && python -m pytest -q tests/test_sql_migration.py` | 5 passed |
| DE retention/migration | `cd DE && python -m pytest -q tests/test_sql_migration.py tests/test_ai_prompt_retention.py tests/test_airflow_dag_import.py` | 23 passed |
| App smoke | `cd backend && python -c 'from app.main import app; print(type(app).__name__)'` | `FastAPI` |
| Diff integrity | `git diff --check` | 통과 |

최종 아키텍처 리뷰: **CLEAR / APPROVE**

## 제한 및 운영 주의

- `AI_LOGGING_TEST_DSN`이 없는 환경에서는 실제 PostgreSQL/TimescaleDB round-trip 테스트가 skip될 수 있다.
- AI 테스트의 1개 skip은 disposable DB 의존 테스트다.
- production enable 시 signed admission의 실제 `expiry`, `audience`, `evidence_id`, `deployment_revision`, `key_version`을 릴리스 값으로 주입해야 한다.
- Gate B HMAC secret은 OAuth secret과 분리하고 rotation 절차를 따른다.
- 이번 작업은 커밋/푸시하지 않았다.
