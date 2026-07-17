#!/usr/bin/env python3
"""Run the fixed replay verifier and force-discard only a validated disposable DB."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlunparse, urlparse

from verify_fixed_migration_replay import (
    missing_external_inputs,
    validate_disposable_dsn,
    write_artifact,
)
import verify_fixed_migration_replay


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    return parser.parse_args(argv)


def _discard_replay_database() -> None:
    """Use postgres maintenance DB only after the replay DSN passed its contract."""
    replay = validate_disposable_dsn(
        os.getenv("SERVICE_DB_REPLAY_DSN", ""),
        expected_host=os.getenv("SERVICE_DB_REPLAY_EXPECTED_HOST", ""),
        expected_port=os.getenv("SERVICE_DB_REPLAY_EXPECTED_PORT", ""),
        expected_user=os.getenv("SERVICE_DB_REPLAY_EXPECTED_USER", ""),
        expected_database=os.getenv("SERVICE_DB_REPLAY_EXPECTED_DATABASE", ""),
        disposable_marker=os.getenv("SERVICE_DB_REPLAY_DISPOSABLE_MARKER", ""),
    )
    parsed = urlparse(replay.dsn)
    admin_dsn = urlunparse(parsed._replace(path="/postgres"))
    import psycopg
    from psycopg import sql

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(replay.database))
        )


def _record_discard(artifact_path: Path, discarded: bool, error: str | None = None) -> None:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["forced_discard"] = {"required": True, "completed": discarded}
    if error:
        artifact["status"] = "FAILED"
        artifact["forced_discard_error"] = error
    write_artifact(artifact_path, artifact)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # This guard deliberately happens before DSN parsing or any SQL. A missing
    # external signer/SBOM/trusted root must retain the verifier's BLOCKED artifact.
    if missing_external_inputs(dict(os.environ)):
        return verify_fixed_migration_replay.main(["--artifact", str(args.artifact)])

    verifier_exit = verify_fixed_migration_replay.main(["--artifact", str(args.artifact)])
    try:
        _discard_replay_database()
        _record_discard(args.artifact, discarded=True)
    except Exception as error:
        if args.artifact.exists():
            _record_discard(args.artifact, discarded=False, error=str(error))
        return 1
    return verifier_exit


if __name__ == "__main__":
    sys.exit(main())
