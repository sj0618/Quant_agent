from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from ai_graph.memory import AnalysisMemory
from ai_graph.nodes.backtest import (
    BENCHMARK_LABEL,
    BENCHMARK_METHOD,
    BENCHMARK_WARNING,
    MAX_OBJECTIVE_DRAWDOWN,
    MIN_OBJECTIVE_SHARPE,
    MIN_OBJECTIVE_TRADES,
    MIN_RELIABLE_TICKERS,
    METRIC_ROUND_DIGITS,
    _calmar_ratio,
    _equal_weight_benchmark_curve,
    _is_numeric_metric,
    _passes_objective_floor,
    _price_rows,
    _public_engine_summary,
    _summary_float_default,
)
from ai_graph.quant_explanations import metric_explanation
from ai_graph.schemas import (
    BacktestBenchmark,
    BacktestMetrics,
    BacktestPerformance,
    BacktestReliability,
    CandidateBacktestResult,
    EnvelopeStatus,
    PublicMetricDetail,
    RecommendationGate,
)
from ai_graph.state import QuantAgentState


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

_RELIABILITY_MIN_DAYS = 252
_RELIABILITY_MIN_DAYS_HINT = 30
_UNAVAILABLE_METRIC_REASON = "신뢰도가 부족해 공개 성능 수치를 비활성화합니다."
_BENCHMARK_UNAVAILABLE_REASON = "신뢰도 미충족으로 벤치마크를 계산하지 않습니다."


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
            price_rows=normalized_rows,
            reliability=reliability,
            benchmark=benchmark,
        ),
    )


def _recommendation_gate(state: QuantAgentState) -> RecommendationGate | None:
    if state.get("backtest") is None:
        return None

    try:
        backtest = CandidateBacktestResult.model_validate(state["backtest"])
    except Exception as exc:
        return RecommendationGate(
            validated=False,
            reason=f"백테스트 결과를 읽는 중 오류가 발생했습니다: {type(exc).__name__}",
        )

    if backtest.selected_candidate.metrics is None:
        return RecommendationGate(
            validated=False,
            reason="선택 후보의 지표가 없어 전략 조건을 계산할 수 없습니다.",
        )

    reasons = _objective_gate_reasons(backtest)
    validated = _passes_objective_floor(backtest)
    reason = "전략 검증 조건 통과" if validated else (
        "전략 검증 조건 미충족: " + ", ".join(reasons)
        if reasons
        else "전략 검증 조건 미충족"
    )
    return RecommendationGate(validated=validated, reason=reason)


def _record_analysis_memory(state: QuantAgentState, status: EnvelopeStatus) -> None:
    memory = AnalysisMemory.from_env()
    if not memory.enabled:
        return

    strategy = state.get("strategy_spec") or {}
    strategy_id = str(strategy.get("strategy_id") or "")
    if not strategy_id:
        return

    data = state.get("data") or {}
    pipeline = data.get("pipeline_data_source") or {}
    availability = data.get("data_availability") or {}

    performance = build_public_backtest_performance(
        state.get("backtest"),
        price_rows=state.get("price_rows"),
        pipeline_data_source=state.get("data", {}).get("pipeline_data_source"),
    )
    if performance is None:
        metrics: dict[str, Any] = {}
    else:
        metrics = performance.metrics.model_dump()

    try:
        memory.record(
            strategy_id,
            query=str(state.get("user_query") or ""),
            outcome=status.value,
            candidate_count=len(data.get("screening_candidates") or []),
            metrics=metrics,
            relaxation_rounds=int(
                (pipeline.get("screening_relaxation") or {}).get("relaxing_rounds", 0)
            ),
            unmet_requirements=[
                str(item) for item in (availability.get("unsupported_capabilities") or [])
            ],
            note=(state.get("strategy_revision") or {}).get("rationale"),
        )
    except Exception:
        # Memory should never block the graph path.
        pass


def _pipeline_source(
    pipeline_data_source: Mapping[str, Any] | None,
) -> Literal["fixture", "postgres", "unknown"]:
    if not isinstance(pipeline_data_source, Mapping):
        return "unknown"
    source = pipeline_data_source.get("source")
    if source in {"fixture", "postgres"}:
        return source
    return "unknown"


