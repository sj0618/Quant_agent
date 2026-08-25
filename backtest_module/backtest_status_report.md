# 백테스트 현재 상태 보고서

**작성일:** 2026-06-01  
**버전:** 6/1 최신 재작성본  
**범위:** `backtest_module` 백테스트 엔진, `QuantStrategy` 전략 런타임, 결과 요약/오류/불일치 사례  
**검증 방식:** 자연어 서버를 거치지 않고, 직접 `StrategySpec`를 만들어 `QuantStrategy`와 `run_backtest()`를 실제로 실행함  
**실행 옵션:** `initial_capital=1000`, `write_outputs=False`

---

## 1. 한 줄 요약

현재 백테스트는 **정형화된 전략 입력이 들어오면 정상 실행**됩니다.  
다만 아래 제약은 아직 그대로입니다.

1. `execution_timing='next_close'`는 미지원
2. `cross_above` / `cross_below`는 `previous_metrics`가 없으면 기대한 BUY/SELL이 아니라 `WATCH`가 나올 수 있음

즉, **엔진은 동작하지만 전략 변환/필터링/체결 타이밍 쪽은 아직 완성형이 아닙니다.**

---

## 2. 입력과 출력이 정확히 무엇인지

### 2-1. 입력

| 입력 | 역할 | 예시 |
|---|---|---|
| `StrategySpec` | 전략 규칙과 백테스트 설정을 담는 핵심 구조체 | `entry_rules`, `exit_rules`, `backtest` |
| `OhlcvBar[]` | 일봉 가격/거래량 원천 데이터 | `date`, `ticker`, `open`, `high`, `low`, `close`, `volume` |
| `metric_rows` | 외부/보조 지표 | `market_cap`, `rsi_14` |
| `BacktestRunConfig` | 초기자본, 출력 저장 여부, TA-Lib 계산 방식 | `initial_capital=1000`, `write_outputs=False` |
| `MarketSnapshot` | `QuantStrategy.generate_signal()` 같은 런타임 신호 평가용 | `metrics`, `previous_metrics` |

### 2-2. 출력

| 출력 | 의미 |
|---|---|
| `BacktestPlan` | `QuantStrategy.compile_backtest_plan()`가 만드는 실행 계획 |
| `summary` | 최종 성과 요약 (`final_equity`, `period_return`, `trade_count` 등) |
| `equity_curve` | 날짜별 자산 변화 |
| `trades` | 실제 체결된 거래 목록 |
| `signals` | 날짜별 BUY / SELL / HOLD / WATCH 기록 |
| `ValueError` | 현재 엔진이 지원하지 않는 설정일 때 나는 오류 |
| `WATCH` | 실행은 되지만 기대한 매수/매도가 아닌 결과 |

---

## 3. 현재 코드 기준 핵심 동작

### 3-1. `QuantStrategy` 쪽 현재 상태

- `compile_backtest_plan()`은 점수 기반 선별 없이 조건을 충족한 모든 종목을 평가하는 계획을 만듦
- `generate_signal()`은 `entry_rules` / `exit_rules` 를 평가해서 BUY / SELL / HOLD / WATCH 를 결정함
- `CROSS_ABOVE` / `CROSS_BELOW` 는 `previous_metrics`가 있어야 crossing 판정이 가능함
- `MarketSnapshot.metrics`에 있는 숫자는 그대로 조건 평가에 사용됨

### 3-2. `BacktestEngine` 쪽 현재 상태

- `run()`은 `execution_timing == next_open`일 때만 동작함
- `next_close`는 즉시 `ValueError` 발생
- TA-Lib 기반 지표는 OHLCV로 계산 가능하면 자동 계산됨
- `metric_rows`는 계산된 값보다 **우선 적용됨**
- 종목 제외는 필요한 metric이 빠진 티커에 대해 기록
---

## 4. 실제 실행 검증 1: 정상 동작 예시

아래는 실제로 돌린 최신 결과입니다.

### 4-1. 생성한 전략 구조체

```python
from backtest_module import (
    BacktestConfig,
    Condition,
    ConditionOperator,
    CostModel,
    PositionSizing,
    RiskControls,
    StrategySpec,
)
spec = StrategySpec(
    strategy_id="market_cap_rsi_strategy",
    strategy_name="시총 5000억 이상 RSI 70 이상 매수",
    description="Direct struct test",
    entry_rules=[
        Condition(
            left="market_cap",
            operator=ConditionOperator.GTE,
            right=500000000000,
            description="시총 5000억원 이상",
        ),
        Condition(
            left="rsi_14",
            operator=ConditionOperator.GTE,
            right=70,
            description="RSI 70 이상",
        ),
    ],
    exit_rules=[
        Condition(
            left="rsi_14",
            operator=ConditionOperator.LT,
            right=70,
            description="RSI 70 미만",
        ),
    ],
    position_sizing=PositionSizing(max_positions=1),
    risk_controls=RiskControls(stop_loss_pct=0.5, take_profit_pct=None),
    backtest=BacktestConfig(),
)
```

