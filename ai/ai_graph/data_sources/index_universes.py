"""Named KRX index universes (KOSPI200, KOSDAQ150) as point-in-time membership filters.

"KOSPI200 종목" is not a market and not a metric: it is the set of names that were index
constituents *on each date* of the tested window. The warehouse contract for that is
``feature.krx_index_membership_history`` - one row per (symbol_id, index_code) interval,
shaped like the WICS sector history the sector universe filter already reads
(DE/migrations/015_krx_index_membership_history.sql).

Unlike sectors there is deliberately no static fallback: a research node that was told
"KOSPI200 is available" while the loader has no membership rows would seal a universe
the backtest silently widens to the whole market, which is the substitution the refusal
exists to prevent. When the table is absent or empty the index is simply not offered,
and a request that names it is refused with that fact as the reason.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

AI_INDEX_UNIVERSE_CACHE_TTL_SECONDS_ENV = "AI_INDEX_UNIVERSE_CACHE_TTL_SECONDS"
DEFAULT_INDEX_UNIVERSE_CACHE_TTL_SECONDS = 300

INDEX_MEMBERSHIP_HISTORY_TABLE = "feature.krx_index_membership_history"

# Canonical index_code -> the spellings users actually type. Matched case-insensitively.
INDEX_UNIVERSE_ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "KOSPI200": ("KOSPI200", "KOSPI 200", "코스피200", "코스피 200"),
    "KOSDAQ150": ("KOSDAQ150", "KOSDAQ 150", "코스닥150", "코스닥 150"),
}

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"universes": None, "expires_at": 0.0}


def _cache_ttl_seconds() -> int:
    raw = os.environ.get(AI_INDEX_UNIVERSE_CACHE_TTL_SECONDS_ENV)
    return int(raw) if raw else DEFAULT_INDEX_UNIVERSE_CACHE_TTL_SECONDS


def get_known_index_universes(conn: Any | None = None) -> list[str]:
    """Index codes with at least one membership interval in the warehouse, TTL-cached.

    Empty when there is no DSN, the table does not exist, or it holds no rows: all three
    mean the loader cannot restrict a universe by index membership.
    """

    now = time.monotonic()
    cached = _CACHE["universes"]
    if cached is not None and now < _CACHE["expires_at"]:
        return cached
    with _CACHE_LOCK:
        cached = _CACHE["universes"]
        if cached is not None and now < _CACHE["expires_at"]:
            return cached
        universes = _fetch_index_universes(conn)
        if universes:
            _CACHE["universes"] = universes
            _CACHE["expires_at"] = now + _cache_ttl_seconds()
        return universes


def _fetch_index_universes(conn: Any | None) -> list[str]:
    query = f"""
        SELECT DISTINCT index_code
        FROM {INDEX_MEMBERSHIP_HISTORY_TABLE}
        WHERE index_code IS NOT NULL
        ORDER BY index_code
    """
    try:
        if conn is not None:
            rows = conn.execute(query).fetchall()
            return [str(row["index_code"]) for row in rows if row.get("index_code")]

        from .db import DataSourceConfig

        config = DataSourceConfig.from_env()
        if not config.database_dsn:
            return []
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(
            config.database_dsn,
            connect_timeout=config.connect_timeout_seconds,
            row_factory=dict_row,
        ) as short_lived_conn:
            rows = short_lived_conn.execute(query).fetchall()
            return [str(row["index_code"]) for row in rows if row.get("index_code")]
    except Exception:
        return []


def clear_index_universe_cache() -> None:
    """Test helper - force a probe on the next get_known_index_universes() call."""

    with _CACHE_LOCK:
        _CACHE["universes"] = None
        _CACHE["expires_at"] = 0.0


def extract_index_universe_from_query(query: str) -> str | None:
    """The canonical index code a request names, whether or not the warehouse has it.

    Independent of availability on purpose: the research gate needs to know that a
    request asked for KOSPI200 precisely when KOSPI200 cannot be served, so the refusal
    can say so instead of letting the constraint be dropped into a market-wide test.
    """

    normalized = query.upper()
    for code, aliases in INDEX_UNIVERSE_ALIAS_MAP.items():
        if any(alias.upper() in normalized for alias in aliases):
            return code
    return None


def index_universe_unavailable_message(index_code: str) -> str:
    return (
        f"이 배포에는 {index_code}의 날짜별 구성종목(point-in-time membership) 데이터가 없어 "
        f"{index_code} 유니버스를 봉인할 수 없습니다. 유니버스를 코스피/코스닥 전체 또는 "
        f"WICS 섹터로 바꾸거나, {INDEX_MEMBERSHIP_HISTORY_TABLE}에 {index_code} 구성 이력을 적재해야 합니다."
    )


__all__ = [
    "INDEX_MEMBERSHIP_HISTORY_TABLE",
    "INDEX_UNIVERSE_ALIAS_MAP",
    "clear_index_universe_cache",
    "extract_index_universe_from_query",
    "get_known_index_universes",
    "index_universe_unavailable_message",
]
