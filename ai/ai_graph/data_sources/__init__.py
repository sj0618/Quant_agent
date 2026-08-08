from __future__ import annotations

import os
from importlib import import_module
from types import ModuleType


AI_DATA_SOURCE_VARIANT_ENV = "AI_DATA_SOURCE_VARIANT"
_DEFAULT_DATA_SOURCE_VARIANT = "db"
_DATA_SOURCE_VARIANT_ALIASES = {
    "benchmark": "db_test",
    "db": "db",
    "db_test": "db_test",
    "fast": "db_test",
    "test": "db_test",
}


def _resolve_data_source_variant() -> str:
    raw = os.environ.get(AI_DATA_SOURCE_VARIANT_ENV, "").strip().lower()
    if not raw:
        return _DEFAULT_DATA_SOURCE_VARIANT
    try:
        return _DATA_SOURCE_VARIANT_ALIASES[raw]
    except KeyError as exc:
        allowed = ", ".join(sorted(set(_DATA_SOURCE_VARIANT_ALIASES)))
        raise ValueError(
            f"{AI_DATA_SOURCE_VARIANT_ENV} must be one of: {allowed}"
        ) from exc


def _load_data_source_module() -> tuple[str, ModuleType]:
    variant = _resolve_data_source_variant()
    module = import_module(f".{variant}", __name__)
    return variant, module


ACTIVE_DATA_SOURCE_VARIANT, _impl = _load_data_source_module()

DataSourceConfig = _impl.DataSourceConfig
PipelineDataBundle = _impl.PipelineDataBundle
PipelineDataUnavailableError = _impl.PipelineDataUnavailableError
PostgresPipelineDataSource = _impl.PostgresPipelineDataSource
load_pipeline_data_from_env = _impl.load_pipeline_data_from_env
screening_data_families = _impl.screening_data_families
screening_profile = _impl.screening_profile

__all__ = [
    "ACTIVE_DATA_SOURCE_VARIANT",
    "DataSourceConfig",
    "PipelineDataBundle",
    "PipelineDataUnavailableError",
    "PostgresPipelineDataSource",
    "load_pipeline_data_from_env",
    "screening_data_families",
    "screening_profile",
]
