from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from app.core.config import ConfigurationError
from app.core.errors import AppError
from app.workers import email_delivery_worker
from app.workers.email_delivery_worker import EmailDeliveryWorker
from scripts import run_email_delivery_worker as worker_script

BACKEND_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = BACKEND_ROOT / "scripts" / "run_email_delivery_worker.py"


class _FakeWorker:
    def __init__(self, engine: Any, settings: Any) -> None:
        self.engine = engine
        self.settings = settings
        self.state = SimpleNamespace(
            worker_id="email-worker:test",
            batch_size=10,
            claim_lease_seconds=300,
            shutdown_grace_seconds=30,
        )
        self.validate_startup_calls = 0
        self.validate_readiness_calls = 0
        self.run_once_calls = 0
        self.run_calls = 0

    def validate_startup(self) -> None:
        self.validate_startup_calls += 1

    def validate_readiness(self) -> None:
        self.validate_readiness_calls += 1

    async def run_once(self) -> int:
        self.run_once_calls += 1
        return 1

    async def run(self) -> None:
        self.run_calls += 1


@pytest.fixture()
def worker_script_harness(monkeypatch):
    settings = SimpleNamespace(
        name="settings",
        email_effective_rollout_mode="disabled",
        email_api_key=None,
        email_from_address=None,
        email_sender_domain_category="not_configured",
    )
    engine = SimpleNamespace(name="engine")
    created_workers: list[_FakeWorker] = []
    check_db_calls: list[Any] = []
    redis_check_calls: list[Any] = []
    disposed_engines: list[Any] = []

    class HarnessWorker(_FakeWorker):
        def __init__(self, engine: Any, settings: Any) -> None:
            super().__init__(engine, settings)
            created_workers.append(self)

    async def fake_check_db(passed_engine):
        check_db_calls.append(passed_engine)
        return {"status": "ok"}

    async def fake_dispose_db_engine(passed_engine):
        disposed_engines.append(passed_engine)

    async def fake_queue_snapshot(passed_engine):
        assert passed_engine is engine
        return {
            "due_count": 0,
            "processing_count": 0,
            "stale_claim_count": 0,
            "last_outcome_category": "none",
        }

    async def fake_redis_check(passed_settings):
        assert passed_settings is settings
        redis_check_calls.append(passed_settings)
        return {"status": "ok", "role": "master", "logical_db": 11}

    monkeypatch.setattr(worker_script, "load_settings", lambda: settings)
    monkeypatch.setattr(worker_script, "create_db_engine", lambda passed: engine if passed is settings else None)
    monkeypatch.setattr(worker_script, "check_db", fake_check_db)
    monkeypatch.setattr(worker_script, "dispose_db_engine", fake_dispose_db_engine)
    monkeypatch.setattr(worker_script.email_outbox, "get_queue_readiness_snapshot", fake_queue_snapshot)
    monkeypatch.setattr(worker_script, "_check_redis_master", fake_redis_check)
    monkeypatch.setattr(worker_script, "EmailDeliveryWorker", HarnessWorker)

    return SimpleNamespace(
        settings=settings,
        engine=engine,
        created_workers=created_workers,
        check_db_calls=check_db_calls,
        redis_check_calls=redis_check_calls,
        disposed_engines=disposed_engines,
    )


def _fake_module(path: Path) -> ModuleType:
    module = ModuleType("provenance_test_module")
    module.__file__ = str(path)
    return module


