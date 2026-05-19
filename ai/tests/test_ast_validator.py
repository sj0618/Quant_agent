from security.ast_validator import validate_backtest_code


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
