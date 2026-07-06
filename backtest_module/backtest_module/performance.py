from __future__ import annotations

import math
import warnings
from collections.abc import Mapping, Sequence
from datetime import date, datetime

ROUND_DIGITS = 10
DEFAULT_ROLLING_PERIOD = 126
MONTECARLO_SIMULATION_COUNT = 250
MONTECARLO_RANDOM_SEED = 42
QUANTSTATS_REQUIRED_MESSAGE = (
    "quantstats is required for performance metrics. Install with: python -m pip install quantstats"
)
CORE_METRIC_DEFAULTS = {
    "total_return": 0.0,
    "cagr": 0.0,
    "sharpe": 0.0,
    "sortino": 0.0,
    "adjusted_sortino": 0.0,
    "max_drawdown": 0.0,
    "calmar": 0.0,
    "volatility": 0.0,
    "win_rate": 0.0,
    "avg_return": 0.0,
    "avg_win": 0.0,
    "avg_loss": 0.0,
    "profit_factor": 0.0,
    "payoff_ratio": 0.0,
    "recovery_factor": 0.0,
    "expected_return": 0.0,
    "cvar": 0.0,
    "conditional_value_at_risk": 0.0,
    "value_at_risk": 0.0,
    "best": 0.0,
    "worst": 0.0,
    "omega": 0.0,
    "common_sense_ratio": 0.0,
    "gain_to_pain_ratio": 0.0,
    "geometric_mean": 0.0,
    "kelly_criterion": 0.0,
    "exposure": 0.0,
    "cpc_index": 0.0,
    "tail_ratio": 0.0,
    "risk_of_ruin": 0.0,
    "ulcer_index": 0.0,
    "ulcer_performance_index": 0.0,
    "outlier_loss_ratio": 0.0,
    "outlier_win_ratio": 0.0,
    "kurtosis": 0.0,
    "skew": 0.0,
    "consecutive_negative_periods": 0,
    "consecutive_positive_periods": 0,
}
LIST_METRIC_DEFAULTS = {
    "monthly_returns": [],
    "drawdown_details": [],
    "drawdown_series": [],
    "rolling_volatility": [],
    "rolling_sharpe": [],
    "rolling_sortino": [],
    "rolling_greeks": [],
    "montecarlo_mean": [],
}
OBJECT_METRIC_DEFAULTS = {
    "compare": {},
    "montecarlo": {},
    "montecarlo_drawdown": {},
    "montecarlo_sharpe": {},
    "outliers": {},
}


