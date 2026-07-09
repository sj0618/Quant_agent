from __future__ import annotations

from typing import Iterable

from .models import (
    BacktestPlan,
    CandidateSnapshot,
    Condition,
    ConditionOperator,
    LogicMode,
    MarketSnapshot,
    SignalAction,
    SignalDecision,
    StrategySpec,
)


ALLOWED_BACKTEST_MODULES = [
    "math",
    "statistics",
    "datetime",
    "pandas",
    "numpy",
]


class QuantStrategy:
    """최종 StrategySpec을 엔진에서 사용하기 위한 canonical strategy runtime.

    설계 원칙
    - 비정형 데이터는 직접 매수/매도 신호가 아니라 후보군 필터로 사용
    - 기술적 신호는 entry/exit rules로 판단
    - 백테스트에서는 동일 StrategySpec으로 filtered / unfiltered 비교 가능
    """

    def __init__(self, spec: StrategySpec):
        self.spec = spec

    def compile_backtest_plan(self) -> BacktestPlan:
        notes = [
            "template compile only",
            "new external libraries are forbidden",
            "network calls are forbidden during code execution",
        ]
        if self.spec.research_overlay.enabled:
            notes.append("candidate snapshot is applied as a universe filter")
        else:
            notes.append("candidate filter disabled")

        return BacktestPlan(
            strategy_id=self.spec.strategy_id,
            strategy_name=self.spec.strategy_name,
            market=self.spec.market,
            asset_type=self.spec.asset_type,
            allowed_modules=ALLOWED_BACKTEST_MODULES,
            use_candidate_filter=self.spec.backtest.use_candidate_filter,
            compare_filtered_vs_unfiltered=self.spec.backtest.compare_filtered_vs_unfiltered,
            execution_timing=self.spec.backtest.execution_timing,
            use_adjusted_price=self.spec.backtest.use_adjusted_price,
            respect_historical_index_membership=self.spec.universe.respect_historical_index_membership,
            apply_reports_from=self.spec.research_overlay.apply_reports_from,
            walk_forward=self.spec.backtest.walk_forward,
            cost_model=self.spec.backtest.cost_model,
            notes=notes,
        )

    def effective_universe(
        self,
        full_universe: Iterable[str],
        candidate_snapshot: CandidateSnapshot | None = None,
        when=None,
    ) -> list[str]:
        full_universe = list(full_universe)
        if not self.spec.research_overlay.enabled:
            return full_universe

        if candidate_snapshot is None:
            return []

        if when is not None and not candidate_snapshot.is_effective_for(when):
            return []

        if self.spec.universe.mode.value == "full_universe":
            return full_universe

        return [ticker for ticker in full_universe if candidate_snapshot.contains_ticker(ticker)]

    def generate_signal(
        self,
        market: MarketSnapshot,
        has_position: bool = False,
        candidate_snapshot: CandidateSnapshot | None = None,
    ) -> SignalDecision:
        if self.spec.research_overlay.enabled:
            if candidate_snapshot is None:
                return SignalDecision(
                    strategy_id=self.spec.strategy_id,
                    ticker=market.ticker,
                    action=SignalAction.FILTERED_OUT,
                    confidence=1.0,
                    reasons=["candidate snapshot is required but missing"],
                )
            if not candidate_snapshot.is_effective_for(market.timestamp):
                return SignalDecision(
                    strategy_id=self.spec.strategy_id,
                    ticker=market.ticker,
                    action=SignalAction.FILTERED_OUT,
                    confidence=1.0,
                    reasons=["candidate snapshot is not effective yet"],
                    candidate_snapshot_id=candidate_snapshot.snapshot_id,
                )
            if not candidate_snapshot.contains_ticker(market.ticker):
                reason = candidate_snapshot.reason_trace.get(market.ticker, ["ticker not in candidate universe"])
                return SignalDecision(
                    strategy_id=self.spec.strategy_id,
                    ticker=market.ticker,
                    action=SignalAction.FILTERED_OUT,
                    confidence=1.0,
                    reasons=reason,
                    candidate_snapshot_id=candidate_snapshot.snapshot_id,
                )

        entry_hits = self._evaluate_rules(
            rules=self.spec.entry_rules,
            logic=self.spec.entry_logic,
            market=market,
        )
        exit_hits = self._evaluate_rules(
            rules=self.spec.exit_rules,
            logic=self.spec.exit_logic,
            market=market,
        )

        if has_position and exit_hits:
            return SignalDecision(
                strategy_id=self.spec.strategy_id,
                ticker=market.ticker,
                action=SignalAction.SELL,
                confidence=1.0,
                reasons=["exit condition matched"],
                matching_exit_rules=exit_hits,
                candidate_snapshot_id=candidate_snapshot.snapshot_id if candidate_snapshot else None,
            )

        if not has_position and entry_hits:
            return SignalDecision(
                strategy_id=self.spec.strategy_id,
                ticker=market.ticker,
                action=SignalAction.BUY,
                confidence=1.0,
                reasons=["entry condition matched"],
                matching_entry_rules=entry_hits,
                candidate_snapshot_id=candidate_snapshot.snapshot_id if candidate_snapshot else None,
            )

        return SignalDecision(
            strategy_id=self.spec.strategy_id,
            ticker=market.ticker,
            action=SignalAction.HOLD if has_position else SignalAction.WATCH,
            confidence=1.0,
            reasons=["no actionable rule matched"],
            candidate_snapshot_id=candidate_snapshot.snapshot_id if candidate_snapshot else None,
        )

    def _evaluate_rules(
        self,
        rules: list[Condition],
        logic: LogicMode,
        market: MarketSnapshot,
    ) -> list[str]:
        if not rules:
            return []

        hits: list[str] = []
        for rule in rules:
            if self._evaluate_condition(rule, market):
                hits.append(rule.description or self._humanize(rule))

        if logic == LogicMode.ALL:
            return hits if len(hits) == len(rules) else []
        return hits if hits else []

    def _evaluate_condition(self, rule: Condition, market: MarketSnapshot) -> bool:
        current_left = self._resolve_metric(rule.left, market.metrics)

        if rule.operator in {
            ConditionOperator.LT,
            ConditionOperator.LTE,
            ConditionOperator.GT,
            ConditionOperator.GTE,
            ConditionOperator.EQ,
            ConditionOperator.NE,
        }:
            right = float(rule.right)
            return self._compare_scalar(current_left, right, rule.operator)

        if rule.operator == ConditionOperator.BETWEEN:
            low, high = rule.right  # type: ignore[misc]
            return float(low) <= current_left <= float(high)

        if rule.operator in {ConditionOperator.CROSS_ABOVE, ConditionOperator.CROSS_BELOW}:
            right_metric = str(rule.right)
            current_right = self._resolve_metric(right_metric, market.metrics)
            prev_left = self._resolve_metric(rule.left, market.previous_metrics)
            prev_right = self._resolve_metric(right_metric, market.previous_metrics)
            if rule.operator == ConditionOperator.CROSS_ABOVE:
                return prev_left <= prev_right and current_left > current_right
            return prev_left >= prev_right and current_left < current_right

        raise ValueError(f"Unsupported operator: {rule.operator}")

    @staticmethod
    def _resolve_metric(name: str, pool: dict[str, float]) -> float:
        if name not in pool:
            raise KeyError(f"metric '{name}' not found in market snapshot")
        return float(pool[name])

    @staticmethod
    def _compare_scalar(left: float, right: float, operator: ConditionOperator) -> bool:
        if operator == ConditionOperator.LT:
            return left < right
        if operator == ConditionOperator.LTE:
            return left <= right
        if operator == ConditionOperator.GT:
            return left > right
        if operator == ConditionOperator.GTE:
            return left >= right
        if operator == ConditionOperator.EQ:
            return left == right
        if operator == ConditionOperator.NE:
            return left != right
        raise ValueError(f"Unsupported scalar operator: {operator}")

    @staticmethod
    def _humanize(rule: Condition) -> str:
        if rule.operator == ConditionOperator.BETWEEN:
            low, high = rule.right  # type: ignore[misc]
            return f"{rule.left} between {low} and {high}"
        return f"{rule.left} {rule.operator.value} {rule.right}"
