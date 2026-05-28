from __future__ import annotations

import math
import statistics
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.schemas import ABBacktestResult, BacktestMetrics, CodeCandidate
from ai_graph.schemas import StrategySpec as AIStrategySpec
from ai_graph.security.ast_validator import validate_backtest_code


BACKTEST_MODULE_SOURCE_ROOT = Path(__file__).resolve().parents[3] / "backtest_module"
DEFAULT_FIXTURE_TICKER = "005930"
DEFAULT_FIXTURE_MARKET = "KRX"
DEFAULT_FIXTURE_VOLUME = 1_000_000.0
DEFAULT_INITIAL_CAPITAL = 1_000_000.0
DEFAULT_MAX_POSITIONS = 10
TRADING_DAYS_PER_YEAR = 252
METRIC_ROUND_DIGITS = 6
MIN_RETURNS_FOR_SPLIT = 4
BACKTEST_SPLIT_FRACTION = 0.5
GENERATED_SIGNAL_METRIC = "generated_signal"
BUY_SIGNAL_VALUE = 1.0
SELL_SIGNAL_VALUE = -1.0
HOLD_SIGNAL_VALUE = 0.0
PRICE_FIELD_NAMES = frozenset(
    {"date", "ticker", "name", "market", "open", "high", "low", "close", "volume"}
)
ALLOWED_RUNTIME_IMPORTS = frozenset({"datetime", "math", "statistics"})
DEFAULT_BACKTEST_PRICE_ROWS: tuple[dict[str, object], ...] = (
    {
        "date": "2026-01-02",
        "ticker": DEFAULT_FIXTURE_TICKER,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": DEFAULT_FIXTURE_VOLUME,
        "rsi": 25.0,
    },
    {
        "date": "2026-01-03",
        "ticker": DEFAULT_FIXTURE_TICKER,
        "open": 102.0,
        "high": 103.0,
        "low": 101.0,
        "close": 102.0,
        "volume": DEFAULT_FIXTURE_VOLUME,
        "rsi": 50.0,
    },
    {
        "date": "2026-01-04",
        "ticker": DEFAULT_FIXTURE_TICKER,
        "open": 101.0,
        "high": 102.0,
        "low": 100.0,
        "close": 101.0,
        "volume": DEFAULT_FIXTURE_VOLUME,
        "rsi": 75.0,
    },
    {
        "date": "2026-01-05",
        "ticker": DEFAULT_FIXTURE_TICKER,
        "open": 105.0,
        "high": 106.0,
        "low": 104.0,
        "close": 105.0,
        "volume": DEFAULT_FIXTURE_VOLUME,
        "rsi": 50.0,
    },
)
SIGNAL_METRIC_VALUES = {
    "BUY": BUY_SIGNAL_VALUE,
    "SELL": SELL_SIGNAL_VALUE,
    "HOLD": HOLD_SIGNAL_VALUE,
}


def _ensure_backtest_module_source_path() -> None:
    package_root = BACKTEST_MODULE_SOURCE_ROOT / "backtest_module"
    if not package_root.is_dir():
        return
    source_path = str(BACKTEST_MODULE_SOURCE_ROOT)
    if source_path not in sys.path:
        sys.path.insert(0, source_path)


try:
    from backtest_module import (
        Condition as EngineCondition,
        ConditionOperator as EngineConditionOperator,
        PositionSizing as EnginePositionSizing,
        RiskControls as EngineRiskControls,
        StrategySpec as EngineStrategySpec,
    )
    from backtest_module.backtest import (
        BacktestRunConfig as EngineBacktestRunConfig,
        OhlcvBar as EngineOhlcvBar,
        TalibIndicatorConfig as EngineTalibIndicatorConfig,
        run_backtest as run_engine_backtest,
    )
except ImportError:
    _ensure_backtest_module_source_path()
    sys.modules.pop("backtest_module", None)
    from backtest_module import (
        Condition as EngineCondition,
        ConditionOperator as EngineConditionOperator,
        PositionSizing as EnginePositionSizing,
        RiskControls as EngineRiskControls,
        StrategySpec as EngineStrategySpec,
    )
    from backtest_module.backtest import (
        BacktestRunConfig as EngineBacktestRunConfig,
        OhlcvBar as EngineOhlcvBar,
        TalibIndicatorConfig as EngineTalibIndicatorConfig,
        run_backtest as run_engine_backtest,
    )


class GeneratedSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(min_length=1)
    action: str = Field(pattern="^(BUY|SELL|HOLD)$")
    price: float = Field(gt=0.0)


def run_ab_backtest(
    strategy_a: AIStrategySpec,
    strategy_b: AIStrategySpec,
    candidates: list[CodeCandidate],
    *,
    price_rows: Sequence[Mapping[str, Any]] | None = None,
) -> ABBacktestResult:
    if not candidates:
        raise ValueError("at least one candidate is required")

    rows = _price_rows(price_rows)
    enriched_candidates: list[CodeCandidate] = []
    engine_summaries_by_candidate: dict[str, dict[str, Any]] = {}

    for candidate in candidates:
        if not candidate.validation_ok:
            enriched_candidates.append(candidate)
            continue
        strategy = strategy_a if candidate.variant == "A" else strategy_b
        engine_result = _run_candidate_backtest(strategy, candidate, rows)
        metrics = _metrics_from_engine_result(engine_result)
        enriched_candidate = candidate.model_copy(update={"metrics": metrics})
        enriched_candidates.append(enriched_candidate)
        engine_summaries_by_candidate[candidate.candidate_id] = dict(engine_result.summary)

    valid_candidates = [
        candidate
        for candidate in enriched_candidates
        if candidate.validation_ok and candidate.metrics is not None
    ]
    if not valid_candidates:
        raise ValueError("at least one candidate must pass validation and engine backtest")

    selected = max(valid_candidates, key=_candidate_rank)
    metrics_by_variant: dict[str, BacktestMetrics] = {}
    for variant in ("A", "B"):
        variant_candidates = [
            candidate for candidate in valid_candidates if candidate.variant == variant
        ]
        if not variant_candidates:
            raise ValueError(f"variant {variant} has no backtested candidate")
        best = max(variant_candidates, key=_candidate_rank)
        metrics_by_variant[variant] = _candidate_metrics(best)

    return ABBacktestResult(
        strategy_a=strategy_a,
        strategy_b=strategy_b,
        candidates=enriched_candidates,
        selected_candidate=selected,
        metrics_by_variant=metrics_by_variant,
        engine_summaries_by_candidate=engine_summaries_by_candidate,
    )


def backtest_node(state: dict[str, Any]) -> dict[str, Any]:
    strategy_a = AIStrategySpec.model_validate(state["strategy_spec"])
    strategy_b = AIStrategySpec.model_validate(
        state.get("improved_strategy_spec") or state["strategy_spec"]
    )
    candidates = [
        CodeCandidate.model_validate(candidate)
        for candidate in state["backtest_code"]["candidates"]
    ]
    result = run_ab_backtest(
        strategy_a,
        strategy_b,
        candidates,
        price_rows=state["price_rows"] if "price_rows" in state else state.get("market_prices"),
    )
    return {"backtest": result.model_dump()}


def _run_candidate_backtest(
    strategy: AIStrategySpec,
    candidate: CodeCandidate,
    price_rows: Sequence[Mapping[str, Any]],
):
    generated_signals = _execute_candidate_code(candidate, price_rows)
    ohlcv_rows, base_metric_rows = _engine_market_rows(price_rows)
    metric_rows = _merge_generated_signals(base_metric_rows, generated_signals)
    engine_spec = _engine_strategy_spec(strategy, candidate)
    return run_engine_backtest(
        engine_spec,
        ohlcv_rows=ohlcv_rows,
        metric_rows=metric_rows,
        config=EngineBacktestRunConfig(
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            write_outputs=False,
            talib=EngineTalibIndicatorConfig(enabled=False, mode="none"),
        ),
    )


def _execute_candidate_code(
    candidate: CodeCandidate, price_rows: Sequence[Mapping[str, Any]]
) -> list[GeneratedSignal]:
    validation = validate_backtest_code(candidate.code)
    validation.raise_for_violations()

    namespace: dict[str, Any] = {}
    exec(candidate.code, {"__builtins__": _safe_builtins()}, namespace)
    build_signals = namespace.get("build_signals")
    if not callable(build_signals):
        raise ValueError(f"candidate {candidate.candidate_id} build_signals is not callable")

    raw_signals = build_signals([dict(row) for row in price_rows])
    if not isinstance(raw_signals, Sequence):
        raise ValueError(f"candidate {candidate.candidate_id} must return a signal sequence")
    return [GeneratedSignal.model_validate(signal) for signal in raw_signals]


