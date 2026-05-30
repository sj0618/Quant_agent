from __future__ import annotations

from typing import Any, TypedDict


class QuantAgentState(TypedDict, total=False):
    user_query: str
    trace_id: str
    debug_ref: str
    route: str
    status: str
    ambiguity: dict[str, Any]
    retrieval: dict[str, Any]
    data: dict[str, Any]
    original_strategy_spec: dict[str, Any]
    strategy_spec: dict[str, Any]
    price_rows: list[dict[str, Any]]
    l4_evidence: list[dict[str, Any]]
    macro_snapshot: dict[str, Any]
    backtest_code: dict[str, Any]
    backtest: dict[str, Any]
    signal: dict[str, Any]
    risk: dict[str, Any]
    report: dict[str, Any]
    internal_payload: dict[str, Any]
    envelope: dict[str, Any]
