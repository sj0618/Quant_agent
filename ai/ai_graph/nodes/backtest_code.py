from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_graph.llm import LLMClient, LLMClientError, create_llm_client, is_live_llm_provider
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
from ai_graph.progress import activity_role, report_activity
from ai_graph.nodes.position_sizing import (
    DEFAULT_MAX_POSITIONS,
    applied_max_positions,
    available_ticker_count,
    max_position_pct_from_risk_constraints,
    requested_max_positions,
)
from ai_graph.schemas import (
    CandidateParameters,
    CodeCandidate,
    Condition,
    StrategyIR,
    StrategySpec,
    StructuredProfile,
)
from ai_graph.nodes.condition_compiler import (
    CompiledConditions,
    compile_conditions,
    compile_score_expression,
    indicator_row_keys,
)
from ai_graph.quant_strategy import (
    AUTOMATIC_TOURNAMENT_PROFILES,
    automatic_candidate_lookbacks,
    automatic_candidate_profiles,
)
from ai_graph.security.ast_validator import validate_backtest_code
from ai_graph.strategy_blueprint_catalog import (
    CATALOG_VERSION,
    StrategyBlueprintTemplate,
    catalog_selection_terms,
    customize_blueprint_parameters,
    select_strategy_blueprints,
    strategy_blueprint_catalog,
    strategy_blueprint_catalog_fingerprint,
)


MOCK_BACKTEST_CODE_LLM = MockBacktestCodeLLM()
SAFE_RSI_CODE = MOCK_BACKTEST_CODE_CANDIDATES[0]
CONSERVATIVE_RSI_CODE = MOCK_BACKTEST_CODE_CANDIDATES[1]
SMOOTHED_RSI_CODE = MOCK_BACKTEST_CODE_CANDIDATES[2]


# Kept small on purpose. Twelve threshold variants over 200 names × 10 years was slow
# (interpreted Python per candidate) and, worse, invited overfitting - picking the best
# of many variants fitted to the same history is a multiple-comparisons trap. The
# compiled condition candidate is the strategy's actual rule; a couple of profile
# variants around it are enough to check robustness.
MIN_GENERATED_CANDIDATES = 3
MAX_GENERATED_CANDIDATES = 3
MAX_SELF_IMPROVEMENT_CANDIDATES = 6
MAX_VALIDATION_FEEDBACK_ITEMS = 20
MAX_VALIDATION_FEEDBACK_CHARS = 4_000
TRUNCATED_VALIDATION_FEEDBACK = "Additional validation failures omitted."


class FeatureMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_features: list[str] = Field(default_factory=list)
    direct_features: list[str] = Field(default_factory=list)
    proxy_features: dict[str, str] = Field(default_factory=dict)
    proxy_used: list[str] = Field(default_factory=list)


class GeneratedStrategyBlueprint(BaseModel):
    """A strategy created before returns are inspected and later sent to backtest."""

    model_config = ConfigDict(extra="forbid")

    blueprint_id: str = Field(min_length=1)
    profile: StructuredProfile
    title: str = Field(min_length=1)
    catalog_version: str | None = None
    catalog_family: str | None = None
    preset_id: str | None = None
    plain_explanation: str | None = None
    formula: str = Field(min_length=1)
    derivation: str = Field(min_length=1)
    why_used: str | None = None
    entry_conditions: list[Condition] = Field(min_length=1)
    exit_conditions: list[Condition] = Field(min_length=1)
    ranking_metric: str = Field(min_length=1)
    ranking_direction: Literal["desc", "asc"] = "desc"
    execution_mode: Literal["event_driven", "scheduled_rotation"] = "event_driven"
    execution_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    indicator_explanations: list[dict[str, object]] = Field(min_length=1)
    why_generated: str = Field(min_length=1)
    lookback: int = Field(ge=3, le=252)
    threshold: float = Field(default=0.0, ge=-1.0, le=100.0)
    max_positions: int = Field(gt=0, le=1000)
    rebalance_interval_days: int = Field(ge=5, le=63)
    stop_loss_pct: float = Field(gt=0.0, le=1.0)
    take_profit_pct: float = Field(default=10.0, gt=0.0, le=10.0)
    trailing_stop_pct: float = Field(gt=0.0, le=0.75)
    matched_terms: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    implementation_notes: str | None = None
    parameter_schema: dict[str, dict[str, object]] = Field(default_factory=dict)


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
    candidate_profiles: list[StructuredProfile] = Field(default_factory=list)
    customization_style: Literal["aggressive", "balanced", "defensive"] = "balanced"
    investment_horizon: Literal["short", "medium", "long"] = "medium"
    rebalance_interval_days: int = Field(default=21, ge=5, le=63)
    trailing_stop_pct: float = Field(default=0.25, gt=0.0, le=0.75)
    medium_momentum_weight: float = Field(default=0.60, ge=0.0, le=1.0)
    benchmark_objective: bool = False
    customization_summary: str | None = None
    generated_strategies: list[GeneratedStrategyBlueprint] = Field(default_factory=list)
    catalog_version: str | None = None
    catalog_size: int = Field(default=0, ge=0)
    catalog_fingerprint: str | None = None


class Loop3Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: StrategySpec
    variant: str = Field(pattern="^(A|B)$")
    trace_id: str = Field(min_length=1)
    max_positions: int = Field(default=DEFAULT_MAX_POSITIONS, gt=0)
    server_only: bool = False


class Loop3Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant: str
    candidates: list[CodeCandidate] = Field(
        min_length=MIN_GENERATED_CANDIDATES, max_length=MAX_GENERATED_CANDIDATES
    )
    selected_candidate: CodeCandidate
    feature_mapping: FeatureMapping
    code_plan: CodeGenerationPlan
    strategy_ir: StrategyIR
    fallback_reasons: list[str] = Field(default_factory=list)


