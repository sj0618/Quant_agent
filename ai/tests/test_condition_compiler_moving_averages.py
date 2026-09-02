"""Crossovers and arbitrary-window moving averages, end to end through both evaluators.

Three common Korean requests stopped at a clarification on the deployed site instead of
running, and each failed at a different gate:

  * "20일 이동평균선이 60일선을 상향 돌파" - the vocabulary had no sma60.
  * "MACD 골든크로스" - cross_above was in the grammar but not in the compiler.
  * "볼린저밴드 하단" - a flag metric's inputs were never expanded, so the ta_* family
    holding them was not loaded and the condition was then reported unverifiable.
"""

from __future__ import annotations

from datetime import date, timedelta
from math import isfinite

import pytest

from ai_graph.data_sources.db import indicator_families_for_metrics
from ai_graph.nodes.backtest_features import (
    PreparedFeatureStore,
    unavailable_condition_metrics,
)
from ai_graph.nodes.condition_compiler import (
    compile_conditions,
    condition_metric_inputs,
    moving_average_spec,
    untranslatable_conditions,
)
from ai_graph.nodes.strategy_research import (
    StrategyResearchError,
    research_strategy_execution_spec,
)
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.schemas import Condition, ConditionOperator


class _ResearchClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.requests.append(request)
        return self.response


def _v_shaped_rows(count: int = 200, ticker: str = "005930") -> list[dict[str, object]]:
    """A falling then rising close path, so the fast average crosses the slow one once."""

    start = date(2024, 1, 1)
    rows: list[dict[str, object]] = []
    for index in range(count):
        close = 100.0 - index * 0.4 if index < count // 2 else 60.0 + (index - count // 2) * 0.9
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "ticker": ticker,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1_000.0,
            }
        )
    return rows


def _research_response(entry: dict, exit_: dict, required: list[str]) -> dict:
    return {
        "resolution_summary": "이동평균 교차 규칙으로 해석했습니다. 후보는 하나만 봉인합니다.",
        "sources": [
            {
                "source_id": "source-1",
                "title": "Moving average crossover",
                "url": "https://example.com/golden-cross",
                "claim": "골든크로스는 단기 이동평균이 장기 이동평균을 상향 돌파하는 신호입니다.",
            }
        ],
        "candidates": [
            {
                "candidate_id": "research-candidate-1",
                "title": "이동평균 교차",
                "hypothesis": "상향 돌파 뒤 추세가 이어질 수 있습니다.",
                "counter_hypothesis": "횡보장에서는 교차가 잦은 손절로 이어집니다.",
                "entry_conditions": [entry],
                "exit_conditions": [exit_],
                "required_metrics": required,
                "assumptions": ["KRX 일봉 종가 기준으로 다음 거래일 체결을 가정합니다."],
                "source_ids": ["source-1"],
            }
        ],
    }


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("sma60", ("sma", 60)),
        ("sma_60", ("sma", 60)),
        ("ema250", ("ema", 250)),
        ("sma2", ("sma", 2)),
        ("sma1", None),
        ("sma251", None),
        ("rsi", None),
    ],
)
def test_moving_average_window_bounds(name: str, expected: tuple[str, int] | None) -> None:
    assert moving_average_spec(name) == expected


def test_metric_to_metric_crossovers_compile_instead_of_being_refused() -> None:
    conditions = [
        Condition(left="sma20", operator=ConditionOperator.CROSS_ABOVE, right="sma60"),
        Condition(left="macd", operator=ConditionOperator.CROSS_ABOVE, right="macd_signal"),
        Condition(left="macd", operator=ConditionOperator.CROSS_BELOW, right="macd_signal"),
    ]

    assert untranslatable_conditions(conditions) == ()
    compiled = compile_conditions(conditions)
    assert compiled is not None
    # A cross is "above now, not above before"; a plain comparison would over-match.
    assert compiled.per_stock.count("and") >= 3
    # The 60-day average does not exist until sixty closes do.
    assert compiled.warmup_bars >= 60


def test_arbitrary_window_moving_average_compiles_from_closes() -> None:
    compiled = compile_conditions(
        [Condition(left="close", operator=ConditionOperator.GT, right="sma60")]
    )

    assert compiled is not None
    assert "closes[-59:]" in compiled.per_stock
    assert compiled.warmup_bars >= 60


def test_published_moving_average_windows_still_use_the_warehouse_value() -> None:
    compiled = compile_conditions(
        [Condition(left="close", operator=ConditionOperator.GT, right="sma200")]
    )

    assert compiled is not None
    assert compiled.per_stock == "(close > sma200)"
    assert condition_metric_inputs("sma200") == ("sma200",)


