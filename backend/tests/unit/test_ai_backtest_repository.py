from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.db.ai_backtest_repository import SqlAIBacktestRepository
from app.schemas.ai_backtest import ModelCallLogBundle, PromptLogBundle


class FakeConnection:
    def __init__(self, *, fail_on: int | None = None) -> None:
        self.executions = []
        self.fail_on = fail_on

    async def execute(self, statement, params) -> None:
        self.executions.append((str(statement), params))
        if self.fail_on == len(self.executions):
            raise RuntimeError("injected constraint failure")


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.exited_with = None

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.exited_with = exc_type


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.transaction = FakeTransaction(connection)
        self.begin_calls = 0

    def begin(self) -> FakeTransaction:
        self.begin_calls += 1
        return self.transaction


def make_bundle() -> ModelCallLogBundle:
    return ModelCallLogBundle(
        task_type="backtest_code_generation",
        provider="aoai",
        model_name="gpt-test",
        response_schema_name="quantagent.backtest_code.v1",
        web_search_used=True,
        status="succeeded",
        prompt_log=PromptLogBundle(
            system_prompt="full system prompt",
            user_prompt="full user prompt",
            assistant_response="full assistant response",
            masked=False,
        ),
    )


def test_model_call_requires_one_prompt_bundle() -> None:
    with pytest.raises(ValidationError):
        ModelCallLogBundle(task_type="backtest_code_generation")


def test_model_and_prompt_use_one_transaction_and_execution_correlation() -> None:
    connection = FakeConnection()
    engine = FakeEngine(connection)
    repository = SqlAIBacktestRepository(engine)  # type: ignore[arg-type]
    trace_id = uuid4()
    execution_id = uuid4()

    call_id = asyncio.run(
        repository.create_model_call_log(
            trace_id=trace_id,
            execution_id=execution_id,
            user_id=7,
            session_id=None,
            message_id=None,
            code_id=None,
            bundle=make_bundle(),
        )
    )

    assert engine.begin_calls == 1
    assert len(connection.executions) == 2
    model_sql, model_params = connection.executions[0]
    prompt_sql, prompt_params = connection.executions[1]
    assert "execution_id" in model_sql
    assert model_params["trace_id"] == str(trace_id)
    assert model_params["execution_id"] == str(execution_id)
    assert model_params["response_schema_name"] == "quantagent.backtest_code.v1"
    assert model_params["web_search_used"] is True
    assert prompt_params["call_id"] == model_params["call_id"] == str(call_id)
    assert prompt_params["system_prompt"] == "full system prompt"
    assert prompt_params["user_prompt"] == "full user prompt"
    assert prompt_params["assistant_response"] == "full assistant response"
    assert "INSERT INTO app.ai_prompt_log" in prompt_sql


def test_prompt_insert_failure_exits_the_shared_transaction_with_error() -> None:
    connection = FakeConnection(fail_on=2)
    engine = FakeEngine(connection)
    repository = SqlAIBacktestRepository(engine)  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc_info:
        asyncio.run(
            repository.create_model_call_log(
                trace_id=uuid4(),
                execution_id=uuid4(),
                user_id=None,
                session_id=None,
                message_id=None,
                code_id=None,
                bundle=make_bundle(),
            )
        )

    assert exc_info.value.code == "db_query_failed"
    assert engine.begin_calls == 1
    assert engine.transaction.exited_with is RuntimeError
