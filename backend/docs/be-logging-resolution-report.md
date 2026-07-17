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

## P0 로컬 운영 안전장치 추가

- `AI_BACKTEST_RAW_AUDIT_ENABLED=false`를 기본값으로 추가하고, 비활성 상태에서는 test marker를 포함한 admission 발급과 raw INSERT를 차단한다.
- AI PostgreSQL audit session은 각 write transaction 직전에 expiry, claim integrity, revocation 상태를 재검증한다. 외부 signer/provider가 없는 환경에서는 raw-on과 Gate B 활성화를 BLOCKED로 유지한다.
- `service_db/scripts/verify_fixed_migration_replay.py`와 `run_fixed_migration_replay.py`는 011/013/014/015/016 고정 순서, disposable DSN, PG17/pgcrypto, catalog fingerprint, BLOCKED artifact를 검증한다.
- `.github/workflows/ai-logging.yml`은 replay DB와 purge DB를 분리하고, purge DB를 `ai_prompt_retention_test_ci`로 생성해 `AI_PROMPT_RETENTION_TEST_DSN`으로 연결한다. 따라서 `DE/tests/test_ai_prompt_retention.py`의 실제 PostgreSQL integration이 CI에서 skip되지 않고 실행된다.
- workflow PR path는 config, raw admission, `.env.example`, auth config 계약 변경을 감시하고, focused lint/backend pytest는 lint/test 가능한 해당 Python 경로를 함께 검증한다.
- 외부 signer/SBOM/trusted root와 revocation/WORM provider가 없으므로 production/staging raw-on, canary, Gate B 실제 활성화는 수행하지 않았다.
- `production`, `prod`, `staging`, `stage` runtime에서는 backend admission과 AI PostgreSQL sink를 provider-backed 승인 전까지 hard-disable한다.

## 검증 결과

| 영역 | 명령 | 결과 |
|---|---|---:|
| Backend focused | `cd backend && python -m pytest -q tests/unit/test_auth_config.py tests/unit/test_ai_backtest_flow.py tests/unit/test_ai_backtest_repository.py` | 53 passed |
| AI write-guard focused | `cd ai && python -m pytest -q tests/test_audit_postgres.py` | 32 passed, 1 skipped |
| Service DB replay contract | `cd service_db && python -m pytest -q tests/test_sql_migration.py` | 9 passed |
| DE retention focused | `cd DE && python -m pytest -q tests/test_ai_prompt_retention.py` | 6 passed, 2 skipped |
| Backend regression suite | `cd backend && python -m pytest -q tests/unit/test_main_smoke.py tests/unit/test_ai_backtest_subprocess_runner.py tests/unit/test_ai_backtest_runtime.py tests/unit/test_ai_backtest_flow.py tests/unit/test_ai_backtest_repository.py tests/unit/test_ai_backtest_route.py tests/unit/test_auth_config.py` | 82 passed, 6 warnings |
| AI regression suite | `cd ai && python -m pytest -q tests/test_audit.py tests/test_audit_postgres.py tests/test_api.py tests/test_graph_e2e.py` | 78 passed, 1 skipped, 2 warnings |
| Service DB regression | `cd service_db && python -m pytest -q tests/test_sql_migration.py` | 9 passed |
| DE regression suite | `cd DE && python -m pytest -q tests/test_sql_migration.py tests/test_ai_prompt_retention.py tests/test_airflow_dag_import.py` | 23 passed, 2 skipped |
| Replay scripts | `python -m py_compile service_db/scripts/verify_fixed_migration_replay.py service_db/scripts/run_fixed_migration_replay.py` | 통과 |
| Workflow YAML 정적 검증 | `python - <<'PY' ... yaml.safe_load(...) 및 workflow 계약 assert ... PY` | 통과 |
| Diff integrity | `git diff --check` | 통과 |
| QA artifact | `backend/docs/p0-local-qa-report.json` | focused adversarial matrix와 BLOCKED/SKIPPED 증거 기록 |

최종 통합 리뷰: **CLEAR / APPROVE** (`84-P0FinalReviewR4`)

## 제한 및 운영 주의

- 로컬에서 `AI_PROMPT_RETENTION_TEST_DSN`이 없으면 PostgreSQL purge integration은 명시적으로 skip된다. CI workflow는 disposable `ai_prompt_retention_test_ci` DSN을 이 환경 변수에 설정하므로 해당 integration을 실제 실행한다.
- 외부 signer/SBOM/trusted root가 없는 환경에서 replay runner는 SQL 실행 전 `BLOCKED` artifact를 만들고 종료한다.
- production/staging raw-on, customer canary, Gate B 실제 활성화는 외부 signer/revocation/WORM 증거가 준비될 때까지 금지한다.
- production enable 시 signed admission의 실제 `expiry`, `audience`, `evidence_id`, `deployment_revision`, `key_version`을 릴리스 값으로 주입해야 한다.
- Gate B HMAC secret은 OAuth secret과 분리하고 rotation 절차를 따른다.
- 이번 P0 구현에서는 커밋/푸시하지 않았다.
