# Recovery Objectives

WBS `P2-DB-01`. This document records what this repository can and cannot say
about recovery time, recovery point, and post-restore schema consistency.

## Scope boundary

`service_db/scripts/benchmark_recovery_objective.py` runs two distinct drills.
They measure different things and must not be conflated.

| Backend | Mechanism | Restores data? | `is_backup_restore_rto` |
| --- | --- | --- | --- |
| `migration_replay` | rollback SQL then forward migration | no | `false` |
| `logical_backup` | real `pg_dump` then `pg_restore` | yes | `true` |

**What still does not exist.** This repository has no WAL archiving, no
point-in-time recovery, no `pg_basebackup` or physical replication, no cloud
snapshot integration, no backup scheduler, and no operational retention or
encryption policy. The `logical_backup` backend is a drill that takes a dump and
restores it on demand; it is not a production disaster-recovery capability.
Operational backup, WAL, and retention controls remain tracked as provider-level
evidence in `ai/docs/ai-logging-operations.md` section 9, where they are still
blank and explicitly not marked PASS.

### Why the migration replay is kept separate

The `migration_replay` backend reuses the `P1-DB-01` drill
(`service_db/scripts/verify_fixed_migration_replay.py`): it runs
`rollbacks/022_immutable_analysis_results.down.sql` and then re-applies
`migrations/022_immutable_analysis_results.sql`.

**A migration replay is not a backup restore.** The rollback script executes
`DROP TABLE IF EXISTS app.analysis_result`, and the forward migration recreates
that table empty. No row is ever restored. Its measurement therefore keeps
`is_backup_restore_rto: false` and is never renamed to a backup restore figure.

## Recovery time

Both backends separate the *measured* value from the *objective*. No recovery
time objective has been agreed for this service, so `objective_seconds` stays
`null` on both. A measured value never becomes an objective on its own.

### `migration_replay`

| Field | Value |
| --- | --- |
| Metric | `migration_forward_restore_duration_seconds` |
| Measurement start | forward restore migration execution begins |
| Measurement end | post-restore catalog union fingerprint verified |
| Objective | **not established** |
| `is_backup_restore_rto` | `false` |

The measured window covers the forward restore and its consistency check. It
**excludes** database instance provisioning, data restore, and application
readiness. It is therefore one component of a recovery time objective, not the
objective itself.

### `logical_backup`

| Field | Value |
| --- | --- |
| Metric | `logical_backup_restore_duration_seconds` |
| Measurement start | `pg_restore` invocation begins |
| Measurement end | post-restore catalog fingerprint and probe data verified |
| Reported separately | `backup_creation_duration_seconds` |
| Objective | **not established** |
| `is_backup_restore_rto` | `true` |

Backup creation and restore are timed separately so a slow dump can never be
read as a fast recovery, or vice versa. The restore window still **excludes**
instance provisioning and application readiness, so it is a database restore
time, not a full service recovery time.

No recovery time objective has been agreed for this service, so
`objective_seconds` stays `null`. A measured value never becomes an objective on
its own; an operator has to set the target.

The rollback leg is deliberately outside the measured window. It is the drill's
simulated failure, not part of recovery.

## Recovery point

**The recovery point objective is `not_established` on both backends, and
`RPO = 0` is never recorded.** `objective_seconds` and `measured_seconds` stay
`null` throughout. An observed backup snapshot is not an agreed data-loss
budget; only the team can set that.

### `migration_replay`

| Field | Value |
| --- | --- |
| Status | `not_established` |
| `objective_seconds` | `null` |
| `measured_seconds` | `null` |

There is no recovery point at all here. The replay drill being synchronous says
only that its DDL statements run synchronously; it says nothing about a
data-loss window. Because the drill drops and recreates schema objects without
restoring any row, the honest reading of its data-loss behaviour is total loss
for the affected table, not zero.

### `logical_backup`

| Field | Value |
| --- | --- |
| Status | `observed` |
| `objective_status` | `not_established` |
| `objective_seconds` | `null` |
| `measured_seconds` | `null` |

A logical dump does have a recovery point: the instant the dump was taken. The
run records `backup_started_at`, `backup_completed_at`, and the dump's size and
SHA-256, and it *demonstrates* the boundary rather than asserting it:

