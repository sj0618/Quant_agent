"""Benchmark-friendly profile-aware variant of :mod:`ai_graph.data_sources.db`.

This module keeps the public API of the data-source layer but exposes the
profile-aware loader under the report-facing module name. The implementation is
delegated to :mod:`ai_graph.data_sources.db_test`, which preserves the fast
screening path used by the benchmark and deployment experiments while keeping
the public surface stable.
"""

from __future__ import annotations

from collections.abc import Sequence

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


def load_pipeline_data_from_env(
    query: str,
    trace_id: str,
    *,
    screen_current: bool = True,
    required_metrics: Sequence[str] | None = None,
    requires_financials: bool | None = None,
    compact_price_rows: bool = False,
    sector: str | None = None,
    backtest_lookback_years: int | None = None,
    period_locked: bool = False,
) -> PipelineDataBundle:
    config = DataSourceConfig.from_env()
    if period_locked and backtest_lookback_years is None:
        raise ValueError("a locked backtest period requires backtest_lookback_years")
    if backtest_lookback_years is not None:
        if (
            isinstance(backtest_lookback_years, bool)
            or not isinstance(backtest_lookback_years, int)
            or not 1 <= backtest_lookback_years <= 5
        ):
            raise ValueError("backtest_lookback_years must be 1..5")
        config = config.model_copy(
            update={
                "backtest_lookback_years": backtest_lookback_years,
                "period_locked": period_locked,
            }
        )
    if not config.database_dsn:
        bundle = _fixture_bundle(
            f"database DSN is not set in any of {', '.join(DATABASE_DSN_ENV_CANDIDATES)}.", query=query
        )
        return bundle.model_copy(
            update={
                "metadata": {
                    **bundle.metadata,
                    "backtest_lookback_years": config.backtest_lookback_years,
                    "backtest_period_locked": config.period_locked,
                }
            }
        )
    return PostgresPipelineDataSource(config).load(
        query,
        trace_id,
        screen_current=screen_current,
        required_metrics=required_metrics,
        requires_financials=requires_financials,
        compact_price_rows=compact_price_rows,
        sector=sector,
    )
