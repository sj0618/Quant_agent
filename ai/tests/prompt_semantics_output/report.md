# Strategy Prompt Semantics - Report Output

## [01] OK - expected `value_quality` / actual `value_quality_a`

**prompt**: 저PER·고ROE·부채비율 100% 이하 조건을 만족하는 가치주 중 최근 20일 수익률이 시장보다 강한 종목을 찾아줘.

**status**: `ready`

### KOSPI200 저평가 퀄리티 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "value_quality_a",
  "name": "KOSPI200 저평가 퀄리티",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "per_percentile",
      "operator": "lte",
      "right": 0.4,
      "description": "PER 업종/시장 하위권"
    },
    {
      "left": "roe",
      "operator": "gte",
      "right": 0.15,
      "description": "ROE 15% 이상"
    },
    {
      "left": "debt_ratio",
      "operator": "lte",
      "right": 100.0,
      "description": "부채비율 100% 이하"
    },
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 상대강도 양호"
    }
  ],
  "exit_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "lt",
      "right": 0.0,
      "description": "단기 상대강도 약화"
    }
  ],
  "indicators": [
    "PER",
    "ROE",
    "debt_ratio",
    "relative_strength_20d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "재무 조건은 후보 필터, OHLCV 기반 상대강도는 검증 proxy로 사용",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l2_talib_catalog_158",
    "l2_rsi"
  ],
  "confidence": 0.78
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "per_percentile",
    "operator": "lte",
    "right": 0.4,
    "description": "PER 업종/시장 하위권"
  },
  {
    "left": "roe",
    "operator": "gte",
    "right": 0.15,
    "description": "ROE 15% 이상"
  },
  {
    "left": "debt_ratio",
    "operator": "lte",
    "right": 100.0,
    "description": "부채비율 100% 이하"
  },
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 상대강도 양호"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "재무 조건은 후보 필터, OHLCV 기반 상대강도는 검증 proxy로 사용",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "value_quality_a_a1",
    "strategy_name": "KOSPI200 저평가 퀄리티 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-01:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [02] OK - expected `breakout_volume_momentum` / actual `breakout_volume_momentum_a`

**prompt**: 최근 52주 신고가를 돌파했고 거래량이 20일 평균 대비 150% 이상 증가한 모멘텀 종목을 찾아줘.

**status**: `ready`

### KOSPI200 거래량 돌파 모멘텀 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "breakout_volume_momentum_a",
  "name": "KOSPI200 거래량 돌파 모멘텀",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "breakout_high",
      "operator": "eq",
      "right": 1.0,
      "description": "신고가 또는 상단 돌파"
    },
    {
      "left": "volume_ratio_20",
      "operator": "gte",
      "right": 1.5,
      "description": "20일 평균 대비 거래량 150% 이상"
    },
    {
      "left": "close_above_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "종가가 20일선 위"
    },
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 상대강도 양호"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 이탈"
    }
  ],
  "indicators": [
    "rolling_high",
    "volume_ratio_20",
    "SMA20",
    "relative_strength_20d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "신고가 기간은 입력의 52주/120일/20일 표현에 맞춰 L2에서 선택",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion",
    "l2_rsi"
  ],
  "confidence": 0.8300000000000001
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "breakout_high",
    "operator": "eq",
    "right": 1.0,
    "description": "신고가 또는 상단 돌파"
  },
  {
    "left": "volume_ratio_20",
    "operator": "gte",
    "right": 1.5,
    "description": "20일 평균 대비 거래량 150% 이상"
  },
  {
    "left": "close_above_sma_20",
    "operator": "eq",
    "right": 1.0,
    "description": "종가가 20일선 위"
  },
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 상대강도 양호"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "신고가 기간은 입력의 52주/120일/20일 표현에 맞춰 L2에서 선택",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "breakout_volume_momentum_a_a1",
    "strategy_name": "KOSPI200 거래량 돌파 모멘텀 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-02:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [03] OK - expected `rsi_rebound` / actual `rsi_rebound_a`

**prompt**: RSI(14)가 30 이하로 과매도된 뒤 다시 30을 상향 돌파한 반등 후보 종목을 찾아줘.

**status**: `ready`

### KOSPI200 RSI 과매도 반등 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "rsi_rebound_a",
  "name": "KOSPI200 RSI 과매도 반등",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "rsi",
      "operator": "lte",
      "right": 30.0,
      "description": "RSI <= 30 또는 30 상향 회복"
    }
  ],
  "exit_conditions": [
    {
      "left": "rsi",
      "operator": "gte",
      "right": 70.0,
      "description": "RSI >= 70"
    }
  ],
  "indicators": [
    "RSI"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "RSI 30 회복 조건은 L2에서 과매도 반등 proxy로 해석",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion",
    "l2_talib_catalog_158"
  ],
  "confidence": 0.87
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "rsi",
    "operator": "lte",
    "right": 30.0,
    "description": "RSI <= 30 또는 30 상향 회복"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "RSI 30 회복 조건은 L2에서 과매도 반등 proxy로 해석",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A3",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "rsi_rebound_a_a3",
    "strategy_name": "KOSPI200 RSI 과매도 반등 A3",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-03:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [04] OK - expected `pullback_trend` / actual `pullback_trend_a`

**prompt**: 주가가 200일 이동평균선 위에 있고 20일선까지 조정받은 상승추세 눌림목 종목을 찾아줘.

**status**: `ready`

### KOSPI200 상승추세 눌림목 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "pullback_trend_a",
  "name": "KOSPI200 상승추세 눌림목",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "close_above_sma_200",
      "operator": "eq",
      "right": 1.0,
      "description": "주가가 200일선 위"
    },
    {
      "left": "pullback_to_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 근처 조정"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 이탈"
    }
  ],
  "indicators": [
    "SMA20",
    "SMA200"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "눌림목은 L1 정의에 따라 장기 상승추세 안의 단기 조정으로 해석",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_pullback"
  ],
  "confidence": 0.81
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "close_above_sma_200",
    "operator": "eq",
    "right": 1.0,
    "description": "주가가 200일선 위"
  },
  {
    "left": "pullback_to_sma_20",
    "operator": "eq",
    "right": 1.0,
    "description": "20일선 근처 조정"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "눌림목은 L1 정의에 따라 장기 상승추세 안의 단기 조정으로 해석",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "pullback_trend_a_a1",
    "strategy_name": "KOSPI200 상승추세 눌림목 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-04:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [05] OK - expected `earnings_momentum` / actual `earnings_momentum_a`

**prompt**: 최근 3개월 EPS 컨센서스가 상향 조정되고 주가도 20일 신고가를 돌파한 실적 모멘텀 종목을 찾아줘.

**status**: `ready`

### KOSPI200 실적 모멘텀 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "earnings_momentum_a",
  "name": "KOSPI200 실적 모멘텀",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "earnings_revision_3m",
      "operator": "gte",
      "right": 0.0,
      "description": "최근 3개월 이익 전망 상향"
    },
    {
      "left": "breakout_high",
      "operator": "eq",
      "right": 1.0,
      "description": "20일 신고가 또는 상단 돌파"
    },
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 상대강도 양호"
    }
  ],
  "exit_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "lt",
      "right": 0.0,
      "description": "상대강도 약화"
    }
  ],
  "indicators": [
    "earnings_revision_3m",
    "rolling_high",
    "relative_strength_20d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "실적/가이던스 조건은 후보 필터, 신고가와 상대강도는 검증 proxy로 사용",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping"
  ],
  "confidence": 0.75
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "earnings_revision_3m",
    "operator": "gte",
    "right": 0.0,
    "description": "최근 3개월 이익 전망 상향"
  },
  {
    "left": "breakout_high",
    "operator": "eq",
    "right": 1.0,
    "description": "20일 신고가 또는 상단 돌파"
  },
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 상대강도 양호"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "실적/가이던스 조건은 후보 필터, 신고가와 상대강도는 검증 proxy로 사용",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "earnings_momentum_a_a1",
    "strategy_name": "KOSPI200 실적 모멘텀 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용",
    "SEIBro feature mart 미적재: raw analyst report evidence만 사용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-05:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [06] OK - expected `dividend_defensive` / actual `dividend_defensive_a`

**prompt**: 배당수익률이 4% 이상이고 최근 5년 배당 삭감이 없으며 부채비율이 낮은 배당주를 찾아줘.

**status**: `ready`

