#!/usr/bin/env python3
"""Backtest the fundamental-factor / multi-factor blueprint rows on real warehouse data.

This is a read-only operator benchmark: it loads point-in-time KRX prices + DART
fundamentals through the production ``load_pipeline_data_from_env`` path and runs each of
the newly added blueprint rows (families value_quality / quality / defensive_quality /
quality_momentum / garp / multi_factor) INDEPENDENTLY through the same walk-forward engine
the product uses, so the numbers are out-of-sample.  It writes nothing to the database or
the app tree; it only prints a JSON report to stdout.

No LLM is involved: the blueprints are pre-defined, so candidates are built directly from
the catalog rather than generated.  Run on a host where the warehouse DSN is configured
(AI_DATABASE_DSN / QUANT_DB_DSN / DATABASE_URL), e.g. the deployed server:

    ai/.venv/bin/python ai/scripts/benchmark_new_fundamental_strategies.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from ai_graph.data_sources import load_pipeline_data_from_env
from ai_graph.graph import build_strategy_spec
from ai_graph.nodes.backtest import run_candidate_backtest
from ai_graph.schemas import CandidateParameters, CodeCandidate, StrategyIR
from ai_graph.strategy_blueprint_catalog import strategy_blueprint_catalog

# The families added on top of the price-only technical catalog.
FUNDAMENTAL_FAMILIES = {
    "value_quality",
    "quality",
    "defensive_quality",
    "quality_momentum",
    "garp",
    "multi_factor",
}

# A neutral request so the loader selects its standard point-in-time common-stock
# universe/window rather than a sector- or size-restricted one.  Overridable with --query.
DEFAULT_QUERY = "코스피 코스닥 보통주 대상 장기 퀀트 전략 백테스트"


def _strategy_ir(item) -> StrategyIR:
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


def _parameters(item) -> CandidateParameters:
    return CandidateParameters(
        profile="compiled_conditions",
        blueprint_id=item.catalog_id,
        **item.default_parameters.model_dump(),
    )


def _candidate(index: int, item) -> CodeCandidate:
    return CodeCandidate(
        candidate_id=f"FUND{index:02d}",
        variant="A",
        code="def build_signals(prices):\n    return []\n",
        validation_ok=True,
        representation="structured",
        strategy_ir=_strategy_ir(item),
        parameters=_parameters(item),
    )


def _trade_facts(summary: dict) -> dict:
    keys = (
        "trade_count",
        "total_trades",
        "buy_count",
        "sell_count",
        "closed_trades",
        "final_positions",
        "held_positions",
        "average_positions",
    )
    return {key: summary[key] for key in keys if key in summary}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument(
        "--no-walk-forward",
        action="store_true",
        help="Run the single-pass engine instead of rolling walk-forward (faster, in-sample).",
    )
    args = parser.parse_args()

    load_started = time.perf_counter()
    bundle = load_pipeline_data_from_env(
        args.query,
        trace_id=f"fundamental-strategy-benchmark-{time.time_ns()}",
        requires_financials=True,
    )
    load_seconds = time.perf_counter() - load_started
    rows = bundle.price_rows
    if not rows:
        print(json.dumps({"status": "error", "reason": "no price rows"}, ensure_ascii=False))
        return 1

    tickers = sorted({str(row.get("ticker") or "") for row in rows})
    dates = sorted(str(row.get("date") or "") for row in rows)
    # Confirm fundamentals actually reached the bars (else every rule silently no-matches).
    fundamental_coverage = {
        metric: sum(1 for row in rows if isinstance(row.get(metric), (int, float)))
        for metric in ("per", "roe", "operating_margin", "debt_to_equity", "operating_income_up_streak")
    }

    strategy = build_strategy_spec(args.query, variant="A", semantic_slots={})
    new_rows = [item for item in strategy_blueprint_catalog() if item.family in FUNDAMENTAL_FAMILIES]

    results = []
    for index, item in enumerate(new_rows, start=1):
        candidate = _candidate(index, item)
        started = time.perf_counter()
        try:
            result = run_candidate_backtest(
                strategy,
                [candidate],
                price_rows=rows,
                _walk_forward_enabled=not args.no_walk_forward,
            )
            done = result.candidates[0]
            metrics = done.metrics.model_dump() if done.metrics is not None else None
            summary = result.engine_summaries_by_candidate.get(candidate.candidate_id, {})
            results.append(
                {
                    "strategy_id": item.catalog_id,
                    "title": item.title,
                    "family": item.family,
                    "risk_style": item.risk_style,
                    "horizon": item.investment_horizon,
                    "validation_ok": done.validation_ok,
                    "violations": list(done.violations),
                    "metrics": metrics,
                    "trades": _trade_facts(summary),
                    "wall_seconds": round(time.perf_counter() - started, 2),
                }
            )
        except Exception as exc:  # noqa: BLE001 - report the failure, keep going
            results.append(
                {
                    "strategy_id": item.catalog_id,
                    "title": item.title,
                    "family": item.family,
                    "error": f"{type(exc).__name__}: {exc}",
                    "wall_seconds": round(time.perf_counter() - started, 2),
                }
            )

    report = {
        "status": "completed",
        "walk_forward": not args.no_walk_forward,
        "query": args.query,
        "data_source": bundle.metadata.get("source"),
        "load_seconds": round(load_seconds, 2),
        "rows": len(rows),
        "tickers": len(tickers),
        "date_from": dates[0] if dates else None,
        "date_to": dates[-1] if dates else None,
        "fundamental_coverage_rows": fundamental_coverage,
        "strategies_tested": len(new_rows),
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
