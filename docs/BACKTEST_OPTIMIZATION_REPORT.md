# QuantAgent 백테스트 성능·정확성 최적화 보고서

작성일: 2026-07-23
대상: `ai` 백테스트 후보 생성·평가 경로와 `backtest_module` 실행 엔진

## 1. 결과 요약

기존 구조는 LLM이 후보마다 완전한 Python 프로그램을 만들고, 각 프로그램이 전체
가격 행을 다시 순회한 뒤, 백테스트 엔진도 후보마다 시장 인덱스와 객체를 다시 만들고
QuantStats·Monte Carlo까지 전부 실행했다.

변경 후에는 LLM이 하나의 `StrategyIR`과 정확히 3개의 작은
`CandidateParameters`만 반환한다. 검증된 고정 실행기가 가격 데이터를 한 번 정렬하고,
공통 rolling feature를 NumPy 배열에 한 번 계산하여 모든 후보가 재사용한다. 1차 후보
선별은 경량 지표만 계산하고, QuantStats·Monte Carlo는 최종 선택 후보 한 개에만
실행한다.

운영 유사 합성 입력 203종목 × 2,520거래일 = 511,560행의 최종 로컬 실측은 다음과 같다.

| 실행 | wall time | 평균/최대 process-tree CPU | peak process-tree RSS | canonical SHA-256 |
|---|---:|---:|---:|---|
| fresh, 1 worker | 49.910초 | 98.969% / 114.7% | 1.204 GiB | `6c8c398a…e40b3` |
| fresh, 2 workers | 45.923초 | 73.994% / 114.7% | 3.591 GiB | `6c8c398a…e40b3` |
| disk cache hit, 1 worker | 13.583초 | fresh와 같은 측정 세션 | 1.204 GiB 이하 | `6c8c398a…e40b3` |

기존 운영 관측치인 “초기 후보 3개에 1시간 이상”을 하한 3,600초로 잡으면,
변경 후 1 worker는 최소 72.1배, 2 workers는 최소 78.4배 빠르다. 단, 기존 수치는
실제 운영 관측이고 변경 후 수치는 동일 규모의 결정론적 로컬 합성 데이터이므로,
이 수치는 엄밀한 동일 머신 A/B가 아니라 목표 달성 여부를 보는 보수적 비교다.

같은 로컬 머신·같은 데이터에서 신호 생성 코드 경로만 직접 A/B한 결과는 다음과 같다.

| 입력 | 기존 후보별 slicing 구현 | 구조화 공통 feature 구현 | 배속 | action SHA-256 |
|---|---:|---:|---:|---|
| 20종목 × 252일, 5,040행 | 0.337초 | 0.173초 | 1.95배 | 동일 |
| 203종목 × 2,520일, 511,560행 | 26.085초 | 18.419초 | 1.42배 | 동일 |

전체 파이프라인 가속 폭이 신호 단계 단독 가속보다 큰 이유는 신호 계산뿐 아니라
후보별 dict/Pydantic 생성, 시장 인덱스 재구축, QuantStats·Monte Carlo 반복 실행도
함께 제거했기 때문이다.

## 2. 실제 원인

1. 프롬프트가 3~12개의 완전한 `build_signals` 프로그램을 요구했다.
2. 후보 코드는 각 행에서 `closes[-window:]`, `sum`, `max`, `min`과 수익률 배열 생성을
   반복했다. 시간 복잡도는 사실상 `O(후보 × 행 × lookback)`이었다.
3. 후보마다 원본 행을 dict로 다시 다루고, 행별 신호를 Pydantic 객체로 검증했다.
4. 백테스트 엔진이 후보마다 OHLCV/metric 정규화, ticker/date 인덱스, snapshot,
   decision, audit 객체를 다시 만들었다.
5. 모든 후보에 QuantStats 전체 지표와 Monte Carlo를 실행했다.
6. 프로세스 풀은 후보를 병렬화했지만 Windows `spawn`에서는 큰 시장 데이터를 worker별로
   복제했고, 작은 입력도 프로세스 시작 비용을 냈다.
