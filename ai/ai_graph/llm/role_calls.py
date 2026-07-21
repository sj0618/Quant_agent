from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_graph.llm import LLMClientError, LLMJsonRequest, create_llm_client, is_live_llm_provider
from ai_graph.schemas import (
    Condition,
    ConditionOperator,
    DailyDigestComparisonRow,
    DailyDigestStrategyInput,
    MarketBrief,
    MarketBriefItem,
)


ROLE_DEBATE_SCHEMA_NAME = "quantagent.role_debate.v1"
MARKET_BRIEF_SCHEMA_NAME = "quantagent.market_brief.v1"
STRATEGY_CONDITIONS_SCHEMA_NAME = "quantagent.strategy_conditions.v1"
ROLE_DEBATE_PROMPT_TEMPLATE_NAME = "role_debate"
MARKET_BRIEF_PROMPT_TEMPLATE_NAME = "daily_market_brief"
STRATEGY_CONDITIONS_PROMPT_TEMPLATE_NAME = "strategy_conditions"
ROLE_DEBATE_PROMPT_VERSION = "v2"
MARKET_BRIEF_PROMPT_VERSION = "v1"
STRATEGY_CONDITIONS_PROMPT_VERSION = "v1"
SCREENING_RELAXATION_SCHEMA_NAME = "quantagent.screening_relaxation.v1"
SCREENING_RELAXATION_PROMPT_TEMPLATE_NAME = "screening_relaxation"
SCREENING_RELAXATION_PROMPT_VERSION = "v1"


class RoleDebatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommendation: str = Field(default="HOLD", min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    validation_results: dict[str, Any] = Field(default_factory=dict)
    fallback_reasons: list[str] = Field(default_factory=list)
    citations: list[dict[str, str]] = Field(default_factory=list)


class _LiveRoleCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str


class _LiveValidationResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: list[str]


class _LiveRoleDebateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    evidence: list[str]
    concerns: list[str]
    recommendation: str
    confidence: float
    validation_results: _LiveValidationResults
    citations: list[_LiveRoleCitation]


class StrategyDescriptionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strategy_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    fallback_reasons: list[str] = Field(default_factory=list)


class StrategyConditionsPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entry_conditions: list[Condition] = Field(default_factory=list)
    exit_conditions: list[Condition] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    fallback_reasons: list[str] = Field(default_factory=list)


class _LiveCondition(BaseModel):
    """Strict-schema twin of Condition: AOAI's structured-output mode requires every
    property to be listed in the JSON schema's "required" array, but Condition.description
    has a default (None) so pydantic omits it from "required" — Azure then rejects the
    schema outright. Keeping this separate from Condition (used elsewhere with an
    optional description) avoids forcing every other caller to always supply one.
    """

    model_config = ConfigDict(extra="forbid")

    left: str
    operator: ConditionOperator
    right: float | str | list[float]
    description: str


class _LiveStrategyConditionsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_conditions: list[_LiveCondition]
    exit_conditions: list[_LiveCondition]
    indicators: list[str]
    confidence: float


def generate_role_debate(
    *,
    role: str,
    task: str,
    context: dict[str, Any],
    fallback: RoleDebatePayload,
    enable_web_search: bool = False,
) -> RoleDebatePayload:
    """Run a role-specific LLM call, falling back to deterministic MVP notes.

    The fallback keeps local tests and mock mode stable, while AOAI deployments can
    be split by role through create_llm_client(role=...).

    enable_web_search mirrors generate_market_brief's usage: it asks the AOAI
    Responses API to attach its web search tool for this call so the role can
    ground its findings in current information instead of local retrieval only.
    """

    expected_json_schema = _role_debate_output_schema()
    request = LLMJsonRequest(
        schema_name=ROLE_DEBATE_SCHEMA_NAME,
        system_prompt=_system_prompt(role, task, enable_web_search=enable_web_search),
        user_prompt=_user_prompt(context, expected_json_schema),
        temperature=0.0,
        enable_web_search=enable_web_search,
        task_type=role.lower(),
        prompt_template_name=ROLE_DEBATE_PROMPT_TEMPLATE_NAME,
        prompt_version=ROLE_DEBATE_PROMPT_VERSION,
        response_schema=expected_json_schema,
        variables_jsonb={
            "role": role,
            "task": task,
            "context": context,
            "expected_json_schema": expected_json_schema,
        },
    )
    try:
        payload = create_llm_client(role=role).generate_json(request)
        provider_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"role", "fallback_reasons"}
        }
        if is_live_llm_provider():
            provider_payload = _LiveRoleDebateOutput.model_validate(provider_payload).model_dump()
        return RoleDebatePayload.model_validate(
            {
                **provider_payload,
                "role": role,
            }
        )
    except (LLMClientError, ValidationError, ValueError, TypeError) as exc:
        if is_live_llm_provider():
            raise
        reasons = [*fallback.fallback_reasons, f"{type(exc).__name__}: {exc}"]
        return fallback.model_copy(update={"fallback_reasons": reasons})