def calculate_quantstats_metrics(
    equity_curve: Sequence[object] | object,
    *,
    benchmark_returns: object | None = None,
    include_montecarlo: bool = False,
) -> dict[str, object]:
    _, qs_stats, np, pd = _load_quantstats()
    equity = _equity_series(equity_curve, pd=pd, np=np)
    returns = _returns_from_equity_series(equity, np=np)
    metric_warnings: list[dict[str, str]] = []
    rolling_period = _rolling_period(len(returns))

    conditional_value_at_risk = _safe_metric(
        "conditional_value_at_risk",
        lambda: qs_stats.conditional_value_at_risk(returns),
        metric_warnings,
    )
    drawdown_series = _raw_metric(
        "to_drawdown_series",
        lambda: qs_stats.to_drawdown_series(returns),
        metric_warnings,
    )

    metrics: dict[str, object] = {
        "total_return": _safe_metric("total_return", lambda: qs_stats.comp(returns), metric_warnings),
        "cagr": _safe_metric("cagr", lambda: qs_stats.cagr(returns), metric_warnings),
        "sharpe": _safe_metric("sharpe", lambda: qs_stats.sharpe(returns), metric_warnings),
        "sortino": _safe_metric("sortino", lambda: qs_stats.sortino(returns), metric_warnings),
        "adjusted_sortino": _safe_metric(
            "adjusted_sortino",
            lambda: qs_stats.adjusted_sortino(returns),
            metric_warnings,
        ),
        "max_drawdown": _safe_metric("max_drawdown", lambda: qs_stats.max_drawdown(returns), metric_warnings),
        "calmar": _safe_metric("calmar", lambda: qs_stats.calmar(returns), metric_warnings),
        "volatility": _safe_metric("volatility", lambda: qs_stats.volatility(returns), metric_warnings),
        "win_rate": _safe_metric("win_rate", lambda: qs_stats.win_rate(returns), metric_warnings),
        "avg_return": _safe_metric("avg_return", lambda: qs_stats.avg_return(returns), metric_warnings),
        "avg_win": _safe_metric("avg_win", lambda: qs_stats.avg_win(returns), metric_warnings),
        "avg_loss": _safe_metric("avg_loss", lambda: qs_stats.avg_loss(returns), metric_warnings),
        "profit_factor": _safe_metric(
            "profit_factor", lambda: qs_stats.profit_factor(returns), metric_warnings
        ),
        "payoff_ratio": _safe_metric("payoff_ratio", lambda: qs_stats.payoff_ratio(returns), metric_warnings),
        "recovery_factor": _safe_metric(
            "recovery_factor", lambda: qs_stats.recovery_factor(returns), metric_warnings
        ),
        "expected_return": _safe_metric(
            "expected_return", lambda: qs_stats.expected_return(returns), metric_warnings
        ),
        "cvar": conditional_value_at_risk,
        "conditional_value_at_risk": conditional_value_at_risk,
        "value_at_risk": _safe_metric(
            "value_at_risk", lambda: qs_stats.value_at_risk(returns), metric_warnings
        ),
        "best": _safe_metric("best", lambda: qs_stats.best(returns), metric_warnings),
        "worst": _safe_metric("worst", lambda: qs_stats.worst(returns), metric_warnings),
        "omega": _safe_metric("omega", lambda: qs_stats.omega(returns), metric_warnings),
        "common_sense_ratio": _safe_metric(
            "common_sense_ratio", lambda: qs_stats.common_sense_ratio(returns), metric_warnings
        ),
        "gain_to_pain_ratio": _safe_metric(
            "gain_to_pain_ratio", lambda: qs_stats.gain_to_pain_ratio(returns), metric_warnings
        ),
        "geometric_mean": _safe_metric(
            "geometric_mean", lambda: qs_stats.geometric_mean(returns), metric_warnings
        ),
        "kelly_criterion": _safe_metric(
            "kelly_criterion", lambda: qs_stats.kelly_criterion(returns), metric_warnings
        ),
        "exposure": _safe_metric("exposure", lambda: qs_stats.exposure(returns), metric_warnings),
        "cpc_index": _safe_metric("cpc_index", lambda: qs_stats.cpc_index(returns), metric_warnings),
        "tail_ratio": _safe_metric("tail_ratio", lambda: qs_stats.tail_ratio(returns), metric_warnings),
        "risk_of_ruin": _safe_metric(
            "risk_of_ruin", lambda: qs_stats.risk_of_ruin(returns), metric_warnings
        ),
        "ulcer_index": _safe_metric(
            "ulcer_index", lambda: qs_stats.ulcer_index(returns), metric_warnings
        ),
        "ulcer_performance_index": _safe_metric(
            "ulcer_performance_index",
            lambda: qs_stats.ulcer_performance_index(returns),
            metric_warnings,
        ),
        "outlier_loss_ratio": _safe_metric(
            "outlier_loss_ratio", lambda: qs_stats.outlier_loss_ratio(returns), metric_warnings
        ),
        "outlier_win_ratio": _safe_metric(
            "outlier_win_ratio", lambda: qs_stats.outlier_win_ratio(returns), metric_warnings
        ),
        "kurtosis": _safe_metric("kurtosis", lambda: qs_stats.kurtosis(returns), metric_warnings),
        "skew": _safe_metric("skew", lambda: qs_stats.skew(returns), metric_warnings),
        "consecutive_negative_periods": _safe_metric(
            "consecutive_negative_periods",
            lambda: qs_stats.consecutive_losses(returns),
            metric_warnings,
        ),
        "consecutive_positive_periods": _safe_metric(
            "consecutive_positive_periods",
            lambda: qs_stats.consecutive_wins(returns),
            metric_warnings,
        ),
        "monthly_returns": _safe_metric(
            "monthly_returns",
            lambda: _dataframe_to_records(qs_stats.monthly_returns(returns), pd=pd, np=np),
            metric_warnings,
        ),
        "drawdown_series": _json_safe(drawdown_series) if drawdown_series is not None else None,
        "rolling_volatility": _safe_metric(
            "rolling_volatility",
            lambda: qs_stats.rolling_volatility(returns, rolling_period=rolling_period),
            metric_warnings,
        ),
        "rolling_sharpe": _safe_metric(
            "rolling_sharpe",
            lambda: qs_stats.rolling_sharpe(returns, rolling_period=rolling_period),
            metric_warnings,
        ),
        "rolling_sortino": _safe_metric(
            "rolling_sortino",
            lambda: qs_stats.rolling_sortino(returns, rolling_period=rolling_period),
            metric_warnings,
        ),
        "outliers": _outlier_detail(returns, pd=pd),
    }

    drawdown_input = drawdown_series if drawdown_series is not None else returns
    metrics["drawdown_details"] = _safe_metric(
        "drawdown_details",
        lambda: _dataframe_to_records(qs_stats.drawdown_details(drawdown_input), pd=pd, np=np),
        metric_warnings,
    )

    if benchmark_returns is None:
        metrics["information_ratio"] = None
        metrics["r_squared"] = None
        metrics["greeks"] = None
        metrics["rolling_greeks"] = None
        metrics["compare"] = None
    else:
        aligned_returns, aligned_benchmark = _align_benchmark_returns(
            returns, benchmark_returns, pd=pd, np=np
        )
        if aligned_returns.empty or aligned_benchmark.empty:
            metrics["information_ratio"] = None
            metrics["r_squared"] = None
            metrics["greeks"] = None
            metrics["rolling_greeks"] = None
            metrics["compare"] = None
        else:
            greeks = _safe_metric(
                "greeks", lambda: qs_stats.greeks(aligned_returns, aligned_benchmark), metric_warnings
            )
            metrics["information_ratio"] = _safe_metric(
                "information_ratio",
                lambda: qs_stats.information_ratio(aligned_returns, aligned_benchmark),
                metric_warnings,
            )
            metrics["r_squared"] = _safe_metric(
                "r_squared",
                lambda: qs_stats.r_squared(aligned_returns, aligned_benchmark),
                metric_warnings,
            )
            metrics["greeks"] = greeks
            metrics["rolling_greeks"] = _safe_metric(
                "rolling_greeks",
                lambda: qs_stats.rolling_greeks(
                    aligned_returns,
                    aligned_benchmark,
                    periods=_rolling_period(len(aligned_returns)),
                ),
                metric_warnings,
            )
            metrics["compare"] = _compare_detail(
                aligned_returns,
                aligned_benchmark,
                greeks=greeks,
                qs_stats=qs_stats,
                np=np,
                pd=pd,
                metric_warnings=metric_warnings,
            )

    if include_montecarlo:
        metrics.update(_montecarlo_detail(returns, np=np))

    _apply_metric_defaults(metrics, metric_warnings)
    _apply_metric_aliases(metrics)
    metrics["metric_warnings"] = metric_warnings
    return metrics


