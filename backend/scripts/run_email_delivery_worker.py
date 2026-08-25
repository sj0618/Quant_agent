from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import signal
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

PROVENANCE_ERROR_CATEGORY = "worker_launcher_provenance_mismatch"
PROVENANCE_EXIT_CODE = 2


class ProvenanceError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(PROVENANCE_ERROR_CATEGORY)
        self.code = PROVENANCE_ERROR_CATEGORY


def _derive_backend_root(launcher_file: str | Path = __file__) -> Path:
    return Path(launcher_file).resolve().parent.parent


def _is_path_within(path: str | Path, root: str | Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False
    return True


def _module_paths(module: ModuleType) -> list[Path]:
    module_file = getattr(module, "__file__", None)
    if module_file:
        return [Path(module_file).resolve()]
    module_path = getattr(module, "__path__", None)
    if module_path:
        return [Path(value).resolve() for value in module_path]
    return []


def _reject_conflicting_loaded_app_modules(backend_root: Path) -> None:
    for name, module in tuple(sys.modules.items()):
        if name != "app" and not name.startswith("app."):
            continue
        if module is None:
            raise ProvenanceError()
        paths = _module_paths(module)
        if not paths or any(not _is_path_within(path, backend_root) for path in paths):
            raise ProvenanceError()


def _establish_import_source(backend_root: Path) -> None:
    if not (backend_root / "app" / "__init__.py").is_file():
        raise ProvenanceError()
    _reject_conflicting_loaded_app_modules(backend_root)
    normalized_root = str(backend_root.resolve())
    sys.path[:] = [entry for entry in sys.path if not entry or str(Path(entry).resolve()) != normalized_root]
    sys.path.insert(0, normalized_root)


def _verify_runtime_provenance(
    backend_root: Path,
    *,
    launcher_file: str | Path,
    app_module: ModuleType,
    worker_module: ModuleType,
    email_outbox_module: ModuleType,
) -> None:
    _reject_conflicting_loaded_app_modules(backend_root)
    inspected_paths = [Path(launcher_file).resolve()]
    for module in (app_module, worker_module, email_outbox_module):
        paths = _module_paths(module)
        if len(paths) != 1:
            raise ProvenanceError()
        inspected_paths.extend(paths)
    if any(not _is_path_within(path, backend_root) for path in inspected_paths):
        raise ProvenanceError()


def _bootstrap_runtime() -> tuple[Path, ModuleType, ModuleType, ModuleType]:
    backend_root = _derive_backend_root()
    _establish_import_source(backend_root)
    app_module = importlib.import_module("app")
    worker_module = importlib.import_module("app.workers.email_delivery_worker")
    email_outbox_module = importlib.import_module("app.db.email_outbox")
    _verify_runtime_provenance(
        backend_root,
        launcher_file=__file__,
        app_module=app_module,
        worker_module=worker_module,
        email_outbox_module=email_outbox_module,
    )
    return backend_root, app_module, worker_module, email_outbox_module


try:
    INTENDED_BACKEND_ROOT, _APP_MODULE, _WORKER_MODULE, _EMAIL_OUTBOX_MODULE = _bootstrap_runtime()
except (ImportError, OSError, ProvenanceError):
    print(PROVENANCE_ERROR_CATEGORY, file=sys.stderr)
    raise SystemExit(PROVENANCE_EXIT_CODE) from None

from app.core.config import ConfigurationError, load_settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.db import email_outbox  # noqa: E402
from app.db.session import check_db, create_db_engine, dispose_db_engine  # noqa: E402
from app.services.email_observability import emit_email_event  # noqa: E402
from app.workers.email_delivery_worker import EmailDeliveryWorker  # noqa: E402


def _require_runtime_provenance() -> None:
    _verify_runtime_provenance(
        INTENDED_BACKEND_ROOT,
        launcher_file=__file__,
        app_module=_APP_MODULE,
        worker_module=_WORKER_MODULE,
        email_outbox_module=_EMAIL_OUTBOX_MODULE,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the General Backend email delivery worker")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate configuration and database connectivity, then exit")
    mode.add_argument("--once", action="store_true", help="Run a single polling iteration and exit")
    mode.add_argument("--loop", action="store_true", help="Run the worker loop until stopped")
    parser.add_argument(
        "--require-send-ready",
        action="store_true",
        help="With --check, require the worker to be enabled and ready to claim deliveries",
    )
    return parser


def _install_signal_handlers(worker: EmailDeliveryWorker) -> None:
    def _request_stop(_signum: int, _frame: Any) -> None:
        worker.stop()

    try:
        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)
    except Exception:  # noqa: BLE001
        return