def _objective_gate_reasons(backtest: CandidateBacktestResult) -> list[str]:
    trade_count = _summary_float_default(backtest.engine_summary, "effective_trade_count", 0.0)
    metrics = _candidate_metrics(backtest)
    reasons: list[str] = []

    if trade_count < MIN_OBJECTIVE_TRADES:
        reasons.append(f"거래 횟수 {trade_count:.0f}회(< {MIN_OBJECTIVE_TRADES}회) 미달")
    if metrics.out_sample_sharpe < MIN_OBJECTIVE_SHARPE:
        reasons.append(
            f"아웃-표본 샤프 {metrics.out_sample_sharpe:.4f} < {MIN_OBJECTIVE_SHARPE:.2f}"
        )
    if metrics.max_drawdown < MAX_OBJECTIVE_DRAWDOWN:
        reasons.append(
            f"최대 낙폭 {metrics.max_drawdown:.4f} < {MAX_OBJECTIVE_DRAWDOWN:.2f}"
        )
    return reasons


def _build_backtest_reliability(
    result: CandidateBacktestResult,
    price_rows: Sequence[Mapping[str, Any]],
    *,
    source: Literal["fixture", "postgres", "unknown"],
) -> BacktestReliability:
    row_count = len(price_rows)
    dates = sorted({str(row.get("date")) for row in price_rows if row.get("date") is not None})
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
    if row_count == 0:
        reasons.append("데이터가 비어 있어 신뢰도를 계산할 수 없습니다.")
    if trading_days < _RELIABILITY_MIN_DAYS_HINT:
        reasons.append("거래일이 30일 미만입니다.")
    if ticker_count < MIN_RELIABLE_TICKERS:
        reasons.append(f"종목 수가 {MIN_RELIABLE_TICKERS}개 미만입니다.")
    if source == "fixture":
        reasons.append("fixture 데이터는 신뢰도 판단에서 제외됩니다.")
        warnings.append("fixture 데이터는 참고용 수치입니다.")

    if source == "unknown":
        warnings.append("데이터 소스가 불명확해 신뢰도가 제한됩니다.")
    if trade_count < MIN_OBJECTIVE_TRADES:
        warnings.append(
            f"거래 횟수({trade_count}회)가 {MIN_OBJECTIVE_TRADES}회 미만입니다."
        )
    if source == "postgres" and trading_days < _RELIABILITY_MIN_DAYS:
        warnings.append("postgres 데이터라도 252일 미만은 제한 신뢰도입니다.")
    if source != "postgres" and row_count > 0:
        warnings.append("postgres 외 소스는 제한 신뢰도로 처리됩니다.")

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
    ]
    if reliability.status == "insufficient":
        quality.append("신뢰도:부족")
    elif reliability.status == "limited":
        quality.append("신뢰도:제한")
    else:
        quality.append("신뢰도:충분")
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

    curve, total_return = _equal_weight_benchmark_curve(price_rows)
    if not curve:
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
        cumulative_curve=curve,
        is_available=True,
        unavailable_reason=None,
    )