### KOSPI200 배당 방어주 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "dividend_defensive_a",
  "name": "KOSPI200 배당 방어주",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "dividend_yield",
      "operator": "gte",
      "right": 0.04,
      "description": "배당수익률 4% 이상"
    },
    {
      "left": "debt_ratio",
      "operator": "lte",
      "right": 100.0,
      "description": "부채비율 100% 이하"
    },
    {
      "left": "dividend_cut_5y",
      "operator": "eq",
      "right": 0.0,
      "description": "최근 5년 배당 삭감 없음"
    },
    {
      "left": "close_above_sma_200",
      "operator": "eq",
      "right": 1.0,
      "description": "200일선 위 기술 확인"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_200",
      "operator": "eq",
      "right": 1.0,
      "description": "200일선 이탈"
    }
  ],
  "indicators": [
    "dividend_yield",
    "debt_ratio",
    "dividend_cut_5y",
    "SMA200"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "배당수익률과 부채비율은 L1/L2에서 재무 안정성 필터로 해석",
    "배당 삭감 이력 데이터가 없으면 후보 확정 후 기술 proxy 백테스트로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l2_screening_indicator_mapping",
    "l1_screening_strategy_playbook",
    "l2_volatility"
  ],
  "confidence": 0.76
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "dividend_yield",
    "operator": "gte",
    "right": 0.04,
    "description": "배당수익률 4% 이상"
  },
  {
    "left": "debt_ratio",
    "operator": "lte",
    "right": 100.0,
    "description": "부채비율 100% 이하"
  },
  {
    "left": "dividend_cut_5y",
    "operator": "eq",
    "right": 0.0,
    "description": "최근 5년 배당 삭감 없음"
  },
  {
    "left": "close_above_sma_200",
    "operator": "eq",
    "right": 1.0,
    "description": "200일선 위 기술 확인"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "배당수익률과 부채비율은 L1/L2에서 재무 안정성 필터로 해석",
  "배당 삭감 이력 데이터가 없으면 후보 확정 후 기술 proxy 백테스트로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "dividend_defensive_a_a1",
    "strategy_name": "KOSPI200 배당 방어주 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-06:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [07] OK - expected `quality_growth` / actual `quality_growth_a`

**prompt**: 영업이익률과 ROE가 업종 평균보다 높고 매출 성장률도 양호한 퀄리티 성장주를 찾아줘.

**status**: `ready`

### KOSPI200 퀄리티 성장주 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "quality_growth_a",
  "name": "KOSPI200 퀄리티 성장주",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "sales_growth",
      "operator": "gte",
      "right": 0.1,
      "description": "매출 성장률 양호"
    },
    {
      "left": "operating_margin_improving",
      "operator": "eq",
      "right": 1.0,
      "description": "영업이익률 개선"
    },
    {
      "left": "debt_ratio",
      "operator": "lte",
      "right": 100.0,
      "description": "부채비율 100% 이하"
    },
    {
      "left": "close_above_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 위"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 이탈"
    }
  ],
  "indicators": [
    "sales_growth",
    "operating_margin",
    "debt_ratio",
    "SMA50"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "성장·수익성 조건은 후보 필터, 추세는 OHLCV proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping"
  ],
  "confidence": 0.73
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "sales_growth",
    "operator": "gte",
    "right": 0.1,
    "description": "매출 성장률 양호"
  },
  {
    "left": "operating_margin_improving",
    "operator": "eq",
    "right": 1.0,
    "description": "영업이익률 개선"
  },
  {
    "left": "debt_ratio",
    "operator": "lte",
    "right": 100.0,
    "description": "부채비율 100% 이하"
  },
  {
    "left": "close_above_sma_50",
    "operator": "eq",
    "right": 1.0,
    "description": "50일선 위"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "성장·수익성 조건은 후보 필터, 추세는 OHLCV proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "quality_growth_a_a1",
    "strategy_name": "KOSPI200 퀄리티 성장주 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-07:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [08] OK - expected `bollinger_squeeze_breakout` / actual `bollinger_squeeze_breakout_a`

**prompt**: 최근 20거래일 변동성이 낮아지고 볼린저밴드 폭이 축소된 뒤 상단을 돌파한 종목을 찾아줘.

**status**: `ready`

### KOSPI200 볼린저 스퀴즈 돌파 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "bollinger_squeeze_breakout_a",
  "name": "KOSPI200 볼린저 스퀴즈 돌파",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "bb_width_percentile",
      "operator": "lte",
      "right": 0.25,
      "description": "밴드 폭 축소"
    },
    {
      "left": "bollinger_breakout",
      "operator": "eq",
      "right": 1.0,
      "description": "상단 돌파 또는 밴드 재진입"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_middle_band",
      "operator": "eq",
      "right": 1.0,
      "description": "중심선 이탈"
    }
  ],
  "indicators": [
    "Bollinger Bands",
    "close"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "상단 돌파와 하단 재진입은 입력 문맥에 따라 L2에서 분기",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l2_screening_indicator_mapping",
    "l1_screening_strategy_playbook",
    "l1_strategy_catalog_50"
  ],
  "confidence": 0.77
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "bb_width_percentile",
    "operator": "lte",
    "right": 0.25,
    "description": "밴드 폭 축소"
  },
  {
    "left": "bollinger_breakout",
    "operator": "eq",
    "right": 1.0,
    "description": "상단 돌파 또는 밴드 재진입"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "상단 돌파와 하단 재진입은 입력 문맥에 따라 L2에서 분기",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "bollinger_squeeze_breakout_a_a1",
    "strategy_name": "KOSPI200 볼린저 스퀴즈 돌파 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-08:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [09] OK - expected `flow_accumulation` / actual `flow_accumulation_a`

**prompt**: 기관과 외국인이 최근 5거래일 연속 순매수했고 주가가 20일선 위에 있는 종목을 찾아줘.

**status**: `ready`

### KOSPI200 기관·외국인 수급 모멘텀 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "flow_accumulation_a",
  "name": "KOSPI200 기관·외국인 수급 모멘텀",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "net_buy_streak_5d",
      "operator": "gte",
      "right": 5.0,
      "description": "기관·외국인 5거래일 순매수"
    },
    {
      "left": "close_above_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "주가 20일선 위"
    },
    {
      "left": "volume_ratio_20",
      "operator": "gte",
      "right": 1.0,
      "description": "거래량 확인"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 이탈"
    }
  ],
  "indicators": [
    "net_buy_streak_5d",
    "SMA20",
    "volume_ratio_20"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "수급 데이터가 없으면 거래량과 20일선 proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping"
  ],
  "confidence": 0.6900000000000001
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "net_buy_streak_5d",
    "operator": "gte",
    "right": 5.0,
    "description": "기관·외국인 5거래일 순매수"
  },
  {
    "left": "close_above_sma_20",
    "operator": "eq",
    "right": 1.0,
    "description": "주가 20일선 위"
  },
  {
    "left": "volume_ratio_20",
    "operator": "gte",
    "right": 1.0,
    "description": "거래량 확인"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "수급 데이터가 없으면 거래량과 20일선 proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "flow_accumulation_a_a1",
    "strategy_name": "KOSPI200 기관·외국인 수급 모멘텀 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-09:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [10] OK - expected `rsi_rebound` / actual `rsi_rebound_a`

**prompt**: 최근 10거래일 하락했지만 거래량은 줄고 RSI가 과매도권에 진입한 기술적 반등 후보를 찾아줘.

**status**: `ready`

### KOSPI200 RSI 과매도 반등 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "rsi_rebound_a",
  "name": "KOSPI200 RSI 과매도 반등",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "rsi",
      "operator": "lte",
      "right": 30.0,
      "description": "RSI <= 30 또는 30 상향 회복"
    }
  ],
  "exit_conditions": [
    {
      "left": "rsi",
      "operator": "gte",
      "right": 70.0,
      "description": "RSI >= 70"
    }
  ],
  "indicators": [
    "RSI"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "RSI 30 회복 조건은 L2에서 과매도 반등 proxy로 해석",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion"
  ],
  "confidence": 0.87
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "rsi",
    "operator": "lte",
    "right": 30.0,
    "description": "RSI <= 30 또는 30 상향 회복"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "RSI 30 회복 조건은 L2에서 과매도 반등 proxy로 해석",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A3",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "rsi_rebound_a_a3",
    "strategy_name": "KOSPI200 RSI 과매도 반등 A3",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-10:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [11] OK - expected `growth_momentum` / actual `growth_momentum_a`

**prompt**: 매출 성장률 20% 이상, 영업이익률 개선, 부채비율 100% 이하인 성장주를 찾아줘.

**status**: `ready`

