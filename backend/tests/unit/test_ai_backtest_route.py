from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import ai_backtest
from app.core.errors import AppError, register_exception_handlers
from app.schemas.ai_backtest import (
    AIBacktestErrorResponse,
    AIBacktestRunningResponse,
    AIBacktestExecutionContext,
    AICodeBacktestFlowResult,
)
from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis


@dataclass
class FakeService:
    captured_payload: object | None = None

    async def run_generated_backtest(self, payload):
        self.captured_payload = payload
        return AICodeBacktestFlowResult(
            trace_id=uuid4(),
            parse_id=uuid4(),
            code_id=uuid4(),
            validation_id=uuid4(),
            execution_run_id=uuid4(),
            run_id=uuid4(),
            report_id=uuid4(),
            code_status="executed",
            execution_status="succeeded",
        )
@dataclass
class ReturningService:
    result: object
    captured_payload: object | None = None

    async def run_generated_backtest(self, payload):
        self.captured_payload = payload
        return self.result


@dataclass
class FailingService:
    error: Exception

    async def run_generated_backtest(self, _payload):
        raise self.error


def request_payload(**overrides):
    payload = {
        "natural_language_prompt": "RSI 반등 전략을 코드 생성해서 실행해줘",
        "target_runtime": "python-sandbox",
        "code_purpose": "backtest",
    }
    payload.update(overrides)
    return payload


def bind_authenticated_user(monkeypatch, user_id: int = 17):
    async def fake_context(_request):
        return AIBacktestExecutionContext(
            user_id=user_id,
            scope_family_id=uuid4(),
            session_hmac="a" * 64,
            session_hmac_version="test-v1",
        )

    monkeypatch.setattr(ai_backtest, "get_authenticated_execution_context", fake_context)




def make_client(service: object, *, raise_server_exceptions: bool = True):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(ai_backtest.router)
    app.state.settings = valid_settings()
    app.state.redis_client = FakeRedis()
    app.state.db_engine = object()
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    app.state.ai_backtest_service = service
    client = TestClient(
        app,
        base_url="https://api.example.co.kr",
        raise_server_exceptions=raise_server_exceptions,
    )
    client.headers["Idempotency-Key"] = "route-test-idempotency-key"
    return client


def test_generate_and_run_backtest_route_uses_bound_service(monkeypatch):
    service = FakeService()
    client = make_client(service)

    bind_authenticated_user(monkeypatch)
    response = client.post(
        "/ai/backtests/generate-and-run",
        json={
            "natural_language_prompt": "RSI 반등 전략을 코드 생성해서 실행해줘",
            "parsed_strategy_jsonb": {"strategy_id": "rsi_rebound", "name": "RSI 반등", "universe": "KOSPI200", "market": "KRX", "timeframe": "daily", "entry_conditions": [{"left": "rsi", "operator": "lte", "right": 30}], "exit_conditions": [], "indicators": ["RSI"], "risk_constraints": {"max_position_pct": 0.1}, "assumptions": [], "source_refs": [], "confidence": 0.9},
            "strategy_id": "rsi_rebound",
            "target_runtime": "python-sandbox",
            "code_purpose": "backtest"
        },
    )

    assert response.status_code == 200
    assert response.json()["code_status"] == "executed"
    assert service.captured_payload is not None
    assert service.captured_payload.user_id == 17
    assert service.captured_payload.target_runtime == "python-sandbox"
def test_generate_and_run_rejects_body_identity_fields_without_invoking_service(monkeypatch):
    service = FakeService()
    client = make_client(service)

    bind_authenticated_user(monkeypatch)
    response = client.post(
        "/ai/backtests/generate-and-run",
        json=request_payload(user_id=999, session_id="raw-session-secret", trace_id=str(uuid4())),
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "request_validation_failed",
        "message": "Request validation failed.",
        "trace_id": None,
        "details": {"fields": [{"location": "body", "code": "extra_forbidden"}] * 3},
    }
    assert "raw-session-secret" not in response.text
    assert service.captured_payload is None
def test_generate_and_run_rejects_replacement_approval_credentials_from_public_body(monkeypatch):
    service = FakeService()
    client = make_client(service)

    bind_authenticated_user(monkeypatch)
    response = client.post(
        "/ai/backtests/generate-and-run",
        json=request_payload(
            replacement_approval_id=str(uuid4()),
            replacement_approval_token="a" * 43,
        ),
    )

    assert response.status_code == 422
    assert response.json()["details"] == {
        "fields": [{"location": "body", "code": "extra_forbidden"}] * 2
    }
    assert service.captured_payload is None