def generate_loop3_candidates(
    request: Loop3Request, *, llm_client: LLMClient | None = None
) -> Loop3Result:
    feature_mapping = map_strategy_features(request.strategy)
    code_plan = build_code_generation_plan(request.strategy, feature_mapping)
    if request.server_only:
        output = BacktestCodeLLMOutput.model_construct(
            strategy_ir=_normalized_strategy_ir(None, request.strategy, code_plan),
            candidates=_default_parameter_sets(
                request.strategy,
                code_plan,
                request.max_positions,
            ),
            fallback_code=[],
            fallback_reasons=[],
        )
    else:
        client = llm_client or create_llm_client(role="BACKTEST_CODE")
        output = _generate_backtest_code_output(client, request)
    strategy_ir = _normalized_strategy_ir(output.strategy_ir, request.strategy, code_plan)
    fallback_reasons = list(output.fallback_reasons)
    if len(output.fallback_code) >= MIN_GENERATED_CANDIDATES:
        candidates = _validate_candidates(request, output.fallback_code)
    else:
        parameter_sets = _normalized_parameter_sets(
            output.candidates,
            request.strategy,
            code_plan,
            request.max_positions,
        )
        candidates = _structured_candidates(
            request,
            strategy_ir,
            parameter_sets,
            generated_strategies=code_plan.generated_strategies,
        )
        invalid_fallbacks = [
            violation.message
            for code in output.fallback_code
            for violation in validate_backtest_code(code).violations
        ]
        if invalid_fallbacks:
            fallback_reasons.append(
                "LLM Python fallback rejected: " + "; ".join(invalid_fallbacks[:10])
            )
    try:
        selected = next(candidate for candidate in candidates if candidate.validation_ok)
    except StopIteration as exc:
        raise ValueError("no safe backtest candidates") from exc
    return Loop3Result(
        variant=request.variant,
        candidates=candidates,
        selected_candidate=selected,
        feature_mapping=feature_mapping,
        code_plan=code_plan,
        strategy_ir=strategy_ir,
        fallback_reasons=fallback_reasons,
    )


def _normalized_strategy_ir(
    proposed: StrategyIR | None,
    strategy: StrategySpec,
    plan: CodeGenerationPlan,
) -> StrategyIR:
    """Preserve screening semantics even when a model omits or rewrites conditions."""

    base = StrategyIR(
        strategy_id=strategy.strategy_id,
        entry_feature=plan.entry_feature,
        exit_feature=plan.exit_feature,
        proxy_feature=plan.proxy_feature,
        entry_conditions=strategy.entry_conditions,
        exit_conditions=strategy.exit_conditions,
    )
    if proposed is None or proposed.strategy_id != strategy.strategy_id:
        return base
    return proposed.model_copy(
        update={
            "entry_conditions": strategy.entry_conditions,
            "exit_conditions": strategy.exit_conditions,
        }
    )


def _normalized_parameter_sets(
    proposed: list[CandidateParameters],
    strategy: StrategySpec,
    plan: CodeGenerationPlan,
    max_positions: int,
) -> list[CandidateParameters]:
    compiled = compile_conditions(strategy.entry_conditions) is not None
    defaults = _default_parameter_sets(strategy, plan, max_positions)
    # Automatic mode has a public, cited behavior contract. Model-proposed profiles are
    # intentionally ignored: three catalog blueprints are selected from the request
    # before seeing returns, so a language-model suggestion cannot expand the search
    # after the fact.
    pool = defaults if strategy.selection_mode == "automatic" else [*proposed, *defaults]
    normalized: list[CandidateParameters] = []
    seen: set[str] = set()
    for index, item in enumerate(pool):
        profile = item.profile
        if (
            profile == "compiled_conditions"
            and not compiled
            and strategy.selection_mode != "automatic"
        ):
            profile = defaults[min(index, len(defaults) - 1)].profile
        candidate = item.model_copy(
            update={
                "profile": profile,
                "max_positions": max_positions,
                "stop_loss_pct": float(
                    strategy.risk_constraints.get("stop_loss_pct", item.stop_loss_pct)
                ),
                "take_profit_pct": float(
                    strategy.risk_constraints.get("take_profit_pct", item.take_profit_pct)
                ),
                "rebalance_interval_days": int(
                    strategy.risk_constraints.get(
                        "rebalance_interval_days", plan.rebalance_interval_days
                    )
                ),
                "trailing_stop_pct": float(
                    strategy.risk_constraints.get("trailing_stop_pct", plan.trailing_stop_pct)
                ),
                "medium_momentum_weight": float(
                    strategy.risk_constraints.get(
                        "medium_momentum_weight", plan.medium_momentum_weight
                    )
                ),
            }
        )
        identity = _parameter_identity(candidate)
        if identity in seen:
            continue
        seen.add(identity)
        normalized.append(candidate)
        if len(normalized) >= MAX_GENERATED_CANDIDATES:
            break
    if len(normalized) < MIN_GENERATED_CANDIDATES:
        raise ValueError("unable to create three distinct structured candidates")
    return normalized


def _default_parameter_sets(
    strategy: StrategySpec,
    plan: CodeGenerationPlan,
    max_positions: int,
) -> list[CandidateParameters]:
    if plan.generated_strategies:
        return [
            CandidateParameters(
                profile=blueprint.profile,
                blueprint_id=blueprint.blueprint_id,
                lookback=blueprint.lookback,
                threshold=blueprint.threshold,
                stop_loss_pct=blueprint.stop_loss_pct,
                take_profit_pct=blueprint.take_profit_pct,
                max_positions=max_positions,
                rebalance_interval_days=blueprint.rebalance_interval_days,
                trailing_stop_pct=blueprint.trailing_stop_pct,
                medium_momentum_weight=plan.medium_momentum_weight,
            )
            for blueprint in plan.generated_strategies
        ]
    profiles = _candidate_profiles(plan)
    compiled = compile_conditions(strategy.entry_conditions) is not None
    if plan.entry_feature == "performance_momentum_tournament":
        selected_profiles = profiles
    elif plan.entry_feature == "academic_momentum_trend":
        selected_profiles = ["academic_momentum_trend"] * MIN_GENERATED_CANDIDATES
    elif compiled:
        selected_profiles = ["compiled_conditions", profiles[0], profiles[1]]
    else:
        selected_profiles = profiles[:MIN_GENERATED_CANDIDATES]
    stop_loss = float(strategy.risk_constraints.get("stop_loss_pct", plan.stop_loss_pct))
    take_profit = float(strategy.risk_constraints.get("take_profit_pct", plan.take_profit_pct))
    return [
        CandidateParameters(
            profile=profile,  # type: ignore[arg-type]
            lookback=max(3, min(252, int(plan.lookbacks[index % len(plan.lookbacks)]))),
            threshold=float(plan.thresholds[index % len(plan.thresholds)]),
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            max_positions=max_positions,
            rebalance_interval_days=plan.rebalance_interval_days,
            trailing_stop_pct=plan.trailing_stop_pct,
            medium_momentum_weight=plan.medium_momentum_weight,
        )
        for index, profile in enumerate(selected_profiles)
    ]


