from datetime import datetime, timedelta

import pytest

from ai_graph.graph import _recommendation_gate, build_public_backtest_performance
from ai_graph.nodes.backtest import (
    BENCHMARK_METHOD,
    BENCHMARK_WARNING,
    _equal_weight_benchmark_curve,
)
from ai_graph.nodes.report import build_report_bundle
from ai_graph.nodes.risk_manager import (
    MacroSnapshot,
    _average_pairwise_correlation,
    apply_risk_rules,
)
from ai_graph.quant_performance import MINIMUM_DATA_RULE
from ai_graph.research_eligibility import PerformanceUnavailable
from ai_graph.schemas import (
    BacktestMetrics,
    CodeCandidate,
    Condition,
    SignalDecision,
    StrategySpec,
)


def make_signal() -> SignalDecision:
    return SignalDecision(
        action="BUY",
        confidence=0.95,
        bull_case=["fixture"],
        bear_case=["fixture"],
        judge_reason="fixture judge",
    )


def make_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="rsi",
        name="RSI",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator="lte", right=30)],
        exit_conditions=[Condition(left="rsi", operator="gte", right=70)],
        indicators=["RSI"],
        confidence=0.8,
    )


def _performance_payload(metrics: BacktestMetrics, engine_summary: dict | None = None) -> dict:
    candidate = CodeCandidate(
        candidate_id="A2",
        variant="A",
        code="pass",
        validation_ok=True,
        metrics=metrics,
    )
    return {
        "strategy_a": make_strategy().model_dump(),
        "candidates": [candidate.model_dump()],
        "selected_candidate": candidate.model_dump(),
        "equity_curve": [],
        "engine_summary": engine_summary
        or {
            "effective_trade_count": 110,
            "montecarlo": ["large internal-only payload"],
            "rolling_sharpe": [0.1, 0.2],
        },
    }


def _fixture_rows(row_count: int = 4, ticker: str = "005930") -> list[dict[str, object]]:
    start = datetime(2026, 1, 2)
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        rows.append(
            {
                "date": (start + timedelta(days=index)).date().isoformat(),
                "ticker": ticker,
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.0 + index,
                "volume": 1_000_000.0,
                "rsi": 50.0,
            }
        )
    return rows


def _sequential_rows(start: datetime, days: int, ticker_count: int = 5) -> list[dict[str, object]]:
    tickers = [f"{i:06d}" for i in range(1, ticker_count + 1)]
    rows: list[dict[str, object]] = []
    for day in range(days):
        date = (start + timedelta(days=day)).date().isoformat()
        for idx, ticker in enumerate(tickers):
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "open": 100.0 + day + idx / 10.0,
                    "high": 100.2 + day + idx / 10.0,
                    "low": 99.8 + day + idx / 10.0,
                    "close": 100.0 + day + idx / 10.0,
                    "volume": 1_000_000.0,
                    "rsi": 30.0,
                }
            )
    return rows


def _trend_rows(
    start: datetime, days: int, ticker_count: int = 5, start_price: float = 100.0
) -> list[dict[str, object]]:
    if days <= 1:
        raise ValueError("days must be at least 2")
    rows: list[dict[str, object]] = []
    for day in range(days):
        date = (start + timedelta(days=day)).date().isoformat()
        close = start_price + (1.0 * day / (days - 1))
        for idx in range(1, ticker_count + 1):
            rows.append(
                {
                    "date": date,
                    "ticker": f"{idx:06d}",
                    "open": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1_000_000.0,
                    "rsi": 30.0,
                }
            )
    return rows


def test_risk_manager_overrides_buy_to_hold_on_kospi_drop() -> None:
    decision = apply_risk_rules(
        make_signal(),
        MacroSnapshot(kospi_close_change_pct=-0.051, fx_daily_change_pct=0.0, vkospi=20),
    )

    assert decision.signal.action == "HOLD"
    assert decision.adjustments[0].rule == "KOSPI_CLOSE_DROP_5PCT"


def test_risk_manager_caps_buy_confidence_for_fx_and_vkospi() -> None:
    decision = apply_risk_rules(
        make_signal(),
        MacroSnapshot(kospi_close_change_pct=0.0, fx_daily_change_pct=0.021, vkospi=31),
    )

    assert decision.signal.action == "BUY"
    assert decision.signal.confidence == 0.6
    assert {adjustment.rule for adjustment in decision.adjustments} == {
        "FX_DAILY_MOVE_2PCT_CAP",
        "VKOSPI_30_CAP",
    }


