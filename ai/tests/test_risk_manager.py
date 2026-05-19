from nodes.backtest import BacktestMetrics
from risk_manager import RiskRequest, evaluate_risk


def test_risk_manager_approves_within_limits() -> None:
    decision = evaluate_risk(
        RiskRequest(
            metrics=BacktestMetrics(
                loops=3,
                observations=4,
                total_return_pct=5.0,
                max_drawdown_pct=-0.9804,
                win_rate_pct=66.6667,
            ),
            trace_id="trace-1",
            debug_ref="dbg-1",
        )
    )

    assert decision.approved
    assert decision.position_size_pct == 10.0
    assert all(check.passed for check in decision.checks)


def test_risk_manager_rejects_limit_breach() -> None:
    decision = evaluate_risk(
        RiskRequest(
            metrics=BacktestMetrics(
                loops=3,
                observations=4,
                total_return_pct=-12.0,
                max_drawdown_pct=-20.0,
                win_rate_pct=10.0,
            ),
            trace_id="trace-2",
            debug_ref="dbg-2",
        )
    )

    assert not decision.approved
    assert decision.position_size_pct == 0.0
    assert {check.name for check in decision.checks if not check.passed} == {"max_drawdown", "win_rate"}