### KOSPI200 성장 모멘텀 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "growth_momentum_a",
  "name": "KOSPI200 성장 모멘텀",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "sales_growth",
      "operator": "gte",
      "right": 0.2,
      "description": "매출 성장률 양호"
    },
    {
      "left": "operating_margin_improving",
      "operator": "eq",
      "right": 1.0,
      "description": "영업이익률 개선"
    },
    {
      "left": "debt_ratio",
      "operator": "lte",
      "right": 100.0,
      "description": "부채비율 100% 이하"
    },
    {
      "left": "close_above_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 위"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 이탈"
    }
  ],
  "indicators": [
    "sales_growth",
    "operating_margin",
    "debt_ratio",
    "SMA50"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "성장·수익성 조건은 후보 필터, 추세는 OHLCV proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l2_talib_catalog_158",
    "l1_rsi_mean_reversion"
  ],
  "confidence": 0.73
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "sales_growth",
    "operator": "gte",
    "right": 0.2,
    "description": "매출 성장률 양호"
  },
  {
    "left": "operating_margin_improving",
    "operator": "eq",
    "right": 1.0,
    "description": "영업이익률 개선"
  },
  {
    "left": "debt_ratio",
    "operator": "lte",
    "right": 100.0,
    "description": "부채비율 100% 이하"
  },
  {
    "left": "close_above_sma_50",
    "operator": "eq",
    "right": 1.0,
    "description": "50일선 위"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "성장·수익성 조건은 후보 필터, 추세는 OHLCV proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "growth_momentum_a_a1",
    "strategy_name": "KOSPI200 성장 모멘텀 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-11:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [12] OK - expected `asset_value_catalyst` / actual `asset_value_catalyst_a`

**prompt**: PBR 1배 이하, 순현금 보유, 최근 자사주 매입 공시가 있는 저평가 종목을 찾아줘.

**status**: `ready`

### KOSPI200 자산가치 촉매 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "asset_value_catalyst_a",
  "name": "KOSPI200 자산가치 촉매",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "pbr",
      "operator": "lte",
      "right": 1.0,
      "description": "PBR 1배 이하"
    },
    {
      "left": "net_cash",
      "operator": "gte",
      "right": 1.0,
      "description": "순현금 보유"
    },
    {
      "left": "buyback_notice",
      "operator": "eq",
      "right": 1.0,
      "description": "자사주 매입 공시"
    },
    {
      "left": "close_above_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 위 기술 확인"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 이탈"
    }
  ],
  "indicators": [
    "PBR",
    "net_cash",
    "buyback_notice",
    "SMA20"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "공시/재무 조건은 후보 필터, OHLCV 기반 추세 회복은 백테스트 proxy로 사용",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion",
    "l2_rsi"
  ],
  "confidence": 0.72
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "pbr",
    "operator": "lte",
    "right": 1.0,
    "description": "PBR 1배 이하"
  },
  {
    "left": "net_cash",
    "operator": "gte",
    "right": 1.0,
    "description": "순현금 보유"
  },
  {
    "left": "buyback_notice",
    "operator": "eq",
    "right": 1.0,
    "description": "자사주 매입 공시"
  },
  {
    "left": "close_above_sma_20",
    "operator": "eq",
    "right": 1.0,
    "description": "20일선 위 기술 확인"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "공시/재무 조건은 후보 필터, OHLCV 기반 추세 회복은 백테스트 proxy로 사용",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "asset_value_catalyst_a_a1",
    "strategy_name": "KOSPI200 자산가치 촉매 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-12:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [13] OK - expected `oversold_quality` / actual `oversold_quality_a`

**prompt**: 최근 60거래일 고점 대비 20% 이상 하락했지만 실적 컨센서스가 유지되는 과매도 우량주를 찾아줘.

**status**: `ready`

### KOSPI200 과매도 우량주 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "oversold_quality_a",
  "name": "KOSPI200 과매도 우량주",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "drawdown_60d",
      "operator": "lte",
      "right": -0.2,
      "description": "60일 고점 대비 20% 이상 하락"
    },
    {
      "left": "earnings_revision_3m",
      "operator": "gte",
      "right": 0.0,
      "description": "실적 컨센서스 유지"
    },
    {
      "left": "rsi",
      "operator": "lte",
      "right": 35.0,
      "description": "과매도권"
    }
  ],
  "exit_conditions": [
    {
      "left": "rsi",
      "operator": "gte",
      "right": 60.0,
      "description": "반등 과열 전 청산"
    }
  ],
  "indicators": [
    "drawdown_60d",
    "earnings_revision_3m",
    "RSI"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "컨센서스 유지 조건은 후보 필터, 낙폭과 RSI는 OHLCV proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion",
    "l2_rsi"
  ],
  "confidence": 0.72
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "drawdown_60d",
    "operator": "lte",
    "right": -0.2,
    "description": "60일 고점 대비 20% 이상 하락"
  },
  {
    "left": "earnings_revision_3m",
    "operator": "gte",
    "right": 0.0,
    "description": "실적 컨센서스 유지"
  },
  {
    "left": "rsi",
    "operator": "lte",
    "right": 35.0,
    "description": "과매도권"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "컨센서스 유지 조건은 후보 필터, 낙폭과 RSI는 OHLCV proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A3",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "oversold_quality_a_a3",
    "strategy_name": "KOSPI200 과매도 우량주 A3",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "SEIBro feature mart 미적재: raw analyst report evidence만 사용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-13:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [14] OK - expected `relative_strength_leader` / actual `relative_strength_leader_a`

**prompt**: 시장지수보다 최근 1개월·3개월 상대강도가 모두 높은 섹터 주도주를 찾아줘.

**status**: `ready`

### KOSPI200 상대강도 주도주 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "relative_strength_leader_a",
  "name": "KOSPI200 상대강도 주도주",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 시장 대비 초과수익"
    },
    {
      "left": "relative_strength_60d",
      "operator": "gte",
      "right": 0.0,
      "description": "60일 시장 대비 초과수익"
    }
  ],
  "exit_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "lt",
      "right": 0.0,
      "description": "단기 상대강도 약화"
    }
  ],
  "indicators": [
    "relative_strength_20d",
    "relative_strength_60d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "시장 벤치마크는 KOSPI200 proxy로 해석",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping"
  ],
  "confidence": 0.79
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 시장 대비 초과수익"
  },
  {
    "left": "relative_strength_60d",
    "operator": "gte",
    "right": 0.0,
    "description": "60일 시장 대비 초과수익"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "시장 벤치마크는 KOSPI200 proxy로 해석",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "relative_strength_leader_a_a1",
    "strategy_name": "KOSPI200 상대강도 주도주 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-14:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [15] OK - expected `rate_sensitive_income` / actual `rate_sensitive_income_a`

**prompt**: 금리 하락기에 상대적으로 강했던 리츠·배당주·유틸리티 종목 중 현재 기술적 상승 신호가 있는 종목을 찾아줘.

**status**: `ready`

### KOSPI200 금리 민감 인컴주 (유틸리티) 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "rate_sensitive_income_a",
  "name": "KOSPI200 금리 민감 인컴주 (유틸리티)",
  "universe": "KRX",
  "market": "KRX",
  "sector": "유틸리티",
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "rate_down_proxy",
      "operator": "eq",
      "right": 1.0,
      "description": "금리 하락기 강세 업종 후보"
    },
    {
      "left": "dividend_yield",
      "operator": "gte",
      "right": 0.04,
      "description": "배당 또는 인컴 성격"
    },
    {
      "left": "close_above_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 위 기술 상승"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 이탈"
    }
  ],
  "indicators": [
    "rate_down_proxy",
    "dividend_yield",
    "SMA50"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe filtered to 유틸리티 sector",
    "daily adjusted close data",
    "금리 민감도와 업종 분류는 후보 필터, 현재 검증은 추세 proxy로 수행",
    "유틸리티 섹터로 후보를 한정합니다.",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_pullback"
  ],
  "confidence": 0.6900000000000001
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "rate_down_proxy",
    "operator": "eq",
    "right": 1.0,
    "description": "금리 하락기 강세 업종 후보"
  },
  {
    "left": "dividend_yield",
    "operator": "gte",
    "right": 0.04,
    "description": "배당 또는 인컴 성격"
  },
  {
    "left": "close_above_sma_50",
    "operator": "eq",
    "right": 1.0,
    "description": "50일선 위 기술 상승"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe filtered to 유틸리티 sector",
  "daily adjusted close data",
  "금리 민감도와 업종 분류는 후보 필터, 현재 검증은 추세 proxy로 수행",
  "유틸리티 섹터로 후보를 한정합니다.",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "rate_sensitive_income_a_a1",
    "strategy_name": "KOSPI200 금리 민감 인컴주 (유틸리티) A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용",
    "BOK macro mart 파일럿 상태: 거시 조건은 설명용 availability로만 표시"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-15:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [16] OK - expected `fx_exporter_revision` / actual `fx_exporter_revision_a`

**prompt**: 원달러 환율 상승기에 수혜를 받는 수출주 중 최근 이익 전망이 상향된 종목을 찾아줘.

**status**: `ready`

### KOSPI200 환율 수혜 이익상향 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "fx_exporter_revision_a",
  "name": "KOSPI200 환율 수혜 이익상향",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "fx_benefit_proxy",
      "operator": "eq",
      "right": 1.0,
      "description": "환율 상승 수혜 업종 후보"
    },
    {
      "left": "earnings_revision_3m",
      "operator": "gte",
      "right": 0.0,
      "description": "이익 전망 상향"
    },
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 상대강도 양호"
    }
  ],
  "exit_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "lt",
      "right": 0.0,
      "description": "상대강도 약화"
    }
  ],
  "indicators": [
    "fx_benefit_proxy",
    "earnings_revision_3m",
    "relative_strength_20d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "환율 수혜와 이익 전망은 후보 필터, OHLCV 상대강도는 검증 proxy로 사용",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping"
  ],
  "confidence": 0.68
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "fx_benefit_proxy",
    "operator": "eq",
    "right": 1.0,
    "description": "환율 상승 수혜 업종 후보"
  },
  {
    "left": "earnings_revision_3m",
    "operator": "gte",
    "right": 0.0,
    "description": "이익 전망 상향"
  },
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 상대강도 양호"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "환율 수혜와 이익 전망은 후보 필터, OHLCV 상대강도는 검증 proxy로 사용",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "fx_exporter_revision_a_a1",
    "strategy_name": "KOSPI200 환율 수혜 이익상향 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "BOK macro mart 파일럿 상태: 거시 조건은 설명용 availability로만 표시"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-16:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [17] OK - expected `margin_improvement` / actual `margin_improvement_a`

**prompt**: 원자재 가격 하락으로 마진 개선이 기대되는 소비재·화학·운송 종목을 찾아줘.

**status**: `ready`

