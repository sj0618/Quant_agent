from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from ai_graph.nodes.backtest import (
    BACKTEST_SPLIT_FRACTION,
    INSUFFICIENT_WALK_FORWARD_SAMPLE,
    BENCHMARK_LABEL,
    BENCHMARK_METHOD,
    BENCHMARK_WARNING,
    MIN_OBJECTIVE_TRADES,
    MIN_RELIABLE_TICKERS,
    METRIC_ROUND_DIGITS,
    _is_numeric_metric,
    _price_rows,
    _public_engine_summary,
    _summary_float_default,
)
from ai_graph.quant_explanations import metric_explanation
from ai_graph.quant_strategy import build_strategy_explanation
from ai_graph.schemas import (
    BacktestBenchmark,
    BacktestEvaluationBasis,
    BacktestPerformance,
    BacktestReliability,
    BacktestUniversePolicy,
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
    "out_sample_excess_return",
    "benchmark_period_win_rate",
    "benchmark_period_loss_rate",
    "out_sample_benchmark_period_loss_rate",
    "in_sample_sharpe",
    "out_sample_sharpe",
    "degradation",
)

_RELIABILITY_SHORT_TERM_DAYS = 30
_RELIABILITY_MIN_DAYS = 252

_UNAVAILABLE_METRIC_REASON = "신뢰도 부족으로 공개 지표를 계산할 수 없습니다."
_BENCHMARK_UNAVAILABLE_REASON = "신뢰도 부족으로 벤치마크를 표시하지 않습니다."

_COST_MODEL_RATE_KEYS = ("commission_pct", "tax_pct", "slippage_pct")
_UNIVERSE_SPLIT_SUMMARY = (
    "백테스트는 과거 시점(PIT) 기준으로 그 시점에 상장돼 있던 종목만 거래해 규칙 자체를 "
    "검증하고, 오늘의 추천 종목은 같은 규칙을 오늘 데이터에 적용한 결과입니다. "
    "두 목록이 서로 다른 것은 정상입니다."
)


def build_public_backtest_performance(
    backtest: Mapping[str, Any] | None,
    *,
    price_rows: Sequence[Mapping[str, Any]] | None = None,
    pipeline_data_source: Mapping[str, Any] | None = None,
) -> BacktestPerformance | None:
    if not backtest:
        return None

    result = CandidateBacktestResult.model_validate(backtest)
    walk_forward = result.walk_forward
    metrics = (
        walk_forward.aggregate_metrics
        if walk_forward is not None and walk_forward.status == "ready"
        else result.selected_candidate.metrics
    )
    if metrics is None:
        return None

    normalized_rows = _price_rows(price_rows)
    source = _pipeline_source(pipeline_data_source)
    reliability = _build_backtest_reliability(result, normalized_rows, source=source)
    benchmark = _build_public_benchmark(result, reliability=reliability)
    selected_parameters = result.selected_candidate.parameters
    public_metrics = _public_metrics(metrics, result.engine_summary)
    return BacktestPerformance(
        selected_candidate_id=(
            "walk-forward-selection-policy"
            if walk_forward is not None and walk_forward.status == "ready"
            else result.selected_candidate.candidate_id
        ),
        metrics=public_metrics,
        equity_curve=(walk_forward.equity_curve if walk_forward is not None and walk_forward.status == "ready" else result.equity_curve),
        engine_summary=_public_engine_summary(result.engine_summary),
        reliability=reliability,
        data_quality=_build_data_quality(reliability),
        benchmark=benchmark,
        metric_details=_build_public_metric_details(
            result,
            reliability=reliability,
            benchmark=benchmark,
        ),
        strategy_explanation=build_strategy_explanation(
            result.strategy_a,
            selected_profile=(
                selected_parameters.profile if selected_parameters is not None else None
            ),
            selected_parameters=selected_parameters,
            generated_strategies=result.generated_strategy_blueprints,
        ),
        evaluation_basis=_build_evaluation_basis(
            result, pipeline_data_source=pipeline_data_source
        ),
        universe_policy=_build_universe_policy(
            result, pipeline_data_source=pipeline_data_source
        ),
    )


