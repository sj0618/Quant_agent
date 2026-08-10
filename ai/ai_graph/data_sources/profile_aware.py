"""Benchmark-friendly profile-aware variant of :mod:`ai_graph.data_sources.db`.

This module keeps the public API of the data-source layer but exposes the
profile-aware loader under the report-facing module name. The implementation is
delegated to :mod:`ai_graph.data_sources.db_split`, which keeps the same public
surface while allowing the load path to be exercised through the split-mode
variant used by the benchmark and deployment experiments.
"""

from __future__ import annotations

from . import db_split as _impl
from .db_split import *  # noqa: F401,F403 - re-export the benchmark public API
from .db_split import (
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
