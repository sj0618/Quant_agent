# QuantAgent Strategy Spec (V1)

이 폴더는 QuantAgent 프로젝트의 **최종 StrategySpec 구조체**와 이를 사용하는
**canonical strategy runtime** 예시 구현입니다.

## 포함 파일

- `quantagent_strategy/models.py`
  - `UserIntentSpec`
  - `StrategySpec`
  - `ParsedReport`
  - `BacktestPlan`
  - `SignalDecision`
- `quantagent_strategy/strategy.py`
  - `QuantStrategy`
- `tests/`
  - 모델 validation 테스트
  - buy / sell / compile 테스트
- `MEETING_NOTE_SNIPPET.md`
  - 회의록에 바로 붙여넣을 설명
- `GITHUB_ORG_SETUP.md`
  - GitHub Organization 및 Repository 생성 절차

## 설계 요약

### 1. 메인 플로우 유지

- 사용자 자연어 전략 입력
- 정형 전략 스펙 생성
- 전 종목 조건 평가
- 백테스트 코드 생성/실행
- 결과 분석 및 리포트

### 2. V1 핵심 원칙

- **비정형 데이터(애널리스트 리포트)는 설명 근거로만 사용**
- **실제 매수/매도는 기술적 전략이 결정**
- **리포트는 장 마감 후 수집 시 다음 거래일 시가부터 유효**
- **A/B 비교는 백테스트/분석용으로 남기되, 기본 사용자 리포트에는 숨김**

### 3. 조건 충족 종목 전체 평가

`StrategySpec`은 사용자 의도와 전략 로직을 담는 **정적 명세**입니다.
별도의 점수 기반 후보군을 만들지 않고, 데이터 소스의 전 종목에 동일한 조건을 적용합니다.

## 빠른 사용 예시

```python
from datetime import datetime
from quantagent_strategy import (
    Condition,
    ConditionOperator,
    MarketSnapshot,
    QuantStrategy,
    StrategySpec,
)

spec = StrategySpec(
    strategy_id="mean_reversion_v1",
    strategy_name="Mean Reversion V1",
    entry_rules=[
        Condition(left="rsi", operator=ConditionOperator.LTE, right=30)
    ],
    exit_rules=[
        Condition(left="rsi", operator=ConditionOperator.GTE, right=70)
    ],
)

strategy = QuantStrategy(spec)

market = MarketSnapshot(
    ticker="005930",
    timestamp=datetime(2026, 4, 8, 9, 5),
    metrics={"rsi": 28},
)

signal = strategy.generate_signal(market=market, has_position=False)
print(signal.action)
```

## 테스트 실행

```bash
cd quantagent_strategy
pytest -q
```
