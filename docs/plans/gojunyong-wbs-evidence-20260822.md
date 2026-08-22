# 고준영 담당 WBS 로컬 증적 — 2026-08-22

원본 계획은 [공유 WBS](https://docs.google.com/spreadsheets/d/1V7SnG_x-cLIFbrSurDIadtx5GCY9HfL9jRqdyAl70Ks/edit) `2_WBS` 시트다. 이 문서는 원본 WBS의 상태·승인자·증적 URI를 수정하지 않는 로컬 구현 증적이다.

| WBS ID | 계획 종료 | 구현·검증 결과 | 증적 등급 | 남은 승인 증적 |
| --- | --- | --- | --- | --- |
| EV-GATE-01 | 2026-08-13 | `scripts/evaluate-release-trust.mjs`가 AI API/리서치, 백테스트 지표, 인증·보고서·배포, 프런트 계약을 고정 순서로 실행하고 첫 실패를 그대로 반환한다. PR/push CI의 `release-trust` job이 이 명령을 실행한다. | S — `node --test scripts/evaluate-release-trust.test.mjs` 6 PASS, `node scripts/evaluate-release-trust.mjs` PASS | GitHub Actions 실행 URI, 독립 검토자·검토일 |
| RMP-ENV-01 | 2026-08-20 | 배포 워크플로가 Python 3.11 venv에 `backtest_module`, `backend`, `ai`를 동일 editable dependency graph로 설치하고 `backtest_module`·`quantstats` import를 확인한다. | S — deploy 계약을 포함한 backend 156 PASS | 실제 배포 job 로그 및 서버에서의 import/백테스트 실행 결과 |
| P0-BE-01 | 2026-08-22 | Redis 일시 장애의 `/api/v1/auth/me` 응답이 503, `redis_read_failed`, 고정 envelope이며 password marker와 session ID를 노출하지 않는지 고정했다. 장애 회복 뒤 같은 세션으로 재시도하면 200인 것도 확인한다. | S — auth route 계약을 포함한 backend 156 PASS | CI URI, 독립 검토자·검토일; 실제 인증 smoke는 별도 운영 증적 |
| P0-BE-02 | 2026-08-27 | AI `/readiness`가 persistent job store, `021_ai_analysis_jobs` 스키마 서명, `ai-mvp.v1` 계약과 rule-draft signer를 모두 확인하기 전에는 503을 반환한다. 이유 값은 bounded code만 공개한다. | S — AI API/contract 108 PASS | CI URI, 실제 DB migration·durable store·AI contract·signer probe 로그, 독립 검토자 |
| RMP-REPORT-01 | 2026-08-26 | mutable AI report route와 daily digest API는 410으로 퇴역했고 audit·LLM을 열지 않는다. 전략별 다이제스트 구독 GET/POST/DELETE도 인증·DB 접근 전에 410을 반환한다. 보관 보고서는 backend-owned `/api/v1/reports` immutable snapshot 계약만 사용한다. | S — AI API 30 PASS, backend immutable report/store·retired route 20 PASS | CI URI, 기존 구독 데이터 보존·권한·보관 정책 승인, 독립 검토자 |
| P0-REL-01 | 2026-08-31 | 실제 배포는 실행하지 않았다. WBS가 요구하는 release ID, 실제 deploy log, Google OAuth smoke, rollback 결과와 제2 검토 증적은 외부 환경에서만 생성할 수 있다. | R/O/C 대기 — 로컬 fixture·mock을 운영 release 증적으로 대체하지 않음 | 서버 배포 권한, 승인된 rollback 절차·release ID, GitHub Actions URI, 검토자 2명 |
| P1-SEC-01 | 2026-09-01 | Google callback이 이전 cookie session을 새 session 발급 뒤 폐기한다. OAuth start는 trusted loopback Vite proxy가 append한 최종 forwarded peer만 사용하며, Redis Lua로 count+TTL을 원자화한다. TTL·CSRF·logout revoke는 유지한다. | S — auth core/route 129 PASS, 전체 backend gate 156 PASS | CI URI, Redis 운영 지표·실제 로그인/로그아웃 E2E, 프록시 client-IP smoke, 검토자 |
| P1-OBS-01 | 2026-09-03 | allowlisted request ID, route template, numeric timing만 관측성 로그에 남기며 path/query/cookie/body 값은 제외한다. 이 회귀를 release gate에 편입했다. | S — `test_runtime_perf.py` 포함 backend 156 PASS | trace sink·sampling 설정, 배포 로그/대시보드, PII 검토 승인 |
| P1-CI-01 | 2026-09-05 | deploy workflow가 offline release-trust 완료를 선행 조건으로 삼고, 기동 뒤 `/ai-api/readiness`의 durable store·migration·AI contract·rule-draft signer가 모두 ready인지 확인한다. | S — static workflow 계약 포함 backend 156 PASS | 실제 GitHub Actions deploy/rollback 실행 URI, artifact provenance, 승인된 rollback 결과 |
| P2-OPS-01 | 2026-09-15 | 용량·p95·오류 예산·비용·freshness는 fixture나 로컬 단위 테스트로 증명할 수 없으므로 측정값을 만들지 않았다. runtime metric/redaction 계약만 release gate에 남겼다. | R/O/C 대기 — 운영 부하 시험 증적 없음 | 승인된 staging/production-like 부하 환경, 고정 데이터 기준일·budget, 측정 artifact·검토 승인 |

## 실행 기록

```text
node scripts/evaluate-release-trust.mjs
  ai-api-and-research-contracts: 108 passed
  backtest-metric-contracts: 44 passed
  backend-auth-report-and-deploy-contracts: 156 passed
  frontend-production-build-and-contracts: 34 passed, typecheck/build passed
  exit: 0

ai/.venv/bin/python -m ruff check --select E4,E7,E9,F \
  ai/ai_graph/api.py ai/tests/test_api.py \
  backend/app/api/routes/auth.py backend/app/api/routes/email_reports.py \
  backend/app/core/config.py backend/app/services/session_store.py \
  backend/tests/unit/test_auth_core.py backend/tests/unit/test_auth_routes.py \
  backend/tests/unit/test_fe_contract_routes.py backend/tests/unit/test_deploy_workflow_contract.py \
  backend/tests/integration/test_track4_email_server_qt_db.py
  exit: 0

git diff --check
  exit: 0
```

## 운영 경계

이 검증은 live DB, Redis, AOAI 또는 배포 서버를 호출하지 않는 로컬 계약 검증이다. 따라서 S 증적만 생성한다. CI(R), 배포/실제 서비스(O), 승인 기록(C)는 아직 이 문서로 대체되지 않으며 WBS 원본의 `대기` 상태도 변경하지 않았다.
