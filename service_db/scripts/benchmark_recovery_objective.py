#!/usr/bin/env python3
"""Benchmark the service DB recovery objective on top of the fixed replay drill.

This layer measures how long a *migration* forward restore takes and whether the
restored catalog still matches its pre-rollback baseline.  It deliberately does
not claim to measure a backup restore.  This repository defines no backup
mechanism, so the recovery point objective stays ``not_established`` and the
recovery time objective stays unset until an operator agrees to one.

The recovery mechanism is isolated behind a backend object so that an actual
PostgreSQL backup/restore can be added later without changing this artifact
contract.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urlsplit, urlunsplit

# scripts/ is not a package. run_fixed_migration_replay.py relies on the script
# directory already being on sys.path; this module is also loaded by file path
# from the tests, so it puts the directory there itself before importing.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import verify_fixed_migration_replay as replay  # noqa: E402


BENCHMARK_CONTRACT = "service-db-recovery-objective-v1"
WBS_ID = "P2-DB-01"
MIGRATION_REPLAY_BACKEND = "migration_replay"
LOGICAL_BACKUP_BACKEND = "logical_backup"

RECOVERY_TIME_METRIC = "migration_forward_restore_duration_seconds"
RECOVERY_TIME_SCOPE_START = "forward restore migration execution begins"
RECOVERY_TIME_SCOPE_END = "post-restore catalog union fingerprint verified"

LOGICAL_RESTORE_METRIC = "logical_backup_restore_duration_seconds"
LOGICAL_RESTORE_SCOPE_START = "pg_restore invocation begins"
LOGICAL_RESTORE_SCOPE_END = "post-restore catalog fingerprint and probe data verified"
LOGICAL_BACKUP_DUMP_FORMAT = "custom"
LOGICAL_BACKUP_SCHEMA = "app"

STATUS_MEASURED = "measured"
STATUS_NOT_MEASURED = "not_measured"
STATUS_NOT_ESTABLISHED = "not_established"
STATUS_OBSERVED = "observed"

RECOVERY_POINT_KIND_LOGICAL_BACKUP = "logical_backup_snapshot"

# Deterministic, non-personal probe rows written into a migration-owned table so
# the drill proves rows come back, not just relations.
PROBE_AUTH_PROVIDER = "p2-db-01-probe"
PROBE_BEFORE_BACKUP = "probe-before-backup"
PROBE_AFTER_BACKUP = "probe-after-backup"
PROBE_FIXED_TIMESTAMP = "2026-01-01T00:00:00+00:00"

# Driver errors quote the connection they failed on, so only messages this
# repository authors itself are safe to copy into a published artifact.
WITHHELD_ERROR_DETAIL = "withheld to keep connection details out of evidence"

RECOVERY_TIME_BASIS = (
    "Measured value covers the migration forward restore and its catalog "
    "fingerprint verification only. It excludes instance provisioning, data "
    "restore, and application readiness, so it is a component of a recovery "
    "time objective rather than the objective itself."
)
RECOVERY_POINT_BASIS = (
    "No backup schedule, snapshot timestamp, WAL archive, or restore target "
    "point is defined in this repository, so there is no recovery point to "
    "measure. The replay drill drops and recreates schema objects without "
    "restoring any row, so it cannot stand in for a data recovery point."
)
LOGICAL_RESTORE_BASIS = (
    "Measured value covers pg_restore plus post-restore schema and probe data "
    "verification. It excludes instance provisioning and application readiness, "
    "and it excludes the separately reported backup creation. No recovery time "
    "objective has been agreed, so there is no target to compare it against."
)
LOGICAL_RECOVERY_POINT_BASIS = (
    "A logical dump fixes the recovery point at the moment the dump was taken, "
    "which this run records and demonstrates: a write made after the dump is "
    "not restored. That observed behaviour is not an agreed recovery point "
    "objective, and no allowable data-loss window has been set, so the "
    "objective stays unestablished. This drill covers logical backup only; it "
    "adds no WAL archiving, point-in-time recovery, or continuous replication."
)


class RecoveryBenchmarkError(RuntimeError):
    """A recovery benchmark invariant was not met."""


class DisposableTargetError(RecoveryBenchmarkError):
    """The live connection is not the validated disposable database."""


def assert_disposable_target(conn: Any, replay_dsn: Any) -> None:
    """Re-check the live connection right before a destructive step.

    Parsing the DSN proves what was asked for; this proves what the server
    actually is, so a redirected or reused connection cannot slip through.
    The listening port is deliberately not compared here because a container
    publishes a different port than the one it listens on; the DSN contract
    already pins the port that was dialled.
    """
    database, user, application_name = conn.execute(
        "SELECT current_database(), current_user, "
        "current_setting('application_name', true)"
    ).fetchone()
    mismatched = [
        field
        for field, observed, expected in (
            ("database", database, replay_dsn.database),
            ("user", user, replay_dsn.user),
            ("application_name", application_name, replay_dsn.marker),
        )
        if observed != expected
    ]
    if replay_dsn.marker not in (database or ""):
        mismatched.append("disposable_marker")
    if mismatched:
        raise DisposableTargetError(
            "live connection is not the disposable target: " + ", ".join(sorted(mismatched))
        )


def split_dsn_password(dsn: str) -> tuple[str, str | None]:
    """Move the password out of the URI so it never reaches a command line."""
    parsed = urlsplit(dsn)
    if parsed.password is None:
        return dsn, None
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    if parsed.username:
        host = f"{quote(parsed.username, safe='')}@{host}"
    return urlunsplit(parsed._replace(netloc=host)), unquote(parsed.password)


@dataclass(frozen=True)
class RecoveryMeasurement:
    """One timed restore observation and the fingerprints that bracket it."""

    duration_seconds: float
    baseline_fingerprint: str
    restored_fingerprint: str

    @property
    def consistent(self) -> bool:
        return self.baseline_fingerprint == self.restored_fingerprint


@dataclass(frozen=True)
class MigrationReplayRecoveryBackend:
    """Recovery backend that reuses the fixed migration rollback/restore pair.

    A future backup-based backend implements the same three steps: bring the
    disposable database to a baseline, inject the loss, then restore and report
    the post-restore fingerprint.
    """

    migrations_dir: Path
    rollback_dir: Path
    name: str = MIGRATION_REPLAY_BACKEND

    def _paths(self) -> tuple[Path, Path]:
        return replay._rollback_restore_paths(
            migrations_dir=self.migrations_dir,
            rollback_dir=self.rollback_dir,
        )

    def describe(self) -> dict[str, Any]:
        """Repository-relative identifiers for the replayed pair."""
        rollback_script, forward_migration = self._paths()
        return {
            "backend": self.name,
            "rollback_script": rollback_script.name,
            "forward_migration": forward_migration.name,
            "fixed_migration_count": len(replay.FIXED_MIGRATIONS),
        }

    def prepare(self, conn: Any) -> str:
        """Replay every fixed migration and fingerprint the resulting baseline."""
        migrations = replay._assert_fixed_migration_files(self.migrations_dir)
        replay._preflight_pg17(conn)
        replay._execute_pass(conn, migrations)
        return replay._catalog_fingerprint(conn)

    def inject_loss(self, conn: Any) -> None:
        """Run the rollback script. This is the drill's simulated failure."""
        rollback_script, _ = self._paths()
        replay._execute_migration_script(conn, script=rollback_script)

    def restore(self, conn: Any) -> str:
        """Restore and verify. Every step here is inside the measured window."""
        _, forward_migration = self._paths()
        replay._execute_migration_script(conn, script=forward_migration)
        return replay._catalog_fingerprint(conn)


