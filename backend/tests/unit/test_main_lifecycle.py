from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import create_app


def _make_settings(*, trading_data_url):
    return SimpleNamespace(
        sqlalchemy_database_url="postgresql+asyncpg://main-db/quant_agent",
        trading_data_sqlalchemy_database_url=trading_data_url,
        redis_url_value=None,
    )


def test_lifespan_attaches_and_disposes_trading_data_engine_when_configured(monkeypatch):
    settings = _make_settings(trading_data_url="postgresql+asyncpg://trading-db/quant_agent")
    main_engine = object()
    trading_engine = object()
    disposed: list[object] = []
    seen: dict[str, object] = {}

    def fake_load_settings():
        return settings

    def fake_create_db_engine(runtime_settings):
        seen["main_settings"] = runtime_settings
        return main_engine

    def fake_create_trading_data_db_engine(runtime_settings):
        seen["trading_settings"] = runtime_settings
        return trading_engine

    async def fake_dispose_db_engine(engine):
        disposed.append(engine)

    monkeypatch.setattr(main_module, "load_settings", fake_load_settings)
    monkeypatch.setattr(main_module, "create_db_engine", fake_create_db_engine)
    monkeypatch.setattr(main_module, "create_trading_data_db_engine", fake_create_trading_data_db_engine)
    monkeypatch.setattr(main_module, "dispose_db_engine", fake_dispose_db_engine)

    with TestClient(create_app(), base_url="https://api.example.co.kr") as client:
        assert client.app.state.db_engine is main_engine
        assert client.app.state.trading_data_db_engine is trading_engine
        assert seen == {"main_settings": settings, "trading_settings": settings}

    assert disposed == [trading_engine, main_engine]


def test_lifespan_keeps_trading_data_engine_unset_when_url_absent(monkeypatch):
    settings = _make_settings(trading_data_url=None)
    main_engine = object()
    disposed: list[object] = []
    seen: list[object] = []

    def fake_load_settings():
        return settings

    def fake_create_db_engine(runtime_settings):
        assert runtime_settings is settings
        return main_engine

    def fake_create_trading_data_db_engine(runtime_settings):
        seen.append(runtime_settings)
        return None

    async def fake_dispose_db_engine(engine):
        disposed.append(engine)

    monkeypatch.setattr(main_module, "load_settings", fake_load_settings)
    monkeypatch.setattr(main_module, "create_db_engine", fake_create_db_engine)
    monkeypatch.setattr(main_module, "create_trading_data_db_engine", fake_create_trading_data_db_engine)
    monkeypatch.setattr(main_module, "dispose_db_engine", fake_dispose_db_engine)

    with TestClient(create_app(), base_url="https://api.example.co.kr") as client:
        assert client.app.state.db_engine is main_engine
        assert client.app.state.trading_data_db_engine is None

    assert seen == [settings]
    assert disposed == [main_engine]


def test_lifespan_cleans_up_main_engine_when_trading_data_engine_creation_fails(monkeypatch):
    settings = _make_settings(trading_data_url="postgresql+asyncpg://trading-db/quant_agent")
    main_engine = object()
    disposed: list[object] = []

    def fake_load_settings():
        return settings

    def fake_create_db_engine(runtime_settings):
        assert runtime_settings is settings
        return main_engine

    def fake_create_trading_data_db_engine(runtime_settings):
        assert runtime_settings is settings
        raise RuntimeError("trading-data engine creation failed")

    async def fake_dispose_db_engine(engine):
        disposed.append(engine)

    monkeypatch.setattr(main_module, "load_settings", fake_load_settings)
    monkeypatch.setattr(main_module, "create_db_engine", fake_create_db_engine)
    monkeypatch.setattr(main_module, "create_trading_data_db_engine", fake_create_trading_data_db_engine)
    monkeypatch.setattr(main_module, "dispose_db_engine", fake_dispose_db_engine)

    with pytest.raises(RuntimeError, match="trading-data engine creation failed"):
        with TestClient(create_app(), base_url="https://api.example.co.kr"):
            pass

    assert disposed == [main_engine]
