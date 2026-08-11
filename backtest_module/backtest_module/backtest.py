from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import numpy as np
from functools import lru_cache
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable, Literal, Mapping, Sequence

from .models import Condition, ConditionOperator, ExecutionTiming, MarketSnapshot, SignalAction, StrategySpec
from .performance import calculate_quantstats_metrics
from .strategy import METRIC_ALIASES, QuantStrategy

DEFAULT_INITIAL_CAPITAL = 100_000_000.0
DEFAULT_OHLCV_PATH = Path("data/krx_ohlcv_1y/kr_ohlcv_1y.csv.gz")
DEFAULT_OUTPUT_ROOT = Path("outputs/backtests")
OHLCV_FIELDS = {"open", "high", "low", "close", "volume"}
REQUIRED_OHLCV_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]
METRIC_ID_COLUMNS = {"date", "ticker", "name", "market"}
TALIB_BASE_INPUTS = {"open", "high", "low", "close", "volume"}


@dataclass(frozen=True)
class OhlcvBar:
    date: date
    ticker: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    name: str = ""
    market: str = ""

    @property
    def metrics(self) -> dict[str, float]:
        return {"open": self.open, "high": self.high, "low": self.low, "close": self.close, "volume": self.volume}


@dataclass(frozen=True)
class ExcludedTicker:
    ticker: str
    reason: str
    first_missing_date: str | None = None
    missing_metrics: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "reason": self.reason,
            "first_missing_date": self.first_missing_date,
            "missing_metrics": self.missing_metrics,
        }


@dataclass
class Position:
    ticker: str
    quantity: int
    entry_date: date
    entry_price: float
    entry_notional: float
    entry_cost: float
    last_price: float
    entry_reason: str = ""


@dataclass(frozen=True)
class PendingOrder:
    ticker: str
    side: str
    signal_date: date
    reason: str


@dataclass(frozen=True)
class TradeRecord:
    ticker: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    entry_cost: float
    exit_cost: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    reason: str

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class EquityPoint:
    date: str
    cash: float
    positions_value: float
    total_equity: float
    daily_return: float

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class SignalRecord:
    date: str
    ticker: str
    action: str
    reasons: str
    matching_entry_rules: str
    matching_exit_rules: str

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class OrderAuditRecord:
    date: str
    ticker: str
    side: str
    status: str
    signal_date: str
    reason: str
    price: float | None = None
    quantity: int | None = None
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()

@dataclass(frozen=True)
class BacktestResult:
    strategy_id: str
    summary: dict[str, object]
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
    signals: list[SignalRecord]
    order_audit: list[OrderAuditRecord] = field(default_factory=list)
    output_paths: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TalibComputation:
    function_name: str
    parameters: dict[str, object] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        return (self.function_name.upper(), tuple(sorted((str(k), str(v)) for k, v in self.parameters.items())))