def _engine_market_rows(
    price_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[Any], list[dict[str, object]]]:
    ohlcv_rows: list[Any] = []
    metric_rows: list[dict[str, object]] = []
    tickers: set[str] = set()

    for raw in price_rows:
        if "date" not in raw or "close" not in raw:
            raise ValueError("price rows must include date and close")
        row_date = date.fromisoformat(str(raw["date"]))
        ticker = str(raw.get("ticker") or DEFAULT_FIXTURE_TICKER).zfill(6)
        tickers.add(ticker)
        close = _finite_float(raw["close"], "close")
        open_price = _finite_float(raw.get("open", close), "open")
        high = _finite_float(raw.get("high", max(open_price, close)), "high")
        low = _finite_float(raw.get("low", min(open_price, close)), "low")
        volume = _finite_float(raw.get("volume", DEFAULT_FIXTURE_VOLUME), "volume")
        ohlcv_rows.append(
            EngineOhlcvBar(
                date=row_date,
                ticker=ticker,
                name=str(raw.get("name") or ""),
                market=str(raw.get("market") or DEFAULT_FIXTURE_MARKET),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        metric_row: dict[str, object] = {"date": row_date.isoformat(), "ticker": ticker}
        for key, value in raw.items():
            if str(key) in PRICE_FIELD_NAMES or not _is_numeric_metric(value):
                continue
            metric_row[str(key)] = float(value)
        metric_rows.append(metric_row)

    if len(tickers) != 1:
        raise ValueError("generated-code backtest currently supports one ticker per price row set")
    return ohlcv_rows, metric_rows


def _merge_generated_signals(
    metric_rows: list[dict[str, object]], generated_signals: list[GeneratedSignal]
) -> list[dict[str, object]]:
    metrics_by_date = {str(row["date"]): row for row in metric_rows}
    for signal in generated_signals:
        if signal.date not in metrics_by_date:
            raise ValueError(f"generated signal date {signal.date} is not present in price rows")
        metrics_by_date[signal.date][GENERATED_SIGNAL_METRIC] = SIGNAL_METRIC_VALUES[
            signal.action
        ]
    for row in metric_rows:
        row.setdefault(GENERATED_SIGNAL_METRIC, HOLD_SIGNAL_VALUE)
    return metric_rows


def _engine_strategy_spec(strategy: AIStrategySpec, candidate: CodeCandidate):
    return EngineStrategySpec(
        strategy_id=f"{strategy.strategy_id}_{candidate.candidate_id.lower()}",
        strategy_name=f"{strategy.name} {candidate.candidate_id}",
        description="Generated candidate signals executed by backtest_module.",
        entry_rules=[
            EngineCondition(
                left=GENERATED_SIGNAL_METRIC,
                operator=EngineConditionOperator.EQ,
                right=BUY_SIGNAL_VALUE,
                description="generated BUY signal",
            )
        ],
        exit_rules=[
            EngineCondition(
                left=GENERATED_SIGNAL_METRIC,
                operator=EngineConditionOperator.EQ,
                right=SELL_SIGNAL_VALUE,
                description="generated SELL signal",
            )
        ],
        position_sizing=_engine_position_sizing(strategy),
        risk_controls=_engine_risk_controls(strategy),
    )


def _engine_position_sizing(strategy: AIStrategySpec):
    max_position_pct = _optional_positive_float(
        strategy.risk_constraints.get("max_position_pct"),
        "max_position_pct",
        upper_bound=1.0,
    )
    if max_position_pct is None:
        return EnginePositionSizing(max_positions=DEFAULT_MAX_POSITIONS)
    return EnginePositionSizing(max_positions=max(1, math.ceil(1.0 / max_position_pct)))


def _engine_risk_controls(strategy: AIStrategySpec):
    raw = strategy.risk_constraints
    values: dict[str, float] = {}
    stop_loss_pct = _optional_positive_float(
        raw.get("stop_loss_pct"), "stop_loss_pct", upper_bound=1.0
    )
    take_profit_pct = _optional_positive_float(raw.get("take_profit_pct"), "take_profit_pct")
    max_position_pct = _optional_positive_float(
        raw.get("max_position_pct"), "max_position_pct", upper_bound=1.0
    )
    if stop_loss_pct is not None:
        values["stop_loss_pct"] = stop_loss_pct
    if take_profit_pct is not None:
        values["take_profit_pct"] = take_profit_pct
    if max_position_pct is not None:
        values["max_single_position_pct"] = max_position_pct
    return EngineRiskControls(**values)


def _metrics_from_engine_result(engine_result) -> BacktestMetrics:
    summary = engine_result.summary
    daily_returns = [point.daily_return for point in engine_result.equity_curve[1:]]
    sharpe = _summary_float(summary, "daily_sharpe_like")
    in_sample_sharpe, out_sample_sharpe = _split_sharpes(daily_returns)
    degradation = _degradation(in_sample_sharpe, out_sample_sharpe)
    return BacktestMetrics(
        sharpe_ratio=round(sharpe, METRIC_ROUND_DIGITS),
        max_drawdown=round(_summary_float(summary, "max_drawdown"), METRIC_ROUND_DIGITS),
        win_rate=round(_summary_float(summary, "win_rate"), METRIC_ROUND_DIGITS),
        total_return=round(_summary_float(summary, "period_return"), METRIC_ROUND_DIGITS),
        in_sample_sharpe=round(in_sample_sharpe, METRIC_ROUND_DIGITS),
        out_sample_sharpe=round(out_sample_sharpe, METRIC_ROUND_DIGITS),
        degradation=round(degradation, METRIC_ROUND_DIGITS),
    )


def _split_sharpes(daily_returns: list[float]) -> tuple[float, float]:
    if len(daily_returns) < MIN_RETURNS_FOR_SPLIT:
        full_sample = _sharpe_like(daily_returns)
        return full_sample, full_sample
    split_index = max(1, int(len(daily_returns) * BACKTEST_SPLIT_FRACTION))
    return (
        _sharpe_like(daily_returns[:split_index]),
        _sharpe_like(daily_returns[split_index:]),
    )


def _sharpe_like(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    std = statistics.stdev(daily_returns)
    if std == 0:
        return 0.0
    return statistics.mean(daily_returns) / std * math.sqrt(TRADING_DAYS_PER_YEAR)


def _degradation(in_sample_sharpe: float, out_sample_sharpe: float) -> float:
    if in_sample_sharpe == 0:
        return 0.0
    return max(0.0, (in_sample_sharpe - out_sample_sharpe) / abs(in_sample_sharpe))


def _candidate_rank(candidate: CodeCandidate) -> tuple[float, float, float]:
    metrics = _candidate_metrics(candidate)
    return (metrics.sharpe_ratio, metrics.total_return, metrics.max_drawdown)


def _candidate_metrics(candidate: CodeCandidate) -> BacktestMetrics:
    if candidate.metrics is None:
        raise ValueError(f"candidate {candidate.candidate_id} has no backtest metrics")
    return candidate.metrics


def _price_rows(
    rows: Sequence[Mapping[str, Any]] | None,
) -> Sequence[Mapping[str, Any]]:
    return rows if rows is not None else DEFAULT_BACKTEST_PRICE_ROWS


def _safe_builtins() -> dict[str, Any]:
    return {
        "__import__": _safe_import,
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


def _safe_import(
    name: str,
    globals_: Mapping[str, Any] | None = None,
    locals_: Mapping[str, Any] | None = None,
    fromlist: Sequence[str] = (),
    level: int = 0,
) -> Any:
    if level != 0 or name not in ALLOWED_RUNTIME_IMPORTS:
        raise ImportError(f"import '{name}' is not allowed in generated backtest code")
    return __import__(name, globals_, locals_, fromlist, level)


def _finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _optional_positive_float(
    value: Any, field_name: str, *, upper_bound: float | None = None
) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    parsed = _finite_float(value, field_name)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    if upper_bound is not None and parsed > upper_bound:
        raise ValueError(f"{field_name} must be <= {upper_bound}")
    return parsed


def _summary_float(summary: Mapping[str, Any], key: str) -> float:
    if key not in summary:
        raise ValueError(f"engine summary missing {key}")
    return _finite_float(summary[key], key)


def _is_numeric_metric(value: Any) -> bool:
    if isinstance(value, bool) or value in (None, ""):
        return False
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed)
