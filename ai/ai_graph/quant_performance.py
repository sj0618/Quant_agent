from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import ValidationError

from ai_graph.freshness import build_freshness_evidence
from ai_graph.nodes.backtest import (
    BENCHMARK_LABEL,
    BENCHMARK_METHOD,
    BENCHMARK_WARNING,
    INSUFFICIENT_WALK_FORWARD_SAMPLE,
    METRIC_ROUND_DIGITS,
    MIN_OBJECTIVE_TRADES,
    MIN_RELIABLE_TICKERS,
    _is_numeric_metric,
    _price_rows,
    _public_engine_summary,
    _summary_float_default,
    _summary_warning_list,
    _undefined_metric_availability,
)
from ai_graph.quant_explanations import (
    PUBLIC_METRIC_KEYS,
    metric_explanation,
    metric_registry_provenance,
)
from ai_graph.quant_strategy import build_strategy_explanation
from ai_graph.research_eligibility import (
    PerformanceAvailable,
    PerformanceMethodManifest,
    PerformanceUnavailable,
    PublicPerformance,
)
from ai_graph.schemas import (
    BacktestBenchmark,
    BacktestPerformance,
    BacktestReliability,
    CandidateBacktestResult,
    FreshnessEvidence,
    PublicMetricDetail,
    PublicMetricProvenance,
)

_RELIABILITY_SHORT_TERM_DAYS = 30
_RELIABILITY_MIN_DAYS = 252

_UNAVAILABLE_METRIC_REASON = "신뢰도 부족으로 공개 지표를 계산할 수 없습니다."
_BENCHMARK_UNAVAILABLE_REASON = "신뢰도 부족으로 벤치마크를 표시하지 않습니다."
_UNAVAILABLE_ENGINE_SUMMARY_KEYS = frozenset({"effective_trade_count"})


def project_public_performance(
    backtest: Mapping[str, Any] | None,
    *,
    price_rows: Sequence[Mapping[str, Any]] | None = None,
    pipeline_data_source: Mapping[str, Any] | None = None,
) -> PublicPerformance | None:
    """Project an internal backtest onto the sole public performance contract.

    ``BacktestPerformance`` intentionally remains an internal calculation/audit
    object.  In particular, an insufficient run or a run without an engine-produced
    method manifest never reaches an HTTP, job, report, or export consumer with a
    partially masked metrics object.
    """

    internal = build_public_backtest_performance(
        backtest,
        price_rows=price_rows,
        pipeline_data_source=pipeline_data_source,
    )
    if internal is None:
        return None

    reliability = internal.reliability
    freshness = build_freshness_evidence(pipeline_data_source)
    safe_facts = _safe_performance_facts(
        reliability,
        pipeline_data_source,
        freshness_status=freshness.status,
        freshness_as_of=freshness.as_of.isoformat() if freshness.as_of is not None else None,
        freshness_reason=freshness.reason,
    )
    if reliability is None or reliability.status == "insufficient":
        return PerformanceUnavailable(
            reason_code="insufficient_reliability",
            safe_facts=safe_facts,
        )
    if freshness.status == "stale":
        return PerformanceUnavailable(
            reason_code="stale_source",
            safe_facts=safe_facts,
        )

    manifest = _performance_method_manifest(backtest)
    if manifest is None:
        return PerformanceUnavailable(
            reason_code="incomplete_method_manifest",
            safe_facts=safe_facts,
        )

    # Do not serialize engine_summary: it is useful for local audit/persistence but
    # is not a stable public performance schema and can carry nested raw metrics.
    public_payload = internal.model_dump(exclude={"engine_summary"}, mode="json")
    limitations = list(reliability.warnings)
    if reliability.status == "limited":
        limitations.insert(0, "Performance evidence is limited; review provenance before relying on values.")
    return PerformanceAvailable(
        performance=public_payload,
        method_manifest=manifest,
        limitations=limitations,
    )


