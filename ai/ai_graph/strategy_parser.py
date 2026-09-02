"""Natural-language strategy parsing at the research execution boundary.

The parser accepts only a small, versioned JSON shape from the live provider.  A
non-live provider keeps the local contract usable with a bounded generic parser; it
is never used as evidence for an operational backtest.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ai_graph.llm import LLMClient, LLMClientError, LLMJsonRequest, create_llm_client, is_live_llm_provider
from ai_graph.nodes.condition_compiler import canonical_metric, supported_metrics

STRATEGY_PARSE_SCHEMA_NAME = "quantagent.strategy_parse.v1"
STRATEGY_PARSE_PROMPT_VERSION = "v1"


class StrategyConditionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str = Field(min_length=1, max_length=64)
    comparator: Literal["lt", "lte", "gt", "gte", "eq", "ne"]
    value: float
    lookback: int = Field(ge=1, le=2000)
    role: Literal["entry", "exit"]

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not math.isfinite(value) or abs(value) > 1_000_000_000:
            raise ValueError("condition value is outside the supported range")
        return value


class UnsupportedStrategyConditionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str = Field(min_length=1, max_length=240)
    reason: str = Field(min_length=1, max_length=240)


class IndicatorSelectionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=240)


class StrategyParseResultV1(BaseModel):
    """Validated strategy interpretation shown to the user before confirmation."""

    model_config = ConfigDict(extra="forbid")

    market: Literal["KRX"] = "KRX"
    timeframe: Literal["daily"] = "daily"
    entry_conditions: list[StrategyConditionV1] = Field(default_factory=list, max_length=3)
    exit_conditions: list[StrategyConditionV1] = Field(default_factory=list, max_length=3)
    unsupported_conditions: list[UnsupportedStrategyConditionV1] = Field(
        default_factory=list, max_length=10
    )
    clarification_required: bool = False
    explanation: str = Field(min_length=1, max_length=500)
    indicator_selections: list[IndicatorSelectionV1] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def roles_match_sections(self) -> StrategyParseResultV1:
        if any(item.role != "entry" for item in self.entry_conditions):
            raise ValueError("entry_conditions must use role=entry")
        if any(item.role != "exit" for item in self.exit_conditions):
            raise ValueError("exit_conditions must use role=exit")
        return self


class StrategyParseError(ValueError):
    """A provider or schema failure that must not issue an execution token."""


StrategyParseOutputV1 = StrategyParseResultV1


class _LiveCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    comparator: Literal["lt", "lte", "gt", "gte", "eq", "ne"]
    value: float
    lookback: int
    role: Literal["entry", "exit"]


class _LiveUnsupportedCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str
    reason: str


class _LiveStrategyParseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: Literal["KRX"]
    timeframe: Literal["daily"]
    entry_conditions: list[_LiveCondition] = Field(max_length=3)
    exit_conditions: list[_LiveCondition] = Field(max_length=3)
    unsupported_conditions: list[_LiveUnsupportedCondition] = Field(max_length=10)
    clarification_required: bool
    explanation: str


def parse_natural_language_strategy(
    query: str,
    *,
    available_metrics: Sequence[str] | None = None,
    llm_client: LLMClient | None = None,
    use_llm: bool | None = None,
) -> StrategyParseResultV1:
    """Parse and validate a strategy against the server's available metric names."""

    if not query.strip():
        raise StrategyParseError("strategy query is empty")
    metrics = _metric_catalog(available_metrics)
    use_live_llm = is_live_llm_provider() if use_llm is None else use_llm
    if use_live_llm:
        # A complete, supported rule does not need a second interpretation before it
        # can be reviewed.  In particular, natural Korean RSI pairs such as
        # ``RSI가 30 이하이고 RSI가 70 이상`` are already an unambiguous execution
        # rule.  Sending them to the provider here made admission depend on an
        # otherwise unnecessary network request and let a parser outage turn a valid
        # strategy into a clarification/409 response.  Free-form or incomplete
        # strategies still proceed to the live structured parser below, where the AI
        # can interpret their domain context before the later research/backtest job.
        deterministic = _deterministic_parse(query, metrics)
        if _is_complete_supported_parse(deterministic):
            return deterministic
        try:
            payload = (llm_client or create_llm_client(role="STRATEGY_PARSE")).generate_json(
                _llm_request(query, metrics)
            )
            if not isinstance(payload, Mapping):
                raise TypeError("strategy parser response must be a JSON object")
            payload = _coerce_unsupported_conditions(payload)
            raw = _LiveStrategyParseOutput.model_validate(payload)
            return _normalize(raw.model_dump(), metrics)
        except (
            LLMClientError,
            ValidationError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
            AssertionError,
        ) as exc:
            raise StrategyParseError(f"strategy JSON validation failed: {type(exc).__name__}") from exc
    return _deterministic_parse(query, metrics)


