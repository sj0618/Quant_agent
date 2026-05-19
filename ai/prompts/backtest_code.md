# Backtest Code Prompt

Generate deterministic Python code for the QuantAgent fixture backtest node.

Requirements:
- Output one function named `build_signals(prices)`.
- `prices` is a list of dictionaries containing `date` and `close`.
- Return a list of dictionaries containing `date`, `action`, and `price`.
- Allowed actions are `BUY`, `SELL`, and `HOLD`.
- Do not import network, filesystem, process, or credential-related modules.
- Do not call `open`, `eval`, `exec`, `compile`, `globals`, `locals`, or `__import__`.

The generated code is validated by `security.ast_validator.validate_backtest_code`
before execution.
