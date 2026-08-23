import json

from nodes.backtest import BacktestMetrics, BacktestResult, TradeSignal
from report import ReportRequest, build_report
from risk_manager import RiskCheck, RiskDecision


def test_report_keeps_internal_payload_out_of_public_dump() -> None:
    backtest = BacktestResult(
        signals=[TradeSignal(date="2026-01-02", action="HOLD", price=100.0)],
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
    risk = RiskDecision(
        approved=True,
        checks=[
            RiskCheck(
                name="max_drawdown",
                passed=True,
                observed=-0.9804,
                limit=-10.0,
                message="maximum drawdown is within limit",
            )
        ],
        position_size_pct=10.0,
        trace_id="trace-1",
        debug_ref="dbg-1",
    )

    report = build_report(
        ReportRequest(
            strategy_summary="momentum",
            backtest=backtest,
            risk=risk,
            trace_id="trace-1",
            debug_ref="dbg-1",
            internal_payload={"raw_llm": "hidden"},
        )
    )

    public_payload = report.model_dump()
    public_json = report.model_dump_json()

    assert public_payload["trace_id"] == "trace-1"
    assert public_payload["debug_ref"] == "dbg-1"
    assert public_payload["recommendation"] == "APPROVE"
    assert public_payload["performance_availability"] == "unavailable"
    assert "metrics" not in public_payload
    assert "total_return_pct" not in json.loads(public_json)
    assert "internal_payload" not in public_payload
    assert "raw_llm" not in json.loads(public_json)
