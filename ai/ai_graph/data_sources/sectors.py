from __future__ import annotations

import os
import threading
import time
from typing import Any, Sequence

AI_SECTOR_CACHE_TTL_SECONDS_ENV = "AI_SECTOR_CACHE_TTL_SECONDS"
DEFAULT_SECTOR_CACHE_TTL_SECONDS = 300

CANDIDATE_POOL_VIEW = "mart.common_stock_universe_asof"
SECTOR_SOURCE_TABLE = "core.symbol_master"

# Static fallback for offline/fixture mode — mirrors the WICS taxonomy documented in
# DE/docs/data_engineering_runbook.md (26 sectors ingested via DE/scripts/ingest_wics_sectors.py).
WICS_SECTOR_FALLBACK: tuple[str, ...] = (
    "IT가전", "IT하드웨어", "건강관리", "건설,건축관련", "기계", "디스플레이",
    "미디어,교육", "반도체", "보험", "비철,목재등", "상사,자본재", "소매(유통)",
    "소프트웨어", "에너지", "운송", "유틸리티", "은행", "자동차", "조선", "증권",
    "철강", "통신서비스", "필수소비재", "호텔,레저서비스", "화장품,의류,완구", "화학",
)

# Colloquial terms users actually type, mapped to the canonical WICS label.
# Entries marked "approximate" have no exact WICS category and are best-effort.
SECTOR_ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "반도체": ("반도체", "메모리반도체", "파운드리"),
    "건강관리": ("건강관리", "바이오", "제약", "헬스케어"),
    "화장품,의류,완구": ("화장품", "뷰티", "의류", "패션"),
    "소프트웨어": ("소프트웨어", "인터넷", "플랫폼", "게임"),  # approximate
    "IT하드웨어": ("IT하드웨어", "전자부품"),
    "IT가전": ("IT가전", "가전"),
    "통신서비스": ("통신서비스", "통신"),
    "자동차": ("자동차", "완성차", "자동차부품"),
    "조선": ("조선", "조선업"),
    "은행": ("은행",),
    "증권": ("증권",),
    "보험": ("보험",),
    "화학": ("화학", "석유화학", "2차전지"),  # approximate
    "에너지": ("에너지", "정유"),
    "철강": ("철강",),
    "운송": ("운송", "항공", "해운", "물류"),
    "유틸리티": ("유틸리티", "전력", "가스"),
    "건설,건축관련": ("건설", "건축"),
    "디스플레이": ("디스플레이",),
    "미디어,교육": ("미디어", "교육", "엔터", "콘텐츠"),
    "소매(유통)": ("유통", "소매", "리테일"),
    "필수소비재": ("필수소비재", "음식료", "식품"),
    "호텔,레저서비스": ("호텔", "레저", "여행"),
    "기계": ("기계",),
    "상사,자본재": ("상사", "자본재"),
    "비철,목재등": ("비철금속", "목재"),
}

_CACHE_LOCK = threading.Lock()
_SECTOR_CACHE: dict[str, Any] = {"sectors": None, "expires_at": 0.0}


def _sector_cache_ttl_seconds() -> int:
    raw = os.environ.get(AI_SECTOR_CACHE_TTL_SECONDS_ENV)
    return int(raw) if raw else DEFAULT_SECTOR_CACHE_TTL_SECONDS


def get_known_sectors(conn: Any | None = None) -> list[str]:
    """Dynamic sector list sourced from DE's symbol master, TTL-cached.

    Falls back to WICS_SECTOR_FALLBACK on any DB failure (no DSN, timeout, connect error),
    mirroring the fixture-fallback philosophy used elsewhere in this data source layer.
    """
    now = time.monotonic()
    cached = _SECTOR_CACHE["sectors"]
    if cached is not None and now < _SECTOR_CACHE["expires_at"]:
        return cached
    with _CACHE_LOCK:
        cached = _SECTOR_CACHE["sectors"]
        if cached is not None and now < _SECTOR_CACHE["expires_at"]:
            return cached
        sectors = _fetch_sectors(conn)
        if sectors:
            _SECTOR_CACHE["sectors"] = sectors
            _SECTOR_CACHE["expires_at"] = now + _sector_cache_ttl_seconds()
            return sectors
        return list(WICS_SECTOR_FALLBACK)


def _fetch_sectors(conn: Any | None) -> list[str]:
    query = f"""
        SELECT DISTINCT sm.sector
        FROM {CANDIDATE_POOL_VIEW} u
        JOIN {SECTOR_SOURCE_TABLE} sm
          ON sm.symbol = u.symbol
        WHERE u.as_of_date = (SELECT max(as_of_date) FROM {CANDIDATE_POOL_VIEW})
          AND sm.sector IS NOT NULL
        ORDER BY sm.sector
    """
    try:
        if conn is not None:
            rows = conn.execute(query).fetchall()
            return [str(row["sector"]) for row in rows if row.get("sector")]

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
            return [str(row["sector"]) for row in rows if row.get("sector")]
    except Exception:
        return []


def clear_sector_cache() -> None:
    """Test helper — force a cache miss on the next get_known_sectors() call."""
    with _CACHE_LOCK:
        _SECTOR_CACHE["sectors"] = None
        _SECTOR_CACHE["expires_at"] = 0.0


def _alias_lookup(known_sectors: Sequence[str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical in known_sectors:
        lookup[canonical] = canonical
        for alias in SECTOR_ALIAS_MAP.get(canonical, ()):
            lookup[alias] = canonical
    return lookup


def extract_sector_from_query(query: str, known_sectors: Sequence[str] | None = None) -> str | None:
    """Match a canonical sector label (or a known colloquial alias) inside `query`.

    Longest alias is matched first so e.g. "IT하드웨어" doesn't get shadowed by a
    shorter, less specific alias.
    """
    candidates = known_sectors if known_sectors is not None else get_known_sectors()
    lookup = _alias_lookup(candidates)
    for alias in sorted(lookup, key=len, reverse=True):
        if alias and alias in query:
            return lookup[alias]
    return None