def _is_complete_supported_parse(result: StrategyParseResultV1) -> bool:
    """Whether the bounded parser has an execution-ready result.

    This is deliberately stricter than merely finding two numeric conditions: no
    unsupported condition or pending clarification may bypass the AI-assisted review
    path.  It only prevents redundant provider calls for a complete rule whose
    semantics already fit the versioned execution contract.
    """

    return bool(
        result.entry_conditions
        and result.exit_conditions
        and not result.unsupported_conditions
        and not result.clarification_required
    )


def _llm_request(query: str, metrics: Sequence[str]) -> LLMJsonRequest:
    schema = _LiveStrategyParseOutput.model_json_schema()
    prompt = (
        "You are QuantAgent's strategy parser. Return JSON only matching "
        "EXPECTED_JSON_SCHEMA. Interpret general KRX daily conditions, separating "
        "entry and exit/evaluation rules. Use only the supplied server metrics; "
        "put unavailable or ambiguous requests in unsupported_conditions. "
        "Each condition requires metric, comparator, numeric value, lookback, and role. "
        "Do not invent indicators, tickers, orders, or market/timeframe values.\n\n"
        f"SERVER_METRICS={json.dumps(list(metrics), ensure_ascii=False)}\n"
        f"EXPECTED_JSON_SCHEMA={json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
    )
    return LLMJsonRequest(
        schema_name=STRATEGY_PARSE_SCHEMA_NAME,
        system_prompt=prompt,
        user_prompt=json.dumps({"natural_language": query}, ensure_ascii=False),
        temperature=0.0,
        task_type="strategy_parse",
        prompt_template_name="strategy_parse",
        prompt_version=STRATEGY_PARSE_PROMPT_VERSION,
        response_schema=schema,
        variables_jsonb={"query": query, "server_metrics": list(metrics)},
    )


def _normalize(payload: Mapping[str, Any], metrics: Sequence[str]) -> StrategyParseResultV1:
    if len(payload["entry_conditions"]) > 3 or len(payload["exit_conditions"]) > 3:
        raise ValueError("each condition section accepts at most three conditions")
    if len(payload["unsupported_conditions"]) > 10:
        raise ValueError("unsupported_conditions accepts at most ten conditions")
    allowed = _allowed_metric_map(metrics)
    unsupported = [UnsupportedStrategyConditionV1.model_validate(item) for item in payload["unsupported_conditions"]]
    entry: list[StrategyConditionV1] = []
    exit_: list[StrategyConditionV1] = []
    selections: dict[str, IndicatorSelectionV1] = {}
    for section, role, target in (
        (payload["entry_conditions"], "entry", entry),
        (payload["exit_conditions"], "exit", exit_),
    ):
        for raw in section:
            if raw.get("role") != role:
                raise ValueError(f"{role} condition has the wrong role")
            condition = StrategyConditionV1.model_validate({**raw, "role": role})
            requested = _normalized_metric(condition.metric)
            selected = allowed.get(requested) or allowed.get(_normalized_metric(canonical_metric(requested)))
            if selected is None:
                unsupported.append(
                    UnsupportedStrategyConditionV1(
                        condition=_condition_text(condition),
                        reason="서버에 해당 지표 데이터가 없어 조건을 사용할 수 없습니다.",
                    )
                )
                continue
            normalized = condition.model_copy(update={"metric": selected, "role": role})
            _validate_metric_value(normalized)
            target.append(normalized)
            if selected not in selections:
                selections[selected] = IndicatorSelectionV1(
                    metric=selected,
                    reason="서버 지표 목록에 존재하며 요청 의미와 가장 가까운 지표로 선택했습니다.",
                )
    clarification = bool(
        payload["clarification_required"]
        or unsupported
        or not entry
        or not exit_
    )
    return StrategyParseResultV1(
        market=payload["market"],
        timeframe=payload["timeframe"],
        entry_conditions=entry[:3],
        exit_conditions=exit_[:3],
        unsupported_conditions=unsupported[:10],
        clarification_required=clarification,
        explanation=str(payload["explanation"]),
        indicator_selections=list(selections.values()),
    )


