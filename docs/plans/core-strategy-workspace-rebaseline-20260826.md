# Core strategy-workspace rebaseline — 2026-08-26

## Decision

**D-CORE-001 — QuantAgent's product-critical path is:**

`natural-language strategy -> validated execution specification -> real-data analysis job -> backtest -> evidence-rich natural-language report`

The product must make this path available to an authenticated user.  Safety controls
must prevent an unsafe or unverifiable *result*, not remove the product's core
analysis and backtest capability.

The only permitted success source is an eligible, current PostgreSQL EOD data
snapshot with recorded provenance.  Fixture, stale, unknown, incomplete, or provider
failed runs terminate with an explicit unavailable/failed result and never produce
performance, a recommendation, or a plausible-looking substitute.

## Why the existing plan is invalid

This rebaseline is based on five independent angles.  The external references are
supporting engineering guidance; the product decision above is the requester's
authoritative product direction.

| Claim | Evidence | Verdict |
| --- | --- | --- |
| The original P0 plan deliberately removed the user-facing core path. | Live `2_WBS` rows 28, 34, 41, 45 and 52 define removal of new analysis input, `POST /analysis-jobs`, job writes, and browser creation calls. `docs/plans/quantagent-on-demand-retirement-inventory.md` records the same direction. | Confirmed. |
| The later RMP section did not restore a strategy-validation product. | Live `2_WBS` rows 94–103 and `docs/plans/rmp-yookeunseo-rebaseline-20260820.md` replace it with a research-only six-state candidate projection and explicitly keep legacy strategy jobs retired. | Confirmed. |
| The current application cannot complete the intended path. | `fe/src/pages/AppPage.tsx` renders `ResearchWorkspace`; `ai/ai_graph/api.py` disables raw analysis in production and `GET /api/research/jobs/{job_id}/result` always returns `unavailable_result_for_unverified_job`. | Confirmed. |
| Backtest quality risks require disclosed, reproducible controls—not deletion of backtesting. | [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) frames risk management as Govern, Map, Measure, and Manage across an AI system lifecycle. [QuantConnect reconciliation guidance](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation) documents data-timing, fills, costs, and look-ahead differences that must be measured and disclosed. | Supports fail-closed execution plus evidence. |
| A user should be able to inspect a completed backtest without confusing it with live performance or advice. | [QuantConnect backtesting guidance](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/getting-started) defines backtesting as historical simulation and notes that historical performance does not guarantee future results. | Supports clear report language and a no-order boundary. |

### Adversarial check

The former rationale correctly identified serious hazards: fixture promotion,
look-ahead/stale data, provider failure, weak lifecycle persistence, and misleading
performance copy.  It fails the product-goal check because every mitigation is
implemented as a broad feature-retirement rule.  A feature that cannot run a real
analysis can neither prove its data boundary nor provide the requested natural-language
backtest report.

The replacement plan keeps the hazard controls and reverses only the invalid
product-level prohibition.

## Replacement product contract

### Allowed core capability

- An authenticated user may submit a general, natural-language KRX strategy.
- The service may clarify ambiguous parameters, then materialize a versioned strategy
  specification and create one durable analysis job.
- The job may execute a real PostgreSQL EOD-backed screening and backtest, expose
  progress, and persist an immutable result snapshot.
- The UI may render the strategy, provenance, assumptions, limitations, statistics,
  equity curve, candidate universe, and an explanatory natural-language report.

### Non-negotiable safety boundary

- No account access, holdings, quantity, risk-profile, timing instruction, brokerage
  integration, order placement, or automatic execution.
- A general strategy's entry/exit language is valid strategy syntax; it is **not**
  personalized advice.  The preflight boundary must reject only personalized/direct
  action requests, not legitimate strategy conditions.
- `source != postgres`, stale/unknown source, missing PIT/provenance, insufficient
  coverage, invalid method manifest, provider failure, or incomplete job lifecycle
  must yield a typed terminal unavailable/failed result with no invented metrics or
  action text.