### 4-2. `QuantStrategy.compile_backtest_plan()` 실제 결과

```json
{
  "strategy_id": "market_cap_rsi_strategy",
  "strategy_name": "시총 5000억 이상 RSI 70 이상 매수",
  "market": "KRX",
  "asset_type": "equity",
  "allowed_modules": ["math", "statistics", "datetime", "pandas", "numpy"],
  "network_access_allowed": false,
  "execution_timing": "next_open",
  "use_adjusted_price": true,
  "respect_historical_index_membership": true,
  "apply_reports_from": "next_open",
  "walk_forward": {
    "in_sample_months": 12,
    "out_of_sample_months": 3,
    "roll_months": 1
  },
  "cost_model": {
    "commission_pct": 0.00015,
    "tax_pct": 0.0023,
    "slippage_pct": 0.001
  },
  "notes": [
    "template compile only",
    "new external libraries are forbidden",
    "network calls are forbidden during code execution",
    "candidate filter disabled"
  ]
}
```

### 4-3. 실제 입력 데이터

#### OHLCV

| date | ticker | open | high | low | close | volume |
|---|---:|---:|---:|---:|---:|---:|
| 2026-01-02 | 005930 | 100 | 105 | 95 | 104 | 1000 |
| 2026-01-05 | 005930 | 110 | 116 | 108 | 115 | 1000 |
| 2026-01-06 | 005930 | 116 | 118 | 112 | 114 | 1000 |
| 2026-01-07 | 005930 | 120 | 121 | 117 | 118 | 1000 |
| 2026-01-08 | 005930 | 122 | 124 | 121 | 123 | 1000 |

#### metric_rows

| date | ticker | market_cap | rsi_14 |
|---|---:|---:|---:|
| 2026-01-02 | 005930 | 510000000000 | 25 |
| 2026-01-05 | 005930 | 520000000000 | 72 |
| 2026-01-06 | 005930 | 530000000000 | 75 |
| 2026-01-07 | 005930 | 540000000000 | 68 |
| 2026-01-08 | 005930 | 550000000000 | 66 |

### 4-4. `run_backtest()` 실제 결과 요약

```json
{
  "strategy_id": "market_cap_rsi_strategy",
  "strategy_name": "시총 5000억 이상 RSI 70 이상 매수",
  "initial_capital": 1000,
  "final_equity": 1043.567852,
  "cash": 1043.567852,
  "open_positions": 0,
  "period_return": 0.043567852,
  "max_drawdown": -0.017067339,
  "daily_sharpe_like": 7.3516129539,
  "trade_count": 1,
  "win_rate": 1.0,
  "signal_count": 5,
  "excluded_ticker_count": 0,
  "excluded_tickers": [],
  "execution_timing": "next_open",
  "cost_model": {
    "commission_pct": 0.00015,
    "tax_pct": 0.0023,
    "slippage_pct": 0.001
  },
  "position_sizing": {
    "method": "equal_weight",
    "max_positions": 1,
    "fixed_percent": null,
    "risk_per_position": null
  },
  "indicator_report": {
    "mode": "required",
    "enabled": true,
    "requested_required_metrics": ["market_cap", "rsi_14"],
    "planned_functions": ["RSI"],
    "computed_function_count": 1,
    "computed_functions": ["RSI"],
    "failed_functions": {},
    "computed_metric_names": ["rsi", "rsi_14", "rsi_real"],
    "talib_version": "0.6.8",
    "talib_function_count": 158,
    "talib_calculable_from_ohlcv_count": 157,
    "talib_skipped": {
      "MAVP": ["periods"]
    }
  },
  "notes": [
    "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
    "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated metrics.",
    "Tickers missing required StrategySpec metrics are excluded and recorded here."
  ]
}
```

### 4-5. 실제 체결 거래

```json
[
  {
    "ticker": "005930",
    "entry_date": "2026-01-06",
    "exit_date": "2026-01-08",
    "entry_price": 116.116,
    "exit_price": 121.878,
    "quantity": 8,
    "entry_cost": 0.139339,
    "exit_cost": 2.388809,
    "gross_pnl": 46.096,
    "net_pnl": 43.567852,
    "return_pct": 0.046894181,
    "reason": "exit condition matched"
  }
]
```

### 4-6. 날짜별 시그널

| date | action | reasons | matching rules |
|---|---|---|---|
| 2026-01-02 | `watch` | `no actionable rule matched` | 없음 |
| 2026-01-05 | `buy` | `entry condition matched` | `시총 5000억원 이상;RSI 70 이상` |
| 2026-01-06 | `hold` | `no actionable rule matched` | 없음 |
| 2026-01-07 | `sell` | `exit condition matched` | `RSI 70 미만` |
| 2026-01-08 | `watch` | `no actionable rule matched` | 없음 |

