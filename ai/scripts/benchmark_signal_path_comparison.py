from __future__ import annotations

import argparse
from array import array
import gc
from hashlib import sha256
import json
import time

import psutil

from ai_graph.nodes.backtest_code import (
    _render_adaptive_signal_code,
    build_code_generation_plan,
    generate_loop3_candidates,
    Loop3Request,
    map_strategy_features,
)
from ai_graph.nodes.backtest_features import PreparedFeatureStore
from ai_graph.schemas import CandidateParameters
from benchmark_backtest_optimization import _rows, _strategy


PROFILES = (
    "rsi_trend_rebound",
    "mean_reversion_band",
    "quality_trend_hold",
)
LOOKBACKS = (20, 30, 40)
THRESHOLDS = (0.05, 0.08, 0.1)
ACTION_VALUES = {"BUY": 1, "SELL": -1, "HOLD": 0}


def _parameters(profile: str, lookback: int, threshold: float) -> CandidateParameters:
    return CandidateParameters(
        profile=profile,  # type: ignore[arg-type]
        lookback=lookback,
        threshold=threshold,
        stop_loss_pct=0.08,
        take_profit_pct=0.3,
        max_positions=10,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("legacy", "structured"), required=True)
    parser.add_argument("--tickers", type=int, required=True)
    parser.add_argument("--days", type=int, required=True)
    args = parser.parse_args()

    strategy = _strategy()
    rows = _rows(args.tickers, args.days)
    process = psutil.Process()
    rss_before = process.memory_info().rss
    hashes: list[bytes] = []
    started = time.perf_counter()

    if args.mode == "legacy":
        plan = build_code_generation_plan(strategy, map_strategy_features(strategy))
        for profile, lookback, threshold in zip(
            PROFILES, LOOKBACKS, THRESHOLDS, strict=True
        ):
            namespace: dict[str, object] = {}
            exec(
                _render_adaptive_signal_code(
                    strategy_id=strategy.strategy_id,
                    plan=plan,
                    profile=profile,
                    lookback=lookback,
                    threshold=threshold,
                    stop_loss=0.08,
                    take_profit=0.3,
                    max_positions=10,
                ),
                namespace,
            )
            signals = namespace["build_signals"](rows)  # type: ignore[operator]
            actions = array(
                "b",
                (ACTION_VALUES[str(signal["action"])] for signal in signals),
            )
            hashes.append(actions.tobytes())
            del actions, signals, namespace
            gc.collect()
    else:
        generated = generate_loop3_candidates(
            Loop3Request(strategy=strategy, variant="A", trace_id="path-benchmark")
        )
        store = PreparedFeatureStore(rows)
        for profile, lookback, threshold in zip(
            PROFILES, LOOKBACKS, THRESHOLDS, strict=True
        ):
            actions = store.build_actions(
                generated.strategy_ir,
                _parameters(profile, lookback, threshold),
            )
            hashes.append(actions.tobytes())

    wall_seconds = time.perf_counter() - started
    rss_after = process.memory_info().rss
    digest = sha256(b"".join(hashes)).hexdigest()
    print(
        json.dumps(
            {
                "mode": args.mode,
                "tickers": args.tickers,
                "trading_days": args.days,
                "rows": len(rows),
                "candidates": len(PROFILES),
                "wall_seconds": round(wall_seconds, 6),
                "rss_before_bytes": rss_before,
                "rss_after_bytes": rss_after,
                "rss_delta_bytes": rss_after - rss_before,
                "action_sha256": digest,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
