from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time

try:
    import psutil
except ModuleNotFoundError:  # Production keeps benchmark-only dependencies optional.
    psutil = None

from ai_graph.data_sources import load_pipeline_data_from_env
from ai_graph.llm.factory import create_llm_client
from ai_graph.nodes.backtest import run_candidate_backtest
from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates
from ai_graph.schemas import Condition, ConditionOperator, StrategySpec


DEFAULT_QUERY = (
    "Screen the KOSPI200 universe and backtest RSI <= 30 entries with "
    "RSI >= 70 exits over the full recommended period."
)


def _strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="production-rsi-30-70",
        name="Production RSI 30/70",
        market="KRX",
        timeframe="daily",
        entry_conditions=[
            Condition(left="rsi", operator=ConditionOperator.LTE, right=30.0)
        ],
        exit_conditions=[
            Condition(left="rsi", operator=ConditionOperator.GTE, right=70.0)
        ],
        indicators=["rsi", "close", "volume"],
        risk_constraints={
            "max_position_pct": 0.05,
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.30,
        },
        confidence=0.9,
    )


def _canonical_hash(result: object) -> str:
    selected = result.selected_candidate
    payload = {
        "selected_candidate": selected.model_dump(mode="json"),
        "equity_curve": [
            point.model_dump(mode="json") for point in result.equity_curve
        ],
        "engine_summary": result.engine_summary,
        "objective_scores": result.objective_scores_by_candidate,
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
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
        if psutil is None:
            self._run_procfs()
            return

        root = psutil.Process()
        known: dict[int, object] = {}
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

    @staticmethod
    def _procfs_snapshot(root_pid: int) -> tuple[int, int]:
        entries: dict[int, tuple[int, int, int]] = {}
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        for proc_dir in Path("/proc").iterdir():
            if not proc_dir.name.isdigit():
                continue
            try:
                stat = (proc_dir / "stat").read_text(encoding="utf-8")
                tail = stat.rsplit(")", 1)[1].strip().split()
                statm = (proc_dir / "statm").read_text(encoding="utf-8").split()
                entries[int(proc_dir.name)] = (
                    int(tail[1]),
                    int(statm[1]) * page_size,
                    int(tail[11]) + int(tail[12]),
                )
            except (OSError, IndexError, ValueError):
                continue

        descendants = {root_pid}
        changed = True
        while changed:
            changed = False
            for pid, (parent_pid, _, _) in entries.items():
                if parent_pid in descendants and pid not in descendants:
                    descendants.add(pid)
                    changed = True
        rss = sum(entries[pid][1] for pid in descendants if pid in entries)
        cpu_ticks = sum(entries[pid][2] for pid in descendants if pid in entries)
        return rss, cpu_ticks

    def _run_procfs(self) -> None:
        if not Path("/proc").is_dir():
            return
        root_pid = os.getpid()
        clock_ticks = float(os.sysconf("SC_CLK_TCK"))
        previous_ticks: int | None = None
        previous_time = time.perf_counter()
        while not self.stop_event.wait(0.1):
            rss, cpu_ticks = self._procfs_snapshot(root_pid)
            sampled_at = time.perf_counter()
            cpu = 0.0
            if previous_ticks is not None and sampled_at > previous_time:
                cpu = (
                    (cpu_ticks - previous_ticks)
                    / clock_ticks
                    / (sampled_at - previous_time)
                    * 100.0
                )
            previous_ticks = cpu_ticks
            previous_time = sampled_at
            self.peak_rss = max(self.peak_rss, rss)
            self.cpu_samples.append(max(cpu, 0.0))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--max-wall-seconds", type=float, default=600.0)
    parser.add_argument("--repeat-cache", action="store_true")
    parser.add_argument(
        "--llm-provider",
        choices=("mock", "aoai"),
        default="mock",
    )
    args = parser.parse_args()

    os.environ["AI_LLM_PROVIDER"] = args.llm_provider
    if args.llm_provider == "aoai":
        if os.environ.get("AI_AOAI_LIVE_TEST") != "1":
            raise RuntimeError(
                "live AOAI benchmark requires AI_AOAI_LIVE_TEST=1"
            )
        llm_client = create_llm_client(role="BACKTEST_CODE")
    else:
        # Keep deterministic engine-only benchmarking available to operators, but
        # require an explicit live mode for end-to-end AOAI measurements.
        from ai_graph.llm.mock import MockLLMClient

        llm_client = MockLLMClient()

    load_started = time.perf_counter()
    bundle = load_pipeline_data_from_env(
        args.query,
        trace_id=f"production-backtest-benchmark-{time.time_ns()}",
    )
    data_load_seconds = time.perf_counter() - load_started
    rows = bundle.price_rows
    if not rows:
        raise RuntimeError("production data source returned no price rows")

    strategy = _strategy()
    generated = generate_loop3_candidates(
        Loop3Request(
            strategy=strategy,
            variant="A",
            trace_id="production-backtest-benchmark",
        ),
        llm_client=llm_client,
    )

    sampler = _ProcessTreeSampler()
    sampler.start()
    with TemporaryDirectory(prefix="quantagent-production-backtest-") as cache_dir:
        os.environ["AI_BACKTEST_CACHE_DIR"] = cache_dir
        started = time.perf_counter()
        result = run_candidate_backtest(
            strategy,
            generated.candidates,
            price_rows=rows,
        )
        wall_seconds = time.perf_counter() - started
        cached_result = None
        cached_wall_seconds = None
        if args.repeat_cache:
            cached_started = time.perf_counter()
            cached_result = run_candidate_backtest(
                strategy,
                generated.candidates,
                price_rows=rows,
            )
            cached_wall_seconds = time.perf_counter() - cached_started
    sampler.stop()

    tickers = sorted({str(row.get("ticker") or "") for row in rows})
    dates = sorted(str(row.get("date") or "") for row in rows)
    metrics = result.selected_candidate.metrics
    output: dict[str, object] = {
        "status": "completed",
        "llm_provider": args.llm_provider,
        "data_source": bundle.metadata.get("source"),
        "data_timings": bundle.metadata.get("timings", {}),
        "data_load_seconds": round(data_load_seconds, 6),
        "rows": len(rows),
        "tickers": len(tickers),
        "date_from": dates[0] if dates else None,
        "date_to": dates[-1] if dates else None,
        "workers": int(os.environ.get("AI_BACKTEST_WORKERS", "2")),
        "candidates": len(generated.candidates),
        "wall_seconds": round(wall_seconds, 6),
        "peak_process_tree_rss_bytes": sampler.peak_rss,
        "average_process_tree_cpu_percent": (
            round(sum(sampler.cpu_samples) / len(sampler.cpu_samples), 3)
            if sampler.cpu_samples
            else 0.0
        ),
        "max_process_tree_cpu_percent": (
            round(max(sampler.cpu_samples), 3) if sampler.cpu_samples else 0.0
        ),
        "selected_candidate": result.selected_candidate.candidate_id,
        "metrics": metrics.model_dump(mode="json") if metrics is not None else None,
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
    print(json.dumps(output, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if wall_seconds <= args.max_wall_seconds else 2


if __name__ == "__main__":
    raise SystemExit(main())