def _coerce_unsupported_conditions(payload: Mapping[str, Any]) -> dict[str, Any]:
    values = payload.get("unsupported_conditions", [])
    normalized = [
        item if isinstance(item, Mapping) else {"condition": str(item), "reason": "서버에서 지원하지 않는 조건입니다."}
        for item in values
    ]
    return {**payload, "unsupported_conditions": normalized}


def _deterministic_parse(query: str, metrics: Sequence[str]) -> StrategyParseResultV1:
    """Bounded local fallback for tests/dev; no fixture result is produced."""

    allowed = _allowed_metric_map(metrics)
    text = query.lower()
    found: list[StrategyConditionV1] = []
    unsupported: list[UnsupportedStrategyConditionV1] = []
    metric_patterns = (
        (r"(?<![a-z0-9_])rsi(?![a-z0-9_])(?:\s*\((\d+)\))?", "rsi", 14),
        (r"(?:\bsma\b|\bma\b|이동\s*평균|평균선)\s*[_-]?(\d+)?", "sma", 20),
        (r"(?<![a-z0-9_])ema(?![a-z0-9_])\s*[_-]?(\d+)?", "ema", 20),
        (r"(?<![a-z0-9_])macd(?![a-z0-9_])", "macd", 0),
        (r"(?:거래량|\bvolume\b)", "volume", 0),
        (r"(?:볼린저(?:\s*밴드)?\s*(?:상단|upper)?|\bbb_upper\b)", "bb_upper", 20),
        (r"(?<![a-z0-9_])adx(?![a-z0-9_])", "adx", 14),
        (r"(?<![a-z0-9_])atr(?![a-z0-9_])", "atr", 14),
        (r"(?<![a-z0-9_])mfi(?![a-z0-9_])", "mfi", 14),
        (r"(?<![a-z0-9_])cci(?![a-z0-9_])", "cci", 20),
        (r"(?<![a-z0-9_])obv(?![a-z0-9_])", "obv", 0),
        (r"(?<![a-z0-9_])willr(?![a-z0-9_])", "willr", 14),
    )
    for metric_pattern, base_metric, default_lookback in metric_patterns:
        for match in re.finditer(metric_pattern, text, re.IGNORECASE):
            lookback = int(match.group(1) or default_lookback) if match.lastindex else default_lookback
            window = _condition_window(text, match.end())
            threshold_match = re.search(
                r"(?:가|는|은|이)?\s*(-?\d+(?:\.\d+)?)\s*"
                r"(이하|미만|이상|초과|배|below|under|above|over|<=|>=|<|>|같다|동일|equal|=)",
                window,
                re.IGNORECASE,
            )
            if not threshold_match:
                continue
            comparator_word = threshold_match.group(2).lower()
            comparator = "lte" if comparator_word in {"이하", "미만", "below", "under", "<=", "<"} else "gte" if comparator_word in {"이상", "초과", "배", "above", "over", ">=", ">"} else "eq"
            if base_metric == "volume" and "배" in window:
                metric = "volume_ratio_20"
            else:
                metric = base_metric if base_metric in {"rsi", "macd", "volume", "bb_upper", "adx", "atr", "mfi", "cci", "obv", "willr"} else f"{base_metric}{lookback}"
            metric_key = allowed.get(_normalized_metric(metric)) or allowed.get(
                _normalized_metric(canonical_metric(metric))
            )
            condition = StrategyConditionV1(
                metric=metric_key or metric,
                comparator=comparator,
                value=float(threshold_match.group(1)),
                lookback=lookback or 14,
                role=_role_from_context(text, match.start(), match.end()),
            )
            try:
                _validate_metric_value(condition)
            except ValueError:
                continue
            if metric_key is None:
                unsupported.append(
                    UnsupportedStrategyConditionV1(
                        condition=_condition_text(condition),
                        reason="서버에 해당 지표 데이터가 없어 조건을 사용할 수 없습니다.",
                    )
                )
                continue
            found.append(condition)
            # Korean natural language commonly omits a repeated indicator name:
            # "RSI가 30 이하일 때 진입하고 70 이상일 때 청산".  The second
            # clause is still an RSI condition, not a missing user parameter.  Keep
            # this bounded to an immediately joined, action-labelled clause so a
            # later unrelated number can never be adopted as an indicator threshold.
            found.extend(
                _implicit_metric_continuations(
                    text=text,
                    threshold_end=match.end() + threshold_match.end(),
                    metric=metric_key,
                    lookback=lookback or 14,
                )
            )
    # The old shorthand has no role words: interpret low threshold first and high
    # threshold second, which preserves the public RSI regression contract.
    if found and not re.search(r"매수|진입|entry|매도|종료|exit|청산", text, re.IGNORECASE):
        for index, condition in enumerate(found):
            found[index] = condition.model_copy(update={"role": "entry" if index == 0 else "exit"})
    entry_candidates = [item for item in found if item.role == "entry"]
    exit_candidates = [item for item in found if item.role == "exit"]
    for section, candidates in (("진입", entry_candidates), ("종료", exit_candidates)):
        for condition in candidates[3:]:
            unsupported.append(
                UnsupportedStrategyConditionV1(
                    condition=_condition_text(condition),
                    reason=f"{section} 조건은 한 전략에서 최대 3개까지만 사용할 수 있습니다.",
                )
            )
    entry = entry_candidates[:3]
    exit_ = exit_candidates[:3]
    selections = [
        IndicatorSelectionV1(
            metric=metric,
            reason="개발 환경의 허용 지표 목록에서 요청과 일치하는 지표를 선택했습니다.",
        )
        for metric in dict.fromkeys(item.metric for item in [*entry, *exit_])
    ]
    result = StrategyParseResultV1(
        entry_conditions=entry,
        exit_conditions=exit_,
        unsupported_conditions=unsupported,
        clarification_required=bool(unsupported) or not (entry and exit_),
        explanation="자연어 조건을 진입 조건과 종료 조건으로 나누어 해석했습니다.",
        indicator_selections=selections,
    )
    return result


