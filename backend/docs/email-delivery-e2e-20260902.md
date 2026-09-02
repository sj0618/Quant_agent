# 리포트 이메일 발송 경로 E2E 검증 메모 (2026-09-02)

## 결론
로컬 하네스(임베디드 PostgreSQL + service_db 마이그레이션 011~025 + 가짜 Brevo HTTP 서버)에서
`자연어 → /ai-api/analysis-jobs → ready 리포트 → POST /api/v1/runs → /complete → app.strategy_email_report →
app.email_delivery_history(PENDING) → EmailDeliveryWorker.run_once() → Brevo API HTTP POST → SENT → /me/email-deliveries →
resend(202) → 재발송` 전 구간이 통과했다. 재시도(500 → RETRY_PENDING → SENT), 영구 실패(400 → FAILED),
중복 완료(/complete ×2 → 배송 행 1개, 발송 1회)도 확인했다.

## 운영 서버에서 이메일이 한 번도 나가지 않던 이유 (원인 순서대로)
1. AI job이 `ready`에 도달하지 못했다 — `ai/README_AI.md`의 "운영 raw-query 경로" 항목 참고(실행 스펙 클래스 불일치).
2. `POST /api/v1/runs`·`/runs/{id}/complete`가 production에서 410 `public_create_retired`였다. 47ae545가 닫고, 94b3afe가
   `POST /analysis-jobs`만 되살렸으며, 9e616bf 계열 FE는 분석 완료마다 두 writer를 호출했다(머지 순서 누락).
   `complete_analysis_run_from_db`가 `app.strategy_email_report`의 유일한 writer이자 유일한 이메일 enqueue 지점이라
   리포트 저장·이메일 enqueue가 전무했고, FE에는 "분석 결과를 리포트로 저장하지 못했습니다" 배너가 매번 떴다.
   → 두 route는 이제 "소유한 완료 job의 영속화"로 허용된다(session + CSRF + `aiJobId`가 호출자 소유의 완료 job). 
   `aiJobId` 없음 422, 모르는 job 404, 미완료 409.
3. 서버에 EMAIL_* 설정이 없고(`EMAIL_DELIVERY_ENABLED=false`, rollout disabled, BREVO 키/발신자 없음) 워커 프로세스도 없었다.
   `deploy.yml`은 워커를 띄우지 않았다 → `EMAIL_DELIVERY_WORKER_ENABLED=true`일 때만 manage 스크립트로 start/check 하도록 추가.
   서버에는 `backend/.venv`가 없고 `ai/.venv`만 있으므로 manage 스크립트가 `ai/.venv/bin/python`으로 폴백한다.

## 이번에 고친 이메일 파이프라인 결함
- 재발송: `POST /api/v1/reports/{id}/resend`는 deterministic delivery_id + `ON CONFLICT DO NOTHING` 때문에 이미 SENT/FAILED/CANCELLED인
  행에는 아무 일도 하지 않고 204를 돌려줬다. 이제 터미널 상태 행을 PENDING(attempt_count 0)으로 재큐잉하고 **202**를,
  이미 PENDING/RETRY_PENDING/PROCESSING이면 **204**를 반환한다(`email_outbox.requeue_delivery`, `email_delivery.resend_report_completed_delivery`).
- Brevo 샌드박스: `X-Sib-Sandbox: drop`이 메일 커스텀 헤더(JSON body)에 들어가 있어 실제로는 발송됐다. HTTP 요청 헤더로 옮겼다.
- 워커: `_process_claim`이 AppError만 잡아 DB/드라이버 예외가 루프를 죽였다. 클레임 단위 예외 경계(`claim_lost` 이벤트 + best-effort
  `mark_retry_pending`)와 `run()` 루프 생존(`worker_error`/`run_once_failed` 후 poll 간격만큼 대기)을 추가했다.
- 메일 링크: `{EMAIL_PUBLIC_BASE_URL}/reports/{uuid5}`는 FE가 AI job id(`ai-job:...`)로만 해석해 열리지 않았다.
  `/me/email-reports/{report_id}`(백엔드 제공 소유자 리포트 화면)로 바꿨다.
