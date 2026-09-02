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

_STATUS_BY_SIGNAL: dict[str, str] = {
    "BUY": "주목",
    "HOLD": "유지",
    "SELL": "매도",
    "NO_RECOMMENDATION": "근거 부족",
}


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
    sell_count = sum(1 for row in comparison_rows if row.today_signal == "SELL")
    unavailable_count = sum(
        1 for row in comparison_rows if row.today_signal == "NO_RECOMMENDATION"
    )
    avg_return = sum(row.total_return for row in comparison_rows) / total
    avg_mdd = sum(row.max_drawdown for row in comparison_rows) / total

    summary = [f"총 {total}개 전략 중 {buy_count}개 전략에서 BUY 신호가 발생했습니다."]
    if hold_count:
        summary.append(f"{hold_count}개 전략은 HOLD 상태입니다.")
    if sell_count:
        summary.append(f"{sell_count}개 전략은 SELL(매도) 상태입니다.")
    if unavailable_count:
        summary.append(f"{unavailable_count}개 전략은 L4 근거 부족으로 추천을 생성하지 않았습니다.")
    summary.append(f"최근 백테스트 기준 평균 수익률은 {avg_return * 100:.1f}%, 평균 MDD는 {avg_mdd * 100:.1f}%입니다.")
    if avg_mdd <= -0.10:
        summary.append("변동성이 확대된 전략은 리스크 관리가 필요합니다.")
    return summary


def build_strategy_cards(strategies: list[DailyDigestStrategyInput]) -> list[DailyDigestStrategyCard]:
    return [_build_strategy_card(strategy) for strategy in strategies]


def _build_strategy_card(strategy: DailyDigestStrategyInput) -> DailyDigestStrategyCard:
    if strategy.today_signal == "NO_RECOMMENDATION":
        return DailyDigestStrategyCard(
            strategy_id=strategy.strategy_id,
            title=strategy.name,
            today_signal=strategy.today_signal,
            targets=strategy.targets,
            metrics=strategy.metrics,
            win_rate=strategy.win_rate,
            trade_count=strategy.trade_count,
            ai_interpretation=_fallback_strategy_summary(strategy),
            caution=_fallback_strategy_concerns(strategy)[0],
        )

    context = {
        "strategy_name": strategy.name,
        "timeframe": strategy.timeframe,
        "today_signal": strategy.today_signal,
        "metrics": strategy.metrics.model_dump(),
        "win_rate": strategy.win_rate,
        "trade_count": strategy.trade_count,
    }
    # 메일 본문은 퀀트를 막 시작한 구독자가 읽는다. 지표 이름만 나열하면 "그래서 뭘 하라는
    # 건지" 알 수 없으므로, 지표가 뭘 재는지 → 오늘 왜 이 신호인지 → 무엇을 하면 되는지
    # 순서로 풀어 쓰게 한다. 강조는 `**...**` 로만 표시한다 (렌더러가 굵기만 지원한다).
    payload = generate_role_debate(
        role="DIGEST_STRATEGY_CARD",
        task=(
            "Write for a beginner quant investor who may not know what the indicator measures. "
            "As 'summary', write one paragraph in Korean that (1) explains in plain words what "
            "the strategy's indicator looks at, (2) says why today's signal came out, and "
            "(3) states what the reader should actually do. As the first 'concerns' item, write "
            "the risk and the concrete precaution to take, also in plain Korean. "
            "When today_signal is NO_RECOMMENDATION, state that supporting L4 evidence is absent "
            "and do not imply BUY, SELL, HOLD, or another trading instruction. "
            "Wrap the few most important phrases in **double asterisks** for bold emphasis; "
            "use no other markup."
        ),
        context=context,
        fallback=RoleDebatePayload(
            role="DIGEST_STRATEGY_CARD",
            summary=_fallback_strategy_summary(strategy),
            concerns=_fallback_strategy_concerns(strategy),
            recommendation=strategy.today_signal,
            confidence=0.0 if strategy.today_signal == "NO_RECOMMENDATION" else 0.5,
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


def _fallback_strategy_summary(strategy: DailyDigestStrategyInput) -> str:
    if strategy.today_signal == "NO_RECOMMENDATION":
        return f"{strategy.name} 전략은 L4 근거가 없어 오늘 추천을 생성하지 않았습니다."
    return (
        f"{strategy.name} 전략은 오늘 **{strategy.today_signal}** 신호를 유지하고 있습니다. "
        f"최근 승률 {strategy.win_rate * 100:.1f}%, 거래 {strategy.trade_count}건을 기준으로 판단했습니다."
    )


def _fallback_strategy_concerns(strategy: DailyDigestStrategyInput) -> list[str]:
    if strategy.today_signal == "NO_RECOMMENDATION":
        return ["**L4 근거가 확인될 때까지** 매매 지시로 해석하지 마세요."]
    return ["**손절 기준을 미리 정해두고**, 거래량이 함께 늘고 있는지 확인하세요."]
