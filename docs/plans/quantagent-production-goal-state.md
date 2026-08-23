# QAG-PROD-TRUST-001 Goal 상태

| 필드 | 값 |
|---|---|
| Goal ID | `QAG-PROD-TRUST-001` |
| 상태 | `blocked` (2026-08-24 범위 대체 결정) |
| 생성 시각 | 2026-08-13 KST |
| owner | 제품 신뢰 리드 |
| objective | 온디맨드 분석·추천을 제거/비활성화하고, 검증 불가한 데이터·지표·오류를 성공 결과로 표시하지 않는 출시 기준선을 만든다. |
| evaluator | `d60175f34178589887ea78bbc8b5b352aec0bd7c`의 `node scripts/evaluate-release-trust.mjs`가 비밀 환경변수 제거 로컬 환경에서 PASS. 이 결과는 운영·실데이터 근거가 아니다. |
| 종료 결정 | 요청자(PM 대리)가 기존 production-goal 범위를 8/31 연구용 MVP로 대체하는 것을 승인했다. 기존 Goal은 production completion을 주장하지 않고 `blocked`로 종료한다. |
| 다음 상태 전이 | 없음. 후속 RMP WBS·별도 release goal에서 운영·실데이터·배포 검증을 새로 기록한다. |

## 상태 불변식

- `draft`에서는 `omx performance-goal create/start`를 실행하지 않는다.
- `created`와 `running`의 모든 checkpoint는 같은 Goal ID와 revision, control board 증적 URI를 가져야 한다.
- `complete`는 모든 P0 증적·evaluator PASS·독립 QA APPROVE가 같은 revision을 가리킬 때만 허용한다.
- 이 Goal의 `blocked` 종료는 production release의 실패 판정도, release completion도 아니다. 범위가 RMP로 대체되어 기존 Goal이 더 이상 실행 단위가 아니라는 기록이다.
- 외부 권한·테스트 세션·사람의 정책 결정을 기다리면 `blocked`로 기록하며, 그 사실을 운영 완료로 바꾸지 않는다.

## 종료 checkpoint

- 시각: 2026-08-24 KST
- 결정자: 요청자(PM 대리)
- 결정: 기존 `QAG-PROD-TRUST-001`을 `blocked`로 종료하고 8/31 연구용 MVP WBS로 대체한다.
- 로컬 근거: `d60175f34178589887ea78bbc8b5b352aec0bd7c`, `node scripts/evaluate-release-trust.mjs`, 비밀 환경변수 제거 상태에서 offline gates PASS.
- 금지선: 위 근거로 운영 배포·실데이터·실거래·사용자 권고 완료를 주장하지 않는다.
