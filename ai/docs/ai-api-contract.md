# QuantAgent AI API Contract

## 범위

이 문서는 AI/LLM MVP의 in-process 계약이다. HTTP 라우트는 FE/BE 통합 단계에서 이 계약을 감싸며, 현재 구현은 fixture/mock 기반으로 외부 자격증명 없이 실행된다.

## 실행 파이프라인

| 순서 | 노드 | 책임 |
|---:|---|---|
| 1 | `supervisor` | `trace_id`, `debug_ref`, LLM client 경계 초기화 |
| 2 | `ambiguity` | C1/C2/C4/C5/READY 시나리오 분류 |
| 3 | `data` | mock KRX 후보군과 `StrategySpec` 생성 |
| 4 | `research` | L4 evidence fixture 및 LLMClient JSON 응답 검증 |
| 5 | `backtest_code` | 안전한 fixture 코드 참조 선택 |
| 6 | `backtest` | 백테스트 지표/시계열 생성 |
| 7 | `signal` | Signal Judge 액션과 confidence 산출 |
| 8 | `risk_manager` | 액션을 바꾸지 않고 warning/report_note만 추가 |
| 9 | `report` | FE용 public payload 조립 |

LangGraph가 설치된 환경에서는 `StateGraph`, `START`, `END`, `compile().invoke()`를 사용한다. 미설치 환경에서는 동일한 `.invoke()` 인터페이스를 가진 순차 fallback을 사용한다.

## Envelope

모든 API 응답은 아래 envelope를 따른다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `ok` | boolean | 성공 여부 |
| `trace_id` | string | 요청 추적 ID |
| `debug_ref` | string | 내부 디버깅 참조 |
| `data` | object/null | FE 공개 payload |
| `error` | object/null | 실패 코드와 메시지 |
| `meta` | object | polling 등 부가 메타 |

`internal_payload`, raw LLM 응답, node trace, fixture code ref는 public envelope의 `data`에 포함하지 않는다. 디버깅은 `trace_id`와 `debug_ref`로만 연결한다.

## Job polling

| 함수 | 입력 | 출력 |
|---|---|---|
| `submit_job(user_input)` | 자연어 전략 입력 | `JobRecord(status=succeeded|failed, trace_id, debug_ref, result)` |
| `get_job(job_id)` | `job_*` | 저장된 `JobRecord` 또는 null |

현재 저장소는 `InMemoryJobStore`이며 운영 저장소는 같은 `JobRecord` 스키마를 유지해야 한다.

## Public payload

`PublicRunPayload`는 다음 구조다.

| 필드 | 설명 |
|---|---|
| `scenario` | READY/C1/C2/C4/C5 분류와 사용자 메시지 |
| `workspace` | READY일 때만 Strategy/Candidate/Signal/Risk/Report/Backtest 결과 포함 |

Pydantic 모델은 `extra="forbid"`로 정의되어 예상하지 않은 필드, 특히 `internal_payload`의 외부 노출을 차단한다.
