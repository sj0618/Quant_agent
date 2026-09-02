"""Pure, secret-free eligibility contracts for public research projections.

This module deliberately has no runtime, HTTP, database, or graph imports.  Runtime
adapters measure facts; this module applies the one deterministic policy which public
projections must consume.  It is consequently safe to unit test with contract fixtures
without mistaking those fixtures for operational evidence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EligibilityReasonCode = Literal[
    "database_error",
    "missing_dsn",
    "non_postgres_source",
    "not_production_eligible",
    "missing_as_of",
    "missing_retrieved_at",
    "freshness_not_current",
    "incomplete_coverage",
    "invalid_counts",
]


class ResearchRuntimeFacts(BaseModel):
    """Sanitized observations supplied by an adapter, never caller assertions.

    Fields intentionally exclude DSNs, SQL, exception messages, raw rows, and candidate
    contents so an ineligible decision is safe to expose to a public projection.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dsn_configured: bool
    load_state: Literal["ready", "database_error"] = "ready"
    source: str | None = None
    production_eligible: bool = False
    as_of: str | None = None
    retrieved_at: datetime | None = None
    session_state: str | None = None
    freshness: str | None = None
    required_families: frozenset[str] = Field(default_factory=frozenset)
    available_families: frozenset[str] = Field(default_factory=frozenset)
    row_count: int | None = None
    universe_count: int | None = None
    candidate_count: int | None = None
    candidate_items_count: int | None = None
    snapshot_or_result_id: str | None = None


