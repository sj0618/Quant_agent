# QuantAgent AI MVP
이 디렉터리는 QuantAgent AI/LLM MVP의 로컬 결정론 프로필과 운영 실데이터 프로필을 함께 제공한다.
로컬에서는 외부 credential 없이 e2e 테스트가 동작하고, 운영에서는 PostgreSQL과 AOAI Responses API를 사용한다.

## 실행

### 로컬 점검
```bash
cd ai
python3 -m pytest
python3 -m ruff check .
```

### Rocky Native 저장소 밖 venv 설치 (권장)
```bash
WORKTREE_ROOT=$(readlink -f "$(git rev-parse --show-toplevel)")
AI_VENV_DIR=$(mktemp -d -t quantagent-ai-venv.XXXXXX)
MVP_VENV="$AI_VENV_DIR/venv"

python3 -m venv "$MVP_VENV"
"$MVP_VENV/bin/pip" install --upgrade pip
"$MVP_VENV/bin/pip" install -e "$WORKTREE_ROOT/backtest_module" -e "$WORKTREE_ROOT/ai"
```

### AI API 기본 실행 (loopback 18001, auth-off/mock/memory/noop)
```bash
AI_API_HOST=127.0.0.1
AI_API_PORT=18001
export AUTH_ENABLED=0 AI_LLM_PROVIDER=mock AI_JOB_STORE=memory AI_AUDIT_SINK=noop

# source-derived env 제어
DATA_SOURCE_ENV_KEYS=(
  AI_DATABASE_DSN QUANT_DB_DSN DATABASE_URL
  AI_DEFAULT_TICKER AI_BACKTEST_LOOKBACK_DAYS AI_L4_EVIDENCE_LIMIT
  AI_DB_CONNECT_TIMEOUT_SECONDS AI_DB_STATEMENT_TIMEOUT_MS
  AI_SECTOR_CACHE_TTL_SECONDS
)
for key in "${DATA_SOURCE_ENV_KEYS[@]}" BE_JOB_STORE_MODE REDIS_URL AUTH_SESSION_COOKIE_NAME AI_CORS_ALLOW_ORIGINS; do
  unset "$key"
done

env -i \
  PATH="$PATH" \
  HOME="${HOME:-/tmp}" \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  PYTHONUTF8=1 \
  AUTH_ENABLED=0 \
  AI_LLM_PROVIDER=mock \
  AI_JOB_STORE=memory \
  AI_AUDIT_SINK=noop \
  "$MVP_VENV/bin/python" -m uvicorn ai_graph.api:app \
    --app-dir "$WORKTREE_ROOT/ai" --host "$AI_API_HOST" --port "$AI_API_PORT"
```

Swagger UI는 `http://$AI_API_HOST:$AI_API_PORT/docs`, OpenAPI JSON은
`http://$AI_API_HOST:$AI_API_PORT/openapi.json`에서 확인한다.

브라우저 FE는 Vite의 `/ai-api` 프록시를 사용하므로 이 MVP에서 CORS 설정이 필요하지 않다.
AI API를 브라우저에서 직접 호출하는 별도 개발 점검에서만 정확한 loopback origin을 허용한다.

```bash
AI_CORS_ALLOW_ORIGINS='http://127.0.0.1:18000'
env -i \
  PATH="$PATH" \
  HOME="${HOME:-/tmp}" \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  PYTHONUTF8=1 \
  AI_CORS_ALLOW_ORIGINS="$AI_CORS_ALLOW_ORIGINS" \
  AUTH_ENABLED=0 AI_LLM_PROVIDER=mock AI_JOB_STORE=memory AI_AUDIT_SINK=noop \
  "$MVP_VENV/bin/python" -m uvicorn ai_graph.api:app \
    --app-dir "$WORKTREE_ROOT/ai" --host "$AI_API_HOST" --port "$AI_API_PORT"
```

