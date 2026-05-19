from __future__ import annotations

from typing import Any, TypedDict

from .schemas import (
    BacktestResult,
    CandidateStock,
    InternalPayload,
    PublicRunPayload,
    ScenarioPayload,
    StrategySpec,
    WorkspacePayload,
)


class QuantAgentState(TypedDict, total=False):
    user_input: str
    trace_id: str
    debug_ref: str
    scenario: ScenarioPayload
    strategy: StrategySpec
    candidates: list[CandidateStock]
    backtest: BacktestResult
    signal_decisions: list[Any]
    risk_warnings: list[Any]
    report_preview: list[Any]
    workspace: WorkspacePayload
    public_payload: PublicRunPayload
    internal_payload: InternalPayload
    error: str


def append_internal_trace(
    state: QuantAgentState,
    *,
    node: str,
    status: str,
    detail: str,
) -> InternalPayload:
    internal_payload = state.get("internal_payload")
    if internal_payload is None:
        internal_payload = InternalPayload(llm_provider="mock")

    data = internal_payload.model_dump()
    data["node_trace"].append({"node": node, "status": status, "detail": detail})
    return InternalPayload.model_validate(data)
