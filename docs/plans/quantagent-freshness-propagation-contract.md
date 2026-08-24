# Freshness 한계와 stale 전파 계약

## 결정

release source manifest의 `freshness`와 `as_of`를 하나의 `FreshnessEvidence`로 해석한다.
이 증적은 API envelope와 web/email report projection에 같은 값으로 들어간다.

| 필드 | 의미 |
|---|---|
| `status` | `fresh`, `stale`, `unknown`, `not_time_sensitive` 중 하나 |
| `as_of` | 입력 스냅샷이 유효한 기준일. 알 수 없으면 `null` |
| `reason` | freshness 판정 또는 판정 불가 사유 |
| `source` | 실제 입력 데이터 source |
| `no_recommendation` | stale/unknown 또는 fixture source이면 `true` |

## 전파 규칙

1. source manifest가 없거나 freshness가 해석되지 않으면 `unknown`으로 표시한다.
2. `stale`와 `unknown`은 추천을 생성하지 않는다. API의 `recommendation_gate.validated`는
   `false`, `ticker_actions`는 빈 배열이 된다.
3. API envelope의 `freshness_evidence`와 report의 `freshness` section은 같은 source,
   as-of, reason, no-recommendation 결정을 보존한다.
4. report는 결과를 숨기지 않고 stale 사유와 최신 manifest 확인 후 재실행이라는 다음
   행동을 함께 노출한다.

## QA 증적

`ai/tests/test_freshness_propagation.py`는 stale 표본의 as-of/reason/no-recommendation과
web/email projection 간 동일한 freshness 증적을 검증한다. API envelope contract는
공개 응답에 freshness evidence 필드가 존재하는지 확인한다.
