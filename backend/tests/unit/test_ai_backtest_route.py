from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import ai_backtest
from app.core.errors import register_exception_handlers
from app.schemas.ai_backtest import AICodeBacktestFlowResult
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


def make_client(service: FakeService):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(ai_backtest.router)
    app.state.settings = valid_settings()
    app.state.redis_client = FakeRedis()
    app.state.db_engine = object()
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    app.state.ai_backtest_service = service
    return TestClient(app, base_url="https://api.example.co.kr")


def test_generate_and_run_backtest_route_uses_bound_service(monkeypatch):
    service = FakeService()
    client = make_client(service)

    async def fake_user_id(_request):
        return 17

    monkeypatch.setattr(ai_backtest, "get_authenticated_user_id", fake_user_id)
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