def _structured_candidates(
    request: Loop3Request,
    strategy_ir: StrategyIR,
    parameter_sets: list[CandidateParameters],
    *,
    generated_strategies: list[GeneratedStrategyBlueprint] | None = None,
) -> list[CodeCandidate]:
    blueprint_by_id = {
        item.blueprint_id: item for item in (generated_strategies or [])
    }
    candidates: list[CodeCandidate] = []
    for index, parameters in enumerate(parameter_sets[:MAX_GENERATED_CANDIDATES], start=1):
        blueprint = blueprint_by_id.get(parameters.blueprint_id or "")
        candidate_ir = strategy_ir
        if blueprint is not None:
            candidate_ir = StrategyIR(
                strategy_id=blueprint.blueprint_id,
                entry_feature=f"catalog:{blueprint.blueprint_id}:entry",
                exit_feature=f"catalog:{blueprint.blueprint_id}:exit",
                proxy_feature="past_only_adjusted_ohlcv",
                entry_conditions=blueprint.entry_conditions,
                exit_conditions=blueprint.exit_conditions,
                ranking_metric=blueprint.ranking_metric,
                ranking_direction=blueprint.ranking_direction,
                execution_mode=blueprint.execution_mode,
            )
        code = _render_structured_reference_code(candidate_ir, parameters)
        validation = validate_backtest_code(code)
        candidates.append(
            CodeCandidate(
                candidate_id=(
                    parameters.blueprint_id
                    if blueprint is not None
                    and request.strategy.risk_constraints.get("sealed_candidate_ids")
                    else f"{request.variant}{index}"
                ),
                variant=request.variant,  # type: ignore[arg-type]
                code=code,
                validation_ok=validation.ok,
                violations=[violation.message for violation in validation.violations],
                representation="structured",
                strategy_ir=candidate_ir,
                parameters=parameters,
            )
        )
    if len(candidates) < MIN_GENERATED_CANDIDATES:
        raise ValueError(f"Loop3 requires at least {MIN_GENERATED_CANDIDATES} candidates")
    return candidates


def _parameter_identity(parameters: CandidateParameters) -> str:
    payload = json.dumps(
        parameters.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _render_structured_reference_code(
    strategy_ir: StrategyIR,
    parameters: CandidateParameters,
) -> str:
    """Audit descriptor for a structured candidate, not executable engine logic."""

    return f'''def build_signals(prices):
    """AUDIT DESCRIPTOR ONLY.

    Production execution is ai_graph.nodes.backtest_features.PreparedFeatureStore
    with the StrategyIR and CandidateParameters embedded below.  This function is
    retained only for backwards-compatible display/AST validation and must not be
    interpreted as the executed signal implementation.
    """
    signals = []
    states = {{}}
    profile = {parameters.profile!r}
    threshold = {float(parameters.threshold)!r}
    max_positions = {parameters.max_positions}
    rebalance_interval_days = {parameters.rebalance_interval_days}
    trailing_stop_pct = {float(parameters.trailing_stop_pct)!r}
    medium_momentum_weight = {float(parameters.medium_momentum_weight)!r}
    strategy_id = {strategy_ir.strategy_id!r}
    for row in prices:
        ticker = str(row.get("ticker", "000000"))
        close = float(row["close"])
        volume = float(row.get("volume", 0.0) or 0.0)
        rsi = float(row.get("rsi", row.get("RSI_14", 50.0)))
        state = states.get(ticker)
        if state is None:
            states[ticker] = {{"previous": close, "ema": close, "volume_ema": volume}}
            action = "HOLD"
        else:
            previous = state["previous"]
            ema = state["ema"] + 0.2 * (close - state["ema"])
            volume_ema = state["volume_ema"]
            volume_ok = volume_ema <= 0.0 or volume >= volume_ema
            if profile == "rsi_trend_rebound":
                buy = 35.0 <= rsi <= 62.0 and close >= previous
                sell = rsi >= 72.0 or close < ema
            elif profile == "breakout_volume":
                buy = close >= previous and volume_ok
                sell = close < ema
            else:
                buy = close >= ema and close >= previous and (close / previous - 1.0) >= threshold
                sell = close < ema
            action = "BUY" if buy else "SELL" if sell else "HOLD"
            state["previous"] = close
            state["ema"] = ema
            state["volume_ema"] = volume if volume_ema <= 0.0 else volume_ema * 0.8 + volume * 0.2
        signals.append({{"date": row["date"], "ticker": ticker, "action": action, "price": close}})
    return signals
'''


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
            server_only=True,
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
            "strategy_ir": result_a.strategy_ir.model_dump(mode="json"),
            "fallback_reasons": result_a.fallback_reasons,
        }
    }


