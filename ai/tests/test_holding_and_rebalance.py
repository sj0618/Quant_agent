"""Time exits and periodic rebalancing for V3 research candidates.

Two demo requests were mis-modelled on the deployed site because the grammar had no
way to say "when":

  * "거래량이 20일 평균의 2배 이상 터진 종목을 사고 5일 뒤 파는 전략" sealed an exit of
    ``close gte 0``, which is true on every bar - 717 trades, OOS Sharpe -3.6.
  * "최근 3개월 수익률 상위 모멘텀 종목을 사고 한 달마다 교체" sealed no rebalance at all.

``holding_days`` and ``rebalance_interval_days`` on ResearchCandidateV3 say it
directly. Structured eligibility selects the targets; the engine enforces holding
periods from actual fills and executes the next-open orders.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from ai_graph.llm.base import LLMJsonRequest
from ai_graph.nodes.backtest_code import _normalized_strategy_ir, _render_structured_reference_code
from ai_graph.nodes import backtest as backtest_node
from ai_graph.nodes.strategy_research import (
    StrategyResearchError,
    research_strategy_execution_spec,
)
from ai_graph.schemas import (
    CandidateParameters,
    CodeCandidate,
    StrategySpec,
    Condition,
    ConditionOperator,
    ResearchCandidateV3,
    StrategyIR,
)


def _rows(closes: list[float], ticker: str = "005930") -> list[dict[str, object]]:
    start = date(2024, 1, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "ticker": ticker,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1_000.0,
        }
        for index, close in enumerate(closes)
    ]


def _ir(**overrides: object) -> StrategyIR:
    base: dict[str, object] = {
        "strategy_id": "time_exit_probe",
        "entry_feature": "compiled",
        "exit_feature": "compiled",
        "proxy_feature": "past_only_adjusted_ohlcv",
        "entry_conditions": [
            Condition(left="close", operator=ConditionOperator.GTE, right=100.0)
        ],
        "exit_conditions": [],
    }
    base.update(overrides)
    return StrategyIR.model_validate(base)


def _parameters(**overrides: object) -> CandidateParameters:
    base: dict[str, object] = {
        "profile": "compiled_conditions",
        "lookback": 20,
        "threshold": 0.0,
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.2,
        "max_positions": 1,
    }
    base.update(overrides)
    return CandidateParameters.model_validate(base)


def _fill_dates(rows, strategy_ir, parameters) -> tuple[list[int], list[int]]:
    strategy = StrategySpec(
        strategy_id=strategy_ir.strategy_id, name="Synthetic holding check", market="KRX", timeframe="daily",
        entry_conditions=strategy_ir.entry_conditions, exit_conditions=strategy_ir.exit_conditions,
        risk_constraints={"max_position_pct": 1.0, "stop_loss_pct": parameters.stop_loss_pct}, confidence=1.0,
    )
    candidate = CodeCandidate(
        candidate_id="holding-fill-unit", variant="A", validation_ok=True,
        code="def build_signals(prices):\n    return []", representation="structured",
        strategy_ir=strategy_ir, parameters=parameters,
    )
    result = backtest_node._fold_engine(strategy, candidate, rows, rows, {str(row["date"]) for row in rows})
    indices = {str(row["date"]): index for index, row in enumerate(rows)}
    buys = [indices[event.date] for event in result.order_audit if event.status == "executed" and event.side == "buy"]
    sells = [indices[event.date] for event in result.order_audit if event.status == "executed" and event.side == "sell"]
    return buys, sells

# --- schema -----------------------------------------------------------------


def _candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "research-candidate-1",
        "title": "거래량 급증 5일 보유",
        "hypothesis": "거래량 급증 뒤 단기 추종이 나타날 수 있습니다.",
        "counter_hypothesis": "급증은 분배 신호일 수도 있습니다.",
        "entry_conditions": [{"left": "volume_ratio_20", "operator": "gte", "right": 2.0}],
        "exit_conditions": [],
        "holding_days": 5,
        "required_metrics": ["volume_ratio_20"],
        "assumptions": ["KRX 일봉 종가 기준 다음 거래일 시가 체결을 가정합니다."],
        "source_ids": ["source-1"],
        "backtest_years": 2,
        "backtest_period_basis": "테스트 AI가 데이터 조회 전에 2년을 선택했습니다.",
    }
    payload.update(overrides)
    return payload


def test_holding_days_replaces_an_exit_condition() -> None:
    candidate = ResearchCandidateV3.model_validate(_candidate())

    assert candidate.holding_days == 5
    assert candidate.exit_conditions == []


def test_a_candidate_with_no_exit_at_all_is_still_refused() -> None:
    with pytest.raises(ValidationError, match="exit_conditions or holding_days"):
        ResearchCandidateV3.model_validate(_candidate(holding_days=None))


@pytest.mark.parametrize("holding_days", [0, 251])
def test_holding_days_is_bounded(holding_days: int) -> None:
    with pytest.raises(ValidationError):
        ResearchCandidateV3.model_validate(_candidate(holding_days=holding_days))


@pytest.mark.parametrize("interval", [4, 64])
def test_rebalance_interval_is_bounded(interval: int) -> None:
    with pytest.raises(ValidationError):
        ResearchCandidateV3.model_validate(_candidate(rebalance_interval_days=interval))


@pytest.mark.parametrize(("holding_days", "interval"), [(1, 5), (250, 63)])
def test_boundary_values_are_accepted(holding_days: int, interval: int) -> None:
    candidate = ResearchCandidateV3.model_validate(
        _candidate(holding_days=holding_days, rebalance_interval_days=interval)
    )

    assert (candidate.holding_days, candidate.rebalance_interval_days) == (
        holding_days,
        interval,
    )


# --- evaluator --------------------------------------------------------------


def test_a_position_exits_exactly_five_sessions_after_it_opened() -> None:
    rows = _rows([110.0] * 20)
    buys, sells = _fill_dates(rows, _ir(holding_days=5), _parameters())
    assert buys == [1, 7, 13, 19]
    assert sells == [6, 12, 18]
    assert all(sell - buy == 5 for buy, sell in zip(buys, sells, strict=False))

def test_without_holding_days_the_same_rule_never_sells() -> None:
    buys, sells = _fill_dates(_rows([110.0] * 20), _ir(), _parameters())
    assert buys == [1]
    assert sells == []

def test_an_empty_slot_is_filled_before_the_next_rebalance_date() -> None:
    # Eligible at session 3; the next-open entry at 4 precedes the rotation at 5.
    buys, sells = _fill_dates(
        _rows([90.0] * 3 + [110.0] * 17), _ir(execution_mode="scheduled_rotation"),
        _parameters(rebalance_interval_days=5),
    )
    assert buys == [4]
    assert sells == []

def test_a_holding_that_stops_matching_is_exited_on_the_next_rebalance_date() -> None:
    buys, sells = _fill_dates(
        _rows([110.0] * 7 + [90.0] * 13), _ir(execution_mode="scheduled_rotation"),
        _parameters(rebalance_interval_days=5, stop_loss_pct=0.5),
    )
    assert buys == [1]
    # A failed entry at 7 is reselected at 10 and sold at the next open.
    assert sells == [11]

def test_holding_days_and_rebalancing_compose() -> None:
    buys, sells = _fill_dates(
        _rows([110.0] * 20), _ir(execution_mode="scheduled_rotation", holding_days=3),
        _parameters(rebalance_interval_days=5),
    )
    assert buys == [1, 5, 9, 13, 17]
    assert sells == [4, 8, 12, 16]

def test_the_audit_descriptor_states_the_same_timing_the_evaluator_runs() -> None:
    """One rule, one description. The descriptor is what an auditor reads back."""

    strategy_ir = _ir(execution_mode="scheduled_rotation", holding_days=5)
    code = _render_structured_reference_code(strategy_ir, _parameters(rebalance_interval_days=21))

    assert "holding_days = 5" in code
    assert "execution_mode = 'scheduled_rotation'" in code
    assert "rebalance_interval_days = 21" in code


# --- researcher -------------------------------------------------------------


class _ScriptedClient:
    def __init__(self, *responses: dict) -> None:
        self._responses = list(responses)
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.requests.append(request)
        return self._responses[min(len(self.requests) - 1, len(self._responses) - 1)]


def _response(candidate: dict[str, object]) -> dict:
    return {
        "resolution_summary": "거래량 급증 뒤 5일 보유로 해석했습니다. 후보는 하나만 봉인합니다.",
        "sources": [
            {
                "source_id": "source-1",
                "title": "Volume spike momentum",
                "url": "https://example.com/volume-spike",
                "claim": "거래량 급증은 단기 가격 추종과 연관된다고 보고됩니다.",
            }
        ],
        "candidates": [candidate],
    }


_ALWAYS_TRUE_EXIT = _candidate(
    exit_conditions=[
        {"left": "close", "operator": "gte", "right": 0.0, "window": 5, "aggregate": "last"}
    ],
    holding_days=None,
)


def test_an_always_true_exit_is_rejected_and_repaired_into_holding_days() -> None:
    client = _ScriptedClient(_response(_ALWAYS_TRUE_EXIT), _response(_candidate()))

    spec = research_strategy_execution_spec(
        query="거래량이 20일 평균의 2배 이상 터진 종목을 사고 5일 뒤 파는 전략",
        available_metrics=["volume_ratio_20", "close"],
        llm_client=client,
    )

    assert len(client.requests) == 2
    failure = client.requests[1].variables_jsonb["untrusted_quoted_context"]
    assert failure["previous_validation_failure"]["code"] == "research_exit_condition_vacuous"
    assert spec.candidates[0].holding_days == 5
    assert spec.candidates[0].exit_conditions == []


def test_an_always_true_exit_that_survives_the_repair_turn_stops_the_run() -> None:
    client = _ScriptedClient(_response(_ALWAYS_TRUE_EXIT))

    with pytest.raises(StrategyResearchError) as failure:
        research_strategy_execution_spec(
            query="거래량이 20일 평균의 2배 이상 터진 종목을 사고 5일 뒤 파는 전략",
            available_metrics=["volume_ratio_20", "close"],
            llm_client=client,
        )

    assert failure.value.cause_code == "research_resolution_invalid_after_repair"


def test_a_real_exit_condition_is_not_mistaken_for_an_always_true_one() -> None:
    client = _ScriptedClient(
        _response(
            _candidate(
                exit_conditions=[{"left": "close", "operator": "lt", "right": 1000.0}],
                holding_days=None,
            )
        )
    )

    spec = research_strategy_execution_spec(
        query="거래량 급증 종목을 사고 종가가 1000원 아래로 내려가면 파는 전략",
        available_metrics=["volume_ratio_20", "close"],
        llm_client=client,
    )

    assert len(client.requests) == 1
    assert spec.candidates[0].holding_days is None


def test_the_prompt_teaches_both_fields() -> None:
    client = _ScriptedClient(_response(_candidate()))

    research_strategy_execution_spec(
        query="거래량이 20일 평균의 2배 이상 터진 종목을 사고 5일 뒤 파는 전략",
        available_metrics=["volume_ratio_20", "close"],
        llm_client=client,
    )

    prompt = client.requests[0].system_prompt
    assert "holding_days" in prompt and "rebalance_interval_days" in prompt
    assert "close gte 0" in prompt
    assert "21" in prompt


# --- wiring -----------------------------------------------------------------


def test_a_sealed_candidates_timing_reaches_the_strategy_ir_the_engine_runs() -> None:
    from ai_graph.graph import _strategy_spec_from_execution_spec
    from ai_graph.nodes.backtest_code import build_code_generation_plan, map_strategy_features

    client = _ScriptedClient(
        _response(_candidate(holding_days=5, rebalance_interval_days=21))
    )
    spec = research_strategy_execution_spec(
        query="거래량이 20일 평균의 2배 이상 터진 종목을 사고 5일 뒤 파는 전략",
        available_metrics=["volume_ratio_20", "close"],
        llm_client=client,
    )

    strategy = _strategy_spec_from_execution_spec(spec.model_dump(mode="json"))
    assert strategy.risk_constraints["holding_days"] == 5
    assert strategy.risk_constraints["rebalance_interval_days"] == 21

    plan = build_code_generation_plan(strategy, map_strategy_features(strategy))
    strategy_ir = _normalized_strategy_ir(None, strategy, plan)
    assert strategy_ir.holding_days == 5
    assert strategy_ir.execution_mode == "scheduled_rotation"
