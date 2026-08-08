# Strategy blueprint catalog

## Decision

The canonical strategy definitions live in the versioned Python catalog
`ai_graph.strategy_blueprint_catalog`, not in the application database.

This is deliberate:

- a strategy formula, explanation, parameter range, and citation change together in code review;
- the same commit always produces the same 100 definitions and SHA-256 fingerprint;
- a database outage cannot silently change which strategy is considered canonical;
- test runs and production runs can record the catalog ID and version and remain reproducible;
- runtime selection does not need another network round trip.

The database remains useful for mutable facts. A later persistence layer should store only:

1. `user_strategy_config`: user, catalog ID, catalog version, parameter overrides, creation time;
2. `strategy_evaluation`: catalog ID, data snapshot ID, costs, metrics, benchmark, and holdout result;
3. `catalog_release`: version, fingerprint, deployment commit, and activation time.

It should not become a second editable copy of the formula text. If database seeding is needed, rows
should be generated from the code manifest and treated as read-only projections.

## Catalog shape

The catalog contains exactly 100 pre-registered definitions:

- 20 research or practitioner archetypes;
- 5 operating presets per archetype: fast, tactical, core, patient, and shield;
- 100 stable `qb-v1-*` IDs;
- one catalog version and deterministic SHA-256 fingerprint.

Every definition contains:

- executable structured profile;
- plain-language explanation;
- formula and derivation;
- reason for using the indicators;
- default parameter values and allowed ranges;
- risk style and investment horizon;
- required data;
- primary research or official methodology links;
- limitations and implementation differences.

## Runtime behavior

The service does not backtest all 100 definitions and choose the luckiest result. It first reads only
the user's words, risk style, horizon, and requested number of positions. It then selects three
distinct executable profiles before return data is inspected. Only those three enter the existing
70/30 tournament and benchmark gate.

This keeps the broad catalog useful for personalization without turning every request into a
100-way data-mining exercise.

Examples:

- vague automatic request -> the established three momentum rotation profiles;
- short concentrated momentum -> trend-leader, risk-adjusted momentum, relative momentum;
- long low-volatility request -> risk-adjusted momentum, low-volatility momentum, quality-trend
  proxy;
- volume breakout request -> volume breakout and volatility breakout receive priority.

Explicit user controls override only bounded parameters such as position count, lookback, rebalance
interval, stop loss, take profit, and trailing stop. Formula identity and source provenance stay tied
to the catalog ID.

## Honesty boundaries

- `quality-trend-proxy` is an OHLCV proxy, not an accounting-quality implementation.
- volatility-managed momentum uses a security filter, not the exposure-scaling portfolio from the
  source paper.
- 52-week high uses a maximum 252-trading-day window rather than a calendar-year window.
- research evidence and historical backtests do not guarantee future returns.
- user-facing validation must still pass minimum data, holdout, cost, drawdown, and benchmark rules.
