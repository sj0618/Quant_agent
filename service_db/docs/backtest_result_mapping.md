# Backtest Result Storage Mapping

백테스트 엔진의 `BacktestResult`와 PostgreSQL `app` 스키마 간 저장 계약을 정의한다.

이 문서는 필드명과 형식의 변환 규칙을 정의하며, 실제 DB 연결·트랜잭션·재시도를 담당하는 adapter/writer 구현은 백엔드 통합 계층의 책임이다.

## 현재 `BacktestResult` 요약 매핑

| 백테스트 원본 | DB 저장 위치 | 변환 / 비고 |
| --- | --- | --- |
| `strategy_id` | `app.backtest_run.strategy_id` | 외래 키 |
| `summary.initial_capital` | `app.backtest_run.initial_capital` | 실행 정보 |
| `summary.final_equity` | `app.backtest_summary.final_equity` | 그대로 저장 |
| `summary.cash` | `app.backtest_summary.final_cash` | 필드명 변환 |
| `summary.open_positions` | `app.backtest_summary.open_positions` | 그대로 저장 |
| `summary.period_return` | `app.backtest_summary.period_return` | 전체 기간 복리 수익률 |
| `summary.max_drawdown` | `app.backtest_summary.max_drawdown` | 그대로 저장 |
| `summary.daily_sharpe_like` | `app.backtest_summary.sharpe_ratio` | 일별 수익률, 무위험수익률 0, `sqrt(252)`, 표본 표준편차 |
| `summary.trade_count` | `app.backtest_summary.trade_count` | 완료된 거래 수 |
| `summary.win_rate` | `app.backtest_summary.win_rate` | **거래 기준** 승률 |
| `summary.signal_count` | `app.backtest_summary.signal_count` | 그대로 저장 |
| `summary.excluded_ticker_count` | `app.backtest_summary.excluded_ticker_count` | 그대로 저장 |
| `summary.excluded_tickers` | `app.backtest_summary.excluded_tickers_jsonb` | JSON 배열 |
| `summary.indicator_report` | `app.backtest_summary.indicator_report_jsonb` | JSON 객체 |
| `summary.cost_model` | `app.backtest_summary.cost_model_jsonb` | JSON 객체 |
| `summary.position_sizing` | `app.backtest_summary.position_sizing_jsonb` | JSON 객체 |
| `summary.execution_timing` | `app.backtest_run.config_jsonb.execution_timing` | 실행 설정으로 저장 |
| `summary.notes` | 미저장 | 현재 엔진의 고정 설명문. 저장 요구가 생기면 별도 migration 필요 |
| `output_paths` | `app.backtest_run.output_paths_jsonb` | 영구 스토리지가 있는 경우만 저장 |

`summary.strategy_name`은 `app.strategy.strategy_name`에서 조회하며 실행별로 중복 저장하지 않는다.

## 일별 자산곡선 매핑

`BacktestResult.equity_curve` 각 항목을 `app.backtest_equity_point`에 저장한다.

| 백테스트 필드 | DB 컬럼 |
| --- | --- |
| `date` | `trade_date` |
| `cash` | `cash` |
| `positions_value` | `positions_value` |
| `total_equity` | `total_equity` |
| `daily_return` | `daily_return` |

## 거래내역 매핑

`BacktestResult.trades` 각 항목을 `app.backtest_trade`에 저장한다. `run_id`와 DB 생성 `trade_id`를 제외한 필드명은 현재 모두 일치한다.

## 매매신호 매핑

`BacktestResult.signals` 각 항목을 `app.backtest_signal`에 저장한다.

| 백테스트 필드 | DB 컬럼 | 변환 |
| --- | --- | --- |
| `date` | `signal_date` | ISO date를 `date`로 변환 |
| `ticker` | `ticker` | 그대로 저장 |
| `action` | `action` | 소문자 action 값 |
| `reasons` | `reasons` | `;`로 나눈 후 빈 항목을 제거한 JSON 배열 |
| `matching_entry_rules` | `matching_entry_rules` | `;`로 나눈 JSON 배열 |
| `matching_exit_rules` | `matching_exit_rules` | `;`로 나눈 JSON 배열 |

빈 문자열은 JSONB에 직접 저장하지 않고 `[]`로 변환한다.

## 구현 예정 scalar 지표 매핑

아래 원본 필드명은 백테스트 담당이 전달한 지표 목록을 기준으로 한다. 실제 출력 계약이 확정되면 adapter가 아래 DB 컬럼으로 변환한다.