def _system_prompt(role: str, task: str, *, enable_web_search: bool = False) -> str:
    base = (
        "You are a QuantAgent role-specific analyst. Return only a JSON object that "
        "matches EXPECTED_JSON_SCHEMA exactly. Return "
        "summary, evidence, concerns, recommendation, confidence, and "
        f"validation_results; use an empty citations array unless needed. Role={role}. Task={task}."
    )
    if not enable_web_search:
        return base
    return (
        f"{base} Use the web search tool to find current, relevant information "
        "when the local context is insufficient. Also return a \"citations\" "
        "array of objects with \"title\" and \"url\" for every source found via "
        "the web search tool; never invent a citation, and leave citations "
        "empty if no web search was needed."
    )


def _user_prompt(context: dict[str, Any], expected_json_schema: dict[str, Any]) -> str:
    return (
        "Analyze this QuantAgent state snapshot. Keep the output concise.\n"
        "EXPECTED_JSON_SCHEMA="
        f"{json.dumps(expected_json_schema, ensure_ascii=False, sort_keys=True)}\n"
        "CONTEXT_JSON="
        f"{json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)}"
    )


def _role_debate_output_schema() -> dict[str, Any]:
    return _LiveRoleDebateOutput.model_json_schema()


def generate_daily_digest_overall_comment(
    strategies: list[DailyDigestStrategyInput],
    comparison_rows: list[DailyDigestComparisonRow],
) -> str:
    context = {
        "strategies": [strategy.model_dump() for strategy in strategies],
        "comparison_rows": [row.model_dump() for row in comparison_rows],
    }
    fallback_summary = " ".join(
        f"{row.name}은(는) 오늘 {row.today_signal} 신호이며 {row.status} 상태입니다."
        for row in comparison_rows
    )
    payload = generate_role_debate(
        role="DIGEST_JUDGE",
        task=(
            "Compare the subscribed strategies for today and recommend how the user "
            "should react across all of them together, in 2-4 Korean sentences."
        ),
        context=context,
        fallback=RoleDebatePayload(
            role="DIGEST_JUDGE",
            summary=fallback_summary,
            recommendation=comparison_rows[0].today_signal,
            confidence=0.5,
        ),
    )
    return payload.summary


def generate_strategy_description(
    *,
    strategy_id: str,
    name: str,
    timeframe: str,
    entry_summary: str,
    exit_summary: str,
    risk_summary: str,
    tags: list[str],
    fallback: str,
) -> StrategyDescriptionPayload:
    payload = generate_role_debate(
        role="STRATEGY_DESCRIPTION",
        task=(
            "Write exactly one concise Korean sentence that explains the trading logic only. "
            "Do not mention email delivery, sending cadence, UI, dashboards, or product copy."
        ),
        context={
            "strategy_id": strategy_id,
            "name": name,
            "timeframe": timeframe,
            "entry_summary": entry_summary,
            "exit_summary": exit_summary,
            "risk_summary": risk_summary,
            "tags": tags,
        },
        fallback=RoleDebatePayload(
            role="STRATEGY_DESCRIPTION",
            summary=fallback,
            recommendation="N/A",
            confidence=0.5,
        ),
    )
    return StrategyDescriptionPayload(
        strategy_id=strategy_id,
        description=payload.summary,
        fallback_reasons=payload.fallback_reasons,
    )


