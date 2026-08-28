"""CORE-FAILURE-01: failures are sorted by exception type, not by message text.

The regression this file exists to prevent: `classify_failure` used to end with
`raw = str(exc).lower()` and three substring checks. Any exception whose message merely
contained "schema", "validation" or "contract" was reported as a pipeline contract
breach, which sent whoever read the failed job to the wrong place.
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from ai_graph.jobs import PipelineStageError, classify_failure


class _Shape(BaseModel):
    count: int


def _validation_error() -> ValidationError:
    try:
        _Shape.model_validate({"count": "not a number"})
    except ValidationError as error:
        return error
    raise AssertionError("expected a ValidationError")


def _psycopg_statement_timeout() -> Exception:
    """A stand-in with the driver's identifying marks and none of its import cost.

    `jobs.py` deliberately does not import psycopg so the module stays usable in
    non-PostgreSQL modes; it identifies driver errors by module name plus SQLSTATE.
    This reproduces exactly those marks.
    """

    class QueryCanceled(Exception):
        sqlstate = "57014"

    QueryCanceled.__module__ = "psycopg.errors"
    return QueryCanceled("canceling statement due to statement timeout")


@pytest.mark.parametrize(
    "message",
    [
        "cache schema warm completed late",
        "validation of the user avatar failed",
        "contract renewal job returned nothing",
    ],
)
def test_a_message_mentioning_schema_is_not_a_contract_breach(message: str) -> None:
    """The exact misclassification the string heuristics produced."""

    diagnostic = classify_failure(RuntimeError(message), stage="backtest")

    assert diagnostic.subcause != "contract_shape_error"
    assert diagnostic.category == "unknown_failure"
    assert diagnostic.subcause == "unknown"


def test_a_real_validation_error_is_a_contract_breach() -> None:
    diagnostic = classify_failure(_validation_error(), stage="backtest")

    assert diagnostic.category == "semantic_failure"
    assert diagnostic.subcause == "contract_shape_error"
    assert diagnostic.retryable is False


def test_a_validation_error_is_found_through_the_cause_chain() -> None:
    wrapper = RuntimeError("node failed")
    wrapper.__cause__ = _validation_error()

    assert classify_failure(wrapper, stage="signal").subcause == "contract_shape_error"


def test_a_statement_timeout_is_recognized_by_sqlstate() -> None:
    diagnostic = classify_failure(_psycopg_statement_timeout(), stage="data_collect")

    assert diagnostic.category == "infrastructure_failure"
    assert diagnostic.subcause == "db_statement_timeout"
    assert diagnostic.retryable is True


def test_a_lookalike_without_the_driver_module_is_not_a_statement_timeout() -> None:
    """SQLSTATE alone is not enough; anything can define an attribute called sqlstate."""

    class NotADriverError(Exception):
        sqlstate = "57014"

    assert classify_failure(NotADriverError("nope"), stage="data_collect").subcause == "unknown"


def test_a_plain_connection_error_is_still_classified() -> None:
    diagnostic = classify_failure(ConnectionError("connect failed"), stage="data_collect")

    assert diagnostic.subcause == "db_connect_timeout"
    assert diagnostic.owner == "data_source_config"


def test_a_provider_transport_failure_is_read_from_the_chain() -> None:
    class LLMClientError(Exception):
        pass

    provider = LLMClientError("provider call failed")
    provider.__cause__ = httpx.ConnectError("connection refused")

    assert classify_failure(provider, stage="signal").subcause == "aoai_connection_error"


def test_the_stage_comes_from_where_the_failure_happened() -> None:
    """The caller's assumed stage loses to the stage the graph actually reached."""

    inner = PipelineStageError("indicator window empty", stage="backtest")
    outer = RuntimeError("job failed")
    outer.__cause__ = inner

    assert classify_failure(outer, stage="finalizing").failure_stage == "backtest"


def test_the_caller_stage_is_used_when_no_stage_was_carried() -> None:
    assert classify_failure(RuntimeError("boom"), stage="finalizing").failure_stage == "finalizing"


def test_a_blank_carried_stage_does_not_erase_the_caller_stage() -> None:
    inner = PipelineStageError("no stage recorded", stage="   ")
    outer = RuntimeError("job failed")
    outer.__cause__ = inner

    assert classify_failure(outer, stage="finalizing").failure_stage == "finalizing"


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("dsn=postgres://user:hunter2@db.internal:5432/prod"),
        ConnectionError("Authorization: Bearer sk-live-abcdef"),
        RuntimeError("Traceback (most recent call last): File ..."),
    ],
)
def test_no_safe_message_repeats_the_raw_exception(exc: Exception) -> None:
    """Every branch returns a fixed sentence, so nothing from the error can ride out."""

    message = classify_failure(exc, stage="data_collect").safe_message.lower()

    assert str(exc).lower() not in message
    for secret in ("hunter2", "postgres://", "bearer", "traceback", "dsn="):
        assert secret not in message
