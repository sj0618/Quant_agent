import json
from pathlib import Path

from nodes.backtest import BacktestRequest, run_backtest
from nodes.backtest_code import BacktestCodeRequest, MockLLMClient, generate_backtest_code


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_backtest_code_generation_uses_mock_and_validates_ast() -> None:
    code = (FIXTURE_DIR / "generated_backtest_code.py").read_text(encoding="utf-8")
    result = generate_backtest_code(
        BacktestCodeRequest(strategy_summary="momentum", trace_id="trace-1", debug_ref="dbg-1"),
        llm_client=MockLLMClient(code),
    )

    assert result.validation.ok
    assert result.trace_id == "trace-1"
    assert "build_signals" in result.code


def test_backtest_runs_three_deterministic_loops() -> None:
    code = (FIXTURE_DIR / "generated_backtest_code.py").read_text(encoding="utf-8")
    prices = json.loads((FIXTURE_DIR / "market_prices.json").read_text(encoding="utf-8"))

    result = run_backtest(
        BacktestRequest(code=code, prices=prices, trace_id="trace-1", debug_ref="dbg-1"),
        loops=3,
    )

    assert result.metrics.loops == 3
    assert result.metrics.observations == 4
    assert result.metrics.total_return_pct == 5.0
    assert [signal.action for signal in result.signals] == ["HOLD", "BUY", "SELL", "BUY"]