def quantstats_sharpe_from_returns(
    daily_returns: Sequence[float],
    *,
    metric_name: str = "sharpe",
    metric_warnings: list[dict[str, str]] | None = None,
) -> float:
    if len(daily_returns) < 2:
        return 0.0
    _, qs_stats, np, pd = _load_quantstats()
    returns = pd.Series(daily_returns, index=pd.date_range("2000-01-01", periods=len(daily_returns), freq="D"))
    warnings_out = metric_warnings if metric_warnings is not None else []
    sharpe = _safe_metric(metric_name, lambda: qs_stats.sharpe(returns), warnings_out)
    if sharpe is None and metric_warnings is not None:
        metric_warnings.append({"metric": metric_name, "warning": f"{metric_name} defaulted to 0.0"})
    return 0.0 if sharpe is None else float(sharpe)


def returns_from_equity_curve(equity_curve: Sequence[object] | object) -> list[float]:
    _, _, np, pd = _load_quantstats()
    equity = _equity_series(equity_curve, pd=pd, np=np)
    returns = _returns_from_equity_series(equity, np=np)
    return [float(value) for value in returns.tolist()]


def _load_quantstats():
    try:
        import numpy as np
        import pandas as pd
        import quantstats as qs
        import quantstats.stats as qs_stats
    except ImportError as exc:
        raise ModuleNotFoundError(QUANTSTATS_REQUIRED_MESSAGE) from exc
    return qs, qs_stats, np, pd


