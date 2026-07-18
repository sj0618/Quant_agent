from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_graph.llm import LLMClient, LLMClientError, create_llm_client
from ai_graph.llm.mock import (
    BOLLINGER_CANDIDATES,
    BREAKOUT_VOLUME_CANDIDATES,
    MOCK_BACKTEST_CODE_CANDIDATES,
    MockBacktestCodeLLM,
    RELATIVE_STRENGTH_CANDIDATES,
    TREND_PULLBACK_CANDIDATES,
    VALUE_QUALITY_CANDIDATES,
)
from ai_graph.llm.prompts import BacktestCodeLLMOutput, build_backtest_code_json_request
from ai_graph.nodes.position_sizing import (
    DEFAULT_MAX_POSITIONS,
    applied_max_positions,
    available_ticker_count,
    max_position_pct_from_risk_constraints,
)
from ai_graph.schemas import CodeCandidate, StrategySpec
from ai_graph.security.ast_validator import validate_backtest_code


MOCK_BACKTEST_CODE_LLM = MockBacktestCodeLLM()
SAFE_RSI_CODE = MOCK_BACKTEST_CODE_CANDIDATES[0]
CONSERVATIVE_RSI_CODE = MOCK_BACKTEST_CODE_CANDIDATES[1]
SMOOTHED_RSI_CODE = MOCK_BACKTEST_CODE_CANDIDATES[2]


MIN_GENERATED_CANDIDATES = 6
MAX_GENERATED_CANDIDATES = 12
MAX_SELF_IMPROVEMENT_CANDIDATES = 36


class FeatureMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_features: list[str] = Field(default_factory=list)
    direct_features: list[str] = Field(default_factory=list)
    proxy_features: dict[str, str] = Field(default_factory=dict)
    proxy_used: list[str] = Field(default_factory=list)


class CodeGenerationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    entry_feature: str
    exit_feature: str
    proxy_feature: str
    lookbacks: list[int] = Field(min_length=1)
    thresholds: list[float] = Field(min_length=1)
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.45
    expected_trade_frequency: str


class Loop3Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: StrategySpec
    variant: str = Field(pattern="^(A|B)$")
    trace_id: str = Field(min_length=1)
    max_positions: int = Field(default=DEFAULT_MAX_POSITIONS, gt=0)


class Loop3Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant: str
    candidates: list[CodeCandidate] = Field(min_length=MIN_GENERATED_CANDIDATES, max_length=MAX_GENERATED_CANDIDATES)
    selected_candidate: CodeCandidate
    feature_mapping: FeatureMapping
    code_plan: CodeGenerationPlan
    fallback_reasons: list[str] = Field(default_factory=list)


def generate_loop3_candidates(
    request: Loop3Request, *, llm_client: LLMClient | None = None
) -> Loop3Result:
    feature_mapping = map_strategy_features(request.strategy)
    code_plan = build_code_generation_plan(request.strategy, feature_mapping)

    client = llm_client or create_llm_client(role="BACKTEST_CODE")
    output = _generate_backtest_code_output(client, request)
    llm_candidates, ignored_legacy_count = _non_legacy_llm_candidates(
        output.candidates, request.strategy
    )
    code_candidates = _candidate_code_pool(
        llm_candidates, request.strategy, code_plan, request.max_positions
    )
    candidates = _validate_candidates(request, code_candidates)
    valid_candidates = [candidate for candidate in candidates if candidate.validation_ok]
    fallback_reasons = list(output.fallback_reasons)
    if ignored_legacy_count:
        fallback_reasons.append(
            f"ignored {ignored_legacy_count} legacy template candidates from LLM output"
        )
    if any(candidate.violations for candidate in candidates):
        fallback_reasons.extend(_candidate_violation_summaries(candidates))
    if not valid_candidates:
        fallback_reasons = [
            "all generated candidates failed AST validation",
            *_candidate_violation_summaries(candidates),
            *fallback_reasons,
        ]
        candidates = _validate_candidates(
            request,
            _deterministic_fallback_candidates(request.strategy, code_plan, request.max_positions),
        )
        valid_candidates = [candidate for candidate in candidates if candidate.validation_ok]
        if not valid_candidates:
            raise ValueError("safe fallback candidates failed AST validation")
    selected = valid_candidates[0]
    return Loop3Result(
        variant=request.variant,
        candidates=candidates,
        selected_candidate=selected,
        feature_mapping=feature_mapping,
        code_plan=code_plan,
        fallback_reasons=fallback_reasons,
    )


