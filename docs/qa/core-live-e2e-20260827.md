# CORE-LIVE-E2E-01 staging evidence runbook — 2026-08-27

## Purpose

This runbook defines the evidence boundary for the product-critical path:

`natural-language KRX strategy -> validated execution spec/hash -> durable job/outbox -> PostgreSQL EOD/PIT -> immutable terminal report`

It is a plan for an **isolated staging** run. It is not an operational result,
does not authorize production, node3, PVE, or primary-DB load, and must not be
used to mark a WBS row complete.

## Fixed generic scenario

Use one non-personalized generic RSI rule:

- KRX daily bars
- entry when RSI is less than or equal to 30
- exit when RSI is greater than or equal to 70
- a declared historical one-year interval

The submitted rule is a strategy condition, not investment advice or an order.
Do not record raw prompts, credentials, DSNs, provider payloads, host names, or
user identifiers in the evidence bundle.

## Required same-SHA manifest fields

Before any execution, record only the following non-secret fields in the
immutable staging artifact:

- full candidate Git SHA and artifact/image digest;
- migration revision set;
- `source=postgres`, fallback=false, snapshot digest, as-of date, universe and
  candidate counts, and PIT policy hash;
- execution-spec version/hash, immutable result identifier, and report hash;
- active job-store/audit-sink kind, scenario identifier, time budget, terminal
  status, and cleanup result.

Missing provenance is a `BLOCKED` outcome. It must not be discovered by reading
environment values or replaced by fixture/memory/noop output.

## Scenario matrix

| ID | Class | Harness boundary | Required invariant | Pass condition |
| --- | --- | --- | --- | --- |
| CORE-LIVE-S-01 | S | Contract/API tests only | Parse emits a bounded spec/version/hash/token; a tampered spec creates no job. | Targeted test command exits 0; any mock/memory/noop remains labelled S. |
| CORE-LIVE-R-01 | R | Disposable PostgreSQL plus independent API/worker processes | nonce consumption, job, idempotency, and outbox are atomic; restart cannot duplicate execution. | Transaction/restart artifact proves one durable job and one immutable terminal result. |
| CORE-LIVE-O-01 | O | Isolated staging only | Generic RSI completes as parse -> spec/hash -> durable job -> verified PostgreSQL EOD/PIT -> immutable report. | Public terminal report exposes provenance/as-of/counts/spec/result identifiers without metrics when eligibility is missing. |
| CORE-LIVE-C-01 | C | Worker-only non-root cgroup, isolated staging | N=1 and N=2 preserve result hash, reap descendants, and keep API/sentinel outside the worker cgroup. | Record wall p50/p95/max by stage, memory.peak, PSI/event deltas, cleanup, and no limit breach. |

## UX timing observation and gate

The sole live observation on 2026-08-27 reached the visible running state in
about 1.3 seconds and returned a generic contract failure after about 21.6
seconds. It supplied neither a safe stage/subcause nor a report/provenance
payload. It is an O **failure observation**, not a performance baseline and
not an implementation root cause.

For isolated-staging acceptance, capture acknowledgement, first durable stage,
each stage transition, and terminal time. Do not show an invented percentage.
After 10 seconds the UI must preserve the job link and present truthful
background/cancel/reconnect semantics. A terminal failure must expose only a
safe stage, safe subcause, retryability, and debug reference.

## Decision rule

- `PASS`: every WBS-required class is present for one SHA, all cleanup succeeds,
  and the assigned independent reviewer records approval.
- `FAIL`: a stated invariant or resource budget is violated; preserve the safe
  artifact and fix before rerunning the same scenario.
- `BLOCKED`: isolated staging, non-secret provenance, approved resource budget,
  or reviewer evidence is unavailable.

Neither this runbook nor S-tier tests may promote `CORE-LIVE-E2E-01` to
`완료`.