공용 서버 PostgreSQL/TimescaleDB를 연결하려면 DB DSN을 child process에 전달한다.
DSN이 없으면 로컬 fixture 경로로 실행된다. DSN이 설정된 상태에서 연결이나 조회가 실패하면 fixture로 대체하지 않고 analysis job을 실패 처리한다. `/api-status`/응답에는 비밀값이 노출되지 않는다.
기본 연결 제한은 20초다. 대상 서버가 TLS를 제공하지 않는 것이 확인된 경우에만 DSN에
`sslmode=disable`을 추가해 불필요한 TLS 탐색 지연을 피한다. TLS를 제공하는 서버에는 이 옵션을 사용하지 않는다.
```bash
AI_DATABASE_DSN='postgresql://user:password@host:5432/quant_agent' \
AI_DEFAULT_TICKER=005930 \
AI_BACKTEST_LOOKBACK_DAYS=252 \
AI_L4_EVIDENCE_LIMIT=5 \
"$MVP_VENV/bin/python" -m uvicorn ai_graph.api:app \
  --app-dir "$WORKTREE_ROOT/ai" --host "$AI_API_HOST" --port "$AI_API_PORT"
```

AI 운영 로그는 기본적으로 꺼져 있다. 배포 workflow는 migration 011·013·019를 적용하고,
서버에서 생성한 signed admission과 `AI_AUDIT_PRODUCTION_ENABLED=1`을 AI process에만
주입해 PostgreSQL sink를 명시적으로 켠다. AOAI가 반환한 공개 assistant response 원문은
`assistant_response`, 구조화 응답의 summary 계열 필드에서 만든 축약본은
`assistant_response_summary`에 저장한다. provider가 공개하지 않는 내부 reasoning item은
저장하지 않는다.

DB audit 세션은 각 write transaction 직전에 signed admission의 expiry, claim integrity,
env-backed revocation state를 다시 확인한다. `active` 외의 값(`revoked`, 누락, 알 수 없는
값)은 fail-closed로 해당 raw write만 중단하고 AI 결과는 계속 반환한다.

DSN은 `AI_DATABASE_DSN`, `QUANT_DB_DSN`, `DATABASE_URL` 순서로 선택된다.
즉시 롤백은 `AI_AUDIT_SINK=noop`이며 migration, live audit smoke, TLS, backup,
retention 확인은 [AI 로깅 운영 런북](docs/ai-logging-operations.md)을 따른다.

AOAI Responses API는 opt-in이다. 기본값은 로컬 테스트용 mock LLM이며, 아래 값이 모두 있을 때
`httpx` 기반 AOAI client를 사용한다. `AI_LLM_PROVIDER=aoai`에서는 provider 오류, schema 오류, 안전한 코드 후보 부재를 결정론 fallback으로 숨기지 않고 analysis job 실패로 남긴다.
```bash
AI_LLM_PROVIDER=aoai \
AI_AOAI_RESPONSES_URL='https://<resource>.openai.azure.com/openai/v1/responses' \
AI_AOAI_API_KEY='<secret>' \
AI_AOAI_MODEL='<deployment-or-model-name>' \
AI_LLM_RESEARCH_BULL_MODEL='<mini-deployment>' \
AI_LLM_RESEARCH_BEAR_MODEL='<mini-deployment>' \
AI_LLM_RESEARCH_JUDGE_MODEL='<judge-deployment>' \
AI_LLM_BACKTEST_CODE_MODEL='<code-deployment>' \
AI_LLM_SIGNAL_BULL_MODEL='<mini-deployment>' \
AI_LLM_SIGNAL_BEAR_MODEL='<mini-deployment>' \
AI_LLM_SIGNAL_JUDGE_MODEL='<judge-deployment>' \
AI_LLM_REPORT_BULL_MODEL='<mini-deployment>' \
AI_LLM_REPORT_BEAR_MODEL='<mini-deployment>' \
AI_LLM_REPORT_JUDGE_MODEL='<judge-deployment>' \
"$MVP_VENV/bin/python" -m uvicorn ai_graph.api:app \
  --app-dir "$WORKTREE_ROOT/ai" --host "$AI_API_HOST" --port "$AI_API_PORT"
```

AOAI 설정은 위 명시적 환경변수만 사용한다. role별 model env가 비어 있으면
`AI_AOAI_MODEL`을 fallback으로 사용한다. v1 Responses URL은 기본적으로
`web_search` tool을 사용한다. 기존 preview URL은 `web_search_preview`를 유지하며,
필요하면 `AI_AOAI_WEB_SEARCH_TOOL_TYPE` 또는 역할별 동일 suffix로 명시적으로 덮어쓸 수 있다.

