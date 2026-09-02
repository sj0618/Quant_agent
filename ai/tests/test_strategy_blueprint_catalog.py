from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from ai_graph.graph import build_strategy_spec
from ai_graph.nodes.backtest_code import (
    Loop3Request,
    build_code_generation_plan,
    generate_loop3_candidates,
    map_strategy_features,
)
from ai_graph.nodes.backtest import run_candidate_backtest
from ai_graph.nodes.backtest_features import PreparedFeatureStore
from ai_graph.schemas import CandidateParameters, CodeCandidate, StrategyIR
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


def _rich_ohlcv_rows(*, days: int = 520, tickers: int = 16) -> list[dict[str, object]]:
    """Deterministic regimes, gaps, breakouts and volume climaxes for signal QA."""

    rng = np.random.default_rng(20260809)
    start = date(2020, 1, 1)
    rows: list[dict[str, object]] = []
    for ticker_index in range(tickers):
        close = 60.0 + 4.0 * ticker_index
        for day_index in range(days):
            regime = (day_index // 55 + ticker_index) % 4
            drift = [0.002, -0.0015, 0.0002, 0.003][regime]
            shock = float(rng.normal(drift, 0.012 + 0.004 * (ticker_index % 3)))
            if day_index % 73 == 10 + ticker_index % 7:
                shock += 0.09
            if day_index % 89 == 20 + ticker_index % 5:
                shock -= 0.10
            previous_close = close
            gap = float(rng.normal(0.0, 0.009))
            if day_index % 67 == ticker_index % 11:
                gap += 0.045
            if day_index % 71 == (ticker_index + 3) % 13:
                gap -= 0.05
            open_price = previous_close * (1.0 + gap)
            close = max(3.0, open_price * (1.0 + shock - gap * 0.35))
            spread = abs(float(rng.normal(0.018, 0.008)))
            high = max(open_price, close) * (1.0 + spread * 0.55)
            low = min(open_price, close) * (1.0 - spread * 0.45)
            volume = (500_000.0 + 80_000.0 * ticker_index) * (
                1.0 + abs(shock) * 18.0 + float(rng.uniform(0.0, 0.5))
            )
            if day_index % 47 == ticker_index % 9:
                volume *= 3.2
            rows.append(
                {
                    "date": (start + timedelta(days=day_index)).isoformat(),
                    "ticker": f"{ticker_index + 1:06d}",
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
    return sorted(rows, key=lambda row: (str(row["date"]), str(row["ticker"])))


def _strategy_ir(item: StrategyBlueprintTemplate) -> StrategyIR:
    return StrategyIR(
        strategy_id=item.catalog_id,
        entry_feature=f"catalog:{item.catalog_id}:entry",
        exit_feature=f"catalog:{item.catalog_id}:exit",
        proxy_feature="past_only_adjusted_ohlcv",
        entry_conditions=item.entry_conditions,
        exit_conditions=item.exit_conditions,
        ranking_metric=item.ranking_metric,
        ranking_direction=item.ranking_direction,
        execution_mode=item.execution_mode,
    )


def _parameters(item: StrategyBlueprintTemplate) -> CandidateParameters:
    return CandidateParameters(
        profile="compiled_conditions",
        blueprint_id=item.catalog_id,
        **item.default_parameters.model_dump(),
    )


def test_catalog_has_at_least_fifty_independent_execution_formulas() -> None:
    catalog = strategy_blueprint_catalog()

    assert len(catalog) >= 50
    assert len({item.catalog_id for item in catalog}) == len(catalog)
    assert len({item.archetype_id for item in catalog}) == len(catalog)
    assert len({item.execution_signature for item in catalog}) == len(catalog)
    assert len({item.formula for item in catalog}) == len(catalog)
    assert {item.preset_id for item in catalog} == {"canonical"}
    assert all(item.catalog_id.startswith("qb-v2-") for item in catalog)
    assert all(item.catalog_version == CATALOG_VERSION for item in catalog)
    assert all(item.profile == "compiled_conditions" for item in catalog)
    assert all(item.native_execution and item.independent_strategy for item in catalog)


def test_catalog_explains_every_formula_and_indicator_with_sources() -> None:
    for item in strategy_blueprint_catalog():
        assert item.formula and item.derivation and item.why_used and item.plain_explanation
        assert item.entry_conditions and item.exit_conditions and item.ranking_metric
        assert item.caveats and item.required_data == ["adjusted_ohlcv_daily"]
        assert item.indicator_explanations
        assert all(ref.startswith("https://") for ref in item.source_refs)
        for indicator in item.indicator_explanations:
            assert indicator.formula
            assert indicator.derivation
            assert indicator.why_used
            assert indicator.plain_explanation
            assert all(ref.startswith("https://") for ref in indicator.source_refs)
        assert StrategyBlueprintTemplate.model_validate(item.model_dump()) == item


def test_catalog_summary_does_not_count_parameter_presets_as_strategies() -> None:
    summary = strategy_blueprint_catalog_summary()
    count = len(strategy_blueprint_catalog())

    assert summary["count"] == count
    assert summary["independent_strategy_count"] == count
    assert summary["archetype_count"] == count
    assert summary["preset_count"] == 1
    assert summary["parameter_presets_counted_as_strategies"] is False
    assert summary["storage"] == CATALOG_STORAGE == "versioned_python_catalog"
    assert summary["version"] == CATALOG_VERSION
    assert summary["fingerprint"] == strategy_blueprint_catalog_fingerprint()
    assert len(str(summary["fingerprint"])) == 64


def test_core_catalog_indicator_boundaries_match_their_published_formulas() -> None:
    start = date(2024, 1, 1)
    rows = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "ticker": "000001",
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.0 + index,
            "volume": 1_000_000.0,
        }
        for index in range(260)
    ]
    store = PreparedFeatureStore(rows)

    momentum = store._metric_series("momentum_12_1")
    assert np.isnan(momentum[251])
    assert momentum[252] == rows[231]["close"] / rows[0]["close"] - 1.0

    donchian = store._metric_series("donchian_high_20")
    assert np.isnan(donchian[19])
    assert donchian[20] == max(float(row["high"]) for row in rows[:20])

    rsi = store._metric_series("rsi_14")
    assert np.isnan(rsi[13])
    assert rsi[14] == 100.0


def test_selector_maps_specialized_intent_to_the_matching_independent_formula() -> None:
    breakout = select_strategy_blueprints(
        "ATR range expansion breakout",
        risk_style="aggressive",
        horizon="short",
    )
    low_vol = select_strategy_blueprints(
        "low volatility defensive long",
        risk_style="defensive",
        horizon="long",
    )
    rsi = select_strategy_blueprints(
        "RSI oversold rebound",
        risk_style="aggressive",
        horizon="short",
    )
    mixed = select_strategy_blueprints(
        "거래량이 붙는 신고가 돌파 전략",
        risk_style="aggressive",
        horizon="short",
    )

    assert breakout[0].archetype_id == "atr-range-expansion-breakout"
    assert low_vol[0].archetype_id == "pure-low-volatility-trend"
    assert rsi[0].archetype_id == "rsi-oversold-reversion"
    assert {item.archetype_id for item in mixed} >= {
        "gap-up-volume-breakout",
        "fifty-two-week-high-momentum",
    }
    assert len({item.execution_signature for item in breakout}) == 3


def test_user_controls_change_risk_not_formula_identity_or_fixed_windows() -> None:
    template = strategy_blueprint_catalog()[0]
    customized = customize_blueprint_parameters(
        template,
        max_positions=5,
        rebalance_interval_days=10,
        stop_loss_pct=0.25,
        take_profit_pct=10.0,
        trailing_stop_pct=0.30,
        preferred_lookback=3,
    )

    assert customized.max_positions == 5
    assert customized.rebalance_interval_days == 10
    assert customized.stop_loss_pct == 0.25
    assert customized.trailing_stop_pct == 0.30
    assert customized.lookback == template.default_parameters.lookback
    assert customized.threshold == template.default_parameters.threshold
    assert template.parameter_schema["lookback"].user_overridable is False


def test_automatic_plan_sends_three_distinct_catalog_rules_to_backtest() -> None:
    strategy = build_strategy_spec(
        "5종목으로 단기 고수익 집중 모멘텀 전략 만들어줘",
        variant="A",
        semantic_slots={},
    )
    generated = generate_loop3_candidates(
        Loop3Request(
            strategy=strategy,
            variant="A",
            trace_id="independent-catalog-selection",
            max_positions=5,
        )
    )
    plan = build_code_generation_plan(strategy, map_strategy_features(strategy))

    assert plan.catalog_version == CATALOG_VERSION
    assert plan.catalog_size == len(strategy_blueprint_catalog())
    assert plan.catalog_fingerprint == strategy_blueprint_catalog_fingerprint()
    assert len(plan.generated_strategies) == 3
    assert len({item.execution_signature for item in plan.generated_strategies}) == 3
    assert len({item.blueprint_id for item in plan.generated_strategies}) == 3

    by_id = {item.blueprint_id: item for item in generated.code_plan.generated_strategies}
    for candidate in generated.candidates:
        assert candidate.parameters is not None
        assert candidate.strategy_ir is not None
        assert candidate.parameters.max_positions == 5
        blueprint = by_id[candidate.parameters.blueprint_id or ""]
        assert candidate.strategy_ir.strategy_id == blueprint.blueprint_id
        assert candidate.strategy_ir.entry_conditions == blueprint.entry_conditions
        assert candidate.strategy_ir.exit_conditions == blueprint.exit_conditions
        assert candidate.strategy_ir.ranking_metric == blueprint.ranking_metric
        assert candidate.strategy_ir.execution_mode == blueprint.execution_mode


def test_all_catalog_rules_emit_buy_sell_and_never_read_future_rows() -> None:
    rows = _rich_ohlcv_rows()
    prefix_days = 420
    ticker_count = 16
    prefix_length = prefix_days * ticker_count
    full_store = PreparedFeatureStore(rows)
    prefix_store = PreparedFeatureStore(rows[:prefix_length])

    executed: set[str] = set()
    for item in strategy_blueprint_catalog():
        strategy_ir = _strategy_ir(item)
        parameters = _parameters(item)
        full_actions = full_store.build_actions(strategy_ir, parameters)
        prefix_actions = prefix_store.build_actions(strategy_ir, parameters)

        assert list(full_actions[:prefix_length]) == list(prefix_actions), item.catalog_id
        assert set(full_actions) <= {-1, 0, 1}
        assert any(action == 1 for action in full_actions), item.catalog_id
        assert any(action == -1 for action in full_actions), item.catalog_id
        executed.add(item.catalog_id)

    assert len(executed) == len(strategy_blueprint_catalog())


def test_all_catalog_rules_complete_the_real_next_open_backtest_engine() -> None:
    rows = _rich_ohlcv_rows(days=320, tickers=8)
    strategy = build_strategy_spec(
        "검증된 퀀트 전략을 알아서 만들어줘",
        variant="A",
        semantic_slots={},
    )
    candidates = [
        CodeCandidate(
            candidate_id=f"CAT{index:02d}",
            variant="A",
            code="def build_signals(prices):\n    return []\n",
            validation_ok=True,
            representation="structured",
            strategy_ir=_strategy_ir(item),
            parameters=_parameters(item),
        )
        for index, item in enumerate(strategy_blueprint_catalog(), start=1)
    ]

    # This asserts the per-candidate engine path: every catalog rule runs and produces
    # metrics. Rolling walk-forward reports its candidates through fold aggregates
    # instead, and whether these rows meet its sample minimum now depends on the loaded
    # window (see `walk_forward_policy_for`), which is not what this test is about.
    result = run_candidate_backtest(
        strategy, candidates, price_rows=rows, _walk_forward_enabled=False
    )
    completed = [
        candidate
        for candidate in result.candidates
        if candidate.validation_ok and candidate.metrics is not None
    ]

    assert len(completed) == len(strategy_blueprint_catalog())
    assert len(result.engine_summaries_by_candidate) == len(strategy_blueprint_catalog())
    assert all(not candidate.violations for candidate in completed)
    assert result.selected_candidate.parameters is not None
    assert result.selected_candidate.parameters.blueprint_id


def test_native_compiled_engine_applies_the_customized_trailing_stop() -> None:
    start = date(2024, 1, 1)
    closes = [100.0 + index for index in range(21)] + [112.0]
    rows = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "ticker": "000001",
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1_000_000.0,
        }
        for index, close in enumerate(closes)
    ]
    store = PreparedFeatureStore(rows)
    strategy_ir = StrategyIR(
        strategy_id="trailing-stop-proof",
        entry_feature="always_enter",
        exit_feature="risk_only",
        proxy_feature="close",
        entry_conditions=[
            # Starts entering as soon as the first price exists.
            strategy_blueprint_catalog()[0].entry_conditions[1].model_copy(
                update={"left": "close", "operator": "gt", "right": 0.0}
            )
        ],
        exit_conditions=[
            strategy_blueprint_catalog()[0].exit_conditions[0].model_copy(
                update={"left": "close", "operator": "lt", "right": 0.0}
            )
        ],
        ranking_metric="close",
    )

    def actions_for(trailing_stop_pct: float) -> list[int]:
        actions = store.build_actions(
            strategy_ir,
            CandidateParameters(
                profile="compiled_conditions",
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
