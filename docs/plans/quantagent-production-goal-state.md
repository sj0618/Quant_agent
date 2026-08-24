# QAG-PROD-TRUST-001 Goal 상태

| 필드 | 값 |
|---|---|
| Goal ID | `QAG-PROD-TRUST-001` |
| 상태 | `draft` |
| 생성 시각 | 2026-08-13 KST |
| owner | 제품 신뢰 리드 |
| objective | 온디맨드 분석·추천을 제거/비활성화하고, 검증 불가한 데이터·지표·오류를 성공 결과로 표시하지 않는 출시 기준선을 만든다. |
| evaluator | 미정. `WBS-GATE-001`의 명령과 PASS/FAIL 예시 출력이 고정되기 전에는 Goal을 시작하지 않는다. |
| 다음 상태 전이 | WBS-GATE-001 사전 실행 증적 → `created` → `running` |

## 상태 불변식

- `draft`에서는 `omx performance-goal create/start`를 실행하지 않는다.
- `created`와 `running`의 모든 checkpoint는 같은 Goal ID와 revision, control board 증적 URI를 가져야 한다.
- `complete`는 모든 P0 증적·evaluator PASS·독립 QA APPROVE가 같은 revision을 가리킬 때만 허용한다.
- 외부 권한·테스트 세션·사람의 정책 결정을 기다리면 `blocked`로 기록하며, 그 사실을 완료로 바꾸지 않는다.