class VerifiedResearchProvenance(BaseModel):
    """Facts which are present only when the central eligibility policy passes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["postgres"]
    as_of: str = Field(min_length=1)
    retrieved_at: datetime
    session_state: str = Field(min_length=1)
    freshness: Literal["eod_current"]
    required_families: frozenset[str] = Field(min_length=1)
    available_families: frozenset[str]
    row_count: int = Field(gt=0)
    universe_count: int = Field(gt=0)
    candidate_count: int = Field(ge=0)
    candidate_items_count: int = Field(ge=0)
    snapshot_or_result_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def candidate_items_match_count(self) -> VerifiedResearchProvenance:
        if self.candidate_items_count != self.candidate_count:
            raise ValueError("candidate item count must match candidate count")
        if not self.required_families.issubset(self.available_families):
            raise ValueError("required data families must be available")
        return self


class EligiblePostgresEod(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["eligible"] = "eligible"
    provenance: VerifiedResearchProvenance
    outcome: Literal["ready", "no_match"]

    @model_validator(mode="after")
    def no_match_requires_zero_candidates(self) -> EligiblePostgresEod:
        if (self.outcome == "no_match") != (self.provenance.candidate_count == 0):
            raise ValueError("outcome must agree with candidate count")
        return self


class IneligibleResearchData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["ineligible"] = "ineligible"
    reason_code: EligibilityReasonCode
    safe_facts: ResearchRuntimeFacts


ResearchEligibilityDecision = Annotated[
    EligiblePostgresEod | IneligibleResearchData,
    Field(discriminator="kind"),
]


def evaluate_research_eligibility(facts: ResearchRuntimeFacts) -> ResearchEligibilityDecision:
    """Return the first failing reason in the stable, documented precedence order."""

    reason = _ineligibility_reason(facts)
    if reason is not None:
        return IneligibleResearchData(reason_code=reason, safe_facts=facts)

    # The checks above establish every narrowing condition.  Keeping construction here
    # prevents adapters and public consumers from manufacturing an eligible state.
    provenance = VerifiedResearchProvenance(
        source="postgres",
        as_of=facts.as_of,
        retrieved_at=facts.retrieved_at,
        session_state=facts.session_state,
        freshness="eod_current",
        required_families=facts.required_families,
        available_families=facts.available_families,
        row_count=facts.row_count,
        universe_count=facts.universe_count,
        candidate_count=facts.candidate_count,
        candidate_items_count=facts.candidate_items_count,
        snapshot_or_result_id=facts.snapshot_or_result_id,
    )
    return EligiblePostgresEod(
        provenance=provenance,
        outcome="no_match" if provenance.candidate_count == 0 else "ready",
    )


def _ineligibility_reason(facts: ResearchRuntimeFacts) -> EligibilityReasonCode | None:
    if facts.load_state == "database_error":
        return "database_error"
    if not facts.dsn_configured:
        return "missing_dsn"
    if facts.source != "postgres":
        return "non_postgres_source"
    if not facts.production_eligible:
        return "not_production_eligible"
    if not _nonempty(facts.as_of):
        return "missing_as_of"
    if facts.retrieved_at is None:
        return "missing_retrieved_at"
    if facts.freshness != "eod_current" or not _nonempty(facts.session_state):
        return "freshness_not_current"
    if not facts.required_families or not facts.required_families.issubset(facts.available_families):
        return "incomplete_coverage"
    if (
        facts.row_count is None
        or facts.row_count <= 0
        or facts.universe_count is None
        or facts.universe_count <= 0
        or facts.candidate_count is None
        or facts.candidate_count < 0
        or facts.candidate_items_count is None
        or facts.candidate_items_count < 0
        or facts.candidate_items_count != facts.candidate_count
        or not _nonempty(facts.snapshot_or_result_id)
    ):
        return "invalid_counts"
    return None


def _nonempty(value: str | None) -> bool:
    return bool(value and value.strip())


# What the manifest producer writes when the engine did not state the assumption. A
# manifest carrying it is missing an execution assumption, not documenting one.
MISSING_EXECUTION_ASSUMPTION = "unavailable"
# `cost_tax_slippage_liquidity` serializes the engine's cost model; an empty object
# means no cost model reached the manifest at all.
_EMPTY_COST_MODEL = "cost_model={}"


class PerformanceMethodManifest(BaseModel):
    """Required provenance before a performance payload may become public."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluated_rule: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    substituted: bool
    market: str = Field(min_length=1)
    universe: str = Field(min_length=1)
    start_date: str = Field(min_length=1)
    end_date: str = Field(min_length=1)
    eod_basis: str = Field(min_length=1)
    initial_capital: float = Field(gt=0)
    rebalance_timing: str = Field(min_length=1)
    # Optional so results produced before time exits existed still validate.
    holding_period: str | None = None
    fill_timing: str = Field(min_length=1)
    corporate_action_method: str = Field(min_length=1)
    cost_tax_slippage_liquidity: str = Field(min_length=1)
    observations: int = Field(gt=0)
    trades: int = Field(ge=0)
    benchmark_method: str | None = None
    data_version: str = Field(min_length=1)
    result_version: str = Field(min_length=1)
    execution_version: str = Field(min_length=1)
    historical_simulation_warning: str = Field(min_length=1)

    @model_validator(mode="after")
    def execution_assumptions_are_stated(self) -> PerformanceMethodManifest:
        """Fail closed when the run never said how it filled or what it charged.

        Fill timing, commission, tax and slippage are what make a return reproducible.
        A run that omits them has not produced a cheaper result, it has produced an
        unverifiable one, so the manifest refuses to validate and the public projection
        publishes `unavailable` rather than a number nobody can check.
        """

        if self.fill_timing == MISSING_EXECUTION_ASSUMPTION:
            raise ValueError("fill_timing must state the engine's execution timing")
        if self.cost_tax_slippage_liquidity in {MISSING_EXECUTION_ASSUMPTION, _EMPTY_COST_MODEL}:
            raise ValueError("cost_tax_slippage_liquidity must state the engine's cost model")
        return self


class PerformanceUnavailable(BaseModel):
    """Public unavailable variant; it deliberately has no metrics or chart fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    availability: Literal["unavailable"] = "unavailable"
    reason_code: str = Field(min_length=1)
    safe_facts: dict[str, str | int | bool | None] = Field(default_factory=dict)


class PerformanceAvailable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    availability: Literal["available"] = "available"
    performance: dict[str, object]
    method_manifest: PerformanceMethodManifest
    limitations: list[str] = Field(default_factory=list)


PublicPerformance = Annotated[
    PerformanceAvailable | PerformanceUnavailable,
    Field(discriminator="availability"),
]