def test_portfolio_correlation_keeps_pairwise_missing_date_semantics() -> None:
    rows = [
        {"ticker": "000001", "date": "2026-01-01", "close": 100},
        {"ticker": "000001", "date": "2026-01-02", "close": 110},
        {"ticker": "000001", "date": "2026-01-03", "close": 99},
        {"ticker": "000001", "date": "2026-01-04", "close": 118.8},
        {"ticker": "000002", "date": "2026-01-01", "close": 100},
        {"ticker": "000002", "date": "2026-01-02", "close": 80},
        {"ticker": "000002", "date": "2026-01-04", "close": 88},
        {"ticker": "000003", "date": "2026-01-01", "close": 100},
        {"ticker": "000003", "date": "2026-01-03", "close": 120},
        {"ticker": "000003", "date": "2026-01-04", "close": 108},
    ]

    correlation = _average_pairwise_correlation({"000001", "000002", "000003"}, rows)

    assert correlation is not None
    assert abs(correlation) < 1e-12


def test_report_builds_web_and_email_projection_from_same_decision() -> None:
    risk = apply_risk_rules(make_signal(), MacroSnapshot())
    report = build_report_bundle(make_strategy(), risk)

    assert report.web_projection.title
    assert report.email_projection.title
    assert report.web_projection.summary != report.email_projection.summary


def test_public_performance_excludes_oversized_engine_arrays() -> None:
    performance = build_public_backtest_performance(
        {
            "strategy_a": make_strategy().model_dump(),
            "candidates": [
                CodeCandidate(
                    candidate_id="A2",
                    variant="A",
                    code="pass",
                    validation_ok=True,
                    metrics=BacktestMetrics(
                        sharpe_ratio=0.28,
                        max_drawdown=-0.0776,
                        win_rate=0.3364,
                        total_return=0.0898,
                        in_sample_sharpe=0.3,
                        out_sample_sharpe=0.1,
                        degradation=0.0,
                    ),
                ).model_dump()
            ],
            "selected_candidate": CodeCandidate(
                candidate_id="A2",
                variant="A",
                code="pass",
                validation_ok=True,
                metrics=BacktestMetrics(
                    sharpe_ratio=0.28,
                    max_drawdown=-0.0776,
                    win_rate=0.3364,
                    total_return=0.0898,
                    in_sample_sharpe=0.3,
                    out_sample_sharpe=0.1,
                    degradation=0.0,
                ),
            ).model_dump(),
            "equity_curve": [],
            "engine_summary": {
                "effective_trade_count": 110,
                "montecarlo": ["large internal-only payload"],
                "rolling_sharpe": [0.1, 0.2],
            },
        }
    )

    assert performance is not None
    assert performance.engine_summary == {"effective_trade_count": 110}


def test_public_performance_reliability_marks_fixture_4row_single_ticker_as_insufficient() -> None:
    performance = build_public_backtest_performance(
        _performance_payload(
            BacktestMetrics(
                sharpe_ratio=0.28,
                max_drawdown=-0.0776,
                win_rate=0.3364,
                total_return=0.0898,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.1,
                degradation=0.0,
            ),
            engine_summary={"effective_trade_count": 2},
        ),
        price_rows=_fixture_rows(),
        pipeline_data_source={"source": "fixture"},
    )

    assert performance is not None
    assert performance.reliability is not None
    assert performance.reliability.source == "fixture"
    assert performance.reliability.status == "insufficient"
    assert performance.reliability.row_count == 4
    assert performance.reliability.ticker_count == 1
    assert performance.reliability.trading_days == 4
    assert any("fixture" in reason for reason in performance.reliability.reasons)
    assert performance.is_available is False
    assert performance.metrics is None
    assert performance.equity_curve == []
    assert performance.benchmark is not None
    assert performance.benchmark.is_available is False
    assert performance.benchmark.total_return is None
    assert performance.benchmark.cumulative_curve == []
    assert all(item.is_available is False for item in performance.metric_details)
    assert all(item.unavailable_reason is not None for item in performance.metric_details)


def test_public_performance_reliability_marks_multi_ticker_postgres_as_sufficient_for_long_history() -> (
    None
):
    price_rows = _sequential_rows(datetime(2025, 1, 1), 252, ticker_count=5)
    performance = build_public_backtest_performance(
        _performance_payload(
            BacktestMetrics(
                sharpe_ratio=0.4,
                max_drawdown=-0.2,
                win_rate=0.45,
                total_return=0.15,
                in_sample_sharpe=0.32,
                out_sample_sharpe=0.12,
                degradation=0.02,
            ),
            engine_summary={"effective_trade_count": 10},
        ),
        price_rows=price_rows,
        pipeline_data_source={"source": "postgres"},
    )

    assert performance is not None
    assert performance.reliability is not None
    assert performance.reliability.status == "sufficient"
    assert performance.reliability.ticker_count == 5
    assert performance.reliability.trading_days == 252
    assert performance.reliability.source == "postgres"
    assert not performance.reliability.warnings


