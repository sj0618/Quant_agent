# 전체 플로우 E2E 검증 보고 — 자연어 입력 → 리포트 → 저장 → 이메일 (2026-09-02)

기준: `main` 576ce46(= 배포 revision), 작업 브랜치 `claude/e2e-flow-validation-945b9e`.
검증 대상 플로우: `자연어 입력 → /ai-api/analysis-jobs → 9-node graph → ReportBundle → FE 표시 →
POST /api/v1/runs → /runs/{id}/complete → app.strategy_email_report → app.email_delivery_history(outbox) →
email worker → Brevo API → SENT → /me/email-deliveries → resend`.

## 1. 결론

| 구간 | 검증 전(576ce46, 운영 서버) | 검증 후(이 브랜치, 로컬 하네스) |
|---|---|---|
| 자연어 접수·검증 | 공백 쿼리 201 후 실패, 길이 무제한 | 공백 422, 2000자 상한, 잘못된 JSON/필드 422, 5xx 없음 |
| 핵심 로직(운영 raw-query 경로) | **운영 job 20건 전부 실패**(9건은 노드 실행 전 `contract_shape_error`) | 명시 규칙 → `ready`, 실행 불가 입력 → `need_clarification` |
| 리포트 생성 | mock에서 정상(web 12/email 4 섹션) | 동일 |
| 리포트 저장(서비스 DB) | production에서 410 `public_create_retired` → 저장 0건, FE 오류 배너 | 201/200, `strategy_email_report` 1행 |
| 이메일 enqueue·발송 | enqueue 지점이 410 뒤에 있어 0건, 워커 없음, EMAIL_* 미설정 | PENDING → 워커 → 가짜 Brevo HTTP POST → SENT |
| 재시도·중복·부분 실패 | 재발송이 무동작 204, 워커가 DB 예외에 사망 | 500→RETRY_PENDING→SENT, 400→FAILED, /complete×2→행 1개·발송 1회, 재발송 202 재큐잉 |

**전체 플로우는 로컬 실물 대체 환경(임베디드 PostgreSQL + 실제 마이그레이션 + 가짜 Brevo HTTP 서버)에서 처음부터 끝까지 동작한다.**
운영에서 실제 메일이 나가려면 코드 배포 외에 서버 환경변수(EMAIL_*)와 Brevo 키가 필요하다(§6).

## 2. 실행한 시나리오

로컬 하네스(`scratchpad/harness/e2e_local.py`, 저장소 밖): 시나리오마다 별도 프로세스로 `combined_main:app`(백엔드+AI)을
in-process로 띄우고, 세션은 백엔드 테스트의 `FakeRedis`에 `AuthSessionStore.create_session`으로 만들었다.
AI는 `AI_LLM_PROVIDER=mock`, 데이터는 저장소 fixture, 이메일 provider는 `BREVO_API_BASE_URL`을 로컬 스텁으로 돌렸다.

| 시나리오 | 내용 | 결과 |
|---|---|---|
| happy | NL 쿼리 → ready → runs/complete → PENDING → `run_once` → 스텁 POST 1회 → SENT → 이력 조회 → resend 202 → 2번째 POST | PASS |
| retry | 첫 응답 500 → RETRY_PENDING(attempt 1, available_at +1s) → SENT(attempt 2); 400 → FAILED | PASS |
| duplicate | /complete 2회 → 같은 reportId, 배송 행 1개, 발송 1회 | PASS |
| production-410 | APP_ENV=production에서 이전 410 재현 → 수정 후에는 admission readiness(503)만 남음 | PASS(재현) |
| invalid-input | `{}`, `""`, `"   "`, 잘못된 JSON, 미지 필드, 20,000자 → 모두 422; `"안녕"` → need_clarification | PASS |
| persistent store | `AI_JOB_STORE=persistent`(로컬 PG) happy 경로 | PASS |
| production-raw | production 설정 + 결정론 파서 경로로 bare query → ready → 저장 → 발송 (Phase 3 추가) | 결과는 §5 |

기존 테스트(가상환경): backend unit 407 passed, AI 870 passed/12 skipped/1 failed(§5), backtest_module 42, service_db 57,
DE migration 12, `compileall`·ruff(CI 선택 규칙) 통과, FE `npm run test`(41 node tests + tsc + vite build) 통과.

## 3. 발견한 문제와 발생 지점