공개 배포에서는 `AUTH_ENABLED=1`과 `REDIS_URL`을 설정해 backend가 기록한 `qa_session`을 검증한다. `AUTH_ENABLED=0`은 loopback 로컬 개발 전용이며 실제 AOAI/DB API를 공개하는 설정으로 사용하지 않는다.

실제 AOAI 네트워크 smoke test는 기본 pytest에서 제외된다.
```bash
AI_LLM_PROVIDER=aoai \
AI_AOAI_RESPONSES_URL='https://<resource>.openai.azure.com/openai/v1/responses' \
AI_AOAI_API_KEY='<secret>' \
AI_AOAI_MODEL='<deployment-or-model-name>' \
"$MVP_VENV/bin/python" -m pytest tests/test_llm_aoai_live.py
```

```bash
cd ai
python3 - <<'PY'
from ai_graph import run_analysis

result = run_analysis("RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어")
print(result.model_dump(mode="json"))
PY
```

## 구현 범위
| 영역 | 주요 파일 | 계약 |
|---|---|---|
| 9-node graph | `ai_graph/graph.py` | Supervisor, Ambiguity, Data, Research, BacktestCode, Backtest, Signal, Risk Manager, Report 순서 |
| Swagger/API | `ai_graph/api.py` | `/docs`, `/openapi.json`, `/health`, `/api-status`, `/analysis-jobs`, `/api/strategies/parse`, `/api/strategies/descriptions`, `/api/backtests/{strategy_id}`, `/api/reports/{report_id}` |
| DB data source | `ai_graph/data_sources/db.py` | `feature.kis_adjusted_ohlcv_daily`, `feature.ta_*_ticker_daily`, `meta.view_common_stock_universe`, `core.symbol_master`(`symbol`/`sector` 섹터 보강), `raw.analyst_report_summary` |
| LLM provider | `ai_graph/llm/**` | env 기반 `mock`/`aoai` 선택, role별 AOAI deployment override, AOAI Responses JSON parsing |
| 공통 schema | `ai_graph/schemas.py`, `state.py` | StrategySpec, APIEnvelope, L4 evidence, polling stage, dual output |
| Job/polling | `ai_graph/jobs.py` | `interpreting`, `code_generation`, `backtest`, `debate`, `finalizing` 상태 |
| Retrieval | `ai_graph/retrieval/**` | L1 50+ 전략 KB, L2 150+ 지표 KB, Retrieve-then-Smooth 후보 카드 |
| Code security | `ai_graph/security/ast_validator.py` | allowlist import와 금지 함수/모듈 차단 |
| Backtest | `ai_graph/nodes/backtest_code.py`, `backtest.py` | Loop3 후보 신호를 `backtest_module` 엔진으로 실행하고 A/B 성과 최고 후보 선택 |
| Signal | `ai_graph/nodes/signal.py` | BUY/HOLD/DROP, mock 프로필의 결정론 fallback, L4 evidence fixture/SEIBro raw |
| Risk | `ai_graph/nodes/risk_manager.py` | KOSPI -5%, FX 2%, VKOSPI 30 룰 |
| Report | `ai_graph/nodes/report.py` | web_projection과 email_projection 동시 생성, 데이터 가용성/스크리닝 후보 섹션 |
| API contract | `docs/ai-api-contract.md` | FE/BE envelope와 debug_ref 경계 |

## API status / ready / clarification 계약 (MVP 고정)
- `GET /api-status`는 공용/민감값을 숨긴 상태계약을 반환한다.
  - `data_source.configured`, `data_source.dsn_env`, `data_source.price_source`,
    `data_source.l4_evidence_source`, `data_source.macro_usable` 확인.
  - `job_store.requested_mode`, `job_store.active_mode`, `job_store.mode_env`,
    `job_store.dsn_configured`, `job_store.fallback`, `job_store.fallback_reason` 확인.
  - DSN/secret 값은 응답 본문에 노출되지 않는다.
- `POST /analysis-jobs`는 `201`로 `AnalysisJob`을 반환한다.
  - `result.status`는 `ready | need_clarification | rejected | failed`.
  - `result.status == ready`:
    - `stages` 5개(`interpreting`..`finalizing`)가 채워짐.
    - `result.user_payload.performance`, `result.user_payload.report` 존재.
    - `internal_payload`, `node_outputs`, `llm_prompts` 미노출.
  - `result.status == need_clarification`:
    - `result.user_payload.question` 비어있지 않음.
    - `options`는 정확히 3개.
    - `candidate_cards`는 후보 카드 3개.
    - `result.user_payload.performance`, `result.user_payload.report`는 null.
