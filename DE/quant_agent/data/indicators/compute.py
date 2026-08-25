"""TA-Lib computation helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from quant_agent.data.indicators.catalog import (
    INDICATOR_CATALOG,
    IndicatorDefinition,
    validate_catalog_counts,
)


class MissingTalibError(RuntimeError):
    """Raised when TA-Lib is not installed in the runtime environment."""


class IndicatorComputationError(RuntimeError):
    """Raised for an indicator-level computation failure."""


def compute_symbol_indicator_rows(
    ohlcv_rows: list[dict[str, Any]],
    definitions: list[IndicatorDefinition] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Compute indicator JSON rows for one symbol.

    Returns ``{category: [{symbol_id, trade_date, values, quality_flags}]}``,
    where each row contains all successful indicators for that category/date.
    """

    validate_catalog_counts()
    if not ohlcv_rows:
        return {}

    try:
        from talib import abstract
    except ImportError as exc:  # pragma: no cover - depends on system TA-Lib
        raise MissingTalibError("TA-Lib is required to compute technical indicators.") from exc

    frame = _to_ohlcv_frame(ohlcv_rows)
    input_arrays = {
        "open": frame["open"].to_numpy(dtype=float),
        "high": frame["high"].to_numpy(dtype=float),
        "low": frame["low"].to_numpy(dtype=float),
        "close": frame["close"].to_numpy(dtype=float),
        "volume": frame["volume"].to_numpy(dtype=float),
        "real": frame["close"].to_numpy(dtype=float),
        "real0": frame["high"].to_numpy(dtype=float),
        "real1": frame["low"].to_numpy(dtype=float),
    }
    requested = INDICATOR_CATALOG if definitions is None else definitions
    values_by_category_date: dict[str, dict[date, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    errors_by_category_date: dict[str, dict[date, list[str]]] = defaultdict(lambda: defaultdict(list))

    for definition in requested:
        try:
            function = abstract.Function(definition.name)
            result = function(input_arrays, **definition.parameters)
            output_names = list(getattr(function, "output_names", []) or [definition.name])
            normalized_outputs = _normalize_talib_result(result, output_names)
        except Exception as exc:  # noqa: BLE001 - keep computing independent indicators
            for trade_date in frame["trade_date"].tolist():
                errors_by_category_date[definition.category][trade_date].append(f"{definition.name}: {exc}")
            continue

        for output_name, array in normalized_outputs.items():
            for idx, scalar in enumerate(array):
                value = _scalar_or_none(scalar)
                if value is None:
                    continue
                key = definition.name if len(normalized_outputs) == 1 else f"{definition.name}.{output_name}"
                values_by_category_date[definition.category][frame.iloc[idx]["trade_date"]][key] = value

    output: dict[str, list[dict[str, Any]]] = {}
    symbol_id = int(frame.iloc[0]["symbol_id"])
    for category, values_by_date in values_by_category_date.items():
        category_rows = []
        for trade_date, values in sorted(values_by_date.items()):
            quality_flags: dict[str, Any] = {}
            if errors_by_category_date[category].get(trade_date):
                quality_flags["indicator_errors"] = errors_by_category_date[category][trade_date]
            category_rows.append(
                {
                    "symbol_id": symbol_id,
                    "trade_date": trade_date,
                    "values": values,
                    "quality_flags": quality_flags,
                }
            )
        output[category] = category_rows
    return output


def _to_ohlcv_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].apply(_to_float)
    return frame.sort_values("trade_date").reset_index(drop=True)


def _to_float(value: Any) -> float:
    if value is None:
        return float("nan")
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _normalize_talib_result(result: Any, output_names: list[str]) -> dict[str, np.ndarray]:
    if isinstance(result, dict):
        return {key: np.asarray(value) for key, value in result.items()}
    if isinstance(result, (list, tuple)):
        names = output_names if len(output_names) == len(result) else [f"output_{idx}" for idx, _ in enumerate(result)]
        return {name: np.asarray(value) for name, value in zip(names, result)}
    name = output_names[0] if output_names else "value"
    return {name: np.asarray(result)}


def _scalar_or_none(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, (float, int)):
        return value if np.isfinite(value) else None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None
