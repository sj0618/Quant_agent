"""Research-only public contracts for the RMP vertical slice.

The legacy graph envelope is an internal execution shape.  This module deliberately
does not import it: callers must cross a narrow, versioned boundary before exposing a
rule review or a result to a browser.  In particular, draft tokens never contain the
raw user text and a result cannot be ``ready`` without verified PostgreSQL EOD
provenance.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from os import environ
from threading import Lock
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_graph.exploration_policy import (
    ActiveExplorationPolicyV2,
    select_exploration_templates,
)
from ai_graph.quant_strategy import classify_strategy_request
from ai_graph.strategy_parser import (
    IndicatorSelectionV1,
    StrategyParseError,
    StrategyParseResultV1,
    UnsupportedStrategyConditionV1,
    parse_natural_language_strategy,
)

RULE_DRAFT_SCHEMA_VERSION = "research-rule-draft.v1"
STRATEGY_EXECUTION_SPEC_VERSION = "strategy-execution-spec.v1"
EXPLORATION_EXECUTION_SPEC_VERSION = "exploration-execution-spec.v2"
RULE_DRAFT_POLICY_HASH = hashlib.sha256(
    b"quantagent-research-only-preflight-v1"
).hexdigest()
RULE_DRAFT_HMAC_SECRET_ENV = "AI_RULE_DRAFT_HMAC_SECRET"
RULE_DRAFT_HMAC_KEY_VERSION_ENV = "AI_RULE_DRAFT_HMAC_KEY_VERSION"
DEFAULT_RULE_DRAFT_TTL_SECONDS = 600


class RuleConditionV1(BaseModel):
    """One user-editable research condition.

    ``entry`` and ``exit`` describe rule boundaries only; they are intentionally not
    trading instructions and are never rendered as order actions.
    """

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(min_length=1, max_length=64)
    comparator: Literal["lt", "lte", "gt", "gte", "eq", "ne"]
    value: float
    lookback: int = Field(default=14, ge=1, le=2000)
    role: Literal["entry", "exit"]

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not math.isfinite(value) or abs(value) > 1_000_000_000:
            raise ValueError("condition value is outside the supported range")
        return value

    @model_validator(mode="after")
    def metric_value_range(self) -> RuleConditionV1:
        metric = self.metric.strip().lower().replace("-", "_")
        if metric in {"rsi", "rsi_14", "mfi", "stoch_k", "stoch_d"} and not 0 <= self.value <= 100:
            raise ValueError("bounded oscillator value is outside the supported range")
        if metric == "willr" and not -100 <= self.value <= 0:
            raise ValueError("willr value is outside the supported range")
        return self


class CanonicalRuleV1(BaseModel):
    """The bounded structured form signed by a RuleDraftV1 token."""

    model_config = ConfigDict(extra="forbid")

    market: Literal["KRX"] = "KRX"
    timeframe: Literal["daily"] = "daily"
    entry_conditions: list[RuleConditionV1] = Field(default_factory=list, max_length=3)
    exit_conditions: list[RuleConditionV1] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def separate_condition_roles(self) -> CanonicalRuleV1:
        if any(condition.role != "entry" for condition in self.entry_conditions):
            raise ValueError("entry_conditions must use the entry role")
        if any(condition.role != "exit" for condition in self.exit_conditions):
            raise ValueError("exit_conditions must use the exit role")
        return self

    @property
    def is_executable(self) -> bool:
        return bool(self.entry_conditions and self.exit_conditions)


# ``CanonicalRuleV1`` was the name exposed by the retired research-only path.  The
# primary product path now calls the same bounded, versioned object what it is: an
# execution specification.  Keep the old symbol as a compatibility alias while API
# clients migrate to the explicit contract name.
StrategyExecutionSpecV1 = CanonicalRuleV1


class ExplorationCandidateRefV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: str = Field(pattern=r"^qb-v2-[a-z0-9-]+$")
    execution_signature: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExplorationExecutionSpecV2(BaseModel):
    """Policy and candidate identities sealed before any performance is observed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: Literal["exploratory_return_seeking"] = "exploratory_return_seeking"
    market: Literal["KRX"] = "KRX"
    timeframe: Literal["daily"] = "daily"
    policy_version: str = Field(min_length=1, max_length=100)
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_version: str = Field(min_length=1)
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: list[ExplorationCandidateRefV2] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def candidate_ids_are_unique(self) -> "ExplorationExecutionSpecV2":
        ids = [candidate.catalog_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("exploration candidates must be unique")
        return self

    @property
    def is_executable(self) -> bool:
        return True


ExecutionSpecV1OrV2 = CanonicalRuleV1 | ExplorationExecutionSpecV2


class ExplorationCandidateReasonV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    required_data: list[str] = Field(min_length=1)


class ExplorationReviewV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: Literal["exploratory_return_seeking"] = "exploratory_return_seeking"
    research_hypothesis: str = Field(min_length=1)
    opposing_hypothesis: str = Field(min_length=1)
    market: Literal["KRX"] = "KRX"
    period: str = Field(min_length=1)
    available_metrics: list[str] = Field(min_length=1)
    defaults: list[str] = Field(min_length=1)
    alternatives: list[str] = Field(min_length=1)
    candidate_reasons: list[ExplorationCandidateReasonV2] = Field(min_length=2, max_length=10)
    limitations: list[str] = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_version: str = Field(min_length=1)
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClarificationChoiceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=240)