- `GET /analysis-jobs/{job_id}`는 동일 `job_id/trace_id`의 결과를 반환한다.

## AI_JOB_STORE persistent 별도 게이트
- 기본 fixture는 `AI_JOB_STORE=memory`.
- `AI_JOB_STORE=persistent`는 명시적으로 요청 모드만 persistent로 기록하고,
  저장소/DSN 미구성 상태에서는 `/api-status`에서:
  - `requested_mode=persistent`
  - `active_mode=memory`
  - `fallback=true`
  - `fallback_reason`에 DSN/adapter 미구성 사유가 남는다.

## Mock/Fixture 경계
| 항목 | 동작 |
|---|---|
| `AI_LLM_PROVIDER=mock` | 로컬 결정론 fallback 허용 |
| `AI_LLM_PROVIDER=aoai` | AOAI Responses env 필수, provider/schema 실패 시 fail-closed |
| local markdown KB | 운영용 벡터/검색 인덱스 |
| fixture price rows | 공용 DB `feature.kis_adjusted_ohlcv_daily` + `feature.ta_*_ticker_daily` 기반 가격/TA screening |
| fixture L4 evidence | `raw.analyst_report_summary` 기반 SEIBro raw evidence |
| in-memory debug/job store | `AI_JOB_STORE=memory` |
| persistent gate | `AI_JOB_STORE=persistent`는 `/api-status`에서 requested/active/fallback로 추적 |

## PIT 유니버스: 1년 창 + 거래대금 상위 100종

> 멤버십은 `core.symbol_listing_history`(상장 구간) + `core.symbol_security_type_history`(보통주 분류)의 **창과 겹치는 구간**으로 정한다. `mart.common_stock_universe_asof` 뷰는 security-type 이력이 2026-08-11부터만 있어 그 이전 날짜에는 멤버를 하나도 돌려주지 않았고, 그래서 "5년 PIT 유니버스"가 사실상 오늘 상장 종목이었다(생존자 편향).

Data 노드는 5년치 전체 PIT 보통주(1,717종)를 올렸다. 그 한 건이 875초·21GB였고,
Backtest 노드는 raw 체결가가 없는 bar에서 `raw_execution_unavailable`로 죽었다.
좁힌 기준은 세 가지다.

- **창 길이**: `AI_BACKTEST_LOOKBACK_YEARS`(기본 1, `1~3` clamp). 마지막 완료 KST
  세션이 끝점이고, 길이는 정책 id `krx_pit_common_stock_{N}y_kst_settled_session_v3`에
  실린다. 짧게 읽었다는 사실이 매니페스트에 남지 않으면 재현이 아니라 그냥 다른 실행이다.
- **유니버스 상한**: `AI_BACKTEST_UNIVERSE_MAX_TICKERS`(기본 200).
  `mart.common_stock_universe_asof`에서 창에 속한 멤버를 모두 후보로 두되,
  **창 시작 시점에서 끝나는 60세션**의 평균 거래대금(`adj_close × adj_volume`)으로
  DB가 순위를 매겨 상위 N종만 적재한다. 랭킹·상한은 SQL 한 문장(CTE)에서 끝나고,
  descriptor에 `window_member_count` / `excluded_member_count`가 남는다.
- **raw 체결가**: `core.ohlcv_daily` 조인을 LEFT → INNER로 바꿨다. 엔진이 어차피
  거부하는 bar를 굳이 적재해 feature frame까지 끌고 갈 이유가 없다.

**왜 생존편향이 아닌가.** 잘라낸 기준은 "지금 상장돼 있는가"가 아니라 "창이 시작되기
전에 얼마나 거래됐는가"다.

- 창 **안에서** 상장폐지된 종목은 유니버스에 남는다. 가격 조인이 날짜 기준이라 폐지일까지의
  행을 그대로 갖고, 폐지 처리는 기존 정책(`official-event-then-final-close-v1`)을 따른다.
