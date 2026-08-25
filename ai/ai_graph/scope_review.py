"""Second-opinion adjudication for scope refusals the wording alone cannot settle.

`preflight.classify_research_request` is deterministic and dependency-free so that a
prohibited request is stopped before it reaches a provider, a job store, or the user's
quota. That property is worth keeping, and it is why this lives in a separate module:
the deterministic guard still decides every request on its own, and this only ever
revisits the narrow case it explicitly marked `adjudicable` - a recommendation verb with
no stated object, where "퀀트 전략을 추천해줘" and "종목을 추천해줘" are the same string
shape but opposite answers.

Two properties are deliberate:

- The adjudication is one-directional. It can only turn an ambiguous refusal into an
  allow. It is never consulted for a request the guard allowed, so no request gains a
  provider round trip, a new failure mode, or a prompt-injection surface by being
  ordinary.
- It fails closed. No provider, a timeout, a malformed answer, or an "unclear" verdict
  all leave the original refusal standing.
"""

from __future__ import annotations

from collections.abc import Callable

from ai_graph.preflight import ResearchRequestPreflight

ScopeObjectJudge = Callable[[str], str | None]

# The only verdict that may overturn a refusal.
_STRATEGY_OBJECT = "strategy"


def _default_judge(query: str) -> str | None:
    # Imported lazily so importing this module does not pull the provider stack into
    # callers that only ever use the deterministic guard.
    from ai_graph.llm.role_calls import classify_recommendation_object

    return classify_recommendation_object(query=query)


def review_research_scope(
    query: str,
    decision: ResearchRequestPreflight,
    *,
    judge: ScopeObjectJudge | None = None,
) -> ResearchRequestPreflight:
    """Return `decision`, or an allow when the ambiguous object turns out to be a strategy."""

    if decision.allowed or not decision.adjudicable:
        return decision
    try:
        verdict = (judge or _default_judge)(query)
    except Exception:  # noqa: BLE001 - a guard must not fail open on any judge error
        return decision
    if verdict == _STRATEGY_OBJECT:
        return ResearchRequestPreflight(allowed=True)
    return decision
