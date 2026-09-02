# 온디맨드 분석·추천 퇴역 인벤토리

## 목적

새 분석을 만드는 화면·API·작업 경로를 하나씩 확인하고, 각 항목의 처리 방향을 `제거`, `보관`, `대체` 중 하나로 고정한다. 이 문서는 구현 완료 목록이 아니라 후속 퇴역 작업의 결정 기준이며, 모든 항목은 실제 현재 코드 경로와 연결한다.

## 결정 기준

| 결정 | 의미 |
|---|---|
| 제거 | 신규 생성·실행 또는 더 이상 지원하지 않는 공개 경로를 제품 계약에서 없앤다. 과거 결과 보존은 이 항목의 책임 범위가 아니다. |
| 보관 | 이미 생성된 결과와 읽기 경로를 유지하되, 신규 writer·실행 호출은 허용하지 않는다. |
| 대체 | 기존 진입점은 없애고, 읽기 전용 보관함·제품 범위 안내·명시적 410 등 지원되는 행동으로 연결한다. |

## 결정 항목

| OD ID | 현재 경로·근거 | 현재 공개 범위 | 결정 | 결정 근거 | 대체 사용자 행동 | 회귀 검사 |
|---|---|---|---|---|---|---|
| OD-01 | canonical `fe/src/pages/AppPage.tsx:7-21`은 보관함만 표시하지만 legacy `backend/fe-api-preview/src/pages/AppPage.tsx:287-297`에는 `StrategyInputPanel`과 `createAnalysisJob`이 남아 있다. | 인증 후 `/app`; legacy preview에는 신규 입력 화면이 존재 | 대체 | canonical 화면을 기준으로 신규 입력·실행 UI를 없애고 legacy preview도 같은 보관 UX로 수렴한다. | 기존 리포트 보관함으로 이동 | canonical/legacy 브라우저에서 query 입력·실행 CTA·진행률 DOM 0개 |
| OD-02 | canonical `fe/src/api/quantAgentClient.ts:93-102`는 GET 리포트만 노출하지만 legacy `backend/fe-api-preview/src/api/quantAgentClient.ts:138-166`은 `createAnalysisJob`과 polling을 노출한다. `fe/src/config/appConfig.ts:17-20`에는 잔여 analysis endpoint 상수도 있다. | canonical 브라우저 번들 및 legacy preview 번들 | 제거 | 신규 분석 client 함수·import·endpoint 상수는 지원 계약에서 제거한다. 보관 조회 client만 남긴다. | 없음; 새 분석을 요청하는 API client를 제공하지 않음 | TypeScript typecheck와 canonical/legacy 정적 import 검사; `POST /analysis-jobs` 0회 |
| OD-03 | `ai/ai_graph/api.py:415-451`의 `POST /analysis-jobs`가 `store.create_job`과 background `run_job_sync`를 호출하고, `:542-552`, `:647-658`에는 목록·상세 GET이 있다. | 인증된 API caller | 대체 | 신규 POST는 410 feature-disabled로 바꾸고 job·worker dispatch를 만들지 않는다. 기존 GET은 보관 조회 경로로 분리한다. | 읽기 전용 과거 결과 endpoint 또는 `/reports`로 이동 | POST가 410이고 job·background task·성공 audit 0건; 410 body에 사유·revision·대체 경로 포함 |
| OD-04 | `ai/ai_graph/jobs.py:156-201,230-390`, `ai/ai_graph/job_store_persistent.py:66-146`, `ai/ai_graph/job_repository_postgres.py:34-124`가 job 생성·상태 변경·완료 저장과 목록·상세 조회를 함께 제공한다. | AI API 내부 job store 및 과거 결과 소비자 | 보관 | 기존 완료 job의 GET/list projection은 유지하고, 신규 job 생성·상태 변경·완료 writer 소비자는 OD-03/OD-05와 함께 차단한다. | 기존 job/report 조회 | service test에서 신규 record·background run 0건, 기존 완료 record GET/list PASS |
| OD-05 | Backend Track C `backend/app/api/routes/fe_contract.py`의 `POST /api/v1/runs`, `POST /runs/{run_id}/complete`와 `backend/app/services/fe_contract_store.py:2256-2499`가 소유자 run·report를 영속화하고 이메일을 enqueue한다. | session+CSRF와 소유한 완료 job(`aiJobId`) 확인을 통과한 backend FE contract consumer | 제거 | 온디맨드 **공개 신규 생성**은 제거한다. 남는 두 writer는 새 분석을 만들지 않고, 이미 완료된 소유 job의 결과를 영속화하는 인증 경로(authenticated persistence of an owned completed job: allowed)다. | 완료된 분석 결과가 리포트 보관함·이메일로 남고, 이후 열람은 `/reports` 읽기 경로 | 두 POST가 `aiJobId` 없으면 422, 없는 job이면 404, 미완료 job이면 409. 소유 완료 job이면 201/200으로 영속화되고 `app.strategy_email_report` write 1건 |
| OD-06 | `ai/ai_graph/api.py:708-759`의 `POST /ai/daily-digest`가 `build_daily_digest`와 audit 성공 경로를 직접 호출한다. | 인증 의존성이 없는 AI API route | 제거 | production에서 route를 제거하거나 410으로 닫고, 신규 daily digest 생성·LLM 호출을 만들지 않는다. | 기능 미제공 안내와 읽기 전용 보관함 | POST route absence/410, report 생성·LLM 호출·성공 audit 0건 |
| OD-07 | canonical FE는 `fe/scripts/api-source.test.mts:78-84`에서 `/dev/email-template` route/source 부재를 검증하지만 `fe/docs/email-template/README.md:10-13`과 sample generator가 남아 있다. Backend public fallback은 `backend/tests/unit/test_backend_hosted_pages.py:78-88`에서 404를 검증한다. | 공개 개발 preview 및 production에 섞일 수 있는 email template source | 제거 | public route·preview chunk·mock/source 노출을 제품 bundle에서 제거한다. 내부 문서·검증 fixture는 공개 runtime과 분리한다. | 없음; 이메일 생성 기능은 현재 지원하지 않음 | public smoke 404, route 문자열·preview chunk·mock source 미노출 |
| OD-08 | `fe/src/pages/LandingPage.tsx:7-36,64-74`의 CTA는 `/reports` 로그인 후 보관함으로 연결되며, canonical App route도 보관함이다. | 비인증 landing과 인증 경계 | 대체 | 신규 분석 sample CTA나 과거 report ID를 가장하는 흐름은 두지 않고, 제품 범위와 보관함 안내로 대체한다. | 제품 범위 안내 → 로그인 후 리포트 보관함 | CTA click이 신규 분석·가짜 report 없이 보관함 또는 로그인으로만 이동 |
| OD-09 | `fe/src/api/quantAgentClient.ts:93-102`, `backend/app/api/routes/fe_contract.py:210-248`가 `/reports` 목록·상세 읽기 경로를 제공한다. 별도 정책 문서 `docs/plans/quantagent-read-only-report-retention-policy-decision.md`는 기간·권한·마스킹 승인을 요구한다. | 인증된 과거 report 소비자 | 보관 | 완료된 과거 report는 읽기 전용 보관물로 유지한다. 보관 기간·권한·마스킹의 세부값은 승인 전 임의 확정하지 않지만, lifecycle 방향 자체는 보관으로 결정한다. | 보관 report 조회; stale·근거 부족이면 한계와 홈/목록 행동 표시 | `/reports` GET와 detail GET만 허용, write method 405/410, read-only 표지·기준 시점·한계 표시 |
| OD-10 | legacy `backend/fe-api-preview/src/pages/AppPage.tsx:124-223,255-324`에 progress timer·polling·cancel/new conversation이 있고, canonical `fe/src/pages/AppPage.tsx:7-21`은 이미 보관 UX다. | 인증 후 legacy workspace | 대체 | 실행 중 분석을 전제로 한 진행률·취소·새 대화 state를 제품 화면에서 없애고 보관함 탐색으로 교체한다. | 리포트 탐색·상세 열람 | elapsed progress·cancel request·on-demand polling 0회, 보관함 이동 PASS |