def _generate_backtest_code_output(
    client: LLMClient,
    request: Loop3Request,
    *,
    validation_feedback: list[str] | None = None,
) -> BacktestCodeLLMOutput:
    task = "후보 코드 재생성 (검증 피드백 반영)" if validation_feedback else "후보 코드 생성"
    try:
        llm_request = build_backtest_code_json_request(
            request.strategy,
            request.variant,
            validation_feedback=validation_feedback,
        )
        with activity_role("BACKTEST_CODE"):
            report_activity("role_started", task=task)
            raw_output = client.generate_json(llm_request)
        legacy_candidates = raw_output.get("candidates") if isinstance(raw_output, dict) else None
        if (
            isinstance(legacy_candidates, list)
            and len(legacy_candidates) >= MIN_GENERATED_CANDIDATES
            and all(isinstance(candidate, str) for candidate in legacy_candidates)
        ):
            legacy_code = [str(candidate) for candidate in legacy_candidates]
            if not _has_safe_candidate(legacy_code):
                if not is_live_llm_provider():
                    output = BacktestCodeLLMOutput.model_validate(raw_output)
                    raise AssertionError("unreachable after invalid legacy response")
                if validation_feedback is not None:
                    raise ValueError("no safe backtest candidates after one regeneration")
                return _generate_backtest_code_output(
                    client,
                    request,
                    validation_feedback=_candidate_validation_feedback(legacy_code),
                )
            feature_mapping = map_strategy_features(request.strategy)
            plan = build_code_generation_plan(request.strategy, feature_mapping)
            output = BacktestCodeLLMOutput.model_construct(
                strategy_ir=_normalized_strategy_ir(None, request.strategy, plan),
                candidates=_default_parameter_sets(
                    request.strategy,
                    plan,
                    request.max_positions,
                ),
                fallback_code=legacy_code[:MAX_GENERATED_CANDIDATES],
                fallback_reasons=[
                    "Accepted legacy v1 response through the isolated Python fallback."
                ],
            )
        else:
            output = BacktestCodeLLMOutput.model_validate(raw_output)
        with activity_role("BACKTEST_CODE"):
            report_activity(
                "role_completed",
                summary=f"구조화 후보 {len(output.candidates)}개 생성 완료",
            )
        return output
    except (LLMClientError, ValidationError) as exc:
        if is_live_llm_provider():
            if isinstance(exc, ValidationError) and validation_feedback is None:
                return _generate_backtest_code_output(
                    client,
                    request,
                    validation_feedback=_schema_validation_feedback(exc),
                )
            raise
        with activity_role("BACKTEST_CODE"):
            report_activity("role_completed", summary=f"{type(exc).__name__}: {exc}")
        feature_mapping = map_strategy_features(request.strategy)
        plan = build_code_generation_plan(request.strategy, feature_mapping)
        return BacktestCodeLLMOutput.model_construct(
            strategy_ir=_normalized_strategy_ir(None, request.strategy, plan),
            candidates=_default_parameter_sets(
                request.strategy,
                plan,
                request.max_positions,
            ),
            fallback_code=[],
            fallback_reasons=[f"{type(exc).__name__}: {exc}"],
        )


def _has_safe_candidate(candidates: list[str]) -> bool:
    return any(validate_backtest_code(candidate).ok for candidate in candidates)


def _candidate_validation_feedback(candidates: list[str]) -> list[str]:
    feedback: list[str] = []
    seen: set[str] = set()
    feedback_chars = 0
    truncated = False
    content_limit = MAX_VALIDATION_FEEDBACK_CHARS - len(TRUNCATED_VALIDATION_FEEDBACK)
    for candidate in candidates:
        for violation in validate_backtest_code(candidate).violations:
            message = violation.message.strip()
            if not message or message in seen:
                continue
            if len(feedback) >= MAX_VALIDATION_FEEDBACK_ITEMS - 1:
                truncated = True
                break
            remaining = content_limit - feedback_chars
            if remaining <= 0:
                truncated = True
                break
            clipped_message = message[:remaining]
            feedback.append(clipped_message)
            seen.add(message)
            feedback_chars += len(clipped_message)
            if clipped_message != message:
                truncated = True
                break
        if truncated:
            break
    if truncated:
        feedback.append(TRUNCATED_VALIDATION_FEEDBACK)
    if not feedback:
        return ["Return at least one non-legacy candidate that passes the requested AST contract."]
    return feedback


def _schema_validation_feedback(exc: ValidationError) -> list[str]:
    feedback: list[str] = []
    feedback_chars = 0
    for error in exc.errors(include_url=False, include_input=False):
        location = ".".join(str(item) for item in error.get("loc") or ())
        message = f"{location}: {error.get('msg', 'invalid value')}".strip(": ")
        remaining = MAX_VALIDATION_FEEDBACK_CHARS - feedback_chars
        if remaining <= len(TRUNCATED_VALIDATION_FEEDBACK):
            feedback.append(TRUNCATED_VALIDATION_FEEDBACK)
            break
        clipped = message[:remaining]
        feedback.append(clipped)
        feedback_chars += len(clipped)
        if len(feedback) >= MAX_VALIDATION_FEEDBACK_ITEMS or clipped != message:
            break
    return feedback or ["Regenerate values that satisfy every response schema constraint."]


def map_strategy_features(strategy: StrategySpec) -> FeatureMapping:
    requested = [
        condition.left for condition in strategy.entry_conditions + strategy.exit_conditions
    ]
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


