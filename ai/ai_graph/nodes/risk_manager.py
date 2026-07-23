from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from ai_graph.schemas import PortfolioRisk, RiskAdjustment, RiskDecision, SignalDecision


# Most confidence concentration may remove. A fully concentrated, perfectly correlated
# book keeps 1 - this fraction of its confidence; a diversified one keeps all of it.
MAX_CONCENTRATION_HAIRCUT = 0.33


class MacroSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kospi_close_change_pct: float = 0.0
    fx_daily_change_pct: float = 0.0
    vkospi: float = 20.0


def apply_risk_rules(signal: SignalDecision, macro: MacroSnapshot) -> RiskDecision:
    adjusted = signal.model_copy(deep=True)
    adjustments: list[RiskAdjustment] = []
    if adjusted.action == "BUY" and macro.kospi_close_change_pct <= -0.05:
        adjustments.append(
            RiskAdjustment(
                before="BUY",
                after="HOLD",
                rule="KOSPI_CLOSE_DROP_5PCT",
                reason="KOSPI close dropped at least 5%, so BUY is downgraded to HOLD.",
            )
        )
        adjusted = adjusted.model_copy(update={"action": "HOLD", "confidence": min(adjusted.confidence, 0.7)})
    if adjusted.action == "BUY" and abs(macro.fx_daily_change_pct) > 0.02:
        if adjusted.confidence > 0.7:
            adjustments.append(
                RiskAdjustment(
                    before="BUY",
                    after="BUY",
                    rule="FX_DAILY_MOVE_2PCT_CAP",
                    reason="FX daily move exceeded 2%, so BUY confidence is capped at 0.7.",
                )
            )
        adjusted = adjusted.model_copy(update={"confidence": min(adjusted.confidence, 0.7)})
    if adjusted.action == "BUY" and macro.vkospi > 30:
        if adjusted.confidence > 0.6:
            adjustments.append(
                RiskAdjustment(
                    before="BUY",
                    after="BUY",
                    rule="VKOSPI_30_CAP",
                    reason="VKOSPI is above 30, so BUY confidence is capped at 0.6.",
                )
            )
        adjusted = adjusted.model_copy(update={"confidence": min(adjusted.confidence, 0.6)})
    return RiskDecision(signal=adjusted, adjustments=adjustments)


def risk_manager_node(state: dict) -> dict:
    signal = SignalDecision.model_validate(
        state.get("investment_signal") or state["signal"]["investment_signal"]
    )
    macro = MacroSnapshot.model_validate(state.get("macro_snapshot") or {})
    decision = apply_risk_rules(signal, macro)

    portfolio = _measure_portfolio_risk(
        state.get("data", {}).get("screening_candidates", []),
        state.get("price_rows", []),
    )
    if portfolio is not None:
        decision = _apply_portfolio_risk(decision, portfolio)
    return {"risk": decision.model_dump()}


def _apply_portfolio_risk(decision: RiskDecision, portfolio: PortfolioRisk) -> RiskDecision:
    """Fold concentration/correlation into confidence, scaled - not thresholded.

    A concentrated, highly-correlated book earns less trust than a spread-out one, so
    confidence is multiplied by the diversification score rather than clipped at some
    line. Only a meaningful reduction is recorded as an adjustment, so a well-diversified
    portfolio produces no noise.
    """

    adjusted_signal = decision.signal
    adjustments = list(decision.adjustments)
    # Concentration lowers confidence but never zeroes it: a validated edge in a single
    # sector is still an edge, just a riskier one. Diversification moves confidence
    # across at most a third of its range, so full concentration multiplies by ~0.67
    # rather than 0. The fraction is the knob, not a per-case threshold.
    shrink = 1.0 - MAX_CONCENTRATION_HAIRCUT * (1.0 - portfolio.diversification_score)
    if shrink < 1.0 and adjusted_signal.action == "BUY":
        new_confidence = round(adjusted_signal.confidence * shrink, 4)
        if adjusted_signal.confidence - new_confidence >= 0.05:
            adjustments.append(
                RiskAdjustment(
                    before="BUY",
                    after="BUY",
                    rule="PORTFOLIO_CONCENTRATION",
                    reason=(
                        f"유효 섹터 {portfolio.effective_sectors:.1f}개, 최대 섹터 비중 "
                        f"{portfolio.top_sector_weight:.0%}"
                        + (
                            f", 평균 상관 {portfolio.average_correlation:.2f}"
                            if portfolio.average_correlation is not None
                            else ""
                        )
                        + f" - 분산도 {shrink:.2f}로 BUY 확신을 낮춥니다."
                    ),
                )
            )
            adjusted_signal = adjusted_signal.model_copy(
                update={"confidence": new_confidence}
            )
    return decision.model_copy(
        update={
            "signal": adjusted_signal,
            "adjustments": adjustments,
            "portfolio_risk": portfolio,
        }
    )


