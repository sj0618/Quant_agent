"""Security type classification helpers for Korean listed symbols."""

from __future__ import annotations

import re
from typing import Any, Mapping


COMMON_STOCK = "common_stock"
PREFERRED_STOCK = "preferred_stock"
SPAC = "spac"
REIT = "reit"
ETF = "etf"
ETN = "etn"
OTHER = "other"

CANONICAL_SECURITY_TYPES = {
    COMMON_STOCK,
    PREFERRED_STOCK,
    SPAC,
    REIT,
    ETF,
    ETN,
    OTHER,
}

KOREAN_STOCK_MARKETS = {"KOSPI", "KOSDAQ", "KONEX"}

_SECURITY_TYPE_KEYS = (
    "security_type",
    "SECUGRP_NM",
    "secugrp_nm",
    "SECT_TP_NM",
    "sect_tp_nm",
    "MKT_TP_NM",
    "mkt_tp_nm",
)

_NAME_KEYS = (
    "ISU_ABBRV",
    "isu_abbrv",
    "ISU_NM",
    "isu_nm",
    "name",
)

_CANONICAL_ALIASES = {
    "COMMON_STOCK": COMMON_STOCK,
    "COMMONSTOCK": COMMON_STOCK,
    "COMMON STOCK": COMMON_STOCK,
    "COMMON": COMMON_STOCK,
    "STOCK": COMMON_STOCK,
    "보통주": COMMON_STOCK,
    "주권": COMMON_STOCK,
    "외국주권": COMMON_STOCK,
    "PREFERRED_STOCK": PREFERRED_STOCK,
    "PREFERREDSTOCK": PREFERRED_STOCK,
    "PREFERRED STOCK": PREFERRED_STOCK,
    "PREFERRED": PREFERRED_STOCK,
    "우선주": PREFERRED_STOCK,
    "종류주": PREFERRED_STOCK,
    "종류주권": PREFERRED_STOCK,
    "SPAC": SPAC,
    "스팩": SPAC,
    "기업인수목적": SPAC,
    "REIT": REIT,
    "REITS": REIT,
    "리츠": REIT,
    "부동산투자회사": REIT,
    "ETF": ETF,
    "상장지수펀드": ETF,
    "상장지수집합투자기구": ETF,
    "ETN": ETN,
    "상장지수증권": ETN,
    "OTHER": OTHER,
    "기타": OTHER,
}

_PREFERRED_NAME_RE = re.compile(r"(?:우선주|[0-9]*우(?:B|C)?(?:\(전환\))?)$")
_PREFERRED_SYMBOL_RE = re.compile(r"^\d{5}[57KLM]$")


def classify_security_type(
    raw: Mapping[str, Any] | None = None,
    *,
    symbol: str | None = None,
    name: str | None = None,
    market_segment: str | None = None,
) -> str:
    """Classify a KRX symbol into a canonical security type.

    The classifier prefers explicit KRX metadata, then applies conservative
    Korean ticker/name rules for preferred shares, SPACs, and REITs. Remaining
    KOSPI/KOSDAQ/KONEX symbols are treated as common stocks so the core master
    table can enforce a non-null ``security_type``.
    """

    raw = raw or {}
    explicit_type = _first_text(raw, _SECURITY_TYPE_KEYS)
    explicit_canonical = _canonical_security_type(explicit_type)
    if explicit_canonical in {PREFERRED_STOCK, SPAC, REIT, ETF, ETN, OTHER}:
        return explicit_canonical

    metadata_text = _metadata_text(raw, explicit_type)
    upper_metadata = metadata_text.upper()

    resolved_name = _text(name) or _first_text(raw, _NAME_KEYS)
    compact_name = _compact(resolved_name)
    upper_name = compact_name.upper()

    if "ETN" in upper_metadata or "상장지수증권" in metadata_text or "ETN" in upper_name:
        return ETN
    if (
        "ETF" in upper_metadata
        or "상장지수펀드" in metadata_text
        or "상장지수집합투자기구" in metadata_text
        or "ETF" in upper_name
    ):
        return ETF
    if _contains_any(metadata_text, ("스팩", "기업인수목적")) or "SPAC" in upper_metadata or "스팩" in compact_name or "SPAC" in upper_name:
        return SPAC
    if (
        "REIT" in upper_metadata
        or "부동산투자회사" in metadata_text
        or ("리츠" in compact_name and "메리츠" not in compact_name)
    ):
        return REIT
    if (
        _contains_any(metadata_text, ("우선주", "종류주"))
        or _PREFERRED_NAME_RE.search(compact_name) is not None
        or (not compact_name and _looks_like_preferred_symbol(symbol))
    ):
        return PREFERRED_STOCK
    if explicit_canonical == COMMON_STOCK or _contains_any(metadata_text, ("보통주", "주권")):
        return COMMON_STOCK
    if _normalize_market(market_segment or _first_text(raw, ("MKT_NM", "mkt_nm", "market"))) in KOREAN_STOCK_MARKETS:
        return COMMON_STOCK
    return OTHER


def _metadata_text(raw: Mapping[str, Any], explicit_type: str) -> str:
    values = [explicit_type]
    values.extend(_text(raw.get(key)) for key in (*_SECURITY_TYPE_KEYS, *_NAME_KEYS))
    return " ".join(value for value in values if value)


def _canonical_security_type(value: str) -> str | None:
    normalized = _compact(value).upper()
    if not normalized:
        return None
    if normalized in CANONICAL_SECURITY_TYPES:
        return normalized
    return _CANONICAL_ALIASES.get(normalized)


def _first_text(raw: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(raw.get(key))
        if value:
            return value
    return ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _normalize_market(value: str) -> str:
    return _compact(value).upper()


def _looks_like_preferred_symbol(symbol: str | None) -> bool:
    if not symbol:
        return False
    return _PREFERRED_SYMBOL_RE.fullmatch(symbol.strip().upper()) is not None
