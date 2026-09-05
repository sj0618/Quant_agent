from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.ai_backtest import AICodeBacktestFlowRequest, CodeExecutionResult
from app.services import ai_backtest_subprocess_runner as runner


def _release_fd(payload: bytes) -> int:
    read_fd, write_fd = os.pipe()
    if payload:
        os.write(write_fd, payload)
    os.close(write_fd)
    return read_fd
@pytest.mark.parametrize(
    "payload",
    [b"", b"\x00", runner._RELEASE_BYTE + b"\x00"],
    ids=["eof", "invalid-byte", "extra-byte"],
)

def test_runner_rejects_unreleased_child_without_reading_input(monkeypatch, tmp_path, payload):
    read_paths: list[Path] = []

    def unexpected_read(path: Path, *, encoding: str) -> str:
        read_paths.append(path)
        raise AssertionError("release rejection must precede all file reads")

    monkeypatch.setattr(Path, "read_text", unexpected_read)
    exit_code = runner.main(
        [
            str(tmp_path / "request.json"),
            str(tmp_path / "generated.py"),
            str(tmp_path / "result.json"),
            str(uuid4()),
            str(_release_fd(payload)),
        ]
    )

    assert exit_code == runner._RELEASE_FAILURE_EXIT_CODE
    assert read_paths == []
    assert not (tmp_path / "result.json").exists()


def test_runner_reads_and_executes_only_after_valid_release(monkeypatch, tmp_path):
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="release barrier test",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )
    request_path = tmp_path / "request.json"
    code_path = tmp_path / "generated.py"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    code_path.write_text("def build_signals(prices):\n    return []\n", encoding="utf-8")
    executed: list[tuple[AICodeBacktestFlowRequest, str]] = []

    def execute(captured_request, generated, *, trace_id):
        executed.append((captured_request, generated.generated_code))
        now = datetime.now(UTC)
        return CodeExecutionResult(
            runtime_env=generated.target_runtime,
            status="succeeded",
            timeout_seconds=captured_request.timeout_seconds,
            memory_limit_mb=captured_request.memory_limit_mb,
            started_at=now,
            ended_at=now,
        )

    monkeypatch.setattr(runner, "_execute_generated_backtest", execute)
    exit_code = runner.main(
        [str(request_path), str(code_path), str(result_path), str(uuid4()), str(_release_fd(runner._RELEASE_BYTE))]
    )

    assert exit_code == 0
    assert executed == [(request, "def build_signals(prices):\n    return []\n")]
    assert CodeExecutionResult.model_validate_json(result_path.read_text(encoding="utf-8")).status == "succeeded"


def test_generated_backtest_uses_the_period_sealed_in_the_strategy(monkeypatch) -> None:
    from ai_graph import data_sources
    from ai_graph.nodes import backtest as ai_backtest
    from ai_graph.schemas import StrategySpec

    strategy = StrategySpec(
        strategy_id="sealed_period",
        name="sealed period",
        market="KRX",
        timeframe="daily",
        backtest_years=2,
        entry_conditions=[{"left": "rsi", "operator": "lte", "right": 30}],
        confidence=0.5,
    )
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="RSI 전략",
        target_runtime="python-sandbox",
        code_purpose="backtest",
        parsed_strategy_jsonb=strategy.model_dump(mode="json"),
    )
    observed: dict[str, object] = {}

    def load_pipeline_data(_query: str, _trace_id: str, **kwargs: object):
        observed.update(kwargs)
        return SimpleNamespace(price_rows=[], metadata={"source": "fixture"})

    empty_engine_result = SimpleNamespace(
        summary={}, signals=[], trades=[], equity_curve=[], order_audit=[], output_paths={}
    )
    monkeypatch.setattr(data_sources, "load_pipeline_data_from_env", load_pipeline_data)
    monkeypatch.setattr(ai_backtest, "_execute_candidate_code", lambda *_: [])
    monkeypatch.setattr(ai_backtest, "_engine_market_rows", lambda *_: ([], []))
    monkeypatch.setattr(ai_backtest, "_merge_generated_signals", lambda *_: [])
    monkeypatch.setattr(ai_backtest, "_available_ticker_count", lambda *_: 0)
    monkeypatch.setattr(ai_backtest, "_engine_strategy_spec", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(ai_backtest, "run_engine_backtest", lambda *_args, **_kwargs: empty_engine_result)
    monkeypatch.setattr(ai_backtest, "_benchmark_return", lambda *_: None)

    result = runner._execute_generated_backtest(
        request,
        runner.GeneratedCodeResult(
            target_runtime="python-sandbox",
            code_purpose="backtest",
            generated_code="def build_signals(prices):\n    return []\n",
        ),
        trace_id=uuid4(),
    )

    assert observed == {"backtest_lookback_years": 2, "period_locked": True}
    assert result.backtest_result is not None


def test_generated_backtest_refuses_an_unsealed_strategy_before_loading_data(monkeypatch) -> None:
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="RSI 전략을 2년 백테스트",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )
    called = False

    def load_pipeline_data(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("ai_graph.data_sources.load_pipeline_data_from_env", load_pipeline_data)

    with pytest.raises(ValueError, match="sealed strategy"):
        runner._execute_generated_backtest(
            request,
            runner.GeneratedCodeResult(
                target_runtime="python-sandbox",
                code_purpose="backtest",
                generated_code="def build_signals(prices):\n    return []\n",
            ),
            trace_id=uuid4(),
        )

    assert called is False
def test_realized_cost_totals_sum_trade_costs_and_fill_slippage():
    trade = SimpleNamespace(
        ticker="005930",
        entry_date="2025-01-02",
        exit_date="2025-01-03",
        entry_price=101.0,
        exit_price=117.6,
        quantity=10,
        entry_cost=1.01,
        exit_cost=35.28,
    )
    ohlcv_rows = [
        SimpleNamespace(date=date(2025, 1, 2), ticker="005930", open=100.0),
        SimpleNamespace(date=date(2025, 1, 3), ticker="005930", open=120.0),
    ]

    commission, tax, slippage = runner._realized_cost_totals(
        trades=[trade],
        ohlcv_rows=ohlcv_rows,
        cost_model={"commission_pct": 0.01, "tax_pct": 0.02, "slippage_pct": 0.01},
    )

    assert commission == pytest.approx(12.77)
    assert tax == pytest.approx(23.52)
    assert slippage == pytest.approx(34.0)


def test_realized_cost_totals_does_not_store_rates_when_trade_data_is_incomplete():
    commission, tax, slippage = runner._realized_cost_totals(
        trades=[SimpleNamespace(entry_cost=None, exit_cost=1.0)],
        ohlcv_rows=[],
        cost_model={"commission_pct": 0.00015, "tax_pct": 0.0023, "slippage_pct": 0.001},
    )

    assert (commission, tax, slippage) == (None, None, None)