- 랭킹 구간이 창 **시작 시점에서 끝나므로**, 창 안에서 무슨 일이 있었는지는 선정에
  쓰이지 않는다. 창 안 수익률로 순위를 매기면 결과가 자기 유니버스를 고르게 된다.
- `core.symbol_master.listing_status` 필터는 **당일 스크리닝/추천에만** 건다. 오늘 살 수
  없는 종목을 추천하지 않기 위한 것이고, 같은 술어를 과거 유니버스에 걸면 그게 바로
  생존편향이다.
- 남는 한계: 창 시작 **이후** 신규 상장된 종목은 사전 거래대금이 없어 정렬 최후위
  (`NULLS LAST`)로 밀린다. 상한이 덜 찼을 때만 들어온다.

## backtest execution_timing 및 privacy 범위
- `backtest_module`은 현재 `execution_timing='next_open'`만 지원한다.
  - `next_close`는 현재 사양에서 값 검증 실패/예외(`ValueError`)로 처리된다.
- Privacy 범위:
  - 공개 `APIEnvelope`는 `status`, `trace_id`, `schema_version`, `user_payload`,
    `strategy_spec`, `debug_ref`, `retryable` 중심이다.
  - 공개 응답에 `internal_payload`, `node_outputs`, `llm_prompts`,
    DSN 실제 값, AOAI credential, raw source/validation trace는 남기지 않는다.
  - `debug_ref`는 내부 추적 키로만 사용한다.

## Open Questions for Sprint 0

| 주제 | 합의 필요 |
|---|---|
| 운영 통합 | 운영 API ingress에서 `/analysis-jobs` auth 처리 방식/권한 경계 |
| Storage | `internal_payload`/`debug_ref` 저장소와 retention |
| Data | KOSPI200 구성 종목, 수정주가, 거래정지/상폐 guard 출처 |
| LLM | AOAI deployment, retry, JSON mode, 비용/timeout 정책 |

## Post-MVP 후보(현재 범위 밖)

1. FastAPI adapter의 `InMemoryAnalysisJobStore`를 영속 job store로 교체.
2. L1/L2 KB를 파일 fixture에서 검색 인덱스로 승격.
3. OpenDART/BOK/SEIBro feature mart 적재 후 proxy 조건을 실제 재무/거시/컨센서스 필터로 교체.

## 완료된 항목

| 항목 | 구현 | 검증 |
|---|---|---|
| 실제 market data adapter와 백테스트 엔진 연결 | `AI_DATABASE_DSN` 설정 시 KIS 수정주가/TA feature를 읽어 `backtest_module` 엔진 입력으로 사용 | 로컬 fixture·매핑·configured-DB fail-closed 테스트 통과. 공용 DB live 성공 검증은 DSN 필요 |
| AOAI `LLMClient` 구현과 prompt/schema contract test | `ai_graph/llm` provider interface, mock client, AOAI Responses thin client, env factory, backtest-code prompt schema | `httpx.MockTransport` unit test와 prompt/schema fallback test 통과. live AOAI는 `AI_AOAI_LIVE_TEST=1` opt-in |
| FE와 envelope field freeze 후 contract test 공유 | `AnalysisJob`, `APIEnvelope`, report projection, OpenAPI route/component contract tests | `tests/contracts/*` 통과 |

## 2026-09-02 E2E 검증에서 확인한 사실 (자연어 입력 → 리포트 → 이메일)

### 운영 raw-query 경로가 1초 만에 실패하던 원인
- 배포 FE는 `POST /analysis-jobs`에 `{"query": ...}`만 보낸다. production에서는 admission 시점이 아니라
  job 안에서 `research_contract.build_rule_draft`가 실행 스펙을 봉인하고(`api.py` `_build_analysis_runner_with_audit`),
  그 결과를 `graph.run_analysis(execution_spec=...)`에 넘긴다.
- `ai_graph.research_contract`와 `ai_graph.schemas`는 **같은 JSON 모양의 V1/V2 실행 스펙 클래스를 각자 정의**한다
  (`research_contract.CanonicalRuleV1` = 그 모듈의 `StrategyExecutionSpecV1`, 두 모듈이 각각 `ExecutionSpecV1OrV2` union을 가짐).
  봉인된 `CanonicalRuleV1` 인스턴스를 `schemas.validate_execution_spec`의 TypeAdapter에 넣으면 pydantic이 외래 클래스로
  보고 `model_type` ValidationError를 내고, `jobs.classify_failure`가 이를 `contract_shape_error`로 분류했다.
  서버 `app.ai_analysis_job` 20건 중 9건이 이 경로로 노드 하나 실행되지 않고 실패했다(예: "RSI 30 이하일때 매수하고 70 이상일때 매도").
