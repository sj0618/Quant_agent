"""Per-stock BUY/SELL/HOLD, and the turnover term that decides what gets recommended."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_graph.graph import _ticker_actions as payload_ticker_actions
from ai_graph.nodes.backtest import (
    TURNOVER_PENALTY_WEIGHT,
    _ticker_actions,
    _turnover_cost_penalty,
)
from ai_graph.schemas import ScreeningMatch, StrategyCandidateCard


@dataclass(frozen=True)
class FakeSignal:
    date: str
    ticker: str
    action: str


class FakeResult:
    def __init__(self, signals, held):
        self.signals = signals
        self.summary = {"open_position_tickers": list(held)}


def rows_for(tickers, dates):
    return [
        {"date": d, "ticker": t, "name": f"NAME{t}", "close": 1000.0 + i}
        for d in dates
        for i, t in enumerate(tickers)
    ]


ROWS = rows_for(["000100", "000200", "000300", "000400"], ["2026-08-03", "2026-08-04"])


def action_for(actions, ticker):
    return next((a["action"] for a in actions if a["ticker"] == ticker), None)


def test_held_name_with_an_exit_signal_is_a_sell():
    result = FakeResult([FakeSignal("2026-08-04", "000100", "SELL")], held={"000100"})
    assert action_for(_ticker_actions(result, ROWS, "A1"), "000100") == "SELL"


def test_held_name_without_an_exit_signal_is_a_hold():
    result = FakeResult([], held={"000200"})
    assert action_for(_ticker_actions(result, ROWS, "A1"), "000200") == "HOLD"


def test_unheld_name_with_an_entry_signal_is_a_buy():
    result = FakeResult([FakeSignal("2026-08-04", "000300", "BUY")], held=set())
    assert action_for(_ticker_actions(result, ROWS, "A1"), "000300") == "BUY"


@pytest.mark.parametrize(
    ("signal", "held", "expected_action"),
    [("BUY", set(), "BUY"), ("SELL", {"025980"}, "SELL"), ("BUY", {"025980"}, "HOLD")],
)
def test_actions_preserve_a_canonical_company_name(signal, held, expected_action):
    rows = [{"date": "2026-08-04", "ticker": "025980", "name": "아난티", "close": 5_000.0}]
    result = FakeResult([FakeSignal("2026-08-04", "025980", signal)], held=held)

    action = _ticker_actions(result, rows, "A-ananti")[0]

    assert action["action"] == expected_action
    assert action["ticker"] == "025980"
    assert action["name"] == "아난티"


def test_actions_fall_back_to_the_ticker_only_for_a_blank_company_name():
    rows = [{"date": "2026-08-04", "ticker": "025980", "name": "   ", "close": 5_000.0}]
    result = FakeResult([FakeSignal("2026-08-04", "025980", "BUY")], held=set())

    assert _ticker_actions(result, rows, "A-ananti")[0]["name"] == "025980"


def test_a_buy_signal_on_a_name_already_held_never_returns_buy():
    """The engine skips buys it has no slot for, so signal alone must not mean 'enter'."""
    result = FakeResult([FakeSignal("2026-08-04", "000100", "BUY")], held={"000100"})
    assert action_for(_ticker_actions(result, ROWS, "A1"), "000100") == "HOLD"


def test_sell_signal_on_a_name_not_held_is_not_an_instruction():
    result = FakeResult([FakeSignal("2026-08-04", "000400", "SELL")], held=set())
    assert action_for(_ticker_actions(result, ROWS, "A1"), "000400") is None


def test_only_the_final_bar_decides():
    """A buy two days ago is history, not today's recommendation."""
    result = FakeResult([FakeSignal("2026-08-03", "000300", "BUY")], held=set())
    assert _ticker_actions(result, ROWS, "A1") == []


def test_actions_carry_the_candidate_that_produced_them():
    result = FakeResult([FakeSignal("2026-08-04", "000300", "BUY")], held=set())
    actions = _ticker_actions(result, ROWS, "A7")
    assert {a["source_candidate_id"] for a in actions} == {"A7"}
    assert {a["as_of_date"] for a in actions} == {"2026-08-04"}


