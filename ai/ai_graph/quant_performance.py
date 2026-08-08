from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from ai_graph.nodes.backtest import (
    BENCHMARK_LABEL,
    BENCHMARK_METHOD,
    BENCHMARK_WARNING,
    MIN_OBJECTIVE_TRADES,
    MIN_RELIABLE_TICKERS,
    METRIC_ROUND_DIGITS,
    _equal_weight_benchmark_curve,
    _is_numeric_metric,
    _price_rows,
    _public_engine_summary,
    _summary_float_default,
)
from ai_graph.quant_explanations import metric_explanation
from ai_graph.quant_strategy import build_strategy_explanation
from ai_graph.schemas import (
    BacktestBenchmark,
    BacktestPerformance,
    BacktestReliability,
    CandidateBacktestResult,
    PublicMetricDetail,
)

_METRIC_DETAIL_KEYS = (
    "total_return",
    "cagr",
    "annualized_volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "calmar_ratio",
    "win_rate",
    "profit_factor",
    "benchmark_return",
    "excess_return",
    "in_sample_sharpe",
    "out_sample_sharpe",
    "degradation",
)

_RELIABILITY_SHORT_TERM_DAYS = 30
_RELIABILITY_MIN_DAYS = 252

_UNAVAILABLE_METRIC_REASON = "신뢰도 부족으로 공개 지표를 계산할 수 없습니다."
_BENCHMARK_UNAVAILABLE_REASON = "신뢰도 부족으로 벤치마크를 표시하지 않습니다."


def build_public_backtest_performance(
    backtest: Mapping[str, Any] | None,
    *,
    price_rows: Sequence[Mapping[str, Any]] | None = None,
    pipeline_data_source: Mapping[str, Any] | None = None,
) -> BacktestPerformance | None:
    if not backtest:
        return None

    result = CandidateBacktestResult.model_validate(backtest)
    if result.selected_candidate.metrics is None:
        return None

    normalized_rows = _price_rows(price_rows)
    source = _pipeline_source(pipeline_data_source)
    reliability = _build_backtest_reliability(result, normalized_rows, source=source)
    benchmark = _build_public_benchmark(normalized_rows, reliability=reliability)
    return BacktestPerformance(
        selected_candidate_id=result.selected_candidate.candidate_id,
        metrics=result.selected_candidate.metrics,
        equity_curve=result.equity_curve,
        engine_summary=_public_engine_summary(result.engine_summary),
        reliability=reliability,
        data_quality=_build_data_quality(reliability),
        benchmark=benchmark,
        metric_details=_build_public_metric_details(
            result,
            reliability=reliability,
            benchmark=benchmark,
        ),
        strategy_explanation=build_strategy_explanation(result.strategy_a),
    )


def _pipeline_source(
    pipeline_data_source: Mapping[str, Any] | None,
) -> Literal["fixture", "postgres", "unknown"]:
    if not isinstance(pipeline_data_source, Mapping):
        return "unknown"
    source = pipeline_data_source.get("source")
    if source in {"fixture", "postgres"}:
        return source
    return "unknown"


def _build_backtest_reliability(
    result: CandidateBacktestResult,
    price_rows: Sequence[Mapping[str, Any]],
    *,
    source: Literal["fixture", "postgres", "unknown"],
) -> BacktestReliability:
    row_count = len(price_rows)
    dates = sorted(
        {str(row.get("date")) for row in price_rows if row.get("date") is not None}
    )
    trading_days = len(dates)
    ticker_count = len(
        {
            str(row.get("ticker") or "005930").zfill(6)
            for row in price_rows
            if row.get("ticker") is not None
        }
    )
    trade_count = int(_summary_float_default(result.engine_summary, "effective_trade_count", 0.0))

    reasons: list[str] = []
    warnings: list[str] = []

    if source == "fixture":
        reasons.append("fixture 데이터는 신뢰도 계산에서 제외됩니다.")
    if row_count == 0:
        reasons.append("가격 데이터가 없습니다.")
    if trading_days < _RELIABILITY_SHORT_TERM_DAYS:
        reasons.append(
            f"거래일 수가 {_RELIABILITY_SHORT_TERM_DAYS}일 미만입니다. ({trading_days}일)"
        )
    if ticker_count < MIN_RELIABLE_TICKERS:
        reasons.append(
            f"종목 수가 {MIN_RELIABLE_TICKERS}개 미만입니다. ({ticker_count}개)"
        )

    if source == "unknown":
        warnings.append("데이터 소스가 unknown입니다.")
    if source == "postgres" and trading_days < _RELIABILITY_MIN_DAYS and trading_days >= _RELIABILITY_SHORT_TERM_DAYS:
        warnings.append("PostgreSQL은 거래일 252일 이상일 때만 충분 조건을 충족합니다.")
    if trade_count < MIN_OBJECTIVE_TRADES:
        warnings.append(
            f"유효 거래 수가 기준 미달입니다. ({trade_count} < {MIN_OBJECTIVE_TRADES})"
        )

    if reasons:
        status: Literal["insufficient", "limited", "sufficient"] = "insufficient"
    elif (
        source == "postgres"
        and trading_days >= _RELIABILITY_MIN_DAYS
        and ticker_count >= MIN_RELIABLE_TICKERS
        and trade_count >= MIN_OBJECTIVE_TRADES
    ):
        status = "sufficient"
    else:
        status = "limited"

    return BacktestReliability(
        source=source,
        status=status,
        row_count=row_count,
        ticker_count=ticker_count,
        trading_days=trading_days,
        history_start=dates[0] if dates else None,
        history_end=dates[-1] if dates else None,
        trade_count=trade_count,
        reasons=reasons,
        warnings=warnings,
    )


