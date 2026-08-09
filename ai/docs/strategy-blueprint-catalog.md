# Independent strategy blueprint catalog

## Decision

Canonical formulas live in the versioned Python catalog
`ai_graph.strategy_blueprint_catalog`, not in mutable database rows.

This keeps formula, executable conditions, explanation, parameter bounds, citations, tests, catalog
version, and SHA-256 fingerprint in one reviewed change. A database outage therefore cannot change
the rule being evaluated, and a historical result can be reproduced from its catalog ID and data
snapshot.

The database remains appropriate for mutable records only:

1. `user_strategy_config`: user, catalog ID/version, risk overrides, and creation time;
2. `strategy_evaluation`: catalog ID, data snapshot, costs, metrics, benchmark periods, and holdout;
3. `catalog_release`: version, fingerprint, deployment commit, and activation time.

If a UI needs database rows, they should be read-only projections generated from this manifest, not
a second editable copy of the formulas.

## V2 catalog shape

V1's advertised 100 rows were 20 formulas multiplied by five parameter presets. V2 removes that
counting shortcut. It currently contains 56 independently executable formulas:

- one stable `qb-v2-*` ID per formula;
- one unique hash over entry conditions, exit conditions, ranking, and execution mode;
- no parameter preset counted as another strategy;
- six families: momentum, trend, breakout, mean reversion, volume flow, and defensive;
- adjusted daily OHLCV as the honest common data boundary;
- papers or official quant/indicator projects as provenance.

Every formula stores the exact `Condition` objects and ranking metric sent to `StrategyIR`. It also
stores a plain explanation, mathematical formula, derivation, selection reason, caveats, and a
separate explanation for every indicator: what it means, how its number is calculated, and why it is
used.

Formula windows are fixed. For example, changing SMA(20/50) to SMA(10/40) does not manufacture a new
catalog row. User intent may customize position count, rebalance cadence, stop loss, take profit, and
trailing stop within declared bounds without changing formula identity.

## Runtime behavior

The service does not test all 56 against the same history and report the luckiest one. Before seeing
returns it maps the user's words, risk style, and horizon to three distinct execution signatures.
Those three rules then run through the same next-open, cost-aware backtest and benchmark gate.

Each selected candidate carries its `blueprint_id` from input interpretation through generated plan,
candidate parameters, executing `StrategyIR`, logs, and result provenance. Cross-sectional formulas
rotate on the configured schedule; event-driven formulas enter on their own signal. Scarce position
slots are assigned using the blueprint's declared ranking metric rather than ticker order.

All catalog indicators can be derived from current-and-past OHLCV inside `PreparedFeatureStore`.
Point-in-time warehouse values take precedence when present, and the local derivation fills missing
values. Signals use end-of-day information and orders fill only at the next available open.

## Verification boundary

- Catalog tests require at least 50 unique IDs, formulas, and execution signatures.
- Every formula must emit both buy and sell actions on deterministic multi-regime QA data.
- Every formula is recomputed on a truncated prefix; prefix actions must exactly match the same
  segment of a longer run, proving future rows did not alter past signals.
- Source links and per-indicator formula/derivation/reason fields are mandatory.
- Research evidence and historical backtests never imply guaranteed future returns.