def _run_provenance_probe(cwd: Path, *, pythonpath: Path | None = None) -> subprocess.CompletedProcess[str]:
    root_literal = repr(str(BACKEND_ROOT))
    probe = (
        "from pathlib import Path; import app, app.workers.email_delivery_worker as w, app.db.email_outbox as o; "
        f"r=Path({root_literal}).resolve(); "
        "mods=(app,w,o); "
        "ok=all(Path(m.__file__).resolve().is_relative_to(r) for m in mods); "
        "print('TRACK4E_PROVENANCE_OK='+str(ok)); raise SystemExit(0)\n"
    )
    env = os.environ.copy()
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    return subprocess.run(
        [sys.executable, "-i", str(LAUNCHER), "--help"],
        cwd=cwd,
        env=env,
        input=probe,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_backend_root_is_derived_from_launcher_file():
    assert worker_script._derive_backend_root(LAUNCHER) == BACKEND_ROOT
    assert worker_script.INTENDED_BACKEND_ROOT == BACKEND_ROOT


def test_path_boundary_check_rejects_prefix_sibling(tmp_path):
    root = tmp_path / "backend"
    inside = root / "app" / "module.py"
    sibling = tmp_path / "backend-copy" / "app" / "module.py"

    assert worker_script._is_path_within(inside, root) is True
    assert worker_script._is_path_within(sibling, root) is False


def test_loaded_track4_modules_pass_runtime_provenance():
    worker_script._require_runtime_provenance()


def test_foreign_module_paths_fail_closed_without_path_disclosure(tmp_path):
    foreign = tmp_path / "credential-token-secret" / "app"
    with pytest.raises(worker_script.ProvenanceError) as mismatch:
        worker_script._verify_runtime_provenance(
            BACKEND_ROOT,
            launcher_file=LAUNCHER,
            app_module=_fake_module(foreign / "__init__.py"),
            worker_module=_fake_module(foreign / "workers" / "email_delivery_worker.py"),
            email_outbox_module=_fake_module(foreign / "db" / "email_outbox.py"),
        )

    assert str(mismatch.value) == worker_script.PROVENANCE_ERROR_CATEGORY
    assert "credential-token-secret" not in str(mismatch.value)


def test_preloaded_foreign_app_fails_before_launcher_runtime(tmp_path):
    foreign = tmp_path / "credential-token-secret" / "app" / "__init__.py"
    code = (
        "import runpy,sys,types; "
        "module=types.ModuleType('app'); "
        f"module.__file__={str(foreign)!r}; "
        "sys.modules['app']=module; "
        f"runpy.run_path({str(LAUNCHER)!r}, run_name='__main__')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == worker_script.PROVENANCE_EXIT_CODE
    assert result.stderr.strip() == worker_script.PROVENANCE_ERROR_CATEGORY
    assert "credential-token-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize("cwd_name", ["backend", "repository", "temporary"])
def test_absolute_launcher_imports_track4_from_multiple_caller_directories(tmp_path, cwd_name):
    cwd = {"backend": BACKEND_ROOT, "repository": BACKEND_ROOT.parent, "temporary": tmp_path}[cwd_name]
    result = _run_provenance_probe(cwd)

    assert result.returncode == 0
    assert "TRACK4E_PROVENANCE_OK=True" in result.stdout


def test_stale_pythonpath_cannot_override_track4_imports(tmp_path):
    foreign = tmp_path / "foreign-backend"
    app = foreign / "app"
    app.mkdir(parents=True)
    (app / "__init__.py").write_text("SOURCE = 'foreign'\n", encoding="utf-8")

    result = _run_provenance_probe(tmp_path, pythonpath=foreign)

    assert result.returncode == 0
    assert "TRACK4E_PROVENANCE_OK=True" in result.stdout


def test_parser_exposes_check_once_and_loop_modes():
    parser = worker_script.build_parser()

    assert parser.parse_args(["--check"]).check is True
    assert parser.parse_args(["--once"]).once is True
    assert parser.parse_args(["--loop"]).loop is True
    assert parser.parse_args(["--check", "--require-send-ready"]).require_send_ready is True
    with pytest.raises(SystemExit):
        parser.parse_args(["--check", "--once"])


@pytest.mark.asyncio
async def test_check_mode_performs_no_worker_iteration(worker_script_harness):
    exit_code = await worker_script.run(["--check"])

    worker = worker_script_harness.created_workers[0]
    assert exit_code == 0
    assert worker.validate_startup_calls == 0
    assert worker.validate_readiness_calls == 1
    assert worker.run_once_calls == 0
    assert worker.run_calls == 0
    assert worker_script_harness.check_db_calls == [worker_script_harness.engine]
    assert worker_script_harness.disposed_engines == [worker_script_harness.engine]


@pytest.mark.asyncio
async def test_send_ready_check_validates_startup_without_worker_iteration(worker_script_harness):
    exit_code = await worker_script.run(["--check", "--require-send-ready"])

    worker = worker_script_harness.created_workers[0]
    assert exit_code == 0
    assert worker.validate_startup_calls == 1
    assert worker.validate_readiness_calls == 0
    assert worker.run_once_calls == 0


@pytest.mark.asyncio
async def test_once_mode_checks_database_and_redis_before_iteration(worker_script_harness):
    exit_code = await worker_script.run(["--once"])

    worker = worker_script_harness.created_workers[0]
    assert exit_code == 0
    assert worker.validate_startup_calls == 1
    assert worker.run_once_calls == 1
    assert worker_script_harness.check_db_calls == [worker_script_harness.engine]
    assert worker_script_harness.redis_check_calls == [worker_script_harness.settings]


@pytest.mark.asyncio
async def test_runtime_provenance_failure_precedes_settings_and_engine(monkeypatch, capsys):
    settings_calls: list[bool] = []

    def fail_provenance():
        raise worker_script.ProvenanceError()

    monkeypatch.setattr(worker_script, "_require_runtime_provenance", fail_provenance)
    monkeypatch.setattr(worker_script, "load_settings", lambda: settings_calls.append(True))

    exit_code = await worker_script.run(["--check"])

    assert exit_code == worker_script.PROVENANCE_EXIT_CODE
    assert settings_calls == []
    assert capsys.readouterr().err.strip() == worker_script.PROVENANCE_ERROR_CATEGORY


@pytest.mark.asyncio
async def test_category_shaped_configuration_reason_is_absent_from_worker_check_output(
    monkeypatch,
    capsys,
):
    marker = "category" + "_shaped_worker_readiness_reason"
    error = ConfigurationError(
        marker,
        [
            {
                "loc": ("BREVO_SENDER_EMAIL",),
                "type": marker,
                "msg": marker,
                "input": marker,
                "ctx": {"error": ValueError(marker)},
            }
        ],
    )

    def reject_settings():
        raise error

    monkeypatch.setattr(worker_script, "load_settings", reject_settings)
    monkeypatch.setattr(
        worker_script,
        "create_db_engine",
        lambda _settings: pytest.fail("engine must not be created after configuration rejection"),
    )

    exit_code = await worker_script.run(["--check"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert marker not in captured.out
    assert marker not in captured.err
    assert captured.err.strip() == "Backend configuration is invalid"


def test_worker_delivery_scope_is_forwarded_without_claiming_unrelated_rows(monkeypatch):
    calls: list[tuple[str, str | None]] = []

    async def release_expired_claims(_engine, *, delivery_scope_id=None):
        calls.append(("release", delivery_scope_id))
        return []

    async def claim_next_delivery(_engine, *, delivery_scope_id=None, **_kwargs):
        calls.append(("claim", delivery_scope_id))
        return None

    monkeypatch.setattr(email_delivery_worker.email_outbox, "release_expired_claims", release_expired_claims)
    monkeypatch.setattr(email_delivery_worker.email_outbox, "claim_next_delivery", claim_next_delivery)
    settings = SimpleNamespace(
        email_worker_id="unit-worker",
        email_worker_batch_size=1,
        email_worker_claim_lease_seconds=30,
        email_worker_poll_interval_seconds=1.0,
        email_worker_shutdown_grace_seconds=5,
        email_delivery_worker_enabled=True,
        email_effective_rollout_mode="allowlist",
    )
    provider = SimpleNamespace(validate_configuration=lambda: None)
    worker = EmailDeliveryWorker(object(), settings, provider=provider, delivery_scope_id="synthetic-delivery")

    assert asyncio.run(worker.run_once()) == 0
    assert calls == [("release", "synthetic-delivery"), ("claim", "synthetic-delivery")]


def test_disabled_rollout_fails_before_any_outbox_mutation(monkeypatch):
    async def unexpected(*_args, **_kwargs):
        raise AssertionError("outbox must not be touched while rollout is disabled")

    monkeypatch.setattr(email_delivery_worker.email_outbox, "release_expired_claims", unexpected)
    monkeypatch.setattr(email_delivery_worker.email_outbox, "claim_next_delivery", unexpected)
    settings = SimpleNamespace(
        email_worker_id="unit-worker",
        email_worker_batch_size=1,
        email_worker_claim_lease_seconds=30,
        email_worker_poll_interval_seconds=1.0,
        email_worker_shutdown_grace_seconds=5,
        email_delivery_worker_enabled=True,
        email_effective_rollout_mode="disabled",
    )
    worker = EmailDeliveryWorker(
        object(),
        settings,
        provider=SimpleNamespace(validate_configuration=lambda: None),
    )

    with pytest.raises(AppError) as blocked:
        asyncio.run(worker.run_once())
    assert blocked.value.code == "email_rollout_disabled"


def test_redis_check_reports_an_unreachable_redis_as_a_configuration_error(monkeypatch):
    """`--check` must fail with the sanitized message, not a raw redis traceback."""

    from redis import asyncio as redis_asyncio

    class _UnreachableClient:
        connection_pool = SimpleNamespace(connection_kwargs={"db": 11})

        async def ping(self):
            raise ConnectionError("connection refused (host redacted in message)")

        async def aclose(self):
            return None

    monkeypatch.setattr(redis_asyncio, "from_url", lambda *_args, **_kwargs: _UnreachableClient())
    settings = SimpleNamespace(redis_url_value="redis://example.invalid:6379/11")

    with pytest.raises(ConfigurationError, match="Redis readiness check failed"):
        asyncio.run(worker_script._check_redis_master(settings))
