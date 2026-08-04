"""The condition vocabulary must mean one thing everywhere it is used.

A strategy's conditions are written by a model, translated by condition_compiler, and
evaluated by PreparedFeatureStore. Those three had no shared definition of what a metric
name was: the prompt constrained none, the compiler knew eleven, and the evaluator
looked names up directly on the row. Six of the seven built-in strategy profiles
compiled to nothing, and the backtest silently validated a generic template while the
UI reported "매수 조건 N개 생성 완료".
"""

from array import array

import pytest

from ai_graph.graph import _strategy_profile_base
from ai_graph.llm.role_calls import STRATEGY_CONDITIONS_SYSTEM_PROMPT
from ai_graph.nodes.backtest_features import PreparedFeatureStore
from ai_graph.nodes.condition_compiler import compile_conditions, supported_metrics
from ai_graph.schemas import CandidateParameters, Condition, StrategyIR


def _bars(count: int = 40, **overrides):
    rows = []
    price = 1000.0
    for index in range(count):
        price *= 1.01
        row = {
            "date": f"2026-01-{index + 1:02d}",
            "ticker": "000660",
            "open": price,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": 1_000_000.0,
            "rsi": 45.0,
            "sma20": price * 0.98,
            "sma50": price * 0.97,
            "sma200": price * 0.95,
            "bb_upper": price * 1.05,
            "bb_lower": price * 0.95,
        }
        row.update(overrides)
        rows.append(row)
    return rows


def _actions(conditions, rows):
    store = PreparedFeatureStore(rows)
    ir = StrategyIR(
        strategy_id="t",
        entry_feature="close",
        exit_feature="close",
        proxy_feature="close",
        entry_conditions=conditions,
        exit_conditions=[Condition(left="rsi", operator="gte", right=99)],
    )
    parameters = CandidateParameters(
        profile="compiled_conditions", lookback=20, threshold=0.1,
        stop_loss_pct=0.08, take_profit_pct=0.2, max_positions=5,
    )
    return store.build_actions(ir, parameters)


def test_the_prompt_lists_exactly_what_the_compiler_accepts() -> None:
    """The generator must be told the vocabulary, or it invents names that cannot run."""

    for metric in ("close", "rsi", "sma200", "bb_lower", "volume_ratio_20"):
        assert metric in STRATEGY_CONDITIONS_SYSTEM_PROMPT
    # The old prompt offered "sma_20" as an example, which the compiler never knew.
    assert "sma_20" in supported_metrics()


@pytest.mark.parametrize(
    "query",
    [
        "200일선 위 눌림목 RSI 40 거래량",
        "볼린저 밴드 하단 재진입",
        "RSI 30 이하 과매도 반등",
    ],
)
def test_builtin_profiles_compile_to_their_own_rule(query: str) -> None:
    profile = _strategy_profile_base(query)

    compiled = compile_conditions(profile["entry_conditions"])

    assert compiled is not None, (
        f"{profile['strategy_id']} still falls back to a generic template: "
        f"{[c.left for c in profile['entry_conditions']]}"
    )


def test_close_above_sma_flag_is_evaluated_as_the_comparison_it_stands_for() -> None:
    """`close_above_sma_200 == 1` is a comparison, not a column.

    The evaluator looked it up on the row, found nothing, and never matched - while the
    compiler, once widened, rewrote it. Both must make the same rewrite or a rule that
    "compiled" quietly trades nothing.
    """

    above = _actions([Condition(left="close_above_sma_200", operator="eq", right=1)], _bars())
    below = _actions([Condition(left="close_below_sma_200", operator="eq", right=1)], _bars())

    assert 1 in above, "close is above sma200 on every bar and should enter"
    assert 1 not in below


def test_volume_ratio_is_derived_from_the_bars_not_demanded_of_the_row() -> None:
    rows = _bars()
    for row in rows[-3:]:
        row["volume"] = 5_000_000.0

    matched = _actions(
        [Condition(left="volume_ratio_20", operator="gte", right=2.0)], rows
    )

    assert 1 in matched


def test_percent_quoted_thresholds_are_converted_to_the_rows_unit() -> None:
    """`debt_ratio <= 100` and `debt_to_equity <= 1.0` are the same rule.

    The profiles say debt_ratio (a percentage); the warehouse stores debt_to_equity (a
    ratio). Compared without conversion, 100 vs ~1.0 passes everything.
    """

    rows = _bars()
    for row in rows:
        row["debt_to_equity"] = 1.8

    passes = _actions([Condition(left="debt_ratio", operator="lte", right=200)], rows)
    fails = _actions([Condition(left="debt_ratio", operator="lte", right=100)], rows)

    assert 1 in passes
    assert 1 not in fails


def test_missing_rsi_does_not_read_as_neutral_momentum() -> None:
    """A bar with no RSI used to default to 50, satisfying mid-band conditions."""

    rows = _bars()
    for row in rows:
        row.pop("rsi")

    store = PreparedFeatureStore(rows)

    assert all(value != value for value in store.rsi)  # NaN
    assert 1 not in _actions([Condition(left="rsi", operator="lte", right=60)], rows)


def test_compiled_actions_is_an_array_of_decisions_not_an_exception() -> None:
    """Bars missing every indicator must not crash - they simply never match."""

    rows = [
        {"date": f"2026-01-{i + 1:02d}", "ticker": "000660", "open": 100.0,
         "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0}
        for i in range(20)
    ]

    actions = _actions([Condition(left="close_above_sma_200", operator="eq", right=1)], rows)

    assert isinstance(actions, array)
    assert 1 not in actions
