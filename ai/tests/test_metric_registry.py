from __future__ import annotations

from ai_graph import graph
from ai_graph.nodes.backtest import _profit_factor, _undefined_metric_availability
from ai_graph.quant_explanations import (
    PUBLIC_METRIC_KEYS,
    metric_explanation,
    metric_registry_provenance,
    public_metric_registry,
)


def test_profit_factor_uses_the_unclipped_engine_trade_pnl_ratio() -> None:
    # A 99% trade win rate used to synthesize and clip a value of 3.0. The actual
    # realized-PnL ratio is intentionally unrelated and must reach the report unchanged.
    summary = {"trade_win_rate": 0.99, "trade_profit_factor": 7.25}

    assert _profit_factor(summary) == 7.25


def test_profit_factor_is_unavailable_when_the_engine_cannot_measure_a_finite_ratio() -> None:
    assert _profit_factor({"trade_win_rate": 0.99}) is None
    assert _profit_factor({"trade_profit_factor": float("inf")}) is None
    assert _profit_factor({"trade_profit_factor": "7.25"}) is None


def test_metric_warning_variants_make_public_metrics_unavailable() -> None:
    assert _undefined_metric_availability(
        [{"metric": "profit_factor", "warning": "returned a non-finite value"}]
    ) == {
        "profit_factor": {
            "value": None,
            "unavailable_reason": "returned a non-finite value",
        }
    }


def test_public_metric_registry_is_complete_and_profit_factor_contract_is_explicit() -> None:
    registry = public_metric_registry()

    assert tuple(entry["key"] for entry in registry) == PUBLIC_METRIC_KEYS
    assert len({entry["key"] for entry in registry}) == len(PUBLIC_METRIC_KEYS)
    assert all(len(entry["implementation_hash"]) == 64 for entry in registry)

    profit_factor = metric_explanation("profit_factor")
    assert profit_factor["unit"] == "ratio"
    assert profit_factor["formula"] == "PF = Σ max(net_pnl, 0) / |Σ min(net_pnl, 0)|"
    assert profit_factor["denominator"] == "|Σ min(net_pnl, 0)| (손실 청산 거래의 절대 손익 합)"
    assert "승률 기반 프록시" in profit_factor["clip_policy"]
    assert "분모가 0" in profit_factor["null_policy"]
    assert "실현손익" in profit_factor["plain_explanation"]


def test_graph_metric_detail_carries_the_same_registry_provenance() -> None:
    detail = graph._metric_detail("sharpe_ratio", 1.25)
    registry = metric_registry_provenance("sharpe_ratio")

    assert detail.registry_version == registry["registry_version"]
    assert detail.provenance.implementation_path == registry["implementation_path"]
    assert detail.provenance.implementation_hash == registry["implementation_hash"]
