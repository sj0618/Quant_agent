# Service DB Backtest ERD

`001_app_schema.sql`과 `002_extend_backtest_results.sql`을 모두 적용한 후의 백테스트 저장 구조를 표현한다.

```mermaid
erDiagram
    USERS o|--o{ STRATEGY : owns
    USERS o|--o{ BACKTEST_RUN : requests
    STRATEGY ||--o{ BACKTEST_RUN : executes

    BACKTEST_RUN ||--o| BACKTEST_SUMMARY : has
    BACKTEST_RUN ||--o{ BACKTEST_EQUITY_POINT : contains
    BACKTEST_RUN ||--o{ BACKTEST_TRADE : contains
    BACKTEST_RUN ||--o{ BACKTEST_SIGNAL : contains
    BACKTEST_RUN ||--o| BACKTEST_METRIC_DETAIL : has

    USERS {
        bigint user_id PK
        text email
        text name
        text profile_image_url
        text password_hash
        text auth_provider
        text provider_user_id
        timestamptz created_at
        timestamptz updated_at
        timestamptz last_login_at
    }

    STRATEGY {
        text strategy_id PK
        text schema_version
        text strategy_name
        text description
        bigint user_id FK
        text market
        text asset_type
        text lifecycle
        numeric fit_confidence
        jsonb spec_jsonb
        timestamptz created_at
        timestamptz updated_at
    }

    BACKTEST_RUN {
        uuid run_id PK
        text strategy_id FK
        bigint user_id FK
        numeric initial_capital
        integer max_tickers
        text talib_mode
        jsonb config_jsonb
        text status
        timestamptz started_at
        timestamptz ended_at
        text error_message
        jsonb output_paths_jsonb
        timestamptz created_at
    }

    BACKTEST_SUMMARY {
        uuid run_id PK, FK
        numeric final_equity
        numeric final_cash
        integer open_positions
        numeric period_return
        numeric max_drawdown
        numeric sharpe_ratio
        numeric win_rate
        integer trade_count
        integer signal_count
        numeric avg_holding_days
        integer excluded_ticker_count
        jsonb excluded_tickers_jsonb
        jsonb indicator_report_jsonb
        jsonb cost_model_jsonb
        jsonb position_sizing_jsonb
        numeric avg_negative_period_return
        numeric avg_period_return
        numeric avg_positive_period_return
        numeric best_period_return
        numeric worst_period_return
        numeric cagr
        numeric calmar_ratio
        numeric common_sense_ratio
        numeric expected_return
        numeric geometric_mean
        numeric gain_to_pain_ratio
        numeric recovery_factor
        numeric rar
        numeric conditional_value_at_risk
        numeric value_at_risk
        numeric annualized_volatility
        numeric kurtosis
        numeric skew
        numeric risk_of_ruin
        numeric risk_return_ratio
        numeric tail_ratio
        numeric ulcer_index
        numeric ulcer_performance_index
        integer consecutive_negative_periods
        integer consecutive_positive_periods
        numeric cpc_index
        numeric exposure
        numeric kelly_criterion
        numeric outlier_loss_ratio
        numeric outlier_win_ratio
        numeric payoff_ratio
        numeric profit_factor
        numeric period_win_rate
        numeric information_ratio
        numeric r_squared
        numeric sortino_ratio
        numeric adjusted_sortino_ratio
        timestamptz created_at
    }

    BACKTEST_EQUITY_POINT {
        uuid run_id PK, FK
        date trade_date PK
        numeric cash
        numeric positions_value
        numeric total_equity
        numeric daily_return
    }

    BACKTEST_TRADE {
        bigint trade_id PK
        uuid run_id FK
        text ticker
        date entry_date
        date exit_date
        numeric entry_price
        numeric exit_price
        bigint quantity
        numeric entry_cost
        numeric exit_cost
        numeric gross_pnl
        numeric net_pnl
        numeric return_pct
        text reason
        timestamptz created_at
    }

    BACKTEST_SIGNAL {
        bigint signal_id PK
        uuid run_id FK
        date signal_date
        text ticker
        text action
        jsonb reasons
        jsonb matching_entry_rules
        jsonb matching_exit_rules
        timestamptz created_at
    }

    BACKTEST_METRIC_DETAIL {
        uuid run_id PK, FK
        jsonb compare_jsonb
        jsonb compsum_jsonb
        jsonb drawdown_details_jsonb
        jsonb drawdown_series_jsonb
        jsonb greeks_jsonb
        jsonb rolling_greeks_jsonb
        jsonb monthly_returns_jsonb
        jsonb montecarlo_jsonb
        jsonb montecarlo_cagr_jsonb
        jsonb montecarlo_drawdown_jsonb
        jsonb montecarlo_sharpe_jsonb
        jsonb outliers_jsonb
        timestamptz created_at
    }
```

## `backtest_metric_detail` 저장 방식

`backtest_metric_detail`은 `backtest_run`과 1:0..1 관계이며, 상세 지표를 명시적 JSONB 컬럼으로 저장한다.

| 컬럼 | 내용 | 예상 형태 |
| --- | --- | --- |
| `compare_jsonb` | 전략과 벤치마크 비교 | JSON object |
| `compsum_jsonb` | 누적 복리 수익률 시계열 | JSON array |
| `drawdown_details_jsonb` | drawdown 구간별 상세 | JSON array |
| `drawdown_series_jsonb` | 전체 drawdown 시계열 | JSON array |
| `greeks_jsonb` | alpha, beta 등 | JSON object |
| `rolling_greeks_jsonb` | rolling alpha/beta 시계열 | JSON array |
| `monthly_returns_jsonb` | 월별 수익률 매트릭스 | JSON object |
| `montecarlo_jsonb` | 몬테카를로 요약 결과 | JSON object |
| `montecarlo_cagr_jsonb` | 몬테카를로 CAGR 분포 | JSON object/array |
| `montecarlo_drawdown_jsonb` | 몬테카를로 MDD 분포 | JSON object/array |
| `montecarlo_sharpe_jsonb` | 몬테카를로 Sharpe 분포 | JSON object/array |
| `outliers_jsonb` | 이상치 수익률 목록 | JSON array |

## 해석 주의사항

- `backtest_summary.win_rate`는 현재 백테스트의 **거래 기준 승률**이다.
- `backtest_summary.period_win_rate`는 향후 구현될 **기간 기준 승률**이다.
- `backtest_summary.sharpe_ratio`는 현재 `daily_sharpe_like`를 adapter가 변환해 저장하는 대상이다.
- 아직 백테스트에 구현되지 않은 scalar 지표는 `NULL`로 유지한다.
- 상세 필드 매핑과 별칭 처리는 [`backtest_result_mapping.md`](backtest_result_mapping.md)를 참조한다.
