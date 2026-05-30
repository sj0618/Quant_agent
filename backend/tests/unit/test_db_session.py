from __future__ import annotations

import pytest

from app.db.session import execute_one


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


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


@pytest.mark.asyncio
async def test_execute_one_runs_returning_statement_inside_committing_transaction():
    engine = FakeEngine({"id": "user-1", "email": "user@example.co.kr"})

    row = await execute_one(engine, "INSERT INTO app.users (email) VALUES (:email) RETURNING id", {"email": "user@example.co.kr"})

    assert row == {"id": "user-1", "email": "user@example.co.kr"}
    assert engine.transaction_opened is True
    assert engine.committed is True
    assert engine.rolled_back is False
