import pytest

from ai_graph.nodes.daily_digest import MAX_DIGEST_STRATEGIES, build_daily_digest
from ai_graph.schemas import BacktestMetrics, DailyDigestStrategyInput


def make_strategy(
    strategy_id: str,
    name: str,
    signal: str,
    *,
    total_return: float = 0.1,
    max_drawdown: float = -0.05,
    sharpe_ratio: float = 1.0,
) -> DailyDigestStrategyInput:
    return DailyDigestStrategyInput(
        strategy_id=strategy_id,
        name=name,
        universe="KOSPI200",
        timeframe="1d",
        today_signal=signal,
        targets=["삼성전자"],
        metrics=BacktestMetrics(
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=0.58,
            total_return=total_return,
            in_sample_sharpe=sharpe_ratio,
            out_sample_sharpe=sharpe_ratio,
            degradation=0.0,
        ),
        win_rate=0.583,
        trade_count=24,
    )


def test_build_daily_digest_composes_all_sections_for_three_strategies() -> None:
    strategies = [
        make_strategy("rsi", "RSI 전략", "BUY", total_return=0.124, max_drawdown=-0.068, sharpe_ratio=1.21),
        make_strategy("macd", "MACD 전략", "HOLD", total_return=0.071, max_drawdown=-0.042, sharpe_ratio=0.94),
        make_strategy("boll", "볼린저 전략", "DROP", total_return=0.035, max_drawdown=-0.029, sharpe_ratio=0.71),
    ]

    report = build_daily_digest(strategies, user_name="홍길동", report_date="2026-06-29")

    assert report.header.strategy_count == 3
    assert len(report.comparison_rows) == 3
    assert len(report.strategy_cards) == 3
    assert report.comparison_rows[0].status == "주목"
    assert report.comparison_rows[1].status == "유지"
    assert report.comparison_rows[2].status == "관망"
    assert "BUY" in report.overall_summary[0]
    assert report.ai_overall_comment
    assert report.footer


def test_build_daily_digest_falls_back_to_disclosed_empty_market_brief_in_mock_mode() -> None:
    strategies = [make_strategy("rsi", "RSI 전략", "BUY")]

    report = build_daily_digest(strategies, user_name="홍길동", report_date="2026-06-29")

    assert report.market_brief.items == []
    assert report.market_brief.fallback_reasons


def test_build_daily_digest_rejects_more_than_max_strategies() -> None:
    strategies = [
        make_strategy("a", "전략 A", "BUY"),
        make_strategy("b", "전략 B", "HOLD"),
        make_strategy("c", "전략 C", "DROP"),
        make_strategy("d", "전략 D", "BUY"),
    ]
    assert len(strategies) > MAX_DIGEST_STRATEGIES

    with pytest.raises(ValueError):
        build_daily_digest(strategies, user_name="홍길동", report_date="2026-06-29")


def test_build_daily_digest_rejects_empty_strategy_list() -> None:
    with pytest.raises(ValueError):
        build_daily_digest([], user_name="홍길동", report_date="2026-06-29")
