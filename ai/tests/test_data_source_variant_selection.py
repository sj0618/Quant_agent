from __future__ import annotations

import importlib
import os
import sys

import pytest


MODULE_NAME = "ai_graph.data_sources"
VARIANT_ENV = "AI_DATA_SOURCE_VARIANT"


@pytest.fixture(autouse=True)
def _restore_default_data_sources_module() -> None:
    yield
    os.environ.pop(VARIANT_ENV, None)
    sys.modules.pop(MODULE_NAME, None)
    importlib.import_module(MODULE_NAME)


def _load_data_sources_module(variant: str | None):
    if variant is None:
        os.environ.pop(VARIANT_ENV, None)
    else:
        os.environ[VARIANT_ENV] = variant
    sys.modules.pop(MODULE_NAME, None)
    return importlib.import_module(MODULE_NAME)


def test_data_sources_defaults_to_db_variant() -> None:
    module = _load_data_sources_module(None)

    assert module.ACTIVE_DATA_SOURCE_VARIANT == "db"
    assert module.PostgresPipelineDataSource.__module__.endswith(".db")
    assert module.load_pipeline_data_from_env.__module__.endswith(".db")


def test_data_sources_can_switch_to_db_test_variant() -> None:
    module = _load_data_sources_module("db_test")

    assert module.ACTIVE_DATA_SOURCE_VARIANT == "db_test"
    assert module.PostgresPipelineDataSource.__module__.endswith(".db_test")
    assert module.load_pipeline_data_from_env.__module__.endswith(".db_test")