def _performance_method_manifest(
    backtest: Mapping[str, Any] | None,
) -> PerformanceMethodManifest | None:
    if not isinstance(backtest, Mapping):
        return None
    summary = backtest.get("engine_summary")
    raw = summary.get("performance_method_manifest") if isinstance(summary, Mapping) else None
    if not isinstance(raw, Mapping):
        return None
    try:
        return PerformanceMethodManifest.model_validate(raw)
    except ValidationError:
        # Manifest validation is intentionally fail-closed at the public boundary.
        return None


# The minimum-input rule applied above, restated as data. A consumer that has to
# explain *why* a report is short must not re-derive these numbers from its own copy
# of the thresholds, or the explanation drifts from the rule that was enforced.
MINIMUM_DATA_RULE: dict[str, str | int | bool | None] = {
    "minimum_trading_days": _RELIABILITY_SHORT_TERM_DAYS,
    "minimum_tickers": MIN_RELIABLE_TICKERS,
    "sufficient_trading_days": _RELIABILITY_MIN_DAYS,
    "minimum_trades": MIN_OBJECTIVE_TRADES,
}


def _safe_performance_facts(
    reliability: BacktestReliability | None,
    pipeline_data_source: Mapping[str, Any] | None,
    *,
    freshness_status: str,
    freshness_as_of: str | None,
    freshness_reason: str,
) -> dict[str, str | int | bool | None]:
    source = _pipeline_source(pipeline_data_source)
    if reliability is None:
        facts: dict[str, str | int | bool | None] = {
            "source": source,
            **MINIMUM_DATA_RULE,
        }
    else:
        facts = {
            **MINIMUM_DATA_RULE,
            "source": reliability.source,
            "reliability": reliability.status,
            "row_count": reliability.row_count,
            "ticker_count": reliability.ticker_count,
            "trading_days": reliability.trading_days,
            "trade_count": reliability.trade_count,
            "history_start": reliability.history_start,
            "history_end": reliability.history_end,
        }
    if freshness_status == "stale":
        facts.update(
            {
                "freshness_status": freshness_status,
                "freshness_as_of": freshness_as_of,
                "freshness_reason": freshness_reason,
            }
        )
    return facts


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
    performance = BacktestPerformance(
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
    )
    return sanitize_public_backtest_performance(performance)


def sanitize_public_backtest_performance(
    performance: BacktestPerformance | None,
) -> BacktestPerformance | None:
    """Redact legacy insufficient results before any public serialization boundary.

    New projections are sanitized above, but persisted envelopes may predate that
    invariant.  This function is idempotent so API readers can enforce the same rule
    without mutating the stored execution result.
    """

    if performance is None:
        return None
    reliability = performance.reliability
    if reliability is None or reliability.status != "insufficient":
        return performance

    reason = performance.unavailable_reason or _UNAVAILABLE_METRIC_REASON
    benchmark = performance.benchmark
    if benchmark is not None:
        benchmark = benchmark.model_copy(
            update={
                "total_return": None,
                "cumulative_curve": [],
                "is_available": False,
                "unavailable_reason": benchmark.unavailable_reason
                or _BENCHMARK_UNAVAILABLE_REASON,
            }
        )
    metric_details = [
        detail.model_copy(
            update={
                "value": None,
                "is_available": False,
                "unavailable_reason": detail.unavailable_reason or reason,
            }
        )
        for detail in performance.metric_details
    ]
    return performance.model_copy(
        update={
            "metrics": None,
            "equity_curve": [],
            "engine_summary": _unavailable_engine_summary(performance.engine_summary),
            "benchmark": benchmark,
            "metric_details": metric_details,
            "is_available": False,
            "unavailable_reason": reason,
        }
    )


