from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main as main_module
from app.db import session as session_module


class FakeAsyncEngine:
    def __init__(self):
        self.disposed = False

    async def dispose(self):
        self.disposed = True


class FakeRedisClient:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


def test_create_trading_data_db_engine_returns_none_without_configuration_and_builds_engine(monkeypatch):
    assert session_module.create_trading_data_db_engine(SimpleNamespace(trading_data_sqlalchemy_database_url=None)) is None

    observed: dict[str, object] = {}

    def fake_create_async_engine(database_url, pool_pre_ping=True):
        observed["database_url"] = database_url
        observed["pool_pre_ping"] = pool_pre_ping
        return FakeAsyncEngine()

    monkeypatch.setattr(session_module, "create_db_engine_from_url", fake_create_async_engine)

    engine = session_module.create_trading_data_db_engine(
        SimpleNamespace(trading_data_sqlalchemy_database_url="postgresql+asyncpg://trading-data.example/qt")
    )

    assert isinstance(engine, FakeAsyncEngine)
    assert observed == {"database_url": "postgresql+asyncpg://trading-data.example/qt", "pool_pre_ping": True}


def test_main_lifespan_initializes_and_disposes_trading_data_engine(monkeypatch):
    settings = SimpleNamespace(
        sqlalchemy_database_url="postgresql+asyncpg://main.example/qa",
        redis_url_value="redis://unused",
    )
    main_engine = FakeAsyncEngine()
    trading_engine = FakeAsyncEngine()
    fake_redis = FakeRedisClient()

    monkeypatch.setattr(main_module, "load_settings", lambda: settings)
    monkeypatch.setattr(main_module, "create_db_engine", lambda _settings: main_engine)
    monkeypatch.setattr(main_module, "create_trading_data_db_engine", lambda _settings: trading_engine)
    monkeypatch.setattr(main_module, "create_redis_client", lambda _redis_url: fake_redis)

    app = main_module.create_app()
    with TestClient(app) as client:
        assert client.app.state.db_engine is main_engine
        assert client.app.state.trading_data_db_engine is trading_engine
        assert client.app.state.redis_client is fake_redis
        assert client.get("/api/v1/api-status").status_code == 200

    assert main_engine.disposed is True
    assert trading_engine.disposed is True
    assert fake_redis.closed is True
