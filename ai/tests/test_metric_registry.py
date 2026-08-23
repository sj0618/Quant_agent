from __future__ import annotations

from ai_graph.nodes.backtest import _profit_factor, _undefined_metric_availability
from ai_graph.quant_explanations import (
    PUBLIC_METRIC_KEYS,
    metric_explanation,
    public_metric_registry,
)


def test_profit_factor_uses_the_unclipped_engine_period_return_ratio() -> None:
    # A 99% trade win rate used to synthesize and clip a value of 3.0.  The measured
    # engine ratio is intentionally unrelated and must reach the report unchanged.
    summary = {"trade_win_rate": 0.99, "profit_factor": 7.25}

    assert _profit_factor(summary) == 7.25


def test_profit_factor_is_unavailable_when_the_engine_cannot_measure_a_finite_ratio() -> None:
    assert _profit_factor({"trade_win_rate": 0.99}) is None
    assert _profit_factor({"profit_factor": float("inf")}) is None
    assert (
        _profit_factor(
            {
                "profit_factor": 0.0,
                "metric_warnings": [
                    {
                        "metric": "profit_factor",
                        "warning": "profit_factor was unavailable and defaulted to 0.0",
                    }
                ],
            }
        )
        is None
    )


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
    assert profit_factor["formula"] == "PF = Σ max(R_t, 0) / |Σ min(R_t, 0)|"
    assert profit_factor["denominator"] == "|Σ min(R_t, 0)| (음수 기간수익률의 절대 합)"
    assert "0~3" in profit_factor["clip_policy"]
    assert "분모가 0" in profit_factor["null_policy"]
    assert "승률" in profit_factor["plain_explanation"]