class RuleDraftV1(BaseModel):
    """Public parse result.  The token is opaque and contains no raw query text."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["rule_draft"] = "rule_draft"
    market: Literal["KRX"] = "KRX"
    timeframe: Literal["daily"] = "daily"
    entry_conditions: list[RuleConditionV1] = Field(default_factory=list, max_length=3)
    exit_conditions: list[RuleConditionV1] = Field(default_factory=list, max_length=3)
    unsupported_conditions: list[UnsupportedStrategyConditionV1] = Field(
        default_factory=list, max_length=10
    )
    clarification_required: bool = False
    explanation: str = Field(min_length=1, max_length=500)
    indicator_selections: list[IndicatorSelectionV1] = Field(default_factory=list, max_length=6)
    canonical_rule: CanonicalRuleV1 | None = None
    exploration: ExplorationReviewV2 | None = None
    editable_summary: str = Field(min_length=1, max_length=500)
    clarifications: list[ClarificationChoiceV1] = Field(default_factory=list, max_length=3)
    is_executable: bool
    authoring_method: Literal["deterministic", "llm"] = "deterministic"
    schema_version: Literal[RULE_DRAFT_SCHEMA_VERSION] = RULE_DRAFT_SCHEMA_VERSION
    policy_hash: str = Field(min_length=64, max_length=64)
    expires_at: datetime
    draft_token: str = Field(min_length=32)
    # The canonical execution fields are populated only when the parse is executable.
    # A clarification may show its partial legacy rule summary, but it cannot be sent to
    # the job endpoint as though it were a validated backtest specification.
    strategy_execution_spec: ExecutionSpecV1OrV2 | None = None
    spec_version: Literal[
        STRATEGY_EXECUTION_SPEC_VERSION,
        EXPLORATION_EXECUTION_SPEC_VERSION,
    ] | None = None
    spec_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    parse_token: str | None = Field(default=None, min_length=32)

    @model_validator(mode="after")
    def executable_drafts_are_complete(self) -> RuleDraftV1:
        if self.is_executable:
            if self.clarification_required:
                raise ValueError("executable drafts cannot require clarification")
            if self.unsupported_conditions:
                raise ValueError("executable drafts cannot contain unsupported conditions")
            if self.clarifications:
                raise ValueError("executable drafts cannot carry clarification choices")
            if isinstance(self.strategy_execution_spec, ExplorationExecutionSpecV2):
                if self.exploration is None or self.canonical_rule is not None:
                    raise ValueError("exploration drafts require exploration review only")
                if self.entry_conditions or self.exit_conditions:
                    raise ValueError("exploration drafts cannot carry ad-hoc conditions")
                if self.spec_version != EXPLORATION_EXECUTION_SPEC_VERSION:
                    raise ValueError("exploration drafts require the V2 spec version")
            else:
                if self.canonical_rule is None or not self.canonical_rule.is_executable:
                    raise ValueError("executable rule drafts require entry and exit conditions")
                if self.exploration is not None:
                    raise ValueError("explicit rule drafts cannot carry exploration review")
                if self.entry_conditions != self.canonical_rule.entry_conditions:
                    raise ValueError("draft conditions must match the canonical rule")
                if self.exit_conditions != self.canonical_rule.exit_conditions:
                    raise ValueError("draft conditions must match the canonical rule")
                if self.strategy_execution_spec != self.canonical_rule:
                    raise ValueError("rule drafts require a canonical execution spec")
                if self.spec_version != STRATEGY_EXECUTION_SPEC_VERSION:
                    raise ValueError("rule drafts require the V1 spec version")
            if self.strategy_execution_spec is None:
                raise ValueError("executable drafts require an execution spec")
            if self.spec_hash != canonical_rule_digest(self.strategy_execution_spec):
                raise ValueError("executable drafts require the canonical spec hash")
            if self.parse_token != self.draft_token:
                raise ValueError("executable drafts require the issued parse token")
        elif any(
            value is not None
            for value in (
                self.strategy_execution_spec,
                self.spec_version,
                self.spec_hash,
                self.parse_token,
            )
        ):
            raise ValueError("clarification drafts must not issue an execution spec or token")
        return self


class ScopeRefusalV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["scope_refusal"] = "scope_refusal"
    reason_code: Literal["personalized_investment_request"]
    explanation: str = Field(min_length=1)
    general_example: str = Field(min_length=1)
    guidance: str = Field(min_length=1)


class UnsupportedScopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["unsupported_scope"] = "unsupported_scope"
    reason_code: Literal["unsupported_asset_family"]
    explanation: str = Field(min_length=1)
    general_example: str = Field(min_length=1)
    guidance: str = Field(min_length=1)


ParseReviewV1 = Annotated[
    RuleDraftV1 | ScopeRefusalV1 | UnsupportedScopeV1,
    Field(discriminator="kind"),
]

# The new name makes the parse outcome's three states explicit without breaking older
# callers that still import ``ParseReviewV1``.
ParseOutcomeV1 = ParseReviewV1


class DraftTokenValidationError(ValueError):
    """A bounded token-validation failure safe to map to DraftConflictV1."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DraftConflictV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["draft_conflict"] = "draft_conflict"
    reason_code: Literal[
        "draft_invalid",
        "draft_expired",
        "draft_user_mismatch",
        "draft_rule_mismatch",
        "draft_replayed",
    ]
    explanation: str = Field(min_length=1)
    guidance: str = Field(min_length=1)