def _measure_portfolio_risk(
    candidates: Sequence[Mapping[str, Any]], price_rows: Sequence[Mapping[str, Any]]
) -> PortfolioRisk | None:
    """Concentration and correlation of the recommended names, measured from data.

    Sector weights come from the candidates' own sector tags; correlation from their
    daily returns in the loaded price history. No fixed cutoffs - both feed a single
    continuous diversification score.
    """

    tickers = [str(item.get("ticker") or "").zfill(6) for item in candidates if item.get("ticker")]
    if not tickers:
        return None

    sectors = [str(item.get("sector") or "미분류") for item in candidates if item.get("ticker")]
    sector_counts = Counter(sectors)
    name_count = len(tickers)
    weights = [count / name_count for count in sector_counts.values()]
    hhi = sum(w * w for w in weights)
    effective_sectors = 1.0 / hhi if hhi > 0 else 0.0
    top_sector_weight = max(weights) if weights else 1.0

    average_correlation = _average_pairwise_correlation(set(tickers), price_rows)

    # Sector spread: 1 when every name sits in its own sector, →0 as they pile into one.
    sector_spread = (effective_sectors - 1) / (name_count - 1) if name_count > 1 else 1.0
    sector_spread = min(1.0, max(0.0, sector_spread))
    # Correlation contribution: 1 when uncorrelated, →0 as they move together. Only the
    # positive half matters for concentration risk.
    corr_spread = 1.0 - max(0.0, average_correlation) if average_correlation is not None else 1.0
    # A single name cannot be diversified; more names help only if they are spread and
    # not co-moving. Geometric mean so either factor collapsing pulls the score down.
    diversification_score = round(math.sqrt(sector_spread * corr_spread), 4)

    return PortfolioRisk(
        name_count=name_count,
        sector_count=len(sector_counts),
        effective_sectors=round(effective_sectors, 4),
        top_sector_weight=round(top_sector_weight, 4),
        average_correlation=(
            round(average_correlation, 4) if average_correlation is not None else None
        ),
        diversification_score=diversification_score,
    )


def _average_pairwise_correlation(
    tickers: set[str], price_rows: Sequence[Mapping[str, Any]]
) -> float | None:
    """Mean pairwise correlation of the tickers' daily returns, or None if too little data."""

    series: dict[str, list[tuple[str, float]]] = {}
    for row in price_rows:
        ticker = str(row.get("ticker") or "").zfill(6)
        if ticker not in tickers:
            continue
        close = row.get("close")
        date = row.get("date")
        if close is None or date is None:
            continue
        series.setdefault(ticker, []).append((str(date), float(close)))

    returns: dict[str, dict[str, float]] = {}
    for ticker, points in series.items():
        points.sort()
        daily: dict[str, float] = {}
        for (_, prev_close), (date, close) in zip(points, points[1:]):
            if prev_close:
                daily[date] = close / prev_close - 1
        if len(daily) >= 2:
            returns[ticker] = daily

    keys = list(returns)
    correlations: list[float] = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            corr = _correlation(returns[keys[i]], returns[keys[j]])
            if corr is not None:
                correlations.append(corr)
    if not correlations:
        return None
    return sum(correlations) / len(correlations)


def _correlation(a: Mapping[str, float], b: Mapping[str, float]) -> float | None:
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        return None
    xs = [a[d] for d in common]
    ys = [b[d] for d in common]
    n = len(common)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)
