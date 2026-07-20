from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.nodes.position_sizing import (
    DEFAULT_MAX_POSITIONS,
    applied_max_positions,
    available_ticker_count,
    max_position_pct_from_risk_constraints,
    requested_max_positions,
)
from ai_graph.schemas import Condition, ConditionOperator, StrategySpec


def make_strategy(risk_constraints: dict | None = None) -> StrategySpec:
    return StrategySpec(
        strategy_id="rsi_rebound_test",
        name="RSI Rebound Test",
        market="KRX",
        timeframe="daily",
        entry_conditions=[
            Condition(left="rsi", operator=ConditionOperator.LTE, right=30, description="RSI <= 30")
        ],
        exit_conditions=[
            Condition(left="rsi", operator=ConditionOperator.GTE, right=70, description="RSI >= 70")
        ],
        risk_constraints=risk_constraints or {},
        confidence=0.8,
    )


def test_requested_max_positions_defaults_when_no_max_position_pct() -> None:
    assert requested_max_positions(None) == DEFAULT_MAX_POSITIONS


def test_requested_max_positions_derives_from_max_position_pct() -> None:
    # 10% per position implies at most 10 concurrent positions.
    assert requested_max_positions(0.1) == 10
    # ~7% per position implies at most 15 concurrent positions (ceil(1/0.07)).
    assert requested_max_positions(0.07) == 15


def test_applied_max_positions_is_capped_by_available_tickers() -> None:
    assert applied_max_positions(0.05, available_ticker_count=8) == 8
    assert applied_max_positions(0.05, available_ticker_count=None) == 20
    assert applied_max_positions(0.05, available_ticker_count=0) == 20


def test_available_ticker_count_deduplicates_tickers() -> None:
    rows = [
        {"date": "2026-01-02", "ticker": "005930"},
        {"date": "2026-01-02", "ticker": "000660"},
        {"date": "2026-01-03", "ticker": "005930"},
    ]
    assert available_ticker_count(rows) == 2


def test_max_position_pct_from_risk_constraints_is_non_raising() -> None:
    assert max_position_pct_from_risk_constraints({}) is None
    assert max_position_pct_from_risk_constraints({"max_position_pct": "not-a-number"}) is None
    assert max_position_pct_from_risk_constraints({"max_position_pct": 1.5}) is None
    assert max_position_pct_from_risk_constraints({"max_position_pct": 0.2}) == 0.2


def test_render_adaptive_signal_code_embeds_computed_max_positions_not_hardcoded_five() -> None:
    strategy = make_strategy()
    result = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="trace-max-positions", max_positions=17)
    )

    rendered_codes = [candidate.code for candidate in result.candidates if "max_positions = " in candidate.code]
    assert rendered_codes, "expected at least one generated candidate to declare max_positions"
    for code in rendered_codes:
        assert "max_positions = 17" in code
        assert "max_positions = 5\n" not in code


def test_loop3_request_defaults_to_shared_default_max_positions() -> None:
    strategy = make_strategy()
    result = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="trace-default-max-positions")
    )

    rendered_codes = [candidate.code for candidate in result.candidates if "max_positions = " in candidate.code]
    assert rendered_codes
    for code in rendered_codes:
        assert f"max_positions = {DEFAULT_MAX_POSITIONS}" in code
