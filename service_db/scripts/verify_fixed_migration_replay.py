#!/usr/bin/env python3
"""Fail-closed verifier for the fixed service DB migration replay contract.

A replay can run only with independently supplied signer, SBOM, and trusted-root
inputs.  Missing inputs deliberately produce a BLOCKED artifact before opening a
PostgreSQL connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


FIXED_MIGRATIONS = (
    "011_app_ai_backtest_erd.sql",
    "013_ai_runtime_logging.sql",
    "014_create_report_email_tables.sql",
    "015_ai_backtest_execution_process_identity.sql",
    "016_ai_backtest_idempotency.sql",
    "017_add_notification_settings_to_users.sql",
    "018_create_email_delivery_outbox.sql",
    "019_ai_prompt_response_summary.sql",
    "020_ai_account_tokens.sql",
    "021_ai_analysis_jobs.sql",
    "022_immutable_analysis_results.sql",
)
INTERNAL_TRANSACTION_MIGRATION = "014_create_report_email_tables.sql"
PG17_MIN_VERSION_NUM = 170000
PG18_MIN_VERSION_NUM = 180000
PG17_GOLDEN_LITERAL = "quant-agent/service-db/fixed-replay/pg17"
PG17_GOLDEN_SHA256 = "b3e301d2f3b561cd496c27f39040a352fe93e406c545d776f9ad470184031248"
REQUIRED_EXTERNAL_INPUTS = {
    "external_signer": "SERVICE_DB_REPLAY_EXTERNAL_SIGNER",
    "sbom": "SERVICE_DB_REPLAY_SBOM",
    "trusted_root": "SERVICE_DB_REPLAY_TRUSTED_ROOT",
}

# Names explicitly owned by the fixed migrations above. System-owned primary
# indexes and sequences are intentionally excluded from this migration contract.
OWNED_RELATIONS = {
    "r": (
        "users", "strategy", "ai_chat_session", "ai_chat_message", "ai_trace",
        "ai_strategy_parse", "ai_validation_result", "ai_code_generation",
        "ai_code_validation_result", "code_execution_run", "backtest_run",
        "backtest_equity_point", "backtest_signal", "backtest_trade",
        "backtest_summary", "backtest_metric_detail", "ai_backtest_report",
        "ai_backtest_report_metric", "ai_model_call_log", "ai_prompt_log",
        "ai_agent_execution_log", "ai_error_log", "strategy_report_profile",
        "strategy_email_report", "strategy_email_report_news",
        "strategy_email_report_candidate", "email_digest_subscription",
        "email_delivery_history", "ai_backtest_request",
        "ai_backtest_replacement_approval", "email_delivery_outbox",
        "ai_account_token", "ai_analysis_job", "analysis_result",
    ),
    "i": (
        "idx_users_email", "idx_users_provider_user_id", "idx_strategy_user_created",
        "idx_ai_chat_session_user_created", "idx_ai_chat_message_session_created",
        "idx_ai_trace_user_started", "idx_ai_trace_session_started",
        "idx_ai_strategy_parse_session_created", "idx_ai_strategy_parse_user_created",
        "idx_ai_strategy_parse_trace_created", "idx_ai_validation_result_parse_created",
        "idx_ai_validation_result_strategy_created", "idx_ai_code_generation_parse_created",
        "idx_ai_code_generation_trace_created", "idx_ai_code_generation_status_created",
        "idx_ai_code_generation_hash", "idx_ai_code_validation_result_code_created",
        "idx_code_execution_run_code_created", "idx_code_execution_run_trace_created",
        "idx_code_execution_run_status_created", "idx_backtest_run_strategy_created",
        "idx_backtest_run_user_created", "idx_backtest_run_session_created",
        "idx_backtest_run_parse_created", "idx_backtest_run_trace_created",
        "idx_backtest_run_status_created", "idx_backtest_run_execution_mode_created",
        "idx_backtest_equity_point_run_trade_date", "idx_backtest_signal_run_signal_date",
        "idx_backtest_signal_run_ticker", "idx_backtest_trade_run_entry_date",
        "idx_backtest_trade_run_ticker", "idx_ai_backtest_report_run_created",
        "idx_ai_backtest_report_user_created", "idx_ai_backtest_report_trace_created",
        "idx_ai_backtest_report_metric_report_group", "idx_ai_model_call_log_trace_created",
        "idx_ai_model_call_log_session_created", "idx_ai_model_call_log_user_created",
        "idx_ai_model_call_log_code_created", "idx_ai_prompt_log_session_created",
        "idx_ai_agent_execution_log_trace_started", "idx_ai_agent_execution_log_session_started",
        "idx_ai_agent_execution_log_run_started", "idx_ai_agent_execution_log_execution_run_started",
        "idx_ai_error_log_trace_created", "idx_ai_error_log_session_created",
        "idx_ai_error_log_call_created", "idx_ai_error_log_execution_created",
        "idx_ai_error_log_execution_run_created", "idx_ai_error_log_severity_created",
        "idx_ai_model_call_log_execution_created", "idx_ai_prompt_log_retention",
        "idx_code_execution_run_attempt", "idx_strategy_report_profile_updated",
        "idx_strategy_email_report_strategy_date", "idx_strategy_email_report_status",
        "idx_strategy_email_report_backtest_run", "idx_strategy_email_report_ai_report",
        "idx_strategy_email_report_news_report", "idx_strategy_email_report_candidate_report",
        "idx_email_digest_subscription_user", "idx_email_delivery_history_user_sent",
        "idx_email_delivery_history_report", "uq_ai_backtest_request_scope_key",
        "uq_ai_backtest_request_active_scope_fingerprint", "idx_ai_backtest_request_trace",
        "idx_ai_backtest_request_lease_created", "uq_ai_backtest_replacement_live_source",
        "idx_ai_backtest_replacement_scope_fingerprint", "uq_ai_backtest_replacement_key_hash",
        "idx_email_delivery_outbox_due", "idx_email_delivery_outbox_claim_expiry",
        "idx_email_delivery_outbox_user_created", "idx_email_delivery_outbox_report",
        "idx_ai_account_token_user_created", "idx_ai_account_token_status",
        "idx_ai_analysis_job_user_updated", "uq_analysis_result_owner_manifest_hash",
        "idx_analysis_result_owner_created", "idx_ai_analysis_job_analysis_result",
        "idx_backtest_run_analysis_result", "idx_ai_backtest_report_analysis_result",
        "idx_strategy_email_report_analysis_result",
    ),
    "v": ("strategy_report_summary_v", "email_digest_history_v"),
}
OWNED_TYPES = ("ai_code_status", "code_execution_status", "backtest_execution_mode")
OWNED_COLUMNS = (
    ("ai_model_call_log", "execution_id"),
    ("ai_model_call_log", "response_schema_name"),
    ("ai_model_call_log", "web_search_used"),
    ("ai_prompt_log", "assistant_response_summary"),
    ("code_execution_run", "attempt_id"),
    ("code_execution_run", "worker_host"),
    ("code_execution_run", "worker_pid"),
    ("code_execution_run", "worker_pgid"),
    ("code_execution_run", "worker_started_at"),
    ("users", "daily_report_email"),
    ("users", "action_emails"),
    ("users", "marketing_email"),
    ("users", "delivery_hour"),
    ("ai_analysis_job", "analysis_result_id"),
    ("backtest_run", "analysis_result_id"),
    ("ai_backtest_report", "analysis_result_id"),
    ("strategy_email_report", "analysis_result_id"),
)
OWNED_CONSTRAINTS = (
    "fk_ai_model_call_log_execution",
    "ck_ai_backtest_request_state",
    "ck_ai_backtest_request_safety_lease",
    "ck_ai_backtest_request_state_version",
    "ck_ai_backtest_replacement_approval_status",
    "email_delivery_outbox_idempotency_key_key",
    "email_delivery_outbox_user_id_fkey",
    "email_delivery_outbox_report_id_fkey",
    "email_delivery_outbox_strategy_id_fkey",
    "email_delivery_outbox_status_check",
    "email_delivery_outbox_attempt_count_check",
    "email_delivery_outbox_payload_object_check",
    "fk_analysis_result_user",
    "ck_analysis_result_schema_v1",
    "ck_analysis_result_hash_sha256",
    "ck_analysis_result_manifest_objects",
    "ck_analysis_result_public_snapshot_object",
    "uq_analysis_result_owner_manifest_hash",
    "fk_ai_analysis_job_analysis_result",
    "fk_backtest_run_analysis_result",
    "fk_ai_backtest_report_analysis_result",
    "fk_strategy_email_report_analysis_result",
)
OWNED_TRIGGERS = (
    "trg_email_digest_subscription_limit",
    "trg_analysis_result_immutable",
    "trg_analysis_result_no_truncate",
)



class ReplayContractError(RuntimeError):
    """A replay contract precondition was not met."""


@dataclass(frozen=True)
class ReplayDsn:
    dsn: str
    host: str
    port: int
    user: str
    database: str
    marker: str


def _required(value: str | None, name: str) -> str:
    if not value:
        raise ReplayContractError(f"missing required {name}")
    return value


def validate_disposable_dsn(
    dsn: str,
    *,
    expected_host: str,
    expected_port: str,
    expected_user: str,
    expected_database: str,
    disposable_marker: str,
) -> ReplayDsn:
    """Accept only the declared disposable DSN components; never probe server IP."""
    parsed = urlparse(_required(dsn, "replay DSN"))
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ReplayContractError("replay DSN must use postgres or postgresql")
    if parsed.hostname != _required(expected_host, "expected host"):
        raise ReplayContractError("replay DSN host does not match the disposable contract")
    try:
        port = parsed.port
    except ValueError as error:
        raise ReplayContractError("replay DSN port is invalid") from error
    if port != int(_required(expected_port, "expected port")):
        raise ReplayContractError("replay DSN port does not match the disposable contract")
    if unquote(parsed.username or "") != _required(expected_user, "expected user"):
        raise ReplayContractError("replay DSN user does not match the disposable contract")
    database = unquote(parsed.path.lstrip("/"))
    if database != _required(expected_database, "expected database"):
        raise ReplayContractError("replay DSN database does not match the disposable contract")
    marker = _required(disposable_marker, "disposable marker")
    application_names = parse_qs(parsed.query, keep_blank_values=True).get("application_name", [])
    if application_names != [marker] or marker not in database:
        raise ReplayContractError("replay DSN is missing its disposable marker contract")
    return ReplayDsn(dsn, parsed.hostname, port, unquote(parsed.username or ""), database, marker)


def _canonical_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def write_artifact(path: Path, payload: dict[str, Any]) -> None:
    artifact = {key: value for key, value in payload.items() if key != "artifact_sha256"}
    artifact["artifact_sha256"] = _canonical_hash(artifact)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def missing_external_inputs(env: dict[str, str]) -> list[str]:
    return [label for label, variable in REQUIRED_EXTERNAL_INPUTS.items() if not env.get(variable)]


def _assert_fixed_migration_files(migrations_dir: Path) -> list[Path]:
    actual = tuple(path.name for path in sorted(migrations_dir.glob("*.sql")))
    if actual != FIXED_MIGRATIONS:
        raise ReplayContractError(
            f"fixed migration list/order changed: expected {FIXED_MIGRATIONS}, got {actual}"
        )
    return [migrations_dir / name for name in FIXED_MIGRATIONS]


def _preflight_pg17(conn: Any) -> None:
    version_num = int(conn.execute("SHOW server_version_num").fetchone()[0])
    if not PG17_MIN_VERSION_NUM <= version_num < PG18_MIN_VERSION_NUM:
        raise ReplayContractError(f"PostgreSQL 17 is required, got server_version_num={version_num}")
    pgcrypto = conn.execute(
        "SELECT extversion FROM pg_extension WHERE extname = 'pgcrypto'"
    ).fetchone()
    if pgcrypto is None:
        raise ReplayContractError("pgcrypto must be provisioned before the replay")
    digest = conn.execute(
        "SELECT encode(digest(%s, 'sha256'), 'hex')", (PG17_GOLDEN_LITERAL,)
    ).fetchone()[0]
    if digest != PG17_GOLDEN_SHA256:
        raise ReplayContractError("PG17 pgcrypto digest does not match the literal golden")


def _catalog_union(conn: Any) -> list[str]:
    rows: list[str] = []
    for relkind, names in OWNED_RELATIONS.items():
        found = conn.execute(
            """
            SELECT c.relname,
                   CASE c.relkind
                       WHEN 'i' THEN pg_get_indexdef(c.oid)
                       WHEN 'v' THEN pg_get_viewdef(c.oid, true)
                       ELSE ''
                   END
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'app' AND c.relkind = %s AND c.relname = ANY(%s)
            ORDER BY c.relname
            """,
            (relkind, list(names)),
        ).fetchall()
        if [name for name, _ in found] != sorted(names):
            raise ReplayContractError(f"missing or mismatched app relation predicates for relkind={relkind}")
        rows.extend(f"relation|{relkind}|{name}|{definition}" for name, definition in found)

    found_types = conn.execute(
        """
        SELECT t.typname
        FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'app' AND t.typtype = 'e' AND t.typname = ANY(%s)
        ORDER BY t.typname
        """,
        (list(OWNED_TYPES),),
    ).fetchall()
    if [name for (name,) in found_types] != sorted(OWNED_TYPES):
        raise ReplayContractError("missing migration-owned enum predicate")
    rows.extend(f"type|{name}" for (name,) in found_types)

    found_columns = conn.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'app' AND table_name = ANY(%s)
        ORDER BY table_name, column_name
        """,
        (sorted({table for table, _ in OWNED_COLUMNS}),),
    ).fetchall()
    found_columns = [
        row for row in found_columns if (row[0], row[1]) in OWNED_COLUMNS
    ]
    if [(table, column) for table, column, *_ in found_columns] != sorted(OWNED_COLUMNS):
        raise ReplayContractError("missing migration-owned column predicate")
    rows.extend("column|" + "|".join("" if value is None else str(value) for value in row) for row in found_columns)

    found_constraints = conn.execute(
        """
        SELECT con.conname, pg_get_constraintdef(con.oid, true)
        FROM pg_constraint con JOIN pg_namespace n ON n.oid = con.connamespace
        WHERE n.nspname = 'app' AND con.conname = ANY(%s)
        ORDER BY con.conname
        """,
        (list(OWNED_CONSTRAINTS),),
    ).fetchall()
    if [name for name, _ in found_constraints] != sorted(OWNED_CONSTRAINTS):
        raise ReplayContractError("missing migration-owned constraint predicate")
    rows.extend(f"constraint|{name}|{definition}" for name, definition in found_constraints)
    found_triggers = conn.execute(
        """
        SELECT tg.tgname, pg_get_triggerdef(tg.oid, true)
        FROM pg_trigger tg JOIN pg_class c ON c.oid = tg.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'app' AND NOT tg.tgisinternal AND tg.tgname = ANY(%s)
        ORDER BY tg.tgname
        """,
        (list(OWNED_TRIGGERS),),
    ).fetchall()
    if [name for name, _ in found_triggers] != sorted(OWNED_TRIGGERS):
        raise ReplayContractError("missing migration-owned trigger predicate")
    rows.extend(f"trigger|{name}|{definition}" for name, definition in found_triggers)

    found_function = conn.execute(
        """
        SELECT p.proname, pg_get_functiondef(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'app' AND p.proname = 'enforce_email_digest_subscription_limit'
        """
    ).fetchone()
    if found_function is None:
        raise ReplayContractError("missing migration-owned function predicate")
    rows.append(f"function|{found_function[0]}|{found_function[1]}")
    return sorted(rows)


