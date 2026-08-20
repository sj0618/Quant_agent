from __future__ import annotations

import argparse
import json
import time
from uuid import uuid4

from ai_graph.graph import run_analysis


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
        "selected_candidate_id": (
            performance.selected_candidate_id if performance is not None else None
        ),
        "metrics": (
            performance.metrics.model_dump(mode="json")
            if performance is not None and performance.metrics is not None
            else None
        ),
        "trade_count": (
            performance.engine_summary.get("trade_count")
            if performance is not None
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

    if performance is None:
        return 1
    if wall_seconds > args.max_wall_seconds:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
