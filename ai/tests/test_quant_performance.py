from datetime import datetime, timedelta

from ai_graph import graph
from ai_graph import quant_performance
from ai_graph.quant_explanations import metric_explanation
from ai_graph.quant_performance import build_public_backtest_performance
from ai_graph.schemas import BacktestMetrics, CodeCandidate, Condition, StrategySpec


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


def _rows(trading_days: int, ticker_count: int = 5, *, start: datetime | None = None) -> list[dict]:
    origin = start or datetime(2026, 1, 1)
    tickers = [f"{index + 1:06d}" for index in range(ticker_count)]
    return [
        {
            "date": (origin + timedelta(days=day)).date().isoformat(),
            "ticker": ticker,
            "open": 100.0 + day,
            "high": 100.1 + day,
            "low": 99.9 + day,
            "close": 100.0 + day,
            "volume": 1_000_000.0,
        }
        for day in range(trading_days)
        for ticker in tickers
    ]


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
            "total_return": 0.15,
            "cagr": 0.40,
            "annualized_volatility": 0.11,
            "sharpe_ratio": 2.2,
            "sortino_ratio": 3.3,
            "max_drawdown": -0.04,
            "calmar_ratio": 2.4,
            "win_rate": 0.66,
            "in_sample_sharpe": 0.21,
            "out_sample_sharpe": 0.22,
            "degradation": 0.06,
        },
    )
    performance = build_public_backtest_performance(
        payload,
        price_rows=_rows(trading_days=252, ticker_count=5),
        pipeline_data_source={"source": "postgres"},
    )

    assert performance is not None
    details = {item.key: item.value for item in performance.metric_details}
    assert details["total_return"] == 0.15
    assert details["cagr"] == 0.4
    assert details["annualized_volatility"] == 0.11
    assert details["sharpe_ratio"] == 2.2
    assert details["sortino_ratio"] == 3.3
    assert details["max_drawdown"] == -0.04
    assert details["calmar_ratio"] == 2.4
    assert details["win_rate"] == 0.66
    assert details["in_sample_sharpe"] == 0.21
    assert details["out_sample_sharpe"] == 0.22
    assert details["degradation"] == 0.06
    assert details["benchmark_return"] == performance.benchmark.total_return


def test_public_metrics_missing_engine_scalars_become_null() -> None:
    performance = build_public_backtest_performance(
        _build_payload(
            BacktestMetrics(
                sharpe_ratio=0.45,
                max_drawdown=-0.1,
                win_rate=0.5,
                total_return=0.08,
                in_sample_sharpe=0.11,
                out_sample_sharpe=0.09,
                degradation=0.02,
            ),
            engine_summary={"effective_trade_count": 8},
        ),
        price_rows=_rows(trading_days=252, ticker_count=5),
        pipeline_data_source={"source": "postgres"},
    )
    assert performance is not None
    detail = {item.key: item.value for item in performance.metric_details}
    assert detail["cagr"] is None
    assert detail["annualized_volatility"] is None
    assert detail["sortino_ratio"] is None
    assert detail["calmar_ratio"] is None
    assert detail["benchmark_return"] == performance.benchmark.total_return


def test_public_performance_reliability_and_benchmark_for_source_variants() -> None:
    insufficient_fixture = build_public_backtest_performance(
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
            engine_summary={"effective_trade_count": 2},
        ),
        price_rows=_rows(trading_days=5, ticker_count=1),
        pipeline_data_source={"source": "fixture"},
    )
    assert insufficient_fixture is not None
    assert insufficient_fixture.reliability.status == "insufficient"
    assert insufficient_fixture.benchmark.is_available is False
    assert all(detail.is_available is False for detail in insufficient_fixture.metric_details)

    limited_unknown = build_public_backtest_performance(
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
        price_rows=_rows(trading_days=120, ticker_count=5),
        pipeline_data_source={"source": "mystery"},
    )
    assert limited_unknown is not None
    assert limited_unknown.reliability.status == "limited"

    sufficient_postgres = build_public_backtest_performance(
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
        price_rows=_rows(trading_days=252, ticker_count=5),
        pipeline_data_source={"source": "postgres"},
    )
    assert sufficient_postgres is not None
    assert sufficient_postgres.reliability.status == "sufficient"


def test_public_performance_short_or_too_few_tickers_mark_insufficient() -> None:
    too_short = build_public_backtest_performance(
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
        price_rows=_rows(trading_days=29, ticker_count=5),
        pipeline_data_source={"source": "postgres"},
    )
    four_tickers = build_public_backtest_performance(
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
        price_rows=_rows(trading_days=252, ticker_count=4),
        pipeline_data_source={"source": "postgres"},
    )

    assert too_short is not None and too_short.reliability.status == "insufficient"
    assert too_short.reliability.trading_days == 29
    assert four_tickers is not None and four_tickers.reliability.status == "insufficient"
    assert four_tickers.reliability.ticker_count == 4


def test_public_performance_source_refs_are_preserved() -> None:
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
            engine_summary={"effective_trade_count": 10},
        ),
        price_rows=_rows(trading_days=252, ticker_count=5),
        pipeline_data_source={"source": "postgres"},
    )
    assert performance is not None
    details = {item.key: item for item in performance.metric_details}
    assert details["sharpe_ratio"].source_refs == metric_explanation("sharpe_ratio").get("source_refs", [])
    assert details["benchmark_return"].source_refs == metric_explanation("benchmark_return").get("source_refs", [])


def test_graph_public_performance_alias_points_to_quant_module() -> None:
    assert (
        graph.build_public_backtest_performance
        is quant_performance.build_public_backtest_performance
    )
