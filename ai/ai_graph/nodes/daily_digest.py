from __future__ import annotations

from ai_graph.llm.role_calls import (
    RoleDebatePayload,
    generate_daily_digest_overall_comment,
    generate_market_brief,
    generate_role_debate,
)
from ai_graph.schemas import (
    DailyDigestComparisonRow,
    DailyDigestHeader,
    DailyDigestReport,
    DailyDigestStrategyCard,
    DailyDigestStrategyInput,
    MarketBrief,
)


MAX_DIGEST_STRATEGIES = 3

_STATUS_BY_SIGNAL: dict[str, str] = {"BUY": "주목", "HOLD": "유지", "DROP": "관망"}


def build_daily_digest(
    strategies: list[DailyDigestStrategyInput],
    *,
    user_name: str,
    report_date: str,
) -> DailyDigestReport:
    if not strategies:
        raise ValueError("daily digest requires at least one strategy")
    if len(strategies) > MAX_DIGEST_STRATEGIES:
        raise ValueError(f"daily digest supports at most {MAX_DIGEST_STRATEGIES} strategies")

    comparison_rows = build_comparison_rows(strategies)
    strategy_cards = build_strategy_cards(strategies)
    overall_summary = build_overall_summary(strategies, comparison_rows)
    overall_comment = generate_daily_digest_overall_comment(strategies, comparison_rows)
    market_brief = generate_market_brief(
        strategy_names=[strategy.name for strategy in strategies],
        report_date=report_date,
        fallback=MarketBrief(
            headline="오늘의 시황 브리핑을 가져오지 못했습니다.",
            items=[],
            fallback_reasons=["websearch_unavailable"],
        ),
    )

    return DailyDigestReport(
        header=DailyDigestHeader(report_date=report_date, user_name=user_name, strategy_count=len(strategies)),
        overall_summary=overall_summary,
        comparison_rows=comparison_rows,
        strategy_cards=strategy_cards,
        ai_overall_comment=overall_comment,
        market_brief=market_brief,
        footer=[
            "본 리포트는 투자 참고용 정보이며, 투자 판단과 책임은 사용자 본인에게 있습니다.",
            "QuantAgent는 알고리즘 기반 분석 결과를 제공하며 수익을 보장하지 않습니다.",
            "이 메일은 사용자가 선택한 전략을 기준으로 매일 오전 8시에 자동 발송됩니다.",
        ],
    )


def build_comparison_rows(strategies: list[DailyDigestStrategyInput]) -> list[DailyDigestComparisonRow]:
    return [
        DailyDigestComparisonRow(
            strategy_id=strategy.strategy_id,
            name=strategy.name,
            today_signal=strategy.today_signal,
            total_return=strategy.metrics.total_return,
            max_drawdown=strategy.metrics.max_drawdown,
            sharpe_ratio=strategy.metrics.sharpe_ratio,
            status=_STATUS_BY_SIGNAL[strategy.today_signal],
        )
        for strategy in strategies
    ]


def build_overall_summary(
    strategies: list[DailyDigestStrategyInput],
    comparison_rows: list[DailyDigestComparisonRow],
) -> list[str]:
    total = len(strategies)
    buy_count = sum(1 for row in comparison_rows if row.today_signal == "BUY")
    hold_count = sum(1 for row in comparison_rows if row.today_signal == "HOLD")
    drop_count = sum(1 for row in comparison_rows if row.today_signal == "DROP")
    avg_return = sum(row.total_return for row in comparison_rows) / total
    avg_mdd = sum(row.max_drawdown for row in comparison_rows) / total

    summary = [f"총 {total}개 전략 중 {buy_count}개 전략에서 BUY 신호가 발생했습니다."]
    if hold_count:
        summary.append(f"{hold_count}개 전략은 HOLD 상태입니다.")
    if drop_count:
        summary.append(f"{drop_count}개 전략은 DROP(비중 축소) 상태입니다.")
    summary.append(f"최근 백테스트 기준 평균 수익률은 {avg_return * 100:.1f}%, 평균 MDD는 {avg_mdd * 100:.1f}%입니다.")
    if avg_mdd <= -0.10:
        summary.append("변동성이 확대된 전략은 리스크 관리가 필요합니다.")
    return summary


def build_strategy_cards(strategies: list[DailyDigestStrategyInput]) -> list[DailyDigestStrategyCard]:
    return [_build_strategy_card(strategy) for strategy in strategies]


def _build_strategy_card(strategy: DailyDigestStrategyInput) -> DailyDigestStrategyCard:
    context = {
        "strategy_name": strategy.name,
        "universe": strategy.universe,
        "timeframe": strategy.timeframe,
        "today_signal": strategy.today_signal,
        "metrics": strategy.metrics.model_dump(),
        "win_rate": strategy.win_rate,
        "trade_count": strategy.trade_count,
    }
    payload = generate_role_debate(
        role="DIGEST_STRATEGY_CARD",
        task=(
            "Write a beginner-friendly one-paragraph interpretation of today's signal "
            "(as 'summary') and a one-sentence caution/risk note (as the first 'concerns' item)."
        ),
        context=context,
        fallback=RoleDebatePayload(
            role="DIGEST_STRATEGY_CARD",
            summary=(
                f"{strategy.name} 전략은 오늘 {strategy.today_signal} 신호를 유지하고 있습니다. "
                f"최근 승률 {strategy.win_rate * 100:.1f}%, 거래 {strategy.trade_count}건을 기준으로 판단했습니다."
            ),
            concerns=["손절 기준을 명확히 설정하고 거래량 변화를 함께 확인하세요."],
            recommendation=strategy.today_signal,
            confidence=0.5,
        ),
    )
    caution = payload.concerns[0] if payload.concerns else "손절 기준을 명확히 설정하고 거래량 변화를 함께 확인하세요."
    return DailyDigestStrategyCard(
        strategy_id=strategy.strategy_id,
        title=strategy.name,
        today_signal=strategy.today_signal,
        targets=strategy.targets,
        metrics=strategy.metrics,
        win_rate=strategy.win_rate,
        trade_count=strategy.trade_count,
        ai_interpretation=payload.summary,
        caution=caution,
    )