def _validate_candidates(request: Loop3Request, code_candidates: list[str]) -> list[CodeCandidate]:
    candidates: list[CodeCandidate] = []
    for index, code in enumerate(code_candidates[:MAX_GENERATED_CANDIDATES], start=1):
        validation = validate_backtest_code(code)
        candidates.append(
            CodeCandidate(
                candidate_id=f"{request.variant}{index}",
                variant=request.variant,  # type: ignore[arg-type]
                code=code,
                validation_ok=validation.ok,
                violations=[violation.message for violation in validation.violations],
                metrics=None,
            )
        )
    if len(candidates) < MIN_GENERATED_CANDIDATES:
        raise ValueError(f"Loop3 requires at least {MIN_GENERATED_CANDIDATES} candidates")
    return candidates


def _candidate_violation_summaries(candidates: list[CodeCandidate]) -> list[str]:
    return [
        f"{candidate.candidate_id}: {'; '.join(candidate.violations)}"
        for candidate in candidates
        if candidate.violations
    ]


def _strategy_template_candidates(strategy: StrategySpec) -> list[str] | None:
    strategy_id = strategy.strategy_id
    if strategy_id.startswith("rsi_rebound"):
        return list(MOCK_BACKTEST_CODE_CANDIDATES)
    if strategy_id.startswith("breakout_volume_momentum"):
        return list(BREAKOUT_VOLUME_CANDIDATES)
    if strategy_id.startswith("bollinger"):
        return list(BOLLINGER_CANDIDATES)
    if strategy_id.startswith(
        (
            "value_quality",
            "reasonable_growth",
            "quality_growth",
            "growth_momentum",
            "asset_value_catalyst",
            "margin_improvement",
            "margin_inventory_quality",
            "operating_profit_pullback",
        )
    ):
        return list(VALUE_QUALITY_CANDIDATES)
    if strategy_id.startswith(
        (
            "pullback",
            "breakout_pullback",
            "midterm_pullback",
            "trend_rsi_volume_pullback",
            "dividend_defensive",
            "low_vol_defensive",
            "rate_sensitive_income",
            "fcf_recovery",
        )
    ):
        return list(TREND_PULLBACK_CANDIDATES)
    if strategy_id.startswith(
        (
            "relative_strength",
            "earnings",
            "oversold_quality",
            "fx_exporter_revision",
        )
    ):
        return list(RELATIVE_STRENGTH_CANDIDATES)
    if strategy_id.startswith(
        ("flow_accumulation", "short_covering_proxy", "gap_hold_momentum", "breakout_setup")
    ):
        return list(BREAKOUT_VOLUME_CANDIDATES)
    return None


def backtest_code_node(state: dict) -> dict:
    strategy_a = StrategySpec.model_validate(state["strategy_spec"])
    price_rows = state.get("price_rows") or []
    max_positions = applied_max_positions(
        max_position_pct_from_risk_constraints(strategy_a.risk_constraints),
        available_ticker_count(price_rows) if price_rows else None,
    )
    result_a = generate_loop3_candidates(
        Loop3Request(
            strategy=strategy_a,
            variant="A",
            trace_id=state["trace_id"],
            max_positions=max_positions,
        )
    )
    candidates = result_a.candidates
    selected = next(candidate for candidate in candidates if candidate.validation_ok)
    return {
        "backtest_code": {
            "candidates": [candidate.model_dump() for candidate in candidates],
            "selected_candidate": selected.model_dump(),
            "feature_mapping": result_a.feature_mapping.model_dump(),
            "code_plan": result_a.code_plan.model_dump(),
            "fallback_reasons": result_a.fallback_reasons,
        }
    }