### KOSPI200 원가하락 마진 개선 (운송) 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "margin_improvement_a",
  "name": "KOSPI200 원가하락 마진 개선 (운송)",
  "universe": "KRX",
  "market": "KRX",
  "sector": "운송",
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "input_cost_tailwind_proxy",
      "operator": "eq",
      "right": 1.0,
      "description": "원자재 가격 하락 수혜 후보"
    },
    {
      "left": "operating_margin_improving",
      "operator": "eq",
      "right": 1.0,
      "description": "영업이익률 개선"
    },
    {
      "left": "close_above_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 위"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 이탈"
    }
  ],
  "indicators": [
    "input_cost_tailwind_proxy",
    "operating_margin",
    "SMA50"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe filtered to 운송 sector",
    "daily adjusted close data",
    "원자재/업종 민감도는 후보 필터, 기술 추세는 검증 proxy로 사용",
    "운송 섹터로 후보를 한정합니다.",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping"
  ],
  "confidence": 0.67
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "input_cost_tailwind_proxy",
    "operator": "eq",
    "right": 1.0,
    "description": "원자재 가격 하락 수혜 후보"
  },
  {
    "left": "operating_margin_improving",
    "operator": "eq",
    "right": 1.0,
    "description": "영업이익률 개선"
  },
  {
    "left": "close_above_sma_50",
    "operator": "eq",
    "right": 1.0,
    "description": "50일선 위"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe filtered to 운송 sector",
  "daily adjusted close data",
  "원자재/업종 민감도는 후보 필터, 기술 추세는 검증 proxy로 사용",
  "운송 섹터로 후보를 한정합니다.",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "margin_improvement_a_a1",
    "strategy_name": "KOSPI200 원가하락 마진 개선 (운송) A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "BOK macro mart 파일럿 상태: 거시 조건은 설명용 availability로만 표시"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-17:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [18] OK - expected `growth_momentum` / actual `growth_momentum_a`

**prompt**: 최근 3개월 매출 성장률이 업종 상위 20%이고 주가가 50일선 위에 있는 성장 모멘텀 종목을 찾아줘.

**status**: `ready`

### KOSPI200 성장 모멘텀 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "growth_momentum_a",
  "name": "KOSPI200 성장 모멘텀",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "sales_growth",
      "operator": "gte",
      "right": 0.2,
      "description": "매출 성장률 양호"
    },
    {
      "left": "operating_margin_improving",
      "operator": "eq",
      "right": 1.0,
      "description": "영업이익률 개선"
    },
    {
      "left": "debt_ratio",
      "operator": "lte",
      "right": 100.0,
      "description": "부채비율 100% 이하"
    },
    {
      "left": "close_above_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 위"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 이탈"
    }
  ],
  "indicators": [
    "sales_growth",
    "operating_margin",
    "debt_ratio",
    "SMA50"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "성장·수익성 조건은 후보 필터, 추세는 OHLCV proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion"
  ],
  "confidence": 0.73
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "sales_growth",
    "operator": "gte",
    "right": 0.2,
    "description": "매출 성장률 양호"
  },
  {
    "left": "operating_margin_improving",
    "operator": "eq",
    "right": 1.0,
    "description": "영업이익률 개선"
  },
  {
    "left": "debt_ratio",
    "operator": "lte",
    "right": 100.0,
    "description": "부채비율 100% 이하"
  },
  {
    "left": "close_above_sma_50",
    "operator": "eq",
    "right": 1.0,
    "description": "50일선 위"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "성장·수익성 조건은 후보 필터, 추세는 OHLCV proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "growth_momentum_a_a1",
    "strategy_name": "KOSPI200 성장 모멘텀 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-18:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [19] OK - expected `short_covering_proxy` / actual `short_covering_proxy_a`

**prompt**: 공매도 잔고가 높지만 최근 거래량 증가와 양봉 돌파가 나온 숏커버링 후보 종목을 찾아줘.

**status**: `ready`

### KOSPI200 숏커버링 proxy 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "short_covering_proxy_a",
  "name": "KOSPI200 숏커버링 proxy",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "short_balance_high",
      "operator": "eq",
      "right": 1.0,
      "description": "공매도 잔고 높은 후보"
    },
    {
      "left": "volume_ratio_20",
      "operator": "gte",
      "right": 1.5,
      "description": "거래량 증가"
    },
    {
      "left": "bullish_breakout",
      "operator": "eq",
      "right": 1.0,
      "description": "양봉 돌파"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 이탈"
    }
  ],
  "indicators": [
    "short_balance",
    "volume_ratio_20",
    "bullish_breakout"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "공매도 잔고는 후보 필터, 거래량·양봉 돌파는 백테스트 proxy로 사용",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion"
  ],
  "confidence": 0.65
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "short_balance_high",
    "operator": "eq",
    "right": 1.0,
    "description": "공매도 잔고 높은 후보"
  },
  {
    "left": "volume_ratio_20",
    "operator": "gte",
    "right": 1.5,
    "description": "거래량 증가"
  },
  {
    "left": "bullish_breakout",
    "operator": "eq",
    "right": 1.0,
    "description": "양봉 돌파"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "공매도 잔고는 후보 필터, 거래량·양봉 돌파는 백테스트 proxy로 사용",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "short_covering_proxy_a_a1",
    "strategy_name": "KOSPI200 숏커버링 proxy A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-19:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [20] OK - expected `earnings_surprise_guidance` / actual `earnings_surprise_guidance_a`

**prompt**: 최근 실적 발표에서 어닝 서프라이즈를 기록했고 다음 분기 가이던스가 상향된 종목을 찾아줘.

**status**: `ready`

### KOSPI200 어닝 서프라이즈 가이던스 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "earnings_surprise_guidance_a",
  "name": "KOSPI200 어닝 서프라이즈 가이던스",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "earnings_revision_3m",
      "operator": "gte",
      "right": 0.0,
      "description": "최근 3개월 이익 전망 상향"
    },
    {
      "left": "breakout_high",
      "operator": "eq",
      "right": 1.0,
      "description": "20일 신고가 또는 상단 돌파"
    },
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 상대강도 양호"
    }
  ],
  "exit_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "lt",
      "right": 0.0,
      "description": "상대강도 약화"
    }
  ],
  "indicators": [
    "earnings_revision_3m",
    "rolling_high",
    "relative_strength_20d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "실적/가이던스 조건은 후보 필터, 신고가와 상대강도는 검증 proxy로 사용",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping"
  ],
  "confidence": 0.75
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "earnings_revision_3m",
    "operator": "gte",
    "right": 0.0,
    "description": "최근 3개월 이익 전망 상향"
  },
  {
    "left": "breakout_high",
    "operator": "eq",
    "right": 1.0,
    "description": "20일 신고가 또는 상단 돌파"
  },
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 상대강도 양호"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "실적/가이던스 조건은 후보 필터, 신고가와 상대강도는 검증 proxy로 사용",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "earnings_surprise_guidance_a_a1",
    "strategy_name": "KOSPI200 어닝 서프라이즈 가이던스 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "SEIBro feature mart 미적재: raw analyst report evidence만 사용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-20:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [21] OK - expected `fcf_recovery` / actual `fcf_recovery_a`

**prompt**: 현금흐름이 안정적이고 FCF 수익률이 높은 종목 중 최근 주가가 200일선 위로 회복한 종목을 찾아줘.

**status**: `ready`

### KOSPI200 FCF 회복주 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "fcf_recovery_a",
  "name": "KOSPI200 FCF 회복주",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "fcf_yield",
      "operator": "gte",
      "right": 0.05,
      "description": "FCF 수익률 양호"
    },
    {
      "left": "cashflow_stability",
      "operator": "eq",
      "right": 1.0,
      "description": "현금흐름 안정"
    },
    {
      "left": "close_above_sma_200",
      "operator": "eq",
      "right": 1.0,
      "description": "200일선 위 회복"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_200",
      "operator": "eq",
      "right": 1.0,
      "description": "200일선 재이탈"
    }
  ],
  "indicators": [
    "FCF_yield",
    "cashflow_stability",
    "SMA200"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "현금흐름 조건은 후보 필터, 200일선 회복은 기술 proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_pullback"
  ],
  "confidence": 0.72
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "fcf_yield",
    "operator": "gte",
    "right": 0.05,
    "description": "FCF 수익률 양호"
  },
  {
    "left": "cashflow_stability",
    "operator": "eq",
    "right": 1.0,
    "description": "현금흐름 안정"
  },
  {
    "left": "close_above_sma_200",
    "operator": "eq",
    "right": 1.0,
    "description": "200일선 위 회복"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "현금흐름 조건은 후보 필터, 200일선 회복은 기술 proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "fcf_recovery_a_a1",
    "strategy_name": "KOSPI200 FCF 회복주 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-21:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [22] OK - expected `reasonable_growth` / actual `reasonable_growth_a`

**prompt**: ROE 15% 이상, 매출 성장률 10% 이상, PER이 업종 평균 이하인 합리적 성장주를 찾아줘.

**status**: `ready`

### KOSPI200 합리적 성장주 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "reasonable_growth_a",
  "name": "KOSPI200 합리적 성장주",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "roe",
      "operator": "gte",
      "right": 0.15,
      "description": "ROE 15% 이상"
    },
    {
      "left": "sales_growth",
      "operator": "gte",
      "right": 0.1,
      "description": "매출 성장률 10% 이상"
    },
    {
      "left": "per_vs_industry",
      "operator": "lte",
      "right": 1.0,
      "description": "PER 업종 평균 이하"
    },
    {
      "left": "close_above_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 위"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 이탈"
    }
  ],
  "indicators": [
    "ROE",
    "sales_growth",
    "PER",
    "SMA50"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "성장성과 밸류에이션을 결합한 GARP 후보로 확정",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l2_talib_catalog_158",
    "l1_rsi_mean_reversion"
  ],
  "confidence": 0.75
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "roe",
    "operator": "gte",
    "right": 0.15,
    "description": "ROE 15% 이상"
  },
  {
    "left": "sales_growth",
    "operator": "gte",
    "right": 0.1,
    "description": "매출 성장률 10% 이상"
  },
  {
    "left": "per_vs_industry",
    "operator": "lte",
    "right": 1.0,
    "description": "PER 업종 평균 이하"
  },
  {
    "left": "close_above_sma_50",
    "operator": "eq",
    "right": 1.0,
    "description": "50일선 위"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "성장성과 밸류에이션을 결합한 GARP 후보로 확정",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "reasonable_growth_a_a1",
    "strategy_name": "KOSPI200 합리적 성장주 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-22:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [23] OK - expected `gap_hold_momentum` / actual `gap_hold_momentum_a`

**prompt**: 최근 5거래일 동안 갭 상승 후 갭을 메우지 않고 횡보하는 강한 수급 종목을 찾아줘.

**status**: `ready`

### KOSPI200 갭 유지 수급 모멘텀 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "gap_hold_momentum_a",
  "name": "KOSPI200 갭 유지 수급 모멘텀",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "gap_up",
      "operator": "eq",
      "right": 1.0,
      "description": "최근 갭 상승"
    },
    {
      "left": "gap_unfilled",
      "operator": "eq",
      "right": 1.0,
      "description": "갭 미충족 횡보"
    },
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 상대강도 양호"
    }
  ],
  "exit_conditions": [
    {
      "left": "gap_filled",
      "operator": "eq",
      "right": 1.0,
      "description": "갭 메움"
    }
  ],
  "indicators": [
    "gap_up",
    "gap_unfilled",
    "relative_strength_20d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "갭 유지 여부는 OHLCV 패턴으로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_pullback"
  ],
  "confidence": 0.7000000000000001
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "gap_up",
    "operator": "eq",
    "right": 1.0,
    "description": "최근 갭 상승"
  },
  {
    "left": "gap_unfilled",
    "operator": "eq",
    "right": 1.0,
    "description": "갭 미충족 횡보"
  },
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 상대강도 양호"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "갭 유지 여부는 OHLCV 패턴으로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "gap_hold_momentum_a_a1",
    "strategy_name": "KOSPI200 갭 유지 수급 모멘텀 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-23:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [24] OK - expected `bollinger_lower_reentry` / actual `bollinger_lower_reentry_a`

**prompt**: 볼린저밴드 하단 이탈 후 종가 기준으로 밴드 안에 재진입한 단기 반등 후보를 찾아줘.

**status**: `ready`