def _automatic_strategy_blueprints(
    strategy: StrategySpec,
    *,
    templates: list[StrategyBlueprintTemplate],
    preferred_lookbacks: list[int],
    selection_text: str,
    style: Literal["aggressive", "balanced", "defensive"],
    horizon: Literal["short", "medium", "long"],
    rebalance_interval_days: int,
    trailing_stop_pct: float,
) -> list[GeneratedStrategyBlueprint]:
    max_positions = requested_max_positions(
        max_position_pct_from_risk_constraints(strategy.risk_constraints)
    )
    stop_loss_pct = float(strategy.risk_constraints.get("stop_loss_pct", 0.20))
    take_profit_pct = float(strategy.risk_constraints.get("take_profit_pct", 10.0))
    style_label = {
        "aggressive": "공격형",
        "balanced": "균형형",
        "defensive": "방어형",
    }[style]
    horizon_label = {
        "short": "단기",
        "medium": "중기",
        "long": "장기",
    }[horizon]
    matches = catalog_selection_terms(selection_text, templates)
    generated: list[GeneratedStrategyBlueprint] = []
    for index, template in enumerate(templates, start=1):
        parameters = customize_blueprint_parameters(
            template,
            max_positions=max_positions,
            rebalance_interval_days=rebalance_interval_days,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            preferred_lookback=preferred_lookbacks[index - 1],
        )
        matched_terms = matches.get(template.catalog_id, [])
        match_reason = (
            f"입력에서 {', '.join(matched_terms)} 표현이 일치했습니다. "
            if matched_terms
            else "입력이 특정 산식을 지정하지 않아 위험성향·기간 기본 우선순위를 사용했습니다. "
        )
        generated.append(
            GeneratedStrategyBlueprint(
                blueprint_id=template.catalog_id,
                profile=template.profile,
                title=template.title,
                catalog_version=template.catalog_version,
                catalog_family=template.family,
                preset_id=template.preset_id,
                plain_explanation=template.plain_explanation,
                formula=template.formula,
                derivation=template.derivation,
                why_used=template.why_used,
                entry_conditions=template.entry_conditions,
                exit_conditions=template.exit_conditions,
                ranking_metric=template.ranking_metric,
                ranking_direction=template.ranking_direction,
                execution_mode=template.execution_mode,
                execution_signature=template.execution_signature,
                indicator_explanations=[
                    item.model_dump(mode="json")
                    for item in template.indicator_explanations
                ],
                why_generated=(
                    f"{len(strategy_blueprint_catalog())}개 독립 산식 카탈로그에서 사용자 입력을 "
                    f"{style_label}·{horizon_label} 설정으로 "
                    f"해석해 고른 후보 {index}입니다. {match_reason}"
                    "아직 승자를 정하지 않았으며 이후 백테스트가 별도로 비교합니다."
                ),
                lookback=parameters.lookback,
                threshold=parameters.threshold,
                max_positions=parameters.max_positions,
                rebalance_interval_days=parameters.rebalance_interval_days,
                stop_loss_pct=parameters.stop_loss_pct,
                take_profit_pct=parameters.take_profit_pct,
                trailing_stop_pct=parameters.trailing_stop_pct,
                matched_terms=matched_terms,
                tags=template.tags,
                required_data=template.required_data,
                source_refs=template.source_refs,
                caveats=template.caveats,
                implementation_notes=template.implementation_notes,
                parameter_schema={
                    key: rule.model_dump(mode="json")
                    for key, rule in template.parameter_schema.items()
                },
            )
        )
    return generated


def build_code_generation_plan(
    strategy: StrategySpec, feature_mapping: FeatureMapping
) -> CodeGenerationPlan:
    strategy_id = strategy.strategy_id
    requested_text = " ".join(feature_mapping.requested_features + strategy.indicators).lower()
    if strategy.selection_mode == "automatic":
        raw_style = str(strategy.risk_constraints.get("strategy_style", "balanced"))
        style: Literal["aggressive", "balanced", "defensive"] = (
            raw_style if raw_style in {"aggressive", "balanced", "defensive"} else "balanced"
        )  # type: ignore[assignment]
        raw_horizon = str(strategy.risk_constraints.get("investment_horizon", "medium"))
        horizon: Literal["short", "medium", "long"] = (
            raw_horizon if raw_horizon in {"short", "medium", "long"} else "medium"
        )  # type: ignore[assignment]
        catalog_query = str(strategy.risk_constraints.get("catalog_query", "")).strip()
        selection_text = catalog_query or " ".join([strategy.name, requested_text])
        sealed_ids = [
            item
            for item in str(strategy.risk_constraints.get("sealed_candidate_ids", "")).split(",")
            if item
        ]
        if sealed_ids:
            catalog = {item.catalog_id: item for item in strategy_blueprint_catalog()}
            try:
                selected_templates = [catalog[item] for item in sealed_ids]
            except KeyError as exc:
                raise ValueError("sealed exploration candidate is not in the catalog") from exc
            sealed_signatures = [
                item
                for item in str(
                    strategy.risk_constraints.get("sealed_candidate_signatures", "")
                ).split(",")
                if item
            ]
            if [item.execution_signature for item in selected_templates] != sealed_signatures:
                raise ValueError("sealed exploration candidate signature changed")
        else:
            profile_priority = automatic_candidate_profiles(style, horizon)
            selected_templates = select_strategy_blueprints(
                selection_text,
                risk_style=style,
                horizon=horizon,
                profile_priority=profile_priority,  # type: ignore[arg-type]
                limit=MAX_GENERATED_CANDIDATES,
            )
        selected_profiles = tuple(template.profile for template in selected_templates)
        rotation_lookbacks = automatic_candidate_lookbacks(
            selected_profiles,
            risk_style=style,
            horizon=horizon,
        )
        preferred_lookbacks = [
            int(template.parameter_schema["lookback"].maximum)
            if horizon == "long"
            else (
                rotation_lookbacks[index]
                if template.profile in AUTOMATIC_TOURNAMENT_PROFILES
                else template.default_parameters.lookback
            )
            for index, template in enumerate(selected_templates)
        ]
        rebalance_interval_days = int(strategy.risk_constraints.get("rebalance_interval_days", 21))
        trailing_stop_pct = float(strategy.risk_constraints.get("trailing_stop_pct", 0.25))
        medium_momentum_weight = float(
            strategy.risk_constraints.get("medium_momentum_weight", 0.60)
        )
        generated_strategies = _automatic_strategy_blueprints(
            strategy,
            templates=selected_templates,
            preferred_lookbacks=preferred_lookbacks,
            selection_text=selection_text,
            style=style,
            horizon=horizon,
            rebalance_interval_days=rebalance_interval_days,
            trailing_stop_pct=trailing_stop_pct,
        )
        profiles = [item.profile for item in generated_strategies]
        lookbacks = [item.lookback for item in generated_strategies]
        thresholds = [item.threshold for item in generated_strategies]
        return CodeGenerationPlan(
            strategy_id=strategy_id,
            entry_feature="performance_momentum_tournament",
            exit_feature="scheduled_rank_or_emergency_stop",
            proxy_feature="past_only_price_factors",
            lookbacks=lookbacks,
            thresholds=thresholds,
            stop_loss_pct=float(strategy.risk_constraints.get("stop_loss_pct", 0.20)),
            take_profit_pct=10.0,
            expected_trade_frequency=f"every_{rebalance_interval_days}_trading_days",
            candidate_profiles=profiles,
            customization_style=style,
            investment_horizon=horizon,
            rebalance_interval_days=rebalance_interval_days,
            trailing_stop_pct=trailing_stop_pct,
            medium_momentum_weight=medium_momentum_weight,
            benchmark_objective=True,
            customization_summary=(
                f"{style}/{horizon}: {len(strategy_blueprint_catalog())}개 독립 산식에서 "
                f"{len(profiles)}개 사전등록 후보 선택, "
                f"{rebalance_interval_days}거래일 교체, "
                "63거래일 구간 벤치마크 승패 검증"
            ),
            generated_strategies=generated_strategies,
            catalog_version=CATALOG_VERSION,
            catalog_size=len(strategy_blueprint_catalog()),
            catalog_fingerprint=strategy_blueprint_catalog_fingerprint(),
        )
    if strategy_id.startswith("automatic_academic_momentum"):
        return CodeGenerationPlan(
            strategy_id=strategy_id,
            entry_feature="academic_momentum_trend",
            exit_feature="monthly_trend_or_stop",
            proxy_feature="past_only_price_factors",
            lookbacks=[252],
            thresholds=[0.0, 0.05, 0.1],
            expected_trade_frequency="monthly",
        )
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
    templates = _strategy_template_candidates(
        strategy
    ) or MOCK_BACKTEST_CODE_LLM.generate_backtest_candidates(strategy, "A")
    generated = _generated_strategy_candidates(strategy, plan, max_positions)
    return (generated + templates)[:MAX_GENERATED_CANDIDATES]