def _build_data_quality(reliability: BacktestReliability) -> list[str]:
    quality = [
        f"source:{reliability.source}",
        f"rows:{reliability.row_count}",
        f"tickers:{reliability.ticker_count}",
        f"trading_days:{reliability.trading_days}",
        f"trades:{reliability.trade_count}",
        f"status:{reliability.status}",
    ]
    if reliability.status == "sufficient":
        quality.append("공개 성능 신뢰도가 충분합니다.")
    elif reliability.status == "limited":
        quality.append("공개 성능은 제한 모드입니다.")
    else:
        quality.append("공개 성능을 사용할 수 없습니다.")
    return quality


def _build_public_benchmark(
    price_rows: Sequence[Mapping[str, Any]],
    *,
    reliability: BacktestReliability,
) -> BacktestBenchmark:
    if reliability.status == "insufficient":
        return BacktestBenchmark(
            label=BENCHMARK_LABEL,
            method=BENCHMARK_METHOD,
            warning=BENCHMARK_WARNING,
            total_return=None,
            cumulative_curve=[],
            is_available=False,
            unavailable_reason=_BENCHMARK_UNAVAILABLE_REASON,
        )

    cumulative_curve, total_return = _equal_weight_benchmark_curve(price_rows)
    if not cumulative_curve:
        return BacktestBenchmark(
            label=BENCHMARK_LABEL,
            method=BENCHMARK_METHOD,
            warning=BENCHMARK_WARNING,
            total_return=None,
            cumulative_curve=[],
            is_available=False,
            unavailable_reason=_BENCHMARK_UNAVAILABLE_REASON,
        )

    return BacktestBenchmark(
        label=BENCHMARK_LABEL,
        method=BENCHMARK_METHOD,
        warning=BENCHMARK_WARNING,
        total_return=total_return,
        cumulative_curve=cumulative_curve,
        is_available=True,
        unavailable_reason=None,
    )


def _build_public_metric_details(
    result: CandidateBacktestResult,
    *,
    reliability: BacktestReliability,
    benchmark: BacktestBenchmark,
) -> list[PublicMetricDetail]:
    metrics = result.selected_candidate.metrics
    if metrics is None:
        return []

    summary = result.engine_summary
    values: dict[str, float | None] = {
        "total_return": _safe_metric(metrics.total_return),
        "cagr": _metric_summary(summary, ("cagr",)),
        "annualized_volatility": _metric_summary(
            summary, ("annualized_volatility", "volatility")
        ),
        "sharpe_ratio": _safe_metric(metrics.sharpe_ratio),
        "sortino_ratio": _metric_summary(summary, ("sortino_ratio", "sortino")),
        "max_drawdown": _safe_metric(metrics.max_drawdown),
        "calmar_ratio": _metric_summary(summary, ("calmar_ratio", "calmar")),
        "win_rate": _safe_metric(metrics.win_rate),
        "profit_factor": _metric_summary(summary, ("profit_factor",)),
        "in_sample_sharpe": _safe_metric(metrics.in_sample_sharpe),
        "out_sample_sharpe": _safe_metric(metrics.out_sample_sharpe),
        "degradation": _safe_metric(metrics.degradation),
    }

    if reliability.status == "insufficient":
        unavailable_reason = _UNAVAILABLE_METRIC_REASON
        for key in list(values):
            values[key] = None
        values["benchmark_return"] = None
        values["excess_return"] = None
    else:
        unavailable_reason = None
        values["benchmark_return"] = (
            benchmark.total_return if benchmark.is_available else None
        )
        if (
            _is_numeric_metric(values["total_return"])
            and _is_numeric_metric(values["benchmark_return"])
        ):
            values["excess_return"] = float(values["total_return"]) - float(
                values["benchmark_return"]
            )
        else:
            values["excess_return"] = None

    return [
        _metric_detail(
            key=key,
            value=values.get(key),
            unavailable_reason=unavailable_reason,
        )
        for key in _METRIC_DETAIL_KEYS
    ]


def _metric_detail(
    key: str,
    value: float | None,
    *,
    unavailable_reason: str | None = None,
) -> PublicMetricDetail:
    explanation = metric_explanation(key)
    is_available = _is_numeric_metric(value)
    return PublicMetricDetail(
        key=key,
        label=explanation["label"],
        value=round(float(value), METRIC_ROUND_DIGITS) if is_available else None,
        unit=explanation["unit"],
        is_available=is_available,
        unavailable_reason=None if is_available else (unavailable_reason or explanation.get("unavailable_reason")),
        plain_explanation=explanation["plain_explanation"],
        why_used=explanation["why_used"],
        caution=explanation["caution"],
        source_refs=list(explanation.get("source_refs", [])),
    )


def _metric_summary(summary: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = summary.get(key)
        if _is_numeric_metric(value):
            return float(value)
    return None


def _safe_metric(value: float | int | None) -> float | None:
    if _is_numeric_metric(value):
        return float(value)
    return None