def _catalog_fingerprint(conn: Any) -> str:
    union = _catalog_union(conn)
    payload = "\n".join(union)
    postgres_digest = conn.execute(
        "SELECT encode(digest(%s, 'sha256'), 'hex')", (payload,)
    ).fetchone()[0]
    python_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if postgres_digest != python_digest:
        raise ReplayContractError("catalog union digest parity failed")
    return postgres_digest


def _execute_pass(conn: Any, migrations: list[Path]) -> None:
    for migration in migrations:
        conn.execute(migration.read_text(encoding="utf-8"))
        # 014 owns BEGIN without COMMIT. Commit its internal transaction before
        # the next fixed migration and before replaying the sequence.
        if migration.name == INTERNAL_TRANSACTION_MIGRATION:
            conn.commit()

def _reset_disposable_schema(conn: Any) -> None:
    """Reset only the disposable app schema before a second clean replay pass."""
    conn.execute("DROP SCHEMA IF EXISTS app CASCADE")
    conn.commit()


def _cas(markers: list[dict[str, Any]], expected: str, next_state: str) -> None:
    current = markers[-1]
    if current["state"] != expected:
        raise ReplayContractError(f"marker CAS expected {expected}, got {current['state']}")
    markers.append({"version": current["version"] + 1, "state": next_state})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--dsn", default=os.getenv("SERVICE_DB_REPLAY_DSN"))
    parser.add_argument("--expected-host", default=os.getenv("SERVICE_DB_REPLAY_EXPECTED_HOST"))
    parser.add_argument("--expected-port", default=os.getenv("SERVICE_DB_REPLAY_EXPECTED_PORT"))
    parser.add_argument("--expected-user", default=os.getenv("SERVICE_DB_REPLAY_EXPECTED_USER"))
    parser.add_argument("--expected-database", default=os.getenv("SERVICE_DB_REPLAY_EXPECTED_DATABASE"))
    parser.add_argument("--disposable-marker", default=os.getenv("SERVICE_DB_REPLAY_DISPOSABLE_MARKER"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env = dict(os.environ)
    missing = missing_external_inputs(env)
    base = {
        "contract": "service-db-fixed-replay-v1",
        "fixed_migrations": list(FIXED_MIGRATIONS),
        "pg17_golden_sha256": PG17_GOLDEN_SHA256,
    }
    markers: list[dict[str, Any]] = [{"version": 0, "state": "CREATED"}]
    if missing:
        _cas(markers, "CREATED", "BLOCKED")
        write_artifact(
            args.artifact,
            {**base, "status": "BLOCKED", "missing_external_inputs": missing, "markers": markers},
        )
        return 2

    try:
        replay_dsn = validate_disposable_dsn(
            args.dsn,
            expected_host=args.expected_host,
            expected_port=args.expected_port,
            expected_user=args.expected_user,
            expected_database=args.expected_database,
            disposable_marker=args.disposable_marker,
        )
        migrations = _assert_fixed_migration_files(Path(__file__).resolve().parents[1] / "migrations")
        import psycopg

        with psycopg.connect(replay_dsn.dsn, autocommit=True) as conn:
            _preflight_pg17(conn)
            _cas(markers, "CREATED", "PASS1_RUNNING")
            _execute_pass(conn, migrations)
            pass1_fingerprint = _catalog_fingerprint(conn)
            _cas(markers, "PASS1_RUNNING", "PASS1_COMPLETE")
            _cas(markers, "PASS1_COMPLETE", "PASS2_RUNNING")
            _reset_disposable_schema(conn)
            _execute_pass(conn, migrations)
            pass2_fingerprint = _catalog_fingerprint(conn)
            _cas(markers, "PASS2_RUNNING", "PASS2_COMPLETE")
        if pass1_fingerprint != pass2_fingerprint:
            raise ReplayContractError("pass1/pass2 final catalog union fingerprints differ")
        _cas(markers, "PASS2_COMPLETE", "PASS")
        write_artifact(
            args.artifact,
            {
                **base,
                "status": "PASS",
                "dsn_contract": {
                    "host": replay_dsn.host,
                    "port": replay_dsn.port,
                    "user": replay_dsn.user,
                    "database": replay_dsn.database,
                    "disposable_marker": replay_dsn.marker,
                },
                "markers": markers,
                "pass1_catalog_union_sha256": pass1_fingerprint,
                "pass2_catalog_union_sha256": pass2_fingerprint,
                "final_catalog_union_sha256": pass2_fingerprint,
            },
        )
        return 0
    except Exception as error:
        write_artifact(
            args.artifact, {**base, "status": "FAILED", "error": str(error), "markers": markers}
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