def _build_evaluation_basis(
    result: CandidateBacktestResult,
    *,
    pipeline_data_source: Mapping[str, Any] | None,
) -> BacktestEvaluationBasis:
    """State which period the public numbers cover, taken from the run that produced them."""

    payload = result.backtest_payload if isinstance(result.backtest_payload, Mapping) else {}
    metadata = pipeline_data_source if isinstance(pipeline_data_source, Mapping) else {}
    walk_forward = result.walk_forward
    rolling = walk_forward is not None and walk_forward.status == "ready"

    # The traded rows say what was actually measured; the loader's policy window is the
    # fallback for results that carry no row dates.
    window_start = _text(payload.get("first_date")) or _text(metadata.get("backtest_start_session"))
    window_end = _text(payload.get("last_date")) or _text(metadata.get("backtest_end_session"))
    window = f"{window_start}~{window_end} 구간" if window_start and window_end else ""
    costs_applied = _cost_model_applied(result)

    if rolling and walk_forward is not None:
        fold_count = len(walk_forward.fold_selections)
        session_count = walk_forward.unique_evaluation_session_count
        rolled = f"{window}을 " if window else ""
        caption = (
            f"{rolled}폴드 {fold_count}개로 다시 선택하며 평가한 "
            f"검증 세션 {session_count}거래일 누적"
        )
        return BacktestEvaluationBasis(
            basis="walk_forward_policy",
            caption=_with_cost_clause(caption, costs_applied),
            window_start=window_start,
            window_end=window_end,
            window_policy_id=_text(metadata.get("backtest_window_policy_id")),
            evaluation_session_count=session_count,
            fold_count=fold_count,
            cost_model_applied=costs_applied,
        )

    hold_out_fraction = round(1.0 - BACKTEST_SPLIT_FRACTION, 4)
    percent = f"{hold_out_fraction * 100:g}"
    caption = f"{window or '전체 백테스트 구간'} 중 마지막 {percent}% 검증 구간 누적"
    return BacktestEvaluationBasis(
        basis="hold_out",
        caption=_with_cost_clause(caption, costs_applied),
        hold_out_fraction=hold_out_fraction,
        window_start=window_start,
        window_end=window_end,
        window_policy_id=_text(metadata.get("backtest_window_policy_id")),
        cost_model_applied=costs_applied,
    )


def _with_cost_clause(caption: str, costs_applied: bool) -> str:
    return f"{caption} · 거래비용 반영" if costs_applied else caption


def _cost_model_applied(result: CandidateBacktestResult) -> bool:
    """Whether this run actually charged costs, rather than whether a cost model exists."""

    cost_model = result.engine_summary.get("cost_model")
    if isinstance(cost_model, Mapping) and any(
        _is_numeric_metric(cost_model.get(key)) and float(cost_model[key]) > 0.0
        for key in _COST_MODEL_RATE_KEYS
    ):
        return True
    walk_forward = result.walk_forward
    return bool(
        walk_forward is not None and walk_forward.status == "ready" and walk_forward.costs > 0.0
    )