- 고친 방법: `schemas.validate_execution_spec`은 자기 클래스가 아닌 BaseModel을 `model_dump(mode="json")`으로 한 번 돌려 검증하고,
  runner도 dict로 넘긴다. 회귀 테스트는 `tests/test_raw_query_job_path.py`. **규칙: 두 모듈 경계는 객체가 아니라 JSON dict로 건넌다.**
  두 클래스 계층을 하나로 합치는 리팩터링은 범위 밖으로 남겨 두었다.

### 함께 바뀐 동작
- job 안 파싱이 실행 불가(clarification_required / unsupported_conditions / 후보 없음)이면 job은 실패가 아니라
  `result.status == need_clarification`으로 **완료**된다(question, options 3개, candidate_cards 3개). `debug_ref`는 `clarification:<trace_id>`.
  provider/schema 자체 오류는 여전히 `StrategyResearchError`로 실패한다.
- `CreateAnalysisJobRequest.query`는 공백만 있으면 422, 최대 2000자. `/api/strategies/parse`의 `query`/`natural_language`도 2000자.
- 실패한 job의 `stages[]`는 실제로 멈춘 단계를 `failed`로 표시한다(이전엔 항상 `finalizing`만 실패로 표시).
- `AI_ANALYSIS_QUEUE_WAIT_SECONDS` 기본값 600 → 1860 (job deadline 1800보다 길어야 한다는 주석대로).

### 로컬 재현 방법
```bash
AUTH_ENABLED=0 AI_LLM_PROVIDER=mock AI_JOB_STORE=memory AI_AUDIT_SINK=noop \
  python -m pytest -q ai/tests/test_raw_query_job_path.py
```
`AI_LLM_PROVIDER=mock`이라도 명시적 RSI 규칙은 결정론 파서를 타므로 운영과 같은 코드 경로가 실행된다.

## 전략 문법과 워크포워드 실행 세부 (2026-09-03)

배포 사이트에 실제 시연 입력을 흘려 막힌 지점을 고치면서 넓어진 실행 가능 문법과 V3 후보 타이밍 필드, 자기개선 라운드 실행 방식을 정리한다. 경과는 `docs/qa/e2e-flow-validation-20260902.md` §8.

### 지표·크로스·PER·섹터
- `sma{N}` / `ema{N}`: N은 2~250 어떤 정수든 된다(`ai_graph/nodes/condition_compiler.py` `moving_average_spec`). 웨어하우스가 발행하는 sma20/50/200은 그 컬럼을 그대로 쓰고, 나머지 창은 종가 시계열에서 즉석 계산한다 — "20일선이 60일선을 상향 돌파"의 sma60이 그 경우다.
- `cross_above` / `cross_below`: 임의의 두 지표 사이에 정의된다(`_compile_cross`). 직전 봉과 비교해 부호가 뒤집혔는지로 컴파일하며, MACD 골든/데드크로스와 이동평균 교차가 같은 경로를 탄다. 지표의 전일 값이 없으면(NaN) 교차를 근사하지 않고 보수적으로 거짓 처리한다.
- `per`: `raw_close / 최근 연간 EPS(report_code 11011, forward-fill)`로 PIT 지표에 추가했다(`ai_graph/data_sources/db.py`). EPS ≤ 0이면 값을 비워 둔다 — 분기 EPS(3개월치)를 그대로 나누면 PER이 4배씩 튄다. PBR은 아직 불가능(발행주식수/BPS가 웨어하우스에 없음).
- 섹터: `feature.wics_symbol_sector_history`(symbol_id, sector_name, valid_from, valid_to)를 구간 겹침으로 PIT 유니버스 CTE에 조인한다. 섹터명은 26개(예: 반도체 = 166종목). 리서처는 `allowed_sectors`를 받아 그 안에서만 sector를 써야 하며, 벗어나면 `research_sector_dropped`로 거부한다. 현재 모든 WICS 행이 2026-07-02부터 시작하는 단일 열린 구간이라 섹터 이력은 아직 진짜 point-in-time이 아니다.
- 공유 지점: 어떤 operand(별칭 `bollinger_lower`, boolean 지표 `close_cross_above_sma20` 포함)가 실제로 어떤 raw 지표를 필요로 하는지는 `condition_metric_inputs`(`condition_compiler.py`) 한 곳에서만 계산하고, `db.py`의 `indicator_families_for_metrics`와 `nodes/backtest_features.py`가 그 결과로 로드할 지표 패밀리를 정한다. 예전에는 이 확장이 없어 볼린저·`close_above_sma_200`류 조건이 지표를 한 번도 못 읽고 "검증 불가"로 떨어졌다.

