# QuantAgent AI MVP

이 디렉터리는 QuantAgent AI/LLM MVP의 fixture/mock 기반 실행 표면이다.
외부 LLM 키, 증권 API, 네트워크 호출 없이 자연어 전략 분석부터 최종
API envelope 생성까지 e2e 테스트가 동작한다.

## 실행

```bash
cd ai
python3 -m pytest
python3 -m ruff check .
```

```bash
cd ai
python3 -m pip install -e .
AI_API_HOST=127.0.0.1
AI_API_PORT=8000
python3 -m uvicorn ai_graph.api:app --host "127.0.0.1" --port "8000" --reload
```

Swagger UI는 `http://$AI_API_HOST:$AI_API_PORT/docs`, OpenAPI JSON은
`http://$AI_API_HOST:$AI_API_PORT/openapi.json`에서 확인한다.

브라우저 FE에서 직접 호출할 때는 허용 origin을 환경변수로 주입한다.

```bash
AI_CORS_ALLOW_ORIGINS='http://localhost:5173,http://127.0.0.1:5173'
python3 -m uvicorn ai_graph.api:app --host "$AI_API_HOST" --port "$AI_API_PORT" --reload
```

공용 서버 PostgreSQL/TimescaleDB를 연결하려면 DB DSN을 환경변수로 주입한다.
DSN이 없으면 기존 fixture 경로로 실행되고, 내부 검증 payload에 fallback 이유가 남는다.

```bash
AI_DATABASE_DSN='postgresql://user:password@host:5432/quant_agent'
AI_DEFAULT_TICKER=005930
AI_BACKTEST_LOOKBACK_DAYS=252
AI_L4_EVIDENCE_LIMIT=5
python3 -m uvicorn ai_graph.api:app --host "$AI_API_HOST" --port "$AI_API_PORT" --reload
```

AI 운영 로그는 기본적으로 꺼져 있다. migration 013과 운영 DB 보안 검증을
완료한 환경에서만 PostgreSQL sink를 활성화한다.

```bash
AI_AUDIT_SINK=postgres
AI_AUDIT_CONNECT_TIMEOUT_SECONDS=2
AI_AUDIT_STATEMENT_TIMEOUT_MS=2000
```

DSN은 `AI_DATABASE_DSN`, `QUANT_DB_DSN`, `DATABASE_URL` 순서로 선택된다.
즉시 롤백은 `AI_AUDIT_SINK=noop`이다. migration, canary, 90일 삭제, TLS·backup
검증은 [AI 로깅 운영 런북](docs/ai-logging-operations.md)을 따른다.

AOAI Responses API는 opt-in이다. 기본값은 mock LLM이며, 아래 값이 모두 있을 때만
`httpx` 기반 AOAI client를 사용한다.

```bash
AI_LLM_PROVIDER=aoai
AI_AOAI_RESPONSES_URL='https://<resource>.cognitiveservices.azure.com/openai/responses?api-version=2025-04-01-preview'
AI_AOAI_API_KEY='<secret>'
AI_AOAI_MODEL='<deployment-or-model-name>'
AI_LLM_RESEARCH_BULL_MODEL='<mini-deployment>'
AI_LLM_RESEARCH_BEAR_MODEL='<mini-deployment>'
AI_LLM_RESEARCH_JUDGE_MODEL='<judge-deployment>'
AI_LLM_BACKTEST_CODE_MODEL='<code-deployment>'
AI_LLM_SIGNAL_BULL_MODEL='<mini-deployment>'
AI_LLM_SIGNAL_BEAR_MODEL='<mini-deployment>'
AI_LLM_SIGNAL_JUDGE_MODEL='<judge-deployment>'
AI_LLM_REPORT_BULL_MODEL='<mini-deployment>'
AI_LLM_REPORT_BEAR_MODEL='<mini-deployment>'
AI_LLM_REPORT_JUDGE_MODEL='<judge-deployment>'
python3 -m uvicorn ai_graph.api:app --host "$AI_API_HOST" --port "$AI_API_PORT" --reload
```

전체 예시는 `ai/.env.example`을 기준으로 한다. role별 model env가 비어 있으면
`AI_AOAI_MODEL`을 fallback으로 사용한다.

실제 AOAI 네트워크 smoke test는 기본 pytest에서 제외된다.

```bash
AI_LLM_PROVIDER=aoai \
AI_AOAI_LIVE_TEST=1 \
AI_AOAI_RESPONSES_URL='https://<resource>.cognitiveservices.azure.com/openai/responses?api-version=2025-04-01-preview' \
AI_AOAI_API_KEY='<secret>' \
AI_AOAI_MODEL='<deployment-or-model-name>' \
python3 -m pytest tests/test_llm_aoai_live.py
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
| Swagger/API | `ai_graph/api.py` | `/docs`, `/openapi.json`, `/health`, `/api-status`, `/analysis-jobs`, `/api/strategies/parse`, `/api/strategies/descriptions`, `/api/backtests/{strategy_id}`, `/api/reports/{id}` |
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

## Mock/Fixture 경계

| Mock | 실제 연동 필요 |
|---|---|
| `AI_LLM_PROVIDER=mock` | `AI_LLM_PROVIDER=aoai` + AOAI Responses env |
| local markdown KB | 운영용 벡터/검색 인덱스 |
| fixture price rows | 공용 DB `feature.kis_adjusted_ohlcv_daily` + `feature.ta_*_ticker_daily` 기반 가격/TA screening |
| fixture L4 evidence | `raw.analyst_report_summary` 기반 SEIBro raw evidence |
| in-memory debug/job store | DB/queue 기반 job store |

## Open Questions for Sprint 0

| 주제 | 합의 필요 |
|---|---|
| API path | `/analysis-jobs`의 실제 BE route와 auth 방식 |
| Storage | `internal_payload`/`debug_ref` 저장소와 retention |
| Data | KOSPI200 구성 종목, 수정주가, 거래정지/상폐 guard 출처 |
| LLM | AOAI deployment, retry, JSON mode, 비용/timeout 정책 |
| Risk | macro fixture를 대체할 실시간 KOSPI/FX/VKOSPI feed |

## TODO 우선순위

1. FastAPI adapter의 `InMemoryAnalysisJobStore`를 영속 job store로 교체.
2. L1/L2 KB를 파일 fixture에서 검색 인덱스로 승격.
3. OpenDART/BOK/SEIBro feature mart 적재 후 proxy 조건을 실제 재무/거시/컨센서스 필터로 교체.

## 완료된 항목

| 항목 | 구현 | 검증 |
|---|---|---|
| 실제 market data adapter와 백테스트 엔진 연결 | `AI_DATABASE_DSN` 설정 시 `mart.kis_adjusted_feature_frame_asof`에서 KIS 수정주가/TA feature를 읽어 `backtest_module` 엔진 입력으로 사용 | fixture fallback 및 매핑 테스트 통과. 공용 DB live 검증은 `AI_DATABASE_DSN` 필요 |
| AOAI `LLMClient` 구현과 prompt/schema contract test | `ai_graph/llm` provider interface, mock client, AOAI Responses thin client, env factory, backtest-code prompt schema | `httpx.MockTransport` unit test와 prompt/schema fallback test 통과. live AOAI는 `AI_AOAI_LIVE_TEST=1` opt-in |
| FE와 envelope field freeze 후 contract test 공유 | `AnalysisJob`, `APIEnvelope`, report projection, OpenAPI route/component contract tests | `tests/contracts/*` 통과 |
