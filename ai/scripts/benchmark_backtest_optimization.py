from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
import json
import os
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time

import psutil

from ai_graph.nodes.backtest import run_candidate_backtest
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.schemas import Condition, ConditionOperator, StrategySpec


def _strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="benchmark-rsi-volume",
        name="Benchmark RSI Volume",
        market="KRX",
        timeframe="daily",
        entry_conditions=[
            Condition(left="rsi", operator=ConditionOperator.LTE, right=40.0)
        ],
        exit_conditions=[
            Condition(left="rsi", operator=ConditionOperator.GTE, right=70.0)
        ],
        indicators=["rsi", "volume"],
        risk_constraints={
            "max_position_pct": 0.1,
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.3,
        },
        confidence=0.9,
    )


def _rows(ticker_count: int, trading_days: int) -> list[dict[str, object]]:
    start = date(2016, 1, 4)
    rows: list[dict[str, object]] = []
    for day_index in range(trading_days):
        row_date = (start + timedelta(days=day_index)).isoformat()
        for ticker_index in range(ticker_count):
            drift = day_index * (0.003 + (ticker_index % 11) * 0.0004)
            cycle = ((day_index + ticker_index) % 23 - 11) * 0.07
            close = 50.0 + ticker_index * 0.5 + drift + cycle
            rows.append(
                {
                    "date": row_date,
                    "ticker": f"{ticker_index + 1:06d}",
                    "open": close * 0.998,
                    "high": close * 1.012,
                    "low": close * 0.988,
                    "close": close,
                    "volume": 500_000.0
                    + ticker_index * 2_000.0
                    + day_index * 100.0
                    + (200_000.0 if day_index % 29 == 0 else 0.0),
                    "rsi": 25.0 + float((day_index + ticker_index * 3) % 60),
                }
            )
    return rows


def _canonical_hash(result) -> str:
    payload = {
        "selected_candidate": result.selected_candidate.model_dump(mode="json"),
        "equity_curve": [
            point.model_dump(mode="json") for point in result.equity_curve
        ],
        "engine_summary": result.engine_summary,
        "objective_scores": result.objective_scores_by_candidate,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


class _ProcessTreeSampler:
    def __init__(self) -> None:
        self.stop_event = Event()
        self.peak_rss = 0
        self.cpu_samples: list[float] = []
        self.thread = Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run(self) -> None:
        root = psutil.Process()
        known: dict[int, psutil.Process] = {}
        while not self.stop_event.wait(0.1):
            processes = [root, *root.children(recursive=True)]
            rss = 0
            cpu = 0.0
            for process in processes:
                try:
                    rss += int(process.memory_info().rss)
                    if process.pid not in known:
                        process.cpu_percent(None)
                        known[process.pid] = process
                    else:
                        cpu += process.cpu_percent(None)
                except psutil.Error:
                    continue
            self.peak_rss = max(self.peak_rss, rss)
            self.cpu_samples.append(cpu)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", type=int, required=True)
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2), required=True)
    parser.add_argument("--candidates", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--repeat-cache", action="store_true")
    args = parser.parse_args()

    strategy = _strategy()
    rows = _rows(args.tickers, args.days)
    generated = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="benchmark")
    )
    candidates = generated.candidates[: args.candidates]
    os.environ["AI_BACKTEST_WORKERS"] = str(args.workers)
    with TemporaryDirectory(prefix="quantagent-benchmark-cache-") as cache_dir:
        os.environ["AI_BACKTEST_CACHE_DIR"] = cache_dir
        sampler = _ProcessTreeSampler()
        sampler.start()
        started = time.perf_counter()
        result = run_candidate_backtest(strategy, candidates, price_rows=rows)
        wall_seconds = time.perf_counter() - started
        cached_result = None
        cached_wall_seconds = None
        if args.repeat_cache:
            cached_started = time.perf_counter()
            cached_result = run_candidate_backtest(
                strategy,
                candidates,
                price_rows=rows,
            )
            cached_wall_seconds = time.perf_counter() - cached_started
        sampler.stop()

    output = {
        "tickers": args.tickers,
        "trading_days": args.days,
        "rows": len(rows),
        "workers": args.workers,
        "candidates": len(candidates),
        "wall_seconds": round(wall_seconds, 6),
        "peak_process_tree_rss_bytes": sampler.peak_rss,
        "average_process_tree_cpu_percent": round(
            sum(sampler.cpu_samples) / len(sampler.cpu_samples), 3
        )
        if sampler.cpu_samples
        else 0.0,
        "max_process_tree_cpu_percent": round(
            max(sampler.cpu_samples), 3
        )
        if sampler.cpu_samples
        else 0.0,
        "selected_candidate": result.selected_candidate.candidate_id,
        "canonical_sha256": _canonical_hash(result),
        "execution_stats": result.execution_stats,
    }
    if cached_result is not None:
        output.update(
            {
                "cached_wall_seconds": round(float(cached_wall_seconds), 6),
                "cached_canonical_sha256": _canonical_hash(cached_result),
                "cached_execution_stats": cached_result.execution_stats,
            }
        )
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
