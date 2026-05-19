"""백테스트 결과 기반 리스크 관리 노드."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from nodes.backtest import BacktestMetrics


class RiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: BacktestMetrics
    max_drawdown_limit_pct: float = Field(default=-10.0, le=0)
    min_win_rate_pct: float = Field(default=45.0, ge=0, le=100)
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)


class RiskCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    passed: bool
    observed: float
    limit: float
    message: str = Field(min_length=1)


class RiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    checks: list[RiskCheck] = Field(min_length=1)
    position_size_pct: float = Field(ge=0, le=100)
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)


def evaluate_risk(request: RiskRequest) -> RiskDecision:
    """리스크 한도와 백테스트 지표를 비교해 포지션 크기를 산출한다."""

    drawdown_passed = request.metrics.max_drawdown_pct >= request.max_drawdown_limit_pct
    win_rate_passed = request.metrics.win_rate_pct >= request.min_win_rate_pct
    checks = [
        RiskCheck(
            name="max_drawdown",
            passed=drawdown_passed,
            observed=request.metrics.max_drawdown_pct,
            limit=request.max_drawdown_limit_pct,
            message="maximum drawdown is within limit" if drawdown_passed else "maximum drawdown exceeds limit",
        ),
        RiskCheck(
            name="win_rate",
            passed=win_rate_passed,
            observed=request.metrics.win_rate_pct,
            limit=request.min_win_rate_pct,
            message="win rate meets minimum" if win_rate_passed else "win rate is below minimum",
        ),
    ]
    approved = all(check.passed for check in checks)
    position_size_pct = 10.0 if approved else 0.0
    return RiskDecision(
        approved=approved,
        checks=checks,
        position_size_pct=position_size_pct,
        trace_id=request.trace_id,
        debug_ref=request.debug_ref,
    )