### KOSPI200 볼린저 하단 재진입 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "bollinger_lower_reentry_a",
  "name": "KOSPI200 볼린저 하단 재진입",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "close_below_lower_band_recent",
      "operator": "eq",
      "right": 1.0,
      "description": "최근 종가가 볼린저 하단 밴드 아래를 확인"
    },
    {
      "left": "close_cross_above_lower_band",
      "operator": "eq",
      "right": 1.0,
      "description": "종가가 하단 밴드 위로 재진입"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_middle_band",
      "operator": "eq",
      "right": 1.0,
      "description": "중심선 이탈"
    }
  ],
  "indicators": [
    "Bollinger Bands",
    "close"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "볼린저 하단 재진입은 RSI 반등과 별도 의미로 보존",
    "판정 기준은 종가 기준으로 고정",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion",
    "l2_volatility"
  ],
  "confidence": 0.8300000000000001
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "close_below_lower_band_recent",
    "operator": "eq",
    "right": 1.0,
    "description": "최근 종가가 볼린저 하단 밴드 아래를 확인"
  },
  {
    "left": "close_cross_above_lower_band",
    "operator": "eq",
    "right": 1.0,
    "description": "종가가 하단 밴드 위로 재진입"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "볼린저 하단 재진입은 RSI 반등과 별도 의미로 보존",
  "판정 기준은 종가 기준으로 고정",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "bollinger_lower_reentry_a_a1",
    "strategy_name": "KOSPI200 볼린저 하단 재진입 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-24:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [25] OK - expected `breakout_setup` / actual `breakout_setup_a`

**prompt**: 20일 이동평균 거래대금이 충분하고 최근 신고가 근처에서 거래량이 줄며 횡보하는 돌파 대기 종목을 찾아줘.

**status**: `ready`

### KOSPI200 돌파 대기 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "breakout_setup_a",
  "name": "KOSPI200 돌파 대기",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "near_recent_high",
      "operator": "eq",
      "right": 1.0,
      "description": "최근 신고가 근처"
    },
    {
      "left": "volume_dry_up",
      "operator": "eq",
      "right": 1.0,
      "description": "거래량 감소 횡보"
    },
    {
      "left": "turnover_sufficient",
      "operator": "eq",
      "right": 1.0,
      "description": "거래대금 충분"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 이탈"
    }
  ],
  "indicators": [
    "near_recent_high",
    "volume_dry_up",
    "turnover"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "거래대금과 횡보 압축은 OHLCV proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping"
  ],
  "confidence": 0.7100000000000001
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "near_recent_high",
    "operator": "eq",
    "right": 1.0,
    "description": "최근 신고가 근처"
  },
  {
    "left": "volume_dry_up",
    "operator": "eq",
    "right": 1.0,
    "description": "거래량 감소 횡보"
  },
  {
    "left": "turnover_sufficient",
    "operator": "eq",
    "right": 1.0,
    "description": "거래대금 충분"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "거래대금과 횡보 압축은 OHLCV proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "breakout_setup_a_a1",
    "strategy_name": "KOSPI200 돌파 대기 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-25:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [26] OK - expected `midterm_pullback` / actual `midterm_pullback_a`

**prompt**: 최근 1개월 수익률은 시장보다 약했지만 6개월 수익률은 강한 중기 상승추세 눌림목 종목을 찾아줘.

**status**: `ready`

### KOSPI200 중기 상승추세 눌림목 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "midterm_pullback_a",
  "name": "KOSPI200 중기 상승추세 눌림목",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "lt",
      "right": 0.0,
      "description": "최근 1개월 시장 대비 약세"
    },
    {
      "left": "relative_strength_120d",
      "operator": "gte",
      "right": 0.0,
      "description": "6개월 시장 대비 강세"
    },
    {
      "left": "close_above_sma_200",
      "operator": "eq",
      "right": 1.0,
      "description": "장기 추세 유지"
    }
  ],
  "exit_conditions": [
    {
      "left": "relative_strength_120d",
      "operator": "lt",
      "right": 0.0,
      "description": "중기 상대강도 훼손"
    }
  ],
  "indicators": [
    "relative_strength_20d",
    "relative_strength_120d",
    "SMA200"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "중기 추세와 단기 조정의 조합을 OHLCV proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_pullback"
  ],
  "confidence": 0.75
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "relative_strength_20d",
    "operator": "lt",
    "right": 0.0,
    "description": "최근 1개월 시장 대비 약세"
  },
  {
    "left": "relative_strength_120d",
    "operator": "gte",
    "right": 0.0,
    "description": "6개월 시장 대비 강세"
  },
  {
    "left": "close_above_sma_200",
    "operator": "eq",
    "right": 1.0,
    "description": "장기 추세 유지"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "중기 추세와 단기 조정의 조합을 OHLCV proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "midterm_pullback_a_a1",
    "strategy_name": "KOSPI200 중기 상승추세 눌림목 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-26:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [27] OK - expected `margin_inventory_quality` / actual `margin_inventory_quality_a`

**prompt**: 매출총이익률이 3개 분기 연속 개선되고 재고자산 증가율이 매출 증가율보다 낮은 종목을 찾아줘.

**status**: `ready`

### KOSPI200 마진·재고 퀄리티 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "margin_inventory_quality_a",
  "name": "KOSPI200 마진·재고 퀄리티",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "gross_margin_streak",
      "operator": "gte",
      "right": 3.0,
      "description": "매출총이익률 3개 분기 개선"
    },
    {
      "left": "inventory_growth_vs_sales",
      "operator": "lte",
      "right": 1.0,
      "description": "재고 증가율이 매출 증가율 이하"
    },
    {
      "left": "close_above_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 위"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 이탈"
    }
  ],
  "indicators": [
    "gross_margin",
    "inventory_growth",
    "sales_growth",
    "SMA50"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "분기 재무 품질 조건은 후보 필터, 가격 추세로 타이밍을 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l2_volatility"
  ],
  "confidence": 0.7100000000000001
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "gross_margin_streak",
    "operator": "gte",
    "right": 3.0,
    "description": "매출총이익률 3개 분기 개선"
  },
  {
    "left": "inventory_growth_vs_sales",
    "operator": "lte",
    "right": 1.0,
    "description": "재고 증가율이 매출 증가율 이하"
  },
  {
    "left": "close_above_sma_50",
    "operator": "eq",
    "right": 1.0,
    "description": "50일선 위"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "분기 재무 품질 조건은 후보 필터, 가격 추세로 타이밍을 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "margin_inventory_quality_a_a1",
    "strategy_name": "KOSPI200 마진·재고 퀄리티 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-27:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [28] OK - expected `operating_profit_pullback` / actual `operating_profit_pullback_a`

**prompt**: 최근 4분기 연속 영업이익이 전년 대비 증가했고 주가는 60일 고점 대비 10% 이상 조정받은 종목을 찾아줘.

**status**: `ready`

### KOSPI200 이익성장 조정주 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "operating_profit_pullback_a",
  "name": "KOSPI200 이익성장 조정주",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "operating_profit_growth_streak",
      "operator": "gte",
      "right": 4.0,
      "description": "4분기 연속 영업이익 증가"
    },
    {
      "left": "drawdown_60d",
      "operator": "lte",
      "right": -0.1,
      "description": "60일 고점 대비 10% 이상 조정"
    },
    {
      "left": "relative_strength_60d",
      "operator": "gte",
      "right": 0.0,
      "description": "중기 상대강도 유지"
    }
  ],
  "exit_conditions": [
    {
      "left": "relative_strength_60d",
      "operator": "lt",
      "right": 0.0,
      "description": "중기 상대강도 훼손"
    }
  ],
  "indicators": [
    "operating_profit_growth",
    "drawdown_60d",
    "relative_strength_60d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "분기 이익 조건은 후보 필터, 조정 폭과 상대강도는 OHLCV proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l2_talib_catalog_158",
    "l1_rsi_mean_reversion"
  ],
  "confidence": 0.7100000000000001
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "operating_profit_growth_streak",
    "operator": "gte",
    "right": 4.0,
    "description": "4분기 연속 영업이익 증가"
  },
  {
    "left": "drawdown_60d",
    "operator": "lte",
    "right": -0.1,
    "description": "60일 고점 대비 10% 이상 조정"
  },
  {
    "left": "relative_strength_60d",
    "operator": "gte",
    "right": 0.0,
    "description": "중기 상대강도 유지"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "분기 이익 조건은 후보 필터, 조정 폭과 상대강도는 OHLCV proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "operating_profit_pullback_a_a1",
    "strategy_name": "KOSPI200 이익성장 조정주 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-28:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [29] OK - expected `low_vol_defensive` / actual `low_vol_defensive_a`

**prompt**: 저변동성 종목 중 최근 20일 수익률이 시장을 이기고 배당수익률도 높은 방어주를 찾아줘.

**status**: `ready`

### KOSPI200 저변동 배당 방어주 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "low_vol_defensive_a",
  "name": "KOSPI200 저변동 배당 방어주",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "realized_volatility_20d",
      "operator": "lte",
      "right": 0.25,
      "description": "20일 변동성 낮음"
    },
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 시장 대비 우위"
    },
    {
      "left": "dividend_yield",
      "operator": "gte",
      "right": 0.04,
      "description": "배당수익률 양호"
    },
    {
      "left": "close_above_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 위"
    }
  ],
  "exit_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "lt",
      "right": 0.0,
      "description": "상대강도 약화"
    }
  ],
  "indicators": [
    "realized_volatility_20d",
    "relative_strength_20d",
    "dividend_yield",
    "SMA20"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "방어주 성격은 저변동성과 배당 조건, 진입 타이밍은 OHLCV proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_pullback"
  ],
  "confidence": 0.73
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "realized_volatility_20d",
    "operator": "lte",
    "right": 0.25,
    "description": "20일 변동성 낮음"
  },
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 시장 대비 우위"
  },
  {
    "left": "dividend_yield",
    "operator": "gte",
    "right": 0.04,
    "description": "배당수익률 양호"
  },
  {
    "left": "close_above_sma_20",
    "operator": "eq",
    "right": 1.0,
    "description": "20일선 위"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "방어주 성격은 저변동성과 배당 조건, 진입 타이밍은 OHLCV proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "low_vol_defensive_a_a1",
    "strategy_name": "KOSPI200 저변동 배당 방어주 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-29:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [30] OK - expected `breakout_pullback` / actual `breakout_pullback_a`

**prompt**: 최근 120일 신고가를 돌파한 뒤 20일선까지 되돌림이 나온 추세 지속 후보를 찾아줘.

**status**: `ready`

### KOSPI200 신고가 돌파 후 되돌림 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "breakout_pullback_a",
  "name": "KOSPI200 신고가 돌파 후 되돌림",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "breakout_high",
      "operator": "eq",
      "right": 1.0,
      "description": "120일 신고가 돌파 이력"
    },
    {
      "left": "pullback_to_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선까지 되돌림"
    },
    {
      "left": "relative_strength_60d",
      "operator": "gte",
      "right": 0.0,
      "description": "중기 상대강도 유지"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 이탈"
    }
  ],
  "indicators": [
    "rolling_high",
    "SMA20",
    "relative_strength_60d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "신고가 이후 눌림목을 추세 지속 proxy로 검증",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_pullback",
    "l1_rsi_mean_reversion"
  ],
  "confidence": 0.77
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "breakout_high",
    "operator": "eq",
    "right": 1.0,
    "description": "120일 신고가 돌파 이력"
  },
  {
    "left": "pullback_to_sma_20",
    "operator": "eq",
    "right": 1.0,
    "description": "20일선까지 되돌림"
  },
  {
    "left": "relative_strength_60d",
    "operator": "gte",
    "right": 0.0,
    "description": "중기 상대강도 유지"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "신고가 이후 눌림목을 추세 지속 proxy로 검증",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "breakout_pullback_a_a1",
    "strategy_name": "KOSPI200 신고가 돌파 후 되돌림 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-30:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [31] OK - expected `pullback_rsi_volume` / actual `pullback_rsi_volume_a`

**prompt**: 200일선 위 상승추세를 유지하면서 RSI(14)가 40 이하로 눌리고 거래량이 20일 평균 이상인 종목을 찾아줘.

**status**: `ready`

### KOSPI200 RSI40 거래량 눌림목 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "pullback_rsi_volume_a",
  "name": "KOSPI200 RSI40 거래량 눌림목",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "close_above_sma_200",
      "operator": "eq",
      "right": 1.0,
      "description": "주가가 200일선 위"
    },
    {
      "left": "rsi",
      "operator": "lte",
      "right": 40.0,
      "description": "RSI(14) <= 40 눌림"
    },
    {
      "left": "volume_ratio_20",
      "operator": "gte",
      "right": 1.0,
      "description": "거래량이 20일 평균 이상"
    }
  ],
  "exit_conditions": [
    {
      "left": "rsi",
      "operator": "gte",
      "right": 60.0,
      "description": "RSI >= 60 회복"
    },
    {
      "left": "close_below_sma_200",
      "operator": "eq",
      "right": 1.0,
      "description": "200일선 이탈"
    }
  ],
  "indicators": [
    "SMA200",
    "RSI",
    "volume_ratio_20"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "200일선 위는 상승추세 필터로 해석",
    "RSI 40 이하는 과매도보다 완만한 눌림목 조건으로 해석",
    "거래량 20일 평균 이상은 volume_ratio_20 >= 1.0으로 해석",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion",
    "l2_talib_catalog_158"
  ],
  "confidence": 0.85
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "close_above_sma_200",
    "operator": "eq",
    "right": 1.0,
    "description": "주가가 200일선 위"
  },
  {
    "left": "rsi",
    "operator": "lte",
    "right": 40.0,
    "description": "RSI(14) <= 40 눌림"
  },
  {
    "left": "volume_ratio_20",
    "operator": "gte",
    "right": 1.0,
    "description": "거래량이 20일 평균 이상"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "200일선 위는 상승추세 필터로 해석",
  "RSI 40 이하는 과매도보다 완만한 눌림목 조건으로 해석",
  "거래량 20일 평균 이상은 volume_ratio_20 >= 1.0으로 해석",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A3",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "pullback_rsi_volume_a_a3",
    "strategy_name": "KOSPI200 RSI40 거래량 눌림목 A3",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-31:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [32] OK - expected `breakout_volume_momentum` / actual `breakout_volume_momentum_a`

**prompt**: 최근 52주 신고가를 돌파했고 거래량이 20일 평균 대비 150% 이상 증가한 종목을 찾아줘.

**status**: `ready`

### KOSPI200 거래량 돌파 모멘텀 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "breakout_volume_momentum_a",
  "name": "KOSPI200 거래량 돌파 모멘텀",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "breakout_high",
      "operator": "eq",
      "right": 1.0,
      "description": "신고가 또는 상단 돌파"
    },
    {
      "left": "volume_ratio_20",
      "operator": "gte",
      "right": 1.5,
      "description": "20일 평균 대비 거래량 150% 이상"
    },
    {
      "left": "close_above_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "종가가 20일선 위"
    },
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 상대강도 양호"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_20",
      "operator": "eq",
      "right": 1.0,
      "description": "20일선 이탈"
    }
  ],
  "indicators": [
    "rolling_high",
    "volume_ratio_20",
    "SMA20",
    "relative_strength_20d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "신고가 기간은 입력의 52주/120일/20일 표현에 맞춰 L2에서 선택",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion",
    "l2_rsi"
  ],
  "confidence": 0.8300000000000001
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "breakout_high",
    "operator": "eq",
    "right": 1.0,
    "description": "신고가 또는 상단 돌파"
  },
  {
    "left": "volume_ratio_20",
    "operator": "gte",
    "right": 1.5,
    "description": "20일 평균 대비 거래량 150% 이상"
  },
  {
    "left": "close_above_sma_20",
    "operator": "eq",
    "right": 1.0,
    "description": "종가가 20일선 위"
  },
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 상대강도 양호"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "신고가 기간은 입력의 52주/120일/20일 표현에 맞춰 L2에서 선택",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "breakout_volume_momentum_a_a1",
    "strategy_name": "KOSPI200 거래량 돌파 모멘텀 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-32:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [33] OK - expected `reasonable_growth` / actual `reasonable_growth_a`

