"""FE 노출용 리포트 payload 생성."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from nodes.backtest import BacktestResult
from risk_manager import RiskDecision


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_summary: str = Field(min_length=1)
    backtest: BacktestResult
    risk: RiskDecision
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)
    internal_payload: dict[str, Any] = Field(default_factory=dict)


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    recommendation: str = Field(pattern="^(APPROVE|REVIEW|REJECT)$")
    metrics: dict[str, float | int]
    risk_checks: list[dict[str, Any]]
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)
    internal_payload: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @model_serializer(mode="plain")
    def serialize_public(self) -> dict[str, Any]:
        """기본 직렬화에서 internal_payload를 노출하지 않는다."""

        return {
            "summary": self.summary,
            "recommendation": self.recommendation,
            "metrics": self.metrics,
            "risk_checks": self.risk_checks,
            "trace_id": self.trace_id,
            "debug_ref": self.debug_ref,
        }


def build_report(request: ReportRequest) -> ReportResponse:
    recommendation = "APPROVE" if request.risk.approved else "REJECT"
    metrics = request.backtest.metrics.model_dump()
    summary = (
        f"{request.strategy_summary}: return {metrics['total_return_pct']}%, "
        f"drawdown {metrics['max_drawdown_pct']}%, risk {recommendation.lower()}."
    )
    return ReportResponse(
        summary=summary,
        recommendation=recommendation,
        metrics=metrics,
        risk_checks=[check.model_dump() for check in request.risk.checks],
        trace_id=request.trace_id,
        debug_ref=request.debug_ref,
        internal_payload=request.internal_payload,
    )