def _equity_series(equity_curve: Sequence[object] | object, *, pd, np):
    if isinstance(equity_curve, pd.Series):
        series = equity_curve.copy()
        series.index = pd.to_datetime(series.index)
        series = pd.to_numeric(series, errors="coerce")
        return series.replace([np.inf, -np.inf], np.nan).dropna().sort_index()

    rows: list[tuple[object, float]] = []
    for point in equity_curve or []:
        raw_date = _get_field(point, "date")
        raw_value = _get_field(point, "total_equity")
        if raw_value is None:
            raw_value = _get_field(point, "portfolio_value")
        if raw_date is None or raw_value in (None, ""):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        rows.append((raw_date, value))

    if not rows:
        return pd.Series(dtype="float64")

    equity = pd.Series(
        [value for _, value in rows],
        index=pd.to_datetime([raw_date for raw_date, _ in rows]),
        dtype="float64",
    )
    equity = equity[~equity.index.isna()]
    equity = equity[~equity.index.duplicated(keep="last")]
    return equity.sort_index()


def _align_benchmark_returns(returns, benchmark_returns: object, *, pd, np):
    benchmark_equity = _equity_series(benchmark_returns, pd=pd, np=np)
    benchmark = _returns_from_equity_series(benchmark_equity, np=np)
    benchmark = benchmark.reindex(returns.index).replace([np.inf, -np.inf], np.nan).dropna()
    aligned_returns = returns.reindex(benchmark.index).replace([np.inf, -np.inf], np.nan).dropna()
    aligned_benchmark = benchmark.reindex(aligned_returns.index).dropna()
    return aligned_returns, aligned_benchmark


def _returns_from_equity_series(equity, *, np):
    return equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()


def _get_field(point: object, name: str) -> object | None:
    if isinstance(point, Mapping):
        return point.get(name)
    return getattr(point, name, None)


def _rolling_period(length: int) -> int:
    return max(2, min(DEFAULT_ROLLING_PERIOD, length))


def _apply_metric_defaults(metrics: dict[str, object], metric_warnings: list[dict[str, str]]) -> None:
    for key, default in CORE_METRIC_DEFAULTS.items():
        if metrics.get(key) is None:
            metrics[key] = default
            metric_warnings.append(
                {"metric": key, "warning": f"{key} was unavailable and defaulted to {default}"}
            )
    for key, default in LIST_METRIC_DEFAULTS.items():
        if metrics.get(key) is None:
            metrics[key] = list(default)
            metric_warnings.append(
                {"metric": key, "warning": f"{key} was unavailable and defaulted to an empty list"}
            )
    for key, default in OBJECT_METRIC_DEFAULTS.items():
        if metrics.get(key) is None:
            metrics[key] = dict(default)
            metric_warnings.append(
                {"metric": key, "warning": f"{key} was unavailable and defaulted to an empty object"}
            )


def _apply_metric_aliases(metrics: dict[str, object]) -> None:
    metrics["sharpe_ratio"] = metrics.get("sharpe")
    metrics["sortino_ratio"] = metrics.get("sortino")
    metrics["adjusted_sortino_ratio"] = metrics.get("adjusted_sortino")
    metrics["calmar_ratio"] = metrics.get("calmar")
    metrics["annualized_volatility"] = metrics.get("volatility")
    metrics["avg_period_return"] = metrics.get("avg_return")
    metrics["avg_positive_period_return"] = metrics.get("avg_win")
    metrics["avg_negative_period_return"] = metrics.get("avg_loss")
    metrics["best_period_return"] = metrics.get("best")
    metrics["worst_period_return"] = metrics.get("worst")


