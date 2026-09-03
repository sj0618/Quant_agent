"""Canonical display identity helpers for KRX symbols."""

from __future__ import annotations

from typing import Any


def canonical_ticker(value: Any) -> str:
    """Return a normalized six-digit ticker when the value is numeric."""

    ticker = str(value or "").strip()
    return ticker.zfill(6) if ticker.isdigit() else ticker


def display_name(value: Any) -> str:
    """Return a presentation-safe name without changing non-empty text."""

    return str(value).strip() if value is not None else ""