def _render_condition_signal_code(
    strategy: StrategySpec, compiled: "CompiledConditions", max_positions: int
) -> str:
    """build_signals whose entry test is the strategy's own compiled conditions.

    Unlike the profile templates, which pick a generic momentum/breakout shape, this
    trades exactly the rule the screen used - the per-stock conditions compiled to a
    boolean over each stock's history/financials, plus any cross-sectional cut applied
    against the day's universe. Exits fall back to stop/target on the entry price so a
    position is not held forever; entry is the strategy itself.
    """

    stop_loss = float(strategy.risk_constraints.get("stop_loss_pct", 0.08))
    take_profit = float(strategy.risk_constraints.get("take_profit_pct", 0.2))
    entry_expr = compiled.per_stock
    # How far past its thresholds a name sits, used to order same-day entries when more
    # of them qualify than there are slots. "0.0" leaves every entry tied, which the
    # sort below resolves by ticker code, the old behaviour.
    score_expr = compile_score_expression(strategy.entry_conditions) or "0.0"
    # (metric, pct, top) triples, evaluated against the day's universe below.
    rank_filters = list(compiled.rank_filters)
    # Bars the widest condition needs before it evaluates to what it claims.
    warmup_bars = max(1, int(getattr(compiled, "warmup_bars", 1)))
    # Generated from the compiler's own vocabulary so an expression can never name a
    # variable the template forgot to bind.
    indicator_bindings = "\n            ".join(
        f'{key} = _ind(row, "{key}")' for key in indicator_row_keys()
    )
    return f"""def build_signals(prices):
    def _avg(xs):
        return sum(xs) / len(xs) if xs else 0.0
    def _fin(row, key):
        value = row.get(key)
        # None (not yet filed) becomes a sentinel that fails every numeric comparison,
        # so a name with no filing on this date simply does not match the condition.
        return value if isinstance(value, (int, float)) else float("-inf")
    def _num(value):
        return value if isinstance(value, (int, float)) else None
    def _ind(row, key):
        # Warehouse indicators forward-filled onto the bar. A missing one becomes NaN,
        # which fails every comparison, so the condition simply does not match. It must
        # not become a plausible-looking default: `rsi` used to fall back to 50, and a
        # stock with no RSI at all then read as perfectly neutral momentum.
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return float("nan")
        return float(value)
    rank_filters = {rank_filters!r}
    warmup_bars = {int(warmup_bars)}
    signals = []
    rows_by_date = {{}}
    for row in sorted(prices, key=lambda item: (item["date"], item.get("ticker", "000000"))):
        rows_by_date.setdefault(row["date"], []).append(row)
    histories = {{}}
    states = {{}}
    stop_loss = {stop_loss!r}
    take_profit = {take_profit!r}
    max_positions = {int(max_positions)}
    strategy_id = {strategy.strategy_id!r}
    for current_date in sorted(rows_by_date):
        entries = []
        universe_metrics = {{}}
        for row in rows_by_date[current_date]:
            ticker = row.get("ticker", "000000")
            open_price = float(row.get("open", row.get("close", 0)))
            high_price = float(row.get("high", row.get("close", 0)))
            low_price = float(row.get("low", row.get("close", 0)))
            close = float(row["close"])
            volume = float(row.get("volume", 0))
            {indicator_bindings}
            # The forward-filled financials live on the row itself; _fin() reads them.
            fin = row
            hist = histories.setdefault(
                ticker, {{"opens": [], "highs": [], "lows": [], "closes": [], "volumes": []}}
            )
            state = states.setdefault(ticker, {{"in_position": False, "entry_price": 0.0}})
            opens = hist["opens"]
            highs = hist["highs"]
            lows = hist["lows"]
            closes = hist["closes"]
            volumes = hist["volumes"]
            # Enough history for the longest window before the rule can be judged. This
            # said `>= 1`, which is what the comment always claimed but the code never
            # did: a 52-week-high condition was evaluated on a stock's second bar
            # against a one-day high, and matched.
            ready = len(closes) >= warmup_bars
            entry_ok = False
            entry_score = 0.0
            if ready:
                try:
                    entry_ok = bool({entry_expr})
                except (ValueError, ZeroDivisionError, IndexError):
                    entry_ok = False
                if entry_ok:
                    try:
                        entry_score = float({score_expr})
                    except (ValueError, ZeroDivisionError, IndexError):
                        entry_score = 0.0
                    # NaN and the _fin() sentinel both fall outside this band; neither is
                    # a strength, so they rank as untested rather than as best or worst.
                    if not -1e18 < entry_score < 1e18:
                        entry_score = 0.0
            if state["in_position"]:
                entry_price = state["entry_price"]
                gain = (close / entry_price - 1) if entry_price else 0.0
                if gain <= -stop_loss or gain >= take_profit:
                    signals.append({{"date": current_date, "ticker": ticker, "action": "SELL", "price": close}})
                    state["in_position"] = False
                    state["entry_price"] = 0.0
            elif entry_ok:
                entries.append((ticker, close, entry_score))
            # The percentile cut ranks the whole day's universe, not just today's
            # candidates - otherwise buying the leaders shrinks the pool and lets the
            # next names drift into the "top". Collect every stock's metric here.
            for metric, _pct, _top in rank_filters:
                value = _num(row.get(metric))
                if value is not None:
                    universe_metrics.setdefault(metric, []).append((ticker, value))
            opens.append(open_price)
            highs.append(high_price)
            lows.append(low_price)
            closes.append(close)
            volumes.append(volume)
        # A cross-sectional cut already states what "better" means on this universe, so
        # the first one outranks the per-stock margins as the entry score.
        rank_scores = dict(universe_metrics.get(rank_filters[0][0], [])) if rank_filters else {{}}
        rank_sign = 1.0 if (rank_filters and rank_filters[0][2]) else -1.0
        # Cross-sectional cuts against the full universe: keep only candidates inside the
        # requested top/bottom percentile of that day's ranking on each metric.
        for metric, pct, top in rank_filters:
            scored = universe_metrics.get(metric, [])
            if not scored:
                entries = []
                break
            scored.sort(key=lambda item: item[1], reverse=top)
            cutoff = max(1, int(len(scored) * pct))
            kept = {{t for t, _v in scored[:cutoff]}}
            entries = [
                (t, p, rank_sign * rank_scores[t] if t in rank_scores else s)
                for t, p, s in entries
                if t in kept
            ]
        # Signal strength decides who gets a scarce slot; the ticker code only breaks
        # ties. Sorting by the code first hands every slot to the lowest codes listed.
        entries.sort(key=lambda item: (-item[2], item[0]))
        held = sum(1 for s in states.values() if s["in_position"])
        for ticker, price, entry_score in entries:
            if held >= max_positions:
                break
            signals.append({{"date": current_date, "ticker": ticker, "action": "BUY", "price": price, "score": entry_score}})
            states[ticker]["in_position"] = True
            states[ticker]["entry_price"] = price
            held += 1
    return signals
"""