def _build_public_metric_details(
    result: CandidateBacktestResult,
    *,
    price_rows: Sequence[Mapping[str, Any]],
    reliability: BacktestReliability,
    benchmark: BacktestBenchmark,
) -> list[PublicMetricDetail]:
    metrics = result.selected_candidate.metrics
    if metrics is None:
        return []

    summary = result.engine_summary
    values: dict[str, float | None] = {
        "total_return": _metric_summary(summary, ("total_return",), fallback=metrics.total_return),
        "cagr": _metric_summary(summary, ("cagr",)),
        "annualized_volatility": _metric_summary(summary, ("annualized_volatility", "volatility")),
        "sharpe_ratio": _metric_summary(summary, ("sharpe_ratio",), fallback=metrics.sharpe_ratio),
        "sortino_ratio": _metric_summary(summary, ("sortino_ratio", "sortino")),
        "max_drawdown": _metric_summary(summary, ("max_drawdown",), fallback=metrics.max_drawdown),
        "calmar_ratio": _metric_summary(summary, ("calmar_ratio",)),
        "win_rate": _metric_summary(summary, ("win_rate",), fallback=metrics.win_rate),
        "profit_factor": _metric_summary(summary, ("profit_factor",)),
        "in_sample_sharpe": _metric_summary(summary, ("in_sample_sharpe",), fallback=metrics.in_sample_sharpe),
        "out_sample_sharpe": _metric_summary(summary, ("out_sample_sharpe",), fallback=metrics.out_sample_sharpe),
        "degradation": _metric_summary(summary, ("degradation",), fallback=metrics.degradation),
    }

    if values["calmar_ratio"] is None and values["cagr"] is not None and _is_numeric_metric(values["cagr"]) and _is_numeric_metric(values["max_drawdown"]):
        values["calmar_ratio"] = _calmar_ratio(float(values["cagr"]), float(values["max_drawdown"]))

    if reliability.status == "insufficient":
        for key in list(values):
            values[key] = None
        values["benchmark_return"] = None
        values["excess_return"] = None
    else:
        values["benchmark_return"] = benchmark.total_return if benchmark.is_available else None
        if _is_numeric_metric(benchmark.total_return) and _is_numeric_metric(metrics.total_return):
            values["excess_return"] = float(metrics.total_return) - float(benchmark.total_return)
        else:
            values["excess_return"] = None

    unavailable_reason = None if reliability.status != "insufficient" else _UNAVAILABLE_METRIC_REASON
    return [
        _metric_detail(key, values.get(key), unavailable_reason=unavailable_reason)
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
        source_refs=explanation.get("source_refs", []),
    )


def _metric_summary(
    summary: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    fallback: float | None = None,
) -> float | None:
    for key in keys:
        value = summary.get(key)
        if _is_numeric_metric(value):
            return float(value)
    return fallback


def _candidate_metrics(result: CandidateBacktestResult) -> BacktestMetrics:
    if result.selected_candidate.metrics is None:
        raise ValueError("selected candidate has no metrics")
    return result.selected_candidate.metrics


_UNAVAILABLE_METRIC_REASON = "데이터 신뢰도가 부족해 일부 메트릭을 계산하지 못했습니다."
_BENCHMARK_UNAVAILABLE_REASON = "신뢰도 부족으로 벤치마크 성능을 계산할 수 없습니다."


def _recommendation_gate(state: QuantAgentState) -> RecommendationGate | None:
    if state.get("backtest") is None:
        return None

    try:
        backtest = CandidateBacktestResult.model_validate(state["backtest"])
    except Exception as exc:
        return RecommendationGate(
            validated=False,
            reason=f"백테스트 결과를 해석하지 못했습니다: {type(exc).__name__}",
        )

    if backtest.selected_candidate.metrics is None:
        return RecommendationGate(
            validated=False,
            reason="선택된 후보 성능이 없어 추천 판단을 진행할 수 없습니다.",
        )

    reasons = _objective_gate_reasons(backtest)
    validated = _passes_objective_floor(backtest)
    reason = (
        "추천 기준을 통과했습니다."
        if validated
        else "추천 기준 미충족: " + (", ".join(reasons) if reasons else "추천 기준 미충족")
    )
    return RecommendationGate(validated=validated, reason=reason)


def _objective_gate_reasons(backtest: CandidateBacktestResult) -> list[str]:
    trade_count = _summary_float_default(backtest.engine_summary, "effective_trade_count", 0.0)
    metrics = _candidate_metrics(backtest)
    reasons: list[str] = []

    if trade_count < MIN_OBJECTIVE_TRADES:
        reasons.append(f"거래 수({trade_count:.0f}회) < {MIN_OBJECTIVE_TRADES}회")
    if metrics.out_sample_sharpe < MIN_OBJECTIVE_SHARPE:
        reasons.append(f"OOS 샤프({metrics.out_sample_sharpe:.4f}) < {MIN_OBJECTIVE_SHARPE:.2f}")
    if metrics.max_drawdown < MAX_OBJECTIVE_DRAWDOWN:
        reasons.append(f"최대낙폭({metrics.max_drawdown:.4f}) < {MAX_OBJECTIVE_DRAWDOWN:.2f}")
    return reasons


