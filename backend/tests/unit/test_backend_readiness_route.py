from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.routes import readiness as readiness_module
from app.core.config import ConfigurationError
from app.core.errors import AppError
from app.main import create_app
from tests.unit.test_auth_config import valid_settings


class ReadyRedis:
    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> None:
        return None


class FailingRedis(ReadyRedis):
    async def ping(self) -> bool:
        raise RuntimeError("redis password=super-secret failed")

    async def get(self, key: str) -> None:
        raise RuntimeError("redis password=super-secret failed")


def _patch_runtime(
    monkeypatch,
    *,
    settings,
    main_engine,
    trading_engine,
    redis_client,
    check_db,
) -> None:
    def fake_load_settings():
        return settings

    def fake_create_db_engine(runtime_settings):
        assert runtime_settings is settings
        return main_engine

    def fake_create_trading_data_db_engine(runtime_settings):
        assert runtime_settings is settings
        return trading_engine

    def fake_create_redis_client(redis_url: str | None):
        return redis_client

    async def fake_dispose_db_engine(engine):
        return None

    monkeypatch.setattr(main_module, "load_settings", fake_load_settings)
    monkeypatch.setattr(main_module, "create_db_engine", fake_create_db_engine)
    monkeypatch.setattr(main_module, "create_trading_data_db_engine", fake_create_trading_data_db_engine)
    monkeypatch.setattr(main_module, "create_redis_client", fake_create_redis_client)
    monkeypatch.setattr(main_module, "dispose_db_engine", fake_dispose_db_engine)
    monkeypatch.setattr(readiness_module, "check_db", check_db)


def _response_checks(response):
    return {check["name"]: check for check in response.json()["checks"]}


def test_backend_readiness_returns_ready_when_db_redis_auth_and_trading_data_are_ready(monkeypatch):
    settings = valid_settings(TRADING_DATA_DATABASE_URL="postgresql://trading-db.local:5432/trading_data")
    main_engine = object()
    trading_engine = object()
    redis_client = ReadyRedis()
    seen: list[object] = []

    async def fake_check_db(engine):
        seen.append(engine)
        return {"status": "ok", "check": "SELECT 1", "value": 1}

    _patch_runtime(
        monkeypatch,
        settings=settings,
        main_engine=main_engine,
        trading_engine=trading_engine,
        redis_client=redis_client,
        check_db=fake_check_db,
    )

    with TestClient(create_app(), base_url="https://api.example.co.kr") as client:
        response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    checks = _response_checks(response)
    assert checks["auth_runtime"] == {"name": "auth_runtime", "ready": True, "reason": None}
    assert checks["main_db"] == {"name": "main_db", "ready": True, "reason": None}
    assert checks["trading_data_db"] == {"name": "trading_data_db", "ready": True, "reason": None}
    assert checks["redis"] == {"name": "redis", "ready": True, "reason": None}
    assert seen == [main_engine, trading_engine]
    assert "super-secret" not in response.text


def test_backend_readiness_rejects_unavailable_main_db(monkeypatch):
    settings = valid_settings(TRADING_DATA_DATABASE_URL="postgresql://trading-db.local:5432/trading_data")
    main_engine = object()
    trading_engine = object()
    redis_client = ReadyRedis()

    async def fake_check_db(engine):
        if engine is main_engine:
            raise AppError(
                status_code=503,
                component="db",
                code="db_unavailable",
                message="Database connectivity check failed",
                details={"error": "postgresql://secret-user:secret-pass@db/quant_agent"},
            )
        return {"status": "ok", "check": "SELECT 1", "value": 1}

    _patch_runtime(
        monkeypatch,
        settings=settings,
        main_engine=main_engine,
        trading_engine=trading_engine,
        redis_client=redis_client,
        check_db=fake_check_db,
    )

    with TestClient(create_app(), base_url="https://api.example.co.kr") as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    checks = _response_checks(response)
    assert checks["main_db"] == {
        "name": "main_db",
        "ready": False,
        "reason": "db_unavailable",
    }
    assert checks["trading_data_db"]["ready"] is True
    assert "secret-user" not in response.text


