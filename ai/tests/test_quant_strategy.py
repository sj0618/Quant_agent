from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from ai_graph import run_analysis
from ai_graph.graph import build_strategy_spec
from ai_graph.nodes.backtest import backtest_node, rule_provenance
from ai_graph.nodes.backtest_code import (
    Loop3Request,
    _candidate_profiles,
    build_code_generation_plan,
    generate_loop3_candidates,
    map_strategy_features,
)
from ai_graph.nodes.backtest_features import PreparedFeatureStore
from ai_graph.quant_strategy import (
    AQR_TREND_SOURCE,
    AUTOMATIC_TOURNAMENT_PROFILES,
    BACKTEST_OVERFITTING_SOURCE,
    KEN_FRENCH_MOMENTUM_SOURCE,
    MSCI_MOMENTUM_METHODOLOGY_SOURCE,
    build_strategy_explanation,
    classify_strategy_request,
    compute_academic_factor_arrays,
    infer_automatic_strategy_preferences,
)
from ai_graph.schemas import CandidateParameters, StrategyIR


def _trend_rows(days: int = 300) -> list[dict[str, object]]:
    start = date(2024, 1, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "ticker": "000001",
            "close": 100.0 * (1.001**index),
            "volume": 1_000_000.0,
            "rsi": 50.0,
        }
        for index in range(days)
    ]


def _cross_sectional_rows(days: int = 300) -> list[dict[str, object]]:
    start = date(2024, 1, 1)
    daily_growth = {
        "000001": 1.004,
        "000002": 1.002,
        "000003": 0.999,
    }
    return [
        {
            "date": (start + timedelta(days=day_index)).isoformat(),
            "ticker": ticker,
            "close": 100.0 * (growth**day_index),
            "volume": 1_000_000.0,
            "rsi": 50.0,
        }
        for day_index in range(days)
        for ticker, growth in daily_growth.items()
    ]


def test_concrete_rule_wins_over_automatic_request() -> None:
    assert (
        classify_strategy_request("검증된 전략을 추천하되 RSI 30 이하에서 매수") == "user_defined"
    )
    assert classify_strategy_request("자동 추천하되 주가가 10000원 아래면 매수") == "user_defined"
    assert classify_strategy_request("매수할 종목을 자동 추천해줘") == "automatic"
    assert classify_strategy_request("인기 있는 모멘텀 퀀트 전략을 자동 추천해줘") == "automatic"
    assert classify_strategy_request("시장 상황을 설명해줘") == "standard"


def test_vague_strategy_requests_become_automatic_without_magic_words() -> None:
    assert classify_strategy_request("돈 좀 벌게 아무거나 괜찮은 걸로 해봐") == "automatic"
    assert classify_strategy_request("뭐 좀 괜찮은 거 없냐") == "automatic"
    assert classify_strategy_request("종목 좀 골라줘") == "automatic"
    assert classify_strategy_request("RSI 눌림목으로 해줘") == "standard"
    assert classify_strategy_request("배당 방어주 전략") == "standard"
    assert classify_strategy_request("저PER 종목으로 골라줘") == "standard"
    assert classify_strategy_request("FCF 좋은 기업으로 해줘") == "standard"


def test_vague_request_runs_the_full_automatic_pipeline() -> None:
    envelope = run_analysis(
        "뭐 좀 괜찮은 거 없냐",
        trace_id="vague-automatic-full-pipeline",
    )

    assert envelope.status == "ready"
    assert envelope.strategy_spec is not None
    assert envelope.strategy_spec.selection_mode == "automatic"
    assert envelope.strategy_spec.strategy_id.startswith("automatic_performance_momentum")
    assert envelope.rule_provenance is not None
    assert envelope.rule_provenance.substituted is False
    assert envelope.user_payload.performance is not None
    public_explanation = envelope.user_payload.performance.strategy_explanation
    assert public_explanation is not None
    assert len(public_explanation.generated_strategies) == 3
    assert len(
        {item["execution_signature"] for item in public_explanation.generated_strategies}
    ) == 3
    assert all(item["profile"] == "compiled_conditions" for item in public_explanation.generated_strategies)
    selected_blueprint_id = envelope.rule_provenance.evaluated_rule.removeprefix(
        "automatic_blueprint:"
    )
    selected_blueprint = next(
        item
        for item in public_explanation.generated_strategies
        if item["blueprint_id"] == selected_blueprint_id
    )
    assert public_explanation.title == selected_blueprint["title"]
    assert public_explanation.indicators
    assert all(
        item.formula and item.derivation and item.why_used
        for item in public_explanation.indicators
    )