| 백테스트 원본 / 별칭 | DB 컬럼 | 기준 |
| --- | --- | --- |
| `avg_loss` | `avg_negative_period_return` | 음수인 기간 수익률 평균 |
| `avg_return` | `avg_period_return` | 기간 수익률 평균 |
| `avg_win` | `avg_positive_period_return` | 양수인 기간 수익률 평균 |
| `best` | `best_period_return` | 최고 단일 기간 수익률 |
| `worst` | `worst_period_return` | 최악 단일 기간 수익률 |
| `cagr` | `cagr` | 연평균 복리수익률 |
| `calmar` | `calmar_ratio` | CAGR / abs(MDD) |
| `common_sense_ratio` | `common_sense_ratio` | 복합 ratio |
| `expected_return` | `expected_return` | 연율화 기대수익률 |
| `geometric_mean`, `ghpr` | `geometric_mean` | 구현 결과의 단위가 일치할 때만 별칭 처리 |
| `gain_to_pain_ratio` | `gain_to_pain_ratio` | 양수 수익 합 / abs(음수 수익 합) |
| `recovery_factor` | `recovery_factor` | 전체 수익률 / abs(MDD) |
| `rar` | `rar` | 백테스트 구현 정의 확정 필요 |
| `conditional_value_at_risk`, `cvar`, `expected_shortfall` | `conditional_value_at_risk` | 동일 공식으로 구현된 경우만 통합 |
| `value_at_risk`, `var` | `value_at_risk` | 동일 지표 별칭 |
| `volatility` | `annualized_volatility` | `std(r_t) * sqrt(P)` |
| `kurtosis` | `kurtosis` | 기간 수익률 첨도 |
| `skew` | `skew` | 기간 수익률 왜도 |
| `risk_of_ruin`, `ror` | `risk_of_ruin` | 동일 지표 별칭 |
| `risk_return_ratio` | `risk_return_ratio` | 위험 대비 수익 |
| `tail_ratio` | `tail_ratio` | 우측 꼬리 / abs(좌측 꼬리) |
| `ulcer_index` | `ulcer_index` | drawdown 깊이와 지속성 |
| `ulcer_performance_index`, `upi` | `ulcer_performance_index` | 동일 지표 별칭 |
| `consecutive_losses` | `consecutive_negative_periods` | 연속 음수 수익 기간 수 |
| `consecutive_wins` | `consecutive_positive_periods` | 연속 양수 수익 기간 수 |
| `cpc_index` | `cpc_index` | 복합 수익성 지표 |
| `exposure` | `exposure` | 투자 중인 기간 비율 |
| `kelly_criterion` | `kelly_criterion` | 최적 베팅 비중 |
| `outlier_loss_ratio` | `outlier_loss_ratio` | 극단 손실 비율 |
| `outlier_win_ratio` | `outlier_win_ratio` | 극단 수익 비율 |
| `payoff_ratio`, `profit_ratio`, `win_loss_ratio` | `payoff_ratio` | 공식이 `avg_win / abs(avg_loss)`로 일치할 때만 통합 |
| `profit_factor` | `profit_factor` | 백테스트 구현의 기간/거래 기준 확인 필요 |
| `performance_metrics.win_rate` | `period_win_rate` | **기간 기준** 승률. 현재 `summary.win_rate`와 구분 |
| `information_ratio` | `information_ratio` | 전략-벤치마크 초과수익 기준 |
| `r_squared`, `r2` | `r_squared` | 동일 지표 별칭 |
| `sortino` | `sortino_ratio` | 하방변동성 기준 |
| `adjusted_sortino` | `adjusted_sortino_ratio` | 보정 Sortino |

`sharpe`는 기존 `sharpe_ratio`, `comp`는 기존 `period_return`, `max_drawdown`은 기존 `max_drawdown`을 사용하며 중복 컬럼을 만들지 않는다.

`implied_volatility`는 옵션 가격 기반 정의와 구현이 확정되기 전까지 저장 대상에서 제외한다. `remove_outliers`는 지표가 아닌 데이터 가공 함수이므로 저장하지 않는다.

## 구현 예정 상세 지표 매핑

아래 지표는 `app.backtest_metric_detail`의 명시적 JSONB 컬럼에 저장한다. 한 `run_id`당 최대 한 행을 저장한다.

| 백테스트 원본 | DB 컬럼 | 내용 |
| --- | --- | --- |
| `compare` | `compare_jsonb` | 전략과 벤치마크 비교 결과 |
| `compsum` | `compsum_jsonb` | 누적 복리 수익률 시계열 |
| `drawdown_details` | `drawdown_details_jsonb` | drawdown 구간별 상세 |
| `to_drawdown_series` | `drawdown_series_jsonb` | 전체 drawdown 시계열 |
| `greeks` | `greeks_jsonb` | alpha, beta 등 벤치마크 대비 지표 |
| `rolling_greeks` | `rolling_greeks_jsonb` | rolling alpha/beta 시계열 |
| `monthly_returns` | `monthly_returns_jsonb` | 월별 수익률 매트릭스 |
| `montecarlo` | `montecarlo_jsonb` | 몬테카를로 요약 결과 |
| `montecarlo_cagr` | `montecarlo_cagr_jsonb` | 몬테카를로 CAGR 분포 |
| `montecarlo_drawdown` | `montecarlo_drawdown_jsonb` | 몬테카를로 MDD 분포 |
| `montecarlo_sharpe` | `montecarlo_sharpe_jsonb` | 몬테카를로 Sharpe 분포 |
| `outliers` | `outliers_jsonb` | 이상치 수익률 목록 |

## Adapter 구현 규칙

1. 미구현·미제공 scalar 지표는 `0`이 아닌 `NULL`로 남겨둔다.
2. `NaN`, `Infinity`, `-Infinity`는 numeric/JSONB에 저장하지 않고 검증 오류로 처리한다.
3. 별칭은 공식과 단위가 일치할 때만 대표 컬럼으로 변환한다.
4. `summary.win_rate`는 거래 기준, `performance_metrics.win_rate`는 기간 기준으로 구분한다.
5. run, summary, equity curve, trades, signals, metric details은 하나의 DB 트랜잭션으로 저장한다.