def _metric_catalog(metrics: Sequence[str] | None) -> list[str]:
    values = list(metrics if metrics is not None else supported_metrics())
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _normalized_metric(value: str) -> str:
    return re.sub(r"[\s-]+", "_", str(value).strip().lower())


def _allowed_metric_map(metrics: Sequence[str]) -> dict[str, str]:
    allowed: dict[str, str] = {}
    # Prefer the compiler's canonical spelling over aliases such as ``ma20``.
    for item in metrics:
        if canonical_metric(item) == _normalized_metric(item):
            allowed.setdefault(_normalized_metric(item), item)
    for item in metrics:
        allowed.setdefault(_normalized_metric(item), canonical_metric(item))
        allowed.setdefault(_normalized_metric(canonical_metric(item)), canonical_metric(item))
    return allowed


def _validate_metric_value(condition: StrategyConditionV1) -> None:
    metric = _normalized_metric(condition.metric)
    if metric in {"rsi", "mfi", "stoch_k", "stoch_d"} and not 0 <= condition.value <= 100:
        raise ValueError("bounded oscillator value is outside the supported range")
    if metric == "willr" and not -100 <= condition.value <= 0:
        raise ValueError("willr value is outside the supported range")


def _condition_text(condition: StrategyConditionV1) -> str:
    return f"{condition.metric} {condition.comparator} {condition.value:g} ({condition.lookback})"