def _build_universe_policy(
    result: CandidateBacktestResult,
    *,
    pipeline_data_source: Mapping[str, Any] | None,
) -> BacktestUniversePolicy | None:
    """Say the screen and the backtest are two applications of one rule, when they are.

    Returned only for loads that carry a point-in-time universe descriptor. A fixture run
    has no historical membership to have excluded anything from, and claiming the policy
    there would describe a separation that did not happen.
    """

    metadata = pipeline_data_source if isinstance(pipeline_data_source, Mapping) else {}
    descriptor = metadata.get("backtest_universe")
    if not isinstance(descriptor, Mapping):
        return None

    excluded = descriptor.get("excluded_screening_candidate_count")
    excluded_count = int(excluded) if isinstance(excluded, int) and excluded >= 0 else 0
    traded = metadata.get("pit_member_count")
    payload = result.backtest_payload if isinstance(result.backtest_payload, Mapping) else {}
    if not isinstance(traded, int):
        tickers = payload.get("tickers")
        traded = len(tickers) if isinstance(tickers, list) else None

    return BacktestUniversePolicy(
        summary=_UNIVERSE_SPLIT_SUMMARY,
        policy_id=_text(metadata.get("backtest_window_policy_id")),
        window_start=_text(descriptor.get("as_of_start"))
        or _text(metadata.get("backtest_start_session")),
        window_end=_text(descriptor.get("as_of_end"))
        or _text(metadata.get("backtest_end_session")),
        traded_ticker_count=traded if isinstance(traded, int) and traded >= 0 else None,
        excluded_screening_candidate_count=excluded_count,
        excluded_notice=(
            f"오늘 스크리닝 후보 중 {excluded_count}종목은 백테스트 구간의 과거 시점 "
            "유니버스에 없어 백테스트 거래 대상에서 제외됐습니다."
            if excluded_count > 0
            else None
        ),
    )


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


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

    if source == "fixture":
        reasons.append("fixture 데이터는 신뢰도 계산에서 제외됩니다.")
    if row_count == 0:
        reasons.append("가격 데이터가 없습니다.")
    if trading_days < _RELIABILITY_SHORT_TERM_DAYS:
        reasons.append(
            f"거래일 수가 {_RELIABILITY_SHORT_TERM_DAYS}일 미만입니다. ({trading_days}일)"
        )
    if ticker_count < MIN_RELIABLE_TICKERS:
        reasons.append(f"종목 수가 {MIN_RELIABLE_TICKERS}개 미만입니다. ({ticker_count}개)")

    if source == "unknown":
        warnings.append("데이터 소스가 unknown입니다.")
    if (
        source == "postgres"
        and trading_days < _RELIABILITY_MIN_DAYS
        and trading_days >= _RELIABILITY_SHORT_TERM_DAYS
    ):
        warnings.append("PostgreSQL은 거래일 252일 이상일 때만 충분 조건을 충족합니다.")
    if trade_count < MIN_OBJECTIVE_TRADES:
        warnings.append(f"유효 거래 수가 기준 미달입니다. ({trade_count} < {MIN_OBJECTIVE_TRADES})")

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
    result: CandidateBacktestResult,
    *,
    reliability: BacktestReliability,
) -> BacktestBenchmark:
    payload = result.backtest_payload if isinstance(result.backtest_payload, Mapping) else {}
    benchmark = payload.get("benchmark") if isinstance(payload, Mapping) else None
    primary = benchmark.get("primary") if isinstance(benchmark, Mapping) else None
    reason = (
        primary.get("unavailable_reason")
        if isinstance(primary, Mapping)
        else "official KOSPI/KOSDAQ TR provenance is missing"
    )
    has_official_inputs = isinstance(primary, Mapping) and primary.get(
        "official_series_and_lagged_weights"
    ) is True
    total_return = primary.get("return") if isinstance(primary, Mapping) else None
    if (
        reliability.status == "insufficient"
        or not has_official_inputs
        or not _is_numeric_metric(total_return)
    ):
        return BacktestBenchmark(
            label=BENCHMARK_LABEL,
            method=BENCHMARK_METHOD,
            warning=BENCHMARK_WARNING,
            total_return=None,
            cumulative_curve=[],
            is_available=False,
            unavailable_reason=(
                _BENCHMARK_UNAVAILABLE_REASON
                if reliability.status == "insufficient"
                else str(reason or "official KOSPI/KOSDAQ TR provenance is incomplete")
            ),
        )
    return BacktestBenchmark(
        label=BENCHMARK_LABEL,
        method=BENCHMARK_METHOD,
        warning=None,
        total_return=float(total_return),
        cumulative_curve=[],
        is_available=True,
        unavailable_reason=None,
    )


