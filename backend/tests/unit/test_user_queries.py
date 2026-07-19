from __future__ import annotations

from app.db.user_queries import UserSchemaReport, approval_needed_error, build_google_user_upsert_sql, build_load_user_sql


def test_user_schema_requires_provider_sub_columns_and_unique_constraint():
    report = UserSchemaReport(columns={"id", "email", "auth_provider"}, has_provider_sub_unique=False)
    assert report.supports_google_identity is False
    error = approval_needed_error(report)
    assert error.status_code == 409
    assert error.code == "user_schema_approval_required"
    assert error.details["accepted_id_columns"] == ["id", "user_id"]
    assert "provider_user_id" in error.details["missing_columns"]
    assert error.details["migration_policy"] == "user_approval_required_before_schema_change"


def test_user_schema_accepts_user_id_as_canonical_id():
    report = UserSchemaReport(columns={"user_id", "email", "auth_provider", "provider_user_id"}, has_provider_sub_unique=True)
    assert report.user_id_column == "user_id"
    assert report.supports_google_identity is True
    assert report.missing_required_columns == set()


def test_google_user_upsert_uses_provider_sub_conflict_not_email_only():
    report = UserSchemaReport(
        columns={"id", "email", "auth_provider", "provider_user_id", "name", "avatar_url", "email_verified", "created_at", "updated_at"},
        has_provider_sub_unique=True,
    )
    sql = build_google_user_upsert_sql(report)
    assert "ON CONFLICT (auth_provider, provider_user_id)" in sql
    assert "RETURNING CAST(id AS text) AS id, email" in sql
    assert "email = EXCLUDED.email" in sql
    assert "provider_user_id" in sql
    assert "ON CONFLICT (email)" not in sql


def test_google_user_upsert_returns_user_id_as_id_when_schema_uses_user_id():
    report = UserSchemaReport(
        columns={"user_id", "email", "auth_provider", "provider_user_id", "name", "created_at", "updated_at"},
        has_provider_sub_unique=True,
    )
    sql = build_google_user_upsert_sql(report)
    assert "RETURNING CAST(user_id AS text) AS id, email" in sql


def test_google_user_upsert_uses_profile_image_url_when_erd_schema_is_applied():
    report = UserSchemaReport(
        columns={"user_id", "email", "auth_provider", "provider_user_id", "name", "profile_image_url", "created_at", "updated_at"},
        has_provider_sub_unique=True,
    )
    sql = build_google_user_upsert_sql(report)
    assert "profile_image_url" in sql
    assert "profile_image_url AS avatar_url" in sql



def test_load_user_sql_uses_null_aliases_for_missing_optional_columns():
    report = UserSchemaReport(columns={"id", "email", "auth_provider", "provider_user_id"}, has_provider_sub_unique=True)
    sql = build_load_user_sql(report)
    assert "SELECT CAST(id AS text) AS id, email" in sql
    assert "WHERE CAST(id AS text) = :user_id" in sql
    assert "NULL AS name" in sql
    assert "NULL AS avatar_url" in sql


def test_load_user_sql_maps_user_id_to_id_when_schema_uses_user_id():
    report = UserSchemaReport(columns={"user_id", "email", "auth_provider", "provider_user_id"}, has_provider_sub_unique=True)
    sql = build_load_user_sql(report)
    assert "SELECT CAST(user_id AS text) AS id, email" in sql
    assert "WHERE CAST(user_id AS text) = :user_id" in sql


def test_load_user_sql_maps_profile_image_url_to_avatar_alias():
    report = UserSchemaReport(
        columns={"user_id", "email", "auth_provider", "provider_user_id", "profile_image_url"},
        has_provider_sub_unique=True,
    )
    sql = build_load_user_sql(report)
    assert "profile_image_url AS avatar_url" in sql