- `run_email_delivery_worker.py --check`: Redis 연결 실패 시 raw traceback 대신 `Redis readiness check failed`로 종료한다.
- 재발송 보호(적대적 리뷰 반영): 재큐잉은 마지막 이벤트 후 `EMAIL_RESEND_COOLDOWN_SECONDS`(기본 600초)가 지나야 하고,
  재큐잉 시 수신자 주소와 렌더된 본문을 최신 값으로 갱신한다(주소 변경 후 재발송이 영원히 `recipient_changed`로 취소되던 문제).
  `submission_status` 메타데이터가 없는 레거시 행은 `status` 컬럼으로 판정한다.
- 워커 루프: `AppError`(DB 계층이 드라이버 오류를 `db_query_failed`로 감싼다)도 루프를 죽이지 않고 `worker_error` 후 poll 간격만큼 대기한다.
- hosted-pages 정책: 메일 링크 대상 `/me/email-reports/{id}`를 200 SPA 라우트로 등록했다(이전엔 404 상태의 셸).
- 배포: `/trust` smoke를 `/terms`로 바꿨다(`/trust`는 FE 화면이 없어 404 정책으로 옮김). 워커 시작 여부는 `Settings.email_delivery_worker_enabled`로 읽고, `check` 실패는 경고만 남긴다.

## 운영 전제 (코드가 아니라 설정)
- `DATABASE_URL`과 `TRADING_DATA_DATABASE_URL`은 같은 `qt_db`를 가리켜야 한다. 완료 경로는 trading engine으로 이메일 행을 쓰고,
  resend/이력 조회는 main engine으로 읽는다(서버는 현재 동일 DB).
- allowlist/production rollout validator는 non-loopback DB/Redis 호스트, Redis logical DB 11, `@qt-agent.kro.kr` 발신자,
  https 공개 URL, unsubscribe 설정을 요구한다. 서버 DSN은 공개 호스트명을 쓰므로 통과한다. 레거시 `EMAIL_LOCAL_LIVE_SEND_ENABLED=true`
  경로는 같은 allowlist 모드를 이 검사 없이 만든다(로컬 하네스가 쓰는 경로) — 운영에서는 쓰지 않는다.
- 사용자 36명 중 35명이 `daily_report_email=true`이므로 **첫 발송은 반드시 `EMAIL_ROLLOUT_MODE=allowlist`** 로 운영자 주소만 허용해서 한다.
- 워커 런타임 env는 `~/.bashrc`/`.env`에서 온다. 배포 워크플로는 EMAIL_* 값을 주입하지 않는다.
- 남은 알려진 결함: `app.email_delivery_outbox` 테이블(마이그레이션 018)은 코드가 쓰지 않는다(큐 상태는
  `app.email_delivery_history.metadata_jsonb`). 이메일 본문은 제목·요약·링크만 담고 AI `email_projection`은 쓰이지 않는다.
  `EMAIL_PROVIDER=resend`는 검증기가 막아 실제로 쓸 수 없다.

## 로컬 검증 명령
```bash
cd backend && python -m pytest -q tests/unit/test_email_track4.py tests/unit/test_email_pipeline_fixes.py \
  tests/unit/test_run_email_delivery_worker.py tests/unit/test_fe_contract_routes.py
```
서버 DB를 쓰는 통합 테스트는 `TRACK4_EMAIL_SERVER_WRITE_INTEGRATION=1` opt-in(`tests/integration/test_track4_email_server_qt_db.py`).

## 서버(qt_db) 통합 테스트 갱신 (2026-09-02)
- `tests/integration/test_track_c_server_run_report_qt_db.py`·`test_track4_email_server_qt_db.py`는 요청 본문에 결과를 싣던 옛 계약을 전제하고 있어
  현재 계약(완료 결과는 `analysis_job_store`의 job에서 읽고, `/runs`·`/complete`는 `aiJobId`만 받음)으로 다시 썼다. 가짜 job store에 `aiJobId → owner`를 등록해 쓴다.
- node3 결과: track-c 3 passed, track4 1 passed(clean env + 운영 DSN). `reader` 계약(`ArchivedReportDetail`, extra=forbid)에는 `marketBrief`/`performance`가 없다.
- **주의**: 완료 1건마다 `app.analysis_result`(immutable 트리거) 1행과 그 소유자 `app.users` 1행이 영구히 남는다(`ON DELETE RESTRICT`).
  opt-in 통합 테스트와 운영 smoke는 그래서 완전 자가정리가 불가능하다 — 합성 사용자 행(`track2-report-remediation-*`, `e2e-smoke-*`)이 누적된다.