7. 세션 메모리 캐시는 있었지만 프로세스 간 재사용이 없었고, 정규화된 IR 기준 중복 제거와
   강한 무효화 키가 없었다.
8. AST 검사는 보안 중심이라 중첩 반복, loop 안 slicing 집계, 과도한 코드/AST 크기,
   비종료 `while`을 성능 위험으로 차단하지 못했다.

## 3. 변경 전·후 아키텍처

### 변경 전

```text
StrategySpec
  -> AOAI: Python 전체 코드 3~12개
  -> 후보별 AST 검사
  -> 후보별 build_signals 전체 행 실행
  -> 후보별 dict/Pydantic Signal 생성
  -> 후보별 OHLCV/metric/index/snapshot 재생성
  -> 후보별 전체 엔진 + QuantStats + Monte Carlo
  -> 최고 후보 선택
  -> 자기개선 후보를 만들고 같은 작업 반복
```

### 변경 후

```text
StrategySpec / screening structured conditions
  -> AOAI: StrategyIR 1개 + CandidateParameters 정확히 3개
  -> 원래 StrategySpec 조건으로 IR 정규화
  -> 정규화 IR/파라미터 SHA로 중복 제거
  -> 세션당 가격 정렬·ticker/date index 1회
  -> lookback별 공통 immutable NumPy feature matrix 1회
  -> 후보별 compact int8 action 배열
  -> 준비된 시장 인덱스를 재사용하는 경량 엔진 평가
  -> 세션 메모리/프로세스 간 디스크 캐시
  -> 경량 점수로 후보 선택
  -> 선택 후보 1개만 QuantStats + Monte Carlo + 상세 결과
```

Python fallback은 IR로 표현할 수 없는 전략에만 허용한다. fallback 코드는 AST 검사 후
별도 프로세스에서 격리 실행하며, 후보별 180초 기본 timeout을 초과하면 worker를
종료하고 안전한 실패 결과로 바꾼다. 기존 v1 LLM 응답은 한 번만 검증 피드백을 주어
재생성하고, 안전할 때만 이 fallback 경로로 수용한다.

## 4. 수정 파일과 핵심 변경

### `ai/ai_graph/llm/prompts.py`

- 스키마를 `backtest_code_candidates.v1`에서
  `backtest_strategy_candidates.v2`로 변경했다.
- 3~12개 Python 문자열 대신 `StrategyIR` 1개와 정확히 3개 파라미터 객체를 요구한다.
- 검증된 O(N) fallback 예시, 결정론, 종목별 상태 격리, 미래 참조 금지,
  loop 내부 slicing/집계 금지를 프롬프트에 포함했다.
- `response_schema`를 AOAI 요청에 직접 전달한다.

### `ai/ai_graph/nodes/backtest_code.py`

- 초기 후보 수를 정확히 3개로 제한했다.
- 모델이 조건을 바꾸더라도 원래 `StrategySpec.entry_conditions`와
  `exit_conditions`를 IR에 다시 적용한다.
- 후보 차이는 profile, lookback, threshold, stop/take-profit,
  max positions에만 둔다.
- 정규화한 IR/파라미터 hash로 중복 후보를 제거한다.
- 자기개선은 라운드당 최대 6개, 최대 2라운드로 실제 생성 루프에서 제한한다.
- v1 Python 응답 호환은 안전 검증·1회 재생성·프로세스 격리 fallback으로만 유지한다.
- 생성된 `code` 필드는 실행 원본이 아니라 사람이 확인할 수 있는 O(N) 참조 구현이다.

### `ai/ai_graph/nodes/backtest_features.py`

- 새 `PreparedFeatureStore`를 추가했다.
- 행을 날짜·ticker로 한 번 정렬하고 close/volume/RSI를 read-only NumPy 배열로 만든다.
- ticker 인덱스, date range, previous index를 한 번 계산한다.
- 평균·수익률·변동성은 prefix sum, high/low는 monotonic deque로 O(N)에 계산한다.
- 임의 `avg/sum/max/min/last` rolling도 현재 행을 제외한 과거 데이터만 O(N)에 계산한다.
- profile 후보는 공통 feature matrix를 공유하고 결과는 `array('b')`의
  BUY=1, SELL=-1, HOLD=0으로 저장한다.
