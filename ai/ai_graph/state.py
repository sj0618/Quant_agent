from __future__ import annotations

from typing import Any, TypedDict


class QuantAgentState(TypedDict, total=False):
    user_query: str
    # What the interpreter turned user_query into: one concrete, self-contained
    # strategy. Every stage after the Ambiguity Classifier reads this.
    resolved_query: str
    intent: dict[str, Any]
    trace_id: str
    debug_ref: str
    route: str
    status: str
    ambiguity: dict[str, Any]
    semantic_slots: dict[str, Any]
    data_requirements: list[dict[str, Any]]
    source_usage: list[dict[str, Any]]
    freshness_status: str
    freshness_evidence: dict[str, Any]
    proxy_disclosure: dict[str, str] | None
    failure_cause: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    data: dict[str, Any]
    original_strategy_spec: dict[str, Any]
    strategy_spec: dict[str, Any]
    price_rows: list[dict[str, Any]]
    l4_evidence: list[dict[str, Any]]
    macro_snapshot: dict[str, Any]
    # Official KOSPI/KOSDAQ total-return levels and monthly index weights. Kept out of
    # `data` because it is one value per session per index and `data` is republished in
    # the response envelope.
    official_benchmark: dict[str, Any]
    backtest_code: dict[str, Any]
    backtest: dict[str, Any]
    signal: dict[str, Any]
    risk: dict[str, Any]
    report: dict[str, Any]
    internal_payload: dict[str, Any]
    envelope: dict[str, Any]
