# 코드 리뷰 수정 보고서

작성일: 2026-07-17
범위: 기존 아키텍처를 유지할 수 있는 코드 리뷰 결함 수정

## 반영한 수정

- 백테스트 요약의 `total_commission`, `total_tax`, `total_slippage`를 비용 비율이 아닌 거래별 실현 금액으로 저장한다. 거래 비용 또는 원시 시가가 불완전한 경우 비율을 금액으로 오인하지 않고 `null`로 둔다.
- 백테스트 요청의 프롬프트 길이, 실행 시간, 메모리 상한을 기존 Pydantic 요청 경계에 추가했다. 기본값과 공개 필드명은 유지한다.
- L1/L2 retrieval 결과가 관련 문서를 모두 포함하도록 다양성 계약을 복원했다. unsafe 후보는 후보 ID별 AST fallback 사유를 남긴다.
- PDF ingest와 crawler import의 상태 변경 POST에 기존 origin 검증과 세션 저장소의 조건부 CSRF 토큰 검증을 재사용했다. 새로운 인증 시스템이나 미들웨어 토폴로지는 추가하지 않았다.
- DE 설정 보안 테스트가 존재하지 않는 `DE/main.py`를 읽지 않고 실제 설정 모듈 `DE/quant_agent/data/config.py`를 검사하도록 수정했다.

## 아키텍처 변경 없이 해결하지 않은 항목

다음 항목은 현재 요청의 "아키텍처 변경 금지" 제약 때문에 구현하지 않았으며, 명시적 승인 전까지 BLOCKED로 유지한다.

| 심각도 | BLOCKED 항목 | 현재 근거 | 필요한 승인/결정 |
|---|---|---|---|
| CRITICAL | 생성 Python의 OS subprocess 격리 경계 | `ai/ai_graph/nodes/backtest.py:320-327` `_execute_candidate_code`가 AST 검사 뒤 동일 프로세스에서 `exec`하고, `backend/app/services/ai_backtest_runtime.py:265-313` `SandboxedBacktestExecutor`는 부모 환경을 복사한 subprocess와 rlimit만 설정한다. | 별도 sandbox/컨테이너/권한·네트워크 정책과 운영 비용 승인 |
| HIGH | FE mock/compat 라우트의 운영 노출·소유권 경계 | `backend/app/main.py:89-105`가 모든 환경에서 `fe_contract.router`를 포함하고, `backend/app/api/routes/fe_contract.py:125-144`의 전략 변경 POST/PATCH가 현재 사용자 검증 없이 `fe_contract_store`를 호출한다. | 운영 환경 비노출 방식과 사용자 소유권 모델 승인 |
| HIGH | `/ai/daily-digest` 인증 주체 | `ai/ai_graph/api.py:560-566` `create_daily_digest`에는 `Depends(require_user)`가 없고, `ai/docs/email-digest-be-requirements.md`는 BE 예약 호출의 인증 전달 계약을 정의하지 않는다. | 세션 전달 또는 BE→AI 서비스 인증 계약 승인 |
| HIGH | 배포 시 backend Redis 세션과 AI 인증 토폴로지 | `.github/workflows/deploy.yml`의 기동 대상은 AI/FE이고 `ai/ai_graph/auth.py:38-65`는 `qa_session` Redis 공유 세션을 전제로 한다. backend 세션 발급·공유 경로가 배포 구성에 없다. | 서비스 간 인증·세션 공유 토폴로지 승인 |
| HIGH | `backtest_module` 외부/내부 구현 중복과 import 소유권 | `backtest_module/backtest.py:612`에 외부 `BacktestEngine`, `backtest_module/backtest.py:1048`에 외부 `run_backtest`, `backtest_module/backtest_module/backtest.py:628`에 중첩 `BacktestEngine`, `backtest_module/backtest_module/backtest.py:1270`에 중첩 `run_backtest`가 각각 존재한다. `import backtest_module.backtest`는 외부 경로를, `import backtest_module.backtest_module.backtest`는 중첩 경로를 로드하며 두 `BacktestEngine` 심볼은 서로 다르다. 패키지 설치 시 canonical import 소유권은 별도 결정이 필요하다. | 단일 패키지 소유권 및 호환 import 경로 승인 |
| MEDIUM | 외부 report resolver의 사용자 소유권 식별자 부재 | `ai/ai_graph/api.py:44` `ReportResolver`는 `report_id`만 받고, `ai/ai_graph/api.py:549-553` resolver 호출에도 `user_id`가 전달되지 않는다. | resolver 공개 계약에 사용자 식별자를 추가할지 승인 |
| MEDIUM | 세션 TTL과 CSRF TTL 정책 불일치 여부 | `backend/app/core/config.py:70-72`의 `auth_session_ttl_seconds`는 8시간, `auth_csrf_ttl_seconds`는 1시간 기본값이며 `backend/app/services/session_store.py:75-87`에서 두 Redis 키에 독립 TTL을 설정한다. 갱신·회전 계약은 확인되지 않았다. | 보안 정책 및 갱신/회전 수명 승인 |

## 검증

명령과 보존된 증거는 `backend/docs/code-review-remediation-qa.json`에 기록했다.

```text
cd backend && python -m pytest -q tests/unit/test_ai_backtest_runtime.py tests/unit/test_ai_backtest_subprocess_runner.py tests/unit/test_pdf_temp.py tests/unit/test_ai_backtest_flow.py tests/unit/test_ai_backtest_repository.py tests/unit/test_auth_config.py
cd ai && python -m pytest -q tests/test_retrieval.py tests/test_prompt_schema_contract.py tests/test_ai_graph_backtest_module_integration.py tests/test_daily_digest.py tests/test_graph_e2e.py
cd DE && python -m pytest -q tests/test_config.py
python -m ruff check DE/tests/test_config.py ai/ai_graph/nodes/backtest_code.py ai/ai_graph/retrieval/search.py ai/tests/test_prompt_schema_contract.py ai/tests/test_retrieval.py backend/app/api/routes/reports_pdf_temp.py backend/app/schemas/ai_backtest.py backend/app/services/ai_backtest_subprocess_runner.py backend/tests/unit/test_ai_backtest_subprocess_runner.py backend/tests/unit/test_ai_backtest_runtime.py backend/tests/unit/test_pdf_temp.py
python -m py_compile DE/tests/test_config.py ai/ai_graph/nodes/backtest_code.py ai/ai_graph/retrieval/search.py backend/app/api/routes/reports_pdf_temp.py backend/app/schemas/ai_backtest.py backend/app/services/ai_backtest_subprocess_runner.py backend/tests/unit/test_ai_backtest_subprocess_runner.py backend/tests/unit/test_ai_backtest_runtime.py backend/tests/unit/test_pdf_temp.py
git diff --check
```

결과: Backend `114 passed, 61 warnings`, AI `40 passed`, DE `7 passed`, Ruff/py_compile/diff-check 통과.
Boundary report QA evidence: `backend/docs/code-review-boundary-qa.json`.

로컬 환경에서 실제 PostgreSQL/Redis/OAuth/AOAI 외부 연동은 실행하지 않았다. 외부 연동과 위 BLOCKED 항목은 해당 승인·환경이 제공되기 전까지 성공으로 주장하지 않는다.