class ResearchJobAcceptedV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["research_job_accepted"] = "research_job_accepted"
    job_id: str = Field(min_length=1)
    status: Literal["queued"] = "queued"


@dataclass(frozen=True)
class _SignedDraft:
    token: str
    expires_at: datetime


class RuleDraftSigner:
    """HMAC signer for opaque, short-lived research rule drafts."""

    def __init__(
        self,
        secret: str,
        *,
        key_version: str = "v1",
        ttl_seconds: int = DEFAULT_RULE_DRAFT_TTL_SECONDS,
    ) -> None:
        if not secret.strip():
            raise ValueError("rule draft signing secret must not be empty")
        if not key_version.strip():
            raise ValueError("rule draft key version must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("rule draft ttl must be positive")
        self._secret = secret.encode("utf-8")
        self._key_version = key_version
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RuleDraftSigner | None:
        source = environ if env is None else env
        secret = (source.get(RULE_DRAFT_HMAC_SECRET_ENV) or "").strip()
        if not secret:
            return None
        key_version = (source.get(RULE_DRAFT_HMAC_KEY_VERSION_ENV) or "v1").strip() or "v1"
        return cls(secret, key_version=key_version)

    def issue(self, *, rule: ExecutionSpecV1OrV2 | None, user_id: str, now: datetime | None = None) -> _SignedDraft:
        issued_at = _as_utc(now or datetime.now(UTC))
        expires_at = issued_at + timedelta(seconds=self._ttl_seconds)
        claims = {
            "aud": "research-rule-draft",
            "exp": int(expires_at.timestamp()),
            "iat": int(issued_at.timestamp()),
            "key_version": self._key_version,
            "nonce": str(uuid4()),
            "policy_hash": RULE_DRAFT_POLICY_HASH,
            "rule_digest": canonical_rule_digest(rule),
            "schema_version": RULE_DRAFT_SCHEMA_VERSION,
            "user_id": user_id,
        }
        header = {"alg": "HS256", "typ": "RMP-RULE-DRAFT"}
        signing_input = f"{_encode_json(header)}.{_encode_json(claims)}".encode("ascii")
        signature = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        return _SignedDraft(
            token=f"{signing_input.decode('ascii')}.{_encode_bytes(signature)}",
            expires_at=expires_at,
        )

    def verify(
        self,
        *,
        token: str,
        rule: ExecutionSpecV1OrV2,
        user_id: str,
        now: datetime | None = None,
    ) -> str:
        try:
            encoded_header, encoded_claims, encoded_signature = token.split(".")
            header = _decode_json(encoded_header)
            claims = _decode_json(encoded_claims)
            actual_signature = _decode_bytes(encoded_signature)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise DraftTokenValidationError("draft_invalid") from None
        if header != {"alg": "HS256", "typ": "RMP-RULE-DRAFT"}:
            raise DraftTokenValidationError("draft_invalid")
        signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
        expected_signature = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(actual_signature, expected_signature):
            raise DraftTokenValidationError("draft_invalid")
        if not isinstance(claims, dict):
            raise DraftTokenValidationError("draft_invalid")
        if claims.get("aud") != "research-rule-draft" or claims.get("key_version") != self._key_version:
            raise DraftTokenValidationError("draft_invalid")
        if claims.get("schema_version") != RULE_DRAFT_SCHEMA_VERSION:
            raise DraftTokenValidationError("draft_invalid")
        if claims.get("policy_hash") != RULE_DRAFT_POLICY_HASH:
            raise DraftTokenValidationError("draft_invalid")
        if claims.get("user_id") != user_id:
            raise DraftTokenValidationError("draft_user_mismatch")
        if claims.get("rule_digest") != canonical_rule_digest(rule):
            raise DraftTokenValidationError("draft_rule_mismatch")
        expiry = claims.get("exp")
        if not isinstance(expiry, int) or expiry <= int(_as_utc(now or datetime.now(UTC)).timestamp()):
            raise DraftTokenValidationError("draft_expired")
        nonce = claims.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise DraftTokenValidationError("draft_invalid")
        return nonce


class InMemoryDraftNonceRegistry:
    """Local/test replay fence; production activation requires a durable replacement."""

    def __init__(self) -> None:
        self._consumed: set[tuple[str, str]] = set()
        self._lock = Lock()

    def consume(self, *, user_id: str, nonce: str) -> bool:
        key = (user_id, nonce)
        with self._lock:
            if key in self._consumed:
                return False
            self._consumed.add(key)
            return True


def build_rule_draft(
    *,
    query: str,
    user_id: str,
    signer: RuleDraftSigner,
    now: datetime | None = None,
    available_metrics: list[str] | tuple[str, ...] | None = None,
    llm_client: object | None = None,
    use_llm: bool | None = None,
    exploration_policy: ActiveExplorationPolicyV2 | None = None,
) -> RuleDraftV1:
    """Make a bounded natural-language rule review without retaining raw input."""

    if classify_strategy_request(query) == "automatic" and exploration_policy is not None:
        return _build_exploration_draft(
            query=query,
            user_id=user_id,
            signer=signer,
            policy_record=exploration_policy,
            now=now,
        )

    parser_uses_llm = use_llm if use_llm is not None else _live_parser_enabled()
    authoring_method = "llm" if parser_uses_llm else "deterministic"
    try:
        parsed = parse_natural_language_strategy(
            query,
            available_metrics=available_metrics,
            llm_client=llm_client,  # type: ignore[arg-type]
            use_llm=use_llm,
        )
    except StrategyParseError as exc:
        parsed = StrategyParseResultV1(
            clarification_required=True,
            explanation="조건을 허용된 JSON 구조로 해석하지 못했습니다. 지표와 수치를 다시 입력해 주세요.",
            unsupported_conditions=[
                UnsupportedStrategyConditionV1(
                    condition="입력 조건",
                    reason=f"구조화 실패({type(exc).__name__})",
                )
            ],
        )
    rule = _canonical_rule_from_parse(parsed)
    clarifications = _clarifications_for(rule, parsed)
    executable = bool(
        rule
        and rule.is_executable
        and not parsed.clarification_required
        and not parsed.unsupported_conditions
    )
    # ``draft_token`` is a review token for every response; ``parse_token`` below is
    # the one-shot execution token and is deliberately absent for incomplete parses.
    signed = signer.issue(rule=rule, user_id=user_id, now=now)
    return RuleDraftV1(
        market=parsed.market,
        timeframe=parsed.timeframe,
        entry_conditions=[RuleConditionV1.model_validate(item.model_dump()) for item in parsed.entry_conditions],
        exit_conditions=[RuleConditionV1.model_validate(item.model_dump()) for item in parsed.exit_conditions],
        unsupported_conditions=parsed.unsupported_conditions,
        clarification_required=parsed.clarification_required or not executable,
        explanation=parsed.explanation,
        indicator_selections=parsed.indicator_selections,
        canonical_rule=rule,
        editable_summary=_editable_summary(rule),
        clarifications=clarifications,
        is_executable=executable,
        authoring_method=authoring_method,
        policy_hash=RULE_DRAFT_POLICY_HASH,
        expires_at=signed.expires_at,
        draft_token=signed.token,
        strategy_execution_spec=rule if executable else None,
        spec_version=STRATEGY_EXECUTION_SPEC_VERSION if executable else None,
        spec_hash=canonical_rule_digest(rule) if executable else None,
        parse_token=signed.token if executable else None,
    )


def canonical_rule_digest(rule: ExecutionSpecV1OrV2 | None) -> str:
    encoded = json.dumps(
        None if rule is None else rule.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_rule_execution_query(rule: ExecutionSpecV1OrV2) -> str:
    """Derive an internal graph query from the signed structure, never raw input."""

    if isinstance(rule, ExplorationExecutionSpecV2):
        candidate_ids = ", ".join(candidate.catalog_id for candidate in rule.candidates)
        return f"KRX 일봉 탐색 연구: 봉인 후보 {candidate_ids}의 과거 성과를 동일 조건으로 검증"

    clauses = [
        _condition_clause(condition)
        for condition in [*rule.entry_conditions, *rule.exit_conditions]
    ]
    return f"KRX 일봉 조건식: {'; '.join(clauses)}"


def _build_exploration_draft(
    *,
    query: str,
    user_id: str,
    signer: RuleDraftSigner,
    policy_record: ActiveExplorationPolicyV2,
    now: datetime | None,
) -> RuleDraftV1:
    policy = policy_record.policy
    templates = select_exploration_templates(query, policy_record)
    spec = ExplorationExecutionSpecV2(
        policy_version=policy.policy_version,
        policy_hash=policy_record.policy_hash,
        catalog_version=policy.catalog_version,
        catalog_hash=policy.catalog_hash,
        candidates=[
            ExplorationCandidateRefV2(
                catalog_id=template.catalog_id,
                execution_signature=template.execution_signature,
            )
            for template in templates
        ],
    )
    signed = signer.issue(rule=spec, user_id=user_id, now=now)
    available_metrics = sorted(
        {
            metric
            for template in templates
            for metric in [*template.required_data, *(item.key for item in template.indicator_explanations)]
        }
    )
    review = ExplorationReviewV2(
        research_hypothesis=(
            "사전에 등록한 서로 다른 추세·모멘텀 규칙 중 일부가 비용을 반영한 미래 구간에서도 "
            "KRX 벤치마크와 비교할 만한 성과를 보일 수 있습니다."
        ),
        opposing_hypothesis=(
            "관측된 차이는 우연·시장 국면·거래비용 때문에 사라질 수 있으며 어느 후보도 "
            "충분한 미래 구간 근거를 만들지 못할 수 있습니다."
        ),
        period=f"서버 PIT 데이터 최근 {policy.history_years}년, 일봉",
        available_metrics=available_metrics,
        defaults=[
            f"{policy.risk_style}/{policy.investment_horizon} 위험·기간 해석",
            f"long-only, 최대 {policy.max_positions}종목, {policy.rebalance_interval_days}거래일 교체",
            (
                f"수수료 {policy.cost_model.commission_pct:.3%}, 세금 {policy.cost_model.tax_pct:.3%}, "
                f"슬리피지 {policy.cost_model.slippage_pct:.3%}"
            ),
            f"{policy.validation.method}, 최소 {policy.validation.minimum_evaluation_sessions}개 평가 세션",
        ],
        alternatives=[
            "위험성향이나 투자 기간을 지정해 다른 사전등록 후보군으로 다시 탐색",
            "진입·종료 지표와 수치를 직접 지정해 사용자 정의 규칙으로 검증",
        ],
        candidate_reasons=[
            ExplorationCandidateReasonV2(
                catalog_id=template.catalog_id,
                title=template.title,
                reason=template.why_used,
                required_data=template.required_data,
            )
            for template in templates
        ],
        limitations=[
            "과거 성과는 미래 수익이나 원금 보전을 보장하지 않습니다.",
            "모든 후보 결과를 함께 보고하며 성과를 본 뒤 후보를 바꾸지 않습니다.",
            "개인 보유자산·재무상황을 반영한 매매 추천이 아닙니다.",
        ],
        policy_version=policy.policy_version,
        policy_hash=policy_record.policy_hash,
        catalog_version=policy.catalog_version,
        catalog_hash=policy.catalog_hash,
    )
    return RuleDraftV1(
        explanation="수익 보장이 아닌 과거 데이터 기반 탐색 연구로 해석했습니다.",
        canonical_rule=None,
        exploration=review,
        editable_summary=(
            f"{policy.market} {policy.timeframe}, 사전등록 후보 {len(templates)}개를 "
            "같은 데이터·비용·검증 방식으로 비교합니다."
        ),
        clarification_required=False,
        is_executable=True,
        authoring_method="deterministic",
        policy_hash=RULE_DRAFT_POLICY_HASH,
        expires_at=signed.expires_at,
        draft_token=signed.token,
        strategy_execution_spec=spec,
        spec_version=EXPLORATION_EXECUTION_SPEC_VERSION,
        spec_hash=canonical_rule_digest(spec),
        parse_token=signed.token,
    )


class ResearchDataProvenanceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["postgres"]
    as_of: str = Field(min_length=10, max_length=10)
    retrieved_at: datetime
    freshness: Literal["eod_current"]
    universe_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)


class ResearchCandidateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    name: str = Field(min_length=1)
    market: Literal["KRX"] = "KRX"
    as_of: str = Field(min_length=10, max_length=10)
    matched_conditions: list[str] = Field(min_length=1, max_length=5)


class _ResearchResultBaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    authoring_method: Literal["deterministic", "llm"]


class ResearchReadyV1(_ResearchResultBaseV1):
    status: Literal["ready"] = "ready"
    provenance: ResearchDataProvenanceV1
    candidates: list[ResearchCandidateV1]

    @model_validator(mode="after")
    def candidate_count_matches(self) -> ResearchReadyV1:
        if len(self.candidates) != self.provenance.candidate_count:
            raise ValueError("candidate count must match provenance")
        return self


class ResearchNeedClarificationV1(_ResearchResultBaseV1):
    status: Literal["need_clarification"] = "need_clarification"
    explanation: str = Field(min_length=1)
    choices: list[ClarificationChoiceV1] = Field(min_length=1, max_length=3)


class ResearchNoMatchV1(_ResearchResultBaseV1):
    status: Literal["no_match"] = "no_match"
    provenance: ResearchDataProvenanceV1
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def no_match_has_no_candidates(self) -> ResearchNoMatchV1:
        if self.provenance.candidate_count != 0:
            raise ValueError("no_match requires zero candidates")
        return self


class ResearchUnavailableV1(_ResearchResultBaseV1):
    status: Literal["unavailable"] = "unavailable"
    reason_code: Literal["operational_data_provenance_required"]
    explanation: str = Field(min_length=1)
    retryable: bool


class ResearchFailedV1(_ResearchResultBaseV1):
    status: Literal["failed"] = "failed"
    support_reference: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    retryable: bool


class ResearchDevPreviewV1(_ResearchResultBaseV1):
    """Explicitly non-operational fixture state for local renderer verification."""

    status: Literal["dev_preview"] = "dev_preview"
    reason_code: Literal["development_fixture_only"]
    explanation: str = Field(min_length=1)


ResearchResultV1 = Annotated[
    ResearchReadyV1
    | ResearchNeedClarificationV1
    | ResearchNoMatchV1
    | ResearchUnavailableV1
    | ResearchFailedV1
    | ResearchDevPreviewV1,
    Field(discriminator="status"),
]


def unavailable_result_for_unverified_job(*, job_id: str) -> ResearchUnavailableV1:
    """Fail closed until the result/lifecycle owners attach verified EOD provenance."""

    return ResearchUnavailableV1(
        result_id=f"research:{job_id}",
        rule_version=RULE_DRAFT_SCHEMA_VERSION,
        authoring_method="deterministic",
        reason_code="operational_data_provenance_required",
        explanation="운영 데이터 기준일과 출처가 확인되지 않아 결과를 표시할 수 없습니다.",
        retryable=True,
    )


def _live_parser_enabled() -> bool:
    from ai_graph.llm import is_live_llm_provider

    return is_live_llm_provider()


def _canonical_rule_from_parse(parsed: StrategyParseResultV1) -> CanonicalRuleV1 | None:
    if not parsed.entry_conditions and not parsed.exit_conditions:
        return None
    return CanonicalRuleV1(
        market=parsed.market,
        timeframe=parsed.timeframe,
        entry_conditions=[RuleConditionV1.model_validate(item.model_dump()) for item in parsed.entry_conditions],
        exit_conditions=[RuleConditionV1.model_validate(item.model_dump()) for item in parsed.exit_conditions],
    )


def _clarifications_for(
    rule: CanonicalRuleV1 | None,
    parsed: StrategyParseResultV1 | None = None,
) -> list[ClarificationChoiceV1]:
    choices: list[ClarificationChoiceV1] = []
    if parsed is not None and parsed.unsupported_conditions:
        choices.append(
            ClarificationChoiceV1(
                label="사용 가능한 지표로 조건 수정",
                reason="서버에 없는 지표는 백테스트에 사용할 수 없습니다.",
            )
        )
    if rule is None:
        choices.extend([
            ClarificationChoiceV1(
                label="진입 지표와 수치 추가",
                reason="조건 일치 여부를 계산하려면 하나 이상의 진입 조건이 필요합니다.",
            ),
            ClarificationChoiceV1(
                label="종료 또는 평가 조건 추가",
                reason="과거 시뮬레이션의 평가 범위를 정하려면 종료 조건이 필요합니다.",
            ),
        ])
        return choices[:3]
    if not rule.entry_conditions:
        choices.append(
            ClarificationChoiceV1(
                label="진입 조건 추가",
                reason="조건 일치 여부를 계산하려면 하나 이상의 진입 조건이 필요합니다.",
            )
        )
    if not rule.exit_conditions:
        choices.append(
            ClarificationChoiceV1(
                label="종료 또는 평가 조건 추가",
                reason="과거 시뮬레이션의 평가 범위를 정하려면 종료 조건이 필요합니다.",
            )
        )
    return choices[:3]


def _editable_summary(rule: CanonicalRuleV1 | None) -> str:
    if rule is None:
        return "KRX 일봉 조건식을 완성하려면 진입 지표와 종료 또는 평가 조건을 입력해 주세요."
    pieces = ["KRX 일봉"]
    if rule.entry_conditions:
        pieces.append("진입: " + ", ".join(_condition_summary(item) for item in rule.entry_conditions))
    if rule.exit_conditions:
        pieces.append("종료: " + ", ".join(_condition_summary(item) for item in rule.exit_conditions))
    return " · ".join(pieces)


def _condition_summary(condition: RuleConditionV1) -> str:
    operators = {
        "lt": "미만",
        "lte": "이하",
        "gt": "초과",
        "gte": "이상",
        "eq": "같음",
        "ne": "다름",
    }
    lookback = f" ({condition.lookback}일)" if condition.lookback != 14 else ""
    return f"{condition.metric.upper()} {condition.value:g} {operators[condition.comparator]}{lookback}"


def _condition_clause(condition: RuleConditionV1) -> str:
    return f"{condition.role}={_condition_summary(condition)}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _encode_json(value: object) -> str:
    return _encode_bytes(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _decode_json(value: str) -> object:
    return json.loads(_decode_bytes(value).decode("utf-8"))


def _encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