STRATEGY_CONDITIONS_SYSTEM_PROMPT = (
    "You are a QuantAgent strategy analyst. Convert the user's Korean natural-language "
    "trading strategy into structured JSON that matches EXPECTED_JSON_SCHEMA exactly: "
    '"entry_conditions" and "exit_conditions" (each a non-empty array of objects with '
    "left, operator, right, description — operator one of lt/lte/gt/gte/eq/ne/between/"
    'cross_above/cross_below), "indicators" (array of indicator names referenced), and '
    '"confidence" (0-1). Use the web search tool to confirm current market-standard '
    "definitions and thresholds for any named indicator or strategy pattern when the query "
    "alone is insufficient. Return JSON only, no prose.\n\n"
    "Condition value format (required, no exceptions):\n"
    "- lt/lte/gt/gte/eq/ne: `right` MUST be a number (int or float). Never a ticker, "
    "company name, or any other non-numeric string.\n"
    "- between: `right` MUST be a 2-item [low, high] number array.\n"
    "- cross_above/cross_below: `right` MUST be a string naming the other metric/line "
    "being crossed (e.g. \"sma_20\"), not a company or ticker.\n"
    "Entry/exit conditions describe technical trading logic only (price, indicators, "
    "volume, moving averages, etc.) — never instrument selection. If the user names a "
    "specific stock or ticker (e.g. 삼성전자, 005930), do not emit a condition for it; "
    "stock/universe selection is resolved separately by the data layer, outside this call. "
    "Only describe the trading logic that applies once a stock is already selected."
)


def generate_strategy_conditions(
    *,
    query: str,
    semantic_slots: dict[str, Any],
    fallback: StrategyConditionsPayload,
) -> StrategyConditionsPayload:
    """Interpret the natural-language strategy into structured entry/exit conditions
    via the AOAI web search tool instead of the static keyword-matched templates.

    Falls back to the deterministic template profile only when the live provider is
    not configured (mock/tests); with a live provider, a bad response raises instead
    of silently masking the failure, matching generate_role_debate.
    """

    expected_json_schema = _LiveStrategyConditionsOutput.model_json_schema()
    context = {"query": query, "semantic_slots": semantic_slots}
    request = LLMJsonRequest(
        schema_name=STRATEGY_CONDITIONS_SCHEMA_NAME,
        system_prompt=STRATEGY_CONDITIONS_SYSTEM_PROMPT,
        user_prompt=_user_prompt(context, expected_json_schema),
        temperature=0.0,
        enable_web_search=True,
        task_type="strategy_conditions",
        prompt_template_name=STRATEGY_CONDITIONS_PROMPT_TEMPLATE_NAME,
        prompt_version=STRATEGY_CONDITIONS_PROMPT_VERSION,
        response_schema=expected_json_schema,
        variables_jsonb={**context, "expected_json_schema": expected_json_schema},
    )
    try:
        payload = create_llm_client(role="STRATEGY_CONDITIONS").generate_json(request)
        parsed = _LiveStrategyConditionsOutput.model_validate(payload)
        if not parsed.entry_conditions or not parsed.exit_conditions:
            raise ValueError("strategy_conditions response missing entry/exit conditions")
        return StrategyConditionsPayload(**parsed.model_dump())
    except (LLMClientError, ValidationError, ValueError, TypeError) as exc:
        if is_live_llm_provider():
            raise
        reasons = [*fallback.fallback_reasons, f"{type(exc).__name__}: {exc}"]
        return fallback.model_copy(update={"fallback_reasons": reasons})


SCREENING_RELAXATION_SYSTEM_PROMPT = """\
You are QuantAgent's screening-threshold tuner. A stock screen built from the
user's strategy returned zero matches against the whole listed universe, which
usually means the thresholds are too strict for this particular trading day -
not that the strategy is wrong.

Return JSON only: the same threshold object, loosened just enough to admit a
small number of candidates while still expressing the user's intent. Loosen the
conditions the query cares least about first, and keep the ones it states
explicitly as close to the original as you can. Never tighten a threshold.

Every value must stay inside these inclusive ranges:
  high_252_ratio 0.50..1.0, volume_ratio_min 0.5..10.0,
  relative_strength_20d_min -1.0..1.0, relative_strength_60d_min -1.0..1.0,
  rsi_max 5.0..70.0, rsi_cross_floor 5.0..70.0, sma20_band 0.005..0.50,
  bb_width_max 0.02..1.0, bb_upper_ratio 0.50..1.0.
require_close_above_sma20 is a boolean; set it false to drop the trend filter.
"""