def _safe_metric(metric_name: str, callback, metric_warnings: list[dict[str, str]]):
    value = _raw_metric(metric_name, callback, metric_warnings)
    if value is None:
        return None
    json_safe = _json_safe(value)
    if json_safe is None:
        metric_warnings.append({"metric": metric_name, "warning": f"{metric_name} returned a non-finite value"})
    return json_safe


def _raw_metric(metric_name: str, callback, metric_warnings: list[dict[str, str]]):
    if callback is None:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return callback()
    except Exception as exc:
        metric_warnings.append({"metric": metric_name, "warning": f"{type(exc).__name__}: {exc}"})
        return None


def _compare_detail(aligned_returns, aligned_benchmark, *, greeks, qs_stats, np, pd, metric_warnings):
    active_returns = aligned_returns - aligned_benchmark
    strategy_total_return = _safe_metric(
        "compare_strategy_total_return",
        lambda: qs_stats.comp(aligned_returns),
        metric_warnings,
    )
    benchmark_total_return = _safe_metric(
        "compare_benchmark_total_return",
        lambda: qs_stats.comp(aligned_benchmark),
        metric_warnings,
    )
    strategy_cagr = _safe_metric(
        "compare_strategy_cagr",
        lambda: qs_stats.cagr(aligned_returns),
        metric_warnings,
    )
    benchmark_cagr = _safe_metric(
        "compare_benchmark_cagr",
        lambda: qs_stats.cagr(aligned_benchmark),
        metric_warnings,
    )
    tracking_error = None
    if not active_returns.empty:
        std = active_returns.std(ddof=0)
        if std is not None and math.isfinite(float(std)):
            tracking_error = round(float(std) * math.sqrt(252), ROUND_DIGITS)
    strategy_equity = (1.0 + aligned_returns).cumprod() - 1.0
    benchmark_equity = (1.0 + aligned_benchmark).cumprod() - 1.0
    comparison_frame = pd.DataFrame(
        {
            "strategy": strategy_equity,
            "benchmark": benchmark_equity,
            "active": strategy_equity - benchmark_equity,
        }
    )
    return {
        "observations": int(len(aligned_returns)),
        "strategy_total_return": strategy_total_return,
        "benchmark_total_return": benchmark_total_return,
        "active_return": round(float(strategy_total_return - benchmark_total_return), ROUND_DIGITS)
        if strategy_total_return is not None and benchmark_total_return is not None
        else None,
        "strategy_cagr": strategy_cagr,
        "benchmark_cagr": benchmark_cagr,
        "tracking_error": tracking_error,
        "correlation": _safe_metric(
            "compare_correlation",
            lambda: aligned_returns.corr(aligned_benchmark),
            metric_warnings,
        ),
        "active_win_rate": _safe_metric(
            "compare_active_win_rate",
            lambda: float((active_returns > 0).mean()),
            metric_warnings,
        ),
        "greeks": greeks,
        "cumulative": _dataframe_to_records(comparison_frame, pd=pd, np=np),
    }


def _outlier_detail(returns, *, pd) -> dict[str, object] | None:
    if returns.empty:
        return None
    loss_threshold = returns.quantile(0.01)
    win_threshold = returns.quantile(0.99)
    losses = returns[returns <= loss_threshold].sort_values()
    wins = returns[returns >= win_threshold].sort_values(ascending=False)
    return {
        "loss_threshold": _json_safe(float(loss_threshold)) if pd.notna(loss_threshold) else None,
        "win_threshold": _json_safe(float(win_threshold)) if pd.notna(win_threshold) else None,
        "losses": _json_safe(losses),
        "wins": _json_safe(wins),
    }


