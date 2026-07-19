from __future__ import annotations

from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_graph.llm.role_calls import RoleDebatePayload, generate_role_debate
from ai_graph.nodes.backtest import summarize_backtest
from ai_graph.schemas import L4Evidence, SignalDecision as InvestmentSignalDecision

SignalAction = Literal["BUY", "SELL", "HOLD", "WATCH"]


class ConditionOperator(str, Enum):
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    EQ = "eq"
    NE = "ne"
    BETWEEN = "between"


class SignalCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: str
    operator: ConditionOperator
    right: float | list[float]
    description: str | None = None

    @model_validator(mode="after")
    def validate_right_shape(self) -> "SignalCondition":
        if self.operator == ConditionOperator.BETWEEN:
            if not isinstance(self.right, list) or len(self.right) != 2:
                raise ValueError("between requires two numeric bounds")
            if float(self.right[0]) > float(self.right[1]):
                raise ValueError("between lower bound must be <= upper bound")
        elif not isinstance(self.right, (int, float)):
            raise ValueError("scalar operators require numeric right")
        return self


class SignalStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    entry_rules: list[SignalCondition]
    exit_rules: list[SignalCondition] = Field(default_factory=list)
    entry_logic: Literal["all", "any"] = "all"
    exit_logic: Literal["all", "any"] = "any"


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    timestamp: datetime
    metrics: dict[str, float]


class SignalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    debug_ref: str
    strategy_id: str
    ticker: str
    action: SignalAction
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    matching_entry_rules: list[str] = Field(default_factory=list)
    matching_exit_rules: list[str] = Field(default_factory=list)


def generate_signal(
    strategy: SignalStrategy | dict[str, Any],
    market: MarketSnapshot | dict[str, Any],
    *,
    has_position: bool = False,
    trace_id: str | None = None,
) -> SignalResult:
    spec = (
        strategy
        if isinstance(strategy, SignalStrategy)
        else SignalStrategy.model_validate(strategy)
    )
    market_snapshot = (
        market
        if isinstance(market, MarketSnapshot)
        else MarketSnapshot.model_validate(market)
    )
    trace = trace_id or _trace_id(
        f"{spec.strategy_id}:{market_snapshot.ticker}:{market_snapshot.timestamp.isoformat()}"
    )

    entry_matches = _matching_rules(
        spec.entry_rules, spec.entry_logic, market_snapshot.metrics
    )
    exit_matches = _matching_rules(
        spec.exit_rules, spec.exit_logic, market_snapshot.metrics
    )
    if has_position and exit_matches:
        return _result(
            trace,
            spec.strategy_id,
            market_snapshot.ticker,
            "SELL",
            ["exit condition matched"],
            matching_exit_rules=exit_matches,
        )
    if not has_position and entry_matches:
        return _result(
            trace,
            spec.strategy_id,
            market_snapshot.ticker,
            "BUY",
            ["entry condition matched"],
            matching_entry_rules=entry_matches,
        )
    return _result(
        trace,
        spec.strategy_id,
        market_snapshot.ticker,
        "HOLD" if has_position else "WATCH",
        ["no actionable rule matched"],
    )


def signal_node(state: dict[str, Any]) -> dict[str, Any]:
    debate = build_signal_debate(state)
    if "market_snapshot" in state:
        result = generate_signal(
            state["strategy_spec"],
            state["market_snapshot"],
            has_position=bool(state.get("has_position", False)),
            trace_id=state.get("trace_id"),
        )
        investment_signal = build_investment_signal(
            state.get("backtest", {}),
            trace_id=state.get("trace_id"),
            l4_evidence=state.get("l4_evidence"),
            debate=debate,
        )
    else:
        result = _result(
            state.get("trace_id", _trace_id(str(state))),
            state["strategy_spec"]["strategy_id"],
            "KOSPI200",
            "WATCH",
            ["no single-ticker market snapshot supplied"],
        )
        investment_signal = build_investment_signal(
            state.get("backtest", {}),
            trace_id=state.get("trace_id"),
            l4_evidence=state.get("l4_evidence"),
            debate=debate,
        )
    return {
        "signal": result.model_dump(),
        "investment_signal": investment_signal.model_dump(),
        "signal_debate": debate,
        "trace_id": result.trace_id,
        "debug_ref": result.debug_ref,
    }


def build_investment_signal(
    backtest: dict[str, Any],
    *,
    trace_id: str | None = None,
    l4_evidence: list[dict[str, Any]] | None = None,
    debate: dict[str, Any] | None = None,
) -> InvestmentSignalDecision:
    selected = backtest.get("selected_candidate") or {}
    metrics = selected.get("metrics") or {}
    sharpe = float(metrics.get("sharpe_ratio", 0.0))
    drawdown = float(metrics.get("max_drawdown", 0.0))
    bull_case = [
        "Candidate-code backtest selected the best objective-score candidate.",
        f"Selected Sharpe ratio is {sharpe:.2f}.",
    ]
    bear_case = [
        "Hankyung consensus buy-opinion decrease is a required production adapter.",
        "KIS foreign net-selling N-day cumulative flow is a required production adapter.",
        "English IB report search is optional in MVP and disabled by default.",
    ]
    if debate:
        bull_summary = debate.get("bull", {}).get("summary")
        bear_summary = debate.get("bear", {}).get("summary")
        if bull_summary:
            bull_case.append(str(bull_summary))
        if bear_summary:
            bear_case.append(str(bear_summary))
    if drawdown < -0.12:
        action = "DROP"
        confidence = 0.64
        judge_reason = "Bear case dominates because drawdown is beyond the MVP tolerance."
    elif sharpe >= 1.2:
        action = "BUY"
        confidence = 0.82
        judge_reason = "Bull case dominates after candidate-code backtest."
    else:
        action = "HOLD"
        confidence = 0.68
        judge_reason = "Evidence is usable but not strong enough for BUY."
    evidence_items = default_l4_evidence(trace_id or "trace") if l4_evidence is None else l4_evidence
    evidence = [L4Evidence.model_validate(item) for item in evidence_items]
    return InvestmentSignalDecision(
        action=action,
        confidence=confidence,
        bull_case=bull_case,
        bear_case=bear_case,
        judge_reason=judge_reason,
        l4_evidence=evidence,
    )


