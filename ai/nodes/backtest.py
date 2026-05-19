"""Fixture/mock 기반 백테스트 실행 노드."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from security.ast_validator import validate_backtest_code


SAFE_BUILTINS = {
    "abs": abs,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "sum": sum,
}


class PriceBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(min_length=1)
    close: float = Field(gt=0)


class TradeSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(min_length=1)
    action: str = Field(pattern="^(BUY|SELL|HOLD)$")
    price: float = Field(gt=0)


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    prices: list[PriceBar] = Field(min_length=2)
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)


class BacktestMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loops: int = Field(ge=1)
    observations: int = Field(ge=1)
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float


class BacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: list[TradeSignal]
    metrics: BacktestMetrics
    trace_id: str = Field(min_length=1)
    debug_ref: str = Field(min_length=1)


def run_backtest(request: BacktestRequest, *, loops: int = 3) -> BacktestResult:
    """검증된 코드의 build_signals를 fixture 가격 데이터에 대해 3회 반복 실행한다."""

    if loops < 1:
        raise ValueError("loops must be positive")

    validation = validate_backtest_code(request.code)
    validation.raise_for_violations()

    namespace: dict[str, Any] = {}
    exec(request.code, {"__builtins__": SAFE_BUILTINS}, namespace)
    build_signals = namespace.get("build_signals")
    if not callable(build_signals):
        raise ValueError("build_signals entrypoint is not callable")

    price_rows = [bar.model_dump() for bar in request.prices]
    parsed_signals: list[TradeSignal] = []
    for _ in range(loops):
        raw_signals = build_signals(price_rows)
        parsed_signals = _parse_signals(raw_signals)

    metrics = _calculate_metrics(price_rows, parsed_signals, loops=loops)
    return BacktestResult(
        signals=parsed_signals,
        metrics=metrics,
        trace_id=request.trace_id,
        debug_ref=request.debug_ref,
    )


def _parse_signals(raw_signals: Iterable[Mapping[str, Any]]) -> list[TradeSignal]:
    return [TradeSignal.model_validate(signal) for signal in raw_signals]


def _calculate_metrics(
    price_rows: list[dict[str, Any]],
    signals: list[TradeSignal],
    *,
    loops: int,
) -> BacktestMetrics:
    start = float(price_rows[0]["close"])
    end = float(price_rows[-1]["close"])
    total_return_pct = ((end - start) / start) * 100

    peak = start
    max_drawdown_pct = 0.0
    for row in price_rows:
        close = float(row["close"])
        peak = max(peak, close)
        drawdown_pct = ((close - peak) / peak) * 100
        max_drawdown_pct = min(max_drawdown_pct, drawdown_pct)

    actionable = [signal for signal in signals if signal.action in {"BUY", "SELL"}]
    wins = sum(1 for signal in actionable if signal.action == "BUY")
    win_rate_pct = (wins / len(actionable) * 100) if actionable else 0.0

    return BacktestMetrics(
        loops=loops,
        observations=len(price_rows),
        total_return_pct=round(total_return_pct, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        win_rate_pct=round(win_rate_pct, 4),
    )