def _role_from_context(text: str, start: int, end: int) -> Literal["entry", "exit"]:
    context_start = max(0, start - 50)
    context_end = min(len(text), end + 80)
    context = text[context_start:context_end]
    anchor = start - context_start
    entry_hits = [match.start() for match in re.finditer(r"매수|진입|entry|buy", context, re.IGNORECASE)]
    exit_hits = [match.start() for match in re.finditer(r"매도|종료|청산|exit|sell", context, re.IGNORECASE)]
    # A role marker after the metric belongs to that condition even when a previous
    # condition's marker is closer in the shared conjunction context.
    next_entry = min((hit for hit in entry_hits if hit >= anchor), default=None)
    next_exit = min((hit for hit in exit_hits if hit >= anchor), default=None)
    if next_entry is not None or next_exit is not None:
        return "exit" if next_exit is not None and (next_entry is None or next_exit < next_entry) else "entry"
    entry_distance = min((abs(hit - anchor) for hit in entry_hits), default=10_000)
    exit_distance = min((abs(hit - anchor) for hit in exit_hits), default=10_000)
    return "exit" if exit_distance < entry_distance else "entry"


def _condition_window(text: str, end: int) -> str:
    window = text[end : end + 100]
    boundary = re.search(r"(?:그리고|이고|하고|,|;)", window)
    return window[: boundary.start()] if boundary else window


_IMPLICIT_METRIC_CONTINUATION = re.compile(
    r"(?:그리고|이고|하고|,|;)\s*"
    r"(?:가|는|은|이)?\s*"
    r"(?P<value>-?\d+(?:\.\d+)?)\s*"
    r"(?P<comparator>이하|미만|이상|초과|below|under|above|over|<=|>=|<|>)\s*"
    r"(?:일\s*때|이면|인\s*경우|일\s*경우)?\s*"
    r"(?P<action>매수|진입|entry|buy|매도|종료|청산|exit|sell)",
    re.IGNORECASE,
)


def _implicit_metric_continuations(
    *,
    text: str,
    threshold_end: int,
    metric: str,
    lookback: int,
) -> list[StrategyConditionV1]:
    """Infer only adjacent, action-labelled thresholds that omit a repeated metric."""

    tail = text[threshold_end : threshold_end + 160]
    conditions: list[StrategyConditionV1] = []
    for match in _IMPLICIT_METRIC_CONTINUATION.finditer(tail):
        comparator_word = match.group("comparator").lower()
        comparator = (
            "lte"
            if comparator_word in {"이하", "미만", "below", "under", "<=", "<"}
            else "gte"
        )
        action = match.group("action").lower()
        role: Literal["entry", "exit"] = (
            "entry" if action in {"매수", "진입", "entry", "buy"} else "exit"
        )
        condition = StrategyConditionV1(
            metric=metric,
            comparator=comparator,
            value=float(match.group("value")),
            lookback=lookback,
            role=role,
        )
        try:
            _validate_metric_value(condition)
        except ValueError:
            continue
        conditions.append(condition)
    return conditions


__all__ = [
    "IndicatorSelectionV1",
    "StrategyConditionV1",
    "StrategyParseError",
    "StrategyParseOutputV1",
    "StrategyParseResultV1",
    "UnsupportedStrategyConditionV1",
    "parse_natural_language_strategy",
]