def _public_metrics(metrics, engine_summary: Mapping[str, Any]):
    availability = engine_summary.get("public_metric_availability")
    if not isinstance(availability, Mapping):
        return metrics
    updates = {
        key: None
        for key in (
            "out_sample_sharpe",
            "out_sample_return",
            "out_sample_excess_return",
            "in_sample_benchmark_return",
            "out_sample_benchmark_return",
            "in_sample_excess_return",
            "benchmark_period_count",
            "benchmark_period_win_rate",
            "benchmark_period_loss_rate",
            "in_sample_benchmark_period_count",
            "in_sample_benchmark_period_win_rate",
            "in_sample_benchmark_period_loss_rate",
            "out_sample_benchmark_period_count",
            "out_sample_benchmark_period_win_rate",
            "out_sample_benchmark_period_loss_rate",
        )
        if key in availability or "benchmark_comparison" in availability
    }
    return metrics.model_copy(update=updates) if updates else metrics

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
        "annualized_volatility": _metric_summary(summary, ("annualized_volatility", "volatility")),
        "sharpe_ratio": _safe_metric(metrics.sharpe_ratio),
        "sortino_ratio": _metric_summary(summary, ("sortino_ratio", "sortino")),
        "max_drawdown": _safe_metric(metrics.max_drawdown),
        "calmar_ratio": _metric_summary(summary, ("calmar_ratio", "calmar")),
        "win_rate": _safe_metric(metrics.win_rate),
        "profit_factor": _metric_summary(summary, ("profit_factor",)),
        "in_sample_sharpe": _safe_metric(metrics.in_sample_sharpe),
        "out_sample_sharpe": _safe_metric(metrics.out_sample_sharpe),
        "degradation": _safe_metric(metrics.degradation),
        "out_sample_excess_return": _safe_metric(metrics.out_sample_excess_return),
        "benchmark_period_win_rate": _safe_metric(metrics.benchmark_period_win_rate),
        "benchmark_period_loss_rate": _safe_metric(metrics.benchmark_period_loss_rate),
        "out_sample_benchmark_period_loss_rate": _safe_metric(
            metrics.out_sample_benchmark_period_loss_rate
        ),
    }

    public_availability = summary.get("public_metric_availability")
    availability = public_availability if isinstance(public_availability, Mapping) else {}
    if reliability.status == "insufficient":
        unavailable_reason = _UNAVAILABLE_METRIC_REASON
        for key in list(values):
            values[key] = None
        values["benchmark_return"] = None
        values["excess_return"] = None
        reasons = {key: unavailable_reason for key in _METRIC_DETAIL_KEYS}
    else:
        unavailable_reason = None
        values["benchmark_return"] = benchmark.total_return if benchmark.is_available else None
        if _is_numeric_metric(values["total_return"]) and _is_numeric_metric(
            values["benchmark_return"]
        ):
            values["excess_return"] = float(values["total_return"]) - float(
                values["benchmark_return"]
            )
        else:
            values["excess_return"] = None
        reasons: dict[str, str] = {}
        for key, detail in availability.items():
            if isinstance(detail, Mapping) and isinstance(detail.get("unavailable_reason"), str):
                reasons[str(key)] = str(detail["unavailable_reason"])
        benchmark_reason = reasons.get("benchmark_comparison")
        if "out_sample_sharpe" not in reasons:
            reasons["out_sample_sharpe"] = INSUFFICIENT_WALK_FORWARD_SAMPLE
        if "out_sample_excess_return" not in reasons:
            reasons["out_sample_excess_return"] = INSUFFICIENT_WALK_FORWARD_SAMPLE
        if not benchmark.is_available:
            benchmark_reason = (
                benchmark_reason
                or benchmark.unavailable_reason
                or INSUFFICIENT_WALK_FORWARD_SAMPLE
            )
            for key in (
                "benchmark_return",
                "excess_return",
                "benchmark_period_win_rate",
                "benchmark_period_loss_rate",
                "out_sample_benchmark_period_loss_rate",
            ):
                values[key] = None
                reasons[key] = benchmark_reason
        if benchmark_reason:
            for key in (
                "benchmark_return",
                "excess_return",
                "out_sample_excess_return",
                "benchmark_period_win_rate",
                "benchmark_period_loss_rate",
                "out_sample_benchmark_period_loss_rate",
            ):
                values[key] = None
                reasons[key] = benchmark_reason
        for key in reasons:
            if key in values:
                values[key] = None
    return [
        _metric_detail(
            key=key,
            value=values.get(key),
            unavailable_reason=reasons.get(key, unavailable_reason),
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
        unavailable_reason=None
        if is_available
        else (unavailable_reason or explanation.get("unavailable_reason")),
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
