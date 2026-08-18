# QuantAgent 용량·역량 매트릭스

## 현재 결정

사용자가 개인별 가용 시간·기간·실명 배정을 제공하지 않았으므로 이를 추정하지 않는다. 이 문서는 역할 단위의 배정 한계와 사람 결정이 필요한 입력을 보인다. WBS의 owner와 backup은 역할이며, 실제 담당자는 이 표를 채운 뒤에만 확정한다.

| 역할 | 실명 | 가용 시간·기간 | 담당 가능 범위 | 피해야 할 범위 | 최대 WIP | backup 후보 | SPOF 판정 | 상태 |
|---|---|---|---|---|---:|---|---|---|
| 제품 신뢰 리드 | 사람 결정 필요 | 사람 결정 필요 | Goal, release gate, 정책 충돌 | 단독 코드 구현 | 1 | 독립 심사자 | backup 미정 | 차단 |
| 퀀트 검증 리드 | 사람 결정 필요 | 사람 결정 필요 | PIT, OOS, 비용·체결, metric acceptance | 인증·배포 단독 결정 | 1 | 용어 검사자 | backup 미정 | 차단 |
| 데이터·AI 신뢰 리드 | 사람 결정 필요 | 사람 결정 필요 | provider, fixture, data lineage, job store | 제품 카피 승인 | 1 | 퀀트 검증 리드 | backup 미정 | 차단 |
| UX 검증 리드 | 사람 결정 필요 | 사람 결정 필요 | public/auth/error UI, Playwright, accessibility | 지표 공식 단독 승인 | 1 | 용어 검사자 | backup 미정 | 차단 |
| 용어 검사자 | 사람 결정 필요 | 사람 결정 필요 | metric registry, 사용자 용어, formula 설명 | provider·DB 구현 단독 승인 | 1 | 퀀트 검증 리드 | backup 미정 | 차단 |
| 일정·증적 매니저 | 사람 결정 필요 | 사람 결정 필요 | WBS, risk, board, workload 조율 | 구현·QA 자기 승인 | 1 | 제품 신뢰 리드 | backup 미정 | 차단 |
| 독립 심사자 | 사람 결정 필요 | 사람 결정 필요 | acceptance, counterevidence, release review | 자신이 작성한 행 승인 | 1 | 제품 신뢰 리드 | backup 미정 | 차단 |

## WBS 동결 전 사람 결정 입력

1. 각 역할의 실명, 주당 가용 시간, 참여 시작·종료일
2. 각 역할의 역량 confidence(0.0~1.0)와 피해야 할 작업
3. primary·backup의 실제 조합과 휴가·부재 기간
4. 최대 WIP, 같은 파일/수용 기준 충돌 시 우선순위

이 입력이 비어 있는 동안 WBS는 상대 작업일·의존성·역할 owner까지만 유효하며, 달력 날짜·개인별 과부하·실제 커밋 배정은 `승인 대기`다.
