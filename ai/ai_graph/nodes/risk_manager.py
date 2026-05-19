from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ai_graph.schemas import RiskAdjustment, RiskDecision, SignalDecision


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
    return {"risk": decision.model_dump()}
