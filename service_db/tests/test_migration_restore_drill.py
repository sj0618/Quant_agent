"""State-machine tests for the disposable migration rollback/restore drill."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


SERVICE_DB_ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = SERVICE_DB_ROOT / "scripts" / "verify_fixed_migration_replay.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("service_db_restore_drill", VERIFIER_PATH)
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


def _run_main_with_fingerprints(monkeypatch, tmp_path, fingerprints: list[str]):
    verifier = _load_verifier()
    connection = _RecordingConnection()
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_args, **_kwargs: connection),
    )
    monkeypatch.setattr(verifier, "_preflight_pg17", lambda _conn: None)
    monkeypatch.setattr(verifier, "_execute_pass", lambda _conn, _migrations: None)
    fingerprint_values = iter(fingerprints)
    monkeypatch.setattr(
        verifier,
        "_catalog_fingerprint",
        lambda _conn: next(fingerprint_values),
    )
    artifact = tmp_path / "restore-drill.json"
    exit_code = verifier.main(
        [
            "--artifact",
            str(artifact),
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
    )
    return exit_code, connection, json.loads(artifact.read_text(encoding="utf-8")), verifier


def test_restore_drill_main_runs_rollback_then_forward_restore_before_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_DB_REPLAY_EXTERNAL_SIGNER", "test-signer")
    monkeypatch.setenv("SERVICE_DB_REPLAY_SBOM", "test-sbom")
    monkeypatch.setenv("SERVICE_DB_REPLAY_TRUSTED_ROOT", "test-root")
    exit_code, connection, artifact, verifier = _run_main_with_fingerprints(
        monkeypatch,
        tmp_path,
        ["catalog", "catalog", "catalog"],
    )

    rollback = (SERVICE_DB_ROOT / "rollbacks" / verifier.ROLLBACK_RESTORE_SCRIPT).read_text(
        encoding="utf-8"
    )
    forward = (SERVICE_DB_ROOT / "migrations" / verifier.ROLLBACK_RESTORE_MIGRATION).read_text(
        encoding="utf-8"
    )
    assert exit_code == 0
    assert connection.executed == ["DROP SCHEMA IF EXISTS app CASCADE", rollback, forward]
    assert [marker["state"] for marker in artifact["markers"]] == [
        "CREATED",
        "PASS1_RUNNING",
        "PASS1_COMPLETE",
        "PASS2_RUNNING",
        "PASS2_COMPLETE",
        "ROLLBACK_RUNNING",
        "ROLLBACK_COMPLETE",
        "RESTORE_RUNNING",
        "RESTORE_COMPLETE",
        "PASS",
    ]
    assert artifact["final_catalog_union_sha256"] == "catalog"


def test_restore_drill_main_rejects_a_mismatched_post_restore_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_DB_REPLAY_EXTERNAL_SIGNER", "test-signer")
    monkeypatch.setenv("SERVICE_DB_REPLAY_SBOM", "test-sbom")
    monkeypatch.setenv("SERVICE_DB_REPLAY_TRUSTED_ROOT", "test-root")
    exit_code, _connection, artifact, _verifier = _run_main_with_fingerprints(
        monkeypatch,
        tmp_path,
        ["catalog", "catalog", "changed"],
    )

    assert exit_code == 1
    assert artifact["status"] == "FAILED"
    assert artifact["markers"][-1]["state"] == "RESTORE_COMPLETE"
    assert all(marker["state"] != "PASS" for marker in artifact["markers"])
