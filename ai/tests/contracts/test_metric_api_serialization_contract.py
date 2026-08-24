from datetime import datetime, timedelta

from ai_graph.quant_explanations import metric_explanation, metric_registry_provenance
from ai_graph.quant_performance import build_public_backtest_performance
from ai_graph.schemas import (
    BacktestMetrics,
    CodeCandidate,
    Condition,
    StrategySpec,
)

METRIC_DETAIL_FIELDS = {
    "key",
    "label",
    "value",
    "unit",
    "is_available",
    "unavailable_reason",
    "plain_explanation",
    "why_used",
    "caution",
    "source_refs",
    "registry_version",
    "provenance",
}


def _payload() -> dict:
    metrics = BacktestMetrics(
        sharpe_ratio=0.4,
        max_drawdown=-0.12,
        win_rate=0.56,
        total_return=0.18,
        in_sample_sharpe=0.5,
        out_sample_sharpe=0.2,
        degradation=0.1,
    )
    candidate = CodeCandidate(
        candidate_id="metric-contract",
        variant="A",
        code="pass",
        validation_ok=True,
        metrics=metrics,
    )
    strategy = StrategySpec(
        strategy_id="rsi",
        name="RSI",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator="lte", right=30)],
        exit_conditions=[Condition(left="rsi", operator="gte", right=70)],
        indicators=["RSI"],
        confidence=0.8,
    )
    return {
        "selected_candidate": candidate.model_dump(),
        "candidates": [candidate.model_dump()],
        "strategy_a": strategy.model_dump(),
        "equity_curve": [],
        "engine_summary": {
            "effective_trade_count": 12,
            "cagr": 0.2,
            "annualized_volatility": 0.1,
            "sortino_ratio": 0.45,
            "calmar_ratio": 1.1,
            "profit_factor": 1.5,
        },
    }


def _rows() -> list[dict[str, object]]:
    start = datetime(2024, 1, 1)
    return [
        {
            "date": (start + timedelta(days=day)).date().isoformat(),
            "ticker": f"{ticker:06d}",
            "close": 100.0 + day + ticker,
            "volume": 1_000_000.0,
        }
        for day in range(252)
        for ticker in range(1, 6)
    ]


def test_metric_api_serialization_matches_the_registry_field_by_field() -> None:
    performance = build_public_backtest_performance(
        _payload(),
        price_rows=_rows(),
        pipeline_data_source={"source": "postgres"},
    )

    assert performance is not None
    serialized = performance.model_dump(mode="json")
    details = {detail["key"]: detail for detail in serialized["metric_details"]}

    assert details
    for key, detail in details.items():
        assert set(detail) == METRIC_DETAIL_FIELDS
        explanation = metric_explanation(key)
        assert detail["label"] == explanation["label"]
        assert detail["unit"] == explanation["unit"]
        assert detail["plain_explanation"] == explanation["plain_explanation"]
        assert detail["why_used"] == explanation["why_used"]
        assert detail["caution"] == explanation["caution"]
        assert detail["source_refs"] == explanation["source_refs"]
        registry = metric_registry_provenance(key)
        assert detail["registry_version"] == registry["registry_version"]
        assert detail["provenance"] == {
            "implementation_path": registry["implementation_path"],
            "implementation_hash": registry["implementation_hash"],
        }
        if detail["is_available"]:
            assert detail["value"] is not None
            assert detail["unavailable_reason"] is None
        else:
            assert detail["value"] is None
            assert detail["unavailable_reason"]
