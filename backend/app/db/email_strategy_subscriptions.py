from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import AppError
from app.db.session import fetch_all
from app.schemas.email_strategy_subscriptions import EmailStrategySubscriptionItem, EmailStrategySubscriptionsResponse

EMAIL_SUBSCRIPTION_COMPONENT = "email_strategy_subscriptions"
MAX_SUBSCRIPTIONS = 3


@asynccontextmanager
async def _transaction(db: Any):
    if isinstance(db, AsyncConnection) or not hasattr(db, "begin"):
        yield db
        return
    async with db.begin() as connection:
        yield connection


async def _list_rows(db: Any, user_id: str | int) -> list[dict[str, Any]]:
    return await fetch_all(
        db,
        """
        SELECT subscription.strategy_id, profile.name AS display_name, subscription.created_at
        FROM app.email_digest_subscription AS subscription
        JOIN app.strategy_report_profile AS profile ON profile.strategy_id = subscription.strategy_id
        JOIN app.strategy AS strategy
          ON strategy.strategy_id = subscription.strategy_id
         AND strategy.user_id = subscription.user_id
        WHERE subscription.user_id = CAST(:user_id AS bigint)
        ORDER BY subscription.created_at, subscription.strategy_id
        """,
        {"user_id": int(user_id)},
    )


def _response(rows: list[dict[str, Any]]) -> EmailStrategySubscriptionsResponse:
    return EmailStrategySubscriptionsResponse(
        items=[
            EmailStrategySubscriptionItem(
                strategyId=str(row["strategy_id"]),
                displayName=row.get("display_name"),
                enabled=True,
                createdAt=row["created_at"],
                updatedAt=row["created_at"],
            )
            for row in rows
        ],
        subscriptionCount=len(rows),
        maxSubscriptions=MAX_SUBSCRIPTIONS,
    )


async def list_subscriptions(db: Any, *, user_id: str | int) -> EmailStrategySubscriptionsResponse:
    return _response(await _list_rows(db, user_id))


async def save_subscription(
    db: Any, *, user_id: str | int, strategy_id: str, display_name: str | None = None
) -> EmailStrategySubscriptionsResponse:
    del display_name  # display names are authoritative in strategy_report_profile
    normalized_strategy_id = strategy_id.strip()
    if not normalized_strategy_id:
        raise AppError(
            status_code=422,
            component=EMAIL_SUBSCRIPTION_COMPONENT,
            code="email_strategy_subscription_invalid",
            message="Strategy id is required",
        )
    async with _transaction(db) as connection:
        await connection.execute(text("SELECT pg_advisory_xact_lock(CAST(:user_id AS bigint))"), {"user_id": int(user_id)})
        strategy = (
            await connection.execute(
                text(
                    "SELECT profile.strategy_id "
                    "FROM app.strategy_report_profile AS profile "
                    "JOIN app.strategy AS strategy ON strategy.strategy_id = profile.strategy_id "
                    "WHERE profile.strategy_id = :strategy_id "
                    "AND strategy.user_id = CAST(:user_id AS bigint)"
                ),
                {"strategy_id": normalized_strategy_id, "user_id": int(user_id)},
            )
        ).mappings().first()
        if strategy is None:
            raise AppError(
                status_code=404,
                component=EMAIL_SUBSCRIPTION_COMPONENT,
                code="email_strategy_not_found",
                message="Strategy was not found",
            )
        existing = (
            await connection.execute(
                text(
                    "SELECT 1 FROM app.email_digest_subscription "
                    "WHERE user_id = CAST(:user_id AS bigint) AND strategy_id = :strategy_id"
                ),
                {"user_id": int(user_id), "strategy_id": normalized_strategy_id},
            )
        ).first()
        if existing is None:
            count = int(
                (
                    await connection.execute(
                        text("SELECT count(*) FROM app.email_digest_subscription WHERE user_id = CAST(:user_id AS bigint)"),
                        {"user_id": int(user_id)},
                    )
                ).scalar_one()
            )
            if count >= MAX_SUBSCRIPTIONS:
                raise AppError(
                    status_code=409,
                    component=EMAIL_SUBSCRIPTION_COMPONENT,
                    code="email_strategy_subscription_limit",
                    message="Email strategy subscription limit exceeded",
                    details={"maxSubscriptions": MAX_SUBSCRIPTIONS},
                )
            await connection.execute(
                text(
                    "INSERT INTO app.email_digest_subscription (user_id, strategy_id) "
                    "VALUES (CAST(:user_id AS bigint), :strategy_id) ON CONFLICT DO NOTHING"
                ),
                {"user_id": int(user_id), "strategy_id": normalized_strategy_id},
            )
        rows = await _list_rows(connection, user_id)
    return _response(rows)


async def delete_subscription(db: Any, *, user_id: str | int, strategy_id: str) -> EmailStrategySubscriptionsResponse:
    async with _transaction(db) as connection:
        await connection.execute(text("SELECT pg_advisory_xact_lock(CAST(:user_id AS bigint))"), {"user_id": int(user_id)})
        await connection.execute(
            text(
                "DELETE FROM app.email_digest_subscription "
                "WHERE user_id = CAST(:user_id AS bigint) AND strategy_id = :strategy_id"
            ),
            {"user_id": int(user_id), "strategy_id": strategy_id},
        )
        rows = await _list_rows(connection, user_id)
    return _response(rows)
