from pathlib import Path


SERVICE_DB_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = SERVICE_DB_ROOT / "migrations/022_immutable_analysis_results.sql"
ROLLBACK = SERVICE_DB_ROOT / "rollbacks/022_immutable_analysis_results.down.sql"


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_analysis_result_migration_persists_owner_scoped_immutable_manifests():
    sql = _sql(MIGRATION)

    assert "CREATE TABLE IF NOT EXISTS app.analysis_result" in sql
    assert "analysis_result_id UUID PRIMARY KEY" in sql
    assert "FOREIGN KEY (user_id)" in sql
    assert "UNIQUE (user_id, manifest_hash)" in sql
    for column in (
        "rule_manifest_jsonb JSONB NOT NULL",
        "data_manifest_jsonb JSONB NOT NULL",
        "execution_manifest_jsonb JSONB NOT NULL",
        "report_manifest_jsonb JSONB NOT NULL",
        "public_snapshot_jsonb JSONB NOT NULL",
    ):
        assert column in sql
    assert "manifest_hash ~ '^[0-9a-f]{64}$'" in sql
    assert "BEFORE UPDATE OR DELETE ON app.analysis_result" in sql
    assert "BEFORE TRUNCATE ON app.analysis_result" in sql


def test_analysis_result_migration_links_job_run_and_report_to_one_identity():
    sql = _sql(MIGRATION)

    for table in (
        "app.ai_analysis_job",
        "app.backtest_run",
        "app.ai_backtest_report",
        "app.strategy_email_report",
    ):
        assert f"ALTER TABLE {table}" in sql
    assert sql.count("ADD COLUMN IF NOT EXISTS analysis_result_id UUID") == 4
    assert sql.count("REFERENCES app.analysis_result(analysis_result_id)") == 4
    assert "ON DELETE RESTRICT" in sql


def test_analysis_result_migration_is_replayable_and_forward_only():
    sql = _sql(MIGRATION)
    upper_sql = sql.upper()

    assert sql.startswith("-- Immutable")
    assert "BEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;")
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "ADD COLUMN IF NOT EXISTS" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql
    assert "IF NOT EXISTS (" in sql
    assert "DROP TABLE" not in upper_sql
    assert "DROP COLUMN" not in upper_sql
    assert "\nTRUNCATE " not in upper_sql


def test_analysis_result_rollback_removes_references_before_result_table():
    sql = _sql(ROLLBACK)
    table_drop = sql.index("DROP TABLE IF EXISTS app.analysis_result")

    for table in (
        "app.strategy_email_report",
        "app.ai_backtest_report",
        "app.backtest_run",
        "app.ai_analysis_job",
    ):
        assert sql.index(f"ALTER TABLE IF EXISTS {table}") < table_drop
    assert sql.index("DROP TRIGGER IF EXISTS trg_analysis_result_immutable") < table_drop
    assert sql.rstrip().endswith("COMMIT;")


def test_analysis_result_public_snapshot_contract_is_object_only():
    sql = _sql(MIGRATION)

    assert "ck_analysis_result_public_snapshot_object" in sql
    assert "jsonb_typeof(public_snapshot_jsonb) = 'object'" in sql
    assert "private/internal provenance is not stored here" in sql