1. probe row `probe-before-backup` is written
2. `pg_dump` runs
3. probe row `probe-after-backup` is written
4. the `app` schema is dropped
5. `pg_restore` runs
6. `probe-before-backup` comes back; `probe-after-backup` does not

`post_backup_write_restored` records step 6 and must be `false`. This proves the
restore recovers to the dump instant and loses everything written afterwards —
which is exactly why an unquantified data-loss window is the honest record. The
allowable window is a policy decision nobody has made, so the objective stays
unestablished.

## Schema and data consistency

Schema consistency reuses the `P1-DB-01` catalog fingerprint logic
(`_catalog_union` / `_catalog_fingerprint`) without reimplementing it. That
logic collects the migration-owned relations, indexes, views, enums, columns,
constraints, triggers, and function, then hashes the sorted union in both
PostgreSQL and Python and rejects a digest mismatch.

Both backends record the pre-loss baseline fingerprint, the post-restore
fingerprint, and whether the two are equal.

The `logical_backup` backend additionally records `data_consistency`: probe row
counts before backup and after restore, a SHA-256 digest of the probe rows at
both points, and `post_backup_write_restored`. The probe rows live in
`app.users`, a migration-owned table, and carry only synthetic values on the
reserved `example.invalid` domain — no personal or production data.

`status` is `PASS` only when every recorded consistency flag is true.

## Artifact contract

`service-db-recovery-objective-v1`, written by
`service_db/scripts/benchmark_recovery_objective.py --artifact <path>`.

```json
{
  "contract": "service-db-recovery-objective-v1",
  "wbs_id": "P2-DB-01",
  "status": "PASS",
  "measured_at": "<UTC ISO-8601>",
  "recovery_target": {
    "backend": "migration_replay",
    "rollback_script": "022_immutable_analysis_results.down.sql",
    "forward_migration": "022_immutable_analysis_results.sql",
    "fixed_migration_count": 13
  },
  "recovery_time": {
    "status": "measured",
    "metric_name": "migration_forward_restore_duration_seconds",
    "measured_seconds": 0.0,
    "measurement_scope": { "start": "...", "end": "..." },
    "objective_status": "not_established",
    "objective_seconds": null,
    "is_backup_restore_rto": false
  },
  "recovery_point": {
    "status": "not_established",
    "objective_seconds": null,
    "measured_seconds": null
  },
  "schema_consistency": {
    "consistent": true,
    "baseline_catalog_union_sha256": "...",
    "restored_catalog_union_sha256": "..."
  }
}
```

A `logical_backup` run adds `backup_creation_duration_seconds` to
`recovery_time`, an `observed_recovery_point` block to `recovery_point`, and a
top-level `data_consistency` section. `migration_replay` artifacts keep the
shape shown above.

`check_evidence_invariants` runs before a `BLOCKED` or measured artifact is
written and rejects any record that contradicts itself: a measured duration that
is not a non-negative number, an unestablished objective carrying a value, a
consistency flag that disagrees with the recorded fingerprints or probe, an
observed recovery point with nothing observed, a backup run missing its creation
time, or a non-backup backend claiming `is_backup_restore_rto`.

Every outcome carries both recovery sections. A `BLOCKED` or `FAILED` run still
reports `recovery_point.status = not_established`, so a failure never quietly
drops the recovery point disclosure. On those runs `recovery_time.status` is
`not_measured`, which is distinct from the objective being `not_established`.

The artifact intentionally carries no DSN, host, port, database name, or
credential material. Driver errors quote the connection they failed on, so a
`FAILED` artifact records `error_type` plus, for errors this repository authors
itself, the message; any other message is withheld.

## Disposable target enforcement

Both backends re-check the live connection immediately before every destructive
step — before the migrations run, before `pg_dump`, before the schema is
dropped, and before `pg_restore`. `assert_disposable_target` queries
`current_database()`, `current_user`, and `application_name` from the server and
compares them with the validated contract, then confirms the disposable marker
is part of the database name.

Parsing the DSN proves what was asked for; this proves what the server actually
is. Any mismatch raises `DisposableTargetError` and the run stops before it
writes anything. There is no fallback to another container or an existing
database. The listening port is not compared server-side, because a container
publishes a different port than it listens on; the DSN contract already pins the
port that was dialled.

