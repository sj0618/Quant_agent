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
    build_strategy_explanation,
    classify_strategy_request,
    compute_academic_factor_arrays,
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
    assert envelope.strategy_spec.strategy_id.startswith("automatic_robust_tournament")
    assert envelope.rule_provenance is not None
    assert envelope.rule_provenance.substituted is False


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
    assert strategy.strategy_id.startswith("automatic_robust_tournament")
    assert AQR_TREND_SOURCE in strategy.source_refs
    assert KEN_FRENCH_MOMENTUM_SOURCE in strategy.source_refs
    assert BACKTEST_OVERFITTING_SOURCE in strategy.source_refs
    plan = build_code_generation_plan(strategy, map_strategy_features(strategy))
    assert plan.entry_feature == "robust_strategy_tournament"
    assert tuple(_candidate_profiles(plan)) == AUTOMATIC_TOURNAMENT_PROFILES
    candidates = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="robust-tournament-contract")
    ).candidates
    assert (
        tuple(
            candidate.parameters.profile
            for candidate in candidates
            if candidate.parameters is not None
        )
        == AUTOMATIC_TOURNAMENT_PROFILES
    )
    assert [candidate.parameters.lookback for candidate in candidates if candidate.parameters] == [
        252,
        200,
        126,
    ]
    assert [candidate.parameters.threshold for candidate in candidates if candidate.parameters] == [
        0.0,
        0.0,
        0.03,
    ]

    explanation = build_strategy_explanation(strategy)
    assert explanation["selection_mode"] == "automatic"
    assert "미래 수익을 보장하지 않습니다" in explanation["caution"]
    assert {item["key"] for item in explanation["indicators"]} == {
        "strategy_tournament",
        "momentum_12_1",
        "dual_sma_trend",
        "price_range_volatility",
    }


def test_original_vague_request_survives_a_concrete_interpreter_rewrite() -> None:
    strategy = build_strategy_spec(
        "RSI가 30 이하일 때 매수하고 70 이상이면 매도",
        original_query="대충 좋은 걸로 돈 좀 벌게 해봐",
        variant="A",
        semantic_slots={},
    )

    assert strategy.selection_mode == "automatic"
    assert strategy.strategy_id.startswith("automatic_robust_tournament")
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
    assert envelope.rule_provenance.evaluated_rule in {
        f"automatic_profile:{profile}" for profile in AUTOMATIC_TOURNAMENT_PROFILES
    }
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
    assert stats["selection_policy"] == "pre_registered_three_family_holdout"
    assert stats["self_improvement_rounds_limit"] == 0
    assert len(output["backtest"]["candidates"]) == 3


def test_concrete_strategy_is_not_replaced_by_automatic_profile() -> None:
    strategy = build_strategy_spec(
        "자동 추천도 좋지만 RSI가 30 이하일 때 매수하고 70 이상일 때 매도",
        variant="A",
        semantic_slots={},
    )

    assert strategy.selection_mode == "user_defined"
    assert not strategy.strategy_id.startswith("automatic_robust_tournament")
    assert any("rsi" in indicator.casefold() for indicator in strategy.indicators)
