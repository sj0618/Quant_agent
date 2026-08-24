# Profit factor metric contract

## Decision

`profit_factor` is the ratio of gross positive **daily period returns** to the
absolute gross negative daily period returns from the same backtest equity curve.
It is not inferred from trade win rate, the number of trades, or the number of
winning sessions.

```text
PF = sum(max(R_t, 0)) / abs(sum(min(R_t, 0)))
```

- Unit: dimensionless ratio.
- Numerator: the sum of strictly positive daily period returns after the first equity
  observation.
- Denominator: the absolute sum of strictly negative daily period returns from that
  same interval.
- Zero returns affect neither side.
- Clip policy: none. A finite engine result is published as measured; no 0–3 cap or
  win-rate-derived proxy is allowed.
- Null policy: a missing, non-finite, or engine-defaulted value—including the
  zero-denominator case—is `value=null` and `is_available=false`. It is never shown as
  a favourable `1`, `0`, or capped maximum.

## Ownership and enforcement

The full backtest engine calculates the raw period-return metric through QuantStats.
`ai_graph.nodes.backtest._profit_factor` may only read that engine field and must reject
engine metric warnings. `ai_graph.quant_explanations.public_metric_registry()` is the
public whitelist and carries the formula, denominator, input window, null/clip policy,
implementation reference, and implementation hash for every public metric.

Regression coverage is in `ai/tests/test_metric_registry.py`. These local tests verify
the semantic and serialization boundary only; they are not production-data, release, or
independent-review evidence.
