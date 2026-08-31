# 온디맨드 퇴역 뒤 실행 계약

## 결정

이번 Goal은 사용자 요청으로 시작하는 분석·추천을 없앤다. 따라서 release profile에서 provider, DB, L4, job store 오류가 발생하는 경로는 공개 분석 화면이 아니라 **내부 release evaluator**다. 사용자가 보는 화면에는 새 분석의 진행률·재시도·결과 카드가 남지 않는다.

| 경로 | owner | 인증 | 입력 | 출력 | 실패 전달 | 허용 여부 |
|---|---|---|---|---|---|---|
| 공개 신규 생성 | 없음 | 해당 없음 | `POST /analysis-jobs`, daily digest, 새 전략 입력 | 없음 | 410 feature-disabled와 읽기 전용 대체 링크 | 금지 |
| 내부 release evaluator | 데이터·AI 신뢰 리드 | 로컬 CI/승인된 운영자 환경 | versioned fixture 또는 명시된 release profile | test output, trace, evidence URI | evaluator FAIL, control board blocker. 공개 사용자에게 raw 오류를 보내지 않음 | Goal 범위 안 |
| 과거 report read | UX 검증 리드 | 기존 auth 정책 | 이미 저장된 report ID | 읽기 전용 보관 화면 | unavailable/stale이면 보관 한계와 대체 행동만 표시 | 사람 정책 승인 뒤 허용 |
| 상태 투영 | 일정·증적 매니저 | 공개는 불가, 내부 board만 | evaluator/CI 상태 | control board·evidence URI | 상태 전이 로그 | Goal 범위 안 |
| 새 batch·관리자 분석 | 없음 | 해당 없음 | 어떤 분석 input도 받지 않음 | 없음 | 별도 Goal 없이는 만들지 않음 | 금지 |

## 승인 필드 계약

실행 경계를 코드에서 검사할 때는 다음 식별자·경로와 `owner`, `auth`, `failure 전달` 값을 사용한다.

| 경계 ID | method | path | owner | auth | failure 전달 | 허용 | write |
|---|---|---|---|---|---|---:|---:|
| public-analysis-create | POST | `/analysis-jobs` | none | none | 410 feature-disabled + read-only alternative | 아니오 | 아니오 |
| public-daily-digest-create | POST | `/ai/daily-digest` | none | none | 410 feature-disabled + read-only alternative | 아니오 | 아니오 |
| public-analysis-run-create | POST | `/api/v1/runs` | none | none | 410 feature-disabled + read-only alternative | 아니오 | 아니오 |
| public-research-job-create | POST | `/api/research/jobs` | none | none | 410 feature-disabled + read-only alternative | 아니오 | 아니오 |
| internal-release-evaluator | POST | `/internal/evaluator/analysis` | data_ai_trust_lead | local_ci_or_approved_operator | evaluator FAIL + control board blocker | 예 | 예 |
| historical-report-read | GET | `/api/reports/{report_id}` | ux_verification_lead | existing_authenticated_user | stale/unavailable reason + next action | 예 | 아니오 |

## QA 계약

- 공개 create 허용 건수는 `0`이다.
- 허용된 실행 writer는 internal evaluator 하나뿐이다.
- 과거 report read에는 `owner`, `auth`, `failure 전달`이 모두 있어야 한다.
- read-only projection은 GET만 사용하며 생성·완료·삭제 writer를 포함하지 않는다.
- evaluator 실패는 사용자 화면에 raw 오류를 노출하지 않고 CI 실패와 control board blocker로 전달한다.

## failure UX 원칙

1. provider/DB/L4/job store 실패는 evaluator와 CI의 실패로 검증한다. 이는 public API를 다시 여는 근거가 아니다.
2. 읽기 전용 과거 report에서 stale·provenance 부재·비유한 지표가 발견되면 숫자나 추천을 보여 주지 않고, "이 기록은 현재 검증할 수 없습니다"와 홈 또는 보관 목록 행동을 표시한다.
3. 로그인 실패·rate limit은 read-only route의 인증·보호 정책에만 적용한다. 인증이 필요한 화면을 통과하지 못해도 과거 데이터가 노출되지 않아야 한다.
4. 새 실행이 필요한 요청은 UI에서 받지 않는다. 사용자에게 지원 범위 안내를 보이고 back-office 또는 batch 기능을 암시하지 않는다.

## 내부 상태와 batch 경계

상태 투영은 공개 실행 경로가 아니다. evaluator/CI 상태는 일정·증적 담당자가 control board와 evidence URI로만 관리한다. 새 batch·관리자 분석은 별도 승인된 Goal 없이는 만들지 않으며, 어떤 공개 분석 input도 받지 않는다.

## 후속 구현 경계

이 문서는 실행 경계를 승인하는 계약이다. 실제 API route를 비활성화하거나 evaluator 인증을 연결하는 구현은 이 표의 경계·owner·failure 전달을 바꾸지 않고 별도 작업으로 수행한다.