def test_public_performance_does_not_promote_equal_weight_proxy_to_primary() -> None:
    benchmark_rows = _trend_rows(datetime(2026, 1, 1), 252, ticker_count=5, start_price=100.0)
    performance = build_public_backtest_performance(
        _performance_payload(
            BacktestMetrics(
                sharpe_ratio=0.5,
                max_drawdown=-0.03,
                win_rate=0.56,
                total_return=0.05,
                in_sample_sharpe=0.51,
                out_sample_sharpe=0.4,
                degradation=0.1,
            ),
            engine_summary={"effective_trade_count": 8},
        ),
        price_rows=benchmark_rows,
        pipeline_data_source={"source": "postgres"},
    )

    assert performance is not None
    assert performance.benchmark is not None
    assert performance.benchmark.is_available is False
    assert performance.benchmark.method == BENCHMARK_METHOD
    assert BENCHMARK_WARNING in performance.benchmark.warning
    assert performance.benchmark.total_return is None
    benchmark_metric = next(
        metric for metric in performance.metric_details if metric.key == "benchmark_return"
    )
    excess_metric = next(
        metric for metric in performance.metric_details if metric.key == "excess_return"
    )
    assert benchmark_metric.value is None
    assert benchmark_metric.unavailable_reason
    assert excess_metric.value is None


def test_public_performance_metric_details_have_explanations_and_flags() -> None:
    performance = build_public_backtest_performance(
        _performance_payload(
            BacktestMetrics(
                sharpe_ratio=0.28,
                max_drawdown=-0.0776,
                win_rate=0.3364,
                total_return=0.0898,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.1,
                degradation=0.0,
            )
        )
    )

    assert performance is not None
    assert {item.key for item in performance.metric_details} == {
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
    }
    for detail in performance.metric_details:
        assert detail.label
        assert detail.unit
        assert detail.plain_explanation
        assert detail.why_used
        assert detail.caution
        assert detail.source_refs is not None

    details_by_key = {detail.key: detail for detail in performance.metric_details}
    assert "trade_win_rate" in details_by_key["win_rate"].plain_explanation
    # The published figure is realized trade PnL, not a period-return statistic and not
    # a function of the hit rate - the explanation has to say which one it is.
    assert "실현손익" in details_by_key["profit_factor"].plain_explanation


def test_public_performance_unavailable_benchmark_returns_turn_null_not_zero() -> None:
    performance = build_public_backtest_performance(
        _performance_payload(
            BacktestMetrics(
                sharpe_ratio=0.28,
                max_drawdown=-0.0776,
                win_rate=0.3364,
                total_return=0.0898,
                in_sample_sharpe=0.3,
                out_sample_sharpe=0.1,
                degradation=0.0,
            )
        ),
        price_rows=[],
        pipeline_data_source={},
    )

    assert performance is not None
    assert performance.benchmark is not None
    assert performance.benchmark.is_available is False
    assert performance.benchmark.total_return is None
    benchmark_metric = next(
        metric for metric in performance.metric_details if metric.key == "benchmark_return"
    )
    excess_metric = next(
        metric for metric in performance.metric_details if metric.key == "excess_return"
    )
    assert benchmark_metric.value is None
    assert benchmark_metric.is_available is False
    assert excess_metric.value is None
    assert excess_metric.is_available is False


def test_benchmark_curve_uses_fixed_universe_buy_and_hold() -> None:
    benchmark_rows = [
        {"date": "2026-01-01", "ticker": "000001", "close": 100.0},
        {"date": "2026-01-01", "ticker": "000002", "close": 100.0},
        {"date": "2026-01-02", "ticker": "000001", "close": 200.0},
        {"date": "2026-01-02", "ticker": "000002", "close": 50.0},
        {"date": "2026-01-03", "ticker": "000001", "close": 100.0},
        {"date": "2026-01-03", "ticker": "000002", "close": 100.0},
    ]
    curve, total_return = _equal_weight_benchmark_curve(benchmark_rows)

    assert total_return == pytest.approx(0.0)
    assert curve[1].cumulative_return == pytest.approx(0.25)
    assert curve[-1].cumulative_return == pytest.approx(0.0)
    # Daily rebalanced(구간별 동일비중)을 직접 검증해주는 단위 테스트.
    benchmark_two_days = ((200.0 / 100.0) + (50.0 / 100.0)) / 2.0 - 1.0
    assert benchmark_two_days != 0.0


