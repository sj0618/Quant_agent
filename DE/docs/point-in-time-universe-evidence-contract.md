# Point-in-time universe evidence contract v1

This contract defines the minimum reproducible input for a historical universe.
It is a data-engineering contract, not proof of a live release or a substitute for a
PostgreSQL evidence run.

## Membership

- Each member is evaluated at one `as_of_date` on an open KRX session.
- It must have a `core.symbol_listing_history` interval where
  `valid_from <= as_of_date <= valid_to` (or an open `valid_to`) and
  `listing_status = listed`.
- Only a `KOSPI` or `KOSDAQ` value recorded on the same listing-history interval,
  and `보통주` recorded by `core.symbol_security_type_history` on the same as-of
  date, are eligible. `symbol_master` is a current reference and must not infer a
  past market, listing state, or security type.
- Missing listing or security-type history is an unavailable membership, not an
  invitation to fall back to the current universe. A delisted symbol remains eligible
  only through its final valid historical interval.

Security-type history is inserted only when an observed source payload has an explicit
classification field (`security_type`, KRX `SECUGRP_NM`/`SECT_TP_NM`, or
`MKT_TP_NM`). A name or market-only classifier output may update the current master
record but cannot create historical common-stock evidence.

## Immutable evidence fields

One retained input manifest must contain all of the following before a replay is
called reproducible:

| Field | Meaning |
| --- | --- |
| `source` | `postgres` for a release candidate; `fixture` is local-test only. |
| `as_of` | ISO-8601 trading date used for membership and indicator input. |
| `source_version` | Warehouse/migration or extract version that produced the rows. |
| `lineage_hash` | SHA-256 of the canonical lineage event/extract descriptor. |
| `universe_snapshot_hash` | SHA-256 of canonical PIT member rows. |
| `indicator_input_hash` | SHA-256 of canonical indicator-input rows. |
| `formula_version` | Immutable identifier for the calculation contract. |
| `seed_hash` | SHA-256 of the deterministic strategy seed. |

The `P0-REPLAY-01` local runner rejects malformed SHA-256 fields and emits a
limitation when the manifest source is not PostgreSQL.  Its fixture is deliberately
synthetic: passing that runner proves deterministic serialization only, never live
data freshness, coverage, or production eligibility.

## Verification boundary

The SQL migration `013_point_in_time_universe_membership.sql` is the database
membership boundary.  A server-side replay additionally requires the manifest above,
the actual PostgreSQL query result, and independent review.  No local fixture or
cached output may be reported as that server-side evidence.