class _LiveScreeningThresholds(BaseModel):
    """Strict-schema threshold payload: AOAI structured output requires every property
    to be listed as required, so no field carries a default here."""

    model_config = ConfigDict(extra="forbid")

    high_252_ratio: float
    volume_ratio_min: float
    require_close_above_sma20: bool
    relative_strength_20d_min: float
    relative_strength_60d_min: float
    rsi_max: float
    rsi_cross_floor: float
    sma20_band: float
    bb_width_max: float
    bb_upper_ratio: float
    rationale: str


def generate_relaxed_screening_thresholds(
    *,
    query: str,
    profile: str,
    current: dict[str, Any],
    fallback: dict[str, Any],
    round_index: int,
    universe_rows: int,
) -> dict[str, Any]:
    """Propose looser screening thresholds after a screen returned no candidates.

    Returns a plain mapping rather than the caller's model so ai_graph.data_sources
    stays importable without the LLM stack; the caller re-validates and clamps it.
    Unlike the other role calls this never raises on a live provider - screening has
    a deterministic ladder to fall back on, and failing the whole analysis because a
    relaxation hint was unavailable would be worse than widening the screen blindly.
    """

    expected_json_schema = _LiveScreeningThresholds.model_json_schema()
    context = {
        "query": query,
        "screening_profile": profile,
        "current_thresholds": current,
        "relaxation_round": round_index + 1,
        "universe_size": universe_rows,
        "matched_count": 0,
    }
    request = LLMJsonRequest(
        schema_name=SCREENING_RELAXATION_SCHEMA_NAME,
        system_prompt=SCREENING_RELAXATION_SYSTEM_PROMPT,
        user_prompt=_user_prompt(context, expected_json_schema),
        temperature=0.0,
        task_type="screening_relaxation",
        prompt_template_name=SCREENING_RELAXATION_PROMPT_TEMPLATE_NAME,
        prompt_version=SCREENING_RELAXATION_PROMPT_VERSION,
        response_schema=expected_json_schema,
        variables_jsonb={**context, "expected_json_schema": expected_json_schema},
    )
    try:
        payload = create_llm_client(role="SCREENING_RELAXATION").generate_json(request)
        parsed = _LiveScreeningThresholds.model_validate(payload)
    except (LLMClientError, ValidationError, ValueError, TypeError):
        return dict(fallback)
    return parsed.model_dump(exclude={"rationale"})


MARKET_BRIEF_SYSTEM_PROMPT = """\
You are QuantAgent's daily market-brief writer. Use the web search tool to find
today's Korean/global equity market news and macro headlines relevant to the
given strategies. Return JSON only with a "headline" (one sentence
market wrap-up) and "items" (3-5 objects with title, source, url, published_at,
tone in {positive, warning, negative, neutral, info}, and a one-sentence
summary). Only include items you found via the web search tool; never invent
sources.
"""


def generate_market_brief(
    *,
    strategy_names: list[str],
    report_date: str,
    fallback: MarketBrief,
) -> MarketBrief:
    """Fetch today's market/economic news via the AOAI web search tool.

    Falls back to a disclosed empty brief (fallback_reasons populated) when the
    provider is unset, unreachable, or returns an unparsable payload, so the
    rest of the daily digest still renders without the news section blocking it.
    """

    variables = {
        "report_date": report_date,
        "strategy_names": strategy_names,
        "expected_json_schema": MarketBrief.model_json_schema(),
    }
    request = LLMJsonRequest(
        schema_name=MARKET_BRIEF_SCHEMA_NAME,
        system_prompt=MARKET_BRIEF_SYSTEM_PROMPT,
        user_prompt=json.dumps(variables, ensure_ascii=False, sort_keys=True),
        temperature=0.2,
        enable_web_search=True,
        task_type="digest_market_brief",
        prompt_template_name=MARKET_BRIEF_PROMPT_TEMPLATE_NAME,
        prompt_version=MARKET_BRIEF_PROMPT_VERSION,
        variables_jsonb=variables,
    )
    try:
        payload = create_llm_client(role="DIGEST_MARKET_BRIEF").generate_json(request)
        items = [MarketBriefItem.model_validate(item) for item in payload.get("items", [])]
        return MarketBrief(
            headline=payload["headline"],
            items=items,
            source_usage=fallback.source_usage,
        )
    except (LLMClientError, ValidationError, ValueError, TypeError, KeyError) as exc:
        if is_live_llm_provider():
            raise
        reasons = [*fallback.fallback_reasons, f"{type(exc).__name__}: {exc}"]
        return fallback.model_copy(update={"fallback_reasons": reasons})
