"""Contract tests for the P2 recovery objective benchmark layer."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SERVICE_DB_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = SERVICE_DB_ROOT / "scripts" / "benchmark_recovery_objective.py"

EXTERNAL_INPUTS = {
    "SERVICE_DB_REPLAY_EXTERNAL_SIGNER": "test-signer",
    "SERVICE_DB_REPLAY_SBOM": "test-sbom",
    "SERVICE_DB_REPLAY_TRUSTED_ROOT": "test-root",
}
DISPOSABLE_ARGS = [
    "--dsn",
    "postgresql://replay:test@127.0.0.1:5433/p0_replay_disposable?application_name=disposable",
    "--expected-host",
    "127.0.0.1",
    "--expected-port",
    "5433",
    "--expected-user",
    "replay",
    "--expected-database",
    "p0_replay_disposable",
    "--disposable-marker",
    "disposable",
]


def _load_benchmark():
    spec = importlib.util.spec_from_file_location("service_db_recovery_benchmark", BENCHMARK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _RecordingConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, statement: str) -> None:
        self.executed.append(statement)

    def commit(self) -> None:
        return None


def _stub_replay(monkeypatch, benchmark, fingerprints: list[str]) -> None:
    """Keep the fixed-migration file contract real; stub only the SQL round trips."""
    monkeypatch.setattr(benchmark.replay, "_preflight_pg17", lambda _conn: None)
    monkeypatch.setattr(benchmark.replay, "_execute_pass", lambda _conn, _migrations: None)
    values = iter(fingerprints)
    monkeypatch.setattr(benchmark.replay, "_catalog_fingerprint", lambda _conn: next(values))


def _backend(benchmark):
    return benchmark.MigrationReplayRecoveryBackend(
        migrations_dir=SERVICE_DB_ROOT / "migrations",
        rollback_dir=SERVICE_DB_ROOT / "rollbacks",
    )


def _run_main(monkeypatch, tmp_path, fingerprints: list[str], *, with_inputs: bool = True):
    benchmark = _load_benchmark()
    connection = _RecordingConnection()
    for name, value in EXTERNAL_INPUTS.items():
        if with_inputs:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_args, **_kwargs: connection),
    )
    _stub_replay(monkeypatch, benchmark, fingerprints)
    artifact_path = tmp_path / "recovery-objective.json"
    exit_code = benchmark.main(["--artifact", str(artifact_path), *DISPOSABLE_ARGS])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    return benchmark, exit_code, connection, artifact


def test_benchmark_times_only_the_restore_leg_after_the_injected_rollback(monkeypatch, tmp_path):
    benchmark = _load_benchmark()
    _stub_replay(monkeypatch, benchmark, ["baseline", "baseline"])
    connection = _RecordingConnection()
    ticks = iter([10.0, 10.25])
    measurement = benchmark.measure_recovery(
        _backend(benchmark), connection, clock=lambda: next(ticks)
    )

    rollback = (SERVICE_DB_ROOT / "rollbacks" / benchmark.replay.ROLLBACK_RESTORE_SCRIPT).read_text(
        encoding="utf-8"
    )
    forward = (SERVICE_DB_ROOT / "migrations" / benchmark.replay.ROLLBACK_RESTORE_MIGRATION).read_text(
        encoding="utf-8"
    )
    assert connection.executed == [rollback, forward]
    assert measurement.duration_seconds == pytest.approx(0.25)
    assert measurement.consistent is True


def test_measured_duration_is_a_non_negative_number(monkeypatch, tmp_path):
    _benchmark, exit_code, _connection, artifact = _run_main(
        monkeypatch, tmp_path, ["baseline", "baseline"]
    )
    measured = artifact["recovery_time"]["measured_seconds"]

    assert exit_code == 0
    assert artifact["status"] == "PASS"
    assert isinstance(measured, (int, float)) and not isinstance(measured, bool)
    assert measured >= 0


def test_measurement_scope_is_explicit_and_not_called_a_backup_restore(monkeypatch, tmp_path):
    benchmark, _exit_code, _connection, artifact = _run_main(
        monkeypatch, tmp_path, ["baseline", "baseline"]
    )
    recovery_time = artifact["recovery_time"]

    assert recovery_time["metric_name"] == "migration_forward_restore_duration_seconds"
    assert recovery_time["measurement_scope"]["start"] == benchmark.RECOVERY_TIME_SCOPE_START
    assert recovery_time["measurement_scope"]["end"] == benchmark.RECOVERY_TIME_SCOPE_END
    assert recovery_time["is_backup_restore_rto"] is False
    assert artifact["recovery_target"]["backend"] == "migration_replay"


def test_recovery_point_objective_is_never_filled_with_zero(monkeypatch, tmp_path):
    _benchmark, _exit_code, _connection, artifact = _run_main(
        monkeypatch, tmp_path, ["baseline", "baseline"]
    )
    recovery_point = artifact["recovery_point"]

    assert recovery_point["status"] == "not_established"
    assert recovery_point["objective_seconds"] is None
    assert recovery_point["measured_seconds"] is None
    assert recovery_point["basis"]


def test_recovery_time_objective_stays_unset_even_though_a_value_was_measured(monkeypatch, tmp_path):
    _benchmark, _exit_code, _connection, artifact = _run_main(
        monkeypatch, tmp_path, ["baseline", "baseline"]
    )
    recovery_time = artifact["recovery_time"]

    assert recovery_time["status"] == "measured"
    assert recovery_time["objective_status"] == "not_established"
    assert recovery_time["objective_seconds"] is None


def test_consistency_reuses_the_replay_catalog_fingerprints(monkeypatch, tmp_path):
    _benchmark, _exit_code, _connection, artifact = _run_main(
        monkeypatch, tmp_path, ["baseline", "baseline"]
    )
    consistency = artifact["schema_consistency"]

    assert consistency["consistent"] is True
    assert consistency["baseline_catalog_union_sha256"] == "baseline"
    assert consistency["restored_catalog_union_sha256"] == "baseline"
    assert consistency["source"].endswith("verify_fixed_migration_replay.py")


def test_a_drifted_post_restore_catalog_fails_the_benchmark(monkeypatch, tmp_path):
    _benchmark, exit_code, _connection, artifact = _run_main(
        monkeypatch, tmp_path, ["baseline", "changed"]
    )

    assert exit_code == 1
    assert artifact["status"] == "FAILED"
    assert artifact["schema_consistency"]["consistent"] is False


def test_missing_external_inputs_block_before_any_connection(monkeypatch, tmp_path):
    _benchmark, exit_code, connection, artifact = _run_main(
        monkeypatch, tmp_path, ["baseline", "baseline"], with_inputs=False
    )

    assert exit_code == 2
    assert artifact["status"] == "BLOCKED"
    assert sorted(artifact["missing_external_inputs"]) == ["external_signer", "sbom", "trusted_root"]
    assert connection.executed == []
    assert artifact["recovery_time"]["measured_seconds"] is None
    assert artifact["recovery_point"]["objective_seconds"] is None


def _scan_for_dsn_material(artifact: dict) -> None:
    # The measured duration is the one field whose digits are unpredictable, so
    # it is normalised out before the port number is searched for as a substring.
    scanned = json.loads(json.dumps(artifact))
    scanned.get("recovery_time", {})["measured_seconds"] = None
    serialized = json.dumps(scanned)
    for secret in ("postgresql://", "p0_replay_disposable", "127.0.0.1", "replay:test", "test-signer", "5433"):
        assert secret not in serialized


def test_artifact_carries_no_dsn_or_credential_material(monkeypatch, tmp_path):
    _benchmark, _exit_code, _connection, artifact = _run_main(
        monkeypatch, tmp_path, ["baseline", "baseline"]
    )

    _scan_for_dsn_material(artifact)


def test_a_failed_connection_is_never_recorded_as_a_measured_run(monkeypatch, tmp_path):
    benchmark = _load_benchmark()
    for name, value in EXTERNAL_INPUTS.items():
        monkeypatch.setenv(name, value)

    def _refuse(*_args, **_kwargs):
        raise OSError("failed to resolve host '127.0.0.1' for p0_replay_disposable")

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=_refuse))
    artifact_path = tmp_path / "recovery-objective.json"
    exit_code = benchmark.main(["--artifact", str(artifact_path), *DISPOSABLE_ARGS])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert artifact["status"] == "FAILED"
    assert artifact["error_type"] == "OSError"
    assert artifact["error"] == benchmark.WITHHELD_ERROR_DETAIL
    # A failed run still has to disclose that no recovery point objective exists.
    assert artifact["recovery_time"]["measured_seconds"] is None
    assert artifact["recovery_point"]["status"] == "not_established"
    benchmark.check_evidence_invariants(artifact)
    _scan_for_dsn_material(artifact)


def test_a_contract_failure_keeps_its_own_authored_message(monkeypatch, tmp_path):
    benchmark = _load_benchmark()
    for name, value in EXTERNAL_INPUTS.items():
        monkeypatch.setenv(name, value)
    artifact_path = tmp_path / "recovery-objective.json"

    exit_code = benchmark.main(
        ["--artifact", str(artifact_path), "--dsn", "mysql://replay@127.0.0.1:5433/x"]
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert artifact["error_type"] == "ReplayContractError"
    assert artifact["error"] == "replay DSN must use postgres or postgresql"


class _FakeResult:
    def __init__(self, row) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _FakeBackupConnection:
    """Enough of a PostgreSQL connection to drive the logical backup backend."""

    def __init__(self, *, database="p0_replay_disposable", user="replay", app_name="disposable"):
        self.identity = (database, user, app_name)
        self.probe_rows: list[str] = []
        self.executed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def commit(self) -> None:
        return None

    @staticmethod
    def _digest(rows: list[str]) -> str:
        joined = ",".join(f"{r}@example.invalid|{r}" for r in sorted(rows))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def execute(self, statement: str, params=None):
        self.executed.append(statement)
        if "current_database()" in statement:
            return _FakeResult(self.identity)
        if statement.startswith("INSERT INTO app.users"):
            if params[3] not in self.probe_rows:
                self.probe_rows.append(params[3])
            return _FakeResult(None)
        if "AND provider_user_id = %s" in statement:
            return _FakeResult((1 if params[1] in self.probe_rows else 0,))
        if "FROM app.users WHERE auth_provider" in statement:
            return _FakeResult((len(self.probe_rows), self._digest(self.probe_rows)))
        if "DROP SCHEMA" in statement:
            self.probe_rows = []
            return _FakeResult(None)
        return _FakeResult(None)


class _FakePgTools:
    """Stand-in for the pg_dump/pg_restore binaries with real dump semantics."""

    def __init__(self, connection, *, dump_returncode=0, restore_returncode=0):
        self.connection = connection
        self.dump_returncode = dump_returncode
        self.restore_returncode = restore_returncode
        self.snapshot: list[str] | None = None
        self.commands: list[list[str]] = []
        self.passwords: list[str | None] = []

    def run(self, command, **kwargs):
        self.commands.append(command)
        self.passwords.append(kwargs.get("env", {}).get("PGPASSWORD"))
        executable = Path(command[0]).stem
        if executable == "pg_dump":
            if self.dump_returncode == 0:
                self.snapshot = list(self.connection.probe_rows)
                Path(command[command.index("--file") + 1]).write_bytes(b"fake-custom-dump")
            return SimpleNamespace(returncode=self.dump_returncode, stdout=b"", stderr=b"")
        if executable == "pg_restore":
            if self.restore_returncode == 0:
                self.connection.probe_rows = list(self.snapshot or [])
            return SimpleNamespace(returncode=self.restore_returncode, stdout=b"", stderr=b"")
        raise AssertionError(f"unexpected executable {executable}")


def _run_logical_main(monkeypatch, tmp_path, *, connection=None, fingerprints=None, tools=None):
    benchmark = _load_benchmark()
    connection = connection if connection is not None else _FakeBackupConnection()
    tools = tools if tools is not None else _FakePgTools(connection)
    for name, value in EXTERNAL_INPUTS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_a, **_k: connection),
    )
    _stub_replay(monkeypatch, benchmark, fingerprints or ["catalog", "catalog"])
    monkeypatch.setattr(benchmark.subprocess, "run", tools.run)
    backup_dir = tmp_path / "backups"
    artifact_path = tmp_path / "logical-backup.json"
    exit_code = benchmark.main(
        [
            "--artifact",
            str(artifact_path),
            "--backend",
            "logical_backup",
            "--backup-dir",
            str(backup_dir),
            *DISPOSABLE_ARGS,
        ]
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    return benchmark, exit_code, connection, tools, artifact, backup_dir


def test_logical_backup_run_reports_its_own_backend_and_metric(monkeypatch, tmp_path):
    _b, exit_code, _conn, tools, artifact, _dir = _run_logical_main(monkeypatch, tmp_path)

    assert exit_code == 0
    assert artifact["status"] == "PASS"
    assert artifact["recovery_target"]["backend"] == "logical_backup"
    assert artifact["recovery_target"]["dump_format"] == "custom"
    assert artifact["recovery_time"]["metric_name"] == "logical_backup_restore_duration_seconds"
    # A real backup restore may claim the label; the migration drill may not.
    assert artifact["recovery_time"]["is_backup_restore_rto"] is True
    assert [Path(c[0]).stem for c in tools.commands] == ["pg_dump", "pg_restore"]


def test_backup_creation_and_restore_durations_are_separate_non_negative_numbers(
    monkeypatch, tmp_path
):
    _b, _exit, _conn, _tools, artifact, _dir = _run_logical_main(monkeypatch, tmp_path)
    recovery_time = artifact["recovery_time"]

    for key in ("measured_seconds", "backup_creation_duration_seconds"):
        value = recovery_time[key]
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        assert value >= 0


def test_logical_backup_objectives_are_not_auto_filled_from_measurements(monkeypatch, tmp_path):
    _b, _exit, _conn, _tools, artifact, _dir = _run_logical_main(monkeypatch, tmp_path)

    assert artifact["recovery_time"]["objective_status"] == "not_established"
    assert artifact["recovery_time"]["objective_seconds"] is None
    assert artifact["recovery_point"]["objective_status"] == "not_established"
    assert artifact["recovery_point"]["objective_seconds"] is None
    # A dump gives an observed recovery point, never a quantified data-loss window.
    assert artifact["recovery_point"]["measured_seconds"] is None


def test_observed_recovery_point_records_the_dump_window(monkeypatch, tmp_path):
    _b, _exit, _conn, _tools, artifact, _dir = _run_logical_main(monkeypatch, tmp_path)
    observed = artifact["recovery_point"]["observed_recovery_point"]

    assert artifact["recovery_point"]["status"] == "observed"
    assert observed["kind"] == "logical_backup_snapshot"
    assert observed["backup_started_at"] and observed["backup_completed_at"]
    assert observed["backup_artifact"]["bytes"] > 0
    assert observed["backup_artifact"]["sha256"]


def test_restore_returns_the_pre_backup_row_and_drops_the_post_backup_write(monkeypatch, tmp_path):
    _b, _exit, connection, _tools, artifact, _dir = _run_logical_main(monkeypatch, tmp_path)
    data = artifact["data_consistency"]

    assert connection.probe_rows == ["probe-before-backup"]
    assert data["probe_rows_before_backup"] == 1
    assert data["probe_rows_after_restore"] == 1
    assert data["probe_digest_before_backup"] == data["probe_digest_after_restore"]
    assert data["post_backup_write_restored"] is False
    assert data["consistent"] is True
    assert artifact["schema_consistency"]["consistent"] is True


def test_a_restore_that_resurrects_the_post_backup_write_fails(monkeypatch, tmp_path):
    connection = _FakeBackupConnection()
    tools = _FakePgTools(connection)
    original_run = tools.run

    def _leaky_run(command, **kwargs):
        result = original_run(command, **kwargs)
        if Path(command[0]).stem == "pg_restore":
            connection.probe_rows.append("probe-after-backup")
        return result

    tools.run = _leaky_run
    _b, exit_code, _conn, _tools, artifact, _dir = _run_logical_main(
        monkeypatch, tmp_path, connection=connection, tools=tools
    )

    assert exit_code == 1
    assert artifact["status"] == "FAILED"
    assert artifact["data_consistency"]["post_backup_write_restored"] is True
    assert artifact["data_consistency"]["consistent"] is False


def test_a_drifted_catalog_after_logical_restore_fails(monkeypatch, tmp_path):
    _b, exit_code, _conn, _tools, artifact, _dir = _run_logical_main(
        monkeypatch, tmp_path, fingerprints=["catalog", "changed"]
    )

    assert exit_code == 1
    assert artifact["status"] == "FAILED"
    assert artifact["schema_consistency"]["consistent"] is False


@pytest.mark.parametrize("failing", ["dump", "restore"])
def test_a_failing_pg_tool_fails_the_run_without_quoting_the_connection(
    monkeypatch, tmp_path, failing
):
    connection = _FakeBackupConnection()
    tools = _FakePgTools(
        connection,
        dump_returncode=1 if failing == "dump" else 0,
        restore_returncode=1 if failing == "restore" else 0,
    )
    benchmark, exit_code, _conn, _tools, artifact, _dir = _run_logical_main(
        monkeypatch, tmp_path, connection=connection, tools=tools
    )

    assert exit_code == 1
    assert artifact["status"] == "FAILED"
    assert artifact["error"] == f"pg_{failing} exited with code 1"
    assert artifact["recovery_point"]["status"] == "not_established"
    _scan_for_dsn_material(artifact)
    benchmark.check_evidence_invariants(artifact)


def test_the_dump_file_is_removed_after_the_run(monkeypatch, tmp_path):
    _b, _exit, _conn, _tools, _artifact, backup_dir = _run_logical_main(monkeypatch, tmp_path)

    assert list(backup_dir.glob("*.dump")) == []


def test_the_password_never_reaches_the_pg_tool_command_line(monkeypatch, tmp_path):
    _b, _exit, _conn, tools, artifact, _dir = _run_logical_main(monkeypatch, tmp_path)

    for command in tools.commands:
        assert "test" not in command[command.index("--dbname") + 1].split("@")[0].split("//")[1]
    assert tools.passwords == ["test", "test"]
    _scan_for_dsn_material(artifact)


def test_a_target_that_is_not_the_disposable_database_stops_before_any_write(monkeypatch, tmp_path):
    connection = _FakeBackupConnection(database="quant_agent")
    benchmark, exit_code, _conn, tools, artifact, _dir = _run_logical_main(
        monkeypatch, tmp_path, connection=connection
    )

    assert exit_code == 1
    assert artifact["error_type"] == "DisposableTargetError"
    assert tools.commands == []
    assert not any("DROP SCHEMA" in s for s in connection.executed)
    assert not any(s.startswith("INSERT INTO app.users") for s in connection.executed)
    benchmark.check_evidence_invariants(artifact)


def test_the_migration_backend_may_not_claim_a_backup_restore_rto(monkeypatch, tmp_path):
    benchmark, _exit, _conn, artifact = _run_main(monkeypatch, tmp_path, ["baseline", "baseline"])
    artifact["recovery_time"]["is_backup_restore_rto"] = True

    with pytest.raises(benchmark.RecoveryBenchmarkError):
        benchmark.check_evidence_invariants(artifact)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda artifact: artifact["recovery_point"].update({"objective_seconds": 0}),
            id="rpo_objective_forced_to_zero",
        ),
        pytest.param(
            lambda artifact: artifact["recovery_time"].update({"objective_seconds": 0}),
            id="rto_objective_forced_to_zero",
        ),
        pytest.param(
            lambda artifact: artifact["recovery_time"].update({"measured_seconds": -1.0}),
            id="negative_duration",
        ),
        pytest.param(
            lambda artifact: artifact["recovery_time"].update({"is_backup_restore_rto": True}),
            id="mislabelled_as_backup_restore",
        ),
        pytest.param(
            lambda artifact: artifact["schema_consistency"].update({"consistent": True, "restored_catalog_union_sha256": "other"}),
            id="consistency_flag_contradicts_fingerprints",
        ),
        pytest.param(
            lambda artifact: artifact["recovery_point"].update({"measured_seconds": 0}),
            id="unmeasured_rpo_carrying_a_value",
        ),
    ],
)
def test_evidence_invariants_reject_a_self_contradicting_artifact(monkeypatch, tmp_path, mutate):
    benchmark, _exit_code, _connection, artifact = _run_main(
        monkeypatch, tmp_path, ["baseline", "baseline"]
    )
    benchmark.check_evidence_invariants(artifact)

    mutate(artifact)
    with pytest.raises(benchmark.RecoveryBenchmarkError):
        benchmark.check_evidence_invariants(artifact)
