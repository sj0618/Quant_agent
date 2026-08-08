from datetime import datetime, timedelta

from ai_graph import graph
from ai_graph import quant_performance
from ai_graph.quant_explanations import metric_explanation
from ai_graph.quant_performance import build_public_backtest_performance
from ai_graph.schemas import (
    BacktestMetrics,
    CandidateParameters,
    CodeCandidate,
    Condition,
    StrategySpec,
)


def _make_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="rsi",
        name="RSI",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator="lte", right=30)],
        exit_conditions=[Condition(left="rsi", operator="gte", right=70)],
        indicators=["RSI"],
        confidence=0.8,
    )


def _build_payload(
    metrics: BacktestMetrics, engine_summary: dict | None = None, equity_curve: list | None = None
) -> dict:
    candidate = CodeCandidate(
        candidate_id="A2",
        variant="A",
        code="pass",
        validation_ok=True,
        metrics=metrics,
    )
    return {
        "selected_candidate": candidate.model_dump(),
        "candidates": [candidate.model_dump()],
        "strategy_a": _make_strategy().model_dump(),
        "equity_curve": equity_curve or [],
        "engine_summary": engine_summary
        or {
            "effective_trade_count": 10,
            "montecarlo": [],
            "rolling_sharpe": [0.1, 0.2],
        },
    }


def _rows(start: datetime, trading_days: int, ticker_count: int = 5) -> list[dict]:
    tickers = [f"{idx + 1:06d}" for idx in range(ticker_count)]
    rows: list[dict] = []
    for day in range(trading_days):
        date = (start + timedelta(days=day)).date().isoformat()
        for idx, ticker in enumerate(tickers):
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "close": 100.0 + (day + idx * 0.5),
                    "volume": 1_000_000.0,
                }
            )
    return rows


def test_public_metrics_use_engine_summary_scalars_not_sampled_rows() -> None:
    payload = _build_payload(
        BacktestMetrics(
            sharpe_ratio=0.1,
            max_drawdown=-0.9,
            win_rate=0.05,
            total_return=0.05,
            in_sample_sharpe=0.2,
            out_sample_sharpe=0.3,
            degradation=0.01,
        ),
        engine_summary={
            "effective_trade_count": 12,
            "cagr": 0.40,
            "annualized_volatility": 0.11,
            "sortino_ratio": 3.3,
            "calmar_ratio": 2.4,
            "profit_factor": 1.8,
        },
    )
    performance = build_public_backtest_performance(
        payload,
        price_rows=_rows(start=datetime(2024, 1, 1), trading_days=252),
        pipeline_data_source={"source": "postgres"},
    )

    assert performance is not None
    values = {item.key: item.value for item in performance.metric_details}
    assert values["total_return"] == 0.05
    assert values["sharpe_ratio"] == 0.1
    assert values["win_rate"] == 0.05
    assert values["in_sample_sharpe"] == 0.2
    assert values["out_sample_sharpe"] == 0.3
    assert values["degradation"] == 0.01
    assert values["cagr"] == 0.4
    assert values["annualized_volatility"] == 0.11
    assert values["sortino_ratio"] == 3.3
    assert values["calmar_ratio"] == 2.4
    assert values["profit_factor"] == 1.8


def test_public_metrics_missing_engine_scalars_become_none() -> None:
    performance = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=float("nan"),
                max_drawdown=-0.1,
                win_rate=0.5,
                total_return=0.08,
                in_sample_sharpe=0.11,
                out_sample_sharpe=0.09,
                degradation=0.02,
            ),
            engine_summary={"effective_trade_count": 8},
        ),
        price_rows=_rows(datetime(2024, 1, 1), trading_days=252),
        pipeline_data_source={"source": "postgres"},
    )
    assert performance is not None
    values = {item.key: item.value for item in performance.metric_details}
    assert values["sharpe_ratio"] is None
    assert values["cagr"] is None
    assert values["annualized_volatility"] is None
    assert values["sortino_ratio"] is None
    assert values["calmar_ratio"] is None
    assert values["profit_factor"] is None
    assert values["benchmark_return"] is not None


def test_public_performance_source_refs_are_propagated_from_explanations() -> None:
    performance = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 8},
        ),
        price_rows=_rows(datetime(2024, 1, 1), trading_days=252),
        pipeline_data_source={"source": "postgres"},
    )
    assert performance is not None
    details = {item.key: item for item in performance.metric_details}
    assert details["sharpe_ratio"].source_refs == metric_explanation("sharpe_ratio").get(
        "source_refs"
    )
    assert details["benchmark_return"].source_refs == metric_explanation("benchmark_return").get(
        "source_refs"
    )
    assert details["total_return"].unit == "percent"