async def _run_once(worker: EmailDeliveryWorker) -> int:
    return await worker.run_once()


async def _check_redis_master(settings: Any) -> dict[str, object]:
    from redis import asyncio as redis_asyncio

    if not settings.redis_url_value:
        raise ConfigurationError("Redis readiness check failed")
    client = redis_asyncio.from_url(settings.redis_url_value, decode_responses=True)
    try:
        await client.ping()
        replication = await client.info("replication")
        role = str(replication.get("role") or "").strip().lower()
        database = int(client.connection_pool.connection_kwargs.get("db") or 0)
        if role != "master" or database != 11:
            raise ConfigurationError("Redis readiness check failed")
        return {"status": "ok", "role": "master", "logical_db": 11}
    finally:
        await client.aclose()


async def _run_check(worker: EmailDeliveryWorker) -> int:
    await check_db(worker.engine)
    queue = await email_outbox.get_queue_readiness_snapshot(worker.engine)
    redis = await _check_redis_master(worker.settings)
    settings = worker.settings
    print(
        json.dumps(
            {
                "status": "ok",
                "worker_provenance": "track4",
                "rollout_mode": settings.email_effective_rollout_mode,
                "provider_configured": bool(settings.email_api_key and settings.email_from_address),
                "authenticated_sender_domain": settings.email_sender_domain_category,
                "queue_due_count": queue["due_count"],
                "queue_processing_count": queue["processing_count"],
                "stale_claim_count": queue["stale_claim_count"],
                "last_worker_outcome_category": queue["last_outcome_category"],
                "redis": redis,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


async def _run_forever(worker: EmailDeliveryWorker) -> None:
    _install_signal_handlers(worker)
    await worker.run()


def _emit_preflight_failure(worker: EmailDeliveryWorker | None, exc: Exception) -> None:
    if worker is None:
        return
    emit_email_event(
        worker.logger,
        "worker_preflight_failed",
        worker_id=worker.state.worker_id,
        batch_size=worker.state.batch_size,
        claim_ttl_seconds=worker.state.claim_lease_seconds,
        shutdown_grace_seconds=worker.state.shutdown_grace_seconds,
        reason_code=str(getattr(exc, "code", type(exc).__name__)),
        error_message=str(getattr(exc, "message", exc)),
    )


async def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.require_send_ready and not args.check:
        parser.error("--require-send-ready requires --check")
    engine = None
    worker: EmailDeliveryWorker | None = None
    preflight_complete = False

    try:
        _require_runtime_provenance()
        settings = load_settings()
        engine = create_db_engine(settings)
        worker = EmailDeliveryWorker(engine, settings)
        if args.check:
            if args.require_send_ready:
                worker.validate_startup()
            else:
                worker.validate_readiness()
            exit_code = await _run_check(worker)
            preflight_complete = True
            return exit_code
        worker.validate_startup()
        await check_db(worker.engine)
        await _check_redis_master(settings)
        preflight_complete = True
        if args.once:
            await _run_once(worker)
            return 0
        await _run_forever(worker)
        return 0
    except ConfigurationError as exc:
        if worker is not None and not preflight_complete:
            _emit_preflight_failure(worker, exc)
        print(str(exc), file=sys.stderr)
        return 1
    except ProvenanceError:
        print(PROVENANCE_ERROR_CATEGORY, file=sys.stderr)
        return PROVENANCE_EXIT_CODE
    except AppError as exc:
        if worker is not None and not preflight_complete:
            _emit_preflight_failure(worker, exc)
        print(exc.message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            if engine is not None:
                await dispose_db_engine(engine)
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
