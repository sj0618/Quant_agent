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
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from os import environ
from threading import Lock
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

RULE_DRAFT_SCHEMA_VERSION = "research-rule-draft.v1"
RULE_DRAFT_POLICY_HASH = hashlib.sha256(
    b"quantagent-research-only-preflight-v1"
).hexdigest()
RULE_DRAFT_HMAC_SECRET_ENV = "AI_RULE_DRAFT_HMAC_SECRET"
RULE_DRAFT_HMAC_KEY_VERSION_ENV = "AI_RULE_DRAFT_HMAC_KEY_VERSION"
DEFAULT_RULE_DRAFT_TTL_SECONDS = 600


class RuleConditionV1(BaseModel):
    """One deterministic, user-editable research condition.

    ``entry`` and ``exit`` describe rule boundaries only; they are intentionally not
    trading instructions and are never rendered as order actions.
    """

    model_config = ConfigDict(extra="forbid")

    metric: Literal["rsi"]
    comparator: Literal["lte", "gte"]
    value: float = Field(gt=0.0, le=100.0)
    role: Literal["entry", "exit"]


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


class ClarificationChoiceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=240)


class RuleDraftV1(BaseModel):
    """Public parse result.  The token is opaque and contains no raw query text."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["rule_draft"] = "rule_draft"
    canonical_rule: CanonicalRuleV1 | None = None
    editable_summary: str = Field(min_length=1, max_length=500)
    clarifications: list[ClarificationChoiceV1] = Field(default_factory=list, max_length=3)
    is_executable: bool
    authoring_method: Literal["deterministic"] = "deterministic"
    schema_version: Literal[RULE_DRAFT_SCHEMA_VERSION] = RULE_DRAFT_SCHEMA_VERSION
    policy_hash: str = Field(min_length=64, max_length=64)
    expires_at: datetime
    draft_token: str = Field(min_length=32)

    @model_validator(mode="after")
    def executable_drafts_are_complete(self) -> RuleDraftV1:
        if self.is_executable:
            if self.canonical_rule is None or not self.canonical_rule.is_executable:
                raise ValueError("executable drafts require entry and exit conditions")
            if self.clarifications:
                raise ValueError("executable drafts cannot carry clarification choices")
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

    def issue(self, *, rule: CanonicalRuleV1 | None, user_id: str, now: datetime | None = None) -> _SignedDraft:
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
        rule: CanonicalRuleV1,
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
) -> RuleDraftV1:
    """Make a bounded deterministic RSI rule review without retaining raw input."""

    rule = _parse_rsi_rule(query)
    clarifications = _clarifications_for(rule)
    signed = signer.issue(rule=rule, user_id=user_id, now=now)
    return RuleDraftV1(
        canonical_rule=rule,
        editable_summary=_editable_summary(rule),
        clarifications=clarifications,
        is_executable=bool(rule and rule.is_executable),
        policy_hash=RULE_DRAFT_POLICY_HASH,
        expires_at=signed.expires_at,
        draft_token=signed.token,
    )


def canonical_rule_digest(rule: CanonicalRuleV1 | None) -> str:
    encoded = json.dumps(
        None if rule is None else rule.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_rule_execution_query(rule: CanonicalRuleV1) -> str:
    """Derive an internal graph query from the signed structure, never raw input."""

    clauses = [
        _condition_clause(condition)
        for condition in [*rule.entry_conditions, *rule.exit_conditions]
    ]
    return f"KRX 일봉 조건식: {'; '.join(clauses)}"


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


_RSI_LTE = re.compile(
    r"rsi\s*(?:가|는|은)?\s*(\d+(?:\.\d+)?)\s*(?:이하|미만|below|under|<=|<)",
    re.IGNORECASE,
)
_RSI_GTE = re.compile(
    r"rsi\s*(?:가|는|은)?\s*(\d+(?:\.\d+)?)\s*(?:이상|초과|above|over|>=|>)",
    re.IGNORECASE,
)


def _parse_rsi_rule(query: str) -> CanonicalRuleV1 | None:
    entry_conditions = [
        RuleConditionV1(metric="rsi", comparator="lte", value=float(match.group(1)), role="entry")
        for match in _RSI_LTE.finditer(query)
    ][:3]
    exit_conditions = [
        RuleConditionV1(metric="rsi", comparator="gte", value=float(match.group(1)), role="exit")
        for match in _RSI_GTE.finditer(query)
    ][:3]
    if not entry_conditions and not exit_conditions:
        return None
    return CanonicalRuleV1(
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions,
    )


def _clarifications_for(rule: CanonicalRuleV1 | None) -> list[ClarificationChoiceV1]:
    if rule is None:
        return [
            ClarificationChoiceV1(
                label="진입 지표와 수치 추가",
                reason="조건 일치 여부를 계산하려면 하나 이상의 진입 조건이 필요합니다.",
            ),
            ClarificationChoiceV1(
                label="종료 또는 평가 조건 추가",
                reason="과거 시뮬레이션의 평가 범위를 정하려면 종료 조건이 필요합니다.",
            ),
        ]
    if not rule.entry_conditions:
        return [
            ClarificationChoiceV1(
                label="진입 조건 추가",
                reason="조건 일치 여부를 계산하려면 하나 이상의 진입 조건이 필요합니다.",
            )
        ]
    if not rule.exit_conditions:
        return [
            ClarificationChoiceV1(
                label="종료 또는 평가 조건 추가",
                reason="과거 시뮬레이션의 평가 범위를 정하려면 종료 조건이 필요합니다.",
            )
        ]
    return []


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
    operator = "이하" if condition.comparator == "lte" else "이상"
    return f"RSI {condition.value:g} {operator}"


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