**prompt**: ROE 15% 이상, 매출 성장률 10% 이상, PER이 업종 평균 이하인 합리적 성장주를 찾아줘.

**status**: `ready`

### KOSPI200 합리적 성장주 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "reasonable_growth_a",
  "name": "KOSPI200 합리적 성장주",
  "universe": "KRX",
  "market": "KRX",
  "sector": null,
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "roe",
      "operator": "gte",
      "right": 0.15,
      "description": "ROE 15% 이상"
    },
    {
      "left": "sales_growth",
      "operator": "gte",
      "right": 0.1,
      "description": "매출 성장률 10% 이상"
    },
    {
      "left": "per_vs_industry",
      "operator": "lte",
      "right": 1.0,
      "description": "PER 업종 평균 이하"
    },
    {
      "left": "close_above_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 위"
    }
  ],
  "exit_conditions": [
    {
      "left": "close_below_sma_50",
      "operator": "eq",
      "right": 1.0,
      "description": "50일선 이탈"
    }
  ],
  "indicators": [
    "ROE",
    "sales_growth",
    "PER",
    "SMA50"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe",
    "daily adjusted close data",
    "성장성과 밸류에이션을 결합한 GARP 후보로 확정",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l2_talib_catalog_158",
    "l1_rsi_mean_reversion"
  ],
  "confidence": 0.75
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "roe",
    "operator": "gte",
    "right": 0.15,
    "description": "ROE 15% 이상"
  },
  {
    "left": "sales_growth",
    "operator": "gte",
    "right": 0.1,
    "description": "매출 성장률 10% 이상"
  },
  {
    "left": "per_vs_industry",
    "operator": "lte",
    "right": 1.0,
    "description": "PER 업종 평균 이하"
  },
  {
    "left": "close_above_sma_50",
    "operator": "eq",
    "right": 1.0,
    "description": "50일선 위"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe",
  "daily adjusted close data",
  "성장성과 밸류에이션을 결합한 GARP 후보로 확정",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "reasonable_growth_a_a1",
    "strategy_name": "KOSPI200 합리적 성장주 A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": [
    "OpenDART 재무/공시 mart 미적재: 가격/TA 조건으로 1차 proxy 적용"
  ]
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-33:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [34] OK - expected `relative_strength_leader` / actual `relative_strength_leader_a`

**prompt**: 반도체 섹터 주도주 중 상대강도 강한 종목을 찾아줘.

**status**: `ready`

### KOSPI200 상대강도 주도주 (반도체) 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "relative_strength_leader_a",
  "name": "KOSPI200 상대강도 주도주 (반도체)",
  "universe": "KRX",
  "market": "KRX",
  "sector": "반도체",
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "gte",
      "right": 0.0,
      "description": "20일 시장 대비 초과수익"
    },
    {
      "left": "relative_strength_60d",
      "operator": "gte",
      "right": 0.0,
      "description": "60일 시장 대비 초과수익"
    }
  ],
  "exit_conditions": [
    {
      "left": "relative_strength_20d",
      "operator": "lt",
      "right": 0.0,
      "description": "단기 상대강도 약화"
    }
  ],
  "indicators": [
    "relative_strength_20d",
    "relative_strength_60d"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe filtered to 반도체 sector",
    "daily adjusted close data",
    "시장 벤치마크는 KOSPI200 proxy로 해석",
    "반도체 섹터로 후보를 한정합니다.",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_rsi",
    "l2_screening_indicator_mapping"
  ],
  "confidence": 0.79
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "relative_strength_20d",
    "operator": "gte",
    "right": 0.0,
    "description": "20일 시장 대비 초과수익"
  },
  {
    "left": "relative_strength_60d",
    "operator": "gte",
    "right": 0.0,
    "description": "60일 시장 대비 초과수익"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe filtered to 반도체 sector",
  "daily adjusted close data",
  "시장 벤치마크는 KOSPI200 proxy로 해석",
  "반도체 섹터로 후보를 한정합니다.",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A1",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "relative_strength_leader_a_a1",
    "strategy_name": "KOSPI200 상대강도 주도주 (반도체) A1",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-34:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```

## [35] OK - expected `rsi_rebound` / actual `rsi_rebound_a`

**prompt**: 반도체 섹터에서 RSI 30 이하로 과매도된 반등 후보 종목을 찾아줘.

**status**: `ready`

### KOSPI200 RSI 과매도 반등 (반도체) 분석 결과

BUY / confidence 0.82. Risk Manager did not change the signal.

#### StrategySpec (`strategy`)

```json
{
  "strategy_id": "rsi_rebound_a",
  "name": "KOSPI200 RSI 과매도 반등 (반도체)",
  "universe": "KRX",
  "market": "KRX",
  "sector": "반도체",
  "timeframe": "daily",
  "entry_conditions": [
    {
      "left": "rsi",
      "operator": "lte",
      "right": 30.0,
      "description": "RSI <= 30 또는 30 상향 회복"
    }
  ],
  "exit_conditions": [
    {
      "left": "rsi",
      "operator": "gte",
      "right": 70.0,
      "description": "RSI >= 70"
    }
  ],
  "indicators": [
    "RSI"
  ],
  "risk_constraints": {
    "max_position_pct": 0.1,
    "stop_loss_pct": 0.08
  },
  "assumptions": [
    "fixture KRX universe filtered to 반도체 sector",
    "daily adjusted close data",
    "RSI 30 회복 조건은 L2에서 과매도 반등 proxy로 해석",
    "반도체 섹터로 후보를 한정합니다.",
    "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
    "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
  ],
  "source_refs": [
    "l1_strategy_catalog_50",
    "l1_screening_strategy_playbook",
    "l2_screening_indicator_mapping",
    "l1_rsi_mean_reversion",
    "l2_talib_catalog_158"
  ],
  "confidence": 0.87
}
```

#### 진입 조건 (`entry_conditions`)

```json
[
  {
    "left": "rsi",
    "operator": "lte",
    "right": 30.0,
    "description": "RSI <= 30 또는 30 상향 회복"
  }
]
```

#### 검증 가정 (`assumptions`)

```json
[
  "fixture KRX universe filtered to 반도체 sector",
  "daily adjusted close data",
  "RSI 30 회복 조건은 L2에서 과매도 반등 proxy로 해석",
  "반도체 섹터로 후보를 한정합니다.",
  "L1/L2 검색 결과와 Research Judge 검토로 조건을 명시화함",
  "기술 조건은 ready로 진행하고, 미적재 데이터 조건은 proxy와 data_availability에 명시합니다."
]
```

#### 후보 코드 백테스트 (`backtest`)

```json
{
  "selected_candidate_id": "A3",
  "metrics": {
    "sharpe_ratio": 8.769372,
    "max_drawdown": -0.001149,
    "win_rate": 0.0,
    "total_return": 0.038407,
    "in_sample_sharpe": 8.769372,
    "out_sample_sharpe": 8.769372,
    "degradation": 0.0
  },
  "engine_summary": {
    "strategy_id": "rsi_rebound_a_a3",
    "strategy_name": "KOSPI200 RSI 과매도 반등 (반도체) A3",
    "initial_capital": 1000000.0,
    "final_equity": 1038407.242832,
    "cash": 62.242832,
    "final_cash": 62.242832,
    "open_positions": 1,
    "metrics": {
      "total_return": 0.0384072428,
      "cagr": 22.7075964617,
      "sharpe": 8.7693715412,
      "sortino": 306.788197259,
      "adjusted_sortino": 216.9320146698,
      "max_drawdown": -0.0011487572,
      "calmar": 19767.0988214781,
      "volatility": 0.3683308151,
      "win_rate": 0.5,
      "avg_return": 0.0192263677,
      "avg_win": 0.0396014925,
      "avg_loss": -0.0011487572,
      "profit_factor": 34.4733365776,
      "payoff_ratio": 34.4733365776,
      "recovery_factor": 33.4733365776,
      "expected_return": 0.0126419226,
      "cvar": -0.0253474017,
      "conditional_value_at_risk": -0.0253474017,
      "value_at_risk": -0.0253474017,
      "best": 0.0396014925,
      "worst": -0.0011487572,
      "omega": 34.4733365776,
      "common_sense_ratio": 1188.4109347911,
      "gain_to_pain_ratio": 33.4733365776,
      "geometric_mean": 0.0126419226,
      "kelly_criterion": 0.4854960369,
      "exposure": 0.67,
      "cpc_index": 594.2054673955,
      "tail_ratio": 34.4733365776,
      "risk_of_ruin": 0.037037037,
      "ulcer_index": 0.000812294,
      "ulcer_performance_index": 47.2824415981,
      "outlier_loss_ratio": 0.98,
      "outlier_win_ratio": 1.96,
      "kurtosis": 0.0,
      "skew": 1.7272757003,
      "consecutive_negative_periods": 1,
      "consecutive_positive_periods": 1,
      "monthly_returns": [
        {
          "index": "2026",
          "JAN": 0.0384072428,
          "FEB": 0,
          "MAR": 0,
          "APR": 0,
          "MAY": 0,
          "JUN": 0,
          "JUL": 0,
          "AUG": 0,
          "SEP": 0,
          "OCT": 0,
          "NOV": 0,
          "DEC": 0,
          "EOY": 0.0384072428
        }
      ],
      "drawdown_series": [
        {
          "date": "2026-01-03T00:00:00",
          "value": 0.0
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0
        }
      ],
      "rolling_volatility": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.3683308151
        }
      ],
      "rolling_sharpe": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 8.7693715412
        }
      ],
      "rolling_sortino": [
        {
          "date": "2026-01-03T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-04T00:00:00",
          "value": null
        },
        {
          "date": "2026-01-05T00:00:00",
          "value": 306.788197259
        }
      ],
      "outliers": {
        "loss_threshold": -0.001125782,
        "win_threshold": 0.0388094626,
        "losses": [
          {
            "date": "2026-01-04T00:00:00",
            "value": -0.0011487572
          }
        ],
        "wins": [
          {
            "date": "2026-01-05T00:00:00",
            "value": 0.0396014925
          }
        ]
      },
      "drawdown_details": [
        {
          "index": 0,
          "start": "2026-01-04",
          "valley": "2026-01-04",
          "end": "2026-01-04",
          "days": 1,
          "max drawdown": -0.1148757168,
          "99% max drawdown": null
        }
      ],
      "information_ratio": null,
      "r_squared": null,
      "greeks": null,
      "rolling_greeks": [],
      "compare": {},
      "montecarlo": {
        "seed": 42,
        "simulations": 250,
        "horizon_days": 3,
        "positive_return_probability": 0.724,
        "loss_probability": 0.236,
        "total_return_quantiles": {
          "mean": 0.0404241931,
          "median": 0.0384072428,
          "p05": -0.0022961947,
          "p25": 0.0,
          "p75": 0.0795297195,
          "p95": 0.0807712632,
          "best": 0.1235714183,
          "worst": -0.0034423141
        },
        "cagr_quantiles": {
          "mean": 740.6833917228,
          "median": 22.7075964617,
          "p05": -0.1756022335,
          "p25": 0.0,
          "p75": 618.0228056853,
          "p95": 680.7705637104,
          "best": 17800.5315834667,
          "worst": -0.2514768962
        },
        "max_drawdown_quantiles": {
          "mean": -0.0007764279,
          "median": -0.0011487572,
          "p05": -0.0022961947,
          "p25": -0.0011487572,
          "p75": 0.0,
          "p95": 0.0,
          "best": 0.0,
          "worst": -0.0022961947
        },
        "sharpe_quantiles": {
          "mean": 6.6620733497,
          "median": 10.7402428204,
          "p05": -22.4499443206,
          "p25": 0.0,
          "p75": 11.2249721603,
          "p95": 22.4499443206,
          "best": 22.4499443206,
          "worst": -22.4499443206
        }
      },
      "montecarlo_mean": [
        {
          "step": 1,
          "mean_cumulative_return": 0.0140795062,
          "p05_cumulative_return": -0.0011487572,
          "p95_cumulative_return": 0.0396014925
        },
        {
          "step": 2,
          "mean_cumulative_return": 0.0279690517,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        },
        {
          "step": 3,
          "mean_cumulative_return": 0.0404241931,
          "p05_cumulative_return": -0.0022961947,
          "p95_cumulative_return": 0.0807712632
        }
      ],
      "montecarlo_cagr": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "montecarlo_drawdown": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "montecarlo_sharpe": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      },
      "sharpe_ratio": 8.7693715412,
      "sortino_ratio": 306.788197259,
      "adjusted_sortino_ratio": 216.9320146698,
      "calmar_ratio": 19767.0988214781,
      "annualized_volatility": 0.3683308151,
      "avg_period_return": 0.0192263677,
      "avg_positive_period_return": 0.0396014925,
      "avg_negative_period_return": -0.0011487572,
      "best_period_return": 0.0396014925,
      "worst_period_return": -0.0011487572,
      "metric_warnings": [
        {
          "metric": "kurtosis",
          "warning": "kurtosis returned a non-finite value"
        },
        {
          "metric": "kurtosis",
          "warning": "kurtosis was unavailable and defaulted to 0.0"
        },
        {
          "metric": "rolling_greeks",
          "warning": "rolling_greeks was unavailable and defaulted to an empty list"
        },
        {
          "metric": "compare",
          "warning": "compare was unavailable and defaulted to an empty object"
        }
      ]
    },
    "period_return": 0.0384072428,
    "total_return": 0.0384072428,
    "cagr": 22.7075964617,
    "max_drawdown": -0.0011487572,
    "daily_sharpe_like": 8.7693715412,
    "sharpe": 8.7693715412,
    "sharpe_ratio": 8.7693715412,
    "sortino": 306.788197259,
    "sortino_ratio": 306.788197259,
    "adjusted_sortino": 216.9320146698,
    "adjusted_sortino_ratio": 216.9320146698,
    "calmar": 19767.0988214781,
    "calmar_ratio": 19767.0988214781,
    "volatility": 0.3683308151,
    "annualized_volatility": 0.3683308151,
    "common_sense_ratio": 1188.4109347911,
    "gain_to_pain_ratio": 33.4733365776,
    "geometric_mean": 0.0126419226,
    "kelly_criterion": 0.4854960369,
    "exposure": 0.67,
    "cpc_index": 594.2054673955,
    "omega": 34.4733365776,
    "value_at_risk": -0.0253474017,
    "conditional_value_at_risk": -0.0253474017,
    "cvar": -0.0253474017,
    "ulcer_index": 0.000812294,
    "ulcer_performance_index": 47.2824415981,
    "risk_of_ruin": 0.037037037,
    "tail_ratio": 34.4733365776,
    "kurtosis": 0.0,
    "skew": 1.7272757003,
    "trade_count": 0,
    "trade_win_rate": 0.0,
    "win_rate": 0.0,
    "return_win_rate": 0.5,
    "signal_count": 4,
    "avg_holding_days": 0.0,
    "avg_return": 0.0192263677,
    "avg_period_return": 0.0192263677,
    "avg_win": 0.0396014925,
    "avg_positive_period_return": 0.0396014925,
    "avg_loss": -0.0011487572,
    "avg_negative_period_return": -0.0011487572,
    "best": 0.0396014925,
    "best_period_return": 0.0396014925,
    "worst": -0.0011487572,
    "worst_period_return": -0.0011487572,
    "profit_factor": 34.4733365776,
    "payoff_ratio": 34.4733365776,
    "outlier_loss_ratio": 0.98,
    "outlier_win_ratio": 1.96,
    "recovery_factor": 33.4733365776,
    "expected_return": 0.0126419226,
    "consecutive_negative_periods": 1,
    "consecutive_positive_periods": 1,
    "monthly_returns": [
      {
        "index": "2026",
        "JAN": 0.0384072428,
        "FEB": 0,
        "MAR": 0,
        "APR": 0,
        "MAY": 0,
        "JUN": 0,
        "JUL": 0,
        "AUG": 0,
        "SEP": 0,
        "OCT": 0,
        "NOV": 0,
        "DEC": 0,
        "EOY": 0.0384072428
      }
    ],
    "drawdown_details": [
      {
        "index": 0,
        "start": "2026-01-04",
        "valley": "2026-01-04",
        "end": "2026-01-04",
        "days": 1,
        "max drawdown": -0.1148757168,
        "99% max drawdown": null
      }
    ],
    "drawdown_series": [
      {
        "date": "2026-01-03T00:00:00",
        "value": 0.0
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": -0.0011487572
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.0
      }
    ],
    "rolling_volatility": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 0.3683308151
      }
    ],
    "rolling_sharpe": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 8.7693715412
      }
    ],
    "rolling_sortino": [
      {
        "date": "2026-01-03T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-04T00:00:00",
        "value": null
      },
      {
        "date": "2026-01-05T00:00:00",
        "value": 306.788197259
      }
    ],
    "information_ratio": null,
    "r_squared": null,
    "greeks": null,
    "rolling_greeks": [],
    "compare": {},
    "montecarlo": {
      "seed": 42,
      "simulations": 250,
      "horizon_days": 3,
      "positive_return_probability": 0.724,
      "loss_probability": 0.236,
      "total_return_quantiles": {
        "mean": 0.0404241931,
        "median": 0.0384072428,
        "p05": -0.0022961947,
        "p25": 0.0,
        "p75": 0.0795297195,
        "p95": 0.0807712632,
        "best": 0.1235714183,
        "worst": -0.0034423141
      },
      "cagr_quantiles": {
        "mean": 740.6833917228,
        "median": 22.7075964617,
        "p05": -0.1756022335,
        "p25": 0.0,
        "p75": 618.0228056853,
        "p95": 680.7705637104,
        "best": 17800.5315834667,
        "worst": -0.2514768962
      },
      "max_drawdown_quantiles": {
        "mean": -0.0007764279,
        "median": -0.0011487572,
        "p05": -0.0022961947,
        "p25": -0.0011487572,
        "p75": 0.0,
        "p95": 0.0,
        "best": 0.0,
        "worst": -0.0022961947
      },
      "sharpe_quantiles": {
        "mean": 6.6620733497,
        "median": 10.7402428204,
        "p05": -22.4499443206,
        "p25": 0.0,
        "p75": 11.2249721603,
        "p95": 22.4499443206,
        "best": 22.4499443206,
        "worst": -22.4499443206
      }
    },
    "montecarlo_mean": [
      {
        "step": 1,
        "mean_cumulative_return": 0.0140795062,
        "p05_cumulative_return": -0.0011487572,
        "p95_cumulative_return": 0.0396014925
      },
      {
        "step": 2,
        "mean_cumulative_return": 0.0279690517,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      },
      {
        "step": 3,
        "mean_cumulative_return": 0.0404241931,
        "p05_cumulative_return": -0.0022961947,
        "p95_cumulative_return": 0.0807712632
      }
    ],
    "montecarlo_cagr": {
      "mean": 740.6833917228,
      "median": 22.7075964617,
      "p05": -0.1756022335,
      "p25": 0.0,
      "p75": 618.0228056853,
      "p95": 680.7705637104,
      "best": 17800.5315834667,
      "worst": -0.2514768962
    },
    "montecarlo_drawdown": {
      "mean": -0.0007764279,
      "median": -0.0011487572,
      "p05": -0.0022961947,
      "p25": -0.0011487572,
      "p75": 0.0,
      "p95": 0.0,
      "best": 0.0,
      "worst": -0.0022961947
    },
    "montecarlo_sharpe": {
      "mean": 6.6620733497,
      "median": 10.7402428204,
      "p05": -22.4499443206,
      "p25": 0.0,
      "p75": 11.2249721603,
      "p95": 22.4499443206,
      "best": 22.4499443206,
      "worst": -22.4499443206
    },
    "outliers": {
      "loss_threshold": -0.001125782,
      "win_threshold": 0.0388094626,
      "losses": [
        {
          "date": "2026-01-04T00:00:00",
          "value": -0.0011487572
        }
      ],
      "wins": [
        {
          "date": "2026-01-05T00:00:00",
          "value": 0.0396014925
        }
      ]
    },
    "metric_warnings": [
      {
        "metric": "kurtosis",
        "warning": "kurtosis returned a non-finite value"
      },
      {
        "metric": "kurtosis",
        "warning": "kurtosis was unavailable and defaulted to 0.0"
      },
      {
        "metric": "rolling_greeks",
        "warning": "rolling_greeks was unavailable and defaulted to an empty list"
      },
      {
        "metric": "compare",
        "warning": "compare was unavailable and defaulted to an empty object"
      }
    ],
    "excluded_ticker_count": 0,
    "excluded_tickers": [],
    "excluded_ticker_jsonb": [],
    "execution_timing": "next_open",
    "cost_model": {
      "commission_pct": 0.00015,
      "tax_pct": 0.0023,
      "slippage_pct": 0.001
    },
    "cost_model_jsonb": {
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
    "position_sizing_jsonb": {
      "method": "equal_weight",
      "max_positions": 1,
      "fixed_percent": null,
      "risk_per_position": null
    },
    "indicator_report": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "indicator_report_jsonb": {
      "mode": "none",
      "enabled": false,
      "requested_required_metrics": [
        "generated_signal"
      ],
      "planned_functions": [],
      "computed_function_count": 0,
      "computed_functions": [],
      "failed_functions": {},
      "computed_metric_names": [],
      "catalog_error": "RuntimeError: TA-Lib is required for indicator calculation. Install the Python package and native library."
    },
    "notes": [
      "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
      "TA-Lib metrics are calculated from OHLCV when enabled; precomputed metric rows override calculated values.",
      "Tickers missing required StrategySpec metrics are excluded and recorded here."
    ],
    "buy_signal_count": 1,
    "sell_signal_count": 0,
    "execution_audit": {
      "submitted_count": 1,
      "executed_buy_count": 1,
      "executed_sell_count": 0,
      "blocked_count": 0,
      "unfilled_end_count": 0,
      "completed_trade_count": 0,
      "has_real_fills": true,
      "recent_events": [
        {
          "date": "2026-01-03",
          "ticker": "005930",
          "side": "buy",
          "status": "submitted",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": null,
          "quantity": null,
          "detail": "Queued for the next available open."
        },
        {
          "date": "2026-01-04",
          "ticker": "005930",
          "side": "buy",
          "status": "executed",
          "signal_date": "2026-01-03",
          "reason": "entry condition matched",
          "price": 101.101,
          "quantity": 9889,
          "detail": "Filled at the next available open."
        }
      ]
    },
    "ai_backtest_context": {
      "available_ticker_count": 1,
      "requested_max_positions": 10,
      "applied_max_positions": 1,
      "exposure_normalized": true
    },
    "effective_trade_count": 1.0
  },
  "objective_score": 10.15987
}
```

#### 공용 DB 스크리닝 후보 (`screening_candidates`)

```json
[]
```

#### 데이터 가용성 (`data_availability`)

```json
{
  "source": "fixture",
  "price_ta": "fixture",
  "open_dart": "unavailable",
  "bok_macro": "pilot_only",
  "seibro_report": "fixture",
  "agentic_web_search": "not_connected",
  "proxy_used": []
}
```

#### Signal Judge (`signal`)

```json
{
  "action": "BUY",
  "confidence": 0.82,
  "bull_case": [
    "Candidate-code backtest selected the best objective-score candidate.",
    "Selected Sharpe ratio is 8.77.",
    "후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다."
  ],
  "bear_case": [
    "Hankyung consensus buy-opinion decrease is a required production adapter.",
    "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
    "English IB report search is optional in MVP and disabled by default.",
    "매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다."
  ],
  "judge_reason": "Bull case dominates after candidate-code backtest.",
  "l4_evidence": [
    {
      "publisher": "QuantAgent fixture",
      "published_at": "2026-05-19 09:00:00",
      "retrieved_at": "2026-05-19 09:01:00",
      "freshness_days": 0,
      "dedupe_group": "semantic-35:fixture:l4",
      "access_status": "fixture",
      "quality_note": "MVP fixture evidence until production adapters are connected."
    }
  ]
}
```

#### Risk Manager (`risk`)

```json
[]
```

#### Report 정반합 (`report_debate`)

```json
{
  "bull": {
    "role": "REPORT_BULL",
    "summary": "선택된 백테스트 후보와 Risk Manager 결과를 기준으로 실행 가능한 장점을 요약했습니다.",
    "evidence": [
      "Candidate-code backtest result is available.",
      "Risk Manager output is attached."
    ],
    "concerns": [],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BULL', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "bear": {
    "role": "REPORT_BEAR",
    "summary": "재무/뉴스/공시 조건이 포함된 경우 현재 DB 가용성을 함께 표시해야 합니다.",
    "evidence": [],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "paper_trade_or_review",
    "confidence": 0.68,
    "validation_results": {},
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_BEAR', '...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  },
  "judge": {
    "role": "REPORT_JUDGE",
    "summary": "성과 수치와 데이터 가용성을 함께 노출하는 균형 리포트로 확정합니다.",
    "evidence": [
      "Bull/Bear report passes were evaluated."
    ],
    "concerns": [
      "Report must not imply unavailable data was fully validated."
    ],
    "recommendation": "BUY",
    "confidence": 0.82,
    "validation_results": {
      "over_optimism_check": "pass",
      "proxy_disclosure": "pass"
    },
    "fallback_reasons": [
      "ValidationError: 1 validation error for RoleDebatePayload\nsummary\n  Field required [type=missing, input_value={'role': 'REPORT_JUDGE', ...tagent.role_debate.v1']}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing"
    ],
    "citations": []
  }
}
```
