from __future__ import annotations

from fastapi import FastAPI

from app.main import app, create_app


def test_app_module_import_and_composition_do_not_require_runtime_credentials():
    assert isinstance(app, FastAPI)
    assert isinstance(create_app(), FastAPI)