def _generated_strategy_candidates(
    strategy: StrategySpec,
    plan: CodeGenerationPlan,
    max_positions: int = DEFAULT_MAX_POSITIONS,
) -> list[str]:
    codes: list[str] = []
    # If the strategy's conditions compile - a per-stock rule and/or cross-sectional
    # cuts - trade exactly that first: it is the screen's own rule, not a generic
    # profile. Conditions that do not compile fall through to the profiles.
    compiled = compile_conditions(strategy.entry_conditions)
    if compiled is not None:
        codes.append(_render_condition_signal_code(strategy, compiled, max_positions))
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


def _candidate_profiles(plan: CodeGenerationPlan) -> list[StructuredProfile]:
    if plan.generated_strategies:
        return [blueprint.profile for blueprint in plan.generated_strategies]
    if plan.candidate_profiles:
        return list(plan.candidate_profiles)
    if plan.entry_feature == "performance_momentum_tournament":
        return [
            "relative_momentum_rotation",
            "risk_adjusted_momentum_rotation",
            "trend_leader_rotation",
        ]
    if plan.entry_feature == "academic_momentum_trend":
        return ["academic_momentum_trend"] * MIN_GENERATED_CANDIDATES
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
    return f"""def build_signals(prices):
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
    trailing_stop_pct = {float(plan.trailing_stop_pct)!r}
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
            # The window has to be full before it is the window the profile names.
            # `min(lookback, len(closes))` made a 120-day average mean a 2-day average on
            # the second bar, which is where the profile's first entries came from.
            window = lookback
            buy = False
            sell = False
            score = -999.0
            if len(closes) >= lookback:
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
                trailing_stop = state["peak"] > 0 and close < state["peak"] * (1 - trailing_stop_pct)
                score = rolling_sharpe + medium_return * 4 + long_return * 2 - volatility
                if profile == "academic_momentum_trend" and len(closes) >= 252:
                    momentum_12_1 = closes[-21] / closes[-252] - 1
                    sma_50 = (sum(closes[-49:]) + close) / 50
                    sma_200 = (sum(closes[-199:]) + close) / 200
                    volatility_closes = closes[-21:] + [close]
                    daily_returns = [
                        after / before - 1
                        for before, after in zip(
                            volatility_closes[:-1], volatility_closes[1:]
                        )
                        if before
                    ]
                    daily_mean = sum(daily_returns) / len(daily_returns)
                    daily_variance = sum(
                        (item - daily_mean) ** 2 for item in daily_returns
                    ) / len(daily_returns)
                    realized_volatility_21d = daily_variance ** 0.5 * (252 ** 0.5)
                    rebalance_eligible = (len(closes) - 252) % 21 == 0
                    score = (
                        momentum_12_1 * 4
                        + (sma_50 / sma_200 - 1) * 2
                        - realized_volatility_21d
                    )
                    buy = (
                        rebalance_eligible
                        and momentum_12_1 > threshold
                        and close >= sma_200
                        and sma_50 >= sma_200
                        and realized_volatility_21d <= 0.35
                    )
                    sell = state["in_position"] and (
                        close < sma_200 * 0.95
                        or (
                            rebalance_eligible
                            and (momentum_12_1 <= 0 or sma_50 < sma_200)
                        )
                    )
                elif profile == "long_regime_momentum":
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
                    buy = rolling_sharpe >= threshold / 10 and close >= medium_average and trend > 0
                    sell = state["in_position"] and (rolling_sharpe <= 0 or close < medium_average)
                elif profile == "dual_sma_trend":
                    score = medium_return * 3 + (short_average / medium_average - 1) * 8 if medium_average else 0
                    buy = short_average > medium_average > average * 0.98 and close >= short_average
                    sell = state["in_position"] and (short_average < medium_average or close < average)
                elif profile == "low_vol_momentum":
                    score = trend * 3 + medium_return * 2 - volatility * 1.5
                    buy = trend >= threshold and medium_return >= 0 and volatility <= 0.28 and close >= medium_average
                    sell = state["in_position"] and (close < medium_average * 0.96 or medium_return < -0.06 or long_drawdown > 0.22)
                elif profile == "breakout_volume":
                    score = (close / high - 0.99) * 10 + volume_ratio * 0.2 + trend * 2
                    buy = close >= high * 0.995 and volume_ratio >= threshold and trend >= 0
                    sell = state["in_position"] and close < short_average
                elif profile == "rsi_trend_rebound":
                    score = medium_return * 3 + (55 - abs(rsi - 45)) / 50 - volatility
                    buy = close >= medium_average and trend >= 0 and 35 <= rsi <= 62 and close >= previous
                    sell = state["in_position"] and (rsi >= 72 or close < medium_average)
                elif profile == "mean_reversion_band":
                    score = pullback * 2 + (50 - rsi) / 50 - volatility
                    buy = close <= average * (1 - max(0.0, min(0.20, threshold))) and rsi <= 45
                    sell = state["in_position"] and (close >= medium_average or rsi >= 60)
                elif profile == "return_to_volatility":
                    score = return_to_volatility + medium_return * 2
                    buy = return_to_volatility >= threshold * 4 and close >= medium_average
                    sell = state["in_position"] and (return_to_volatility <= 0 or close < medium_average)
                elif profile == "cash_preserving_trend":
                    score = rolling_sharpe + trend * 2 - volatility * 2
                    buy = trend >= threshold and rolling_sharpe > 0.05 and volatility <= 0.3
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
        # Strongest signal first; the ticker code only breaks ties, ascending.
        ranked_buys = sorted(ranked_buys, key=lambda item: (-item["score"], item["ticker"]))[:open_slots]
        selected_buys = {{}}
        for item in ranked_buys:
            selected_buys[item["ticker"]] = item["score"]
        for item in evaluations:
            ticker = item["ticker"]
            row = item["row"]
            close = item["close"]
            state = item["state"]
            entry_score = None
            if item["sell"] and state["in_position"]:
                action = "SELL"
                state["in_position"] = False
                state["entry_price"] = 0.0
                state["days"] = 0
                state["peak"] = 0.0
            elif ticker in selected_buys:
                action = "BUY"
                entry_score = selected_buys[ticker]
                state["in_position"] = True
                state["entry_price"] = close
                state["days"] = 0
                state["peak"] = close
            else:
                action = "HOLD"
                if state["in_position"]:
                    state["days"] += 1
                    state["peak"] = max(state["peak"], close)
            signals.append({{"date": row["date"], "ticker": ticker, "action": action, "price": close, "score": entry_score}})
            item["history"]["closes"].append(close)
            item["history"]["volumes"].append(item["volume"])
    return signals
"""