def _generate_backtest_code_output(
    client: LLMClient, request: Loop3Request
) -> BacktestCodeLLMOutput:
    try:
        llm_request = build_backtest_code_json_request(request.strategy, request.variant)
        raw_output = client.generate_json(llm_request)
        return BacktestCodeLLMOutput.model_validate(raw_output)
    except (LLMClientError, ValidationError) as exc:
        return BacktestCodeLLMOutput.model_construct(
            candidates=[],
            fallback_reasons=[f"{type(exc).__name__}: {exc}"],
        )


def map_strategy_features(strategy: StrategySpec) -> FeatureMapping:
    requested = [condition.left for condition in strategy.entry_conditions + strategy.exit_conditions]
    direct_vocab = {
        "rsi",
        "relative_strength_20d",
        "relative_strength_60d",
        "close_above_sma_20",
        "close_above_sma_50",
        "close_above_sma_200",
        "close_below_sma_20",
        "close_below_sma_50",
        "close_below_sma_200",
        "volume_ratio_20",
    }
    proxy_map = {
        "per_percentile": "discount_to_120d_high",
        "per_vs_industry": "discount_to_120d_high",
        "pbr": "discount_to_120d_high",
        "roe": "trend_quality_proxy",
        "debt_ratio": "low_volatility_proxy",
        "sales_growth": "relative_strength_20d",
        "eps_revision_3m": "breakout_momentum_proxy",
        "dividend_yield": "low_volatility_proxy",
        "dividend_cut_5y": "trend_quality_proxy",
        "institutional_foreign_net_buy_5d": "volume_accumulation_proxy",
    }
    direct: list[str] = []
    proxies: dict[str, str] = {}
    proxy_used: list[str] = []
    for feature in requested:
        normalized = feature.lower()
        if normalized in direct_vocab:
            direct.append(normalized)
        else:
            proxy = proxy_map.get(normalized, "technical_proxy")
            proxies[feature] = proxy
            proxy_used.append(f"{feature} -> {proxy}")
    return FeatureMapping(
        requested_features=requested,
        direct_features=sorted(set(direct)),
        proxy_features=proxies,
        proxy_used=proxy_used,
    )


def build_code_generation_plan(
    strategy: StrategySpec, feature_mapping: FeatureMapping
) -> CodeGenerationPlan:
    strategy_id = strategy.strategy_id
    requested_text = " ".join(feature_mapping.requested_features + strategy.indicators).lower()
    if "rsi" in requested_text:
        return CodeGenerationPlan(
            strategy_id=strategy_id,
            entry_feature="rsi_rebound",
            exit_feature="rsi_overbought_or_stop",
            proxy_feature="rsi",
            lookbacks=[5, 10, 14, 20, 30, 40],
            thresholds=[30, 35, 40, 45, 50, 55],
            expected_trade_frequency="medium",
        )
    if "volume" in requested_text or "신고가" in " ".join(strategy.assumptions):
        return CodeGenerationPlan(
            strategy_id=strategy_id,
            entry_feature="breakout_volume",
            exit_feature="sma_or_stop",
            proxy_feature="volume_accumulation_proxy",
            lookbacks=[10, 15, 20, 30, 40, 60],
            thresholds=[1.1, 1.2, 1.35, 1.5, 1.75, 2.0],
            expected_trade_frequency="medium",
        )
    if "dividend" in strategy_id or "low_vol" in strategy_id:
        return CodeGenerationPlan(
            strategy_id=strategy_id,
            entry_feature="low_volatility_pullback",
            exit_feature="sma_or_stop",
            proxy_feature="low_volatility_proxy",
            lookbacks=[10, 15, 20, 30, 45, 60],
            thresholds=[0.02, 0.03, 0.04, 0.05, 0.07, 0.1],
            expected_trade_frequency="low",
        )
    if "value" in strategy_id or "growth" in strategy_id or "earnings" in strategy_id:
        return CodeGenerationPlan(
            strategy_id=strategy_id,
            entry_feature="quality_momentum_proxy",
            exit_feature="momentum_decay_or_stop",
            proxy_feature="trend_quality_proxy",
            lookbacks=[10, 15, 20, 30, 45, 60],
            thresholds=[0.0, 0.01, 0.02, 0.03, 0.05, 0.08],
            expected_trade_frequency="medium",
        )
    return CodeGenerationPlan(
        strategy_id=strategy_id,
        entry_feature="adaptive_trend",
        exit_feature="sma_or_stop",
        proxy_feature="technical_proxy",
        lookbacks=[10, 15, 20, 30, 45, 60],
        thresholds=[0.0, 0.01, 0.02, 0.03, 0.05, 0.08],
        expected_trade_frequency="medium",
    )


