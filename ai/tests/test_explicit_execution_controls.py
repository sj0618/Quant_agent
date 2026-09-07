from datetime import datetime
from pathlib import Path
import json
import pytest

from ai_graph.graph import _strategy_spec_from_execution_spec
from ai_graph.nodes.backtest import _engine_strategy_spec
from ai_graph.nodes.backtest_code import backtest_code_node
from ai_graph.nodes.strategy_research import research_strategy_execution_spec, StrategyResearchError
from ai_graph.research_contract import build_rule_draft, RuleDraftSigner, canonical_rule_digest, DraftTokenValidationError
from ai_graph.schemas import validate_execution_spec, canonical_execution_spec_digest, CodeCandidate
from ai_graph.strategy_parser import parse_execution_controls, StrategyParseError
from ai_graph.strategy_blueprint_catalog import strategy_blueprint_catalog_fingerprint
from test_exploration_policy_v2 import _active_policy
from test_strategy_research_v3 import _ResearchClient, _donchian_response


def generate(spec, policy=None):
    strategy = _strategy_spec_from_execution_spec(spec, policy.policy.model_dump() if policy else None)
    output = backtest_code_node({"strategy_spec": strategy.model_dump(), "trace_id": "controls-unit"})["backtest_code"]
    candidates = [CodeCandidate.model_validate(candidate) for candidate in output["candidates"]]
    return strategy, candidates


@pytest.mark.parametrize("count, stop_text, expected_stop, expected_trailing, cadence", [
    (3, "손절 없음", None, None, 5),
    (7, "고정 손절 없음", None, .25, 21),
    (3, "손절 12%", .12, .25, 5),
])
def test_raw_automatic_request_preserves_controls_in_all_three_candidates(count, stop_text, expected_stop, expected_trailing, cadence):
    policy = _active_policy()
    query = f"돈이 되는 전략 최대 {count}종목 {stop_text} {cadence}거래일마다 교체"
    draft = build_rule_draft(query=query, user_id="unit", signer=RuleDraftSigner("unit-controls-secret"), use_llm=False, exploration_policy=policy)
    wire = json.loads(draft.strategy_execution_spec.model_dump_json())
    restored = validate_execution_spec(wire)
    assert canonical_execution_spec_digest(restored) == draft.spec_hash
    strategy, candidates = generate(restored, policy)
    assert strategy.selection_mode == "automatic"
    assert len(candidates) == 3
    for candidate in candidates:
        params = candidate.parameters
        assert params.max_positions == count
        assert params.stop_loss_pct == expected_stop
        assert params.trailing_stop_pct == expected_trailing
        assert params.rebalance_interval_days == cadence
        engine = _engine_strategy_spec(strategy, candidate, available_ticker_count=100)
        assert engine.position_sizing.max_positions == count
        assert engine.risk_controls.stop_loss_pct == expected_stop
        assert engine.risk_controls.trailing_stop_pct == expected_trailing
    assert f"최대 {count}종목" in draft.editable_summary
    assert f"{cadence}거래일" in draft.editable_summary
    assert policy.policy_hash == _active_policy().policy_hash
    assert restored.catalog_hash == strategy_blueprint_catalog_fingerprint()


@pytest.mark.parametrize("query, expected", [
    ("돈치안 돌파 최대 7종목 손절 12% 매월 교체", {"max_positions": 7, "stop_loss_pct": .12, "rebalance_interval_days": 21}),
    ("돈치안 돌파 최대 3종목 손절 없음 5거래일마다 교체", {"max_positions": 3, "stop_loss_pct": None, "trailing_stop_pct": None, "rebalance_interval_days": 5}),
])
def test_raw_research_query_overrides_model_omissions_and_survives_json(query, expected):
    spec = research_strategy_execution_spec(query=query, available_metrics=["sma20"], llm_client=_ResearchClient(_donchian_response()))
    restored = validate_execution_spec(json.loads(spec.model_dump_json()))
    assert restored.execution_controls.model_dump() == expected
    assert restored.research_prompt_version == "v11-controls"
    strategy, candidates = generate(restored)
    candidate = candidates[0]
    for key, value in expected.items():
        assert getattr(candidate.parameters, key) == value
    engine = _engine_strategy_spec(strategy, candidate, available_ticker_count=100)
    assert engine.position_sizing.max_positions == expected["max_positions"]
    assert engine.risk_controls.stop_loss_pct == expected["stop_loss_pct"]


