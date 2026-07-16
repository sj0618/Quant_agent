# QuantAgent AI MVP
이 디렉터리는 QuantAgent AI/LLM MVP의 fixture/mock 기반 실행 표면이다.
외부 LLM 키, 증권 API, 네트워크 호출 없이 자연어 전략 분석부터 최종
API envelope 생성까지 e2e 테스트가 동작한다.

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
  AI_SCREENING_LIMIT AI_SCREENING_BACKTEST_SELECTION_LIMIT
  AI_PORTFOLIO_BACKTEST_TICKER_LIMIT AI_SECTOR_CACHE_TTL_SECONDS
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

공용 서버 PostgreSQL/TimescaleDB를 연결하려면 DB DSN/fixture 변수는 child process에 inline으로 전달한다.
DSN이 없으면 공개 fixture 경로로 실행되고, `/api-status`/응답에서 비밀값 비노출이 유지되어야 한다.
```bash
AI_DATABASE_DSN='postgresql://user:password@host:5432/quant_agent' \
AI_DEFAULT_TICKER=005930 \
AI_BACKTEST_LOOKBACK_DAYS=252 \
AI_L4_EVIDENCE_LIMIT=5 \
"$MVP_VENV/bin/python" -m uvicorn ai_graph.api:app \
  --app-dir "$WORKTREE_ROOT/ai" --host "$AI_API_HOST" --port "$AI_API_PORT"
```

AI 운영 로그는 기본적으로 `noop`이다. PostgreSQL sink는 signed Gate B admission 변수
6개, migration, TLS·backup, retention, canary row 검증을 모두 요구하며 이 fixture MVP
범위에서 활성화하지 않는다. `AI_AUDIT_SINK=postgres`와 DSN만 설정하면 admission이
거부되어 `NoOpAuditSink`로 fail-open하므로 운영 활성화 성공으로 간주하면 안 된다.

기존 [AI 로깅 운영 런북](docs/ai-logging-operations.md)은 migration, canary, TLS,
backup, retention 확인에만 사용한다. signed admission 발급·서명·만료·주입 절차는
현재 문서와 fixture MVP 범위에서 제공하지 않으므로 PostgreSQL audit를 활성화하지
않는다. 이 MVP의 고정값은 `AI_AUDIT_SINK=noop`이다.

AOAI Responses API는 opt-in이다. 기본값은 mock LLM이며, 아래 값이 모두 있을 때만
`httpx` 기반 AOAI client를 사용한다.
```bash
AI_LLM_PROVIDER=aoai \
AI_AOAI_RESPONSES_URL='https://<resource>.cognitiveservices.azure.com/openai/responses?api-version=2025-04-01-preview' \
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
`AI_AOAI_MODEL`을 fallback으로 사용한다.

실제 AOAI 네트워크 smoke test는 기본 pytest에서 제외된다.
```bash
AI_LLM_PROVIDER=aoai \
AI_AOAI_RESPONSES_URL='https://<resource>.cognitiveservices.azure.com/openai/responses?api-version=2025-04-01-preview' \
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
| DB data source | `ai_graph/data_sources/db.py` | `feature.kis_adjusted_ohlcv_daily`, `feature.ta_*_ticker_daily`, `meta.view_common_stock_universe`, `raw.analyst_report_summary` |
| LLM provider | `ai_graph/llm/**` | env 기반 `mock`/`aoai` 선택, role별 AOAI deployment override, AOAI Responses JSON parsing |
| 공통 schema | `ai_graph/schemas.py`, `state.py` | StrategySpec, APIEnvelope, L4 evidence, polling stage, dual output |
| Job/polling | `ai_graph/jobs.py` | `interpreting`, `code_generation`, `backtest`, `debate`, `finalizing` 상태 |
| Retrieval | `ai_graph/retrieval/**` | L1 50+ 전략 KB, L2 150+ 지표 KB, Retrieve-then-Smooth 후보 카드 |
| Code security | `ai_graph/security/ast_validator.py` | allowlist import와 금지 함수/모듈 차단 |
| Backtest | `ai_graph/nodes/backtest_code.py`, `backtest.py` | Loop3 후보 신호를 `backtest_module` 엔진으로 실행하고 A/B 성과 최고 후보 선택 |
| Signal | `ai_graph/nodes/signal.py` | BUY/HOLD/DROP, role별 Bull/Bear/Judge fallback, L4 evidence fixture/SEIBro raw |
| Risk | `ai_graph/nodes/risk_manager.py` | KOSPI -5%, FX 2%, VKOSPI 30 룰 |
| Report | `ai_graph/nodes/report.py` | web_projection과 email_projection 동시 생성, 데이터 가용성/스크리닝 후보 섹션 |
| API contract | `docs/ai-api-contract.md` | FE/BE envelope와 debug_ref 경계 |

## API status / ready / clarification 계약 (MVP 고정)
- `GET /api-status`는 공용/민감값을 숨긴 상태계약을 반환한다.
  - `data_source.configured`, `data_source.dsn_env`, `data_source.price_source`,
    `data_source.universe_source`, `data_source.l4_evidence_source`, `data_source.macro_usable` 확인.
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
| `AI_LLM_PROVIDER=mock` | `AI_LLM_PROVIDER=aoai` + AOAI Responses env가 있어야만 AOAI 사용 |
| local markdown KB | 운영용 벡터/검색 인덱스 |
| fixture price rows | 공용 DB `feature.kis_adjusted_ohlcv_daily` + `feature.ta_*_ticker_daily` 기반 가격/TA screening |
| fixture L4 evidence | `raw.analyst_report_summary` 기반 SEIBro raw evidence |
| in-memory debug/job store | `AI_JOB_STORE=memory` |
| persistent gate | `AI_JOB_STORE=persistent`는 `/api-status`에서 requested/active/fallback로 추적 |

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
| 실제 market data adapter와 백테스트 엔진 연결 | `AI_DATABASE_DSN` 설정 시 `mart.kis_adjusted_feature_frame_asof`에서 KIS 수정주가/TA feature를 읽어 `backtest_module` 엔진 입력으로 사용 | fixture fallback 및 매핑 테스트 통과. 공용 DB live 검증은 `AI_DATABASE_DSN` 필요 |
| AOAI `LLMClient` 구현과 prompt/schema contract test | `ai_graph/llm` provider interface, mock client, AOAI Responses thin client, env factory, backtest-code prompt schema | `httpx.MockTransport` unit test와 prompt/schema fallback test 통과. live AOAI는 `AI_AOAI_LIVE_TEST=1` opt-in |
| FE와 envelope field freeze 후 contract test 공유 | `AnalysisJob`, `APIEnvelope`, report projection, OpenAPI route/component contract tests | `tests/contracts/*` 통과 |