def test_feature_store_derives_sma60_and_fires_the_crossover_once() -> None:
    rows = _v_shaped_rows()
    store = PreparedFeatureStore(rows)

    sma60 = store._metric_series("sma60")  # noqa: SLF001 - evaluator contract under test.
    assert sum(1 for value in sma60 if isfinite(value)) == len(rows) - 59

    condition = Condition(
        left="sma20", operator=ConditionOperator.CROSS_ABOVE, right="sma60"
    )
    hits = [
        index
        for index in range(len(rows))
        # noqa: SLF001 - evaluator contract under test.
        if store._base_condition_matches(condition, index)  # noqa: SLF001
    ]
    assert len(hits) == 1
    index = hits[0]
    assert store._metric_series("sma20")[index] > sma60[index]  # noqa: SLF001
    assert store._metric_series("sma20")[index - 1] <= sma60[index - 1]  # noqa: SLF001


def test_feature_store_evaluates_a_macd_golden_cross_from_ohlcv_only() -> None:
    rows = _v_shaped_rows()
    store = PreparedFeatureStore(rows)

    condition = Condition(
        left="macd", operator=ConditionOperator.CROSS_ABOVE, right="macd_signal"
    )
    hits = [
        index
        for index in range(len(rows))
        if store._base_condition_matches(condition, index)  # noqa: SLF001
    ]

    assert hits
    assert unavailable_condition_metrics(rows, [condition]) == []


def test_researcher_admits_sma60_and_a_macd_cross_without_listing_500_metrics() -> None:
    client = _ResearchClient(
        _research_response(
            {"left": "sma20", "operator": "cross_above", "right": "sma60"},
            {"left": "sma20", "operator": "cross_below", "right": "sma60"},
            ["sma20", "sma60"],
        )
    )

    spec = research_strategy_execution_spec(
        query="20일 이동평균선이 60일 이동평균선을 상향 돌파하면 매수",
        available_metrics=["sma20", "macd", "macd_signal"],
        llm_client=client,
    )

    assert spec.candidates[0].entry_conditions[0].right == "sma60"
    allowed = client.requests[0].variables_jsonb["untrusted_quoted_context"]["allowed_metrics"]
    assert "sma60" not in allowed
    assert len(allowed) < 200
    notes = client.requests[0].variables_jsonb["untrusted_quoted_context"]["condition_grammar"][
        "notes"
    ]
    assert "sma{N}" in notes and "250" in notes


def test_researcher_still_refuses_a_moving_average_window_it_cannot_derive() -> None:
    client = _ResearchClient(
        _research_response(
            {"left": "close", "operator": "gt", "right": "sma400"},
            {"left": "close", "operator": "lt", "right": "sma400"},
            ["close", "sma400"],
        )
    )

    with pytest.raises(StrategyResearchError, match="sma400"):
        research_strategy_execution_spec(
            query="400일 이동평균 전략",
            available_metrics=["sma20"],
            llm_client=client,
        )


def test_flag_and_alias_metrics_load_their_families_and_are_not_reported_missing() -> None:
    """A sealed rule on `bollinger_lower` and `close_cross_above_sma20`.

    Neither name is a warehouse column: the first is a spelling of `bb_lower`, the
    second is a rule over close and sma20. Looking them up raw loaded no ta_* family,
    so the trend table was never read and the run stopped with
    "현재 데이터로 검증할 수 없는 조건이 있습니다: bb_lower, close_cross_above_sma20".
    """

    sealed_metrics = ("bollinger_lower", "close_cross_above_sma20")

    assert indicator_families_for_metrics(sealed_metrics, include_default=False) == (
        "trend",
        "volatility",
    )

    rows = _v_shaped_rows(count=80)
    for index, row in enumerate(rows):
        row["bb_lower"] = float(row["close"]) * 0.95
        row["sma20"] = float(row["close"]) * (1.01 if index % 2 else 0.99)

    conditions = [
        Condition(left="close", operator=ConditionOperator.LT, right="bollinger_lower"),
        Condition(left="close_cross_above_sma20", operator=ConditionOperator.EQ, right=1),
    ]
    assert unavailable_condition_metrics(rows, conditions) == []


def test_a_genuinely_absent_metric_is_still_reported_missing() -> None:
    rows = _v_shaped_rows(count=40)
    conditions = [Condition(left="close", operator=ConditionOperator.LT, right="bb_lower")]

    assert unavailable_condition_metrics(rows, conditions) == ["bb_lower"]