def _candidate_code_pool(
    llm_candidates: list[str],
    strategy: StrategySpec,
    plan: CodeGenerationPlan,
    max_positions: int = DEFAULT_MAX_POSITIONS,
) -> list[str]:
    pool: list[str] = []
    for code in llm_candidates:
        if code not in pool:
            pool.append(code)
    for code in _generated_strategy_candidates(strategy, plan, max_positions):
        if code not in pool:
            pool.append(code)
    if len(pool) < MIN_GENERATED_CANDIDATES:
        for code in _deterministic_fallback_candidates(strategy, plan, max_positions):
            if code not in pool:
                pool.append(code)
    return pool[:MAX_GENERATED_CANDIDATES]


def _non_legacy_llm_candidates(
    candidates: list[str], strategy: StrategySpec
) -> tuple[list[str], int]:
    legacy_templates = set(_strategy_template_candidates(strategy) or [])
    filtered = [candidate for candidate in candidates if candidate not in legacy_templates]
    return filtered, len(candidates) - len(filtered)


def _deterministic_fallback_candidates(
    strategy: StrategySpec,
    plan: CodeGenerationPlan,
    max_positions: int = DEFAULT_MAX_POSITIONS,
) -> list[str]:
    templates = _strategy_template_candidates(strategy) or MOCK_BACKTEST_CODE_LLM.generate_backtest_candidates(strategy, "A")
    generated = _generated_strategy_candidates(strategy, plan, max_positions)
    return (generated + templates)[:MAX_GENERATED_CANDIDATES]


def _generated_strategy_candidates(
    strategy: StrategySpec,
    plan: CodeGenerationPlan,
    max_positions: int = DEFAULT_MAX_POSITIONS,
) -> list[str]:
    codes: list[str] = []
    profiles = _candidate_profiles(plan)
    lookbacks = [*plan.lookbacks, 75, 100, 125, 150, 200, 252]
    thresholds = [*plan.thresholds, 0.12, 0.18, 0.25, 0.35, 0.5, 0.75]
    for index, profile in enumerate(profiles[:MAX_GENERATED_CANDIDATES]):
        lookback = lookbacks[index % len(lookbacks)]
        threshold = thresholds[index % len(thresholds)]
        stop_loss = float(strategy.risk_constraints.get("stop_loss_pct", plan.stop_loss_pct))
        take_profit = float(strategy.risk_constraints.get("take_profit_pct", plan.take_profit_pct))
        codes.append(
            _render_adaptive_signal_code(
                strategy_id=strategy.strategy_id,
                plan=plan,
                profile=profile,
                lookback=lookback,
                threshold=threshold,
                stop_loss=stop_loss,
                take_profit=take_profit,
                max_positions=max_positions,
            )
        )
    return codes