def test_screened_names_the_strategy_is_not_acting_on_come_back_as_watch():
    """A screened name vanishing from the list would read as 'sell'. It must say WATCH."""
    state = {
        "backtest": {
            "ticker_actions": [
                {
                    "ticker": "000100",
                    "name": "NAME1",
                    "action": "BUY",
                    "reason": "진입 조건 충족 - 신규 매수",
                    "as_of_date": "2026-08-04",
                    "close": 1000.0,
                    "source_candidate_id": "A1",
                }
            ]
        }
    }
    card = StrategyCandidateCard(
        strategy_id="s1",
        title="t",
        summary="s",
        key_conditions=["c"],
        confidence=0.5,
        matches=[
            ScreeningMatch(
                ticker="000100",
                name="NAME1",
                market="KOSPI",
                as_of_date="2026-08-04",
                close=1000.0,
            ),
            ScreeningMatch(
                ticker="000900",
                name="NAME9",
                market="KOSPI",
                as_of_date="2026-08-04",
                close=2000.0,
            ),
        ],
    )
    actions = payload_ticker_actions(state, [card])
    by_ticker = {a.ticker: a.action for a in actions}
    assert by_ticker == {"000100": "BUY", "000900": "WATCH"}


def _watch_card(tickers):
    return StrategyCandidateCard(
        strategy_id="s1",
        title="t",
        summary="s",
        key_conditions=["c"],
        confidence=0.5,
        matches=[
            ScreeningMatch(
                ticker=ticker,
                name=f"NAME{ticker}",
                market="KOSPI",
                as_of_date="2026-08-04",
                close=1000.0,
            )
            for ticker in tickers
        ],
    )


def test_a_screened_name_outside_the_traded_universe_says_it_was_never_judged():
    """The backtest never priced it, so 'did not meet the entry condition' is invented."""
    state = {
        "backtest": {
            "ticker_actions": [],
            "backtest_payload": {"tickers": ["000100", "000200"]},
        }
    }
    action = payload_ticker_actions(state, [_watch_card(["000900"])])[0]
    assert action.action == "WATCH"
    assert "유니버스에 없는 종목" in action.reason
    assert "진입 조건" not in action.reason


def test_a_full_book_on_the_last_session_is_named_as_the_limit():
    state = {
        "backtest": {
            "ticker_actions": [],
            "backtest_payload": {"tickers": ["000100", "000200", "000900"]},
            "engine_summary": {
                "open_position_tickers": ["000100", "000200"],
                "ai_backtest_context": {"applied_max_positions": 2},
            },
        }
    }
    action = payload_ticker_actions(state, [_watch_card(["000900"])])[0]
    assert action.action == "WATCH"
    assert "슬롯 2/2" in action.reason


def test_a_book_with_room_left_claims_no_slot_limit():
    state = {
        "backtest": {
            "ticker_actions": [],
            "backtest_payload": {"tickers": ["000100", "000900"]},
            "engine_summary": {
                "open_position_tickers": ["000100"],
                "ai_backtest_context": {"applied_max_positions": 5},
            },
        }
    }
    action = payload_ticker_actions(state, [_watch_card(["000900"])])[0]
    assert "슬롯" not in action.reason
    assert "지시가 없었습니다" in action.reason


def test_a_run_that_recorded_no_positions_states_no_cause_it_cannot_see():
    """The rolling-policy path builds its own summary and carries neither half."""
    state = {"backtest": {"ticker_actions": [], "engine_summary": {}}}
    action = payload_ticker_actions(state, [_watch_card(["000900"])])[0]
    assert action.reason == (
        "백테스트 마지막 거래일에 이 종목에 대한 신규 진입·청산 지시가 없었습니다."
    )