@dataclass(frozen=True)
class TalibIndicatorConfig:
    """TA-Lib calculation policy.

    mode="required" computes only the TA-Lib functions needed by StrategySpec
    metrics. mode="all" computes every TA-Lib function whose default inputs are
    calculable from OHLCV (currently all except MAVP, which needs `periods`).
    Precomputed metric rows always override calculated values for the same key.
    """

    enabled: bool = True
    mode: Literal["required", "all", "none"] = "required"
    functions: tuple[str, ...] = ()
    parameters: Mapping[str, Mapping[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestRunConfig:
    initial_capital: float = DEFAULT_INITIAL_CAPITAL
    output_dir: Path | None = None
    max_tickers: int | None = None
    write_outputs: bool = True
    talib: TalibIndicatorConfig = field(default_factory=TalibIndicatorConfig)
    metrics_mode: Literal["selection", "full"] = "full"
    # Trading days a held name may go without a bar before the position is written off.
    # A position in a name that stops trading used to be carried at its last observed
    # close for the rest of the run: never sold, never marked down, and still counted in
    # equity. On a survivorship-free universe that is not an edge case - a quarter of the
    # candidates ended runs with most of their final equity in names that had not traded
    # for years. The grace period is long enough that an ordinary suspension which
    # resumes is not caught by it.
    delisting_grace_days: int = 20
    # What a holder recovers when a name is written off, as a fraction of its last close.
    # Zero is the conservative convention for survivorship-corrected backtests and is
    # close to the Korean outcome, where 정리매매 typically clears at a small fraction of
    # the last quoted price. It is an assumption either way, so it is a knob and it is
    # reported in the summary rather than being buried.
    delisting_recovery_rate: float = 0.0


@dataclass(frozen=True)
class PreparedMarketData:
    """Read-only market indexes that can be reused by many strategy candidates."""

    ohlcv_rows: tuple[OhlcvBar, ...]
    bars_by_ticker: Mapping[str, tuple[OhlcvBar, ...]]
    bars_by_date: Mapping[date, Mapping[str, OhlcvBar]]
    metrics_by_key: Mapping[tuple[date, str], Mapping[str, float]]
    previous_metrics_by_key: Mapping[tuple[date, str], Mapping[str, float] | None]
    dates: tuple[date, ...]
    row_index_by_key: Mapping[tuple[date, str], int]
    indicator_report: Mapping[str, object]


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", newline="", encoding="utf-8")
    return path.open("r", newline="", encoding="utf-8")


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _parse_float(value: object, *, field_name: str) -> float:
    if value is None or value == "":
        raise ValueError(f"{field_name} is empty")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _coerce_internal_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def load_strategy_spec(path: str | Path) -> StrategySpec:
    return StrategySpec.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_ohlcv_csv(path: str | Path) -> list[OhlcvBar]:
    path = Path(path)
    with _open_text(path) as f:
        reader = csv.DictReader(f)
        missing = [column for column in REQUIRED_OHLCV_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"OHLCV CSV missing required columns: {missing}")
        rows: list[OhlcvBar] = []
        for raw in reader:
            rows.append(
                OhlcvBar(
                    date=_parse_date(raw["date"]),
                    ticker=str(raw["ticker"]).zfill(6),
                    name=str(raw.get("name") or ""),
                    market=str(raw.get("market") or ""),
                    open=_parse_float(raw["open"], field_name="open"),
                    high=_parse_float(raw["high"], field_name="high"),
                    low=_parse_float(raw["low"], field_name="low"),
                    close=_parse_float(raw["close"], field_name="close"),
                    volume=_parse_float(raw["volume"], field_name="volume"),
                )
            )
    return rows


def load_metric_csv(path: str | Path) -> dict[tuple[date, str], dict[str, float]]:
    path = Path(path)
    with _open_text(path) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for required in ["date", "ticker"]:
            if required not in fieldnames:
                raise ValueError(f"metrics CSV missing required column: {required}")
        metric_columns = [name for name in fieldnames if name not in METRIC_ID_COLUMNS]
        metrics: dict[tuple[date, str], dict[str, float]] = {}
        for raw in reader:
            key = (_parse_date(raw["date"]), str(raw["ticker"]).zfill(6))
            row_metrics: dict[str, float] = {}
            for column in metric_columns:
                value = raw.get(column)
                if value in (None, ""):
                    continue
                row_metrics[column] = _parse_float(value, field_name=column)
            metrics.setdefault(key, {}).update(row_metrics)
    return metrics


def normalize_metric_rows(
    metrics: Mapping[tuple[date | str, str], Mapping[str, object]] | Iterable[Mapping[str, object]] | None,
) -> dict[tuple[date, str], dict[str, float]]:
    if metrics is None:
        return {}
    normalized: dict[tuple[date, str], dict[str, float]] = {}
    if isinstance(metrics, Mapping):
        for (raw_date, raw_ticker), raw_metrics in metrics.items():
            key = (_parse_date(raw_date), str(raw_ticker).zfill(6))
            normalized[key] = {
                str(name): _parse_float(value, field_name=str(name))
                for name, value in raw_metrics.items()
                if value not in (None, "")
            }
        return normalized
    for raw in metrics:
        if "date" not in raw or "ticker" not in raw:
            raise ValueError("metric rows must include date and ticker")
        key = (_parse_date(raw["date"]), str(raw["ticker"]).zfill(6))
        normalized[key] = {
            str(name): _parse_float(value, field_name=str(name))
            for name, value in raw.items()
            if name not in METRIC_ID_COLUMNS and value not in (None, "")
        }
    return normalized


def required_metric_names(spec: StrategySpec) -> set[str]:
    required: set[str] = set()
    for rule in [*spec.entry_rules, *spec.exit_rules]:
        required.update(_condition_metric_names(rule))
    return required


def _condition_metric_names(rule: Condition) -> set[str]:
    names = {rule.left}
    if rule.operator in {
        ConditionOperator.LT,
        ConditionOperator.LTE,
        ConditionOperator.GT,
        ConditionOperator.GTE,
        ConditionOperator.EQ,
        ConditionOperator.NE,
        ConditionOperator.CROSS_ABOVE,
        ConditionOperator.CROSS_BELOW,
    } and isinstance(rule.right, str):
        names.add(rule.right)
    return names


def _metric_present(metric_name: str, metrics: Mapping[str, float]) -> bool:
    return metric_name in metrics or METRIC_ALIASES.get(metric_name, metric_name) in metrics


def _import_talib():
    try:
        import talib  # type: ignore[import-not-found]
        from talib import abstract  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on environment packaging
        raise RuntimeError(
            "TA-Lib is required for indicator calculation. Install the Python package and native library."
        ) from exc
    return talib, abstract


def _talib_required_inputs(function) -> set[str]:
    required: set[str] = set()
    for value in function.input_names.values():
        if isinstance(value, (list, tuple)):
            required.update(str(item) for item in value)
        else:
            required.add(str(value))
    return required


def _is_talib_calculable(function) -> bool:
    return _talib_required_inputs(function).issubset(TALIB_BASE_INPUTS)


@lru_cache(maxsize=1)
def talib_function_catalog() -> dict[str, object]:
    talib, abstract = _import_talib()
    functions = talib.get_functions()
    groups = talib.get_function_groups()
    calculable: list[str] = []
    skipped: dict[str, list[str]] = {}
    for name in functions:
        function = abstract.Function(name)
        missing = sorted(_talib_required_inputs(function) - TALIB_BASE_INPUTS)
        if missing:
            skipped[name] = missing
        else:
            calculable.append(name)
    return {
        "talib_version": getattr(talib, "__version__", "unknown"),
        "function_count": len(functions),
        "calculable_from_ohlcv_count": len(calculable),
        "calculable_from_ohlcv": calculable,
        "skipped": skipped,
        "groups": {name: list(values) for name, values in groups.items()},
    }


@lru_cache(maxsize=None)
def _default_parameters(function_name: str) -> dict[str, object]:
    _, abstract = _import_talib()
    return dict(abstract.Function(function_name).parameters)


def _single_timeperiod_computation(function_name: str, timeperiod: int) -> TalibComputation | None:
    parameters = dict(_default_parameters(function_name))
    if "timeperiod" not in parameters:
        return None
    parameters["timeperiod"] = timeperiod
    return TalibComputation(function_name=function_name.upper(), parameters=parameters)


def _metric_output_names(
    function_name: str,
    output_name: str,
    output_count: int,
    parameters: Mapping[str, object],
) -> set[str]:
    fn = function_name.lower()
    out = output_name.lower()
    names = {f"{fn}_{out}"}
    if output_count == 1:
        names.add(fn)
        if "timeperiod" in parameters:
            timeperiod = int(parameters["timeperiod"])
            names.add(f"{fn}_{timeperiod}")
            if fn == "sma":
                names.update({f"ma_{timeperiod}", f"sma_{timeperiod}"})
            if fn == "ema":
                names.add(f"ema_{timeperiod}")
    else:
        names.add(out)
    if fn == "macd":
        aliases = {"macd": "macd", "macdsignal": "macd_signal", "macdhist": "macd_hist"}
        if out in aliases:
            names.add(aliases[out])
    if fn == "bbands":
        aliases = {"upperband": "bbands_upper", "middleband": "bbands_middle", "lowerband": "bbands_lower"}
        if out in aliases:
            names.add(aliases[out])
        if out == "lowerband" and int(parameters.get("timeperiod", 0)) == 20:
            nbdevdn = float(parameters.get("nbdevdn", parameters.get("nbdev", 0.0)))
            if nbdevdn == 2.0:
                names.add("bollinger_lower_20_2")
    return names


@lru_cache(maxsize=1)
def _talib_metric_name_map() -> dict[str, TalibComputation]:
    _, abstract = _import_talib()
    mapping: dict[str, TalibComputation] = {}
    catalog = talib_function_catalog()
    for function_name in catalog["calculable_from_ohlcv"]:  # type: ignore[index]
        function = abstract.Function(function_name)
        computation = TalibComputation(function_name=function_name, parameters=dict(function.parameters))
        output_names = list(function.output_names)
        for output_name in output_names:
            metric_names = _metric_output_names(
                function_name,
                output_name,
                len(output_names),
                computation.parameters,
            )
            for metric_name in metric_names:
                mapping.setdefault(metric_name, computation)
    return mapping


def _resolve_talib_computation_for_metric(metric_name: str) -> TalibComputation | None:
    name = METRIC_ALIASES.get(metric_name, metric_name).lower()
    if name in OHLCV_FIELDS:
        return None
    if name == "bollinger_lower_20_2":
        return TalibComputation(
            function_name="BBANDS",
            parameters={"timeperiod": 20, "nbdevup": 2.0, "nbdevdn": 2.0, "matype": 0},
        )
    if name in {"volume_ratio_20", "rolling_high_60", "rolling_high_252", "days_since_breakout"}:
        return None
    mapped = _talib_metric_name_map().get(name)
    if mapped:
        return mapped

    # Common LLM-friendly parameterized names: rsi_14, sma_20, ema_12, ma_60, etc.
    parts = name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        base, raw_period = parts
        period = int(raw_period)
        function_name = "SMA" if base == "ma" else base.upper()
        try:
            return _single_timeperiod_computation(function_name, period)
        except Exception:
            return None
    return None


def _parameters_for_function(function_name: str, config: TalibIndicatorConfig) -> dict[str, object]:
    parameters = _default_parameters(function_name.upper())
    parameters.update(dict(config.parameters.get(function_name.upper(), {})))
    parameters.update(dict(config.parameters.get(function_name.lower(), {})))
    return parameters


def _dedupe_computations(computations: Iterable[TalibComputation]) -> list[TalibComputation]:
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    result: list[TalibComputation] = []
    for computation in computations:
        if computation.key in seen:
            continue
        seen.add(computation.key)
        result.append(computation)
    return result


def _talib_computations(required_metrics: set[str], config: TalibIndicatorConfig) -> list[TalibComputation]:
    if not config.enabled or config.mode == "none":
        return []
    _, abstract = _import_talib()
    computations: list[TalibComputation] = []
    if config.mode == "all":
        catalog = talib_function_catalog()
        for function_name in catalog["calculable_from_ohlcv"]:  # type: ignore[index]
            computations.append(
                TalibComputation(
                    function_name=function_name,
                    parameters=_parameters_for_function(function_name, config),
                )
            )
    else:
        for metric in required_metrics:
            computation = _resolve_talib_computation_for_metric(metric)
            if computation is not None:
                overrides = dict(config.parameters.get(computation.function_name.upper(), {}))
                overrides.update(dict(config.parameters.get(computation.function_name.lower(), {})))
                if overrides:
                    merged = dict(computation.parameters)
                    merged.update(overrides)
                    computation = TalibComputation(computation.function_name, merged)
                computations.append(computation)
    for function_name in config.functions:
        computations.append(
            TalibComputation(
                function_name=function_name.upper(),
                parameters=_parameters_for_function(function_name, config),
            )
        )
    return _dedupe_computations(computations)


def compute_talib_metrics_for_bars(
    bars: Sequence[OhlcvBar],
    computations: Sequence[TalibComputation],
) -> tuple[dict[tuple[date, str], dict[str, float]], dict[str, object]]:
    if not computations or not bars:
        return {}, {"computed_functions": [], "failed_functions": {}, "computed_metric_names": []}
    import numpy as np

    _, abstract = _import_talib()
    sorted_bars = sorted(bars, key=lambda row: row.date)
    ticker = sorted_bars[0].ticker
    inputs = {
        "open": np.array([bar.open for bar in sorted_bars], dtype=float),
        "high": np.array([bar.high for bar in sorted_bars], dtype=float),
        "low": np.array([bar.low for bar in sorted_bars], dtype=float),
        "close": np.array([bar.close for bar in sorted_bars], dtype=float),
        "volume": np.array([bar.volume for bar in sorted_bars], dtype=float),
    }
    metric_rows: dict[tuple[date, str], dict[str, float]] = {(bar.date, ticker): {} for bar in sorted_bars}
    computed_functions: list[str] = []
    failed_functions: dict[str, str] = {}
    computed_metric_names: set[str] = set()
    for computation in computations:
        try:
            function = abstract.Function(computation.function_name)
            if not _is_talib_calculable(function):
                continue
            output = function(inputs, **dict(computation.parameters))
            output_names = list(function.output_names)
            arrays = output if isinstance(output, list) else [output]
            computed_functions.append(computation.function_name)
            for output_name, values in zip(output_names, arrays):
                metric_names = _metric_output_names(
                    computation.function_name,
                    output_name,
                    len(output_names),
                    computation.parameters,
                )
                computed_metric_names.update(metric_names)
                for bar, value in zip(sorted_bars, values):
                    parsed = _coerce_internal_float(value)
                    for metric_name in metric_names:
                        metric_rows[(bar.date, ticker)][metric_name] = parsed
        except Exception as exc:  # noqa: BLE001 - per-function failure should not stop unrelated calculations
            failed_functions[computation.function_name] = f"{type(exc).__name__}: {exc}"
    return metric_rows, {
        "computed_functions": sorted(set(computed_functions)),
        "failed_functions": failed_functions,
        "computed_metric_names": sorted(computed_metric_names),
    }


def compute_derived_metrics_for_bars(
    bars: Sequence[OhlcvBar],
    required_metrics: set[str],
    *,
    rows_are_sorted: bool = False,
) -> tuple[dict[tuple[date, str], dict[str, float]], list[str]]:
    requested = {METRIC_ALIASES.get(metric, metric).lower() for metric in required_metrics}
    if not requested.intersection(
        {"volume_ratio_20", "rolling_high_60", "rolling_high_252", "days_since_breakout"}
    ):
        return {}, []
    sorted_bars = list(bars) if rows_are_sorted else sorted(bars, key=lambda row: row.date)
    if not sorted_bars:
        return {}, []
    ticker = sorted_bars[0].ticker
    metric_rows: dict[tuple[date, str], dict[str, float]] = {(bar.date, ticker): {} for bar in sorted_bars}
    computed: set[str] = set()

    if "volume_ratio_20" in requested:
        volumes: list[float] = []
        for bar in sorted_bars:
            volumes.append(bar.volume)
            window = volumes[-20:]
            avg_volume = sum(window) / len(window) if window else math.nan
            metric_rows[(bar.date, ticker)]["volume_ratio_20"] = (
                bar.volume / avg_volume if avg_volume and math.isfinite(avg_volume) else math.nan
            )
        computed.add("volume_ratio_20")

    rolling_highs: dict[int, list[float]] = {}
    for period, metric_name in ((60, "rolling_high_60"), (252, "rolling_high_252")):
        if metric_name not in requested and (period != 252 or "days_since_breakout" not in requested):
            continue
        closes: list[float] = []
        values: list[float] = []
        for bar in sorted_bars:
            closes.append(bar.close)
            values.append(max(closes[-period:]))
        rolling_highs[period] = values
        if metric_name in requested:
            for bar, value in zip(sorted_bars, values):
                metric_rows[(bar.date, ticker)][metric_name] = value
            computed.add(metric_name)

    if "days_since_breakout" in requested:
        highs = rolling_highs.get(252)
        if highs is None:
            highs = []
            closes: list[float] = []
            for bar in sorted_bars:
                closes.append(bar.close)
                highs.append(max(closes[-252:]))
        last_breakout_index: int | None = None
        for index, (bar, high) in enumerate(zip(sorted_bars, highs)):
            if bar.close >= high:
                last_breakout_index = index
            metric_rows[(bar.date, ticker)]["days_since_breakout"] = (
                index - last_breakout_index if last_breakout_index is not None else math.nan
            )
        computed.add("days_since_breakout")

    return metric_rows, sorted(computed)


class BacktestEngine:
    """Conservative daily StrategySpec backtest engine with TA-Lib metric support."""

    def __init__(
        self,
        spec: StrategySpec,
        ohlcv_rows: Sequence[OhlcvBar],
        *,
        metric_rows: (
            Mapping[tuple[date | str, str], Mapping[str, object]]
            | Iterable[Mapping[str, object]]
            | None
        ) = None,
        config: BacktestRunConfig | None = None,
        prepared_market_data: PreparedMarketData | None = None,
        generated_actions: Sequence[int] | None = None,
        inputs_normalized: bool = False,
    ):
        self.spec = spec
        self.strategy = QuantStrategy(spec)
        self.config = config or BacktestRunConfig()
        self.prepared_market_data = prepared_market_data
        self.generated_actions = generated_actions
        self.inputs_normalized = inputs_normalized
        if prepared_market_data is None:
            self.ohlcv_rows = (
                list(ohlcv_rows)
                if inputs_normalized
                else sorted(ohlcv_rows, key=lambda row: (row.date, row.ticker))
            )
            self.metric_rows = (
                dict(metric_rows)
                if inputs_normalized and isinstance(metric_rows, Mapping)
                else normalize_metric_rows(metric_rows)
            )
        else:
            self.ohlcv_rows = list(prepared_market_data.ohlcv_rows)
            self.metric_rows = {}
            if generated_actions is not None and len(generated_actions) != len(self.ohlcv_rows):
                raise ValueError("generated_actions must align one-to-one with prepared OHLCV rows")
        self.indicator_report: dict[str, object] = {}
        if self.config.max_tickers is not None:
            allowed = sorted({row.ticker for row in self.ohlcv_rows})[: self.config.max_tickers]
            self.ohlcv_rows = [row for row in self.ohlcv_rows if row.ticker in set(allowed)]

    def run(self) -> BacktestResult:
        if not self.ohlcv_rows:
            raise ValueError("No OHLCV rows supplied")
        if self.spec.backtest.execution_timing != ExecutionTiming.NEXT_OPEN:
            raise ValueError("BacktestEngine currently supports execution_timing='next_open' only")

        prepared = self._prepare_market_data()
        bars_by_ticker = prepared.bars_by_ticker
        bars_by_date = prepared.bars_by_date
        metrics_by_key = prepared.metrics_by_key
        previous_metrics_by_key = prepared.previous_metrics_by_key
        included_tickers, exclusions = self._select_tickers(bars_by_ticker, metrics_by_key)
        bars_by_date = {
            day: {ticker: bar for ticker, bar in by_ticker.items() if ticker in included_tickers}
            for day, by_ticker in bars_by_date.items()
        }
        dates = [day for day in prepared.dates if bars_by_date.get(day)]

        cash = float(self.config.initial_capital)
        positions: dict[str, Position] = {}
        pending_orders: list[PendingOrder] = []
        equity_curve: list[EquityPoint] = []
        trades: list[TradeRecord] = []
        signals: list[SignalRecord] = []
        order_audit: list[OrderAuditRecord] = []
        previous_equity: float | None = None

        stale_days: dict[str, int] = {}
        forced_exits = 0

        for current_date in dates:
            today_bars = bars_by_date[current_date]
            cash, pending_orders, executed, execution_audit = self._execute_pending_orders(
                current_date, today_bars, positions, cash, pending_orders
            )
            trades.extend(executed)
            order_audit.extend(execution_audit)

            cash, forced_trades, forced_audit, pending_orders = self._write_off_stale_positions(
                current_date, today_bars, positions, cash, pending_orders, stale_days
            )
            trades.extend(forced_trades)
            order_audit.extend(forced_audit)
            forced_exits += len(forced_trades)

            generated_orders, generated_signals, generated_audit = self._generate_signals_for_date(
                current_date, today_bars, positions, metrics_by_key, previous_metrics_by_key, pending_orders
            )
            pending_orders.extend(generated_orders)
            signals.extend(generated_signals)
            order_audit.extend(generated_audit)

            for ticker, position in positions.items():
                if ticker in today_bars:
                    position.last_price = today_bars[ticker].close
            point = self._equity_point(current_date, cash, positions, today_bars, previous_equity)
            equity_curve.append(point)
            previous_equity = point.total_equity

        if dates and pending_orders:
            final_date = dates[-1].isoformat()
            order_audit.extend(
                OrderAuditRecord(
                    date=final_date,
                    ticker=order.ticker,
                    side=order.side,
                    status="unfilled_end",
                    signal_date=order.signal_date.isoformat(),
                    reason=order.reason,
                    detail="No later open was available to execute this order.",
                )
                for order in pending_orders
            )

        final_equity = equity_curve[-1].total_equity if equity_curve else cash
        summary = self._summary(cash, positions, trades, equity_curve, signals, exclusions, final_equity)
        summary["delisting"] = {
            "grace_days": self.config.delisting_grace_days,
            "recovery_rate": self.config.delisting_recovery_rate,
            "forced_exits": forced_exits,
            # Equity still held in names that were not trading on the final date. These
            # are marked at a stale close, so this is the part of the headline that no
            # holder could actually have realised.
            "unrealizable_equity": round(
                sum(
                    position.quantity * position.last_price
                    for ticker, position in positions.items()
                    if stale_days.get(ticker, 0) > 0
                ),
                6,
            ),
        }
        result = BacktestResult(
            strategy_id=self.spec.strategy_id,
            summary=summary,
            equity_curve=equity_curve,
            trades=trades,
            signals=signals,
            order_audit=order_audit,
        )
        if self.config.write_outputs:
            output_dir = self.config.output_dir or DEFAULT_OUTPUT_ROOT / self.spec.strategy_id
            result = self.write_outputs(result, output_dir)
        return result

    def _prepare_market_data(self):
        if self.prepared_market_data is not None:
            self.indicator_report = dict(self.prepared_market_data.indicator_report)
            return self.prepared_market_data

        bars_by_ticker: dict[str, list[OhlcvBar]] = {}
        bars_by_date: dict[date, dict[str, OhlcvBar]] = {}
        metrics_by_key: dict[tuple[date, str], dict[str, float]] = {}
        previous_metrics_by_key: dict[tuple[date, str], dict[str, float] | None] = {}
        for bar in self.ohlcv_rows:
            bars_by_ticker.setdefault(bar.ticker, []).append(bar)
            bars_by_date.setdefault(bar.date, {})[bar.ticker] = bar
            metrics_by_key[(bar.date, bar.ticker)] = bar.metrics

        required = required_metric_names(self.spec)
        computations = _talib_computations(required, self.config.talib)
        report = {
            "mode": self.config.talib.mode,
            "enabled": self.config.talib.enabled,
            "requested_required_metrics": sorted(required),
            "planned_functions": sorted({computation.function_name for computation in computations}),
            "computed_function_count": 0,
            "computed_functions": [],
            "failed_functions": {},
            "computed_metric_names": [],
        }
        computed_functions: set[str] = set()
        failed_functions: dict[str, str] = {}
        computed_metric_names: set[str] = set()
        for ticker, bars in bars_by_ticker.items():
            talib_metrics, ticker_report = compute_talib_metrics_for_bars(bars, computations)
            for key, row_metrics in talib_metrics.items():
                metrics_by_key.setdefault(key, {}).update(row_metrics)
            derived_metrics, derived_metric_names = compute_derived_metrics_for_bars(
                bars, required, rows_are_sorted=self.inputs_normalized
            )
            for key, row_metrics in derived_metrics.items():
                metrics_by_key.setdefault(key, {}).update(row_metrics)
            computed_functions.update(ticker_report["computed_functions"])  # type: ignore[arg-type]
            failed_functions.update(ticker_report["failed_functions"])  # type: ignore[arg-type]
            computed_metric_names.update(ticker_report["computed_metric_names"])  # type: ignore[arg-type]
            computed_metric_names.update(derived_metric_names)

        # User/external metric rows intentionally override calculated metrics.
        for key, row_metrics in self.metric_rows.items():
            metrics_by_key.setdefault(key, {}).update(row_metrics)

        for ticker, bars in bars_by_ticker.items():
            previous: dict[str, float] | None = None
            ordered_bars = bars if self.inputs_normalized else sorted(bars, key=lambda item: item.date)
            for bar in ordered_bars:
                previous_metrics_by_key[(bar.date, ticker)] = previous
                previous = metrics_by_key[(bar.date, ticker)]
        report.update(
            {
                "computed_function_count": len(computed_functions),
                "computed_functions": sorted(computed_functions),
                "failed_functions": failed_functions,
                "computed_metric_names": sorted(computed_metric_names),
            }
        )
        try:
            catalog = talib_function_catalog()
            report["talib_version"] = catalog["talib_version"]
            report["talib_function_count"] = catalog["function_count"]
            report["talib_calculable_from_ohlcv_count"] = catalog["calculable_from_ohlcv_count"]
            report["talib_skipped"] = catalog["skipped"]
        except Exception as exc:  # pragma: no cover
            report["catalog_error"] = f"{type(exc).__name__}: {exc}"
        self.indicator_report = report
        dates = tuple(
            (day for day, by_ticker in bars_by_date.items() if by_ticker)
            if self.inputs_normalized
            else sorted(day for day, by_ticker in bars_by_date.items() if by_ticker)
        )
        sorted_rows = (
            tuple(self.ohlcv_rows)
            if self.inputs_normalized
            else tuple(
                bar
                for day in dates
                for _, bar in sorted(bars_by_date[day].items())
            )
        )
        row_index_by_key = {
            (bar.date, bar.ticker): index for index, bar in enumerate(sorted_rows)
        }
        return PreparedMarketData(
            ohlcv_rows=sorted_rows,
            bars_by_ticker={
                ticker: tuple(bars if self.inputs_normalized else sorted(bars, key=lambda item: item.date))
                for ticker, bars in bars_by_ticker.items()
            },
            bars_by_date={
                day: dict(by_ticker) if self.inputs_normalized else dict(sorted(by_ticker.items()))
                for day, by_ticker in bars_by_date.items()
            },
            metrics_by_key=metrics_by_key,
            previous_metrics_by_key=previous_metrics_by_key,
            dates=dates,
            row_index_by_key=row_index_by_key,
            indicator_report=dict(report),
        )

    def _select_tickers(self, bars_by_ticker, metrics_by_key):
        required = sorted(required_metric_names(self.spec))
        if self.generated_actions is not None:
            required = [name for name in required if name != "generated_signal"]
        included: set[str] = set()
        exclusions: list[ExcludedTicker] = []
        for ticker, bars in bars_by_ticker.items():
            excluded = None
            for bar in bars:
                metrics = metrics_by_key[(bar.date, ticker)]
                missing = [metric for metric in required if not _metric_present(metric, metrics)]
                if missing:
                    excluded = ExcludedTicker(
                        ticker=ticker,
                        reason="missing_required_metric",
                        first_missing_date=bar.date.isoformat(),
                        missing_metrics=missing,
                    )
                    break
            if excluded:
                exclusions.append(excluded)
            else:
                included.add(ticker)
        return included, exclusions

    def _write_off_stale_positions(
        self, current_date, today_bars, positions, cash, pending_orders, stale_days
    ):
        """Realise positions in names that have stopped trading.

        Without this a delisted or indefinitely suspended name is held forever: the
        engine only refreshes `last_price` on days the ticker has a bar, so the position
        keeps its final quoted value, is never sold, and keeps contributing that value to
        every later equity point. The capital is also never returned, so the strategy
        silently runs with fewer usable slots than `max_positions` suggests.

        Names simply absent from the universe on a given day (a holiday for one listing,
        a one-day suspension) are not delisted, which is why this waits
        `delisting_grace_days` trading days before acting.
        """

        grace = self.config.delisting_grace_days
        trades: list[TradeRecord] = []
        audit: list[OrderAuditRecord] = []
        if grace <= 0:
            return cash, trades, audit, pending_orders

        for ticker in list(positions):
            if ticker in today_bars:
                stale_days[ticker] = 0
                continue
            stale_days[ticker] = stale_days.get(ticker, 0) + 1
            if stale_days[ticker] < grace:
                continue

            position = positions.pop(ticker)
            exit_price = position.last_price * self.config.delisting_recovery_rate
            gross = position.quantity * exit_price
            exit_cost = gross * (
                self.spec.backtest.cost_model.commission_pct
                + self.spec.backtest.cost_model.tax_pct
            )
            proceeds = gross - exit_cost
            cash += proceeds
            invested = position.entry_notional + position.entry_cost
            trades.append(
                TradeRecord(
                    ticker=ticker,
                    entry_date=position.entry_date.isoformat(),
                    exit_date=current_date.isoformat(),
                    entry_price=round(position.entry_price, 6),
                    exit_price=round(exit_price, 6),
                    quantity=position.quantity,
                    entry_cost=round(position.entry_cost, 6),
                    exit_cost=round(exit_cost, 6),
                    gross_pnl=round(gross - position.entry_notional, 6),
                    net_pnl=round(proceeds - invested, 6),
                    return_pct=round((proceeds - invested) / invested, 10) if invested else 0.0,
                    reason="delisted_write_off",
                )
            )
            audit.append(
                OrderAuditRecord(
                    date=current_date.isoformat(),
                    ticker=ticker,
                    side="sell",
                    status="delisted_write_off",
                    signal_date=current_date.isoformat(),
                    reason="delisted_write_off",
                    price=round(exit_price, 6),
                    quantity=position.quantity,
                    detail=(
                        f"No bar for {grace} trading days; written off at "
                        f"{self.config.delisting_recovery_rate:.0%} of the last close."
                    ),
                )
            )
            stale_days.pop(ticker, None)

        # A queued order for a name that no longer trades can never fill, and leaving it
        # pending would let it execute if the ticker ever reappeared after the write-off.
        written_off = {record.ticker for record in trades}
        if written_off:
            pending_orders = [
                order for order in pending_orders if order.ticker not in written_off
            ]
        return cash, trades, audit, pending_orders

    def _execute_pending_orders(self, current_date, today_bars, positions, cash, pending_orders):
        executable = [
            order
            for order in pending_orders
            if order.signal_date < current_date and order.ticker in today_bars and today_bars[order.ticker].open > 0
        ]
        remaining = [order for order in pending_orders if order not in executable]
        trades: list[TradeRecord] = []
        audit: list[OrderAuditRecord] = []
        for order in [item for item in executable if item.side == "sell"]:
            position = positions.pop(order.ticker, None)
            if position is None:
                audit.append(
                    OrderAuditRecord(
                        date=current_date.isoformat(),
                        ticker=order.ticker,
                        side=order.side,
                        status="ignored_missing_position",
                        signal_date=order.signal_date.isoformat(),
                        reason=order.reason,
                        detail="Sell order reached the next open without an active position.",
                    )
                )
                continue
            bar = today_bars[order.ticker]
            sell_price = bar.open * (1 - self.spec.backtest.cost_model.slippage_pct)
            gross = position.quantity * sell_price
            exit_cost = gross * (self.spec.backtest.cost_model.commission_pct + self.spec.backtest.cost_model.tax_pct)
            proceeds = gross - exit_cost
            cash += proceeds
            invested = position.entry_notional + position.entry_cost
            gross_pnl = gross - position.entry_notional
            net_pnl = proceeds - invested
            trades.append(
                TradeRecord(
                    ticker=order.ticker,
                    entry_date=position.entry_date.isoformat(),
                    exit_date=current_date.isoformat(),
                    entry_price=round(position.entry_price, 6),
                    exit_price=round(sell_price, 6),
                    quantity=position.quantity,
                    entry_cost=round(position.entry_cost, 6),
                    exit_cost=round(exit_cost, 6),
                    gross_pnl=round(gross_pnl, 6),
                    net_pnl=round(net_pnl, 6),
                    return_pct=round(net_pnl / invested, 10) if invested else 0.0,
                    reason=order.reason,
                )
            )
            audit.append(
                OrderAuditRecord(
                    date=current_date.isoformat(),
                    ticker=order.ticker,
                    side=order.side,
                    status="executed",
                    signal_date=order.signal_date.isoformat(),
                    reason=order.reason,
                    price=round(sell_price, 6),
                    quantity=position.quantity,
                    detail="Filled at the next available open.",
                )
            )
        buy_orders = [item for item in executable if item.side == "buy" and item.ticker not in positions]
        buy_orders.sort(key=lambda order: order.ticker)
        for order in buy_orders:
            if len(positions) >= self.spec.position_sizing.max_positions:
                audit.append(
                    OrderAuditRecord(
                        date=current_date.isoformat(),
                        ticker=order.ticker,
                        side=order.side,
                        status="skipped_max_positions",
                        signal_date=order.signal_date.isoformat(),
                        reason=order.reason,
                        detail="Position cap was already full at the fill open.",
                    )
                )
                continue
            bar = today_bars[order.ticker]
            positions_value = sum(
                position.quantity
                * (today_bars[ticker].open if ticker in today_bars else position.last_price)
                for ticker, position in positions.items()
            )
            current_equity = cash + positions_value
            slots_left = max(1, self.spec.position_sizing.max_positions - len(positions))
            budget = min(
                cash / slots_left,
                current_equity / self.spec.position_sizing.max_positions,
                current_equity * self.spec.risk_controls.max_single_position_pct,
                max(0.0, current_equity * self.spec.risk_controls.max_gross_exposure_pct - positions_value),
            )
            buy_price = bar.open * (1 + self.spec.backtest.cost_model.slippage_pct)
            unit_cash = buy_price * (1 + self.spec.backtest.cost_model.commission_pct)
            if unit_cash <= 0:
                audit.append(
                    OrderAuditRecord(
                        date=current_date.isoformat(),
                        ticker=order.ticker,
                        side=order.side,
                        status="skipped_invalid_unit_cash",
                        signal_date=order.signal_date.isoformat(),
                        reason=order.reason,
                        detail="Unit cash was non-positive at the fill open.",
                    )
                )
                continue
            quantity = int(budget // unit_cash)
            if quantity <= 0:
                audit.append(
                    OrderAuditRecord(
                        date=current_date.isoformat(),
                        ticker=order.ticker,
                        side=order.side,
                        status="skipped_insufficient_cash",
                        signal_date=order.signal_date.isoformat(),
                        reason=order.reason,
                        price=round(buy_price, 6),
                        detail="Budget could not buy one share at the fill open.",
                    )
                )
                continue
            notional = quantity * buy_price
            entry_cost = notional * self.spec.backtest.cost_model.commission_pct
            cash -= notional + entry_cost
            positions[order.ticker] = Position(
                ticker=order.ticker,
                quantity=quantity,
                entry_date=current_date,
                entry_price=buy_price,
                entry_notional=notional,
                entry_cost=entry_cost,
                last_price=bar.close,
                entry_reason=order.reason,
            )
            audit.append(
                OrderAuditRecord(
                    date=current_date.isoformat(),
                    ticker=order.ticker,
                    side=order.side,
                    status="executed",
                    signal_date=order.signal_date.isoformat(),
                    reason=order.reason,
                    price=round(buy_price, 6),
                    quantity=quantity,
                    detail="Filled at the next available open.",
                )
            )
        return cash, remaining, trades, audit

    def _generate_signals_for_date(
        self,
        current_date,
        today_bars,
        positions,
        metrics_by_key,
        previous_metrics_by_key,
        pending_orders,
    ):
        if self.generated_actions is not None and self.prepared_market_data is not None:
            return self._generate_compact_signals_for_date(
                current_date,
                today_bars,
                positions,
                pending_orders,
            )

        pending_tickers = {(order.side, order.ticker) for order in pending_orders}
        orders: list[PendingOrder] = []
        signals: list[SignalRecord] = []
        audit: list[OrderAuditRecord] = []
        for ticker in sorted(today_bars):
            metrics = metrics_by_key[(current_date, ticker)]
            prev_metrics = previous_metrics_by_key.get((current_date, ticker))
            has_position = ticker in positions
            decision = self.strategy.generate_signal(
                MarketSnapshot(
                    ticker=ticker,
                    timestamp=datetime.combine(current_date, time(15, 30)),
                    metrics=metrics,
                    previous_metrics=prev_metrics,
                ),
                has_position=has_position,
            )
            signals.append(self._signal_record(current_date, decision))
            if decision.action == SignalAction.BUY and not has_position and ("buy", ticker) not in pending_tickers:
                orders.append(
                    PendingOrder(
                        ticker=ticker,
                        side="buy",
                        signal_date=current_date,
                        reason=";".join(decision.reasons),
                    )
                )
                audit.append(
                    OrderAuditRecord(
                        date=current_date.isoformat(),
                        ticker=ticker,
                        side="buy",
                        status="submitted",
                        signal_date=current_date.isoformat(),
                        reason=";".join(decision.reasons),
                        detail="Queued for the next available open.",
                    )
                )
            elif decision.action == SignalAction.SELL and has_position and ("sell", ticker) not in pending_tickers:
                orders.append(
                    PendingOrder(
                        ticker=ticker,
                        side="sell",
                        signal_date=current_date,
                        reason=";".join(decision.reasons),
                    )
                )
                audit.append(
                    OrderAuditRecord(
                        date=current_date.isoformat(),
                        ticker=ticker,
                        side="sell",
                        status="submitted",
                        signal_date=current_date.isoformat(),
                        reason=";".join(decision.reasons),
                        detail="Queued for the next available open.",
                    )
                )
            elif has_position and ("sell", ticker) not in pending_tickers:
                risk_reason = self._risk_exit_reason(positions[ticker], today_bars[ticker])
                if risk_reason:
                    orders.append(
                        PendingOrder(
                            ticker=ticker,
                            side="sell",
                            signal_date=current_date,
                            reason=risk_reason,
                        )
                    )
                    signals.append(
                        SignalRecord(
                            date=current_date.isoformat(),
                            ticker=ticker,
                            action="sell",
                            reasons=risk_reason,
                            matching_entry_rules="",
                            matching_exit_rules=risk_reason,
                        )
                    )
                    audit.append(
                        OrderAuditRecord(
                            date=current_date.isoformat(),
                            ticker=ticker,
                            side="sell",
                            status="submitted",
                            signal_date=current_date.isoformat(),
                            reason=risk_reason,
                            detail="Risk control queued the exit for the next available open.",
                        )
                    )
        return orders, signals, audit

    def _generate_compact_signals_for_date(
        self,
        current_date,
        today_bars,
        positions,
        pending_orders,
    ):
        """Consume aligned int8-style actions without MarketSnapshot/SignalDecision churn."""

        pending_tickers = {(order.side, order.ticker) for order in pending_orders}
        orders: list[PendingOrder] = []
        signals: list[SignalRecord] = []
        audit: list[OrderAuditRecord] = []
        row_index_by_key = self.prepared_market_data.row_index_by_key
        for ticker in sorted(today_bars):
            action_value = int(self.generated_actions[row_index_by_key[(current_date, ticker)]])
            has_position = ticker in positions
            if action_value == 1 and not has_position:
                action = "buy"
                reason = "generated BUY signal"
                if ("buy", ticker) not in pending_tickers:
                    orders.append(
                        PendingOrder(
                            ticker=ticker,
                            side="buy",
                            signal_date=current_date,
                            reason=reason,
                        )
                    )
                    audit.append(
                        OrderAuditRecord(
                            date=current_date.isoformat(),
                            ticker=ticker,
                            side="buy",
                            status="submitted",
                            signal_date=current_date.isoformat(),
                            reason=reason,
                            detail="Queued for the next available open.",
                        )
                    )
                    pending_tickers.add(("buy", ticker))
            elif action_value == -1 and has_position:
                action = "sell"
                reason = "generated SELL signal"
                if ("sell", ticker) not in pending_tickers:
                    orders.append(
                        PendingOrder(
                            ticker=ticker,
                            side="sell",
                            signal_date=current_date,
                            reason=reason,
                        )
                    )
                    audit.append(
                        OrderAuditRecord(
                            date=current_date.isoformat(),
                            ticker=ticker,
                            side="sell",
                            status="submitted",
                            signal_date=current_date.isoformat(),
                            reason=reason,
                            detail="Queued for the next available open.",
                        )
                    )
                    pending_tickers.add(("sell", ticker))
            else:
                action = "hold" if has_position else "watch"

            signals.append(
                SignalRecord(
                    date=current_date.isoformat(),
                    ticker=ticker,
                    action=action,
                    reasons=(
                        "generated BUY signal"
                        if action == "buy"
                        else "generated SELL signal"
                        if action == "sell"
                        else "no actionable rule matched"
                    ),
                    matching_entry_rules="generated BUY signal" if action == "buy" else "",
                    matching_exit_rules="generated SELL signal" if action == "sell" else "",
                )
            )
            if has_position and ("sell", ticker) not in pending_tickers:
                risk_reason = self._risk_exit_reason(positions[ticker], today_bars[ticker])
                if risk_reason:
                    orders.append(
                        PendingOrder(
                            ticker=ticker,
                            side="sell",
                            signal_date=current_date,
                            reason=risk_reason,
                        )
                    )
                    signals.append(
                        SignalRecord(
                            date=current_date.isoformat(),
                            ticker=ticker,
                            action="sell",
                            reasons=risk_reason,
                            matching_entry_rules="",
                            matching_exit_rules=risk_reason,
                        )
                    )
                    audit.append(
                        OrderAuditRecord(
                            date=current_date.isoformat(),
                            ticker=ticker,
                            side="sell",
                            status="submitted",
                            signal_date=current_date.isoformat(),
                            reason=risk_reason,
                            detail="Risk control queued the exit for the next available open.",
                        )
                    )
        return orders, signals, audit

    def _risk_exit_reason(self, position: Position, bar: OhlcvBar) -> str | None:
        stop_loss = self.spec.risk_controls.stop_loss_pct
        if stop_loss and bar.close <= position.entry_price * (1 - stop_loss):
            return f"daily_close_stop_loss_{stop_loss}"
        take_profit = self.spec.risk_controls.take_profit_pct
        if take_profit and bar.close >= position.entry_price * (1 + take_profit):
            return f"daily_close_take_profit_{take_profit}"
        return None

    @staticmethod
    def _signal_record(current_date, decision):
        return SignalRecord(
            date=current_date.isoformat(),
            ticker=decision.ticker,
            action=decision.action.value,
            reasons=";".join(decision.reasons),
            matching_entry_rules=";".join(decision.matching_entry_rules),
            matching_exit_rules=";".join(decision.matching_exit_rules),
        )

    def _equity_point(self, current_date, cash, positions, today_bars, previous_equity):
        positions_value = self._positions_value(positions, today_bars)
        total = cash + positions_value
        daily_return = 0.0 if previous_equity in (None, 0) else (total / previous_equity) - 1
        return EquityPoint(
            date=current_date.isoformat(),
            cash=round(cash, 6),
            positions_value=round(positions_value, 6),
            total_equity=round(total, 6),
            daily_return=round(daily_return, 10),
        )

    @staticmethod
    def _positions_value(positions, today_bars) -> float:
        total = 0.0
        for ticker, position in positions.items():
            price = today_bars[ticker].close if ticker in today_bars else position.last_price
            total += position.quantity * price
        return total

    def _summary(self, cash, positions, trades, equity_curve, signals, exclusions, final_equity):
        if self.config.metrics_mode == "selection":
            metrics = _calculate_selection_metrics(equity_curve)
        else:
            metrics = calculate_quantstats_metrics(equity_curve, include_montecarlo=True)
        winners = [trade for trade in trades if trade.net_pnl > 0]
        trade_win_rate = round(len(winners) / len(trades), 10) if trades else 0.0
        holding_days = [
            (date.fromisoformat(trade.exit_date) - date.fromisoformat(trade.entry_date)).days
            for trade in trades
        ]
        avg_holding_days = round(sum(holding_days) / len(holding_days), 6) if holding_days else 0.0
        excluded_tickers = [item.as_dict() for item in exclusions]
        cost_model = self.spec.backtest.cost_model.model_dump(mode="json")
        position_sizing = self.spec.position_sizing.model_dump(mode="json")
        return {
            "strategy_id": self.spec.strategy_id,
            "strategy_name": self.spec.strategy_name,
            "metrics_mode": self.config.metrics_mode,
            "initial_capital": self.config.initial_capital,
            "final_equity": round(final_equity, 6),
            "cash": round(cash, 6),
            "final_cash": round(cash, 6),
            "open_positions": len(positions),
            # Which names are still held, not just how many. A per-ticker BUY/SELL/HOLD
            # verdict cannot be derived from the signal stream alone: the engine skips
            # buys it has no cash or slot for, so "the rule said buy" and "the book is
            # long" are different facts, and only this one says what is actually held.
            "open_position_tickers": sorted(positions),
            "metrics": metrics,
            "period_return": metrics.get("total_return"),
            "total_return": metrics.get("total_return"),
            "cagr": metrics.get("cagr"),
            "max_drawdown": metrics.get("max_drawdown"),
            "daily_sharpe_like": metrics.get("sharpe"),
            "sharpe": metrics.get("sharpe"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "sortino": metrics.get("sortino"),
            "sortino_ratio": metrics.get("sortino_ratio"),
            "adjusted_sortino": metrics.get("adjusted_sortino"),
            "adjusted_sortino_ratio": metrics.get("adjusted_sortino_ratio"),
            "calmar": metrics.get("calmar"),
            "calmar_ratio": metrics.get("calmar_ratio"),
            "volatility": metrics.get("volatility"),
            "annualized_volatility": metrics.get("annualized_volatility"),
            "common_sense_ratio": metrics.get("common_sense_ratio"),
            "gain_to_pain_ratio": metrics.get("gain_to_pain_ratio"),
            "geometric_mean": metrics.get("geometric_mean"),
            "kelly_criterion": metrics.get("kelly_criterion"),
            "exposure": metrics.get("exposure"),
            "cpc_index": metrics.get("cpc_index"),
            "omega": metrics.get("omega"),
            "value_at_risk": metrics.get("value_at_risk"),
            "conditional_value_at_risk": metrics.get("conditional_value_at_risk"),
            "cvar": metrics.get("cvar"),
            "ulcer_index": metrics.get("ulcer_index"),
            "ulcer_performance_index": metrics.get("ulcer_performance_index"),
            "risk_of_ruin": metrics.get("risk_of_ruin"),
            "tail_ratio": metrics.get("tail_ratio"),
            "kurtosis": metrics.get("kurtosis"),
            "skew": metrics.get("skew"),
            "trade_count": len(trades),
            "trade_win_rate": trade_win_rate,
            "win_rate": trade_win_rate,
            "return_win_rate": metrics.get("win_rate"),
            "signal_count": len(signals),
            "avg_holding_days": avg_holding_days,
            "avg_return": metrics.get("avg_return"),
            "avg_period_return": metrics.get("avg_period_return"),
            "avg_win": metrics.get("avg_win"),
            "avg_positive_period_return": metrics.get("avg_positive_period_return"),
            "avg_loss": metrics.get("avg_loss"),
            "avg_negative_period_return": metrics.get("avg_negative_period_return"),
            "best": metrics.get("best"),
            "best_period_return": metrics.get("best_period_return"),
            "worst": metrics.get("worst"),
            "worst_period_return": metrics.get("worst_period_return"),
            "profit_factor": metrics.get("profit_factor"),
            "payoff_ratio": metrics.get("payoff_ratio"),
            "outlier_loss_ratio": metrics.get("outlier_loss_ratio"),
            "outlier_win_ratio": metrics.get("outlier_win_ratio"),
            "recovery_factor": metrics.get("recovery_factor"),
            "expected_return": metrics.get("expected_return"),
            "consecutive_negative_periods": metrics.get("consecutive_negative_periods"),
            "consecutive_positive_periods": metrics.get("consecutive_positive_periods"),
            "monthly_returns": metrics.get("monthly_returns"),
            "drawdown_details": metrics.get("drawdown_details"),
            "drawdown_series": metrics.get("drawdown_series"),
            "rolling_volatility": metrics.get("rolling_volatility"),
            "rolling_sharpe": metrics.get("rolling_sharpe"),
            "rolling_sortino": metrics.get("rolling_sortino"),
            "information_ratio": metrics.get("information_ratio"),
            "r_squared": metrics.get("r_squared"),
            "greeks": metrics.get("greeks"),
            "rolling_greeks": metrics.get("rolling_greeks"),
            "compare": metrics.get("compare"),
            "montecarlo": metrics.get("montecarlo"),
            "montecarlo_mean": metrics.get("montecarlo_mean"),
            "montecarlo_cagr": metrics.get("montecarlo_cagr"),
            "montecarlo_drawdown": metrics.get("montecarlo_drawdown"),
            "montecarlo_sharpe": metrics.get("montecarlo_sharpe"),
            "outliers": metrics.get("outliers"),
            "metric_warnings": metrics.get("metric_warnings", []),
            "excluded_ticker_count": len(exclusions),
            "excluded_tickers": excluded_tickers,
            "excluded_ticker_jsonb": excluded_tickers,
            "execution_timing": self.spec.backtest.execution_timing.value,
            "cost_model": cost_model,
            "cost_model_jsonb": cost_model,
            "position_sizing": position_sizing,
            "position_sizing_jsonb": position_sizing,
            "indicator_report": self.indicator_report,
            "indicator_report_jsonb": self.indicator_report,
            "notes": [
                "Signals are evaluated from end-of-day metrics; fills occur at the next available open.",
                "TA-Lib metrics are calculated from OHLCV when enabled; "
                "precomputed metric rows override calculated values.",
                "Tickers missing required StrategySpec metrics are excluded and recorded here.",
            ],
        }

    @staticmethod
    def write_outputs(result: BacktestResult, output_dir: str | Path) -> BacktestResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = output_dir / "summary.json"
        equity_path = output_dir / "equity_curve.csv"
        trades_path = output_dir / "trades.csv"
        signals_path = output_dir / "signals.csv"
        order_audit_path = output_dir / "order_audit.csv"
        summary_path.write_text(json.dumps(result.summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _write_csv(
            equity_path,
            [point.as_dict() for point in result.equity_curve],
            EquityPoint.__dataclass_fields__.keys(),
        )
        _write_csv(trades_path, [trade.as_dict() for trade in result.trades], TradeRecord.__dataclass_fields__.keys())
        _write_csv(
            signals_path,
            [signal.as_dict() for signal in result.signals],
            SignalRecord.__dataclass_fields__.keys(),
        )
        _write_csv(
            order_audit_path,
            [event.as_dict() for event in result.order_audit],
            OrderAuditRecord.__dataclass_fields__.keys(),
        )
        return BacktestResult(
            strategy_id=result.strategy_id,
            summary=result.summary,
            equity_curve=result.equity_curve,
            trades=result.trades,
            signals=result.signals,
            order_audit=result.order_audit,
            output_paths={
                "summary_json": str(summary_path),
                "equity_curve_csv": str(equity_path),
                "trades_csv": str(trades_path),
                "signals_csv": str(signals_path),
                "order_audit_csv": str(order_audit_path),
            },
        )


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames) -> None:
    fieldnames = list(fieldnames)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _calculate_selection_metrics(equity_curve: Sequence[EquityPoint]) -> dict[str, object]:
    """Cheap deterministic metrics used to rank candidates before full post-processing."""

    if not equity_curve:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "metric_warnings": [],
        }

    initial = float(equity_curve[0].total_equity)
    final = float(equity_curve[-1].total_equity)
    total_return = final / initial - 1.0 if initial else 0.0
    returns = np.fromiter((float(point.daily_return) for point in equity_curve), dtype=np.float64)
    usable = returns[1:] if returns.size > 1 else np.array([], dtype=np.float64)
    mean_return = float(np.mean(usable)) if usable.size else 0.0
    variance = float(np.var(usable, ddof=1)) if usable.size > 1 else 0.0
    volatility = math.sqrt(variance)
    sharpe = mean_return / volatility * math.sqrt(252.0) if volatility > 0.0 else 0.0

    equity = np.fromiter((float(point.total_equity) for point in equity_curve), dtype=np.float64)
    peaks = np.maximum.accumulate(equity)
    drawdown_series = np.divide(equity, peaks, out=np.ones_like(equity), where=peaks != 0) - 1.0
    max_drawdown = float(np.min(drawdown_series))

    positive = float(np.sum(usable[usable > 0.0])) if usable.size else 0.0
    negative = -float(np.sum(usable[usable < 0.0])) if usable.size else 0.0
    profit_factor = positive / negative if negative > 0.0 else (1.0 if positive > 0.0 else 0.0)
    elapsed_days = max(
        1,
        (date.fromisoformat(equity_curve[-1].date) - date.fromisoformat(equity_curve[0].date)).days,
    )
    cagr = (final / initial) ** (365.0 / elapsed_days) - 1.0 if initial > 0.0 and final > 0.0 else 0.0
    win_rate = float(np.mean(usable > 0.0)) if usable.size else 0.0
    return {
        "total_return": round(total_return, 10),
        "cagr": round(cagr, 10),
        "sharpe": round(sharpe, 10),
        "sharpe_ratio": round(sharpe, 10),
        "max_drawdown": round(max_drawdown, 10),
        "win_rate": round(win_rate, 10),
        "profit_factor": round(profit_factor, 10),
        "volatility": round(volatility * math.sqrt(252.0), 10),
        "metric_warnings": [],
    }


def run_backtest(
    spec: StrategySpec,
    *,
    ohlcv_rows: Sequence[OhlcvBar] | None = None,
    ohlcv_path: str | Path | None = None,
    metric_rows: Mapping[tuple[date | str, str], Mapping[str, object]] | Iterable[Mapping[str, object]] | None = None,
    metrics_path: str | Path | None = None,
    config: BacktestRunConfig | None = None,
    prepared_market_data: PreparedMarketData | None = None,
    generated_actions: Sequence[int] | None = None,
) -> BacktestResult:
    if ohlcv_rows is None and prepared_market_data is None:
        ohlcv_rows = load_ohlcv_csv(ohlcv_path or DEFAULT_OHLCV_PATH)
    merged_metrics = normalize_metric_rows(metric_rows)
    if metrics_path is not None:
        merged_metrics.update(load_metric_csv(metrics_path))
    return BacktestEngine(
        spec,
        ohlcv_rows or (),
        metric_rows=merged_metrics,
        config=config,
        prepared_market_data=prepared_market_data,
        generated_actions=generated_actions,
    ).run()


def prepare_market_data(
    spec: StrategySpec,
    *,
    ohlcv_rows: Sequence[OhlcvBar],
    metric_rows: Mapping[tuple[date | str, str], Mapping[str, object]] | Iterable[Mapping[str, object]] | None = None,
    config: BacktestRunConfig | None = None,
    inputs_normalized: bool = False,
) -> PreparedMarketData:
    """Normalize, sort, index, and calculate common metrics once for many candidates."""

    engine = BacktestEngine(
        spec,
        ohlcv_rows,
        metric_rows=metric_rows,
        config=config,
        inputs_normalized=inputs_normalized,
    )
    return engine._prepare_market_data()


def build_sample_spec() -> StrategySpec:
    from .models import Condition, CostModel, PositionSizing, RiskControls

    return StrategySpec(
        strategy_id="sample_close_above_open",
        strategy_name="Sample Close Above Open",
        description="Demo strategy using only built-in OHLCV metrics.",
        entry_rules=[Condition(left="close", operator=ConditionOperator.GT, right="open", description="close > open")],
        exit_rules=[Condition(left="close", operator=ConditionOperator.LT, right="open", description="close < open")],
        position_sizing=PositionSizing(max_positions=5),
        risk_controls=RiskControls(stop_loss_pct=0.08, take_profit_pct=None),
        backtest={"cost_model": CostModel(commission_pct=0.0, tax_pct=0.0, slippage_pct=0.0).model_dump()},
    )


def build_sample_talib_spec() -> StrategySpec:
    from .models import Condition, CostModel, PositionSizing, RiskControls

    return StrategySpec(
        strategy_id="sample_rsi_talib",
        strategy_name="Sample RSI TA-Lib",
        description="Demo strategy that requires TA-Lib RSI calculation from OHLCV.",
        entry_rules=[Condition(left="rsi_14", operator=ConditionOperator.LTE, right=30, description="RSI(14) <= 30")],
        exit_rules=[Condition(left="rsi_14", operator=ConditionOperator.GTE, right=70, description="RSI(14) >= 70")],
        position_sizing=PositionSizing(max_positions=10),
        risk_controls=RiskControls(stop_loss_pct=0.08, take_profit_pct=None),
        backtest={"cost_model": CostModel(commission_pct=0.00015, tax_pct=0.0023, slippage_pct=0.001).model_dump()},
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a conservative daily StrategySpec backtest.")
    parser.add_argument(
        "--spec",
        type=Path,
        help="StrategySpec JSON path. Omit with --sample-spec or --sample-talib-spec.",
    )
    parser.add_argument("--sample-spec", action="store_true", help="Run the built-in OHLCV-only sample strategy.")
    parser.add_argument(
        "--sample-talib-spec",
        action="store_true",
        help="Run the built-in RSI strategy that computes TA-Lib RSI from OHLCV.",
    )
    parser.add_argument("--ohlcv", type=Path, default=DEFAULT_OHLCV_PATH)
    parser.add_argument(
        "--metrics",
        type=Path,
        help="Precomputed metrics CSV with date,ticker,<metric...> columns; overrides TA-Lib values.",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--initial-capital", type=float, default=DEFAULT_INITIAL_CAPITAL)
    parser.add_argument("--max-tickers", type=int, help="Debug/demo limit applied by sorted ticker code.")
    parser.add_argument("--talib-mode", choices=["required", "all", "none"], default="required")
    parser.add_argument(
        "--talib-function",
        action="append",
        default=[],
        help="Additional TA-Lib function to calculate. Repeatable.",
    )
    parser.add_argument("--list-talib", action="store_true", help="Print TA-Lib catalog and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.list_talib:
        print(json.dumps(talib_function_catalog(), ensure_ascii=False, indent=2))
        return 0
    if args.sample_spec:
        spec = build_sample_spec()
    elif args.sample_talib_spec:
        spec = build_sample_talib_spec()
    elif args.spec:
        spec = load_strategy_spec(args.spec)
    else:
        raise SystemExit("Provide --spec <path>, --sample-spec, --sample-talib-spec, or --list-talib")
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / spec.strategy_id
    result = run_backtest(
        spec,
        ohlcv_path=args.ohlcv,
        metrics_path=args.metrics,
        config=BacktestRunConfig(
            initial_capital=args.initial_capital,
            output_dir=output_dir,
            max_tickers=args.max_tickers,
            talib=TalibIndicatorConfig(mode=args.talib_mode, functions=tuple(args.talib_function)),
        ),
    )
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