def test_academic_factors_match_exact_12_1_and_sma_boundaries() -> None:
    closes = np.asarray([100.0 + index for index in range(274)])
    factors = compute_academic_factor_arrays(closes)

    assert np.isnan(factors.momentum_12_1[251])
    assert factors.momentum_12_1[252] == (331.0 / 100.0 - 1.0)
    assert factors.sma_50[252] == 327.5
    assert factors.sma_200[252] == 252.5
    assert factors.rebalance_eligible[252]
    assert factors.rebalance_eligible[273]
    assert not factors.rebalance_eligible[272]


def test_academic_factors_do_not_change_when_future_rows_are_appended() -> None:
    prefix = np.asarray([100.0 * (1.001**index) for index in range(290)])
    before = compute_academic_factor_arrays(prefix)
    after = compute_academic_factor_arrays(
        np.concatenate((prefix, np.asarray([5_000.0 - 100.0 * index for index in range(30)])))
    )

    for name in (
        "momentum_12_1",
        "sma_50",
        "sma_200",
        "realized_volatility_21d",
    ):
        np.testing.assert_allclose(
            getattr(before, name),
            getattr(after, name)[: len(prefix)],
            equal_nan=True,
        )
    np.testing.assert_array_equal(
        before.rebalance_eligible,
        after.rebalance_eligible[: len(prefix)],
    )


def test_realized_volatility_uses_exactly_21_past_daily_returns() -> None:
    closes = np.asarray([100.0 + index for index in range(60)])
    factors = compute_academic_factor_arrays(closes)
    index = 30
    expected_returns = closes[index - 20 : index + 1] / closes[index - 21 : index] - 1.0
    expected = np.std(expected_returns) * np.sqrt(252.0)

    np.testing.assert_allclose(factors.realized_volatility_21d[index], expected)

    closes_with_gap = closes.copy()
    closes_with_gap[20] = np.nan
    invalid = compute_academic_factor_arrays(closes_with_gap)
    assert np.isnan(invalid.realized_volatility_21d[index])


def test_automatic_request_builds_cited_three_family_tournament() -> None:
    strategy = build_strategy_spec(
        "사람들이 많이 쓰는 검증된 퀀트 전략으로 자동 추천해줘",
        variant="A",
        semantic_slots={},
    )

    assert strategy.selection_mode == "automatic"
    assert strategy.strategy_id.startswith("automatic_performance_momentum")
    assert AQR_TREND_SOURCE in strategy.source_refs
    assert KEN_FRENCH_MOMENTUM_SOURCE in strategy.source_refs
    assert MSCI_MOMENTUM_METHODOLOGY_SOURCE in strategy.source_refs
    assert BACKTEST_OVERFITTING_SOURCE in strategy.source_refs
    plan = build_code_generation_plan(strategy, map_strategy_features(strategy))
    assert plan.entry_feature == "performance_momentum_tournament"
    assert tuple(_candidate_profiles(plan)) == ("compiled_conditions",) * 3
    assert len({item.execution_signature for item in plan.generated_strategies}) == 3
    candidates = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="robust-tournament-contract")
    ).candidates
    assert (
        tuple(
            candidate.parameters.profile
            for candidate in candidates
            if candidate.parameters is not None
        )
        == ("compiled_conditions",) * 3
    )
    assert [candidate.parameters.lookback for candidate in candidates if candidate.parameters] == [
        252,
        252,
        252,
    ]
    assert [candidate.parameters.threshold for candidate in candidates if candidate.parameters] == [
        0.0,
        0.0,
        0.0,
    ]
    assert all(
        candidate.parameters is not None
        and candidate.parameters.stop_loss_pct == 0.20
        and candidate.parameters.take_profit_pct == 10.0
        and candidate.parameters.max_positions == 10
        for candidate in candidates
    )

    explanation = build_strategy_explanation(strategy)
    assert explanation["selection_mode"] == "automatic"
    assert "미래 수익을 보장하지 않습니다" in explanation["caution"]
    assert {item["key"] for item in explanation["indicators"]} == {
        "strategy_tournament",
        "cross_sectional_rank",
        "momentum_12_1",
        "momentum_blend",
        "winner_hold",
        "crash_risk_guard",
        "portfolio_customization",
        "benchmark_period_gate",
    }


