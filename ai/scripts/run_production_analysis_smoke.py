from __future__ import annotations

import argparse
import json
import time
from uuid import uuid4

from ai_graph.graph import run_analysis
from ai_graph.research_eligibility import PerformanceAvailable, PerformanceUnavailable

DEFAULT_QUERY = (
    "KOSPI200 종목 중 RSI가 30 이하이면 매수하고 70 이상이면 매도하는 "
    "일봉 전략을 전체 추천 기간 데이터로 분석해줘"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--max-wall-seconds", type=float, default=600.0)
    args = parser.parse_args()

    started = time.perf_counter()
    envelope = run_analysis(
        args.query,
        trace_id=f"production-backtest-smoke-{uuid4().hex[:12]}",
        audit_entrypoint="workflow.production_backtest_smoke",
        audit_feature="production_backtest_smoke",
    )
    wall_seconds = time.perf_counter() - started
    performance = envelope.user_payload.performance
    output: dict[str, object] = {
        "status": envelope.status.value,
        "trace_id": envelope.trace_id,
        "wall_seconds": round(wall_seconds, 6),
        "strategy_id": (
            envelope.strategy_spec.strategy_id
            if envelope.strategy_spec is not None
            else None
        ),
        "performance_availability": performance.availability if performance is not None else None,
        "selected_candidate_id": (
            performance.performance.get("selected_candidate_id")
            if isinstance(performance, PerformanceAvailable)
            else None
        ),
        "metrics": (
            performance.performance.get("metrics")
            if isinstance(performance, PerformanceAvailable)
            else None
        ),
        "trade_count": (
            performance.method_manifest.trades
            if isinstance(performance, PerformanceAvailable)
            else None
        ),
        "performance_unavailable_reason": (
            performance.reason_code
            if isinstance(performance, PerformanceUnavailable)
            else None
        ),
        "recommendation_validated": (
            envelope.user_payload.recommendation_gate.validated
            if envelope.user_payload.recommendation_gate is not None
            else None
        ),
        "failure_cause": (
            envelope.failure_cause.model_dump(mode="json")
            if envelope.failure_cause is not None
            else None
        ),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))

    if not isinstance(performance, PerformanceAvailable):
        return 1
    if wall_seconds > args.max_wall_seconds:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
