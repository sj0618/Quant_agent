from security.ast_validator import validate_backtest_code
from ai_graph.security.ast_validator import validate_backtest_code as validate_graph_backtest_code


SAFE_CODE = """def build_signals(prices):
    return [{"date": row["date"], "action": "HOLD", "price": float(row["close"])} for row in prices]
"""


def test_accepts_safe_build_signals_entrypoint() -> None:
    result = validate_backtest_code(SAFE_CODE)

    assert result.ok
    assert result.violations == ()


def test_rejects_filesystem_and_dynamic_execution() -> None:
    result = validate_backtest_code(
        """import os
def build_signals(prices):
    eval("1 + 1")
    os.system("echo unsafe")
    return []
"""
    )

    assert not result.ok
    assert {violation.code for violation in result.violations} >= {
        "import.blocked",
        "call.blocked",
        "attribute_call.blocked",
        "attribute.blocked",
    }


def test_requires_build_signals_function() -> None:
    result = validate_backtest_code("def other(prices):\n    return []\n")

    assert not result.ok
    assert any(violation.code == "function.missing" for violation in result.violations)


def test_graph_validator_blocks_required_forbidden_surface() -> None:
    blocked_cases = [
        "import subprocess\ndef build_signals(prices):\n    return []\n",
        "import sys\ndef build_signals(prices):\n    return []\n",
        "import importlib\ndef build_signals(prices):\n    return []\n",
        "def build_signals(prices):\n    open('x')\n    return []\n",
        "def build_signals(prices):\n    getattr(prices, 'x')\n    return []\n",
        "def build_signals(prices):\n    setattr(prices, 'x', 1)\n    return []\n",
        "def build_signals(prices):\n    __import__('os')\n    return []\n",
        "def build_signals(prices):\n    exec('1')\n    return []\n",
    ]

    for source in blocked_cases:
        assert not validate_graph_backtest_code(source).ok


def test_graph_validator_allows_declared_modules() -> None:
    source = """import math
from datetime import datetime
def build_signals(prices):
    math.sqrt(4)
    datetime.now()
    return [{"date": row["date"], "action": "HOLD", "price": float(row["close"])} for row in prices]
"""
    assert validate_graph_backtest_code(source).ok