def test_generate_and_run_validation_error_does_not_expose_submitted_input(monkeypatch):
    service = FakeService()
    client = make_client(service)

    bind_authenticated_user(monkeypatch)
    response = client.post(
        "/ai/backtests/generate-and-run",
        json=request_payload(target_runtime="", natural_language_prompt="prompt-secret"),
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "request_validation_failed",
        "message": "Request validation failed.",
        "trace_id": None,
        "details": {"fields": [{"location": "body", "code": "string_too_short"}]},
    }
    assert "prompt-secret" not in response.text


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            AppError(
                status_code=409,
                component="ai_backtest",
                code="duplicate_execution_active",
                message="raw exception secret",
                details={"request_id": str(uuid4()), "state": "claimed", "raw": "secret"},
            ),
            409,
            "duplicate_execution_active",
        ),
        (
            AppError(
                status_code=422,
                component="ai_backtest",
                code="generated_code_rejected",
                message="raw exception secret",
                details={"trace_id": str(uuid4()), "validation_id": str(uuid4()), "errors": ["secret"]},
            ),
            422,
            "generated_code_rejected",
        ),
        (
            AppError(
                status_code=502,
                component="ai_backtest",
                code="code_execution_failed",
                message="raw exception secret",
                details={"trace_id": str(uuid4()), "execution_run_id": str(uuid4()), "stderr": "secret"},
            ),
            502,
            "code_execution_failed",
        ),
        (
            AppError(
                status_code=503,
                component="db",
                code="db_query_failed",
                message="raw exception secret",
                details={"dsn": "postgresql://secret"},
            ),
            503,
            "service_unavailable",
        ),
        (
            AppError(
                status_code=504,
                component="ai_backtest",
                code="code_execution_failed",
                message="raw exception secret",
                details={"trace_id": str(uuid4()), "execution_run_id": str(uuid4()), "stderr": "secret"},
            ),
            504,
            "code_execution_timeout",
        ),
    ],
)
def test_generate_and_run_projects_allowlisted_app_errors(monkeypatch, error, status_code, code):
    client = make_client(FailingService(error))

    bind_authenticated_user(monkeypatch)
    response = client.post("/ai/backtests/generate-and-run", json=request_payload())

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert response.json()["message"] == ai_backtest._ERROR_CATALOG[code][1]
    assert "error" not in response.json()
    assert "secret" not in response.text
    assert "stderr" not in response.text
    assert "dsn" not in response.text


def test_generate_and_run_replays_only_the_sanitized_terminal_error(monkeypatch):
    request_id = uuid4()
    service = ReturningService(
        AIBacktestErrorResponse(
            code="execution_outcome_unknown",
            message="stored raw error",
            details={"request_id": str(request_id), "raw": "terminal-secret"},
        )
    )
    client = make_client(service)

    bind_authenticated_user(monkeypatch)
    response = client.post("/ai/backtests/generate-and-run", json=request_payload())

    assert response.status_code == 409
    assert response.json() == {
        "code": "execution_outcome_unknown",
        "message": "Prior execution outcome is unresolved and cannot be retried automatically.",
        "trace_id": None,
        "details": {"request_id": str(request_id)},
    }
    assert "terminal-secret" not in response.text


def test_generate_and_run_returns_stable_running_response(monkeypatch):
    request_id = uuid4()
    trace_id = uuid4()
    service = ReturningService(
        AIBacktestRunningResponse(
            request_id=request_id,
            trace_id=trace_id,
            state="execution_released",
        )
    )
    client = make_client(service)

    bind_authenticated_user(monkeypatch)
    response = client.post("/ai/backtests/generate-and-run", json=request_payload())

    assert response.status_code == 202
    assert response.json() == {
        "request_id": str(request_id),
        "trace_id": str(trace_id),
        "state": "execution_released",
    }


def test_generate_and_run_unknown_exception_uses_sanitized_global_envelope(monkeypatch):
    client = make_client(FailingService(RuntimeError("unexpected exception secret")), raise_server_exceptions=False)

    bind_authenticated_user(monkeypatch)
    response = client.post("/ai/backtests/generate-and-run", json=request_payload())

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "component": "api",
            "code": "internal_error",
            "message": "Internal server error",
            "details": {},
        }
    }
    assert "unexpected exception secret" not in response.text
def test_generate_and_run_unallowlisted_app_error_uses_sanitized_global_envelope(monkeypatch):
    client = make_client(
        FailingService(
            AppError(
                status_code=502,
                component="provider",
                code="provider_failure",
                message="provider exception secret",
                details={"raw": "provider-secret"},
            )
        )
    )

    bind_authenticated_user(monkeypatch)
    response = client.post("/ai/backtests/generate-and-run", json=request_payload())

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "component": "ai_backtest",
            "code": "backtest_request_failed",
            "message": "Backtest request failed",
            "details": {},
        }
    }
    assert "provider-secret" not in response.text




def test_generate_and_run_openapi_preserves_success_and_declares_replay_and_error_models():
    client = make_client(FakeService())

    responses = client.get("/openapi.json").json()["paths"]["/ai/backtests/generate-and-run"]["post"]["responses"]
    assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith("AICodeBacktestFlowResult")
    for status_code in ("202", "409", "422", "502", "503", "504"):
        assert "application/json" in responses[status_code]["content"]