def build_signal_debate(state: dict[str, Any]) -> dict[str, Any]:
    context = {
        "strategy": state.get("strategy_spec", {}),
        "backtest": summarize_backtest(state.get("backtest", {})),
        "l4_evidence": state.get("l4_evidence", []),
        "screening_candidates": state.get("data", {}).get("screening_candidates", []),
        "data_availability": state.get("data", {}).get("data_availability", {}),
    }
    bull = generate_role_debate(
        role="SIGNAL_BULL",
        task="Collect supportive signal evidence only.",
        context=context,
        fallback=RoleDebatePayload(
            role="SIGNAL_BULL",
            summary="후보 코드 백테스트와 공용 DB 후보가 있으면 BUY/HOLD 판단의 긍정 근거로 사용합니다.",
            evidence=["Selected code candidate metrics are available.", "SEIBro raw evidence is attached when DB is configured."],
            recommendation="BUY_OR_HOLD",
            confidence=0.72,
        ),
    )
    bear = generate_role_debate(
        role="SIGNAL_BEAR",
        task="Collect negative signal evidence and sell-deficiency gaps only.",
        context=context,
        fallback=RoleDebatePayload(
            role="SIGNAL_BEAR",
            summary="매도 의견 감소, 외국인 순매도, 영문 IB downgrade 축은 production adapter가 필요합니다.",
            concerns=["Sell-deficiency three-axis data is not fully connected.", "External web search is disabled."],
            recommendation="confidence_cap_if_missing",
            confidence=0.66,
        ),
    )
    judge = generate_role_debate(
        role="SIGNAL_JUDGE",
        task="Judge signal sufficiency and final BUY/HOLD/DROP confidence.",
        context={**context, "bull": bull.model_dump(), "bear": bear.model_dump()},
        fallback=RoleDebatePayload(
            role="SIGNAL_JUDGE",
            summary="백테스트 성과를 우선하되, 누락된 수급/뉴스 축은 confidence에서 보수적으로 반영합니다.",
            evidence=["Backtest metrics and Risk Manager inputs are available."],
            concerns=bear.concerns,
            recommendation="use_backtest_with_missing_data_disclosure",
            confidence=0.7,
            validation_results={
                "source_sufficiency": "partial",
                "source_diversity": "db_and_fixture",
                "sell_deficiency_axes": "not_fully_connected",
            },
        ),
    )
    return {
        "bull": bull.model_dump(),
        "bear": bear.model_dump(),
        "judge": judge.model_dump(),
    }


def default_l4_evidence(trace_id: str) -> list[dict[str, Any]]:
    published = datetime(2026, 5, 19, 9, 0, 0)
    retrieved = datetime(2026, 5, 19, 9, 1, 0)
    return [
        {
            "publisher": "QuantAgent fixture",
            "published_at": published,
            "retrieved_at": retrieved,
            "freshness_days": 0,
            "dedupe_group": f"{trace_id}:fixture:l4",
            "access_status": "fixture",
            "quality_note": "MVP fixture evidence until production adapters are connected.",
        }
    ]


def _matching_rules(
    rules: list[SignalCondition], logic: str, metrics: dict[str, float]
) -> list[str]:
    if not rules:
        return []
    matches = [
        rule.description or _describe(rule) for rule in rules if _matches(rule, metrics)
    ]
    if logic == "all" and len(matches) != len(rules):
        return []
    return matches


def _matches(rule: SignalCondition, metrics: dict[str, float]) -> bool:
    if rule.left not in metrics:
        return False
    left = float(metrics[rule.left])
    if rule.operator == ConditionOperator.BETWEEN:
        low, high = rule.right  # type: ignore[misc]
        return float(low) <= left <= float(high)
    right = float(rule.right)
    if rule.operator == ConditionOperator.LT:
        return left < right
    if rule.operator == ConditionOperator.LTE:
        return left <= right
    if rule.operator == ConditionOperator.GT:
        return left > right
    if rule.operator == ConditionOperator.GTE:
        return left >= right
    if rule.operator == ConditionOperator.EQ:
        return left == right
    if rule.operator == ConditionOperator.NE:
        return left != right
    raise ValueError(f"unsupported operator: {rule.operator}")


def _result(
    trace_id: str,
    strategy_id: str,
    ticker: str,
    action: SignalAction,
    reasons: list[str],
    *,
    matching_entry_rules: list[str] | None = None,
    matching_exit_rules: list[str] | None = None,
) -> SignalResult:
    return SignalResult(
        trace_id=trace_id,
        debug_ref=f"signal:{trace_id}",
        strategy_id=strategy_id,
        ticker=ticker,
        action=action,
        confidence=1.0,
        reasons=reasons,
        matching_entry_rules=matching_entry_rules or [],
        matching_exit_rules=matching_exit_rules or [],
    )


def _describe(rule: SignalCondition) -> str:
    return f"{rule.left} {rule.operator.value} {rule.right}"


def _trace_id(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]
