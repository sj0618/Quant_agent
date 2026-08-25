## StrategySpec 최종 구조체 채택안

### 채택 구조
- `UserIntentSpec`
  - 자연어 전략 해석 결과
  - `fit_confidence`, `missing_fields`, `ambiguity_flags`, `clarification_questions`, `assumptions` 포함
- `StrategySpec`
  - 프로젝트의 canonical 전략 명세
  - `entry_rules`, `exit_rules`, `position_sizing`, `risk_controls`, `backtest`, `reporting` 포함
- `ParsedReport`
  - 애널리스트 리포트 구조화 결과
  - `llm_sentiment`, `extraction_confidence`, `available_at` 포함
- `BacktestPlan`
  - 템플릿 기반 백테스트 실행 계획
- `SignalDecision`
  - 전략 실행 후 최종 신호 결과

### 왜 이렇게 정의했는가
1. **메인 플로우를 그대로 유지하기 위해**
   - 사용자 자연어 전략 입력
   - 정형 전략 스펙 생성
   - 조건을 충족한 전체 종목 평가
   - 백테스트 코드 생성/실행
   - 결과 분석 및 리포트

2. **조건 중심 평가를 강제하기 위해**
   - 후보 점수나 상위 N개 선별 없이 진입·청산 조건을 직접 평가

3. **PIT / lookahead bias 방지를 위해**
   - `ParsedReport.available_at`
   를 명시
   - 장 마감 후 수집 리포트는 다음 거래일 시가부터 유효

4. **설명 가능성을 확보하기 위해**
   - 조건별 충족 여부를 신호와 리포트에 보존

### 채택한 기본 주기
- 리포트 수집: 영업일 1회
- 리포트 효력 발생: 다음 거래일 시가
- Walk-Forward baseline: 12개월 IS / 3개월 OOS / rolling 1개월

### 이 주기를 선택한 이유
- 과거 시점 리포트 기반 후보군을 현실적으로 재현하려면 일배치가 가장 안전함
- 당일 리포트를 당일 전략에 소급 반영하면 lookahead bias 위험이 커짐
- 12M/3M은 전략 일반화 검증과 최신성 반영의 균형점으로 baseline으로 사용하기 적절함
- 단, 최종 가중치와 주기는 백테스트/민감도 실험으로 보정 예정