- A backtest report must state that it is historical simulation, show its as-of,
  data/method/version identifiers, and never claim future performance or place an
  order.

## WBS transformation

The old work remains an audit trail; do not delete its evidence.  Its retirement rows
must be labelled **superseded by D-CORE-001** and must not be counted toward product
completion.  The replacement WBS uses the following work packages.

| New ID | Replaces / reuses | Outcome and acceptance contract | Required evidence tier |
| --- | --- | --- | --- |
| CORE-REB-01 | OD-INV-01, OD-FE-01/02, OD-API-01, OD-JOB-01, OD-E2E-01, RMP-REB-01 | Record the decision and an explicit supersession map; no retired-entry acceptance may remain a release gate. | S + independent review |
| CORE-CONTRACT-01 | RMP-CONTRACT-01 | Version a public execution-result contract that includes strategy, job lifecycle, provenance, performance availability, report, and typed failures. It must not downgrade successful runs to a candidate-only projection. | S + R |
| CORE-SAFE-01 | RMP-PREFLIGHT-01 | Permit general strategy entry/exit conditions; reject personalized advice, account/holding/quantity/timing requests and all order execution before provider/data/job side effects. | S + R |
| CORE-DATA-01 | RMP-DATA-01, FT-RLS-01, FT-DB-02, FT-FIX-08, MT-STALE-01 | Admit a run only with current PostgreSQL EOD, PIT/as-of/coverage provenance. Every other source state is terminal unavailable with zero metrics/action/report performance. | S + R |
| CORE-JOB-01 | RMP-JOB-01, FT-JOB-07 | Durable submit, idempotency, ownership, poll/SSE reconnect, cancel, restart recovery, and immutable result identity. | S + R + O |
| CORE-BACKTEST-01 | RMP-PERF-01, QV-*, MT-*, MR-* | Run reproducible backtests with disclosed universe, dates, fills/costs, benchmark, OOS boundaries, method version, availability and limitations. | S + R + C |
| CORE-REPORT-01 | RMP-REPORT-01, RMP-HISTORY-01 | Generate an immutable, plain-language result report from the same result snapshot; preserve disclosure and avoid recommendation/order language. | S + R + O |
| CORE-FE-01 | RMP-APP-01 and existing `fe/src/features/app/**` | Restore `/app`: natural-language input, clarification, progress, cancel/retry state, result tabs, and accessible real/unavailable rendering. Browser never reaches DB/provider directly. | S + R + O |
| CORE-OPS-01 | P1-OBS-01, P1-CI-01, P1-DB-01 | Same-SHA deployment/readiness/rollback evidence, sanitized correlation, and live result provenance. | S + R + O |
| CORE-LOAD-01 | P2-OPS-01 | Contained worker-only backtest load/recovery budget before any production promotion. | S + R + C |

## First delivery slice

The first implementation slice is intentionally narrow:

1. Replace research-only public contracts with a versioned execution job/result
   contract, retaining the existing server-side preflight and ownership checks.
2. Enable general natural-language strategy submission only when release readiness
   confirms a durable store and eligible data plane; otherwise return a typed terminal
   unavailability result.
3. Reconnect `/app` to the existing strategy-workspace components using server APIs
   only, and render real job lifecycle/provenance rather than mocks.
4. Exercise the happy path and adversarial cases in an isolated test environment;
   obtain real PostgreSQL and staging/browser evidence before marking it complete.

Every following implementation package must start with a short deep-research record:
problem statement, source-of-truth contract, competing options, failure modes,
adversarial checks, chosen invariant, and its S/R/O/C test matrix.  That research
record is a prerequisite, not a substitute for implementation or operational proof.

## Evidence classification

This document is a decision and source audit.  The repository and Sheets observations
are S evidence; no production environment, database, provider, or workload was
accessed.  It makes no operational-ready claim.
