from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_graph.llm import LLMClientError, LLMJsonRequest, create_llm_client, is_live_llm_provider
from ai_graph.progress import activity_role, report_activity
from ai_graph.schemas import (
    Condition,
    ConditionOperator,
    DailyDigestComparisonRow,
    DailyDigestStrategyInput,
    MarketBrief,
    MarketBriefItem,
)


_logger = logging.getLogger(__name__)

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
SCREENING_RESEARCH_SCHEMA_NAME = "quantagent.screening_research.v1"
SCREENING_RESEARCH_PROMPT_TEMPLATE_NAME = "screening_research"
SCREENING_RESEARCH_PROMPT_VERSION = "v1"
SCREENING_SQL_SCHEMA_NAME = "quantagent.screening_sql.v1"
SCREENING_SQL_PROMPT_TEMPLATE_NAME = "screening_sql"
SCREENING_SQL_PROMPT_VERSION = "v1"
REPORT_WRITEUP_SCHEMA_NAME = "quantagent.report_writeup.v1"
REPORT_WRITEUP_PROMPT_TEMPLATE_NAME = "report_writeup"
REPORT_WRITEUP_PROMPT_VERSION = "v1"
STRATEGY_REVISION_SCHEMA_NAME = "quantagent.strategy_revision.v1"
STRATEGY_REVISION_PROMPT_TEMPLATE_NAME = "strategy_revision"
STRATEGY_REVISION_PROMPT_VERSION = "v1"
STRATEGY_REVIEW_SCHEMA_NAME = "quantagent.strategy_review.v1"
STRATEGY_REVIEW_PROMPT_TEMPLATE_NAME = "strategy_review"
STRATEGY_REVIEW_PROMPT_VERSION = "v1"
STRATEGY_INTENT_SCHEMA_NAME = "quantagent.strategy_intent.v1"
STRATEGY_INTENT_PROMPT_TEMPLATE_NAME = "strategy_intent"
STRATEGY_INTENT_PROMPT_VERSION = "v1"


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
        # Tagging the call lets the live view group provider activity under the voice
        # that produced it without the provider client knowing about debates at all.
        with activity_role(role):
            report_activity("role_started", task=task)
            payload = create_llm_client(role=role).generate_json(request)
        provider_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"role", "fallback_reasons"}
        }
        if is_live_llm_provider():
            provider_payload = _LiveRoleDebateOutput.model_validate(provider_payload).model_dump()
        debate = RoleDebatePayload.model_validate(
            {
                **provider_payload,
                "role": role,
            }
        )
        with activity_role(role):
            # The provider's own fields, restructured but not reworded, so the view can
            # show a readable opinion instead of the raw JSON the deltas spell out.
            report_activity(
                "role_completed",
                summary=debate.summary,
                evidence=list(debate.evidence),
                concerns=list(debate.concerns),
                recommendation=debate.recommendation,
                confidence=debate.confidence,
            )
        return debate
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
        with activity_role("STRATEGY_CONDITIONS"):
            report_activity("role_started", task="매수/매도 조건 생성")
            payload = create_llm_client(role="STRATEGY_CONDITIONS").generate_json(request)
        parsed = _LiveStrategyConditionsOutput.model_validate(payload)
        if not parsed.entry_conditions or not parsed.exit_conditions:
            raise ValueError("strategy_conditions response missing entry/exit conditions")
        result = StrategyConditionsPayload(**parsed.model_dump())
        with activity_role("STRATEGY_CONDITIONS"):
            report_activity(
                "role_completed",
                summary=f"매수 조건 {len(result.entry_conditions)}개, 매도 조건 {len(result.exit_conditions)}개 생성 완료",
            )
        return result
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


STRATEGY_REVIEW_SYSTEM_PROMPT = """\
You are QuantAgent's Research Judge.

Review the strategy specification against what the screen actually returned, and act on
what you find - you may rewrite the entry and exit conditions, not merely comment on
them.

Revise only where a concern justifies it. Conditions the user stated explicitly stay as
they are unless they cannot be executed as written; their intent outranks your
preference. If nothing needs changing, say so and leave the conditions untouched - an
unnecessary edit is worse than none.

Terminology has already been researched upstream and is given to you; do not re-derive
it.

Return JSON only:
  summary           - your verdict in one paragraph
  concerns          - what is weak or unverified, each as one sentence
  changed           - whether you rewrote any condition
  rationale         - what you changed and which concern it answers
  entry_conditions  - the full entry condition list after your review
  exit_conditions   - the full exit condition list after your review
  indicators        - indicators the conditions rely on
  confidence        - your confidence in the reviewed specification
"""


