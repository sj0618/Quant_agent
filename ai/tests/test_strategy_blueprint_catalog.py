from __future__ import annotations

from datetime import date, timedelta

from ai_graph.graph import build_strategy_spec
from ai_graph.nodes.backtest_code import (
    Loop3Request,
    build_code_generation_plan,
    generate_loop3_candidates,
    map_strategy_features,
)
from ai_graph.nodes.backtest_features import PreparedFeatureStore
from ai_graph.schemas import CandidateParameters, StrategyIR
from ai_graph.strategy_blueprint_catalog import (
    CATALOG_STORAGE,
    CATALOG_VERSION,
    StrategyBlueprintTemplate,
    customize_blueprint_parameters,
    select_strategy_blueprints,
    strategy_blueprint_catalog,
    strategy_blueprint_catalog_fingerprint,
    strategy_blueprint_catalog_summary,
)


def test_catalog_contains_exactly_one_hundred_versioned_blueprints() -> None:
    catalog = strategy_blueprint_catalog()

    assert len(catalog) == 100
    assert len({item.catalog_id for item in catalog}) == 100
    assert len({item.title for item in catalog}) == 100
    assert len({item.archetype_id for item in catalog}) == 20
    assert len({item.preset_id for item in catalog}) == 5
    assert all(item.catalog_version == CATALOG_VERSION for item in catalog)
    assert all(item.native_execution for item in catalog)


def test_catalog_is_self_explaining_source_backed_and_serializable() -> None:
    for item in strategy_blueprint_catalog():
        assert item.formula
        assert item.derivation
        assert item.why_used
        assert item.plain_explanation
        assert item.caveats
        assert item.required_data == ["adjusted_ohlcv_daily"]
        assert set(item.parameter_schema) == {
            "lookback",
            "threshold",
            "max_positions",
            "rebalance_interval_days",
            "stop_loss_pct",
            "take_profit_pct",
            "trailing_stop_pct",
        }
        assert all(ref.startswith("https://") for ref in item.source_refs)
        assert StrategyBlueprintTemplate.model_validate(item.model_dump()) == item


def test_catalog_summary_is_stable_and_database_independent() -> None:
    summary = strategy_blueprint_catalog_summary()

    assert summary["count"] == 100
    assert summary["archetype_count"] == 20
    assert summary["preset_count"] == 5
    assert summary["storage"] == CATALOG_STORAGE == "versioned_python_catalog"
    assert summary["version"] == CATALOG_VERSION
    assert summary["fingerprint"] == strategy_blueprint_catalog_fingerprint()
    assert len(str(summary["fingerprint"])) == 64


def test_selector_uses_specialized_user_terms_without_looking_at_returns() -> None:
    breakout = select_strategy_blueprints(
        "거래량이 붙는 신고가 돌파 전략을 공격적으로 만들어줘",
        risk_style="aggressive",
        horizon="short",
        profile_priority=(
            "trend_leader_rotation",
            "risk_adjusted_momentum_rotation",
            "relative_momentum_rotation",
        ),
    )
    low_vol = select_strategy_blueprints(
        "손실을 줄이는 장기 저변동 방어 전략",
        risk_style="defensive",
        horizon="long",
        profile_priority=(
            "risk_adjusted_momentum_rotation",
            "relative_momentum_rotation",
            "trend_leader_rotation",
        ),
    )

    assert [item.profile for item in breakout[:2]] == [
        "breakout_volume",
        "volatility_breakout_hold",
    ]
    assert low_vol[0].profile == "risk_adjusted_momentum_rotation"
    assert {item.profile for item in low_vol} >= {"risk_adjusted_momentum_rotation"}
    assert all(item.risk_style == "defensive" for item in low_vol)
    assert all(item.investment_horizon == "long" for item in low_vol)


def test_explicit_user_controls_override_only_bounded_parameters() -> None:
    template = strategy_blueprint_catalog()[0]
    customized = customize_blueprint_parameters(
        template,
        max_positions=5,
        rebalance_interval_days=10,
        stop_loss_pct=0.25,
        take_profit_pct=10.0,
        trailing_stop_pct=0.30,
        preferred_lookback=252,
    )

    assert customized.max_positions == 5
    assert customized.rebalance_interval_days == 10
    assert customized.stop_loss_pct == 0.25
    assert customized.take_profit_pct == 10.0
    assert customized.trailing_stop_pct == 0.30
    assert customized.lookback == 252
    assert customized.threshold == template.default_parameters.threshold

    minimums = customize_blueprint_parameters(
        template,
        max_positions=-10,
        rebalance_interval_days=-10,
        stop_loss_pct=-1.0,
        take_profit_pct=-1.0,
        trailing_stop_pct=-1.0,
        preferred_lookback=-10,
    )
    assert minimums.lookback == int(template.parameter_schema["lookback"].minimum)
    assert minimums.max_positions == int(template.parameter_schema["max_positions"].minimum)
    assert minimums.rebalance_interval_days == int(
        template.parameter_schema["rebalance_interval_days"].minimum
    )
    assert minimums.stop_loss_pct == template.parameter_schema["stop_loss_pct"].minimum
    assert minimums.take_profit_pct == template.parameter_schema["take_profit_pct"].minimum
    assert minimums.trailing_stop_pct == template.parameter_schema["trailing_stop_pct"].minimum