def _build_backtest_reliability(
    result: CandidateBacktestResult,
    price_rows: Sequence[Mapping[str, Any]],
    *,
    source: Literal["fixture", "postgres", "unknown"],
) -> BacktestReliability:
    row_count = len(price_rows)
    dates = sorted({str(row.get("date")) for row in price_rows if row.get("date") is not None})
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
    if row_count == 0:
        reasons.append("데이터가 비어 있어 신뢰도를 계산할 수 없습니다.")
    if trading_days < _RELIABILITY_MIN_DAYS_HINT:
        reasons.append("거래일이 30일 미만입니다.")
    if ticker_count < MIN_RELIABLE_TICKERS:
        reasons.append(f"종목 수가 {MIN_RELIABLE_TICKERS}개 미만입니다.")
    if source == "fixture":
        reasons.append("fixture 데이터는 신뢰도 기준에서 항상 부족으로 처리됩니다.")

    if source == "unknown":
        warnings.append("데이터 출처가 불명확해 일부 판정이 제한될 수 있습니다.")
    if trade_count < MIN_OBJECTIVE_TRADES:
        warnings.append(f"거래 수({trade_count}회)가 {MIN_OBJECTIVE_TRADES}회 미만입니다.")
    if source == "postgres" and trading_days < _RELIABILITY_MIN_DAYS:
        warnings.append("postgres 데이터는 252거래일 미만인 경우 신뢰도가 낮습니다.")
    if source != "postgres" and row_count > 0:
        warnings.append("postgres 이외의 소스는 동일 조건에서 신뢰도가 낮을 수 있습니다.")

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
    ]
    if reliability.status == "insufficient":
        quality.append("신뢰도:부족")
    elif reliability.status == "limited":
        quality.append("신뢰도:보통")
    else:
        quality.append("신뢰도:양호")
    return quality


def _build_public_metric_details(
    result: CandidateBacktestResult,
    *,
    price_rows: Sequence[Mapping[str, Any]],
    reliability: BacktestReliability,
    benchmark: BacktestBenchmark,
) -> list[PublicMetricDetail]:
    metrics = result.selected_candidate.metrics
    if metrics is None:
        return []

    summary = result.engine_summary
    values: dict[str, float | None] = {
        "total_return": _metric_summary(summary, ("total_return",), fallback=metrics.total_return),
        "cagr": _metric_summary(summary, ("cagr",)),
        "annualized_volatility": _metric_summary(summary, ("annualized_volatility", "volatility")),
        "sharpe_ratio": _metric_summary(summary, ("sharpe_ratio",), fallback=metrics.sharpe_ratio),
        "sortino_ratio": _metric_summary(summary, ("sortino_ratio", "sortino")),
        "max_drawdown": _metric_summary(summary, ("max_drawdown",), fallback=metrics.max_drawdown),
        "calmar_ratio": _metric_summary(summary, ("calmar_ratio", "calmar")),
        "win_rate": _metric_summary(summary, ("win_rate",), fallback=metrics.win_rate),
        "profit_factor": _metric_summary(summary, ("profit_factor",), fallback=None),
        "in_sample_sharpe": _metric_summary(summary, ("in_sample_sharpe",), fallback=metrics.in_sample_sharpe),
        "out_sample_sharpe": _metric_summary(summary, ("out_sample_sharpe",), fallback=metrics.out_sample_sharpe),
        "degradation": _metric_summary(summary, ("degradation",), fallback=metrics.degradation),
    }

    if values["calmar_ratio"] is None and values["cagr"] is not None and _is_numeric_metric(values["cagr"]) and _is_numeric_metric(values["max_drawdown"]):
        values["calmar_ratio"] = _calmar_ratio(float(values["cagr"]), float(values["max_drawdown"]))

    if reliability.status == "insufficient":
        for key in list(values):
            values[key] = None
        values["benchmark_return"] = None
        values["excess_return"] = None
    else:
        values["benchmark_return"] = benchmark.total_return if benchmark.is_available else None
        if _is_numeric_metric(benchmark.total_return) and _is_numeric_metric(metrics.total_return):
            values["excess_return"] = float(metrics.total_return) - float(benchmark.total_return)
        else:
            values["excess_return"] = None

    unavailable_reason = None if reliability.status != "insufficient" else _UNAVAILABLE_METRIC_REASON
    return [
        _metric_detail(key, values.get(key), unavailable_reason=unavailable_reason)
        for key in _METRIC_DETAIL_KEYS
    ]
