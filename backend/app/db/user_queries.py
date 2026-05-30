from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import AppError
from app.db.session import execute_one, fetch_all, fetch_one
from app.services.google_oauth import GoogleIdentity

REQUIRED_GOOGLE_USER_COLUMNS = {"email", "auth_provider", "provider_user_id"}
USER_ID_COLUMNS = ("id", "user_id")
OPTIONAL_USER_COLUMNS = ("name", "avatar_url", "picture", "email_verified", "created_at", "updated_at")


@dataclass(frozen=True)
class UserSchemaReport:
    columns: set[str]
    has_provider_sub_unique: bool

    @property
    def user_id_column(self) -> str | None:
        for column in USER_ID_COLUMNS:
            if column in self.columns:
                return column
        return None

    @property
    def missing_required_columns(self) -> set[str]:
        missing_columns = REQUIRED_GOOGLE_USER_COLUMNS - self.columns
        if self.user_id_column is None:
            missing_columns.add("id")
        return missing_columns

    @property
    def supports_google_identity(self) -> bool:
        return not self.missing_required_columns and self.has_provider_sub_unique


def approval_needed_error(report: UserSchemaReport) -> AppError:
    details = {
        "required_columns": sorted(REQUIRED_GOOGLE_USER_COLUMNS | {"id"}),
        "accepted_id_columns": list(USER_ID_COLUMNS),
        "present_columns": sorted(report.columns),
        "missing_columns": sorted(report.missing_required_columns),
        "requires_unique_constraint": ["auth_provider", "provider_user_id"],
        "has_provider_sub_unique": report.has_provider_sub_unique,
        "migration_policy": "user_approval_required_before_schema_change",
    }
    return AppError(
        status_code=409,
        component="db",
        code="user_schema_approval_required",
        message="app.users does not support safe Google provider+sub identity binding",
        details=details,
    )


async def inspect_user_schema(engine: AsyncEngine) -> UserSchemaReport:
    column_rows = await fetch_all(
        engine,
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'app' AND table_name = 'users'
        """,
    )
    columns = {str(row["column_name"]) for row in column_rows}
    constraint_rows = await fetch_all(
        engine,
        """
        SELECT tc.constraint_name, array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.table_schema = 'app'
          AND tc.table_name = 'users'
          AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
        GROUP BY tc.constraint_name
        """,
    )
    has_provider_sub_unique = any({"auth_provider", "provider_user_id"}.issubset(set(row.get("columns") or [])) for row in constraint_rows)
    return UserSchemaReport(columns=columns, has_provider_sub_unique=has_provider_sub_unique)


async def ensure_google_user_schema(engine: AsyncEngine) -> UserSchemaReport:
    report = await inspect_user_schema(engine)
    if not report.supports_google_identity:
        raise approval_needed_error(report)
    return report


def build_google_user_upsert_sql(report: UserSchemaReport) -> str:
    user_id_column = report.user_id_column
    if user_id_column is None:
        raise ValueError("app.users requires either id or user_id")
    user_id_expr = f"CAST({user_id_column} AS text)"

    insert_columns = ["email", "auth_provider", "provider_user_id"]
    values = [":email", ":auth_provider", ":provider_user_id"]
    update_parts = ["email = EXCLUDED.email"]
    returning = [f"{user_id_expr} AS id", "email", "auth_provider", "provider_user_id"]

    if "name" in report.columns:
        insert_columns.append("name")
        values.append(":name")
        update_parts.append("name = EXCLUDED.name")
        returning.append("name")
    if "avatar_url" in report.columns:
        insert_columns.append("avatar_url")
        values.append(":avatar_url")
        update_parts.append("avatar_url = EXCLUDED.avatar_url")
        returning.append("avatar_url")
    elif "picture" in report.columns:
        insert_columns.append("picture")
        values.append(":avatar_url")
        update_parts.append("picture = EXCLUDED.picture")
        returning.append("picture")
    if "email_verified" in report.columns:
        insert_columns.append("email_verified")
        values.append(":email_verified")
        update_parts.append("email_verified = EXCLUDED.email_verified")
        returning.append("email_verified")
    if "updated_at" in report.columns:
        update_parts.append("updated_at = now()")
    if "created_at" in report.columns:
        insert_columns.append("created_at")
        values.append("now()")
    if "updated_at" in report.columns:
        insert_columns.append("updated_at")
        values.append("now()")

    return f"""
    INSERT INTO app.users ({', '.join(insert_columns)})
    VALUES ({', '.join(values)})
    ON CONFLICT (auth_provider, provider_user_id)
    DO UPDATE SET {', '.join(update_parts)}
    RETURNING {', '.join(returning)}
    """


async def upsert_google_user(engine: AsyncEngine, identity: GoogleIdentity) -> dict[str, Any]:
    if not identity.email_verified:
        raise AppError(status_code=401, component="auth", code="google_email_unverified", message="Google email must be verified")
    report = await ensure_google_user_schema(engine)
    row = await execute_one(
        engine,
        build_google_user_upsert_sql(report),
        {
            "email": identity.email,
            "auth_provider": "google",
            "provider_user_id": identity.sub,
            "name": identity.name,
            "avatar_url": identity.picture,
            "email_verified": True,
        },
    )
    if row is None:
        raise AppError(status_code=503, component="db", code="user_upsert_failed", message="Google user upsert returned no row")
    return row


def build_load_user_sql(report: UserSchemaReport) -> str:
    user_id_column = report.user_id_column
    if user_id_column is None:
        raise ValueError("app.users requires either id or user_id")
    user_id_expr = f"CAST({user_id_column} AS text)"

    name_expr = "name" if "name" in report.columns else "NULL AS name"
    if "avatar_url" in report.columns:
        avatar_expr = "avatar_url"
    elif "picture" in report.columns:
        avatar_expr = "picture AS avatar_url"
    else:
        avatar_expr = "NULL AS avatar_url"
    return f"""
    SELECT {user_id_expr} AS id, email, auth_provider, provider_user_id, {name_expr}, {avatar_expr}
    FROM app.users
    WHERE {user_id_expr} = :user_id AND auth_provider = 'google'
    """


async def load_user_by_id(engine: AsyncEngine, user_id: str) -> dict[str, Any] | None:
    report = await ensure_google_user_schema(engine)
    return await fetch_one(engine, build_load_user_sql(report), {"user_id": user_id})
