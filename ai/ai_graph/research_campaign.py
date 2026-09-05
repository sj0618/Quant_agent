"""Finite-budget ledger for autonomous strategy-research campaigns.

The backtest engine may refine an exploratory strategy after it has evaluated the
baseline. That is useful only while it is learning something new. This module is
the single owner of the limits that prevent a request from turning into an unbounded
``try one more variation`` loop.

It intentionally does not decide whether a strategy is investable. It decides only
whether the campaign is still entitled to spend another candidate-evaluation round.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any

AI_RESEARCH_CAMPAIGN_MAX_ROUNDS_ENV = "AI_RESEARCH_CAMPAIGN_MAX_ROUNDS"
AI_RESEARCH_CAMPAIGN_MAX_CANDIDATES_ENV = "AI_RESEARCH_CAMPAIGN_MAX_CANDIDATES"
AI_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS_ENV = "AI_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS"

DEFAULT_RESEARCH_CAMPAIGN_MAX_ROUNDS = 3
DEFAULT_RESEARCH_CAMPAIGN_MAX_CANDIDATES = 24
DEFAULT_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS = 2

# Environment configuration is an operator convenience, not permission to make a
# single job unbounded. These caps deliberately stay below the job-level deadline.
HARD_MAX_RESEARCH_CAMPAIGN_ROUNDS = 6
HARD_MAX_RESEARCH_CAMPAIGN_CANDIDATES = 36
HARD_MAX_RESEARCH_CAMPAIGN_NO_PROGRESS = 3
_SCORE_EPSILON = 1e-9


def _bounded_positive_env(name: str, *, default: int, maximum: int) -> int:
    """Read one positive, bounded integer without treating ``0`` as unlimited."""

    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return min(value, maximum)


@dataclass(frozen=True)
class ResearchCampaignBudget:
    """The non-negotiable search allowance for one user request."""

    max_rounds: int
    max_total_candidates: int
    max_consecutive_no_progress: int

    @classmethod
    def from_environment(cls) -> ResearchCampaignBudget:
        return cls(
            max_rounds=_bounded_positive_env(
                AI_RESEARCH_CAMPAIGN_MAX_ROUNDS_ENV,
                default=DEFAULT_RESEARCH_CAMPAIGN_MAX_ROUNDS,
                maximum=HARD_MAX_RESEARCH_CAMPAIGN_ROUNDS,
            ),
            max_total_candidates=_bounded_positive_env(
                AI_RESEARCH_CAMPAIGN_MAX_CANDIDATES_ENV,
                default=DEFAULT_RESEARCH_CAMPAIGN_MAX_CANDIDATES,
                maximum=HARD_MAX_RESEARCH_CAMPAIGN_CANDIDATES,
            ),
            max_consecutive_no_progress=_bounded_positive_env(
                AI_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS_ENV,
                default=DEFAULT_RESEARCH_CAMPAIGN_MAX_NO_PROGRESS,
                maximum=HARD_MAX_RESEARCH_CAMPAIGN_NO_PROGRESS,
            ),
        )


@dataclass
class ResearchCampaign:
    """Append-only experiment ledger with finite refinement rights.

    ``candidate_identity`` is supplied by the caller because the campaign must stay
    independent of code-generation schemas. An identity is reserved as soon as it is
    admitted, so a later failed backtest cannot cause a duplicate retry.
    """

    budget: ResearchCampaignBudget
    baseline_candidate_count: int
    seen_candidate_identities: set[str] = field(default_factory=set)
    rounds_started: int = 0
    admitted_refinement_candidates: int = 0
    duplicate_candidates_rejected: int = 0
    consecutive_no_progress: int = 0
    stop_reason: str | None = None
    round_history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def start(cls, candidate_identities: set[str]) -> ResearchCampaign:
        return cls(
            budget=ResearchCampaignBudget.from_environment(),
            baseline_candidate_count=len(candidate_identities),
            seen_candidate_identities=set(candidate_identities),
        )

    @property
    def total_candidate_count(self) -> int:
        return self.baseline_candidate_count + self.admitted_refinement_candidates

    def allow_next_round(self) -> bool:
        """Return whether another round may start, setting a durable stop reason."""

        if self.stop_reason is not None:
            return False
        if self.rounds_started >= self.budget.max_rounds:
            self.stop_reason = "round_budget_exhausted"
            return False
        if self.total_candidate_count >= self.budget.max_total_candidates:
            self.stop_reason = "candidate_budget_exhausted"
            return False
        if self.consecutive_no_progress >= self.budget.max_consecutive_no_progress:
            self.stop_reason = "no_progress_budget_exhausted"
            return False
        return True

    def admit_candidate_identities(self, identities: list[str]) -> list[str]:
        """Reserve distinct candidates within the remaining campaign allowance."""

        if not self.allow_next_round():
            return []
        remaining = self.budget.max_total_candidates - self.total_candidate_count
        admitted: list[str] = []
        for identity in identities:
            if identity in self.seen_candidate_identities:
                self.duplicate_candidates_rejected += 1
                continue
            if len(admitted) >= remaining:
                self.stop_reason = "candidate_budget_exhausted"
                break
            self.seen_candidate_identities.add(identity)
            admitted.append(identity)
        self.admitted_refinement_candidates += len(admitted)
        return admitted

    def record_round(
        self,
        *,
        proposed_count: int,
        admitted_count: int,
        score_before: float,
        score_after: float,
        progress: bool | None = None,
    ) -> bool:
        """Append one round result and return whether it produced real progress."""

        self.rounds_started += 1
        improved = _score_improved(score_before, score_after) if progress is None else progress
        if improved:
            self.consecutive_no_progress = 0
        else:
            self.consecutive_no_progress += 1
        self.round_history.append(
            {
                "round": self.rounds_started,
                "proposed_candidates": proposed_count,
                "admitted_candidates": admitted_count,
                "score_before": _finite_or_none(score_before),
                "score_after": _finite_or_none(score_after),
                "improved": improved,
            }
        )
        if not improved and self.consecutive_no_progress >= self.budget.max_consecutive_no_progress:
            self.stop_reason = "no_progress_budget_exhausted"
        return improved

    def stop(self, reason: str, *, replace: bool = False) -> None:
        if self.stop_reason is None or replace:
            self.stop_reason = reason

    def manifest(self) -> dict[str, Any]:
        """Produce the public-safe audit record for the completed campaign."""

        return {
            "policy": "finite_research_campaign.v1",
            "budget": {
                "max_rounds": self.budget.max_rounds,
                "max_total_candidates": self.budget.max_total_candidates,
                "max_consecutive_no_progress": self.budget.max_consecutive_no_progress,
            },
            "usage": {
                "baseline_candidates": self.baseline_candidate_count,
                "refinement_candidates": self.admitted_refinement_candidates,
                "total_candidates": self.total_candidate_count,
                "rounds_started": self.rounds_started,
                "duplicate_candidates_rejected": self.duplicate_candidates_rejected,
                "consecutive_no_progress": self.consecutive_no_progress,
            },
            "stop_reason": self.stop_reason or "campaign_completed",
            "rounds": list(self.round_history),
        }


def _score_improved(before: float, after: float) -> bool:
    """Reject NaN/inf and insignificant floating-point jitter as progress."""

    if not math.isfinite(before) or not math.isfinite(after):
        return False
    return after > before + _SCORE_EPSILON


def _finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None