def _candidate_profiles(plan: CodeGenerationPlan) -> list[str]:
    base = [
        "long_regime_momentum",
        "quality_trend_hold",
        "volatility_breakout_hold",
        "rolling_sharpe_momentum",
        "dual_sma_trend",
        "low_vol_momentum",
        "breakout_volume",
        "rsi_trend_rebound",
        "return_to_volatility",
        "cash_preserving_trend",
    ]
    if plan.entry_feature == "rsi_rebound":
        return [
            "rsi_trend_rebound",
            "mean_reversion_band",
            "quality_trend_hold",
            "long_regime_momentum",
            "rolling_sharpe_momentum",
            "dual_sma_trend",
            "low_vol_momentum",
            "return_to_volatility",
            "volatility_breakout_hold",
            "cash_preserving_trend",
            "breakout_volume",
            "adaptive_market_filter",
        ]
    if plan.entry_feature == "breakout_volume":
        return [
            "breakout_volume",
            "volatility_breakout_hold",
            "long_regime_momentum",
            "quality_trend_hold",
            "rolling_sharpe_momentum",
            "dual_sma_trend",
            "return_to_volatility",
            "low_vol_momentum",
            "cash_preserving_trend",
            "pullback_recovery",
            "adaptive_market_filter",
            "rsi_trend_rebound",
            "mean_reversion_band",
        ]
    if plan.entry_feature == "low_volatility_pullback":
        return [
            "quality_trend_hold",
            "long_regime_momentum",
            "low_vol_momentum",
            "cash_preserving_trend",
            "rolling_sharpe_momentum",
            "dual_sma_trend",
            "volatility_breakout_hold",
            "return_to_volatility",
            "adaptive_market_filter",
            "mean_reversion_band",
            "rsi_trend_rebound",
            "breakout_volume",
        ]
    return base


