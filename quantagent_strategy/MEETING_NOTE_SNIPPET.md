## StrategySpec 최종 구조체 채택안

### 채택 구조
- `UserIntentSpec`
  - 자연어 전략 해석 결과
  - `fit_confidence`, `missing_fields`, `ambiguity_flags`, `clarification_questions`, `assumptions` 포함
- `StrategySpec`
  - 프로젝트의 canonical 전략 명세
  - `universe`, `entry_rules`, `exit_rules`, `position_sizing`, `risk_controls`, `research_overlay`, `backtest`, `reporting` 포함
- `ParsedReport`
  - 애널리스트 리포트 구조화 결과
  - `llm_sentiment`, `extraction_confidence`, `available_at` 포함
- `CandidateSnapshot`
  - 특정 거래일에 유효한 후보군 스냅샷
  - `effective_from`, `top_k_stocks`, `score_list`, `reason_trace` 포함
- `BacktestPlan`
  - 템플릿 기반 백테스트 실행 계획
- `SignalDecision`
  - 전략 실행 후 최종 신호 결과

### 왜 이렇게 정의했는가
1. **메인 플로우를 그대로 유지하기 위해**
   - 사용자 자연어 전략 입력
   - 정형 전략 스펙 생성
   - 종목/섹터 필터링
   - 백테스트 코드 생성/실행
   - 결과 분석 및 리포트

2. **V1 원칙을 구조체에 강제하기 위해**
   - 리포트는 direct signal이 아니라 candidate filter
   - 실제 매수/매도는 기술적 전략이 결정
   - 따라서 `StrategySpec`과 `CandidateSnapshot`을 분리

3. **A/B 백테스트를 지원하기 위해**
   - 동일 `StrategySpec`으로
     - 후보군 필터 O
     - 후보군 필터 X
     를 동시에 비교 가능
   - `BacktestConfig.compare_filtered_vs_unfiltered`로 제어

4. **PIT / lookahead bias 방지를 위해**
   - `ParsedReport.available_at`
   - `CandidateSnapshot.effective_from`
   를 명시
   - 장 마감 후 수집 리포트는 다음 거래일 시가부터 유효

5. **설명 가능성을 확보하기 위해**
   - 후보군 선정 이유를 `reason_trace`에 저장
   - 리포트에서 “왜 이 종목을 골랐는가”를 바로 설명 가능

### 채택한 기본 주기
- 리포트 수집: 영업일 1회
- 리포트 효력 발생: 다음 거래일 시가
- Walk-Forward baseline: 12개월 IS / 3개월 OOS / rolling 1개월

### 이 주기를 선택한 이유
- 과거 시점 리포트 기반 후보군을 현실적으로 재현하려면 일배치가 가장 안전함
- 당일 리포트를 당일 전략에 소급 반영하면 lookahead bias 위험이 커짐
- 12M/3M은 전략 일반화 검증과 최신성 반영의 균형점으로 baseline으로 사용하기 적절함
- 단, 최종 가중치와 주기는 백테스트/민감도 실험으로 보정 예정
