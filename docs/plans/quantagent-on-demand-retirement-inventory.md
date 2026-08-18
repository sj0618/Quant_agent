# 온디맨드 분석·추천 퇴역 인벤토리

## 결정

새 분석 요청과 새 추천을 만드는 흐름은 제거한다. 완료된 과거 결과는 외부 링크와 사용자 소유권을 보존하는 읽기 전용 보관물로만 남길 수 있다. 보관 화면에는 "새 분석은 현재 제공하지 않습니다"와 대체 행동을 표시한다. 이 문서의 항목이 모두 구현·회귀 검사를 통과하기 전에는 `공개 신규 요청 경로 0개`를 선언할 수 없다.

| OD ID | 현재 경로·근거 | 현재 공개 범위 | 결정 | 대체 사용자 행동 | 회귀 검사 |
|---|---|---|---|---|---|
| OD-01 | `fe/src/pages/AppPage.tsx:628-648`에서 사용자가 query를 입력해 `createAnalysisJob`을 호출 | 인증 후 `/app` | 입력창·실행 CTA 제거 또는 읽기 전용 보관 화면으로 교체 | 기존 리포트 조회 또는 홈으로 이동 | Playwright에서 새 query 입력·실행 버튼·`POST /analysis-jobs`가 0회 |
| OD-02 | `fe/src/api/quantAgentClient.ts:345-361`의 `createAnalysisJob` | 브라우저 번들에서 인증 후 호출 가능 | 호출 함수와 노출 import 제거 | 없음 | TypeScript typecheck와 정적 import 검사 |
| OD-03 | `ai/ai_graph/api.py:415-451`의 `POST /analysis-jobs`, background task, `run_job_sync` | 인증된 API caller | route를 410 또는 명시적 feature-disabled 응답으로 전환. worker dispatch 금지 | 읽기 전용 과거 결과 endpoint | API contract test에서 create가 job·task를 만들지 않음 |
| OD-04 | `ai/ai_graph/jobs.py`, `ai/ai_graph/job_store_persistent.py`, `ai/ai_graph/job_repository_postgres.py`의 분석 job 생성·저장 | OD-03의 소비자 | 새 job 생성 소비자를 비활성화. 기존 저장 결과는 migration 없이 읽기 전용 | 과거 결과 조회 | service test에서 새 record·background run 0건 |
| OD-05 | `fe/src/api/quantAgentClient.ts:489-504`의 service DB run 생성·완료 | OD-01 이후 간접 호출 | 새 run 생성·완료 호출 제거. 과거 `/reports` projection만 유지 | 리포트 목록·상세 | network test에서 `/runs` POST 0회 |
| OD-06 | `ai/ai_graph/api.py:708-759`의 `POST /ai/daily-digest` | API 인증 의존성 없음 | production에서 route 제거 또는 410. 개발 fixture는 비공개 test helper로 이동 | 이메일 기능 미제공 문구 | API contract test에서 report 생성·LLM 호출 0회 |
| OD-07 | `fe/src/config/routes.ts:14-15`, `fe/src/App.tsx:103-109`, `fe/src/pages/EmailTemplatePreviewPage.tsx:57-85`의 `/dev/email-template` | 비인증 공개 | production route·bundle에서 제거. 소스·mock·API 정보 노출 금지 | 없음 | public smoke에서 404, 문자열·chunk 노출 없음 |
| OD-08 | landing sample CTA와 `/reports/:id` 보호 흐름 | 비인증 공개에서 로그인 벽으로 종료 | CTA를 제거하거나 공개 읽기 전용 데모로 교체. 과거 실제 report ID를 sample으로 가장하지 않음 | 홈의 제품 범위 안내 | click trace에서 return 없이 login wall로 끝나지 않음 |
| OD-09 | 완료된 analysis job과 reports projection | 인증 후 | 읽기 전용 보관 여부를 정책 결정으로 확정. 유지 시 생성 시각·데이터 상태·한계·보관 범위를 표시 | 리포트 조회 | GET만 허용, write method 405/410 |
| OD-10 | `/app`의 진행률·중단·새 대화 상태 | 인증 후 | 실행 중 분석이 없다는 전제로 진행률 timer·cancel·새 대화 작업 흐름을 제거 | 리포트 탐색 | public/auth smoke에서 elapsed progress·cancel request 0회 |

## 경계

- `GET /reports`와 report detail의 보존 여부는 OD-09 정책 결정을 거친다. 이 계획은 임의 데이터 삭제를 허용하지 않는다.
- 기존 API consumer가 있으면 410 response body에 비활성 사유, 시행 revision, 읽기 전용 대체 URL을 준다. 404로 조용히 사라지게 하지 않는다.
- `daily-digest`의 이메일 전송 기능을 새로 만들지 않는다. 개발 예제도 production bundle·public route에서 분리한다.