def _render_adaptive_signal_code(
    *,
    strategy_id: str,
    plan: CodeGenerationPlan,
    profile: str,
    lookback: int,
    threshold: float,
    stop_loss: float,
    take_profit: float,
    max_positions: int = DEFAULT_MAX_POSITIONS,
) -> str:
    mode = plan.entry_feature
    return f'''def build_signals(prices):
    signals = []
    rows_by_date = {{}}
    for row in sorted(prices, key=lambda item: (item["date"], item.get("ticker", "000000"))):
        rows_by_date.setdefault(row["date"], []).append(row)
    histories = {{}}
    states = {{}}
    lookback = {int(lookback)}
    threshold = {float(threshold)!r}
    stop_loss = {float(stop_loss)!r}
    take_profit = {float(take_profit)!r}
    mode = {mode!r}
    profile = {profile!r}
    strategy_id = {strategy_id!r}
    max_positions = {int(max_positions)}
    for current_date in sorted(rows_by_date):
        evaluations = []
        for row in rows_by_date[current_date]:
            ticker = row.get("ticker", "000000")
            close = float(row["close"])
            volume = float(row.get("volume", 0))
            rsi = float(row.get("rsi", row.get("RSI_14", 50)))
            history = histories.setdefault(ticker, {{"closes": [], "volumes": []}})
            state = states.setdefault(
                ticker,
                {{"in_position": False, "entry_price": 0.0, "days": 0, "peak": 0.0}},
            )
            closes = history["closes"]
            volumes = history["volumes"]
            window = min(lookback, len(closes))
            buy = False
            sell = False
            score = -999.0
            if window:
                recent = closes[-window:]
                average = sum(recent) / window
                short_window = min(max(3, window // 4), len(closes))
                medium_window = min(max(5, window // 2), len(closes))
                short_average = sum(closes[-short_window:]) / short_window
                medium_average = sum(closes[-medium_window:]) / medium_window
                high = max(recent)
                low = min(recent)
                previous = closes[-1]
                trend = close / recent[0] - 1 if recent[0] else 0
                medium_return = close / closes[-medium_window] - 1 if closes[-medium_window] else 0
                pullback = high > 0 and (high - close) / high
                volatility = (high - low) / average if average else 0
                long_window = min(max(60, window), len(closes))
                long_recent = closes[-long_window:]
                long_average = sum(long_recent) / long_window
                long_high = max(long_recent)
                long_return = close / long_recent[0] - 1 if long_recent[0] else 0
                long_drawdown = long_high > 0 and (long_high - close) / long_high
                returns = []
                for before, after in zip(recent[:-1], recent[1:]):
                    if before:
                        returns.append(after / before - 1)
                mean_return = sum(returns) / len(returns) if returns else 0
                variance = sum((item - mean_return) * (item - mean_return) for item in returns) / len(returns) if returns else 0
                std_return = variance ** 0.5
                rolling_sharpe = (mean_return / std_return) if std_return > 0 else 0
                return_to_volatility = trend / volatility if volatility > 0 else 0
                avg_volume = sum(volumes[-window:]) / window if volumes[-window:] else 0
                volume_ratio = volume / avg_volume if avg_volume > 0 else 1
                trailing_stop = state["peak"] > 0 and close < state["peak"] * 0.93
                score = rolling_sharpe + medium_return * 4 + long_return * 2 - volatility
                if profile == "long_regime_momentum":
                    score = rolling_sharpe + long_return * 3 + medium_return * 2 - volatility
                    buy = close >= long_average and medium_average >= long_average * 0.98 and long_return > 0
                    sell = state["in_position"] and (close < long_average * 0.97 or long_drawdown > 0.18)
                elif profile == "quality_trend_hold":
                    score = medium_return * 3 + long_return * 2 + rolling_sharpe * 0.5 - volatility * 0.5
                    buy = close >= medium_average >= long_average * 0.97 and medium_return >= -0.02 and volatility <= 0.28
                    sell = state["in_position"] and (close < medium_average * 0.96 or medium_return < -0.08)
                elif profile == "volatility_breakout_hold":
                    score = (close / long_high - 0.96) * 6 + medium_return * 3 + volume_ratio * 0.1 - volatility
                    buy = close >= long_high * 0.96 and volume_ratio >= 0.85 and volatility <= 0.32 and medium_return >= 0
                    sell = state["in_position"] and (close < medium_average * 0.95 or long_drawdown > 0.2)
                elif profile == "rolling_sharpe_momentum":
                    score = rolling_sharpe + trend * 2 - volatility
                    buy = rolling_sharpe >= max(0.03, threshold / 10) and close >= medium_average and trend > 0
                    sell = state["in_position"] and (rolling_sharpe <= 0 or close < medium_average)
                elif profile == "dual_sma_trend":
                    score = medium_return * 3 + (short_average / medium_average - 1) * 8 if medium_average else 0
                    buy = short_average > medium_average > average * 0.98 and close >= short_average
                    sell = state["in_position"] and (short_average < medium_average or close < average)
                elif profile == "low_vol_momentum":
                    score = trend * 3 + medium_return * 2 - volatility * 1.5
                    buy = trend >= max(0.04, threshold / 2) and medium_return >= 0 and volatility <= 0.28 and close >= medium_average
                    sell = state["in_position"] and (close < medium_average * 0.96 or medium_return < -0.06 or long_drawdown > 0.22)
                elif profile == "breakout_volume":
                    score = (close / high - 0.99) * 10 + volume_ratio * 0.2 + trend * 2
                    buy = close >= high * 0.995 and volume_ratio >= max(1.05, threshold) and trend >= 0
                    sell = state["in_position"] and close < short_average
                elif profile == "rsi_trend_rebound":
                    score = medium_return * 3 + (55 - abs(rsi - 45)) / 50 - volatility
                    buy = close >= medium_average and trend >= 0 and 35 <= rsi <= 62 and close >= previous
                    sell = state["in_position"] and (rsi >= 72 or close < medium_average)
                elif profile == "mean_reversion_band":
                    score = pullback * 2 + (50 - rsi) / 50 - volatility
                    buy = close <= average * (1 - min(0.12, max(0.015, threshold))) and rsi <= 45
                    sell = state["in_position"] and (close >= medium_average or rsi >= 60)
                elif profile == "return_to_volatility":
                    score = return_to_volatility + medium_return * 2
                    buy = return_to_volatility >= max(0.4, threshold * 4) and close >= medium_average
                    sell = state["in_position"] and (return_to_volatility <= 0 or close < medium_average)
                elif profile == "cash_preserving_trend":
                    score = rolling_sharpe + trend * 2 - volatility * 2
                    buy = trend >= max(0.03, threshold) and rolling_sharpe > 0.05 and volatility <= 0.3
                    sell = state["in_position"] and (trend < 0.01 or rolling_sharpe < 0)
                else:
                    score = trend * 2 + medium_return - volatility
                    buy = trend >= threshold and close >= average and close >= previous
                    sell = state["in_position"] and close < average
                if state["in_position"] and state["entry_price"] > 0:
                    pnl = close / state["entry_price"] - 1
                    sell = sell or pnl <= -stop_loss or pnl >= take_profit or trailing_stop
            evaluations.append({{"ticker": ticker, "row": row, "close": close, "volume": volume, "buy": buy, "sell": sell, "score": score, "state": state, "history": history}})
        open_positions = sum(1 for state in states.values() if state["in_position"])
        open_slots = max(0, max_positions - open_positions)
        ranked_buys = [item for item in evaluations if item["buy"] and not item["state"]["in_position"]]
        ranked_buys = sorted(ranked_buys, key=lambda item: (item["score"], item["ticker"]), reverse=True)[:open_slots]
        selected_buys = {{}}
        for item in ranked_buys:
            selected_buys[item["ticker"]] = True
        for item in evaluations:
            ticker = item["ticker"]
            row = item["row"]
            close = item["close"]
            state = item["state"]
            if item["sell"] and state["in_position"]:
                action = "SELL"
                state["in_position"] = False
                state["entry_price"] = 0.0
                state["days"] = 0
                state["peak"] = 0.0
            elif selected_buys.get(ticker, False):
                action = "BUY"
                state["in_position"] = True
                state["entry_price"] = close
                state["days"] = 0
                state["peak"] = close
            else:
                action = "HOLD"
                if state["in_position"]:
                    state["days"] += 1
                    state["peak"] = max(state["peak"], close)
            signals.append({{"date": row["date"], "ticker": ticker, "action": action, "price": close}})
            item["history"]["closes"].append(close)
            item["history"]["volumes"].append(item["volume"])
    return signals
'''