def test_automatic_plan_selects_three_of_one_hundred_before_backtest() -> None:
    strategy = build_strategy_spec(
        "5종목으로 단기 고수익 집중 모멘텀 전략 만들어줘",
        variant="A",
        semantic_slots={},
    )
    plan = build_code_generation_plan(strategy, map_strategy_features(strategy))
    candidates = generate_loop3_candidates(
        Loop3Request(
            strategy=strategy,
            variant="A",
            trace_id="catalog-100-selection",
            max_positions=5,
        )
    ).candidates

    assert plan.catalog_version == CATALOG_VERSION
    assert plan.catalog_size == 100
    assert plan.catalog_fingerprint == strategy_blueprint_catalog_fingerprint()
    assert len(plan.generated_strategies) == 3
    assert all(item.blueprint_id.startswith("qb-v1-") for item in plan.generated_strategies)
    assert all(
        item.parameter_schema and item.source_refs and item.why_used
        for item in plan.generated_strategies
    )
    assert [candidate.parameters.lookback for candidate in candidates if candidate.parameters] == [
        item.lookback for item in plan.generated_strategies
    ]
    assert [candidate.parameters.threshold for candidate in candidates if candidate.parameters] == [
        item.threshold for item in plan.generated_strategies
    ]
    assert all(
        candidate.parameters is not None
        and candidate.parameters.max_positions == 5
        and candidate.parameters.rebalance_interval_days == 10
        for candidate in candidates
    )


def test_all_one_hundred_blueprints_convert_to_native_executable_signals() -> None:
    start = date(2024, 1, 1)
    growth_by_ticker = {"000001": 1.003, "000002": 1.001, "000003": 0.999}
    rows = [
        {
            "date": (start + timedelta(days=day_index)).isoformat(),
            "ticker": ticker,
            "close": 100.0 * (growth**day_index),
            "volume": 1_000_000.0 * (1.0 + (day_index % 7) * 0.05),
            "rsi": 35.0 + float(day_index % 35),
        }
        for day_index in range(270)
        for ticker, growth in growth_by_ticker.items()
    ]
    store = PreparedFeatureStore(rows)
    strategy_ir = StrategyIR(
        strategy_id="catalog_native_execution",
        entry_feature="catalog_profile",
        exit_feature="catalog_profile_or_risk_exit",
        proxy_feature="past_only_ohlcv",
    )

    executed_ids: set[str] = set()
    for item in strategy_blueprint_catalog():
        parameters = CandidateParameters(
            profile=item.profile,
            **item.default_parameters.model_dump(),
        )
        actions = store.build_actions(strategy_ir, parameters)

        assert len(actions) == len(rows)
        assert set(actions) <= {-1, 0, 1}
        executed_ids.add(item.catalog_id)

    assert len(executed_ids) == 100


def test_native_engine_uses_the_customized_trailing_stop() -> None:
    start = date(2024, 1, 1)
    closes = [100.0 + index for index in range(21)] + [112.0]
    rows = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "ticker": "000001",
            "close": close,
            "volume": 1_000_000.0,
            "rsi": 50.0,
        }
        for index, close in enumerate(closes)
    ]
    store = PreparedFeatureStore(rows)
    strategy_ir = StrategyIR(
        strategy_id="catalog_trailing_stop",
        entry_feature="catalog_profile",
        exit_feature="catalog_profile_or_risk_exit",
        proxy_feature="past_only_ohlcv",
    )

    def actions_for(trailing_stop_pct: float) -> list[int]:
        actions = store.build_actions(
            strategy_ir,
            CandidateParameters(
                profile="low_vol_momentum",
                lookback=20,
                threshold=0.0,
                stop_loss_pct=0.50,
                take_profit_pct=10.0,
                max_positions=1,
                trailing_stop_pct=trailing_stop_pct,
            ),
        )
        return list(actions)

    assert actions_for(0.05)[-1] == -1
    assert actions_for(0.15)[-1] == 0