- compiled 조건은 scalar, BETWEEN, CROSS_ABOVE/BELOW, consecutive,
  cross-sectional rank 조건을 처리한다.

### `ai/ai_graph/nodes/backtest.py`

- `_CandidateBacktestSession`이 feature store, 준비된 시장 데이터, worker pool,
  메모리 캐시를 자기개선 라운드 전체에서 재사용한다.
- 후보 평가 결과에 wall time, CPU time, peak RSS, 입력 행, 신호 수,
  cache hit/level을 기록한다.
- 전체 라운드에 new/cached/cumulative candidates와 wall time을 기록한다.
- 1차 평가에서는 native 경량 Sharpe/return/drawdown만 사용한다.
- 최종 후보 한 개만 full metrics로 재평가한다.
- 정규화된 후보 identity로 중복 평가를 제거하고 요청 순서로 결과를 복원한다.
- 작은 입력은 직접 실행한다. 큰 입력은
  `min(AI_BACKTEST_WORKERS, CPU 수, 신규 후보 수)`로 제한된 단일 pool을 사용한다.
- 기본 worker=2, 후보 timeout=180초, 전체 wall budget=540초다.
- timeout 시 futures를 취소하고 실제 worker process를 terminate/join한다.

### `backtest_module/backtest_module/backtest.py`

- `PreparedMarketData`로 OHLCV/metric/date/ticker 인덱스를 후보 간 재사용한다.
- `generated_actions` compact 배열을 직접 받아 Snapshot/SignalDecision 생성을 우회한다.
- `metrics_mode="selection"|"full"`을 추가했다.
- selection은 경량 결정론적 지표, full은 기존 QuantStats·Monte Carlo를 사용한다.
- 거래, 체결 타이밍, 비용 모델, position sizing, audit 의미는 유지했다.

### `ai/ai_graph/security/ast_validator.py`

- source 20,000자, AST 1,500 node, depth 40, loop node 8,
  literal range 10,000 상한을 추가했다.
- `while`, 과도한 중첩 loop, loop 안 `sum/max/min(slice)`를 차단한다.
- 기존 import, filesystem, OS, subprocess, eval/exec/reflection 차단을 유지한다.

### `ai/ai_graph/llm/aoai.py`

- logical call과 실제 HTTP POST 수를 분리해 기록한다.
- 첫 header, 첫 의미 있는 text, 완료 시간을 따로 기록한다.
- HTTP header 도착만으로 10초 response-start 조건을 만족시키지 않는다.
- 첫 non-empty text 전까지 짧은 read timeout과 wall-clock 제한을 유지한다.
- priority service tier 사용과 미지원 시 한 번의 호환 재시도를 유지한다.

### 테스트·벤치마크

- `ai/tests/test_backtest_optimization.py`
- `ai/scripts/benchmark_backtest_optimization.py`
- `ai/scripts/benchmark_signal_path_comparison.py`
- 관련 prompt, AST, AOAI, integration, position sizing 테스트 갱신
- 오래된 public envelope/research web-search 계약 테스트를 현재 공개 스키마와
  단일 screening research 호출 구조에 맞게 갱신

## 5. 프롬프트 변경 전문

### 변경 전 v1

```text
You are QuantAgent's backtest-code generation node.
Return only JSON that conforms to the requested schema.
Each candidate must define a pure Python function named build_signals(prices).
The function must return date/action/price dictionaries and use only supplied price rows.
Generate strategy-specific logic from StrategySpec instead of falling back to RSI unless RSI is explicitly requested.
When a requested fundamental, consensus, flow, macro, or disclosure metric is absent from price rows,
use a clearly named OHLCV proxy that still reflects the StrategySpec assumption.
Do not require a full 20/52/120-day warm-up before emitting any signal; use the available partial lookback
so fixture and short-window validation cannot silently return all HOLD.
Do not import network, filesystem, subprocess, OS, eval, exec, or reflection APIs.
```