def generate_self_improvement_candidates(
    strategy: StrategySpec,
    code_plan: dict[str, object],
    *,
    start_index: int,
    iteration: int,
    max_positions: int = DEFAULT_MAX_POSITIONS,
) -> list[CodeCandidate]:
    plan = CodeGenerationPlan.model_validate(code_plan)
    adjusted_plans = [
        plan.model_copy(
            update={
                "thresholds": [
                    _adjust_threshold(float(value), plan.entry_feature, iteration)
                    for value in plan.thresholds
                ],
                "lookbacks": [max(3, int(value) - iteration * 2) for value in plan.lookbacks],
            }
        ),
        plan.model_copy(
            update={
                "thresholds": [
                    _selective_threshold(float(value), plan.entry_feature, iteration)
                    for value in plan.thresholds
                ],
                "lookbacks": [min(252, int(value) + iteration * 10) for value in plan.lookbacks],
            }
        ),
    ]
    candidates: list[CodeCandidate] = []
    seen: set[str] = set()
    for adjusted in adjusted_plans:
        for code in _generated_strategy_candidates(strategy, adjusted, max_positions)[:6]:
            if code in seen:
                continue
            seen.add(code)
            validation = validate_backtest_code(code)
            candidates.append(
                CodeCandidate(
                    candidate_id=f"A{start_index + len(candidates)}",
                    variant="A",
                    code=code,
                    validation_ok=validation.ok,
                    violations=[violation.message for violation in validation.violations],
                    metrics=None,
                )
            )
    for code in _self_improvement_grid_codes(strategy, plan, iteration, max_positions):
        if len(candidates) >= MAX_SELF_IMPROVEMENT_CANDIDATES:
            break
        if code in seen:
            continue
        seen.add(code)
        validation = validate_backtest_code(code)
        candidates.append(
            CodeCandidate(
                candidate_id=f"A{start_index + len(candidates)}",
                variant="A",
                code=code,
                validation_ok=validation.ok,
                violations=[violation.message for violation in validation.violations],
                metrics=None,
            )
        )
    return candidates


