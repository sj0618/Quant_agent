from __future__ import annotations

from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SignalAction = Literal["BUY", "SELL", "HOLD", "WATCH", "FILTERED_OUT"]


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
    use_candidate_filter: bool = True


class CandidateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    top_k_stocks: list[str] = Field(default_factory=list)
    reason_trace: dict[str, list[str]] = Field(default_factory=dict)


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
    candidate_snapshot_id: str | None = None


def generate_signal(
    strategy: SignalStrategy | dict[str, Any],
    market: MarketSnapshot | dict[str, Any],
    *,
    candidate_snapshot: CandidateSnapshot | dict[str, Any] | None = None,
    has_position: bool = False,
    trace_id: str | None = None,
) -> SignalResult:
    spec = strategy if isinstance(strategy, SignalStrategy) else SignalStrategy.model_validate(strategy)
    market_snapshot = market if isinstance(market, MarketSnapshot) else MarketSnapshot.model_validate(market)
    candidate = _coerce_candidate(candidate_snapshot)
    trace = trace_id or _trace_id(f"{spec.strategy_id}:{market_snapshot.ticker}:{market_snapshot.timestamp.isoformat()}")

    if spec.use_candidate_filter:
        if candidate is None:
            return _result(
                trace,
                spec.strategy_id,
                market_snapshot.ticker,
                "FILTERED_OUT",
                ["candidate snapshot is required but missing"],
            )
        if market_snapshot.ticker not in candidate.top_k_stocks:
            return _result(
                trace,
                spec.strategy_id,
                market_snapshot.ticker,
                "FILTERED_OUT",
                candidate.reason_trace.get(market_snapshot.ticker, ["ticker not in research candidate universe"]),
                candidate_snapshot_id=candidate.snapshot_id,
            )

    entry_matches = _matching_rules(spec.entry_rules, spec.entry_logic, market_snapshot.metrics)
    exit_matches = _matching_rules(spec.exit_rules, spec.exit_logic, market_snapshot.metrics)
    candidate_snapshot_id = candidate.snapshot_id if candidate else None

    if has_position and exit_matches:
        return _result(
            trace,
            spec.strategy_id,
            market_snapshot.ticker,
            "SELL",
            ["exit condition matched"],
            matching_exit_rules=exit_matches,
            candidate_snapshot_id=candidate_snapshot_id,
        )
    if not has_position and entry_matches:
        return _result(
            trace,
            spec.strategy_id,
            market_snapshot.ticker,
            "BUY",
            ["entry condition matched"],
            matching_entry_rules=entry_matches,
            candidate_snapshot_id=candidate_snapshot_id,
        )
    return _result(
        trace,
        spec.strategy_id,
        market_snapshot.ticker,
        "HOLD" if has_position else "WATCH",
        ["no actionable rule matched"],
        candidate_snapshot_id=candidate_snapshot_id,
    )


def signal_node(state: dict[str, Any]) -> dict[str, Any]:
    result = generate_signal(
        state["strategy_spec"],
        state["market_snapshot"],
        candidate_snapshot=state.get("candidate_snapshot"),
        has_position=bool(state.get("has_position", False)),
        trace_id=state.get("trace_id"),
    )
    return {"signal": result.model_dump(), "trace_id": result.trace_id, "debug_ref": result.debug_ref}


def _coerce_candidate(value: CandidateSnapshot | dict[str, Any] | None) -> CandidateSnapshot | None:
    if value is None:
        return None
    return value if isinstance(value, CandidateSnapshot) else CandidateSnapshot.model_validate(value)


def _matching_rules(rules: list[SignalCondition], logic: str, metrics: dict[str, float]) -> list[str]:
    if not rules:
        return []
    matches = [rule.description or _describe(rule) for rule in rules if _matches(rule, metrics)]
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
    candidate_snapshot_id: str | None = None,
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
        candidate_snapshot_id=candidate_snapshot_id,
    )


def _describe(rule: SignalCondition) -> str:
    return f"{rule.left} {rule.operator.value} {rule.right}"


def _trace_id(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]
