from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


TICKER_PATTERN = re.compile(r"(?<!\d)\d{6}(?!\d)")
_CORPORATE_PREFIX = re.compile(r"^(?:\(\s*주\s*\)|㈜|주식회사)\s*", re.IGNORECASE)
_CORPORATE_PREFIX_PATTERN = r"(?:(?:\(\s*주\s*\)|㈜|주식회사)\s*)?"
_PARTICLES = (
    "으로부터",
    "에게서",
    "에서는",
    "으로",
    "에서",
    "에게",
    "까지",
    "부터",
    "처럼",
    "보다",
    "하고",
    "이며",
    "와",
    "이랑",
    "랑",
    "과",
    "을",
    "를",
    "은",
    "는",
    "이",
    "가",
    "의",
    "도",
    "만",
    "로",
)
_NAME_BOUNDARY = rf"(?=(?:{'|'.join(_PARTICLES)})?(?![0-9A-Za-z가-힣]))"
_GENERIC_TARGET_NOUN_PREFIX = re.compile(
    r"(?:코스피|코스닥|보통주|종목|전체)\s+$",
    re.IGNORECASE,
)
_OBJECT_PARTICLE_PREFIX = re.compile(r"[을를]\s*$")
_NUMERIC_MEASURE_SUFFIX = re.compile(
    r"^\s*(?:억원|만원|천원|달러|퍼센트|거래일|영업일|개월|원|일|년|배|회|개|주|%)"
    r"(?:으로|에서|까지|부터|보다|[은는이가을를에도만의])?"
    r"(?![0-9A-Za-z가-힣])"
)


def _canonical_name(value: object) -> str:
    return _CORPORATE_PREFIX.sub("", str(value or "").strip())


def _is_generic_target(query: str, start: int, end: int, name: str) -> bool:
    if name != "대상" or _CORPORATE_PREFIX.match(query[start:end]):
        return False
    if _GENERIC_TARGET_NOUN_PREFIX.search(query[:start]) is not None:
        return True
    return (
        _OBJECT_PARTICLE_PREFIX.search(query[:start]) is not None
        and query[end:].startswith("으로")
    )


def _is_numeric_measure(query: str, end: int) -> bool:
    suffix = query[end:]
    if suffix[:1].isspace() and suffix.lstrip().startswith("주가"):
        return False
    return _NUMERIC_MEASURE_SUFFIX.search(suffix) is not None


def resolve_query_tickers(
    query: str,
    symbol_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return explicitly mentioned stock codes in query order."""

    matches: list[tuple[int, int, str]] = [
        (match.start(), match.end(), match.group(0))
        for match in TICKER_PATTERN.finditer(query)
        if not _is_numeric_measure(query, match.end())
    ]

    names: list[tuple[str, str]] = []
    for row in symbol_rows:
        symbol = str(row.get("symbol") or "")
        name = _canonical_name(row.get("name"))
        if symbol.isdigit() and name:
            names.append((name, symbol.zfill(6)))

    for name, symbol in sorted(names, key=lambda item: len(item[0]), reverse=True):
        words = [re.escape(word) for word in name.split()]
        if not words:
            continue
        flexible_name = r"\s*".join(words)
        pattern = re.compile(
            rf"(?<![0-9A-Za-z가-힣]){_CORPORATE_PREFIX_PATTERN}"
            rf"{flexible_name}{_NAME_BOUNDARY}",
            re.IGNORECASE,
        )
        for match in pattern.finditer(query):
            if not _is_generic_target(query, match.start(), match.end(), name):
                matches.append((match.start(), match.end(), symbol))

    selected: list[tuple[int, str]] = []
    occupied: list[tuple[int, int]] = []
    seen: set[str] = set()
    for start, end, symbol in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        if symbol in seen or any(
            start < used_end and end > used_start for used_start, used_end in occupied
        ):
            continue
        seen.add(symbol)
        occupied.append((start, end))
        selected.append((start, symbol))
    return tuple(symbol for _, symbol in sorted(selected))