def test_backend_readiness_rejects_missing_trading_data_db(monkeypatch):
    settings = valid_settings()
    main_engine = object()
    redis_client = ReadyRedis()

    async def fake_check_db(engine):
        return {"status": "ok", "check": "SELECT 1", "value": 1}

    _patch_runtime(
        monkeypatch,
        settings=settings,
        main_engine=main_engine,
        trading_engine=None,
        redis_client=redis_client,
        check_db=fake_check_db,
    )

    with TestClient(create_app(), base_url="https://api.example.co.kr") as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    checks = _response_checks(response)
    assert checks["trading_data_db"] == {
        "name": "trading_data_db",
        "ready": False,
        "reason": "trading_data_db_required",
    }


def test_backend_readiness_rejects_redis_ping_failure(monkeypatch):
    settings = valid_settings(TRADING_DATA_DATABASE_URL="postgresql://trading-db.local:5432/trading_data")
    main_engine = object()
    trading_engine = object()
    redis_client = FailingRedis()

    async def fake_check_db(engine):
        return {"status": "ok", "check": "SELECT 1", "value": 1}

    _patch_runtime(
        monkeypatch,
        settings=settings,
        main_engine=main_engine,
        trading_engine=trading_engine,
        redis_client=redis_client,
        check_db=fake_check_db,
    )

    with TestClient(create_app(), base_url="https://api.example.co.kr") as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    checks = _response_checks(response)
    assert checks["redis"] == {
        "name": "redis",
        "ready": False,
        "reason": "redis_unavailable",
    }
    assert "super-secret" not in response.text


def test_backend_readiness_rejects_disabled_auth_runtime(monkeypatch):
    settings = valid_settings(
        AUTH_ENABLED=False,
        TRADING_DATA_DATABASE_URL="postgresql://trading-db.local:5432/trading_data",
    )
    main_engine = object()
    trading_engine = object()
    redis_client = ReadyRedis()

    async def fake_check_db(engine):
        return {"status": "ok", "check": "SELECT 1", "value": 1}

    _patch_runtime(
        monkeypatch,
        settings=settings,
        main_engine=main_engine,
        trading_engine=trading_engine,
        redis_client=redis_client,
        check_db=fake_check_db,
    )

    with TestClient(create_app(), base_url="https://api.example.co.kr") as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    checks = _response_checks(response)
    assert checks["auth_runtime"] == {
        "name": "auth_runtime",
        "ready": False,
        "reason": "auth_disabled",
    }


def test_backend_readiness_rejects_invalid_startup_configuration(monkeypatch):
    def fake_load_settings():
        raise ConfigurationError(
            "Invalid or missing backend configuration",
            {
                "details": [
                    {
                        "loc": ["REDIS_URL"],
                        "msg": "Field required",
                        "input": "redis://secret-user:secret-pass@redis.local:6379/0",
                    }
                ]
            },
        )

    async def fake_check_db(engine):
        return {"status": "ok", "check": "SELECT 1", "value": 1}

    async def fake_dispose_db_engine(_engine):
        return None

    monkeypatch.setattr(main_module, "load_settings", fake_load_settings)
    monkeypatch.setattr(main_module, "create_db_engine", lambda _settings: object())
    monkeypatch.setattr(main_module, "create_trading_data_db_engine", lambda _settings: object())
    monkeypatch.setattr(main_module, "create_redis_client", lambda _redis_url: ReadyRedis())
    monkeypatch.setattr(main_module, "dispose_db_engine", fake_dispose_db_engine)
    monkeypatch.setattr(readiness_module, "check_db", fake_check_db)

    with TestClient(create_app(), base_url="https://api.example.co.kr") as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    checks = _response_checks(response)
    assert checks["auth_runtime"] == {
        "name": "auth_runtime",
        "ready": False,
        "reason": "invalid_config",
    }
    assert "secret-user" not in response.text