The dump file is written outside the repository, is never committed, and is
deleted in a `finally` block once the run ends.

## Extending this to physical or point-in-time recovery

Each backend implements three steps: `prepare` (reach a baseline and fingerprint
it), `inject_loss` (destroy what has to be recovered), and `restore` (recover
and return the post-restore state). `PostgresLogicalBackupRecoveryBackend` shows
the shape a real backup backend takes.

A physical or point-in-time backend would follow the same seam and reuse the
artifact contract, timing separation, and invariant checks. Only then could
`recovery_point` carry a measured data-loss window rather than an observed dump
instant.

## Measurement status

| Layer | Status |
| --- | --- |
| Artifact contract, invariants, consistency reuse (no database) | verified by `tests/test_recovery_objective_benchmark.py` |
| `migration_replay` measured run | measured on PostgreSQL 17 (`server_version_num` 170010) |
| `logical_backup` measured run | measured on PostgreSQL 17, real `pg_dump` / `pg_restore` |

### `migration_replay`

Three consecutive runs, all `PASS` with `consistent = true`:

| Run | `migration_forward_restore_duration_seconds` |
| --- | --- |
| 1 | 0.070052 |
| 2 | 0.078473 |
| 3 | 0.095777 |

### `logical_backup`

Three runs, each against a **freshly created disposable container** so no run
inherits state from another. All `PASS`, schema and data consistent, and
`post_backup_write_restored = false` every time:

| Run | `backup_creation_duration_seconds` | `logical_backup_restore_duration_seconds` | dump bytes |
| --- | --- | --- | --- |
| 1 | 0.643181 | 3.079792 | 154173 |
| 2 | 0.703919 | 3.233122 | 154173 |
| 3 | 0.699796 | 3.350510 | 154173 |

Every run in both tables produced the same catalog union fingerprint before the
loss and after the restore:
`d35a066a5cd1816bd4bd3fdd42c2952a2f9b0e98b3474ba7c0f8fe56463212c3`. The two
backends agreeing on that fingerprint is a useful cross-check: the logical
restore rebuilds exactly the catalogue the migrations produce.

The dump's own SHA-256 differs between runs because the custom format embeds
timestamps, so the dump digest identifies one artifact rather than acting as a
reproducibility check.

Restore is roughly four to five times slower than the dump here, and both are
database-level figures on a local throwaway container. They are not a service
recovery time and carry no agreed objective.

The measurements used throwaway containers that hold no service data. The
shared local database from `DE/compose.yaml` and any operational database are
out of bounds for this benchmark.

These runs were driven locally with placeholder external signer, SBOM, and
trusted-root inputs. The gate only checks that those inputs are present, so a
local run is not equivalent to one gated by the CI-held values.

## Running the benchmark

Unit contract tests, no database required:

```bash
cd service_db && pytest -q tests/test_recovery_objective_benchmark.py
```

A measured run selects its backend and requires a disposable PostgreSQL 17
instance with `pgcrypto`, plus the same external signer, SBOM, and trusted-root
inputs that gate the `P1-DB-01` replay. Missing inputs produce a `BLOCKED`
artifact before any connection is opened.

```bash
python service_db/scripts/benchmark_recovery_objective.py \
  --artifact <path outside the repo> \
  --backend logical_backup \
  --backup-dir <scratch dir outside the repo> \
  --dsn "<disposable DSN>" \
  --expected-host <host> --expected-port <port> --expected-user <user> \
  --expected-database <db> --disposable-marker disposable
```

Omit `--backend` for the `migration_replay` drill. `pg_dump` and `pg_restore`
are taken from `PATH` and can be overridden with `--pg-dump` / `--pg-restore` or
`SERVICE_DB_PG_DUMP` / `SERVICE_DB_PG_RESTORE`.

Never point this benchmark at the shared local database from
`DE/compose.yaml` or at any operational database. Both backends execute
`DROP SCHEMA IF EXISTS app CASCADE`. The disposable DSN contract inherited from
`P1-DB-01` enforces the expected host, port, user, database name, and
`application_name` marker, and the live connection is re-checked before every
destructive step.