def measure_recovery(
    backend: MigrationReplayRecoveryBackend,
    conn: Any,
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> RecoveryMeasurement:
    """Time the restore leg only. Baseline and injected loss stay outside it."""
    baseline_fingerprint = backend.prepare(conn)
    backend.inject_loss(conn)
    started = clock()
    restored_fingerprint = backend.restore(conn)
    duration_seconds = clock() - started
    if duration_seconds < 0:
        raise RecoveryBenchmarkError("recovery clock produced a negative duration")
    return RecoveryMeasurement(
        duration_seconds=duration_seconds,
        baseline_fingerprint=baseline_fingerprint,
        restored_fingerprint=restored_fingerprint,
    )


@dataclass(frozen=True)
class LogicalBackupMeasurement:
    """One timed pg_restore observation plus the snapshot it restored from."""

    restore_duration_seconds: float
    backup_creation_duration_seconds: float
    baseline_fingerprint: str
    restored_fingerprint: str
    probe_rows_before_backup: int
    probe_rows_after_restore: int
    probe_digest_before_backup: str
    probe_digest_after_restore: str
    post_backup_write_restored: bool
    backup_started_at: str
    backup_completed_at: str
    backup_artifact: dict[str, Any] = field(default_factory=dict)

    @property
    def schema_consistent(self) -> bool:
        return self.baseline_fingerprint == self.restored_fingerprint

    @property
    def data_consistent(self) -> bool:
        return (
            self.probe_rows_before_backup == self.probe_rows_after_restore
            and self.probe_digest_before_backup == self.probe_digest_after_restore
            and not self.post_backup_write_restored
        )

    @property
    def consistent(self) -> bool:
        return self.schema_consistent and self.data_consistent


@dataclass(frozen=True)
class PostgresLogicalBackupRecoveryBackend:
    """Recovery backend driven by a real pg_dump / pg_restore pair.

    It keeps the same three steps as the migration backend, but each one means
    what it says for a backup drill: ``prepare`` seeds probe rows and writes a
    dump file, ``inject_loss`` destroys the schema so recovery must come from
    that file, and ``restore`` runs pg_restore and verifies what came back.

    This is logical backup only. It adds no WAL archiving, point-in-time
    recovery, or replication.
    """

    migrations_dir: Path
    backup_path: Path
    replay_dsn: Any
    dump_executable: str = "pg_dump"
    restore_executable: str = "pg_restore"
    name: str = LOGICAL_BACKUP_BACKEND

    def describe(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "dump_format": LOGICAL_BACKUP_DUMP_FORMAT,
            "dumped_schema": LOGICAL_BACKUP_SCHEMA,
            "dump_executable": Path(self.dump_executable).stem,
            "restore_executable": Path(self.restore_executable).stem,
            "fixed_migration_count": len(replay.FIXED_MIGRATIONS),
        }

    def _run_pg_tool(self, executable: str, args: list[str]) -> None:
        dsn, password = split_dsn_password(self.replay_dsn.dsn)
        env = dict(os.environ)
        if password is not None:
            env["PGPASSWORD"] = password
        completed = subprocess.run(
            [executable, "--dbname", dsn, *args],
            capture_output=True,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            # stderr quotes the connection it failed on, so only the exit
            # status is surfaced; the detail never reaches the artifact.
            raise RecoveryBenchmarkError(
                f"{Path(executable).stem} exited with code {completed.returncode}"
            )

    def _insert_probe(self, conn: Any, provider_user_id: str) -> None:
        conn.execute(
            "INSERT INTO app.users "
            "(email, name, auth_provider, provider_user_id, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (auth_provider, provider_user_id) DO NOTHING",
            (
                f"{provider_user_id}@example.invalid",
                provider_user_id,
                PROBE_AUTH_PROVIDER,
                provider_user_id,
                PROBE_FIXED_TIMESTAMP,
                PROBE_FIXED_TIMESTAMP,
            ),
        )

    def _probe_state(self, conn: Any) -> tuple[int, str]:
        rows, digest = conn.execute(
            "SELECT count(*)::bigint, "
            "encode(digest(coalesce(string_agg("
            "email || '|' || provider_user_id, ',' ORDER BY provider_user_id"
            "), ''), 'sha256'), 'hex') "
            "FROM app.users WHERE auth_provider = %s",
            (PROBE_AUTH_PROVIDER,),
        ).fetchone()
        return int(rows), digest

    def _probe_present(self, conn: Any, provider_user_id: str) -> bool:
        (found,) = conn.execute(
            "SELECT count(*)::bigint FROM app.users "
            "WHERE auth_provider = %s AND provider_user_id = %s",
            (PROBE_AUTH_PROVIDER, provider_user_id),
        ).fetchone()
        return int(found) > 0

    def _backup_artifact_digest(self) -> dict[str, Any]:
        payload = self.backup_path.read_bytes()
        return {
            # Basename only. An absolute path would leak the local filesystem.
            "name": self.backup_path.name,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def prepare(self, conn: Any) -> dict[str, Any]:
        """Build the schema, seed a probe row, then dump it to a real file."""
        assert_disposable_target(conn, self.replay_dsn)
        migrations = replay._assert_fixed_migration_files(self.migrations_dir)
        replay._preflight_pg17(conn)
        replay._execute_pass(conn, migrations)
        self._insert_probe(conn, PROBE_BEFORE_BACKUP)
        baseline_fingerprint = replay._catalog_fingerprint(conn)
        probe_rows, probe_digest = self._probe_state(conn)

        assert_disposable_target(conn, self.replay_dsn)
        backup_started_at = _utc_now()
        started = time.perf_counter()
        self._run_pg_tool(
            self.dump_executable,
            [
                f"--format={LOGICAL_BACKUP_DUMP_FORMAT}",
                f"--schema={LOGICAL_BACKUP_SCHEMA}",
                "--file",
                str(self.backup_path),
            ],
        )
        backup_creation_duration = time.perf_counter() - started
        backup_completed_at = _utc_now()

        # Written after the dump, so a correct restore must not bring it back.
        self._insert_probe(conn, PROBE_AFTER_BACKUP)
        return {
            "baseline_fingerprint": baseline_fingerprint,
            "probe_rows_before_backup": probe_rows,
            "probe_digest_before_backup": probe_digest,
            "backup_creation_duration_seconds": backup_creation_duration,
            "backup_started_at": backup_started_at,
            "backup_completed_at": backup_completed_at,
            "backup_artifact": self._backup_artifact_digest(),
        }

    def inject_loss(self, conn: Any) -> None:
        """Destroy the schema so recovery has to come from the dump file."""
        assert_disposable_target(conn, self.replay_dsn)
        replay._reset_disposable_schema(conn)

    def restore(self, conn: Any, prepared: dict[str, Any]) -> dict[str, Any]:
        """Run pg_restore and verify. Every step here is inside the timer."""
        assert_disposable_target(conn, self.replay_dsn)
        self._run_pg_tool(self.restore_executable, ["--no-owner", "--exit-on-error", str(self.backup_path)])
        restored_fingerprint = replay._catalog_fingerprint(conn)
        probe_rows, probe_digest = self._probe_state(conn)
        return {
            "restored_fingerprint": restored_fingerprint,
            "probe_rows_after_restore": probe_rows,
            "probe_digest_after_restore": probe_digest,
            "post_backup_write_restored": self._probe_present(conn, PROBE_AFTER_BACKUP),
        }

    def cleanup(self) -> None:
        """Remove the dump file. It is working data, never evidence."""
        self.backup_path.unlink(missing_ok=True)


def measure_logical_recovery(
    backend: PostgresLogicalBackupRecoveryBackend,
    conn: Any,
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> LogicalBackupMeasurement:
    """Time the pg_restore leg only. Dump creation is reported separately."""
    prepared = backend.prepare(conn)
    backend.inject_loss(conn)
    started = clock()
    restored = backend.restore(conn, prepared)
    restore_duration = clock() - started
    if restore_duration < 0:
        raise RecoveryBenchmarkError("recovery clock produced a negative duration")
    return LogicalBackupMeasurement(
        restore_duration_seconds=restore_duration,
        backup_creation_duration_seconds=prepared["backup_creation_duration_seconds"],
        baseline_fingerprint=prepared["baseline_fingerprint"],
        restored_fingerprint=restored["restored_fingerprint"],
        probe_rows_before_backup=prepared["probe_rows_before_backup"],
        probe_rows_after_restore=restored["probe_rows_after_restore"],
        probe_digest_before_backup=prepared["probe_digest_before_backup"],
        probe_digest_after_restore=restored["probe_digest_after_restore"],
        post_backup_write_restored=restored["post_backup_write_restored"],
        backup_started_at=prepared["backup_started_at"],
        backup_completed_at=prepared["backup_completed_at"],
        backup_artifact=prepared["backup_artifact"],
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_artifact(
    measurement: RecoveryMeasurement,
    *,
    target: dict[str, Any],
    measured_at: str,
) -> dict[str, Any]:
    """Assemble the evidence record for one benchmarked recovery."""
    return {
        "contract": BENCHMARK_CONTRACT,
        "wbs_id": WBS_ID,
        "status": "PASS" if measurement.consistent else "FAILED",
        "measured_at": measured_at,
        "recovery_target": target,
        "recovery_time": {
            "status": STATUS_MEASURED,
            "metric_name": RECOVERY_TIME_METRIC,
            "measured_seconds": round(measurement.duration_seconds, 6),
            "measurement_scope": {
                "start": RECOVERY_TIME_SCOPE_START,
                "end": RECOVERY_TIME_SCOPE_END,
            },
            "objective_status": STATUS_NOT_ESTABLISHED,
            "objective_seconds": None,
            "is_backup_restore_rto": False,
            "basis": RECOVERY_TIME_BASIS,
        },
        "recovery_point": {
            "status": STATUS_NOT_ESTABLISHED,
            "objective_seconds": None,
            "measured_seconds": None,
            "basis": RECOVERY_POINT_BASIS,
        },
        "schema_consistency": {
            "consistent": measurement.consistent,
            "baseline_catalog_union_sha256": measurement.baseline_fingerprint,
            "restored_catalog_union_sha256": measurement.restored_fingerprint,
            "source": "service_db/scripts/verify_fixed_migration_replay.py",
        },
    }


def build_logical_backup_artifact(
    measurement: LogicalBackupMeasurement,
    *,
    target: dict[str, Any],
    measured_at: str,
) -> dict[str, Any]:
    """Assemble the evidence record for one real backup/restore drill."""
    return {
        "contract": BENCHMARK_CONTRACT,
        "wbs_id": WBS_ID,
        "status": "PASS" if measurement.consistent else "FAILED",
        "measured_at": measured_at,
        "recovery_target": target,
        "recovery_time": {
            "status": STATUS_MEASURED,
            "metric_name": LOGICAL_RESTORE_METRIC,
            "measured_seconds": round(measurement.restore_duration_seconds, 6),
            "backup_creation_duration_seconds": round(
                measurement.backup_creation_duration_seconds, 6
            ),
            "measurement_scope": {
                "start": LOGICAL_RESTORE_SCOPE_START,
                "end": LOGICAL_RESTORE_SCOPE_END,
            },
            "objective_status": STATUS_NOT_ESTABLISHED,
            "objective_seconds": None,
            "is_backup_restore_rto": True,
            "basis": LOGICAL_RESTORE_BASIS,
        },
        "recovery_point": {
            "status": STATUS_OBSERVED,
            "objective_status": STATUS_NOT_ESTABLISHED,
            "objective_seconds": None,
            "measured_seconds": None,
            "basis": LOGICAL_RECOVERY_POINT_BASIS,
            "observed_recovery_point": {
                "kind": RECOVERY_POINT_KIND_LOGICAL_BACKUP,
                "backup_started_at": measurement.backup_started_at,
                "backup_completed_at": measurement.backup_completed_at,
                "post_backup_write_restored": measurement.post_backup_write_restored,
                "backup_artifact": measurement.backup_artifact,
            },
        },
        "schema_consistency": {
            "consistent": measurement.schema_consistent,
            "baseline_catalog_union_sha256": measurement.baseline_fingerprint,
            "restored_catalog_union_sha256": measurement.restored_fingerprint,
            "source": "service_db/scripts/verify_fixed_migration_replay.py",
        },
        "data_consistency": {
            "consistent": measurement.data_consistent,
            "probe_rows_before_backup": measurement.probe_rows_before_backup,
            "probe_rows_after_restore": measurement.probe_rows_after_restore,
            "probe_digest_before_backup": measurement.probe_digest_before_backup,
            "probe_digest_after_restore": measurement.probe_digest_after_restore,
            "post_backup_write_restored": measurement.post_backup_write_restored,
        },
    }


def unmeasured_recovery_sections() -> dict[str, Any]:
    """Recovery sections for a run that produced no measurement.

    A blocked or failed run still has to disclose that no recovery point
    objective exists, so every artifact carries both sections.
    """
    return {
        "recovery_time": {
            "status": STATUS_NOT_MEASURED,
            "metric_name": RECOVERY_TIME_METRIC,
            "measured_seconds": None,
            "objective_status": STATUS_NOT_ESTABLISHED,
            "objective_seconds": None,
            "is_backup_restore_rto": False,
            "basis": RECOVERY_TIME_BASIS,
        },
        "recovery_point": {
            "status": STATUS_NOT_ESTABLISHED,
            "objective_seconds": None,
            "measured_seconds": None,
            "basis": RECOVERY_POINT_BASIS,
        },
    }


def blocked_artifact(missing: list[str], *, measured_at: str) -> dict[str, Any]:
    """Record a run that never opened a connection, mirroring the P1 gate."""
    return {
        "contract": BENCHMARK_CONTRACT,
        "wbs_id": WBS_ID,
        "status": "BLOCKED",
        "measured_at": measured_at,
        "missing_external_inputs": missing,
        **unmeasured_recovery_sections(),
    }


def failed_artifact(error: BaseException, *, measured_at: str) -> dict[str, Any]:
    """Record a failure without echoing the connection back into evidence."""
    authored = isinstance(error, (replay.ReplayContractError, RecoveryBenchmarkError))
    return {
        "contract": BENCHMARK_CONTRACT,
        "wbs_id": WBS_ID,
        "status": "FAILED",
        "measured_at": measured_at,
        "error_type": type(error).__name__,
        "error": str(error) if authored else WITHHELD_ERROR_DETAIL,
        **unmeasured_recovery_sections(),
    }


def check_evidence_invariants(artifact: dict[str, Any]) -> None:
    """Reject any artifact whose stated status contradicts its own values."""
    recovery_time = artifact.get("recovery_time", {})
    recovery_point = artifact.get("recovery_point", {})

    measured = recovery_time.get("measured_seconds")
    if recovery_time.get("status") == STATUS_MEASURED:
        if not isinstance(measured, (int, float)) or isinstance(measured, bool):
            raise RecoveryBenchmarkError("measured recovery time must be a number")
        if measured < 0:
            raise RecoveryBenchmarkError("measured recovery time must not be negative")
    elif measured is not None:
        raise RecoveryBenchmarkError("unmeasured recovery time must not carry a value")

    for section, label in ((recovery_time, "recovery time"), (recovery_point, "recovery point")):
        status_key = "objective_status" if "objective_status" in section else "status"
        if section.get(status_key) == STATUS_NOT_ESTABLISHED and section.get("objective_seconds") is not None:
            raise RecoveryBenchmarkError(f"unestablished {label} objective must stay null")

    if recovery_point.get("status") != STATUS_MEASURED and recovery_point.get("measured_seconds") is not None:
        raise RecoveryBenchmarkError("unmeasured recovery point must not carry a value")

    backend = artifact.get("recovery_target", {}).get("backend")
    if recovery_time.get("is_backup_restore_rto") and backend != LOGICAL_BACKUP_BACKEND:
        raise RecoveryBenchmarkError(
            "only a real backup restore may be labelled a backup restore RTO"
        )
    if backend == LOGICAL_BACKUP_BACKEND:
        if not isinstance(recovery_time.get("backup_creation_duration_seconds"), (int, float)):
            raise RecoveryBenchmarkError("a backup restore must report its backup creation time")
        if recovery_time["backup_creation_duration_seconds"] < 0:
            raise RecoveryBenchmarkError("backup creation time must not be negative")

    if recovery_point.get("status") == STATUS_OBSERVED and not recovery_point.get(
        "observed_recovery_point"
    ):
        raise RecoveryBenchmarkError("an observed recovery point must record what was observed")

    consistency = artifact.get("schema_consistency")
    if consistency is not None:
        baseline = consistency.get("baseline_catalog_union_sha256")
        restored = consistency.get("restored_catalog_union_sha256")
        if consistency.get("consistent") != (baseline == restored):
            raise RecoveryBenchmarkError("consistency flag contradicts the recorded fingerprints")
        if artifact.get("status") == "PASS" and not consistency.get("consistent"):
            raise RecoveryBenchmarkError("PASS requires a consistent post-restore catalog")

    data = artifact.get("data_consistency")
    if data is not None:
        restored_snapshot = (
            data.get("probe_rows_before_backup") == data.get("probe_rows_after_restore")
            and data.get("probe_digest_before_backup") == data.get("probe_digest_after_restore")
            and not data.get("post_backup_write_restored")
        )
        if data.get("consistent") != restored_snapshot:
            raise RecoveryBenchmarkError("data consistency flag contradicts the recorded probe")
        if artifact.get("status") == "PASS" and not data.get("consistent"):
            raise RecoveryBenchmarkError("PASS requires the probe data to come back intact")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument(
        "--backend",
        choices=(MIGRATION_REPLAY_BACKEND, LOGICAL_BACKUP_BACKEND),
        default=MIGRATION_REPLAY_BACKEND,
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="Directory for the dump file. Required by the logical_backup backend. "
        "Keep it outside the repository; the file is working data, not evidence.",
    )
    parser.add_argument("--pg-dump", default=os.getenv("SERVICE_DB_PG_DUMP", "pg_dump"))
    parser.add_argument("--pg-restore", default=os.getenv("SERVICE_DB_PG_RESTORE", "pg_restore"))
    parser.add_argument("--dsn", default=os.getenv("SERVICE_DB_REPLAY_DSN"))
    parser.add_argument("--expected-host", default=os.getenv("SERVICE_DB_REPLAY_EXPECTED_HOST"))
    parser.add_argument("--expected-port", default=os.getenv("SERVICE_DB_REPLAY_EXPECTED_PORT"))
    parser.add_argument("--expected-user", default=os.getenv("SERVICE_DB_REPLAY_EXPECTED_USER"))
    parser.add_argument("--expected-database", default=os.getenv("SERVICE_DB_REPLAY_EXPECTED_DATABASE"))
    parser.add_argument("--disposable-marker", default=os.getenv("SERVICE_DB_REPLAY_DISPOSABLE_MARKER"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    measured_at = _utc_now()

    missing = replay.missing_external_inputs(dict(os.environ))
    if missing:
        artifact = blocked_artifact(missing, measured_at=measured_at)
        check_evidence_invariants(artifact)
        replay.write_artifact(args.artifact, artifact)
        return 2

    try:
        replay_dsn = replay.validate_disposable_dsn(
            args.dsn,
            expected_host=args.expected_host,
            expected_port=args.expected_port,
            expected_user=args.expected_user,
            expected_database=args.expected_database,
            disposable_marker=args.disposable_marker,
        )
        service_db_root = Path(__file__).resolve().parents[1]
        migrations_dir = service_db_root / "migrations"
        import psycopg

        if args.backend == LOGICAL_BACKUP_BACKEND:
            if args.backup_dir is None:
                raise RecoveryBenchmarkError("the logical_backup backend requires --backup-dir")
            args.backup_dir.mkdir(parents=True, exist_ok=True)
            backend = PostgresLogicalBackupRecoveryBackend(
                migrations_dir=migrations_dir,
                backup_path=args.backup_dir / "service-db-logical-backup.dump",
                replay_dsn=replay_dsn,
                dump_executable=args.pg_dump,
                restore_executable=args.pg_restore,
            )
            target = backend.describe()
            try:
                with psycopg.connect(replay_dsn.dsn, autocommit=True) as conn:
                    measurement = measure_logical_recovery(backend, conn)
            finally:
                backend.cleanup()
            artifact = build_logical_backup_artifact(
                measurement, target=target, measured_at=measured_at
            )
        else:
            backend = MigrationReplayRecoveryBackend(
                migrations_dir=migrations_dir,
                rollback_dir=service_db_root / "rollbacks",
            )
            target = backend.describe()
            with psycopg.connect(replay_dsn.dsn, autocommit=True) as conn:
                measurement = measure_recovery(backend, conn)
            artifact = build_artifact(measurement, target=target, measured_at=measured_at)

        check_evidence_invariants(artifact)
        replay.write_artifact(args.artifact, artifact)
        return 0 if artifact["status"] == "PASS" else 1
    except Exception as error:
        replay.write_artifact(args.artifact, failed_artifact(error, measured_at=measured_at))
        return 1


if __name__ == "__main__":
    sys.exit(main())