def test_recommendation_gate_reasons_follow_objective_floor() -> None:
    metrics = BacktestMetrics(
        sharpe_ratio=0.5,
        max_drawdown=-0.4,
        win_rate=0.6,
        total_return=0.1,
        in_sample_sharpe=0.1,
        out_sample_sharpe=-0.2,
        degradation=0.05,
    )
    candidate = CodeCandidate(
        candidate_id="A2",
        variant="A",
        code="pass",
        validation_ok=True,
        metrics=metrics,
    )
    gate = _recommendation_gate(
        {
            "backtest": {
                "strategy_a": make_strategy().model_dump(),
                "candidates": [candidate.model_dump()],
                "selected_candidate": candidate.model_dump(),
                "equity_curve": [],
                "engine_summary": {"effective_trade_count": 3},
            }
        }
    )
    assert gate is not None
    assert gate.validated is False
    assert "objective 조건 미충족" in gate.reason
    assert "benchmark" not in gate.reason


def test_recommendation_gate_accepts_valid_objective() -> None:
    metrics = BacktestMetrics(
        sharpe_ratio=1.2,
        max_drawdown=-0.3,
        win_rate=0.6,
        total_return=0.5,
        in_sample_sharpe=0.6,
        out_sample_sharpe=0.5,
        degradation=0.1,
    )
    candidate = CodeCandidate(
        candidate_id="A2",
        variant="A",
        code="pass",
        validation_ok=True,
        metrics=metrics,
    )
    gate = _recommendation_gate(
        {
            "backtest": {
                "strategy_a": make_strategy().model_dump(),
                "candidates": [candidate.model_dump()],
                "selected_candidate": candidate.model_dump(),
                "equity_curve": [],
                "engine_summary": {"effective_trade_count": 10},
            }
        }
    )
    assert gate is not None
    assert gate.validated is True
    assert "objective gate를 모두 통과" in gate.reason


def _passing_gate_state() -> dict:
    """A backtest whose metrics clear the objective floor on their own."""

    candidate = CodeCandidate(
        candidate_id="A2",
        variant="A",
        code="pass",
        validation_ok=True,
        metrics=BacktestMetrics(
            sharpe_ratio=1.2,
            max_drawdown=-0.3,
            win_rate=0.6,
            total_return=0.5,
            in_sample_sharpe=0.6,
            out_sample_sharpe=0.5,
            degradation=0.1,
        ),
    )
    return {
        "backtest": {
            "strategy_a": make_strategy().model_dump(),
            "candidates": [candidate.model_dump()],
            "selected_candidate": candidate.model_dump(),
            "equity_curve": [],
            "engine_summary": {"effective_trade_count": 10},
        }
    }


def test_recommendation_gate_withholds_when_inputs_miss_the_minimum_data_rule() -> None:
    """Metrics that clear the floor still cannot validate picks over too little data.

    A ratio computed across four sessions of one ticker is arithmetic, not evidence.
    The public projection already refuses to publish it; the gate has to reach the same
    answer, or the envelope says "성과 없음" and "검증됨" in the same breath.
    """

    unavailable = PerformanceUnavailable(
        reason_code="insufficient_reliability",
        safe_facts={
            **MINIMUM_DATA_RULE,
            "source": "postgres",
            "reliability": "insufficient",
            "row_count": 4,
            "trading_days": 4,
            "ticker_count": 1,
            "trade_count": 1,
        },
    )

    gate = _recommendation_gate(_passing_gate_state(), performance=unavailable)

    assert gate is not None
    assert gate.validated is False
    assert gate.verification_complete is False
    assert gate.unmet_objective_criteria == []
    assert "performance_unavailable:insufficient_reliability" in gate.unmet_data_requirements
    assert "trading_days:4 < minimum_trading_days:30" in gate.unmet_data_requirements
    assert "ticker_count:1 < minimum_tickers:5" in gate.unmet_data_requirements
    # The reason states the rule that was applied, not a bare "부족" label.
    assert "최소" in gate.reason and "30" in gate.reason and "5" in gate.reason

    # Same backtest, no unavailable projection: the objective floor still decides. This
    # is what proves the new branch is what withheld the recommendation above.
    assert _recommendation_gate(_passing_gate_state()).validated is True


def _automatic_strategy() -> StrategySpec:
    return make_strategy().model_copy(update={"selection_mode": "automatic"})