| ID | 단계 | 지점 | 증상 | 근본 원인 |
|---|---|---|---|---|
| SR-01/AI-ROOT | 핵심 로직 | `ai/ai_graph/api.py` runner → `graph.run_analysis` → `schemas.validate_execution_spec` | 운영 raw-query job이 ~1초 만에 `contract_shape_error`로 실패(20건 중 9건) | `research_contract`와 `schemas`가 같은 모양의 실행 스펙 클래스를 따로 정의. 봉인된 `CanonicalRuleV1` 인스턴스를 다른 모듈의 TypeAdapter가 외래 클래스로 거부 |
| AIR-05 | 핵심 로직 | `api.py` `_build_analysis_runner_with_audit` | 실행 불가 입력("fgdgd", 후보 없음)이 FAILED | 리서치 결과가 non-executable이면 `StrategyResearchError`로 실패 처리 |
| BPE-01/PDV-01 | 저장 | `backend/app/api/routes/fe_contract.py` | production에서 `/api/v1/runs`·`/complete` 410 → 저장·이메일 0건 | 47ae545 퇴역 후 94b3afe가 `/analysis-jobs`만 되살리고 9e616bf FE가 두 writer를 다시 호출(머지 순서 누락) |
| FE-01 | 출력 | `fe/src/pages/AppPage.tsx` | 분석마다 "리포트 저장 실패" 배너, 매 폴링 재시도 | 410을 종결 오류로 인식하지 않음 |
| BPE-03 | 이메일 | `backend/app/db/email_outbox.py` | 재발송 204 무동작 | deterministic delivery_id + `ON CONFLICT DO NOTHING` |
| BPE-04 | 이메일 | `email_provider.py` | `BREVO_SANDBOX_MODE=true`여도 실제 발송 | 샌드박스 마커를 HTTP 헤더가 아닌 메일 커스텀 헤더에 넣음 |
| BPE-05 | 이메일 | `email_delivery_worker.py` | DB/드라이버 예외에 워커 루프 사망, PROCESSING 클레임 방치 | AppError만 catch |
| BPE-11 | 이메일 | `email_templates.py` | 메일 링크 `/reports/{uuid5}`가 FE에서 안 열림 | FE `/reports/:id`는 AI job id만 해석 |
| SR-02/BPE-06 | 운영 | `.github/workflows/deploy.yml` | 워커 프로세스 없음 | 배포가 워커를 띄우지 않음, manage 스크립트 기본 python 경로(backend/.venv) 부재 |
| SR-03 | 운영 | 서버 env | EMAIL_* 전부 미설정 | 설정 부재(코드 아님) |
| AIR-01/02, FE-05 | 입력 | `api.py`, `StrategyInputPanel.tsx` | 공백 쿼리 201, 길이 무제한 | 검증 누락 |
| AIR-03 | 로그 | `jobs.py fail_job` | 실패 job의 stages가 interpreting..debate를 succeeded로 표기 | polling_stage를 항상 FINALIZING으로 고정 |
| AIR-06 | 운영 | `analysis_capacity.py` | 대기 job이 10분 뒤 실패 | 대기 600s < deadline 1800s |
| FE-04 | 출력 | `fe/scripts/production-gateway.mjs` | SSE 스트림 끊김 가능 | 게이트웨이 timeout 15s == keepalive 15s |
| 테스트 드리프트 | - | `backend/app/api/routes/pages.py` vs `fe/src/config/routes.ts` | backend 단위 테스트 1건 실패 | FE `/dev/email-template` 잔존, `/trust` 화면 부재 |

## 4. 변경한 파일과 핵심 수정

