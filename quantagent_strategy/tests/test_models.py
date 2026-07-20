from datetime import time

import pytest
from pydantic import ValidationError

from quantagent_strategy import (
    Condition,
    ConditionOperator,
    StrategySpec,
)


def test_between_condition_requires_two_values():
    with pytest.raises(ValidationError):
        Condition(left="rsi", operator=ConditionOperator.BETWEEN, right=[30])


def test_cross_condition_requires_metric_name():
    with pytest.raises(ValidationError):
        Condition(left="macd", operator=ConditionOperator.CROSS_ABOVE, right=0.0)


def test_strategy_spec_defaults_and_normalization():
    spec = StrategySpec(
        strategy_id=" Mean Reversion V1 ",
        strategy_name="Mean Reversion V1",
        entry_rules=[Condition(left="rsi", operator=ConditionOperator.LTE, right=30)],
    )
    assert spec.strategy_id == "mean_reversion_v1"
    assert spec.backtest.walk_forward.in_sample_months == 12
    assert spec.reporting.daily_email_time == time(8, 0)
