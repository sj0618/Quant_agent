from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_graph.llm import LLMClientError, LLMJsonRequest, create_llm_client
from ai_graph.schemas import DailyDigestComparisonRow, DailyDigestStrategyInput, MarketBrief, MarketBriefItem


ROLE_DEBATE_SCHEMA_NAME = "quantagent.role_debate.v1"
MARKET_BRIEF_SCHEMA_NAME = "quantagent.market_brief.v1"
ROLE_DEBATE_PROMPT_TEMPLATE_NAME = "role_debate"
MARKET_BRIEF_PROMPT_TEMPLATE_NAME = "daily_market_brief"
PROMPT_VERSION = "v1"


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


class StrategyDescriptionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strategy_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    fallback_reasons: list[str] = Field(default_factory=list)


def generate_role_debate(
    *,
    role: str,
    task: str,
    context: dict[str, Any],
    fallback: RoleDebatePayload,
) -> RoleDebatePayload:
    """Run a role-specific LLM call, falling back to deterministic MVP notes.

    The fallback keeps local tests and mock mode stable, while AOAI deployments can
    be split by role through create_llm_client(role=...).
    """

    request = LLMJsonRequest(
        schema_name=ROLE_DEBATE_SCHEMA_NAME,
        system_prompt=_system_prompt(role, task),
        user_prompt=_user_prompt(context),
        temperature=0.0,
        task_type=role.lower(),
        prompt_template_name=ROLE_DEBATE_PROMPT_TEMPLATE_NAME,
        prompt_version=PROMPT_VERSION,
        variables_jsonb={"role": role, "task": task, "context": context},
    )
    try:
        payload = create_llm_client(role=role).generate_json(request)
        return RoleDebatePayload.model_validate(
            {
                "role": role,
                **payload,
            }
        )
    except (LLMClientError, ValidationError, ValueError, TypeError) as exc:
        reasons = [*fallback.fallback_reasons, f"{type(exc).__name__}: {exc}"]
        return fallback.model_copy(update={"fallback_reasons": reasons})


def _system_prompt(role: str, task: str) -> str:
    return (
        "You are a QuantAgent role-specific analyst. Return JSON only with "
        "summary, evidence, concerns, recommendation, confidence, and "
        f"validation_results. Role={role}. Task={task}."
    )


def _user_prompt(context: dict[str, Any]) -> str:
    return (
        "Analyze this QuantAgent state snapshot. Keep the output concise and "
        f"machine-readable.\nCONTEXT_JSON={context}"
    )


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
    universe: str,
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
            "universe": universe,
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


MARKET_BRIEF_SYSTEM_PROMPT = """\
You are QuantAgent's daily market-brief writer. Use the web search tool to find
today's Korean/global equity market news and macro headlines relevant to the
given strategy universes. Return JSON only with a "headline" (one sentence
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
        "strategy_universes": strategy_names,
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
        prompt_version=PROMPT_VERSION,
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
        reasons = [*fallback.fallback_reasons, f"{type(exc).__name__}: {exc}"]
        return fallback.model_copy(update={"fallback_reasons": reasons})