- AI: `ai/ai_graph/schemas.py`(validate_execution_spec JSON round-trip), `api.py`(runner dict 전달, need_clarification 엔벨로프, 공백 422·2000자), `jobs.py`(실패 단계 진실성), `analysis_capacity.py`(1860s), `execution_boundary.py`(인증 영속화 경계 등록, historical-report-read 경로 수정). 테스트 `ai/tests/test_raw_query_job_path.py`(신규) 외.
- Backend: `fe_contract.py`(410 제거, create는 `aiJobId` 소유 완료 job 필수), `contract_policy.py`, `email_outbox.py`(requeue), `email_delivery.py`(resend), `email_reports.py`(202/204), `email_provider.py`(샌드박스 헤더), `email_delivery_worker.py`(예외 경계), `email_templates.py`(링크), `pages.py`, `scripts/run_email_delivery_worker.py`(Redis 오류 정제), `scripts/manage_email_delivery_worker.sh`(python 폴백). 테스트 `test_email_pipeline_fixes.py`(신규), `test_fe_contract_routes.py`, `test_track_c_contract_policy.py`, `test_deploy_workflow_contract.py`, `test_run_email_delivery_worker.py`, `test_backend_hosted_pages.py`.
- FE: `AppPage.tsx`(410 종결), `EmailHistoryTimeline.tsx`(다시 보내기), `StrategyInputPanel.tsx`(maxLength), `routes.ts`/`App.tsx`(dev 라우트 제거), `EmailTemplatePreviewPage.tsx` 삭제, `production-gateway.mjs`(65s).
- 적대적 리뷰(Fable) 반영: 배포 smoke·server-health의 `/trust` 확인을 `/terms`로 교체(삭제된 라우트 때문에 배포가 롤백 루프에 빠질 뻔함), 재발송 쿨다운(`EMAIL_RESEND_COOLDOWN_SECONDS`)·재큐잉 시 수신자/본문 갱신, 워커 루프가 `AppError`도 생존, `/me/email-reports/{id}` hosted 라우트 200, 워커 게이트를 Settings로 판정하고 check 실패는 경고 처리.
- Ops/Docs: `.github/workflows/deploy.yml`(워커 start/check 게이트), `README.md`(이메일 운영 계약, 큐 대기 1860), `ai/README_AI.md`, `backend/docs/email-delivery-e2e-20260902.md`, `fe/README.md`, `docs/plans/*`(경계 계약 갱신).

## 5. 검증 결과 요약

- 회귀: §2 수치. AI 스위트의 유일한 실패 `test_backtest_optimization.py::test_parallel_evaluation_stops_at_a_wave_boundary_when_cancelled`는
  변경 전 HEAD를 별도 worktree로 실행해도 동일하게 실패(Windows 프로세스 풀 취소 경로, CI 선택 목록 밖) → 이 변경과 무관.
- 하네스 재실행(수정 후): happy 12/12, retry 10/10, duplicate 7/7, production-410 6/6(410 → 이제 503/404: 관리 admission만 남음), invalid-input 6/6,
  persistent 13/13, **production-raw 10/10**(production 설정 + 결정론 파서로 bare query → ready → 201/200 → PENDING → 워커 → 스텁 POST → SENT; aiJobId 없음 422, 미지 job 404).
- 적대적 리뷰(Fable, 보안·동시성): 차단 1건(`/trust` smoke) 포함 위 §4 반영. 소유권·CSRF·Origin·재큐잉 vs PROCESSING 클레임·CancelledError 처리·AI 엔벨로프 비노출은 "검증됨 안전".
- **node3 서버(별도 checkout `~/mvp_sp1/e2e-check`, python3.11 venv, clean env)**: compileall·ruff CI 통과, backtest 42, service_db 57(+3 skip), DE 12,
  **AI 872 passed/11 skipped(로컬 Windows 실패 1건도 Linux에서는 통과)**, **backend unit 408 passed**, FE `npm ci`+`npm run test` 통과.
  주의: 서버 로그인 셸의 `~/.bashrc`가 운영 AUTH_/EMAIL_/AI_ 값을 export하므로 backend 설정 테스트는 반드시 `env -i`로 돌려야 한다(그렇지 않으면 27건이 환경 때문에 실패).
- PR #86 CI(Python checks, Frontend checks, Offline release-trust gate, ai-logging) 모두 통과.
- qt_db 통합 테스트(opt-in, node3, clean env + 운영 DSN): track-c 3 passed, track4(email outbox → 워커 → 가짜 provider → SENT/재시도/취소) 1 passed.
- **배포**: PR #86 머지 → `Deploy to SSH Server` 성공(run 33639267553). node3 `/ai-api/api-status.deployment_revision = 608b2f1`(머지 커밋), job_store persistent,
  `/readiness`·`/ai-api/readiness` ready, 공개 라우트 `/`·`/terms`·`/me/email-reports/{id}` 200, `/trust`·미지 경로 404,
  배포 로그에 `email worker disabled (EMAIL_DELIVERY_WORKER_ENABLED != true)`(게이트 정상 동작, 운영 env 미설정이라 워커 미기동).
