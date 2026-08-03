from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
import time
from typing import Any

from ai_graph.audit import RecordingAuditSession, create_audit_correlation
from ai_graph.graph import build_graph
from ai_graph.schemas import APIEnvelope


DEFAULT_QUERY = (
    "Screen the KOSPI200 universe and backtest RSI <= 30 entries with "
    "RSI >= 70 exits over the full recommended period."
)


def _node_results(session: RecordingAuditSession) -> list[dict[str, Any]]:
    records = sorted(session.agent_executions, key=lambda item: item.started_at)
    return [
        {
            "name": record.agent_name,
            "status": record.status,
            "seconds": (
                round(float(record.latency_ms) / 1000.0, 6)
                if record.latency_ms is not None
                else None
            ),
        }
        for record in records
    ]


def _model_results(session: RecordingAuditSession) -> list[dict[str, Any]]:
    execution_names = {
        record.execution_id: record.agent_name
        for record in session.agent_executions
    }
    prompts = {record.call_id: record for record in session.prompt_logs}
    records = sorted(session.model_calls, key=lambda item: item.created_at)
    results: list[dict[str, Any]] = []
    for record in records:
        prompt = prompts.get(record.call_id)
        results.append(
            {
                "node": execution_names.get(record.execution_id),
                "task_type": record.task_type,
                "status": record.status,
                "model": record.model_name,
                "web_search": record.web_search_used,
                "seconds": (
                    round(float(record.latency_ms) / 1000.0, 6)
                    if record.latency_ms is not None
                    else None
                ),
                "prompt_tokens": record.prompt_tokens,
                "completion_tokens": record.completion_tokens,
                "total_tokens": record.total_tokens,
                "retry_count": record.retry_count,
                "error_message": record.error_message,
                "system_prompt_chars": (
                    len(prompt.system_prompt) if prompt is not None else None
                ),
                "user_prompt_chars": (
                    len(prompt.user_prompt) if prompt is not None else None
                ),
            }
        )
    return results


def _backtest_results(backtest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if backtest is None:
        return None
    execution = backtest.get("execution_stats") or {}
    candidates = execution.get("candidates") or {}
    return {
        "feature_preparation_seconds": execution.get(
            "feature_preparation_seconds"
        ),
        "feature_preparation_phases": execution.get("feature_preparation_phases") or {},
        "prepared_market_cache_hit": execution.get("prepared_market_cache_hit"),
        "total_backtest_wall_seconds": execution.get(
            "total_backtest_wall_seconds"
        ),
        "cache_hits": execution.get("cache_hits"),
        "cache_misses": execution.get("cache_misses"),
        "rounds": execution.get("rounds") or [],
        "candidates": {
            candidate_id: {
                key: detail.get(key)
                for key in (
                    "metrics_mode",
                    "wall_seconds",
                    "cpu_seconds",
                    "cache_hit",
                    "cache_level",
                    "error_type",
                    "timeout_seconds",
                )
                if key in detail
            }
            for candidate_id, detail in candidates.items()
            if isinstance(detail, dict)
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--max-wall-seconds", type=float, default=1200.0)
    args = parser.parse_args()

    if os.environ.get("AI_LLM_PROVIDER", "").strip().lower() != "aoai":
        raise RuntimeError("full live benchmark requires AI_LLM_PROVIDER=aoai")
    if os.environ.get("AI_AOAI_LIVE_TEST") != "1":
        raise RuntimeError("full live benchmark requires AI_AOAI_LIVE_TEST=1")

    trace_id = f"live-aoai-full-{time.time_ns()}"
    correlation = create_audit_correlation(
        trace_id=trace_id,
        debug_ref=f"debug:{trace_id}",
        entrypoint="benchmark_live_aoai_full_analysis",
        feature="live_aoai_full_analysis",
    )
    session = RecordingAuditSession(correlation)
    started = time.perf_counter()
    error: Exception | None = None
    envelope = None
    state: Mapping[str, Any] | None = None
    try:
        state = build_graph(audit_session=session).invoke(
            {"user_query": args.query, "trace_id": trace_id}
        )
        envelope = APIEnvelope.model_validate(state["envelope"])
    except Exception as exc:
        error = exc
    wall_seconds = time.perf_counter() - started

    model_results = _model_results(session)
    output = {
        "provider": "aoai",
        "status": "failed" if error is not None else "completed",
        "envelope_status": (
            envelope.status.value if envelope is not None else None
        ),
        "wall_seconds": round(wall_seconds, 6),
        "nodes": _node_results(session),
        "model_calls": model_results,
        "model_call_count": len(model_results),
        "model_call_seconds": round(
            sum(
                float(item["seconds"])
                for item in model_results
                if item["seconds"] is not None
            ),
            6,
        ),
        "backtest": _backtest_results(
            state.get("backtest") if state is not None else None
        ),
        "error_type": type(error).__name__ if error is not None else None,
        "error_message": str(error)[:240] if error is not None else None,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True), flush=True)

    if error is not None:
        return 1
    return 0 if wall_seconds <= args.max_wall_seconds else 2


if __name__ == "__main__":
    raise SystemExit(main())
