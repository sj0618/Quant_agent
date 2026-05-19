from __future__ import annotations

from ai_graph.schemas import ABBacktestResult, BacktestMetrics, CodeCandidate, StrategySpec


def run_ab_backtest(
    strategy_a: StrategySpec,
    strategy_b: StrategySpec,
    candidates: list[CodeCandidate],
) -> ABBacktestResult:
    if not candidates:
        raise ValueError("at least one candidate is required")
    selected = max(
        [candidate for candidate in candidates if candidate.validation_ok],
        key=lambda candidate: candidate.metrics.sharpe_ratio,  # type: ignore[union-attr]
    )
    metrics_by_variant: dict[str, BacktestMetrics] = {}
    for variant in ("A", "B"):
        variant_candidates = [candidate for candidate in candidates if candidate.variant == variant]
        best = max(variant_candidates, key=lambda candidate: candidate.metrics.sharpe_ratio)  # type: ignore[union-attr]
        metrics_by_variant[variant] = best.metrics  # type: ignore[assignment]
    return ABBacktestResult(
        strategy_a=strategy_a,
        strategy_b=strategy_b,
        candidates=candidates,
        selected_candidate=selected,
        metrics_by_variant=metrics_by_variant,
    )


def backtest_node(state: dict) -> dict:
    strategy_a = StrategySpec.model_validate(state["strategy_spec"])
    strategy_b = StrategySpec.model_validate(state.get("improved_strategy_spec") or state["strategy_spec"])
    candidates = [
        CodeCandidate.model_validate(candidate)
        for candidate in state["backtest_code"]["candidates"]
    ]
    result = run_ab_backtest(strategy_a, strategy_b, candidates)
    return {"backtest": result.model_dump()}