## 결정 집계

| 결정 | 항목 수 |
|---|---:|
| 제거 | 4 |
| 보관 | 2 |
| 대체 | 4 |
| 합계 | 10 |

## 정책 경계

- 이 문서는 10개 항목의 lifecycle 방향을 결정한다. 실제 route·writer·bundle 제거는 OD-FE-01, OD-FE-02, OD-API-01, OD-JOB-01, OD-DIG-01, OD-DIG-02, OD-REP-02의 후속 구현 범위다.
- OD-09는 `보관`으로 결정했지만, 보관 기간·열람 권한·마스킹·만료 후 처리는 `docs/plans/quantagent-read-only-report-retention-policy-decision.md`의 승인 없이는 임의로 정하지 않는다. 이는 `보관` 결정을 미완료로 되돌리는 의미가 아니다.
- (2026-09-02) 47ae545가 OD-05의 두 backend writer를 production에서 410으로 닫은 뒤, 94b3afe가 `POST /analysis-jobs`를 인증 writer로 되살렸고 9e616bf 계열 FE는 분석 완료마다 두 writer를 호출한다. 머지 순서 탓에 production에서 `complete_analysis_run_from_db`가 실행되지 않아 리포트 저장과 이메일 enqueue가 전무했다. OD-05의 결정은 그대로 `제거`(공개 온디맨드 생성 제거)이며, 소유한 완료 job의 영속화는 인증 경로로 허용한다. 자세한 경계는 `docs/plans/quantagent-retained-execution-contract.md`의 2026-09-02 갱신 절을 따른다.
- 기존 API consumer가 남아 있으면 조용한 404 대신 410 body에 비활성 사유, 시행 revision, 읽기 전용 대체 경로를 제공한다.
- `daily-digest` 생성과 이메일 preview를 새로 만들지 않는다. 개발 fixture와 내부 문서는 production bundle·public route와 분리한다.

## QA 실행

```powershell
cd ai
python scripts/validate_on_demand_retirement_inventory.py --inventory ../docs/plans/quantagent-on-demand-retirement-inventory.md
```

검증기는 정확히 OD-01~OD-10 열 개 행의 ID·필수 열·결정값을 확인하고, `제거·보관·대체` 집계가 문서의 합계와 일치하는지 검사한다.