def sanitize_public_performance(
    performance: PublicPerformance | None,
    *,
    freshness_evidence: FreshnessEvidence | None = None,
    freshness_status: str | None = None,
) -> PublicPerformance | None:
    """Fail closed when a legacy public envelope claims availability without valid data.

    New envelopes are built through :func:`project_public_performance`, but a stored
    payload from before that boundary can still carry an available variant whose nested
    performance document says the warm-up/history was insufficient, or whose envelope
    records a stale source. Readers must downgrade that object before it reaches any API
    response.
    """

    if performance is None:
        if freshness_evidence is not None and freshness_evidence.status == "stale":
            return _stale_public_performance(
                freshness_evidence=freshness_evidence,
            )
        if freshness_status == "stale":
            return _stale_public_performance(freshness_status=freshness_status)
        return None
    if not isinstance(performance, PerformanceAvailable):
        return performance
    payload = performance.performance
    reliability = payload.get("reliability") if isinstance(payload, Mapping) else None
    if freshness_evidence is not None and freshness_evidence.status == "stale":
        return _stale_public_performance(
            reliability=reliability,
            freshness_evidence=freshness_evidence,
        )
    if freshness_status == "stale":
        return _stale_public_performance(
            reliability=reliability,
            freshness_status=freshness_status,
        )
    safe_facts = _legacy_performance_safe_facts(reliability)
    if not isinstance(reliability, Mapping) or reliability.get("status") != "insufficient":
        return performance
    return PerformanceUnavailable(
        reason_code="insufficient_reliability",
        safe_facts=safe_facts,
    )


def _legacy_performance_safe_facts(
    reliability: Mapping[str, Any] | None,
) -> dict[str, str | int | bool | None]:
    if not isinstance(reliability, Mapping):
        return {}
    return {
        key: reliability.get(key)
        for key in (
            "source",
            "row_count",
            "ticker_count",
            "trading_days",
            "trade_count",
            "history_start",
            "history_end",
        )
        if isinstance(reliability.get(key), (str, int, bool)) or reliability.get(key) is None
    }


def _stale_public_performance(
    *,
    reliability: Mapping[str, Any] | None = None,
    freshness_evidence: FreshnessEvidence | None = None,
    freshness_status: str | None = None,
) -> PerformanceUnavailable:
    safe_facts = _legacy_performance_safe_facts(reliability)
    if freshness_evidence is not None:
        safe_facts.update(
            {
                "source": freshness_evidence.source,
                "freshness_status": freshness_evidence.status,
                "freshness_as_of": (
                    freshness_evidence.as_of.isoformat()
                    if freshness_evidence.as_of is not None
                    else None
                ),
                "freshness_reason": freshness_evidence.reason,
            }
        )
    elif freshness_status == "stale":
        safe_facts["freshness_status"] = freshness_status
    return PerformanceUnavailable(
        reason_code="stale_source",
        safe_facts=safe_facts,
    )


def _unavailable_engine_summary(engine_summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in engine_summary.items()
        if key in _UNAVAILABLE_ENGINE_SUMMARY_KEYS
    }


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
    availability = {
        **(public_availability if isinstance(public_availability, Mapping) else {}),
        **_undefined_metric_availability(_summary_warning_list(summary)),
    }
    if reliability.status == "insufficient":
        unavailable_reason = _UNAVAILABLE_METRIC_REASON
        for key in list(values):
            values[key] = None
        values["benchmark_return"] = None
        values["excess_return"] = None
        reasons = {key: unavailable_reason for key in PUBLIC_METRIC_KEYS}
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
        for key in PUBLIC_METRIC_KEYS
    ]


def _metric_detail(
    key: str,
    value: float | None,
    *,
    unavailable_reason: str | None = None,
) -> PublicMetricDetail:
    explanation = metric_explanation(key)
    registry = metric_registry_provenance(key)
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
        registry_version=registry["registry_version"],
        provenance=PublicMetricProvenance(
            implementation_path=registry["implementation_path"],
            implementation_ref=registry["implementation_ref"],
            implementation_hash=registry["implementation_hash"],
        ),
    )


def _metric_summary(summary: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = summary.get(key)
        if _is_numeric_metric(value):
            return float(value)
    return None


def _safe_metric(value: float | None) -> float | None:
    if _is_numeric_metric(value):
        return float(value)
    return None