def generate_self_improvement_candidates(
    strategy: StrategySpec,
    code_plan: dict[str, object],
    *,
    start_index: int,
    iteration: int,
    max_positions: int = DEFAULT_MAX_POSITIONS,
) -> list[CodeCandidate]:
    plan = CodeGenerationPlan.model_validate(code_plan)
    strategy_ir = _normalized_strategy_ir(None, strategy, plan)
    profiles = _candidate_profiles(plan)
    # Keep at least two nearby variants of the user's own compiled rule in every
    # refinement. Generic profiles are comparisons, not replacements for that rule.
    if compile_conditions(strategy.entry_conditions) is not None:
        profiles = ["compiled_conditions", "compiled_conditions", *profiles]
    lookbacks = [max(3, int(value) - iteration * 2) for value in plan.lookbacks] + [
        min(252, int(value) + iteration * 10) for value in plan.lookbacks
    ]
    thresholds = [
        _adjust_threshold(float(value), plan.entry_feature, iteration) for value in plan.thresholds
    ] + [
        _selective_threshold(float(value), plan.entry_feature, iteration)
        for value in plan.thresholds
    ]
    stop_loss = float(strategy.risk_constraints.get("stop_loss_pct", plan.stop_loss_pct))
    take_profit = float(strategy.risk_constraints.get("take_profit_pct", plan.take_profit_pct))
    candidates: list[CodeCandidate] = []
    seen: set[str] = set()
    # A compact Cartesian traversal varies one axis at a time before combining
    # changes.  The prior modulo zip moved every axis together along one diagonal.
    compiled_variants = [
        (
            "compiled_conditions",
            lookbacks[index % len(lookbacks)],
            thresholds[index % len(thresholds)],
        )
        for index in range(2)
        if "compiled_conditions" in profiles
    ]
    comparison_profiles = [profile for profile in profiles if profile != "compiled_conditions"]
    # Seed with two faithful user-rule variants, then diversify profiles before
    # expanding into the rest of the Cartesian product.
    diverse_variants = [
        (
            profile,
            lookbacks[(index + iteration) % len(lookbacks)],
            thresholds[(index * 2 + iteration) % len(thresholds)],
        )
        for index, profile in enumerate(comparison_profiles)
    ]
    parameter_grid = [
        *compiled_variants,
        *diverse_variants,
        *[
            (profile, lookback, threshold)
            for profile in profiles
            for lookback in lookbacks
            for threshold in thresholds
        ],
    ]
    for profile, lookback, threshold in parameter_grid:
        if len(candidates) >= MAX_SELF_IMPROVEMENT_CANDIDATES:
            break
        parameters = CandidateParameters(
            profile=profile,
            lookback=lookback,
            threshold=threshold,
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            max_positions=max_positions,
            rebalance_interval_days=plan.rebalance_interval_days,
            trailing_stop_pct=plan.trailing_stop_pct,
            medium_momentum_weight=plan.medium_momentum_weight,
        )
        identity = _parameter_identity(parameters)
        if identity in seen:
            continue
        seen.add(identity)
        code = _render_structured_reference_code(strategy_ir, parameters)
        validation = validate_backtest_code(code)
        candidates.append(
            CodeCandidate(
                candidate_id=f"A{start_index + len(candidates)}",
                variant="A",
                code=code,
                validation_ok=validation.ok,
                violations=[violation.message for violation in validation.violations],
                metrics=None,
                representation="structured",
                strategy_ir=strategy_ir,
                parameters=parameters,
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
                        strategy.risk_constraints.get("stop_loss_pct", plan.stop_loss_pct)
                    ),
                    take_profit=float(
                        strategy.risk_constraints.get("take_profit_pct", plan.take_profit_pct)
                    ),
                    max_positions=max_positions,
                )
            )
    return codes