def _adjust_threshold(value: float, entry_feature: str, iteration: int) -> float:
    if entry_feature == "breakout_volume":
        return max(1.02, value - 0.1 * iteration)
    if entry_feature == "rsi_rebound":
        return min(60.0, value + 5 * iteration)
    if entry_feature == "low_volatility_pullback":
        return min(0.12, value + 0.01 * iteration)
    return max(-0.02, value - 0.01 * iteration)


def _selective_threshold(value: float, entry_feature: str, iteration: int) -> float:
    if entry_feature == "breakout_volume":
        return value + 0.12 * iteration
    if entry_feature == "rsi_rebound":
        return max(25.0, value - 3 * iteration)
    if entry_feature == "low_volatility_pullback":
        return max(0.015, value - 0.005 * iteration)
    return value + 0.03 * iteration


def _self_improvement_grid_codes(
    strategy: StrategySpec,
    plan: CodeGenerationPlan,
    iteration: int,
    max_positions: int = DEFAULT_MAX_POSITIONS,
) -> list[str]:
    profiles = [
        "volatility_breakout_hold",
        "low_vol_momentum",
        "cash_preserving_trend",
        "return_to_volatility",
        "quality_trend_hold",
        "long_regime_momentum",
    ]
    lookbacks = [30, 45, 60, 90, 120, 180, 240]
    thresholds = [0.02, 0.05, 0.08, 0.12, 0.18, 0.25, 0.35]
    if plan.entry_feature == "rsi_rebound":
        profiles = [
            "cash_preserving_trend",
            "rsi_trend_rebound",
            "low_vol_momentum",
            "quality_trend_hold",
            "return_to_volatility",
            "volatility_breakout_hold",
        ]
    if plan.entry_feature == "breakout_volume":
        profiles = [
            "volatility_breakout_hold",
            "breakout_volume",
            "low_vol_momentum",
            "cash_preserving_trend",
            "return_to_volatility",
            "quality_trend_hold",
        ]
    offset = max(0, iteration - 1) * 2
    codes: list[str] = []
    for index, profile in enumerate(profiles):
        for lookback in lookbacks[offset : offset + 4]:
            threshold = thresholds[(index + lookback + iteration) % len(thresholds)]
            codes.append(
                _render_adaptive_signal_code(
                    strategy_id=strategy.strategy_id,
                    plan=plan,
                    profile=profile,
                    lookback=lookback,
                    threshold=threshold,
                    stop_loss=float(
                        strategy.risk_constraints.get(
                            "stop_loss_pct", plan.stop_loss_pct
                        )
                    ),
                    take_profit=float(
                        strategy.risk_constraints.get(
                            "take_profit_pct", plan.take_profit_pct
                        )
                    ),
                    max_positions=max_positions,
                )
            )
    return codes
