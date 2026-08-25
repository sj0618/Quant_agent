from __future__ import annotations

import pytest

from app.db.session import _sql_params_with_bigint_user_id, execute_one, fetch_all, fetch_one


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def all(self):
        if self.row is None:
            return []
        if isinstance(self.row, list):
            return [dict(item) for item in self.row]
        return [dict(self.row)]

    def first(self):
        if self.row is None:
            return None
        if isinstance(self.row, list):
            return dict(self.row[0]) if self.row else None
        return dict(self.row)


class FakeConnection:
    def __init__(self, engine):
        self.engine = engine

    async def execute(self, statement, params):
        self.engine.executed_statement = statement
        self.engine.executed_params = params
        return FakeResult(self.engine.row)


class FakeTransaction:
    def __init__(self, engine):
        self.engine = engine

    async def __aenter__(self):
        self.engine.transaction_opened = True
        return FakeConnection(self.engine)

    async def __aexit__(self, exc_type, _exc, _tb):
        self.engine.committed = exc_type is None
        self.engine.rolled_back = exc_type is not None
        return False


class FakeEngine:
    def __init__(self, row):
        self.row = row
        self.transaction_opened = False
        self.committed = False
        self.rolled_back = False
        self.executed_statement = None
        self.executed_params = None

    def begin(self):
        return FakeTransaction(self)

    def connect(self):
        return FakeTransaction(self)


class ActiveConnection:
    def __init__(self, rows):
        self.rows = rows
        self.executed_statement = None
        self.executed_params = None
        self.execute_calls = 0

    async def execute(self, statement, params):
        self.execute_calls += 1
        self.executed_statement = statement
        self.executed_params = params
        return FakeResult(self.rows)


@pytest.mark.asyncio
async def test_execute_one_runs_returning_statement_inside_committing_transaction():
    engine = FakeEngine({"id": "user-1", "email": "user@example.co.kr"})

    row = await execute_one(engine, "INSERT INTO app.users (email) VALUES (:email) RETURNING id", {"email": "user@example.co.kr"})

    assert row == {"id": "user-1", "email": "user@example.co.kr"}
    assert engine.transaction_opened is True
    assert engine.committed is True
    assert engine.rolled_back is False


@pytest.mark.asyncio
async def test_fetch_helpers_use_active_connection_without_opening_new_transaction():
    connection = ActiveConnection([{"id": "user-1", "email": "user@example.co.kr"}])

    rows = await fetch_all(
        connection,
        "SELECT id, email FROM app.users WHERE user_id = CAST(:user_id AS bigint)",
        {"user_id": " 42 "},
    )
    row = await fetch_one(
        connection,
        "SELECT id, email FROM app.users WHERE user_id = CAST(:user_id AS bigint)",
        {"user_id": " 42 "},
    )

    assert rows == [{"id": "user-1", "email": "user@example.co.kr"}]
    assert row == {"id": "user-1", "email": "user@example.co.kr"}
    assert connection.execute_calls == 2
    assert connection.executed_params["user_id"] == 42


@pytest.mark.asyncio
async def test_execute_one_uses_active_connection_without_beginning_a_nested_transaction():
    connection = ActiveConnection([{"id": "user-1", "email": "user@example.co.kr"}])

    row = await execute_one(
        connection,
        "INSERT INTO app.users (email) VALUES (:email) RETURNING id, email",
        {"email": "user@example.co.kr"},
    )

    assert row == {"id": "user-1", "email": "user@example.co.kr"}
    assert connection.execute_calls == 1
    assert connection.executed_params["email"] == "user@example.co.kr"


def test_sql_params_with_bigint_user_id_normalizes_string_user_ids_for_cast_sql():
    params = _sql_params_with_bigint_user_id(
        "SELECT * FROM app.backtest_run WHERE user_id = CAST(:user_id AS bigint)",
        {"user_id": " 42 ", "other": "value"},
    )

    assert params["user_id"] == 42
    assert params["other"] == "value"
