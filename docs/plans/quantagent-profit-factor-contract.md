# Profit factor metric contract

## Decision

`profit_factor` is the ratio of gross positive **realized net PnL from closed trades**
to the absolute gross negative realized net PnL from those same trades. It is not
inferred from trade win rate, daily period returns, or the number of winning sessions.

```text
PF = sum(max(net_pnl_i, 0)) / abs(sum(min(net_pnl_i, 0)))
```

- Unit: dimensionless ratio.
- Numerator: the sum of strictly positive realized net PnL for closed trades.
- Denominator: the absolute sum of strictly negative realized net PnL for those trades.
- Zero-PnL trades affect neither side.
- Clip policy: none. A finite engine result is published as measured; no 0–3 cap or
  win-rate-derived proxy is allowed.
- Null policy: a missing, non-finite, or zero-denominator value is `value=null` and
  `is_available=false`. It is never shown as a favourable `1`, `0`, or capped maximum.

## Ownership and enforcement

The full backtest engine calculates the raw ratio from closed-trade net PnL.
`ai_graph.nodes.backtest._profit_factor` may only read the engine's
`trade_profit_factor` field and must reject period-return substitutes.
`ai_graph.quant_explanations.public_metric_registry()` is the
public whitelist and carries the formula, denominator, input window, null/clip policy,
implementation reference, and implementation hash for every public metric.

Regression coverage is in `ai/tests/test_metric_registry.py`. These local tests verify
the semantic and serialization boundary only; they are not production-data, release, or
independent-review evidence.
