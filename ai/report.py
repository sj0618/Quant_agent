"""FE 노출용 리포트 payload 생성."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from ai_graph.research_eligibility import PerformanceAvailable, PublicPerformance
from nodes.backtest import BacktestResult
from risk_manager import RiskDecision


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_summary: str = Field(min_length=1)
    backtest: BacktestResult
    risk: RiskDecision
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)
    # The legacy standalone report can still receive its internal engine object for
    # audit, but it may publish performance only through this projection.
    public_performance: PublicPerformance | None = None
    internal_payload: dict[str, Any] = Field(default_factory=dict)


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    recommendation: str = Field(pattern="^(APPROVE|REVIEW|REJECT)$")
    performance_availability: str = Field(pattern="^(available|unavailable)$")
    metrics: dict[str, float | int] | None = None
    risk_checks: list[dict[str, Any]]
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)
    internal_payload: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @model_serializer(mode="plain")
    def serialize_public(self) -> dict[str, Any]:
        """기본 직렬화에서 internal_payload를 노출하지 않는다."""

        payload = {
            "summary": self.summary,
            "recommendation": self.recommendation,
            "performance_availability": self.performance_availability,
            "risk_checks": self.risk_checks,
            "trace_id": self.trace_id,
            "debug_ref": self.debug_ref,
        }
        if self.metrics is not None:
            payload["metrics"] = self.metrics
        return payload


def build_report(request: ReportRequest) -> ReportResponse:
    recommendation = "APPROVE" if request.risk.approved else "REJECT"
    performance = request.public_performance
    if isinstance(performance, PerformanceAvailable):
        raw_metrics = performance.performance.get("metrics")
        metrics = (
            {key: value for key, value in raw_metrics.items() if isinstance(value, (float, int))}
            if isinstance(raw_metrics, dict)
            else None
        )
        summary = f"{request.strategy_summary}: published performance is available; risk {recommendation.lower()}."
        availability = "available"
    else:
        metrics = None
        summary = f"{request.strategy_summary}: performance is unavailable; risk {recommendation.lower()}."
        availability = "unavailable"
    return ReportResponse(
        summary=summary,
        recommendation=recommendation,
        performance_availability=availability,
        metrics=metrics,
        risk_checks=[check.model_dump() for check in request.risk.checks],
        trace_id=request.trace_id,
        debug_ref=request.debug_ref,
        internal_payload=request.internal_payload,
    )