def test_stop_only_json_does_not_turn_unspecified_trailing_into_disable():
    controls = parse_execution_controls("고정 손절 없음")
    assert json.loads(controls.model_dump_json()) == {"stop_loss_pct": None}
    spec = research_strategy_execution_spec(query="돈치안 돌파 고정 손절 없음", available_metrics=["sma20"], llm_client=_ResearchClient(_donchian_response()))
    restored = validate_execution_spec(json.loads(spec.model_dump_json()))
    assert restored.execution_controls.model_dump() == {"stop_loss_pct": None}
    _, candidates = generate(restored)
    assert candidates[0].parameters.stop_loss_pct is None
    assert candidates[0].parameters.trailing_stop_pct == .25


def test_pre_change_7417_signed_wire_contracts_keep_digest_and_token():
    records = json.loads((Path(__file__).parent / "fixtures/controls_7417_signed_wire.json").read_text())
    signer = RuleDraftSigner("unit-controls-secret")
    for record in records:
        spec = validate_execution_spec(record["spec"])
        assert spec.execution_controls is None
        assert "execution_controls" not in spec.model_dump()
        assert canonical_rule_digest(spec) == record["digest"]
        assert canonical_execution_spec_digest(spec) == record["digest"]
        signer.verify(token=record["token"], rule=spec, user_id="unit", now=datetime.fromisoformat(record["now"]))
        changed = validate_execution_spec({**record["spec"], "execution_controls": {"stop_loss_pct": None}})
        assert canonical_execution_spec_digest(changed) != record["digest"]
        with pytest.raises(DraftTokenValidationError):
            signer.verify(token=record["token"], rule=changed, user_id="unit", now=datetime.fromisoformat(record["now"]))
    old_v3 = validate_execution_spec(records[1]["spec"])
    strategy, candidates = generate(old_v3)
    assert candidates[0].parameters.stop_loss_pct is not None
    assert candidates[0].parameters.trailing_stop_pct is not None


@pytest.mark.parametrize("text", ["매월말 교체", "매월 첫 거래일 교체", "2거래일마다 교체", "손절 0%", "손절 없음 손절 8%"])
def test_unsupported_controls_are_rejected_before_research(text):
    client = _ResearchClient(_donchian_response())
    with pytest.raises(StrategyResearchError):
        research_strategy_execution_spec(query=f"돈치안 돌파 {text}", available_metrics=["sma20"], llm_client=client)
    assert client.requests == []


def test_cadence_does_not_reinterpret_reporting_periods():
    assert parse_execution_controls("월간 수익률을 보고하는 RSI 전략") is None
    assert parse_execution_controls("weekly RSI 기준 전략") is None
    assert parse_execution_controls("매월 교체").rebalance_interval_days == 21


def test_existing_numeric_trailing_and_take_profit_are_preserved():
    controls = parse_execution_controls("손절 12% 추적 손절 30% 익절 60%")
    assert controls.model_dump() == {"stop_loss_pct": .12, "trailing_stop_pct": .3, "take_profit_pct": .6}


