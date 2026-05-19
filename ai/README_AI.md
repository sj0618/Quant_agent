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
| 공통 schema | `ai_graph/schemas.py`, `state.py` | StrategySpec, APIEnvelope, L4 evidence, polling stage, dual output |
| Job/polling | `ai_graph/jobs.py` | `interpreting`, `code_generation`, `backtest`, `debate`, `finalizing` 상태 |
| Retrieval | `ai_graph/retrieval/**` | L1 전략 KB, L2 지표 KB, Retrieve-then-Smooth 후보 카드 |
| Code security | `ai_graph/security/ast_validator.py` | allowlist import와 금지 함수/모듈 차단 |
| Backtest | `ai_graph/nodes/backtest_code.py`, `backtest.py` | A/B StrategySpec와 Loop3 후보 중 Sharpe 최고 선택 |
| Signal | `ai_graph/nodes/signal.py` | BUY/HOLD/DROP, Bull/Bear/Judge, L4 evidence fixture |
| Risk | `ai_graph/nodes/risk_manager.py` | KOSPI -5%, FX 2%, VKOSPI 30 룰 |
| Report | `ai_graph/nodes/report.py` | web_projection과 email_projection 동시 생성 |
| API contract | `docs/ai-api-contract.md` | FE/BE envelope와 debug_ref 경계 |

## Mock/Fixture 경계

| Mock | 실제 연동 필요 |
|---|---|
| `MockBacktestCodeLLM` | OpenAI/Azure OpenAI LLM client |
| local markdown KB | 운영용 벡터/검색 인덱스 |
| mock A/B metrics | 실가격 백테스트 엔진 |
| fixture L4 evidence | 한경컨센서스, KIS 외국인 순매도, optional 영문 IB 검색 |
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

1. FastAPI/BE adapter에서 `InMemoryAnalysisJobStore`를 영속 job store로 교체.
2. 실제 market data adapter와 백테스트 엔진 연결.
3. AOAI `LLMClient` 구현과 prompt/schema contract test 추가.
4. L1/L2 KB를 파일 fixture에서 검색 인덱스로 승격.
5. FE와 envelope field freeze 후 contract test를 공유.
