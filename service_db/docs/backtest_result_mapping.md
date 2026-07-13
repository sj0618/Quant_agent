# 백테스트 결과 저장 매핑

백테스트 엔진이 계산하는 지표와 현재 PostgreSQL `app` 스키마에 실제로 저장되는 지표를 구분한다.

## 현재 저장 범위

현재 저장 계약의 기준은 `011_app_ai_backtest_erd.sql`이다. 백엔드의 `BacktestSummaryRecord`, `ai_backtest_subprocess_runner.py`, `ai_backtest_repository.py`도 이 구조를 사용한다.

- 실행 정보: `app.backtest_run`
- 일별 자산곡선: `app.backtest_equity_point`
- 매매 신호: `app.backtest_signal`
- 거래 내역: `app.backtest_trade`
- 주요 성과지표: `app.backtest_summary`
- JSON 상세지표: `app.backtest_metric_detail`

`app.backtest_summary`에는 최종 자산, 기간수익률, CAGR, 벤치마크 수익률, 알파·베타, MDD, 변동성, Sharpe·Sortino·Calmar, 승률, Profit Factor, Payoff Ratio, 평균 손익, 연속 승·패 기간, 거래 수 등이 저장된다.

`app.backtest_metric_detail`에는 비교 결과, 구성 정보, drawdown, greeks, rolling returns, 월별 수익률, Monte Carlo 결과, 이상치 결과 등이 JSONB로 저장된다.

## 엔진 계산값과 DB 저장값의 차이

`backtest_module/performance.py`와 `backtest_module/backtest.py`는 현재 DB 저장 범위보다 많은 성과지표를 계산한다. 예를 들면 VaR·CVaR, Tail Ratio, Ulcer Index, Kelly Criterion, Risk of Ruin, Information Ratio, R-squared 등이 있다.

하지만 현재 백엔드 변환기와 repository는 이 추가 지표 대부분을 DB INSERT 대상으로 사용하지 않는다. 따라서 이번 migration에는 확장 컬럼을 추가하지 않는다.

추후 확장하려면 다음 작업을 한 단위로 진행해야 한다.

1. 저장할 지표와 공식·단위·NULL 처리 기준 확정
2. API/Pydantic 저장 모델 확장
3. 엔진 결과를 저장 모델로 변환하는 매핑 추가
4. repository INSERT 컬럼 추가
5. 후속 migration과 통합 테스트 추가

계산 코드가 있다는 이유만으로 DB 컬럼만 먼저 추가하지 않는다. 현재 사용 중인 일부 지표는 011의 기존 컬럼으로 계속 저장된다.

## 저장 규칙

1. 계산되지 않은 scalar 값은 `0` 대신 `NULL`로 처리한다.
2. `NaN`, `Infinity`, `-Infinity`는 numeric/JSONB에 저장하지 않는다.
3. 지표의 공식과 단위가 일치하는 경우에만 동일 DB 컬럼으로 매핑한다.
4. `summary.win_rate`의 거래 기준 승률과 기간 기준 승률을 혼동하지 않는다.
5. run, summary, equity curve, trades, signals, metric details는 하나의 DB 트랜잭션으로 저장한다.