def test_complete_v1_rule_with_controls_uses_v3_without_changing_conditions():
    from test_strategy_research_v3 import _rsi_mean_reversion_response
    client = _ResearchClient(_rsi_mean_reversion_response())
    draft = build_rule_draft(
        query="최근 5년 RSI 30 이하 매수 RSI 55 이상 매도 최대 3종목 손절 없음",
        user_id="unit", signer=RuleDraftSigner("unit-controls-secret"), use_llm=True,
        available_metrics=["rsi_14"], llm_client=client,
    )
    assert draft.is_executable
    spec = validate_execution_spec(draft.strategy_execution_spec)
    assert spec.execution_controls.model_dump() == {"max_positions": 3, "stop_loss_pct": None, "trailing_stop_pct": None}
    assert len(client.requests) == 1
    assert spec.candidates[0].entry_conditions[0].right == 30
    assert spec.candidates[0].exit_conditions[0].right == 55
    _, candidates = generate(spec)
    assert candidates[0].parameters.max_positions == 3
    assert candidates[0].parameters.stop_loss_pct is None


def test_controls_cannot_admit_a_changed_explicit_v1_rule():
    from test_strategy_research_v3 import _rsi_mean_reversion_response
    draft = build_rule_draft(
        query="최근 5년 RSI 30 이하 매수 RSI 70 이상 매도 최대 3종목 손절 없음",
        user_id="unit", signer=RuleDraftSigner("unit-controls-secret"), use_llm=True,
        available_metrics=["rsi_14"], llm_client=_ResearchClient(_rsi_mean_reversion_response()),
    )
    assert not draft.is_executable
    assert draft.parse_token is None


def test_no_controls_keeps_existing_v1_fast_path():
    draft = build_rule_draft(query="RSI 30 이하 매수 RSI 70 이상 매도", user_id="unit", signer=RuleDraftSigner("unit-controls-secret"), use_llm=False)
    assert draft.is_executable
    assert draft.spec_version == "strategy-execution-spec.v1"
    assert "execution_controls" not in draft.strategy_execution_spec.model_dump()


@pytest.mark.parametrize("query, key, expected", [
    ("손절 1%", "stop_loss_pct", .01),
    ("추적 손절 2%", "trailing_stop_pct", .02),
    ("익절 4%", "take_profit_pct", .04),
])
def test_explicit_small_percentages_follow_existing_catalog_bounds(query, key, expected):
    assert parse_execution_controls(query).model_dump() == {key: expected}
    policy = _active_policy()
    draft = build_rule_draft(query="돈이 되는 전략 " + query, user_id="unit", signer=RuleDraftSigner("unit-controls-secret"), use_llm=False, exploration_policy=policy)
    strategy, candidates = generate(validate_execution_spec(json.loads(draft.strategy_execution_spec.model_dump_json())), policy)
    for candidate in candidates:
        assert getattr(candidate.parameters, key) == expected
        assert getattr(_engine_strategy_spec(strategy, candidate, available_ticker_count=100).risk_controls, key) == expected


def test_calendar_reporting_does_not_set_execution_cadence():
    assert parse_execution_controls("매월말 수익률 보고") is None
    assert parse_execution_controls("달력 기준 월초 수익률 보고") is None
    with pytest.raises(StrategyParseError):
        parse_execution_controls("매월말 종목 교체")


@pytest.mark.parametrize("automatic", [True, False])
def test_explicit_take_profit_disable_survives_signed_json_and_engine(automatic):
    if automatic:
        policy = _active_policy()
        draft = build_rule_draft(query="돈이 되는 전략 익절 없음", user_id="unit", signer=RuleDraftSigner("unit-controls-secret"), use_llm=False, exploration_policy=policy)
        spec = draft.strategy_execution_spec
        assert "익절 없음" in draft.editable_summary
    else:
        policy = None
        spec = research_strategy_execution_spec(query="돈치안 돌파 익절 없음", available_metrics=["sma20"], llm_client=_ResearchClient(_donchian_response()))
    restored = validate_execution_spec(json.loads(spec.model_dump_json()))
    assert restored.execution_controls.model_dump() == {"take_profit_pct": None}
    strategy, candidates = generate(restored, policy)
    for candidate in candidates:
        assert candidate.parameters.take_profit_pct is None
        assert _engine_strategy_spec(strategy, candidate, available_ticker_count=100).risk_controls.take_profit_pct is None
        compile(candidate.code, "<generated-unit-candidate>", "exec")
