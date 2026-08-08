"""Benchmark-friendly variant of :mod:`ai_graph.data_sources.db`.

This module keeps the same public surface as ``db.py`` but short-circuits the
expensive price-path and DART joins for screening profiles that do not consume
them in the predicate itself.

For those profiles we still populate a deterministic ranking score in the
``relative_strength_20d`` / ``relative_strength_60d`` slots so the rest of the
pipeline can keep using the existing candidate cap logic during performance
experiments.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .db import *  # noqa: F401,F403 - re-export the baseline public API
from .db import (
    DATABASE_DSN_ENV_CANDIDATES,
    KIS_FEATURE_FRAME_VIEW,
    PostgresPipelineDataSource as _BasePostgresPipelineDataSource,
    _fixture_bundle,
    _financial_sql,
    _mart_frame_sql,
    _optional_float_value,
    _prev_rsi_sql,
)


_FAST_SCREENING_PROFILES = {
    # Pure TA screens that can be ranked without the market-relative path scan.
    "rsi_rebound",
    "pullback_trend",
    "bollinger_squeeze",
    # Fundamental profiles can reuse the frame + DART snapshot and a cheap proxy.
    "value_quality",
    "quality_growth",
    "growth_momentum",
}

_FAST_PROFILE_REQUIRES_DART = {
    "value_quality",
    "quality_growth",
    "growth_momentum",
}


def _proxy_ranking_score(profile: str, row: Mapping[str, Any]) -> tuple[float | None, str]:
    """Return a cheap ranking score and a human-readable proxy label.

    The score only exists so the existing candidate cap logic can continue to
    sort rows after we skip the market-relative path scan.
    """

    if profile == "rsi_rebound":
        rsi = _optional_float_value(row.get("rsi"))
        if rsi is None:
            return None, "rsi"
        return 100.0 - rsi, "100 - rsi"

    if profile == "pullback_trend":
        close = _optional_float_value(row.get("close"))
        sma20 = _optional_float_value(row.get("sma20"))
        if close is None or sma20 is None or sma20 <= 0:
            return None, "distance_to_sma20"
        score = 1.0 - abs(close / sma20 - 1.0)
        sma200 = _optional_float_value(row.get("sma200"))
        if sma200 is not None:
            score += 0.05 if close > sma200 else -0.05
        return score, "distance_to_sma20_plus_sma200"

    if profile == "bollinger_squeeze":
        width = _optional_float_value(row.get("bb_width"))
        if width is None:
            return None, "bb_width"
        return -width, "-bb_width"

    if profile == "value_quality":
        roe = _optional_float_value(row.get("roe"))
        debt = _optional_float_value(row.get("debt_to_equity"))
        if roe is None and debt is None:
            return None, "roe_minus_debt_to_equity"
        return (roe or 0.0) - (debt or 0.0), "roe_minus_debt_to_equity"

    if profile == "quality_growth":
        roe = _optional_float_value(row.get("roe"))
        operating_margin = _optional_float_value(row.get("operating_margin"))
        revenue_growth = _optional_float_value(row.get("revenue_growth_yoy"))
        if roe is None and operating_margin is None and revenue_growth is None:
            return None, "quality_growth_composite"
        return (
            (roe or 0.0) + (operating_margin or 0.0) + (revenue_growth or 0.0),
            "roe_plus_operating_margin_plus_revenue_growth",
        )

    if profile == "growth_momentum":
        revenue_growth = _optional_float_value(row.get("revenue_growth_yoy"))
        close = _optional_float_value(row.get("close"))
        sma50 = _optional_float_value(row.get("sma50"))
        if revenue_growth is None and close is None:
            return None, "revenue_growth_yoy"
        trend_bonus = 0.0
        if close is not None and sma50 is not None and sma50 > 0:
            trend_bonus = close / sma50 - 1.0
        return (revenue_growth or 0.0) + trend_bonus, "revenue_growth_yoy_plus_sma50"

    return None, "none"


class FastPostgresPipelineDataSource(_BasePostgresPipelineDataSource):
    """Profile-aware screening variant for benchmark runs.

    The expensive path scan is skipped for profiles whose screen does not read
    market-relative path features. A profile-local ranking proxy fills the same
    candidate slot so the rest of the pipeline can still cap and order matches.
    """

    def _load_screening_frame(
        self, conn: Any, *, sector: str | None, profile: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if profile not in _FAST_SCREENING_PROFILES:
            return super()._load_screening_frame(conn, sector=sector, profile=profile)

        as_of = self._resolve_screening_date(conn)
        if as_of is None:
            return [], {"as_of_date": None, "reason": "no recent rows in the price table"}

        frame_rows = conn.execute(
            _mart_frame_sql(sector=bool(sector)),
            {"as_of": as_of, "sector": sector},
        ).fetchall()

        prev_date = self._resolve_previous_trading_date(conn, as_of)
        prev_rsi_by_ticker: dict[str, Any] = {}
        if profile == "rsi_rebound" and prev_date is not None:
            prev_rsi_by_ticker = {
                str(row["ticker"]).zfill(6): row.get("prev_rsi")
                for row in conn.execute(_prev_rsi_sql(), {"prev": prev_date}).fetchall()
            }

        financials_by_symbol: dict[str, Mapping[str, Any]] = {}
        if profile in _FAST_PROFILE_REQUIRES_DART:
            financials_by_symbol = {
                str(row["symbol"]).zfill(6): row
                for row in conn.execute(_financial_sql(), {"as_of": as_of}).fetchall()
            }

        rows: list[dict[str, Any]] = []
        for frame_row in frame_rows:
            ticker = str(frame_row.get("ticker") or "").zfill(6)
            row = dict(frame_row)
            row["ticker"] = ticker

            score, proxy_label = _proxy_ranking_score(profile, row)
            row["relative_strength_20d"] = score
            row["relative_strength_60d"] = score

            if profile == "rsi_rebound":
                row["prev_rsi"] = prev_rsi_by_ticker.get(ticker)
            else:
                row["prev_rsi"] = None

            financial = financials_by_symbol.get(ticker)
            if financial is not None:
                row["financial_period_end"] = financial.get("financial_period_end")
                for field in (
                    "roe",
                    "debt_to_equity",
                    "operating_margin",
                    "revenue_growth_yoy",
                ):
                    row[field] = financial.get(field)
                eps = _optional_float_value(financial.get("eps"))
                close = _optional_float_value(frame_row.get("close"))
                row["per"] = close / eps if eps and eps > 0 and close is not None else None

            rows.append(row)

        trace = {
            "as_of_date": as_of.isoformat(),
            "previous_trading_date": prev_date.isoformat() if prev_date else None,
            "indicator_source": KIS_FEATURE_FRAME_VIEW,
            "indicators_read": list(INDICATOR_FIELDS),
            "path_features_computed": [],
            "path_lookback_days": 0,
            "frame_rows": len(frame_rows),
            "relative_strength_benchmark": None,
            "path_query_skipped": True,
            "ranking_mode": "proxy",
            "ranking_proxy": proxy_label,
        }
        return rows, trace


PostgresPipelineDataSource = FastPostgresPipelineDataSource


def load_pipeline_data_from_env(query: str, trace_id: str) -> PipelineDataBundle:
    config = DataSourceConfig.from_env()
    if not config.database_dsn:
        return _fixture_bundle(
            f"database DSN is not set in any of {', '.join(DATABASE_DSN_ENV_CANDIDATES)}.",
            query=query,
        )
    return PostgresPipelineDataSource(config).load(query, trace_id)