def test_actions_are_ordered_sell_buy_hold_watch():
    state = {
        "backtest": {
            "ticker_actions": [
                {
                    "ticker": "000300",
                    "name": "N3",
                    "action": "HOLD",
                    "reason": "보유 유지",
                    "as_of_date": "2026-08-04",
                },
                {
                    "ticker": "000100",
                    "name": "N1",
                    "action": "SELL",
                    "reason": "청산",
                    "as_of_date": "2026-08-04",
                },
                {
                    "ticker": "000200",
                    "name": "N2",
                    "action": "BUY",
                    "reason": "진입",
                    "as_of_date": "2026-08-04",
                },
            ]
        }
    }
    assert [a.action for a in payload_ticker_actions(state, [])] == ["SELL", "BUY", "HOLD"]


# --------------------------------------------------------------- turnover pricing


def penalty(trades_per_year, positions=10):
    return _turnover_cost_penalty(
        trades_per_year, {"position_sizing": {"max_positions": positions}}
    )


def test_turnover_penalty_keeps_rising_past_the_old_saturation_point():
    """The old penalty was min(1, turnover/24) - flat above 24 trades a year."""
    assert penalty(86) > penalty(47) > penalty(24) > penalty(12)


def test_turnover_penalty_matches_the_modelled_round_trip_cost():
    # 2x commission + tax + 2x slippage = 0.46% per round trip, over 10 slots.
    assert penalty(47) == pytest.approx(47 * 0.0046 / 10, rel=1e-6)


def test_turnover_penalty_uses_the_summary_cost_model_when_present():
    free = _turnover_cost_penalty(
        47,
        {
            "position_sizing": {"max_positions": 10},
            "cost_model": {"commission_pct": 0.0, "tax_pct": 0.0, "slippage_pct": 0.0},
        },
    )
    assert free == 0.0


def test_turnover_penalty_falls_back_when_the_summary_is_unusable():
    assert _turnover_cost_penalty(47, {}) == pytest.approx(47 * 0.0046 / 10, rel=1e-6)
    assert _turnover_cost_penalty(47, {"cost_model": "nonsense"}) == pytest.approx(
        47 * 0.0046 / 10, rel=1e-6
    )


def test_penalty_keeps_its_previous_magnitude_at_the_turnover_actually_observed():
    """Calibration check: 47 trades a year should still cost about the old 0.08."""
    assert TURNOVER_PENALTY_WEIGHT * penalty(47) == pytest.approx(0.08, abs=0.005)


# ------------------------------------------------------- turnover as a hard ceiling


def _candidate(cid):
    from ai_graph.schemas import CodeCandidate

    return CodeCandidate(
        candidate_id=cid,
        variant="A",
        code="def build_signals(prices):\n    return []\n",
        validation_ok=True,
    )


def _rows(days):
    return [{"date": f"2026-01-{d + 1:02d}", "ticker": "000001"} for d in range(days)]


def test_a_candidate_over_the_turnover_ceiling_is_not_selectable():
    from ai_graph.nodes.backtest import MAX_SELECTABLE_ANNUAL_TURNOVER, _within_turnover_cap

    rows = _rows(20)  # 14 selection days, so 24 trades a year is ~1.3 buys
    calm, churner = _candidate("A1"), _candidate("A2")
    summaries = {
        "A1": {"selection_buy_count": 1.0},
        "A2": {"selection_buy_count": 10.0},
    }
    eligible = _within_turnover_cap([calm, churner], summaries, rows)
    assert [c.candidate_id for c in eligible] == ["A1"]
    assert MAX_SELECTABLE_ANNUAL_TURNOVER == 24.0


def test_the_ceiling_never_leaves_the_run_without_a_recommendation():
    """All candidates over the ceiling must still yield a pick, not an empty list."""
    from ai_graph.nodes.backtest import _within_turnover_cap

    rows = _rows(20)
    pool = [_candidate("A1"), _candidate("A2")]
    summaries = {"A1": {"selection_buy_count": 40.0}, "A2": {"selection_buy_count": 50.0}}
    assert [c.candidate_id for c in _within_turnover_cap(pool, summaries, rows)] == ["A1", "A2"]


def test_a_candidate_with_no_summary_is_treated_as_not_trading():
    from ai_graph.nodes.backtest import _within_turnover_cap

    pool = [_candidate("A1")]
    assert _within_turnover_cap(pool, {}, _rows(20)) == pool