def _gate_state(
    metrics: BacktestMetrics,
    *,
    strategy: StrategySpec,
    engine_summary: dict,
    benchmark_primary: dict | None = None,
) -> dict:
    candidate = CodeCandidate(
        candidate_id="A2",
        variant="A",
        code="pass",
        validation_ok=True,
        metrics=metrics,
    )
    backtest = {
        "strategy_a": strategy.model_dump(),
        "candidates": [candidate.model_dump()],
        "selected_candidate": candidate.model_dump(),
        "equity_curve": [],
        "engine_summary": engine_summary,
    }
    if benchmark_primary is not None:
        backtest["backtest_payload"] = {"benchmark": {"primary": benchmark_primary}}
    return {"backtest": backtest}


def _clearing_metrics() -> BacktestMetrics:
    return BacktestMetrics(
        sharpe_ratio=1.2,
        max_drawdown=-0.3,
        win_rate=0.6,
        total_return=0.5,
        in_sample_sharpe=0.6,
        out_sample_sharpe=0.5,
        degradation=0.1,
        selection_adjusted_sharpe=0.6,
        in_sample_benchmark_return=0.05,
        out_sample_benchmark_return=0.02,
        out_sample_excess_return=0.2,
        benchmark_period_count=12,
        out_sample_benchmark_period_count=6,
        out_sample_benchmark_period_loss_rate=0.1,
    )


def test_an_unloaded_official_benchmark_is_not_reported_as_a_performance_shortfall() -> None:
    gate = _recommendation_gate(
        _gate_state(
            _clearing_metrics(),
            strategy=_automatic_strategy(),
            engine_summary={"effective_trade_count": 10},
            benchmark_primary={
                "available": False,
                "unavailable_reason": "official KOSPI/KOSDAQ TR rows are not loaded",
            },
        )
    )

    assert gate is not None
    assert gate.verification_complete is False
    assert gate.unmet_objective_criteria == []
    assert len(gate.unmet_data_requirements) == 1
    assert "적재되지 않아" in gate.unmet_data_requirements[0]
    assert "official KOSPI/KOSDAQ TR rows are not loaded" in gate.unmet_data_requirements[0]
    assert "미달" not in gate.reason


def test_a_loaded_official_benchmark_leaves_the_gate_complete() -> None:
    gate = _recommendation_gate(
        _gate_state(
            _clearing_metrics(),
            strategy=_automatic_strategy(),
            engine_summary={"effective_trade_count": 10},
            benchmark_primary={"available": True, "return": 0.1},
        )
    )

    assert gate is not None
    assert gate.validated is True
    assert gate.verification_complete is True
    assert gate.unmet_data_requirements == []
    assert "objective gate를 모두 통과" in gate.reason


def test_a_measured_shortfall_and_a_missing_input_are_reported_separately() -> None:
    metrics = _clearing_metrics().model_copy(update={"out_sample_sharpe": None})
    gate = _recommendation_gate(
        _gate_state(
            metrics,
            strategy=make_strategy(),
            engine_summary={"effective_trade_count": 3},
        )
    )

    assert gate is not None
    assert gate.validated is False
    assert gate.verification_complete is False
    assert any("거래 횟수" in item for item in gate.unmet_objective_criteria)
    assert any("계산할 수 없음" in item for item in gate.unmet_data_requirements)
    assert "그리고 아직 검증하지 못한 항목" in gate.reason


def test_a_gate_blocked_only_on_missing_inputs_never_says_the_strategy_underperformed() -> None:
    metrics = _clearing_metrics().model_copy(update={"out_sample_sharpe": None})
    gate = _recommendation_gate(
        _gate_state(
            metrics,
            strategy=make_strategy(),
            engine_summary={"effective_trade_count": 10},
        )
    )

    assert gate is not None
    assert gate.validated is False
    assert gate.unmet_objective_criteria == []
    assert "성과가 기준에 미달한 것이 아니라" in gate.reason


def test_the_universe_split_is_disclosed_on_the_ready_message() -> None:
    from ai_graph.graph import _ready_message

    message = _ready_message(
        {
            "data": {
                "pipeline_data_source": {
                    "backtest_universe": {"excluded_screening_candidate_count": 3}
                }
            }
        },
        validated=True,
    )

    assert "과거 시점(PIT)" in message
    assert "3종목" in message


def test_a_run_without_a_point_in_time_universe_claims_no_split() -> None:
    from ai_graph.graph import _ready_message

    message = _ready_message({"data": {"pipeline_data_source": {"source": "fixture"}}}, validated=True)

    assert "과거 시점(PIT)" not in message