- 배포 사이트 smoke(실제 AOAI + qt_db, 합성 사용자): 결과는 아래 "배포 사이트 smoke" 절.

## 6. 남은 문제 · 외부 설정 · 수동 확인

1. **운영 이메일 활성화(설정, 코드 아님)**: 서버 `~/.bashrc` 또는 `~/mvp_sp1/quant-proj/.env`에 다음을 넣고 배포(README "이메일 발송 운영 계약").
   `EMAIL_DELIVERY_ENABLED=true`, `EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED=true`, `EMAIL_DELIVERY_WORKER_ENABLED=true`,
   `EMAIL_ROLLOUT_MODE=allowlist`, `EMAIL_LOCAL_RECIPIENT_ALLOWLIST=<운영자 주소>`, `EMAIL_PROVIDER=brevo`, `BREVO_API_KEY`,
   `BREVO_SENDER_EMAIL=<mailbox>@qt-agent.kro.kr`, `BREVO_SENDER_NAME`, (`BREVO_SANDBOX_MODE=true`로 1차 dry-run),
   `EMAIL_PUBLIC_BASE_URL=https://qt-agent.kro.kr`(이미 있음), `EMAIL_UNSUBSCRIBE_*`(이미 있음), `REDIS_URL` DB 11(이미 있음).
   첫 발송은 반드시 allowlist(사용자 35명이 수신 동의 상태).
2. 배포 후 수동 확인: `/health`의 `email_*` 필드, `.run/email-worker.log`, `app.email_delivery_history`에 SENT 1건, 수신함.
3. 운영 데이터 의존 실패(`data_required` 3건, `QueryCanceled`/OOM Data 노드)는 이번 범위 밖 — 데이터 적재·쿼리 예산 문제.
4. 알려진 미해결: `app.email_delivery_outbox`(018) 미사용 테이블; AI `email_projection` 미사용(메일은 제목·요약·링크만);
   `EMAIL_PROVIDER=resend` 사용 불가; 두 실행 스펙 클래스 계층 통합은 리팩터링 과제; 서버 로그가 배포마다 truncate됨;
   런타임 env가 `~/.bashrc`에 있어 비로그인 셸에서는 보이지 않음.
5. 배포는 PR → main 머지로 자동 실행된다. 이 변경은 production 쓰기 경로를 다시 열므로 머지 전 사람의 승인이 필요하다.

## 7. 2차 작업: 실행 시간 1분 목표 (2026-09-02 저녁)

배포 후 실사용 job(job_490c3cc69941)이 Data 노드 **875초·RSS 21GB** 뒤 Backtest 노드에서 `raw_execution_unavailable`로 실패했다. 프로파일(node3 실측):
- Data 노드는 PIT 종목 1,717개 × **5년**(1,222세션) × TA 4패밀리 × DART를 dict 190만 개(≈10KB/행)로 적재했다. 12개월만 돌려도 115초/4.1GB.
- 스크리닝은 이미 DB 단일 날짜 조회(9초)라 가설 1은 사실상 구현돼 있었고, 지표도 `feature.ta_*`에서 읽는다(가설 3). 실제 지렛대는 **창 길이(가설 2)와 종목 수**였다.
- `mart.common_stock_universe_asof`의 기반인 `core.symbol_security_type_history`가 2026-08-11부터만 있어 과거 날짜엔 멤버가 0 → "PIT 유니버스"가 사실상 오늘 상장 종목이었다(생존자 편향 존재).
- 워크포워드 검증은 24폴드·480세션(≈41개월)을 요구해 1년 창에서는 폴드 0개로 실패한다.

