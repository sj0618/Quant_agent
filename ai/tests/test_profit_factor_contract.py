"""The published profit factor must be measured from trades, not derived from the hit rate."""

from __future__ import annotations

import pytest

from ai_graph.nodes.backtest import _profit_factor


def test_the_engine_measurement_is_what_gets_published() -> None:
    assert _profit_factor({"trade_profit_factor": 1.83, "trade_win_rate": 0.75}) == 1.83


def test_two_runs_with_the_same_win_rate_report_different_profit_factors() -> None:
    """The defect this pins: the old formula was `win_rate / (1 - win_rate)` capped at
    3.0, so every 75%-win-rate run published exactly 3.0 no matter how big the losses
    were. Same hit rate, different losses, must not be the same number."""

    small_losses = _profit_factor({"trade_win_rate": 0.75, "trade_profit_factor": 6.0})
    large_losses = _profit_factor({"trade_win_rate": 0.75, "trade_profit_factor": 0.4})

    assert small_losses != large_losses
    assert large_losses is not None and large_losses < 1.0


def test_a_high_win_rate_does_not_by_itself_produce_a_passing_number() -> None:
    """A strategy can win 90% of its trades and still lose money overall."""

    assert _profit_factor({"trade_win_rate": 0.9, "trade_profit_factor": 0.5}) == 0.5


@pytest.mark.parametrize(
    "summary",
    (
        {},
        {"trade_profit_factor": None},
        {"trade_win_rate": 0.75},
        {"trade_profit_factor": float("inf")},
        {"trade_profit_factor": float("nan")},
        {"trade_profit_factor": "1.5"},
        {"trade_profit_factor": True},
    ),
)
def test_an_undefined_ratio_is_published_as_unavailable_not_as_a_number(summary: dict) -> None:
    """No closed trades, or no losing trade to divide by, is not a measured result.

    The public metric contract carries `float | None`, so the honest answer is None.
    Returning a capped stand-in is what made the old value unreadable.
    """

    assert _profit_factor(summary) is None