```json
{
  "task": "Generate three to twelve build_signals Python implementations.",
  "variant": "<A|B>",
  "strategy_spec": "<StrategySpec JSON>",
  "expected_json_schema": {
    "candidates": "list[str], min 3, max 12",
    "fallback_reasons": "list[str]"
  },
  "output_contract": {
    "candidates": "array of three to twelve Python code strings",
    "fallback_reasons": "array of strings, empty when generation succeeded"
  },
  "quality_checks": [
    "Use build_signals as the top-level entrypoint; keep any helper functions nested and do not define classes.",
    "Avoid imports; if needed, use only datetime, math, or statistics.",
    "Do not use eval, exec, open, reflection, network, filesystem, subprocess, or OS APIs.",
    "Each candidate should emit one signal per supplied price row.",
    "At least one candidate should be capable of BUY/SELL/WATCH-equivalent behavior on a short fixture.",
    "The code should reference the StrategySpec's main indicators or documented OHLCV proxies.",
    "Avoid unconditional empty lists, unconditional HOLD, or warm-up gates that skip all short fixtures."
  ]
}
```

검증 실패 시 task는 다음 문장으로 바뀌었다.

```text
Regenerate three to twelve build_signals implementations that correct every listed validation failure.
```

### 변경 후 v2

```text
You are QuantAgent's structured backtest-strategy generation node.
Return only JSON that conforms to the requested schema.
Return one StrategyIR and exactly three bounded CandidateParameters objects.
Reuse entry_conditions and exit_conditions already present in StrategySpec; do not restate
the same strategy as three Python programs. Vary only profile, lookback, threshold, stop loss,
take profit, and max positions.
Choose profile="compiled_conditions" when the supplied conditions are expressible by StrategyIR.
Use a clearly named OHLCV proxy only when a requested metric is absent, and preserve that mapping
in proxy_feature. Python fallback_code is exceptional: use it only when StrategyIR cannot express
the user strategy, and explain why in fallback_reasons.

Any fallback build_signals implementation must be deterministic, keep state per ticker, emit one
signal per input row, and make one chronological pass. Target O(N), at worst O(N log N), with O(N)
additional memory. Never scan or filter all prices from inside the row loop. Never use nested
full-data loops, unbounded slicing, or sum/max/min over a growing history inside a loop. Rolling
values must use incremental state or supplied precomputed columns. Do not use future rows or mix
history across tickers. Do not import network, filesystem, subprocess, OS, eval, exec, reflection,
or concurrency APIs.

Verified O(N) fallback shape:
def build_signals(prices):
    signals = []
    previous_by_ticker = {}
    for row in prices:
        ticker = str(row.get("ticker", "000000"))
        close = float(row["close"])
        previous = previous_by_ticker.get(ticker)
        action = "HOLD"
        if previous is not None:
            action = "BUY" if close > previous else "SELL" if close < previous else "HOLD"
        signals.append({"date": row["date"], "ticker": ticker, "action": action, "price": close})
        previous_by_ticker[ticker] = close
    return signals
```

```json
{
  "task": "Generate one StrategyIR and exactly three CandidateParameters objects.",
  "variant": "<A|B>",
  "strategy_spec": "<StrategySpec JSON>",
  "expected_json_schema": {
    "strategy_ir": "StrategyIR",
    "candidates": "list[CandidateParameters], exactly 3",
    "fallback_code": "list[str], max 3",
    "fallback_reasons": "list[str]"
  },
  "output_contract": {
    "strategy_ir": "one normalized strategy rule shared by all candidates",
    "candidates": "exactly three bounded parameter objects",
    "fallback_code": "zero to three Python strings; only for unrepresentable StrategyIR",
    "fallback_reasons": "array of strings, empty when generation succeeded"
  },
  "quality_checks": [
    "Reuse StrategySpec entry_conditions and exit_conditions in StrategyIR.",
    "Keep the candidate count equal to the evaluator limit of three.",
    "Vary parameters, not duplicated program text.",
    "Keep lookback between 3 and 252 and preserve supplied risk constraints.",
    "Use compiled_conditions when StrategyIR can represent the user rule.",
    "Document any OHLCV proxy in proxy_feature.",
    "Use fallback_code only when the structured rule cannot represent the strategy."
  ]
}
```