class _LiveStrategyReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    concerns: list[str]
    changed: bool
    rationale: str
    entry_conditions: list[_LiveCondition]
    exit_conditions: list[_LiveCondition]
    indicators: list[str]
    confidence: float


def review_strategy_spec(
    *,
    query: str,
    strategy: dict[str, Any],
    screening: dict[str, Any],
    research: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Judge the strategy once, with the authority to rewrite its conditions.

    This replaced a three-way bull/bear/judge debate that cost three web-searching
    calls and changed nothing: its verdict was appended to `assumptions` and the
    conditions that got code-generated were identical either way. One reviewer that can
    actually edit the specification is worth more than three that only comment.

    No web search here - screening research already resolved the terminology, and this
    call reasons about the strategy against the screen's own results.
    """

    if not is_live_llm_provider():
        return None

    expected_json_schema = _LiveStrategyReview.model_json_schema()
    context = {"query": query, "strategy": strategy, "screening": screening}
    if research:
        context["terminology"] = research
    request = LLMJsonRequest(
        schema_name=STRATEGY_REVIEW_SCHEMA_NAME,
        system_prompt=STRATEGY_REVIEW_SYSTEM_PROMPT,
        user_prompt=_user_prompt(context, expected_json_schema),
        temperature=0.0,
        task_type="strategy_review",
        prompt_template_name=STRATEGY_REVIEW_PROMPT_TEMPLATE_NAME,
        prompt_version=STRATEGY_REVIEW_PROMPT_VERSION,
        response_schema=expected_json_schema,
        variables_jsonb={**context, "expected_json_schema": expected_json_schema},
    )
    try:
        with activity_role("RESEARCH_JUDGE"):
            report_activity("role_started", task="strategy review")
            payload = create_llm_client(role="STRATEGY_REVIEW").generate_json(request)
        parsed = _LiveStrategyReview.model_validate(payload)
    except (LLMClientError, ValidationError, ValueError, TypeError):
        return None
    with activity_role("RESEARCH_JUDGE"):
        report_activity(
            "role_completed",
            summary=parsed.summary,
            evidence=[],
            concerns=list(parsed.concerns),
            recommendation="revised" if parsed.changed else "approved",
            confidence=parsed.confidence,
        )
    return parsed.model_dump()


SCREENING_RESEARCH_SYSTEM_PROMPT = """\
You are QuantAgent's investment-terminology researcher.

Before any query is written, work out what the user's strategy actually asks for. Use
the web search tool for any metric, indicator or concept whose definition you are not
certain of - do not rely on memory for formulas. Korean market terms are in scope.

For every quantity the strategy depends on, give its standard definition, the formula,
and the raw inputs the formula consumes (e.g. PER = price / earnings per share, inputs:
price, EPS). Where a term is ambiguous in practice, say which reading you took.

Never report that the request is too vague to work with. If it leaves something open,
pick the market-standard reading, state it as the reading you took, and carry on -
strategy_reading always describes a strategy, never a missing input.

Return JSON only:
  strategy_reading - one paragraph on what the strategy screens for
  metrics          - each with name, definition, formula, required_inputs
  citations        - sources you actually consulted, title and url
"""


class _LiveScreeningMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    definition: str
    formula: str
    required_inputs: list[str]


class _LiveScreeningResearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_reading: str
    metrics: list[_LiveScreeningMetric]
    citations: list[_LiveRoleCitation]


def research_screening_terms(*, query: str) -> dict[str, Any] | None:
    """Resolve the strategy's terminology before any SQL is attempted.

    Formulas are researched rather than recalled: the previous design hardcoded how each
    metric is computed and blocked PER on a wrong assumption about needing a share
    count. Returns None with no live provider so mock mode keeps its deterministic path.
    """

    if not is_live_llm_provider():
        return None

    expected_json_schema = _LiveScreeningResearch.model_json_schema()
    context = {"query": query}
    request = LLMJsonRequest(
        schema_name=SCREENING_RESEARCH_SCHEMA_NAME,
        system_prompt=SCREENING_RESEARCH_SYSTEM_PROMPT,
        user_prompt=_user_prompt(context, expected_json_schema),
        temperature=0.0,
        enable_web_search=True,
        task_type="screening_research",
        prompt_template_name=SCREENING_RESEARCH_PROMPT_TEMPLATE_NAME,
        prompt_version=SCREENING_RESEARCH_PROMPT_VERSION,
        response_schema=expected_json_schema,
        variables_jsonb={**context, "expected_json_schema": expected_json_schema},
    )
    try:
        payload = create_llm_client(role="SCREENING_RESEARCH").generate_json(request)
        return _LiveScreeningResearch.model_validate(payload).model_dump()
    except (LLMClientError, ValidationError, ValueError, TypeError):
        return None


STRATEGY_INTENT_SYSTEM_PROMPT = """\
You are QuantAgent's strategy interpreter for Korean cash equities (KRX).

Your job is to turn WHATEVER the user typed into one concrete, backtestable strategy.
The user is not a quant and will not be asked follow-up questions - "돈 버는 전략 만들어줘",
"화학 관련주 사줘", "네가 알아서 설정해" are all valid, complete requests. Treat a vague
request as a mandate to decide, not as a defect in the input.

So: never ask the user for a market, a period, a risk level or a screening rule. Choose
them yourself, and say in `assumptions` what you chose and why. A request with nothing
specified is the easy case, not the blocked one - answer it with the strategy you would
actually run.

Use the web search tool before deciding. Look up what is currently working or in focus in
the Korean market, how the sector or theme the user named is usually screened, and the
conventional parameters for the rule you pick. Ground the choice in what you find rather
than defaulting to the same textbook rule every time; cite the sources you used.

Constraints on what you may choose:
- KRX-listed cash equities only (KOSPI/KOSDAQ). No options, futures, FX or crypto.
- Only conditions computable from daily OHLCV, technical indicators derived from it,
  and the fundamentals/consensus/flow fields listed in CAPABILITIES. If a natural
  reading of the request needs something outside that, pick the closest rule that IS
  computable and record the substitution in `assumptions`.
- `resolved_query` must stand alone: a downstream engine sees only that string, never
  the user's original words. Write it in Korean as a single screening instruction
  naming the universe/sector, the entry conditions with concrete numbers and windows,
  the exit or holding rule, and the backtest period. No hedging, no options, no
  questions - one strategy.

Set scope="unsupported" ONLY when the request is inherently about an asset class outside
KRX cash equities. Vagueness, missing parameters and unfamiliar slang are never
unsupported - resolve them.

Return JSON only:
  interpretation - one Korean sentence on what the user is asking for
  resolved_query - the self-contained Korean strategy instruction described above
  assumptions    - Korean sentences, one per decision you made for the user, each
                   giving the reason ("기간 미지정 → 최근 3년으로 백테스트합니다")
  scope          - "supported" or "unsupported"
  scope_reason   - Korean; why it is out of scope, or "" when supported
  citations      - sources you actually consulted, title and url
"""


class _LiveStrategyIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interpretation: str
    resolved_query: str
    assumptions: list[str]
    scope: Literal["supported", "unsupported"]
    scope_reason: str
    citations: list[_LiveRoleCitation]


def resolve_strategy_intent(
    *, query: str, capabilities: list[dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    """Turn any request, however vague, into one concrete strategy to run.

    This is the step that decides whether the user gets an answer or a question. Every
    stage after it reads `resolved_query` instead of the raw input, so the vagueness is
    resolved once, by a model that can search, rather than re-detected by keyword at
    each stage. Returns None with no live provider so mock mode keeps its
    deterministic path.
    """

    if not is_live_llm_provider():
        return None

    expected_json_schema = _LiveStrategyIntent.model_json_schema()
    context = {"query": query, "capabilities": capabilities or []}
    request = LLMJsonRequest(
        schema_name=STRATEGY_INTENT_SCHEMA_NAME,
        system_prompt=STRATEGY_INTENT_SYSTEM_PROMPT,
        user_prompt=(
            "Resolve this request into one runnable strategy.\n"
            "EXPECTED_JSON_SCHEMA="
            f"{json.dumps(expected_json_schema, ensure_ascii=False, sort_keys=True)}\n"
            "CAPABILITIES="
            f"{json.dumps(context['capabilities'], ensure_ascii=False, sort_keys=True, default=str)}\n"
            f"USER_QUERY={query}"
        ),
        # Not 0.0: the point of this call is to pick a strategy worth running, and a
        # frozen decoder returns the same textbook rule for every vague request.
        temperature=0.4,
        enable_web_search=True,
        task_type="strategy_intent",
        prompt_template_name=STRATEGY_INTENT_PROMPT_TEMPLATE_NAME,
        prompt_version=STRATEGY_INTENT_PROMPT_VERSION,
        response_schema=expected_json_schema,
        variables_jsonb={**context, "expected_json_schema": expected_json_schema},
    )
    try:
        payload = create_llm_client(role="STRATEGY_INTENT").generate_json(request)
        resolved = _LiveStrategyIntent.model_validate(payload)
    except (LLMClientError, ValidationError, ValueError, TypeError):
        return None
    if not resolved.resolved_query.strip():
        # An empty resolution would silently hand the raw vague query back to the
        # screening stage - the exact failure this call exists to prevent.
        return None
    return resolved.model_dump()


SCREENING_SQL_SYSTEM_PROMPT = """\
You are QuantAgent's stock screening engineer for a Korean equity warehouse.

Translate the strategy into ONE PostgreSQL SELECT returning the stocks that satisfy it.
You are given the real schema, how full each table is, and the warehouse's known
pitfalls - follow them exactly.

Reason before writing: name each quantity the strategy needs, map it onto columns, then
compose the query. If a quantity cannot be derived from this schema, leave it out of the
conditions and report it under unmet_requirements naming the missing input. Never
substitute an unrelated column for a condition you cannot express.

If earlier attempts are supplied, fix precisely what they got wrong. When a previous
attempt matched nothing, the conditions were too tight for this particular date -
loosen the least load-bearing one rather than abandoning the strategy.

Also express the same conditions in a structured form, so the screen (run today) and
the backtest (run over history) share one definition instead of drifting apart. Each
entry/exit condition has:
  left            - the metric being tested (a column or a metric you named)
  operator        - one of lt, lte, gt, gte, eq, ne, between, cross_above, cross_below
  right           - a number, or another metric name for a relative comparison
  window          - rolling window in trading days, if the metric is over a window
                    (52-week high -> left "high", window 252, aggregate "max")
  aggregate       - max | min | avg | sum | last, how the window is reduced
  scale           - multiplier on the right side (volume >= 1.5x its 20d average ->
                    right "volume", window 20, aggregate "avg", scale 1.5)
  consecutive     - number of periods the condition must hold in a row (4 quarters up)
  universe_rank_pct - top-percentile cross-sectional cut instead of an absolute value
                    (top 20% by revenue growth -> 0.2)
Leave the optional fields null when a plain comparison suffices. The SQL and the
structured conditions MUST describe the same rule.

Return JSON only:
  reasoning          - how each condition maps onto columns
  sql                - the SELECT (single statement, no semicolon, no DDL/DML)
  metrics            - metric column names the SELECT returns
  entry_conditions   - structured entry conditions (as above)
  exit_conditions    - structured exit conditions, if the strategy implies any
  unmet_requirements - conditions you could not express, each naming the missing input
"""


class _LiveStructuredCondition(BaseModel):
    """Strict-schema twin of Condition for AOAI structured output.

    Azure requires every property in `required`, so the optional windowing fields are
    present-but-nullable here; _structured_condition() below drops the nulls before
    validating against the real Condition.
    """

    model_config = ConfigDict(extra="forbid")

    left: str
    operator: ConditionOperator
    right: float | str | list[float]
    window: int | None
    aggregate: Literal["max", "min", "avg", "sum", "last"] | None
    scale: float | None
    consecutive: int | None
    universe_rank_pct: float | None


class _LiveScreeningSQL(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: str
    sql: str
    metrics: list[str]
    entry_conditions: list[_LiveStructuredCondition]
    exit_conditions: list[_LiveStructuredCondition]
    unmet_requirements: list[str]


def generate_screening_sql(
    *,
    query: str,
    schema_context: str,
    schema_notes: str,
    output_contract: str,
    research: dict[str, Any] | None = None,
    previous_attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Ask the model to author the screening SELECT."""

    if not is_live_llm_provider():
        return None

    expected_json_schema = _LiveScreeningSQL.model_json_schema()
    context: dict[str, Any] = {
        "query": query,
        "schema": schema_context,
        "pitfalls": schema_notes,
        "output_contract": output_contract,
    }
    if research:
        context["terminology"] = research
    if previous_attempts:
        # Each retry sees what the previous SQL did and why it was unusable, so it
        # corrects that specific failure instead of guessing again.
        context["previous_attempts"] = previous_attempts
    request = LLMJsonRequest(
        schema_name=SCREENING_SQL_SCHEMA_NAME,
        system_prompt=SCREENING_SQL_SYSTEM_PROMPT,
        user_prompt=_user_prompt(context, expected_json_schema),
        temperature=0.0,
        task_type="screening_sql",
        prompt_template_name=SCREENING_SQL_PROMPT_TEMPLATE_NAME,
        prompt_version=SCREENING_SQL_PROMPT_VERSION,
        response_schema=expected_json_schema,
        variables_jsonb={**context, "expected_json_schema": expected_json_schema},
    )
    try:
        payload = create_llm_client(role="SCREENING_SQL").generate_json(request)
        parsed = _LiveScreeningSQL.model_validate(payload)
    except (LLMClientError, ValidationError, ValueError, TypeError):
        return None
    result = parsed.model_dump()
    # Validate the structured conditions against the real Condition (dropping the AOAI
    # nulls). A malformed structure must not sink the screen - the SQL still ran - so bad
    # conditions are simply omitted, and the SQL remains the source of truth until the
    # backtest compiler consumes these.
    result["entry_conditions"] = _clean_structured_conditions(parsed.entry_conditions)
    result["exit_conditions"] = _clean_structured_conditions(parsed.exit_conditions)
    return result


def _clean_structured_conditions(
    conditions: list["_LiveStructuredCondition"],
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for condition in conditions:
        fields = {key: value for key, value in condition.model_dump().items() if value is not None}
        try:
            cleaned.append(Condition.model_validate(fields).model_dump(exclude_none=True))
        except ValidationError:
            _logger.warning("screening returned an invalid structured condition; dropping it")
    return cleaned


STRATEGY_REVISION_SYSTEM_PROMPT = """\
You are QuantAgent's Research Judge, acting on your own verdict.

You have just reviewed a strategy and raised concerns. Now act on them: revise the
entry and exit conditions so the concerns are addressed, and say what you changed.

Revise only what your concerns justify. Keep every condition the user stated explicitly
unless it is unusable as written - their intent outranks your preference. If the
concerns do not warrant any change, return the conditions unchanged and set changed to
false; an unnecessary edit is worse than none.

Return JSON only:
  changed          - whether you altered anything
  rationale        - what you changed and which concern it answers
  entry_conditions - the full revised entry condition list
  exit_conditions  - the full revised exit condition list
  indicators       - indicators the revised conditions rely on
  confidence       - your confidence in the revised specification
"""


def revise_strategy_conditions(
    *,
    query: str,
    strategy: dict[str, Any],
    judge: dict[str, Any],
    fallback: StrategyConditionsPayload,
) -> dict[str, Any] | None:
    """Let the Research Judge actually change the strategy it just criticised.

    The judge's verdict used to land only as a sentence appended to `assumptions` and a
    +0.03 confidence bump - the conditions that get code-generated and backtested were
    never touched, so four web-search calls produced commentary and nothing else.

    Returns None when the judge changed nothing or the revision was unusable, leaving
    the original specification in place.
    """

    if not is_live_llm_provider():
        return None

    expected_json_schema = _LiveStrategyRevision.model_json_schema()
    context = {
        "query": query,
        "current_strategy": strategy,
        "judge_verdict": judge,
    }
    request = LLMJsonRequest(
        schema_name=STRATEGY_REVISION_SCHEMA_NAME,
        system_prompt=STRATEGY_REVISION_SYSTEM_PROMPT,
        user_prompt=_user_prompt(context, expected_json_schema),
        temperature=0.0,
        task_type="strategy_revision",
        prompt_template_name=STRATEGY_REVISION_PROMPT_TEMPLATE_NAME,
        prompt_version=STRATEGY_REVISION_PROMPT_VERSION,
        response_schema=expected_json_schema,
        variables_jsonb={**context, "expected_json_schema": expected_json_schema},
    )
    try:
        payload = create_llm_client(role="STRATEGY_REVISION").generate_json(request)
        parsed = _LiveStrategyRevision.model_validate(payload)
    except (LLMClientError, ValidationError, ValueError, TypeError):
        return None
    if not parsed.changed or not parsed.entry_conditions:
        return None
    return parsed.model_dump()


class _LiveStrategyRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changed: bool
    rationale: str
    entry_conditions: list[_LiveCondition]
    exit_conditions: list[_LiveCondition]
    indicators: list[str]
    confidence: float


REPORT_WRITEUP_SYSTEM_PROMPT = """\
You are QuantAgent's report writer for retail investors.

The decision has already been made upstream: research judged the strategy, the signal
stage judged BUY/HOLD/DROP, and the risk manager set the final action. Do not re-decide
any of it. Your job is to explain that outcome faithfully.

Write a balanced account from the material given - the supporting case, the objections,
the backtest numbers and what data was actually available. State the strengths and the
limitations with equal candour; if a condition could not be verified, say so rather than
implying it was. Never present an unverified condition as validated.

Return JSON only with summary, evidence, concerns, recommendation, confidence,
validation_results and citations.
"""


def generate_report_writeup(
    *,
    context: dict[str, Any],
    fallback: RoleDebatePayload,
) -> RoleDebatePayload:
    """Write the report's interpretation in one call.

    This replaced a three-way bull/bear/judge debate. That debate re-argued a decision
    the signal stage had already reached - its own fallback simply echoed the risk
    manager's action - so it cost three provider calls to restate a settled conclusion.
    The opposing views it needed are already in state from the research and signal
    debates and are passed in as material.
    """

    expected_json_schema = _role_debate_output_schema()
    request = LLMJsonRequest(
        schema_name=REPORT_WRITEUP_SCHEMA_NAME,
        system_prompt=REPORT_WRITEUP_SYSTEM_PROMPT,
        user_prompt=_user_prompt(context, expected_json_schema),
        temperature=0.0,
        task_type="report_writeup",
        prompt_template_name=REPORT_WRITEUP_PROMPT_TEMPLATE_NAME,
        prompt_version=REPORT_WRITEUP_PROMPT_VERSION,
        response_schema=expected_json_schema,
        variables_jsonb={**context, "expected_json_schema": expected_json_schema},
    )
    try:
        with activity_role("REPORT_WRITER"):
            report_activity("role_started", task="report writeup")
            payload = create_llm_client(role="REPORT_WRITER").generate_json(request)
        provider_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"role", "fallback_reasons"}
        }
        if is_live_llm_provider():
            provider_payload = _LiveRoleDebateOutput.model_validate(provider_payload).model_dump()
        written = RoleDebatePayload.model_validate({**provider_payload, "role": "REPORT_WRITER"})
        with activity_role("REPORT_WRITER"):
            report_activity(
                "role_completed",
                summary=written.summary,
                evidence=list(written.evidence),
                concerns=list(written.concerns),
                recommendation=written.recommendation,
                confidence=written.confidence,
            )
        return written
    except (LLMClientError, ValidationError, ValueError, TypeError) as exc:
        # Unlike the debates, this never re-raises on a live provider. By the time the
        # report is written the screen, backtest and risk decision are all done; losing
        # the entire analysis because the write-up failed its schema check throws away
        # everything that did work. The fallback still carries the real decision.
        _logger.warning("report write-up failed; using deterministic fallback: %s", exc)
        reasons = [*fallback.fallback_reasons, f"{type(exc).__name__}: {exc}"]
        return fallback.model_copy(update={"fallback_reasons": reasons})


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