### V3 후보의 타이밍 필드
`ResearchCandidateV3`(`ai_graph/schemas.py`)에 `holding_days`(1~250)와 `rebalance_interval_days`(5~63, 기본 21 ≈ 한 달)가 있다.
- `holding_days`: 진입 후 N세션 뒤 무조건 청산. `exit_conditions`가 비어 있어도 되지만 둘 중 하나는 있어야 한다(`rule_states_an_exit` 검증).
- `rebalance_interval_days`: `execution_mode="scheduled_rotation"`일 때 의미가 있고, 그 간격마다 진입 규칙을 다시 평가해 더 이상 만족하지 않는 보유 종목을 교체한다.
- 이전에는 "5일 뒤 매도"를 표현할 방법이 없어 `close >= 0`(항상 참)으로 흉내 냈고, 매 봉마다 팔아 거래 717건이 나왔다. 지금은 evaluator가 종목별 `sessions_held`를 추적해 정확히 N세션 뒤 청산하고, validation이 항상 참인 exit을 repairable 오류로 거부한다.

### 잡담은 리서치 호출 전에 끝낸다
`classify_query`가 `AmbiguityCode.NO_STRATEGY_INTENT`로 분류하면(`research_contract.py`, `api.py`) 리서치 호출 없이 "어떤 투자 전략이나 매매 조건을 분석할까요?" 질문으로 바로 끝낸다. "안녕"은 예전에 "automatic"으로 분류돼 ~26초짜리 web-grounded V3 리서치를 태우고도 범용 옵션 3개짜리 clarification으로 끝났다.

### 워크포워드 자기개선: 메모이제이션과 병렬 실행
자기개선 라운드는 후보를 늘려 워크포워드 전체를 다시 돌리는데, 예전에는 라운드마다 모든 후보를 모든 폴드에 다시 채점했다(6개씩 늘어나는 3라운드가 21개 분량을 지불). 지금은 `nodes/backtest.py`의 세션이 폴드 엔진 실행을 `(candidate, fold, pass)` 키로 캐시해서, 새 라운드는 새로 추가된 후보만 실제로 돌린다. 폴드 준비(시세, feature store, prepared market)는 폴드당 한 번만 만들어 워커 간에 공유하고, 폴드 태스크는 기존 `ProcessPoolExecutor`에서 순서 무관하게 실행된다. selection-width 디플레이션 항은 여전히 게시되지만 워크포워드에서는 더 이상 floor를 막지 않는다 — 폴드마다 이미 train/validation만으로 후보를 뽑으므로 롤링 OOS 집계 자체가 out-of-sample이고, 디플레이션까지 걸면 같은 탐색을 두 번 벌주는 셈이 된다.

env 노브(모두 `nodes/backtest.py`): `AI_BACKTEST_WORKERS`, `AI_BACKTEST_ALLOW_SPAWN_PARALLEL`, `AI_BACKTEST_CANDIDATE_TIMEOUT_SECONDS`, `AI_BACKTEST_WALL_BUDGET_SECONDS`(기본 22초). node3 실측: backtest 노드 11.8초/0라운드 → 21.5~25.9초/1라운드, 전체 43~50초(mock LLM).

> 주의: `condition_compiler`가 만드는 `build_signals` 소스는 감사·표시용으로 생성되는 템플릿일 뿐, 실제로 백테스트를 실행하는 evaluator가 아니다. 실행은 `nodes/backtest_features.py`의 `PreparedFeatureStore`(`_base_condition_matches` 등)가 담당한다.