def test_public_performance_includes_beginner_strategy_explanation() -> None:
    payload = _build_payload(
        BacktestMetrics(
            sharpe_ratio=0.8,
            max_drawdown=-0.1,
            win_rate=0.55,
            total_return=0.12,
            in_sample_sharpe=0.9,
            out_sample_sharpe=0.7,
            degradation=0.1,
        ),
        engine_summary={"effective_trade_count": 8},
    )
    payload["strategy_a"]["selection_mode"] = "automatic"
    payload["strategy_a"]["strategy_id"] = "automatic_academic_momentum_a"
    payload["strategy_a"]["indicators"] = [
        "momentum_12_1",
        "SMA50",
        "SMA200",
        "realized_volatility_21d",
    ]

    performance = build_public_backtest_performance(
        payload,
        price_rows=_rows(datetime(2024, 1, 1), trading_days=252),
        pipeline_data_source={"source": "postgres"},
    )

    assert performance is not None
    assert performance.strategy_explanation is not None
    assert performance.strategy_explanation.selection_mode == "automatic"
    assert "자동" in performance.strategy_explanation.why_selected
    assert "미래 수익을 보장하지 않습니다" in performance.strategy_explanation.caution
    assert any(
        item.key == "momentum_12_1" and item.source_refs
        for item in performance.strategy_explanation.indicators
    )


def test_public_explanation_matches_the_selected_automatic_profile() -> None:
    payload = _build_payload(
        BacktestMetrics(
            sharpe_ratio=0.9,
            max_drawdown=-0.08,
            win_rate=0.52,
            total_return=0.15,
            in_sample_sharpe=0.7,
            out_sample_sharpe=1.1,
            degradation=-0.4,
        ),
        engine_summary={"effective_trade_count": 12},
    )
    payload["strategy_a"]["selection_mode"] = "automatic"
    payload["strategy_a"]["strategy_id"] = "automatic_robust_tournament_a"
    parameters = CandidateParameters(
        profile="low_vol_momentum",
        lookback=126,
        threshold=0.03,
        stop_loss_pct=0.08,
        take_profit_pct=0.45,
        max_positions=10,
    ).model_dump()
    payload["selected_candidate"]["parameters"] = parameters
    payload["candidates"][0]["parameters"] = parameters

    performance = build_public_backtest_performance(
        payload,
        price_rows=_rows(datetime(2024, 1, 1), trading_days=252),
        pipeline_data_source={"source": "postgres"},
    )

    assert performance is not None
    explanation = performance.strategy_explanation
    assert explanation is not None
    assert explanation.title == "저변동 모멘텀 전략"
    assert "126거래일" in explanation.summary
    assert "마지막 30%" in explanation.why_selected
    assert {item.key for item in explanation.indicators} == {
        "medium_momentum_126d",
        "price_range_volatility",
        "trend_risk_exit",
    }


def test_public_performance_reliability_boundary_cases() -> None:
    fixture = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 7},
        ),
        price_rows=_rows(datetime(2024, 1, 1), 252, ticker_count=5),
        pipeline_data_source={"source": "fixture"},
    )
    assert fixture is not None
    assert fixture.reliability is not None
    assert fixture.reliability.status == "insufficient"

    no_rows = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 10},
        ),
        price_rows=[],
        pipeline_data_source={"source": "postgres"},
    )
    assert no_rows is not None
    assert no_rows.reliability is not None
    assert no_rows.reliability.status == "insufficient"
    assert all(item.is_available is False for item in no_rows.metric_details)

    short = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 10},
        ),
        price_rows=_rows(datetime(2024, 1, 1), 29),
        pipeline_data_source={"source": "postgres"},
    )
    assert short is not None
    assert short.reliability.status == "insufficient"

    limited_30 = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 3},
        ),
        price_rows=_rows(datetime(2024, 1, 1), 30),
        pipeline_data_source={"source": "postgres"},
    )
    assert limited_30 is not None
    assert limited_30.reliability.status == "limited"

    limited_251 = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 3},
        ),
        price_rows=_rows(datetime(2024, 1, 1), 251),
        pipeline_data_source={"source": "postgres"},
    )
    assert limited_251 is not None
    assert limited_251.reliability.status == "limited"

    limited_trades_4 = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 4},
        ),
        price_rows=_rows(datetime(2024, 1, 1), 252, ticker_count=5),
        pipeline_data_source={"source": "postgres"},
    )
    assert limited_trades_4 is not None
    assert limited_trades_4.reliability.status == "limited"

    insufficient_tickers = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 10},
        ),
        price_rows=_rows(datetime(2024, 1, 1), 252, ticker_count=4),
        pipeline_data_source={"source": "postgres"},
    )
    assert insufficient_tickers is not None
    assert insufficient_tickers.reliability.status == "insufficient"

    sufficient = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 5},
        ),
        price_rows=_rows(datetime(2024, 1, 1), 252, ticker_count=5),
        pipeline_data_source={"source": "postgres"},
    )
    assert sufficient is not None
    assert sufficient.reliability.status == "sufficient"

    unknown_252 = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.3,
                max_drawdown=-0.15,
                win_rate=0.6,
                total_return=0.12,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.2,
                degradation=0.05,
            ),
            engine_summary={"effective_trade_count": 5},
        ),
        price_rows=_rows(datetime(2024, 1, 1), 252, ticker_count=5),
        pipeline_data_source={"source": "mystery"},
    )
    assert unknown_252 is not None
    assert unknown_252.reliability.status == "limited"


def test_graph_public_performance_alias_points_to_quant_module() -> None:
    assert (
        graph.build_public_backtest_performance
        is quant_performance.build_public_backtest_performance
    )