def test_user_risk_and_horizon_customize_the_automatic_candidate_menu() -> None:
    aggressive = build_strategy_spec(
        "5종목으로 단기 고수익 집중 모멘텀 전략 만들어줘",
        variant="A",
        semantic_slots={},
    )
    assert aggressive.selection_mode == "automatic"
    assert (
        infer_automatic_strategy_preferences(
            "5종목으로 단기 고수익 집중 모멘텀 전략 만들어줘"
        ).risk_style
        == "aggressive"
    )
    aggressive_plan = build_code_generation_plan(
        aggressive,
        map_strategy_features(aggressive),
    )
    assert aggressive_plan.customization_style == "aggressive"
    assert aggressive_plan.investment_horizon == "short"
    assert aggressive_plan.rebalance_interval_days == 10
    assert aggressive_plan.trailing_stop_pct == 0.30
    assert aggressive_plan.medium_momentum_weight == 0.70
    assert aggressive_plan.lookbacks == [20, 20, 20]
    assert [item.blueprint_id for item in aggressive_plan.generated_strategies] == [
        "qb-v2-donchian-price-breakout",
        "qb-v2-atr-range-expansion-breakout",
        "qb-v2-bollinger-volatility-breakout",
    ]
    assert len(aggressive_plan.generated_strategies) == 3
    assert len({item.execution_signature for item in aggressive_plan.generated_strategies}) == 3
    assert all(
        "아직 승자를 정하지 않았으며" in item.why_generated and item.formula and item.derivation
        for item in aggressive_plan.generated_strategies
    )
    aggressive_candidates = generate_loop3_candidates(
        Loop3Request(
            strategy=aggressive,
            variant="A",
            trace_id="aggressive-custom",
            max_positions=5,
        )
    ).candidates
    assert all(
        candidate.parameters is not None
        and candidate.parameters.max_positions == 5
        and candidate.parameters.stop_loss_pct == 0.25
        and candidate.parameters.rebalance_interval_days == 10
        for candidate in aggressive_candidates
    )

    defensive = build_strategy_spec(
        "손실을 최소화하는 장기 저변동 15종목 전략 만들어줘",
        variant="A",
        semantic_slots={},
    )
    defensive_plan = build_code_generation_plan(
        defensive,
        map_strategy_features(defensive),
    )
    assert defensive_plan.customization_style == "defensive"
    assert defensive_plan.investment_horizon == "long"
    assert defensive_plan.rebalance_interval_days == 42
    assert defensive_plan.lookbacks == [126, 200, 126]
    assert [item.blueprint_id for item in defensive_plan.generated_strategies] == [
        "qb-v2-low-volatility-momentum",
        "qb-v2-pure-low-volatility-trend",
        "qb-v2-ulcer-index-trend",
    ]
    assert defensive.risk_constraints["stop_loss_pct"] == 0.12
    assert defensive.risk_constraints["trailing_stop_pct"] == 0.15


def test_automatic_indicator_explanations_show_formula_derivation_and_customization() -> None:
    strategy = build_strategy_spec(
        "5종목으로 단기 고수익 집중 모멘텀 전략 만들어줘",
        variant="A",
        semantic_slots={},
    )
    parameters = CandidateParameters(
        profile="trend_leader_rotation",
        lookback=126,
        threshold=0.0,
        stop_loss_pct=0.25,
        take_profit_pct=10.0,
        max_positions=5,
        rebalance_interval_days=10,
        trailing_stop_pct=0.30,
        medium_momentum_weight=0.70,
    )
    explanation = build_strategy_explanation(
        strategy,
        selected_profile=parameters.profile,
        selected_parameters=parameters,
    )
    indicators = {item["key"]: item for item in explanation["indicators"]}

    assert "70%×중기모멘텀순위" in indicators["momentum_blend"]["formula"]
    assert "입력 투자기간" in indicators["momentum_blend"]["customization"]
    assert "손절 25%" in indicators["crash_risk_guard"]["customization"]
    assert "최대 5종목" in indicators["portfolio_customization"]["plain_explanation"]
    assert "패배율 ≥ 50%이면 실패" in indicators["benchmark_period_gate"]["formula"]
    assert all(item.get("formula") and item.get("derivation") for item in indicators.values())


def test_original_vague_request_survives_a_concrete_interpreter_rewrite() -> None:
    strategy = build_strategy_spec(
        "RSI가 30 이하일 때 매수하고 70 이상이면 매도",
        original_query="대충 좋은 걸로 돈 좀 벌게 해봐",
        variant="A",
        semantic_slots={},
    )

    assert strategy.selection_mode == "automatic"
    assert strategy.strategy_id.startswith("automatic_performance_momentum")
    assert strategy.entry_conditions[0].left == "past_only_signal"


def test_automatic_profile_is_reported_as_the_intended_rule() -> None:
    envelope = run_analysis(
        "사람들이 많이 쓰는 검증된 퀀트 전략으로 자동 추천해줘",
        trace_id="automatic-profile-provenance",
    )

    assert envelope.status == "ready"
    assert envelope.strategy_spec is not None
    assert envelope.strategy_spec.selection_mode == "automatic"
    assert envelope.rule_provenance is not None
    assert envelope.rule_provenance.substituted is False
    assert envelope.rule_provenance.evaluated_rule.startswith("automatic_blueprint:qb-v2-")
    assert envelope.rule_provenance.untranslatable_conditions == []


