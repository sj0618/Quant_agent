from __future__ import annotations

from .models import (
    BacktestPlan,
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


METRIC_ALIASES = {
    "rsi": "rsi_14",
    "RSI": "rsi_14",
    "MA5": "ma_5",
    "MA_5": "ma_5",
    "5ma": "ma_5",
    "ma5": "ma_5",
    "MA20": "ma_20",
    "MA_20": "ma_20",
    "ma20": "ma_20",
    "MA60": "ma_60",
    "MA_60": "ma_60",
    "ma60": "ma_60",
    "signal": "macd_signal",
    "price": "close",
}


class QuantStrategy:
    """최종 StrategySpec을 엔진에서 사용하기 위한 canonical strategy runtime.

    기술적 신호는 entry/exit rules로 판단합니다.
    """

    def __init__(self, spec: StrategySpec):
        self.spec = spec

    def compile_backtest_plan(self) -> BacktestPlan:
        notes = [
            "template compile only",
            "new external libraries are forbidden",
            "network calls are forbidden during code execution",
            "all condition matches are evaluated without score-based candidate filtering",
        ]

        return BacktestPlan(
            strategy_id=self.spec.strategy_id,
            strategy_name=self.spec.strategy_name,
            market=self.spec.market,
            asset_type=self.spec.asset_type,
            allowed_modules=ALLOWED_BACKTEST_MODULES,
            execution_timing=self.spec.backtest.execution_timing,
            use_adjusted_price=self.spec.backtest.use_adjusted_price,
            walk_forward=self.spec.backtest.walk_forward,
            cost_model=self.spec.backtest.cost_model,
            notes=notes,
        )

    def generate_signal(
        self,
        market: MarketSnapshot,
        has_position: bool = False,
    ) -> SignalDecision:
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
            )

        if not has_position and entry_hits:
            return SignalDecision(
                strategy_id=self.spec.strategy_id,
                ticker=market.ticker,
                action=SignalAction.BUY,
                confidence=1.0,
                reasons=["entry condition matched"],
                matching_entry_rules=entry_hits,
            )

        return SignalDecision(
            strategy_id=self.spec.strategy_id,
            ticker=market.ticker,
            action=SignalAction.HOLD if has_position else SignalAction.WATCH,
            confidence=1.0,
            reasons=["no actionable rule matched"],
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
            right = self._resolve_right(rule.right, market.metrics)
            return self._compare_scalar(current_left, right, rule.operator)

        if rule.operator == ConditionOperator.BETWEEN:
            low, high = rule.right  # type: ignore[misc]
            return float(low) <= current_left <= float(high)

        if rule.operator in {ConditionOperator.CROSS_ABOVE, ConditionOperator.CROSS_BELOW}:
            if not market.previous_metrics:
                return False
            current_right = self._resolve_right(rule.right, market.metrics)
            prev_left = self._resolve_metric(rule.left, market.previous_metrics)
            prev_right = self._resolve_right(rule.right, market.previous_metrics)
            if rule.operator == ConditionOperator.CROSS_ABOVE:
                return prev_left <= prev_right and current_left > current_right
            return prev_left >= prev_right and current_left < current_right

        raise ValueError(f"Unsupported operator: {rule.operator}")

    @staticmethod
    def _resolve_metric(name: str, pool: dict[str, float]) -> float:
        normalized_name = METRIC_ALIASES.get(name, name)
        if normalized_name in pool:
            return float(pool[normalized_name])
        if name not in pool:
            raise KeyError(f"metric '{name}' not found in market snapshot")
        return float(pool[name])

    def _resolve_right(self, right, pool: dict[str, float]) -> float:
        if isinstance(right, (int, float)):
            return float(right)
        if isinstance(right, str):
            return self._resolve_metric(right, pool)
        raise ValueError(f"right side cannot be resolved as scalar: {right}")

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
