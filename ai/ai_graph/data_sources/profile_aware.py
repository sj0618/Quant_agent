"""Benchmark-friendly profile-aware variant of :mod:`ai_graph.data_sources.db`.

This module keeps the public API of ``db_test.py`` but gives the benchmark a
stable module name that matches the report labels. The actual implementation is
the same profile-aware screening shortcut used by ``db_test.py``.
"""

from __future__ import annotations

from . import db_test as _impl
from .db_test import *  # noqa: F401,F403 - re-export the benchmark public API
from .db_test import (
    DATABASE_DSN_ENV_CANDIDATES,
    DataSourceConfig,
    PipelineDataBundle,
    _fixture_bundle,
)


class PostgresPipelineDataSource(_impl.PostgresPipelineDataSource):
    """Profile-aware screening variant exposed under its benchmark name."""

    pass


def load_pipeline_data_from_env(query: str, trace_id: str) -> PipelineDataBundle:
    config = DataSourceConfig.from_env()
    if not config.database_dsn:
        return _fixture_bundle(
            f"database DSN is not set in any of {', '.join(DATABASE_DSN_ENV_CANDIDATES)}.",
            query=query,
        )
    return PostgresPipelineDataSource(config).load(query, trace_id)