검증 실패 시 task는 다음 문장으로 바뀐다.

```text
Regenerate one StrategyIR and exactly three parameter candidates that correct every listed validation failure.
```

## 6. 캐시 키와 무효화 규칙

디스크 캐시 키는 다음 값을 정렬된 JSON으로 직렬화한 SHA-256이다.

```text
cache_schema
engine_version
feature_version
data_version = 전체 정규화 행 내용 SHA-256
universe = row count, ticker count, ticker-set SHA, first/last date
strategy_sha = 전체 StrategySpec SHA-256
candidate_sha = normalized StrategyIR + CandidateParameters SHA-256
validation_ok
metrics_mode = selection | full
```

따라서 데이터 값, 종목 집합, 기간, 전략 조건, 후보 파라미터, feature 정의, 엔진,
검증 상태, 지표 단계 중 하나라도 달라지면 hit가 나지 않는다.

- 세션 메모리 캐시와 프로세스 간 디스크 캐시를 구분한다.
- 기본 경로: OS temporary directory의 `quantagent-backtest-v2`
- 기본 TTL: 1일
- 기본 용량: 2 GiB
- 쓰기: temporary file 작성 후 atomic `os.replace`
- 읽기: schema/version/Pydantic 검증 실패나 손상 JSON은 삭제 후 miss 처리
- 시작 시: TTL 초과 파일 삭제 후 오래된 순서로 용량 상한까지 정리
- PostgreSQL을 임시 캐시로 사용하지 않는다.

production-like fresh run은 캐시 1,858,609 bytes를 썼다. 이어진 동일 실행은
selection 3개와 full 1개가 모두 disk hit였고 `new_candidates=0`이었다.

## 7. 병렬 실행 정책

1. 후보 내부에는 executor가 없다. 병렬화는 `_CandidateBacktestSession` 한 곳뿐이다.
2. 신규 후보만 executor에 제출한다.
3. worker 수는 신규 후보, OS CPU 수, `AI_BACKTEST_WORKERS` 중 최솟값이다.
4. `candidate_count × row_count < 250,000`이면 직접 실행한다.
5. pool은 자기개선 라운드와 최종 full 평가까지 재사용한다.
6. POSIX에서는 `fork`의 copy-on-write를 사용하고, Windows에서는 `spawn` 시
   초기화 데이터 전송을 pool 생성 한 번으로 제한한다.
7. 결과는 입력 후보 순서로 복원하고 tie-break 순서는 고정한다.

Arrow/Parquet, DuckDB, SQLite, NumPy memmap, shared memory를 비교했으나 현재 범위에서는
추가 파일 수명·정리·schema 관리보다 장기 pool + POSIX copy-on-write가 단순하고
안정적이다. Windows production-like 2-worker peak가 3.591 GiB로 24 GiB의 약 15%여서
현재는 충분한 여유가 있다. 종목·기간·worker 수가 크게 증가하면 첫 다음 단계는
NumPy memmap으로 prepared market/feature 배열까지 worker와 공유하는 것이다.

## 8. 테스트 결과

최종 로컬 결과:

- AI 전체: **244 passed, 8 skipped**
- backtest module 전체: **26 passed**
- 합계: **270 passed, 8 skipped**
- 변경 파일 Ruff 검사: **all checks passed**

추가한 핵심 회귀:

- 11개 구조화 profile action이 기존 참조 Python action과 완전 동일
- 현재 행 이후 데이터를 붙여도 prefix action이 바뀌지 않는 no-lookahead
- 일반 rolling 집계가 현재 행을 제외하고 missing 값을 일관되게 처리
- rank-only, consecutive compiled 조건의 BUY 동작
- 1 worker와 2 workers의 selected candidate, trade/audit, equity,
  objective 결과 canonical SHA-256 동일
- fresh와 disk-cache hit 결과 canonical SHA-256 동일
- 완료 후보의 다음 라운드 재평가 수 0
- 자기개선 후보 수 상한과 normalized identity 중복 제거
- 무한/비정상 Python fallback timeout 후 worker가 남지 않음
- AST source/node/depth/loop/slicing/range 제한
- AOAI retry가 logical call 1회, physical POST 2회로 기록됨