변경:
- `AI_BACKTEST_LOOKBACK_YEARS`(기본 1, 최대 3), `AI_BACKTEST_UNIVERSE_MAX_TICKERS`(기본 200). 유니버스는 상장이력+보통주 분류가 **창과 겹치는** 종목(창 중간 상장폐지 포함) 중 **창 시작 직전 60세션 거래대금 상위 N**을 DB에서 랭킹. 현재 신호 스크린은 `listing_status='listed'`만.
- raw 시세 없는 행은 INNER JOIN으로 적재하지 않음(백테스트 크래시 원인 제거). V1 명시 규칙은 필요한 지표 패밀리만 읽고 DART는 건너뜀.
- 워크포워드 정책을 창 길이에 비례(≤15개월: 1/6/1/1, 최소 3폴드·60세션; 16~40개월: 1/12/3/1, `max(6, months-17)`폴드; ≥41개월: 기존). 후보 타임아웃 8초, 노드 예산 25초, 자기개선 최대 1라운드, 폴드 경계에서 취소·데드라인 검사.
- AOAI 클라이언트 기본 timeout 120→45초, 재시도 2→1(호출당 최악 90초 → 운영 env로 더 낮출 수 있음: `AI_AOAI_TIMEOUT_SECONDS`, `AI_AOAI_MAX_RETRIES`).
- 실측(node3 DB, 1년·상위 200): 유니버스 2.4~2.9초, 가격(raw inner join) 1.1초(48,512행), momentum 지표 0.9초(41,789행). 로컬 백테스트 노드 200종목×250세션 3후보 ≈12초(서버 ≈6초). LLM은 Data 이후 순차 2회(리서치 컴파일, 리포트 작성) ≈15초.

### 7.1 node3 실측(실제 웨어하우스, LLM은 mock) — 최종
| 버전 | Data | Backtest | 합계 | 비고 |
|---|---|---|---|---|
| 배포 608b2f1(5년·전체 1,717종) | 875s | 실패(56s) | 실패 | RSS 21GB |
| 1년·상위 200 | 32.1s | 25.1s | 58.1s | RSS 577MB, 오늘자 스크린 9s 직렬 |
| **1년·상위 100 + 스크린 병렬** | **18.9s**(스크린 9.3s 병렬 포함) | **11.9s** | **31.3s** | 가격 24,250행 |

실제 AOAI 호출(리서치 컴파일 + 리포트 작성 ≈ 15s)을 더하면 **약 45~50초**로 1분 목표 안. 운영 env로 `AI_AOAI_TIMEOUT_SECONDS`/`AI_AOAI_MAX_RETRIES`를 더 조이면 최악 케이스도 줄어든다.

