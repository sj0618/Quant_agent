from __future__ import annotations

import asyncio
from uuid import uuid4

from app.schemas.ai_backtest import AICodeBacktestFlowRequest, GeneratedCodeResult
from app.services.ai_backtest_runtime import ASTCodeValidator, SandboxedBacktestExecutor


def test_ast_code_validator_blocks_non_runtime_imports_and_file_io_calls():
    validator = ASTCodeValidator()
    code = """
import pandas

def build_signals(prices):
    pandas.read_csv('prices.csv')
    return []
"""
    result = validator.validate(
        GeneratedCodeResult(
            target_runtime="python-sandbox",
            code_purpose="backtest",
            generated_code=code,
        ),
        trace_id=uuid4(),
    )

    assert result.is_safe is False
    assert result.uses_allowed_imports is False
    assert result.blocks_file_write is False
    assert any("runtime import 'pandas' is not allowed" in error["message"] for error in result.errors_jsonb)
    assert any("pandas.read_csv" in error["message"] for error in result.errors_jsonb)


def test_sandboxed_backtest_executor_enforces_timeout():
    executor = SandboxedBacktestExecutor()
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="무한 루프 전략",
        parsed_strategy_jsonb={
            "strategy_id": "loop_strategy",
            "name": "Loop Strategy",
            "universe": "KOSPI200",
            "market": "KRX",
            "timeframe": "daily",
            "entry_conditions": [{"left": "rsi", "operator": "lte", "right": 30}],
            "exit_conditions": [],
            "indicators": ["RSI"],
            "risk_constraints": {"max_position_pct": 0.1},
            "assumptions": [],
            "source_refs": [],
            "confidence": 0.5,
        },
        strategy_id="loop_strategy",
        target_runtime="python-sandbox",
        code_purpose="backtest",
        timeout_seconds=1,
        memory_limit_mb=128,
    )
    generated = GeneratedCodeResult(
        target_runtime="python-sandbox",
        code_purpose="backtest",
        generated_code="def build_signals(prices):\n    while True:\n        pass\n",
    )

    result = asyncio.run(executor.execute(request, generated, trace_id=uuid4(), execution_run_id=uuid4()))

    assert result.status == "timeout"
    assert result.timeout_seconds == 1
    assert result.memory_limit_mb == 128
    assert result.backtest_result is None