## 9. 입력 규모별 benchmark

### 전체 파이프라인

| 규모 | worker 정책 | wall | peak RSS | 결과 hash |
|---|---|---:|---:|---|
| 20 × 252 = 5,040행 | 요청 1, direct 실행 | 3.300초 | 234,983,424 bytes | `30c548bf…5444d` |
| 20 × 252 = 5,040행 | 요청 2, 작은 입력 direct 실행 | 3.104초 | 234,987,520 bytes | `30c548bf…5444d` |
| 203 × 2,520 = 511,560행 | 1 worker | 49.910초 | 1,293,234,176 bytes | `6c8c398a…e40b3` |
| 203 × 2,520 = 511,560행 | 2 workers | 45.923초 | 3,856,670,720 bytes | `6c8c398a…e40b3` |
| 203 × 2,520 = 511,560행 | disk cache hit | 13.583초 | fresh 이하 | `6c8c398a…e40b3` |

### production-like 1-worker 단계

- feature/market 준비: 16.628초
- selection round: 26.263초
- selected full round: 6.376초
- candidate A1 selection: 3.906초 CPU / 3.906초 wall
- candidate A2 selection: 3.297초 CPU / 3.321초 wall
- selected A3 full: 4.844초 CPU / 5.000초 wall
- feature 배열 추정 크기: 159,606,720 bytes

### production-like 2-worker 단계

- feature/market 준비: 13.451초
- selection round: 23.589초
- selected full round: 6.647초
- candidate A1 selection: 3.063초 CPU / 3.067초 wall
- candidate A2 selection: 2.938초 CPU / 2.954초 wall
- selected A3 full: 5.031초 CPU / 5.263초 wall

fresh 실행은 selection에서 신규 후보 3개, full에서 신규 후보 1개만 평가했다.
cache hit 실행은 selection `new=0/cached=3`, full `new=0/cached=1`이었다.

## 10. 정확성·호환성

- screening의 종목 범위, universe, 추천 데이터 기간을 줄이지 않았다.
- 원래 `StrategySpec`의 매수·매도 조건과 risk constraints를 보존한다.
- 기존 execution timing, cost model, position sizing, trade/audit/equity 결과 형식을 유지한다.
- Monte Carlo seed와 tie-break 순서는 기존 결정론을 유지한다.
- legacy profile 11개의 action hash가 동일하다.
- 1/2 worker 및 fresh/cache 전체 결과 hash가 동일하다.
- public `recommendation_gate` 계약을 테스트로 고정했다.

## 11. 남은 위험과 다음 우선순위

1. **캐시 hit에도 준비 비용 13초가 든다.** 현재는 정확한 data fingerprint와
   정규화 검증을 위해 전체 행을 다시 읽는다. 다음 최우선은 DB snapshot/version을
   신뢰 가능한 입력으로 받아 prepared market/feature 자체를 디스크 캐시하는 것이다.
2. **Windows spawn은 메모리를 더 쓴다.** 2 worker가 1 worker보다 약 3.0배 많은 peak RSS를
   사용했다. 현재 24 GiB에서는 안전하지만 worker를 늘리기 전에 memmap이 필요하다.
3. **2 worker 이득은 8% 수준이다.** 이미 공통 계산과 경량 선택으로 직렬 부분 비중이
   커졌다. 2-core 운영 기본값은 유지하되 작은 입력은 계속 직접 실행하는 것이 낫다.
4. **실제 운영 데이터/서버 확인이 별도로 필요하다.** 로컬 production-like 입력은
   10분 목표를 크게 만족하지만, 배포 후 실제 전체 데이터로 한 번 실행해 DB I/O와
   Linux copy-on-write 효과를 확인해야 한다.
5. **캐시 파일은 결과 JSON만 저장한다.** 더 큰 규모에서 equity/audit 결과가 커지면
   Parquet 또는 SQLite 기반 결과 저장을 재검토한다.
