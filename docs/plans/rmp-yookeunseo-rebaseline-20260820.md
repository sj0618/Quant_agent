# RMP 육은서 담당 재기준화·수용 기록 — 2026-08-20

> 기준 WBS: [QuantAgent_WBS](https://docs.google.com/spreadsheets/d/1V7SnG_x-cLIFbrSurDIadtx5GCY9HfL9jRqdyAl70Ks/edit) `2_WBS`.
> 2026-08-20에 읽기 전용으로 다시 확인한 범위는 `RMP-REB-01`(row 94),
> `RMP-CONTRACT-01`(row 96), `RMP-PREFLIGHT-01`(row 97),
> `RMP-PERF-01`(row 100), `RMP-APP-01`(row 101)이다.
> 이 문서는 WBS 상태를 바꾸거나 출시를 승인하지 않는다.

## 재기준화 결정

8월 31일 목표는 한국 주식 EOD 기반의 비개인화 리서치 흐름이다. 기존 OD-* 읽기 전용/분석 은퇴 작업은 이 목표의 containment history이며, 새 RMP 공개 기능의 운영 증거가 아니다.

| RMP 기능 | 기존 작업과의 관계 | 현재 구현 경계 | 공개 gate |
| --- | --- | --- | --- |
| F-01 연구 범위 | OD-FE-01/02의 레거시 직접 분석 호출은 계속 은퇴 상태 | `/app`은 연구 전용 API만 호출하고 브라우저가 DB/provider에 직접 접근하지 않는다. | API와 브라우저가 legacy job/run 경로를 호출하지 않음 |
| F-02 규칙 검토 | OD-API-01의 raw job 작성 모델을 대체할 신규 경계 | 일반 입력은 deterministic signed rule review로만 변환한다. | 입력 원문을 결과/토큰/로그 projection에 노출하지 않음 |
| F-03~F-05 데이터·일치·성과 | 기존 fixture/archive를 운영 결과로 승격하지 않음 | PostgreSQL EOD provenance가 검증되기 전에는 `ready`를 만들지 않는다. | source/as-of/freshness/coverage와 immutable result가 모두 확인됨 |
| F-06 terminal UX | OD-DIG-02/UX-ROUTE-01의 공개 preview 제거와 양립 | six-state renderer는 안전한 공개 projection만 소비한다. | internal/raw/provider field와 행동 유도 copy가 없음 |
| F-07~F-08 history/trust | OD-REP-*의 정책·보관 이력을 대체하지 않음 | history/trust owner가 immutable snapshot을 붙이기 전에는 결과를 `unavailable`로 끝낸다. | immutable result/version, lifecycle/outbox, 독립 검토 |

## 구현·증적 상태

| WBS | 담당 경계 | 현 상태 | S-tier 증거 | 운영 상태 |
| --- | --- | --- | --- | --- |
| `RMP-REB-01` | RMP/OD 대체 관계와 8/31 gate 기록 | 구현 완료·검토 대기 | 이 문서의 매핑과 `git diff --check` | WBS approver 승인 대기 |
| `RMP-CONTRACT-01` | six-state `ResearchResultV1` public projection | 구현 완료·검토 대기 | six-state type, OpenAPI contract, projection adapter | `ready`는 verified PostgreSQL EOD provenance 없이는 불가 |
| `RMP-PREFLIGHT-01` | 일반 규칙 검토와 pre-job 거부 | 구현 완료·검토 대기 | deterministic review, signed draft, one-shot confirmation, 0–3 clarification choices | 실제 provider/data/job 실행 증거는 제공하지 않음 |
| `RMP-APP-01` | authenticated `/app` workspace | 구현 완료·검토 대기 | rule review → confirmed job → safe result polling, six-state renderer, no legacy client | R/O/C 증거와 durable lifecycle 전에는 실행 fail-closed |

`dev_preview`는 여섯 번째 상태지만 fixture/renderer 검증 전용이다. 운영 데이터나 사용자 결과를 나타내지 않으며 public release evidence가 아니다.

## 현재 공개 계약

1. `POST /api/strategies/parse`는 허용된 일반 입력에 `ParseReviewV1`만 반환한다. Job, audit, quota 소비, provider, data source를 시작하지 않는다.
2. 개인화·직접 행동·명확한 비지원 자산 요청은 위 경계에서 422로 종료하며, 입력 원문·job/trace/result ID를 반환하지 않는다.
3. `POST /api/research/jobs`는 signed canonical rule만 받으며, explicit operational activation 없이는 fail-closed 한다. Replay는 conflict로 끝난다.
4. `GET /api/research/jobs/{job_id}/result`는 owned job의 `ResearchResultV1` projection만 반환한다. durable result identity와 verified PostgreSQL EOD provenance가 아직 없으면 `unavailable`이다.
5. `/app`은 rule review, confirmation, safe polling, clarification/refusal/error recovery를 렌더한다. `quantAgentClient`에는 legacy create/cancel/run 호출이 없다.

## Quant-QA scenario matrix

| ID | Class | Boundary / invariant | Command | Outcome |
| --- | --- | --- | --- | --- |
| RMP-S-01 | S | parse가 Job·runner를 만들지 않고 signed deterministic review만 반환 | `ai/.venv/bin/python -m pytest -q ai/tests/test_research_contract.py ai/tests/test_research_contract_api.py` | PASS (11) |
| RMP-S-02 | S | signed confirmation, replay fence, disabled execution, safe `unavailable` projection | `ai/.venv/bin/python -m pytest -q ai/tests/test_research_contract.py ai/tests/test_research_contract_api.py ai/tests/contracts/test_openapi_contract.py` | PASS (14) |
| RMP-S-03 | S | preflight, graph/API contract, offline fixture cache isolation, OpenAPI | `ai/.venv/bin/python -m pytest -q ai/tests/test_api.py ai/tests/test_graph_e2e.py ai/tests/contracts/test_api_envelope_contract.py ai/tests/contracts/test_openapi_contract.py ai/tests/test_research_contract.py ai/tests/test_research_contract_api.py` | PASS (65) |
| RMP-S-04 | S | public UI source contract, typecheck, production bundle build | `cd fe && npm test` | PASS (34) |
| RMP-S-05 | S | provider timeout/connection/HTTP 분류와 preflight/token boundary 회귀 | `ai/.venv/bin/python -m pytest -q ai/tests/test_llm_aoai.py ai/tests/test_live_provider_fail_closed.py ai/tests/test_research_request_preflight.py ai/tests/test_token_auth.py ai/tests/test_graph_e2e.py ai/tests/test_api.py ai/tests/contracts/test_api_envelope_contract.py ai/tests/contracts/test_openapi_contract.py ai/tests/test_research_contract.py ai/tests/test_research_contract_api.py` | PASS (152) |
| RMP-LINT-01 | S | changed API/contract/fixture/test files | `cd ai && .venv/bin/python -m ruff check --ignore BLE001 ai_graph/api.py ai_graph/research_contract.py tests/offline_test_environment.py tests/test_api.py tests/test_graph_e2e.py tests/test_research_contract.py tests/test_research_contract_api.py tests/contracts/test_openapi_contract.py` | PASS; the four ignored audit-boundary catches predate this change |
| RMP-R-01 | R | disposable PostgreSQL EOD source, result immutability, job replay/restart | isolated DB + two-process harness | BLOCKED: durable data/lifecycle implementation and isolated provenance are absent |
| RMP-O-01 | O | authenticated browser flow against isolated staging, API lifecycle/provenance | browser + isolated staging manifest | BLOCKED: same-SHA staging and non-secret provenance are absent |
| RMP-C-01 | C | worker/recovery capacity for confirmed jobs | cgroup-contained staging workload | BLOCKED: approved budget and durable worker lifecycle are absent |

The broad local `ai/tests` run is not an operational substitute: an unrelated integration test selected a live provider configuration and ended with a network connection failure. No environment value was inspected, and that command is recorded as **inconclusive**, not a product failure or an operational test.

## Explicit non-completion conditions

- A local mock/fixture/noop/in-memory result remains S-tier only and is never reported as production data.
- `ready`/`no_match` need a verified PostgreSQL EOD source with as-of, freshness, universe count, candidate count, and immutable result/version linkage.
- Confirmed execution needs durable claim/idempotency/quota/outbox/restart behavior before activation. The in-memory replay fence is intentionally insufficient for release.
- `RMP-PERF-01` remains owned by its performance/data lane. No performance number or chart has been added to this workspace.
- WBS rows remain `대기`/`증적대기` until evidence URI, same-SHA required tier, and independent reviewer decision are recorded by the authorized owner.