### 7.2 배포 사이트 실측 (2026-09-03 00:22 KST, 배포 0108590, 실제 AOAI + qt_db)
- 배포 직후 두 번의 실측 실패로 기존 결함 2건을 추가로 고쳤다: (1) KST 자정~새벽 적재 사이 창 종료일이 시세 없는 세션이라 릴리스 매니페스트 거부 → 창 종료일을 마지막 적재 세션으로 캡(PR #88); (2) production에서 `AI_BACKTEST_CACHE_DIR` 미설정이면 백테스트 거부 → deploy가 `.run/backtest-cache`를 export(PR #89).
- 최종: `RSI 30 이하일때 매수하고 70 이상일때 매도` → interpreting/code_generation/backtest/debate/finalizing 모두 succeeded, **53초에 ready**(기존: 875초 후 실패). `POST /api/v1/runs` 201 → `/complete` 200 → `app.strategy_email_report` 1행(sent) → `/api/v1/reports` 1건. 이메일 enqueue는 서버 `EMAIL_DELIVERY_ENABLED=false`라 정책상 skip.
- 남은 여지: 53초 중 LLM 2회(리서치 컴파일·리포트 작성)가 ~20초. `AI_AOAI_TIMEOUT_SECONDS`/`AI_AOAI_MAX_RETRIES`를 운영 env로 더 조이거나 리포트 작성 호출을 축약하면 40초대 가능.

## 8. 시연 준비 루프 (2026-09-03)

§7.2의 53초 측정 이후, 실제 시연에 쓸 자연어 입력 10개를 배포 사이트에 직접 흘려 막힌 지점을 하나씩 고쳤다(배포 f4e412e → 7210cab).

### 8.1 프로브 방법
`node3_demo_probe.py`(저장소 밖): 합성 Google 사용자 + 실제 Redis 세션을 만들고 `POST /ai-api/analysis-jobs`로 폴링, ready면 선택적으로 `/api/v1/runs` + `/complete`까지 저장한 뒤 정리한다. 시연 입력 10개: RSI 30/70, 20/60일 이동평균 골든/데드크로스, MACD 골든/데드크로스, 볼린저 하단/중간선, 거래량 20일 평균 2배 후 5일 보유, 최근 3개월 모멘텀 상위 월간 교체, PER 10 이하, 반도체 섹터 RSI 30 이하, "유명한 퀀트전략", "안녕".

### 8.2 배포 전/후
| 구간 | 전(f4e412e) | 후(7210cab) |
|---|---|---|
| 리포트까지 완주 | 4/10(RSI, 거래량, 모멘텀, 유명한 퀀트전략) | 8/10 |
| 나머지 6건 | clarification("먼저 어떤 후보 전략으로 구체화할까요?" + 범용 옵션 3개)에서 정지, "안녕"은 26초 소요 | "안녕"은 5.7초에 "어떤 투자 전략이나 매매 조건을 분석할까요?"로 응답; "유명한 퀀트전략"은 목표 기준 통과(OOS Sharpe 0.31, validated); 모멘텀 1건은 일시적 AOAI 장애("strategy research provider is temporarily unavailable")로 실패 |
| 소요 시간 | - | ready 도달 52~78초(순차 부하). 단독 실행 스테이지 타임라인: interpreting 11~18초, code_generation 2~9초, backtest 20초(라운드 없음)~30초(2라운드), debate/report 11초 → 합계 55~58초 |

### 8.3 원인과 수정
- (i) sma60 부재 — compiler가 sma20/50/200만 알았다. 이제 sma{N}/ema{N}(2~250)을 종가에서 직접 계산하고(`ai/ai_graph/nodes/condition_compiler.py`) 패턴으로 리서처에 광고한다.
- (ii) MACD 크로스 거부 — 문법에는 CROSS_ABOVE/CROSS_BELOW가 있었지만 `_compile_one`이 컴파일하지 않았다. 이제 임의의 두 지표에 대해 직전 봉 대비 반전으로 컴파일한다.
- (iii) 볼린저 "검증 불가" — indicator-family 로딩이 원본 operand 이름(별칭 `bollinger_lower`, boolean 지표 `close_cross_above_sma20`)을 그대로 찾다 보니 변동성/추세 테이블을 한 번도 읽지 못했다. 이제 하나의 공유 operand 확장 `condition_metric_inputs`를 `ai/ai_graph/data_sources/db.py`의 `indicator_families_for_metrics`와 `ai/ai_graph/nodes/backtest_features.py`가 함께 쓴다. 같은 버그가 `close_above_sma_200` 규칙도 굶기고 있었다(거래 0건).
- (iv) PER — `per`를 PIT 지표로 추가했다(raw_close / 최근 연간 EPS 이월, report_code 11011). EPS ≤ 0이면 미설정으로 둔다(분기 EPS는 3개월치라 그대로 나누면 PER이 4배씩 튄다). PBR은 아직 불가능(웨어하우스에 발행주식수/BPS 없음).
- (v) 섹터 — `feature.wics_symbol_sector_history`(symbol_id, sector_name, valid_from, valid_to; 섹터명 26개; 반도체 = 166종목)를 구간 겹침으로 PIT 유니버스 CTE에 조인한다. 리서처는 allowed_sectors를 받고 그 안의 섹터명만 써야 한다(벗어나면 research_sector_dropped). 주의: WICS 행이 전부 2026-07-02부터 시작하는 단일 열린 구간이라 섹터 이력은 아직 진짜 point-in-time이 아니다.
- (vi) holding_days / rebalance_interval_days(ResearchCandidateV3, `ai/ai_graph/schemas.py`) — 리서처가 "5일 뒤 매도"를 `close >= 0`(항상 참, 거래 717건)으로 흉내 내던 것을 없앴다. evaluator가 종목별 sessions_held를 추적해 정확히 청산하고, 교체매매는 기존 scheduled_rotation 경로를 재사용하며, validation이 항상 참인 exit을 repairable 오류로 거부한다.
- (vii) 리서치 호출 전에 잡담을 짧게 처리하고(`ai/ai_graph/research_contract.py`) clarification 질문을 의도에 맞춰 고른다(`ai/ai_graph/api.py`).
- (viii) 워크포워드 라운드: 폴드 평가를 (candidate, fold, pass) 단위로 메모이즈, 폴드 준비를 공유, 기존 프로세스 풀에서 병렬 실행, selection-width 디플레이션 항은 계속 게시하되 워크포워드에서는 더 이상 floor를 막지 않음, budget 25→30초(`ai/ai_graph/nodes/backtest.py`) — node3: backtest 노드 11.8초/0라운드 → 21.5~25.9초/1라운드, 전체 43~50초(mock LLM).
- (ix) FE(`fe/src/api/quantAgentClient.ts`, `fe/src/features/app/OverviewTab.tsx`, `PerformanceTab.tsx`): 거부된 실행에서 "10.0 / 10" 대신 "보류", overview 타일과 차트 카드가 OOS 지표 세트를 읽음(라벨 "검증 구간(OOS) 누적 수익률", "Sharpe (Walk-forward OOS)"), 차트가 더 이상 마지막 5개 포인트로 잘리지 않음, 승률 부호 없음, 0 degradation 카드 숨김.

### 8.4 node3 회귀
병합된 스냅샷 기준: backtest_module 42 · service_db 57/3 skip · DE 12 · ai 959/11 skip · backend unit 409 · fe build+tests · Track C server integration 3 · Track 4 email server integration 1 — 전부 pass.

### 8.5 UI 검증
합성 세션(cookie `qa_session` + localStorage `quantagent.auth.session.v1`)을 발급해 확인했다: RSI·이동평균 교차 실행이 conclusion, 보류, OOS 타일, 전체 곡선(81 포인트, 날짜축 7개), reports 목록/상세를 그린다.

### 8.6 남은 항목
후속 PR에서 고치는 중: `GET /ai-api/analysis-jobs` 500(statement timeout — list_jobs가 전체 사용자의 job 100건을 JSON 통째로 읽어 Python에서 필터링), 워크포워드 실행이 ticker_actions 0건 발행(폴드가 엔진 결과를 보관하지 않음), 일시적 리서치 제공자 장애가 역량 부재처럼 범용 옵션 3개짜리 clarification으로 표시됨, wall budget 30→22초로 낮춰 60초 이내 유지. 운영 항목: node3에 EMAIL_*/Brevo 미설정(실제 발송 불가), 합성 사용자 `e2e-demo-*`/`e2e-ui-*`가 `app.analysis_result`에 남아있을 수 있음, `db_split.py`가 loader 함수의 stale한 사본을 갖고 있음(테스트 전용).

### 8.7 배포 후 실사이트 프로브 (7f57fe4, 2026-09-03 17:32 KST, 순차 실행·node3 회귀와 일부 겹침)

| 입력 | 상태 | 소요(s) | OOS Sharpe | 곡선 점수 | 종목 판정 | 영속화 |
|---|---|---:|---:|---:|---:|---|
| RSI 30 이하 매수 / 70 이상 매도 | ready | 56.3 | -0.07 | 81 | 117 | run 201 · complete 200 |
| 20일/60일 이동평균 골든·데드크로스 | ready | 41.1 | -1.36 | 81 | 5 | 201 · 200 |
| MACD 골든·데드크로스 | ready | 62.4 | -4.61 | 81 | 7 | 201 · 200 |
| 볼린저 하단 이탈 매수 / 중간선 회복 매도 | ready | 44.8 | -1.15 | 81 | 5 | 201 · 200 |
| 거래량 20일 평균 2배 매수 후 5일 보유 | ready | 50.9 | -2.28 | 81 | 10 | 201 · 200 |
| 최근 3개월 모멘텀 상위, 월간 교체 | ready | 63.2 | -3.37 | 81 | 6 | 201 · 200 |
| PER 10 이하 가치주 매수 | ready | 46.8 | -2.72 | 81 | 2 | 201 · 200 |
| 반도체 섹터 RSI 30 이하 매수 | ready | 57.4 | -1.55 | 81 | 1 | 201 · 200 |
| 유명한 퀀트전략 | ready | 51.1 | -2.92 | 81 | 7 | 201 · 200 |
| 안녕 | need_clarification | 3.7 | — | — | — | 질문: "어떤 투자 전략이나 매매 조건을 분석할까요?" |

- 10/10이 시연 가능한 응답으로 끝났다: 9건은 성과 신뢰도 `sufficient`, 81점 OOS 곡선, 결론 문자열, 종목별 판정을 갖춘 리포트로 영속화됐고, 인사말은 리서치 호출 없이 전략 의도 질문으로 끝났다.
- 60초 초과 2건(62.4 s, 63.2 s)은 같은 시각 node3에서 회귀 스위트(ai 967 tests, FE 빌드)가 돌던 구간과 겹친다. 단독 실행 스테이지 타임라인은 55~58 s였고, 라운드 예산 22 s 반영 후 단독 재측정이 남은 확인 항목이다.
- 이번 실행에서는 어떤 규칙도 수용 플로어(OOS Sharpe ≥ 0)를 넘지 못했다. 직전 실행(7210cab)에서 "유명한 퀀트전략"이 OOS Sharpe 0.31로 통과했듯 리서치 후보는 실행마다 달라진다. 플로어 미달은 결론과 참고용 판정으로 표시되며 화면이 비지 않는다.
- `GET /ai-api/analysis-jobs` 200(10건), `GET /api/v1/reports` 200(9건).

### 8.8 진입 조건만 있는 입력의 기본 청산 (874f0aa)

UI로 "반도체 섹터에서 RSI 30 이하 종목 매수"를 다시 넣었을 때 리서처가 "청산 규칙을 임의로 추가하지 않았습니다"라며 후보를 내지 않았다(같은 입력이 10분 전 프로브에서는 통과). 프롬프트 정책을 고정했다: 진입만 있고 청산이 없는 요청은 `holding_days=20`(약 1개월)으로 실행하고 가정("청산 조건이 없어 20거래일 보유 후 청산으로 가정")을 기록하며, 청산 부재는 후보 거부 사유가 아니다(`ai/ai_graph/nodes/strategy_research.py`, 테스트 `ai/tests/test_entry_only_default_exit.py`).

874f0aa 배포 후 단독 실행(스테이지 타임라인은 interpreting/code_generation/backtest/debate 완료 시각):

| 입력 | 상태 | 소요(s) | 타임라인(s) | 종목 판정 |
|---|---|---:|---|---:|
| 반도체 섹터 RSI 30 이하 매수 (1회차) | ready | 61.4 | 34.4 / 34.4 / 52.3 / 61.4 | 0 |
| PER 10 이하 가치주 매수 | ready | 57.0 | 28.0 / 28.0 / 43.5 / 54.5 | 9 |
| 반도체 섹터 RSI 30 이하 매수 (2회차) | ready | 57.4 | 25.6 / 28.1 / 46.1 / 54.8 | 0 |
| 20일/60일 이동평균 크로스 | ready | 40.5 | 22.1 / 22.1 / 29.3 / 38.0 | 5 |

- 라운드 예산 22 s 반영 후 백테스트 스테이지는 7~18 s, 토론/리포트 9~11 s. 남은 병목은 V3 리서치(interpreting 22~34 s, 리페어 턴이 들어가면 30 s 이상)이며 60 s 초과는 그 경우에만 발생한다.
- 반도체 섹터 실행의 종목 판정 0건은 마지막 세션에 RSI ≤ 30인 섹터 종목과 보유 중인 포지션이 없다는 뜻이다(엔진 최종 상태 기준). FE는 이 경우 "규칙상 오늘 해당 종목 없음"으로 표시한다.
- node3 AI 스위트(874f0aa 스냅샷): 968 passed, 11 skipped.

### 8.9 "리포트 저장 실패 (Analysis run is already completed with different content)" 배너

사용자가 본 배너의 원인은 두 겹이다. (1) 백엔드 `complete_analysis_run_from_db`는 이미 완료된 run에 대해 AI 잡 결과에서 스냅샷을 다시 유도해 저장본과 비교했는데, 배포 사이에 AI 결과 스키마가 필드를 얻으면(holding_days, out_sample_max_drawdown 등) 같은 잡의 스냅샷이 달라져 409 `completion_payload_conflict`가 났다. 실사이트에서 f4e412e 시점에 저장된 리포트를 다시 저장하면 409, 스키마 변경 뒤 저장된 리포트는 200 `created:false`로 재현됐다. (2) FE는 클라이언트 라우터가 없어 화면 이동마다 재마운트되고, 완료된 잡을 매번 다시 저장하며, 실패하면 다음 폴링마다 무한 재시도했다.

수정: 백엔드는 같은 사용자·같은 aiJobId의 완료된 run이면 스냅샷 비교 없이 기존 핸들을 돌려준다(불변 `app.analysis_result`는 절대 다시 쓰지 않음; 다른 aiJobId는 여전히 409). FE는 409 `completion_payload_conflict`를 "이미 저장됨"으로 처리하고, 그 밖의 실패는 5 s·20 s 백오프로 최대 2회만 재시도한 뒤 멈추며, 배너는 닫기 버튼이 있고 성공하면 지워진다. 테스트: backend unit 413, FE 54.

