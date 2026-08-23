from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_graph.research_eligibility import (
    EligiblePostgresEod,
    IneligibleResearchData,
    PerformanceUnavailable,
    ResearchRuntimeFacts,
    VerifiedResearchProvenance,
    evaluate_research_eligibility,
)


def _valid_facts(**overrides: object) -> ResearchRuntimeFacts:
    values: dict[str, object] = {
        "dsn_configured": True,
        "load_state": "ready",
        "source": "postgres",
        "production_eligible": True,
        "as_of": "2026-08-21",
        "retrieved_at": datetime(2026, 8, 21, 16, tzinfo=UTC),
        "session_state": "closed",
        "freshness": "eod_current",
        "required_families": frozenset({"prices", "symbols"}),
        "available_families": frozenset({"prices", "symbols", "indicators"}),
        "row_count": 120,
        "universe_count": 10,
        "candidate_count": 2,
        "candidate_items_count": 2,
        "snapshot_or_result_id": "snapshot-20260821-a",
    }
    values.update(overrides)
    return ResearchRuntimeFacts(**values)


@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"load_state": "database_error", "dsn_configured": False}, "database_error"),
        ({"dsn_configured": False, "source": "fixture"}, "missing_dsn"),
        ({"source": "fixture", "production_eligible": True}, "non_postgres_source"),
        ({"production_eligible": False}, "not_production_eligible"),
        ({"as_of": None}, "missing_as_of"),
        ({"retrieved_at": None}, "missing_retrieved_at"),
        ({"freshness": "stale"}, "freshness_not_current"),
        ({"session_state": None}, "freshness_not_current"),
        ({"available_families": frozenset({"prices"})}, "incomplete_coverage"),
        ({"row_count": 0}, "invalid_counts"),
        ({"universe_count": 0}, "invalid_counts"),
        ({"candidate_count": -1}, "invalid_counts"),
        ({"candidate_items_count": 1}, "invalid_counts"),
        ({"snapshot_or_result_id": ""}, "invalid_counts"),
    ],
)
def test_ineligible_reasons_have_fixed_precedence(
    overrides: dict[str, object], expected_reason: str
) -> None:
    decision = evaluate_research_eligibility(_valid_facts(**overrides))

    assert isinstance(decision, IneligibleResearchData)
    assert decision.reason_code == expected_reason


def test_valid_postgres_eod_facts_create_ready_decision() -> None:
    decision = evaluate_research_eligibility(_valid_facts())

    assert isinstance(decision, EligiblePostgresEod)
    assert decision.outcome == "ready"
    assert decision.provenance.source == "postgres"
    assert decision.provenance.candidate_count == 2


def test_valid_zero_candidates_is_no_match_only_after_all_other_gates_pass() -> None:
    decision = evaluate_research_eligibility(
        _valid_facts(candidate_count=0, candidate_items_count=0)
    )

    assert isinstance(decision, EligiblePostgresEod)
    assert decision.outcome == "no_match"


def test_eligible_provenance_cannot_be_constructed_with_missing_or_mismatched_facts() -> None:
    with pytest.raises(ValidationError):
        VerifiedResearchProvenance(
            source="postgres",
            as_of="2026-08-21",
            retrieved_at=datetime(2026, 8, 21, tzinfo=UTC),
            session_state="closed",
            freshness="eod_current",
            required_families=frozenset({"prices"}),
            available_families=frozenset(),
            row_count=1,
            universe_count=1,
            candidate_count=1,
            candidate_items_count=0,
            snapshot_or_result_id="result-1",
        )


def test_safe_facts_reject_raw_error_or_secret_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchRuntimeFacts(dsn_configured=False, password="never-public")  # type: ignore[call-arg]


def test_unavailable_public_performance_cannot_carry_metrics_or_charts() -> None:
    unavailable = PerformanceUnavailable(
        reason_code="insufficient_provenance",
        safe_facts={"row_count": 0, "source": "fixture"},
    )

    assert unavailable.model_dump() == {
        "availability": "unavailable",
        "reason_code": "insufficient_provenance",
        "safe_facts": {"row_count": 0, "source": "fixture"},
    }
    with pytest.raises(ValidationError):
        PerformanceUnavailable(
            reason_code="insufficient_provenance",
            performance={"total_return": 1.0},
        )