def test_every_pre_registered_automatic_profile_has_truthful_provenance() -> None:
    for profile in AUTOMATIC_TOURNAMENT_PROFILES:
        provenance = rule_provenance(
            {
                "selected_candidate": {"parameters": {"profile": profile}},
                "candidates": [],
            },
            [{"left": "past_only_signal", "operator": "eq", "right": 1}],
            selection_mode="automatic",
        )

        assert provenance["evaluated_rule"] == f"automatic_profile:{profile}"
        assert provenance["substituted"] is False
        assert provenance["reason"] is None


def test_automatic_profile_waits_for_history_and_monthly_rebalance() -> None:
    rows = _trend_rows()
    store = PreparedFeatureStore(rows)
    strategy_ir = StrategyIR(
        strategy_id="automatic_academic_momentum",
        entry_feature="academic_momentum_trend",
        exit_feature="monthly_trend_or_stop",
        proxy_feature="past_only_price_factors",
    )
    parameters = CandidateParameters(
        profile="academic_momentum_trend",
        lookback=252,
        threshold=0.0,
        stop_loss_pct=0.08,
        take_profit_pct=0.45,
        max_positions=1,
    )

    actions = store.build_actions(strategy_ir, parameters)

    assert 1 not in actions[:252]
    assert actions[252] == 1


def test_automatic_tournament_does_not_tune_after_seeing_returns() -> None:
    strategy = build_strategy_spec(
        "뭐 좀 괜찮은 거 없냐",
        variant="A",
        semantic_slots={},
    )
    generated = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="fixed-auto-tournament")
    )

    output = backtest_node(
        {
            "strategy_spec": strategy.model_dump(),
            "backtest_code": generated.model_dump(),
            "price_rows": _trend_rows(),
        }
    )

    stats = output["backtest"]["execution_stats"]
    assert stats["selection_policy"] == "performance_momentum_train_select_holdout_validate"
    assert stats["self_improvement_rounds_limit"] == 0
    assert len(output["backtest"]["candidates"]) == 3


def test_relative_momentum_rotation_selects_and_keeps_the_strongest_winner() -> None:
    rows = _cross_sectional_rows()
    store = PreparedFeatureStore(rows)
    strategy_ir = StrategyIR(
        strategy_id="automatic_performance_momentum",
        entry_feature="performance_momentum_tournament",
        exit_feature="monthly_rank_or_emergency_stop",
        proxy_feature="past_only_price_factors",
    )
    parameters = CandidateParameters(
        profile="relative_momentum_rotation",
        lookback=252,
        threshold=0.0,
        stop_loss_pct=0.20,
        take_profit_pct=10.0,
        max_positions=1,
    )

    actions = store.build_actions(strategy_ir, parameters)
    first_rotation = {
        store.tickers[index]: actions[index]
        for index, value in enumerate(store.dates)
        if value == (date(2024, 1, 1) + timedelta(days=252)).isoformat()
    }

    assert first_rotation == {"000001": 1, "000002": 0, "000003": 0}
    assert -1 not in actions[253 * 3 : 273 * 3]


def test_relative_momentum_rotation_does_not_read_future_rows() -> None:
    rows = _cross_sectional_rows()
    strategy_ir = StrategyIR(
        strategy_id="automatic_performance_momentum",
        entry_feature="performance_momentum_tournament",
        exit_feature="monthly_rank_or_emergency_stop",
        proxy_feature="past_only_price_factors",
    )
    parameters = CandidateParameters(
        profile="risk_adjusted_momentum_rotation",
        lookback=252,
        threshold=0.0,
        stop_loss_pct=0.20,
        take_profit_pct=10.0,
        max_positions=2,
    )
    prefix_length = 270 * 3

    full_actions = PreparedFeatureStore(rows).build_actions(strategy_ir, parameters)
    prefix_actions = PreparedFeatureStore(rows[:prefix_length]).build_actions(
        strategy_ir,
        parameters,
    )

    assert list(full_actions[:prefix_length]) == list(prefix_actions)


def test_concrete_strategy_is_not_replaced_by_automatic_profile() -> None:
    strategy = build_strategy_spec(
        "자동 추천도 좋지만 RSI가 30 이하일 때 매수하고 70 이상일 때 매도",
        variant="A",
        semantic_slots={},
    )

    assert strategy.selection_mode == "user_defined"
    assert not strategy.strategy_id.startswith("automatic_performance_momentum")
    assert any("rsi" in indicator.casefold() for indicator in strategy.indicators)
    plan = build_code_generation_plan(strategy, map_strategy_features(strategy))
    assert plan.entry_feature == "rsi_rebound"
    assert plan.generated_strategies == []
    explanation = build_strategy_explanation(strategy)
    rsi = next(item for item in explanation["indicators"] if item["key"] == "rsi")
    assert "100 - 100/(1 +" in rsi["formula"]
    assert rsi["derivation"]