def _montecarlo_detail(returns, *, np) -> dict[str, object]:
    if returns.empty:
        return {
            "montecarlo": {},
            "montecarlo_mean": [],
            "montecarlo_drawdown": {},
            "montecarlo_sharpe": {},
        }

    values = returns.to_numpy(dtype="float64")
    horizon = len(values)
    rng = np.random.default_rng(MONTECARLO_RANDOM_SEED)
    sampled = rng.choice(values, size=(MONTECARLO_SIMULATION_COUNT, horizon), replace=True)
    cumulative_paths = np.cumprod(1.0 + sampled, axis=1) - 1.0
    final_returns = cumulative_paths[:, -1]

    running_max = np.maximum.accumulate(cumulative_paths + 1.0, axis=1)
    drawdowns = ((cumulative_paths + 1.0) / running_max) - 1.0
    max_drawdowns = drawdowns.min(axis=1)

    sharpe_denominator = sampled.std(axis=1, ddof=0)
    sharpe_numerator = sampled.mean(axis=1)
    sharpes = np.divide(
        sharpe_numerator,
        sharpe_denominator,
        out=np.zeros_like(sharpe_numerator),
        where=sharpe_denominator > 0,
    ) * math.sqrt(252)

    path_mean = cumulative_paths.mean(axis=0)
    path_p05 = np.quantile(cumulative_paths, 0.05, axis=0)
    path_p95 = np.quantile(cumulative_paths, 0.95, axis=0)

    montecarlo_mean = [
        {
            "step": step + 1,
            "mean_cumulative_return": _json_safe(float(path_mean[step])),
            "p05_cumulative_return": _json_safe(float(path_p05[step])),
            "p95_cumulative_return": _json_safe(float(path_p95[step])),
        }
        for step in range(horizon)
    ]

    return {
        "montecarlo": {
            "seed": MONTECARLO_RANDOM_SEED,
            "simulations": MONTECARLO_SIMULATION_COUNT,
            "horizon_days": horizon,
            "positive_return_probability": _json_safe(float((final_returns > 0).mean())),
            "loss_probability": _json_safe(float((final_returns < 0).mean())),
            "total_return_quantiles": _distribution_summary(final_returns, np=np),
            "max_drawdown_quantiles": _distribution_summary(max_drawdowns, np=np),
            "sharpe_quantiles": _distribution_summary(sharpes, np=np),
        },
        "montecarlo_mean": montecarlo_mean,
        "montecarlo_drawdown": _distribution_summary(max_drawdowns, np=np),
        "montecarlo_sharpe": _distribution_summary(sharpes, np=np),
    }


def _distribution_summary(values, *, np) -> dict[str, float | None]:
    if values is None:
        return {}
    array = np.asarray(values, dtype="float64")
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return {}
    return {
        "mean": _json_safe(float(np.mean(finite))),
        "median": _json_safe(float(np.median(finite))),
        "p05": _json_safe(float(np.quantile(finite, 0.05))),
        "p25": _json_safe(float(np.quantile(finite, 0.25))),
        "p75": _json_safe(float(np.quantile(finite, 0.75))),
        "p95": _json_safe(float(np.quantile(finite, 0.95))),
        "best": _json_safe(float(np.max(finite))),
        "worst": _json_safe(float(np.min(finite))),
    }


def _dataframe_to_records(frame, *, pd, np) -> list[dict[str, object]]:
    if frame is None:
        return []
    normalized = frame.copy().reset_index()
    normalized = normalized.replace([np.inf, -np.inf], np.nan)
    normalized = normalized.astype(object).where(pd.notna(normalized), None)
    return [_json_safe(record) for record in normalized.to_dict(orient="records")]


def _json_safe(value):
    try:
        import numpy as np
        import pandas as pd
    except ImportError:
        np = None
        pd = None

    if pd is not None and isinstance(value, pd.DataFrame):
        return _dataframe_to_records(value, pd=pd, np=np)
    if pd is not None and isinstance(value, pd.Series):
        return [_json_safe({"date": index, "value": item}) for index, item in value.items()]
    if pd is not None and isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if isinstance(value, float):
        return round(value, ROUND_DIGITS) if math.isfinite(value) else None
    return value
