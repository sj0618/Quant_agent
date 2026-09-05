from __future__ import annotations

from ai_graph.research_campaign import (
    AI_RESEARCH_CAMPAIGN_MAX_CANDIDATES_ENV,
    AI_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS_ENV,
    AI_RESEARCH_CAMPAIGN_MAX_ROUNDS_ENV,
    DEFAULT_RESEARCH_CAMPAIGN_MAX_CANDIDATES,
    DEFAULT_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS,
    DEFAULT_RESEARCH_CAMPAIGN_MAX_ROUNDS,
    HARD_MAX_RESEARCH_CAMPAIGN_CANDIDATES,
    HARD_MAX_RESEARCH_CAMPAIGN_NO_PROGRESS,
    HARD_MAX_RESEARCH_CAMPAIGN_ROUNDS,
    ResearchCampaign,
    ResearchCampaignBudget,
)


def test_campaign_environment_never_allows_an_unbounded_value(monkeypatch) -> None:
    monkeypatch.setenv(AI_RESEARCH_CAMPAIGN_MAX_ROUNDS_ENV, "0")
    monkeypatch.setenv(AI_RESEARCH_CAMPAIGN_MAX_CANDIDATES_ENV, "not-a-number")
    monkeypatch.setenv(AI_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS_ENV, "-2")

    defaults = ResearchCampaignBudget.from_environment()

    assert defaults.max_rounds == DEFAULT_RESEARCH_CAMPAIGN_MAX_ROUNDS
    assert defaults.max_total_candidates == DEFAULT_RESEARCH_CAMPAIGN_MAX_CANDIDATES
    assert defaults.max_consecutive_no_progress == DEFAULT_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS

    monkeypatch.setenv(AI_RESEARCH_CAMPAIGN_MAX_ROUNDS_ENV, "999")
    monkeypatch.setenv(AI_RESEARCH_CAMPAIGN_MAX_CANDIDATES_ENV, "999")
    monkeypatch.setenv(AI_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS_ENV, "999")

    capped = ResearchCampaignBudget.from_environment()

    assert capped.max_rounds == HARD_MAX_RESEARCH_CAMPAIGN_ROUNDS
    assert capped.max_total_candidates == HARD_MAX_RESEARCH_CAMPAIGN_CANDIDATES
    assert capped.max_consecutive_no_progress == HARD_MAX_RESEARCH_CAMPAIGN_NO_PROGRESS


def test_campaign_rejects_duplicates_and_stops_when_candidate_budget_is_spent() -> None:
    campaign = ResearchCampaign(
        budget=ResearchCampaignBudget(
            max_rounds=3,
            max_total_candidates=4,
            max_consecutive_no_progress=2,
        ),
        baseline_candidate_count=2,
        seen_candidate_identities={"baseline-a", "baseline-b"},
    )

    admitted = campaign.admit_candidate_identities(
        ["baseline-a", "variant-a", "variant-a", "variant-b", "variant-c"]
    )

    assert admitted == ["variant-a", "variant-b"]
    assert campaign.duplicate_candidates_rejected == 2
    assert campaign.total_candidate_count == 4
    assert campaign.stop_reason == "candidate_budget_exhausted"
    assert not campaign.allow_next_round()


def test_campaign_stops_after_two_non_improving_rounds() -> None:
    campaign = ResearchCampaign(
        budget=ResearchCampaignBudget(
            max_rounds=3,
            max_total_candidates=12,
            max_consecutive_no_progress=2,
        ),
        baseline_candidate_count=1,
        seen_candidate_identities={"baseline"},
    )

    assert campaign.record_round(
        proposed_count=2,
        admitted_count=2,
        score_before=1.0,
        score_after=1.0,
    ) is False
    assert campaign.allow_next_round()
    assert campaign.record_round(
        proposed_count=2,
        admitted_count=2,
        score_before=1.0,
        score_after=0.9,
    ) is False

    assert campaign.stop_reason == "no_progress_budget_exhausted"
    assert not campaign.allow_next_round()
    assert campaign.manifest()["usage"]["consecutive_no_progress"] == 2


def test_campaign_acceptance_overrides_an_already_spent_candidate_budget() -> None:
    campaign = ResearchCampaign(
        budget=ResearchCampaignBudget(
            max_rounds=1,
            max_total_candidates=2,
            max_consecutive_no_progress=1,
        ),
        baseline_candidate_count=1,
        seen_candidate_identities={"baseline"},
    )
    assert campaign.admit_candidate_identities(["variant", "unadmitted"]) == ["variant"]
    assert campaign.stop_reason == "candidate_budget_exhausted"

    campaign.record_round(
        proposed_count=2,
        admitted_count=1,
        score_before=0.1,
        score_after=0.1,
        progress=True,
    )
    campaign.stop("objective_target_reached", replace=True)

    assert campaign.manifest()["stop_reason"] == "objective_target_reached"