### 4-7. 해석

- `market_cap` 같은 외부 metric은 `metric_rows`에 직접 넣으면 정상 평가됨
- `rsi_14`는 TA-Lib가 계산 가능해서 `indicator_report`에 `RSI`가 잡힘
- 체결은 일봉 기준 `next_open`으로 들어가므로, 시그널 날짜와 체결 날짜가 다를 수 있음
- 수수료/슬리피지 때문에 손익이 `gross_pnl=46.096` → `net_pnl=43.567852`로 줄어듦

---

## 5. 실제 실행 검증 2: 오류가 나는 경우

### 5-1. 입력

```python
err_spec = StrategySpec(
    strategy_id="next_close_error",
    strategy_name="Next close error",
    entry_rules=[
        Condition(left="rsi_14", operator=ConditionOperator.GTE, right=70),
    ],
    backtest={"execution_timing": ExecutionTiming.NEXT_CLOSE},
)
```

### 5-2. 실제 오류 메시지

```text
ValueError BacktestEngine currently supports execution_timing='next_open' only
```

### 5-3. 해석

입력 구조체 자체는 유효하지만, 엔진 구현이 아직 `next_close`를 허용하지 않습니다.  
즉, **전략이 틀린 것이 아니라 엔진 기능이 아직 거기까지 못 간 상태**입니다.

---

## 6. 실제 실행 검증 3: 작동은 하지만 원하던 결과가 아닌 경우
### 6-1. `cross_above`는 `previous_metrics`가 없으면 BUY가 아니라 WATCH가 됨

#### 입력

```python
signal_spec = StrategySpec(
    strategy_id="cross_without_prev",
    strategy_name="Cross without previous metrics",
    entry_rules=[
        Condition(
            left="rsi_14",
            operator=ConditionOperator.CROSS_ABOVE,
            right=30,
            description="RSI crosses above 30",
        )
    ],
)

market = MarketSnapshot(
    ticker="005930",
    timestamp=datetime(2026, 4, 8, 9, 5),
    metrics={"rsi_14": 31},
)
```

#### 실제 결과

```json
{
  "strategy_id": "cross_without_prev",
  "ticker": "005930",
  "action": "watch",
  "confidence": 1.0,
  "reasons": ["no actionable rule matched"],
  "matching_entry_rules": [],
  "matching_exit_rules": [],
  "candidate_snapshot_id": null
}
```

#### 해석

`CROSS_ABOVE`는 현재 값만이 아니라 **이전 값(`previous_metrics`)까지 있어야** crossing 여부를 판정할 수 있습니다.  
그래서 입력값이 있어도 실제 출력은 `buy`가 아니라 `watch`가 됩니다.

---

## 7. 지금 백테스트에서 되는 것 / 안 되는 것

### 되는 것

1. `StrategySpec` 기반 전략 실행
2. OHLCV + 외부 metric 동시 입력
3. `next_open` 기준 체결
4. TA-Lib 기반 지표 계산
5. 수수료 / 세금 / 슬리피지 반영
6. summary / trade / signal 출력

### 아직 안 되는 것

1. `next_close` 체결
2. 자연어에서 전략 구조체로의 안정적 변환
3. 실서버 / 실DB / 실시간 연동
4. intraday / partial fill / walk-forward 고도화

---

## 8. 최신 검증 결과

### 8-1. 단위 테스트

```text
19 passed in 0.33s
```

검증 범위:
- `Qaunt_agent/backtest_module/tests/test_backtest.py`
- `Qaunt_agent/backtest_module/tests/test_strategy.py`

이 숫자는 **1년치 실데이터 백테스트 시간이 아니라, 작은 fixture 기반 단위 테스트 전체 실행 시간**입니다.

### 8-2. 실제 1년치 데이터 재측정


- 로드 row 수: `692,780`
- 로드 시간: `3.162 sec`
- 백테스트 실행 시간: `18.96 sec`
- trade_count: `670`
- signal_count: `692,780`
- excluded_ticker_count: `0`
- final_equity: `348,382,065.0`
- period_return: `2.48382065`
- max_drawdown: `-0.219130332`

즉, **0.33초는 1년 테스트 시간이 아니라 단위 테스트 시간**이고, 실제 1년치 데이터는 로드/실행 합쳐서 훨씬 더 걸립니다.

---

## 9. 최종 결론

현재 백테스트는 **정형화된 `StrategySpec`를 직접 넣으면 결과를 안정적으로 뽑을 수 있는 상태**입니다.  
다만 **`next_close` 체결과 cross 조건의 이전 시점 데이터 처리**는 아직 기대대로 동작하지 않거나 아예 막혀 있습니다.

가장 중요한 우선순위는 아래 순서입니다.

1. 자연어 → `StrategySpec` 변환 고도화
2. `next_close` / intraday 체결 확장
3. 실서버 / 실데이터 연동
