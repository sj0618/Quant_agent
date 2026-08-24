"""The single-process contract this service runs under, and its startup enforcement.

Job events, the AOAI concurrency gate, and the per-request process pool are all
process-local. A second worker shares none of them, so running two would give each its
own SSE buffer (clients miss events served by the other worker), its own provider gate
(twice the intended concurrency against a rate-limited deployment), and its own view of
which jobs are in flight (the restart reaper in `jobs` would fail jobs a sibling worker
is actively running).

That constraint used to live only in comments, which is not a place a `--workers 4`
lands. Startup refuses instead, so the failure is loud and immediate rather than a slow
leak of missing events and rate-limit errors.

Detection is by configuration, not by process inspection: `WEB_CONCURRENCY` and an
explicit `--workers`/`-w` argument are how multiple workers actually get requested here.
A supervisor that fans out some other way - a gunicorn config file, a process manager
running N copies - is not detected. For those the contract is documented, not enforced.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence

WEB_CONCURRENCY_ENV = "WEB_CONCURRENCY"

_SERVER_COMMANDS = ("uvicorn", "gunicorn", "hypercorn")
_WORKER_FLAGS = ("--workers", "-w")


class MultiProcessStartupError(RuntimeError):
    """Raised when the process was asked to run more than one worker."""


def _worker_flag_value(argv: Sequence[str]) -> str | None:
    """The value of an explicit worker flag, if this argv is running a server at all.

    The command check keeps `-w` from being read out of an unrelated tool's arguments -
    a test runner's flags are not a deployment topology.
    """

    if not any(command in part for part in argv for command in _SERVER_COMMANDS):
        return None
    for index, argument in enumerate(argv):
        for flag in _WORKER_FLAGS:
            if argument == flag:
                return argv[index + 1] if index + 1 < len(argv) else None
            if argument.startswith(f"{flag}="):
                return argument.split("=", 1)[1]
    return None


def _requested_worker_count(
    argv: Sequence[str], environ: Mapping[str, str]
) -> tuple[int | None, str]:
    """The worker count this process was asked for, and the setting that asked for it."""

    flag_value = _worker_flag_value(argv)
    if flag_value is not None:
        source = f"--workers {flag_value}"
    else:
        flag_value = str(environ.get(WEB_CONCURRENCY_ENV, "")).strip() or None
        source = f"{WEB_CONCURRENCY_ENV}={flag_value}"
    if flag_value is None:
        return None, ""
    try:
        return int(flag_value), source
    except ValueError:
        # An unparseable setting is not a second worker. Refusing to start over a typo
        # would take the service down for something that changes no behaviour.
        return None, ""


def enforce_single_process(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Refuse to serve when more than one worker was requested.

    Raises `MultiProcessStartupError`. A single worker, or no explicit request at all,
    returns quietly.
    """

    count, source = _requested_worker_count(
        list(sys.argv if argv is None else argv),
        os.environ if environ is None else environ,
    )
    if count is None or count <= 1:
        return
    raise MultiProcessStartupError(
        f"이 서비스는 단일 프로세스 계약으로 동작합니다 ({source}). "
        "SSE 이벤트 버퍼·AOAI 동시성 게이트·진행 중 잡 판별이 모두 프로세스 로컬이라 "
        "워커를 늘리면 이벤트 유실과 게이트 초과가 발생합니다. "
        "워커를 1로 두고 수직 확장하거나, 먼저 이 상태들을 외부화하십시오."
    )
