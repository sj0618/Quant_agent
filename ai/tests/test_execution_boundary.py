from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_graph.api import create_app
from ai_graph.execution_boundary import (
    APPROVED_EXECUTION_BOUNDARIES,
    ExecutionBoundary,
    validate_execution_boundaries,
)
from ai_graph.jobs import InMemoryAnalysisJobStore


def test_approved_execution_boundary_has_one_authenticated_job_create_and_one_internal_evaluator() -> None:
    result = validate_execution_boundaries()

    assert result.valid, result.errors
    assert result.summary.as_dict() == {
        "public_create_allowed": 0,
        "authenticated_job_create_allowed": 1,
        "internal_evaluator_allowed": 1,
        "read_only_projection_count": 1,
        "read_only_projection_with_owner_auth_failure": 1,
    }


def test_unauthenticated_public_create_cannot_be_enabled() -> None:
    public_create = next(
        boundary for boundary in APPROVED_EXECUTION_BOUNDARIES if boundary.kind == "public_create"
    )
    changed = public_create.model_copy(update={"allowed": True, "write_allowed": True})
    boundaries = tuple(
        changed if boundary.boundary_id == changed.boundary_id else boundary
        for boundary in APPROVED_EXECUTION_BOUNDARIES
    )

    result = validate_execution_boundaries(boundaries)

    assert not result.valid
    assert "public create boundary count must be zero" in result.errors


def test_read_only_projection_requires_owner_auth_and_failure_delivery() -> None:
    projection = next(
        boundary
        for boundary in APPROVED_EXECUTION_BOUNDARIES
        if boundary.kind == "read_only_projection"
    )
    changed = projection.model_copy(update={"failure_delivery": ""})

    result = validate_execution_boundaries(
        tuple(
            changed if boundary.boundary_id == changed.boundary_id else boundary
            for boundary in APPROVED_EXECUTION_BOUNDARIES
        )
    )

    assert not result.valid
    assert any("read-only boundary lacks owner/auth/failure" in error for error in result.errors)


def test_contract_model_rejects_extra_boundary_fields() -> None:
    boundary = APPROVED_EXECUTION_BOUNDARIES[0].model_dump()
    boundary["unexpected"] = True

    try:
        ExecutionBoundary.model_validate(boundary)
    except ValueError:
        pass
    else:
        raise AssertionError("extra execution boundary fields must be rejected")


# ---------------------------------------------------------------------------
# Router conformance.
#
# The tests above only check the declaration's internal shape.  Nothing tied the
# table to the running app, so a route could drift from its declared contract while
# every structural test stayed green (issue #102: "you can change the route while
# keeping the declaration and nothing breaks").  The tests below close that gap for
# the boundaries the *ai* FastAPI app owns.  ``APPROVED_EXECUTION_BOUNDARIES`` is a
# cross-service table: some rows are served by the backend app (``/api/v1/runs``, the
# ``/api/v1/reports`` read-only projection) or by CI (``/internal/evaluator/analysis``)
# and cannot be exercised from this app.  Those rows are asserted here only to be
# *absent* from the ai router; the backend enforces its own rows via
# ``backend/tests/unit/test_track_c_contract_policy.py``.
# ---------------------------------------------------------------------------

_AI_SERVED_BOUNDARY_IDS = frozenset(
    {
        "authenticated-analysis-job-create",  # POST /analysis-jobs (auth-gated writer)
        "public-daily-digest-create",  # POST /ai/daily-digest (retired -> 410)
        "public-research-job-create",  # POST /api/research/jobs (retired/auth-gated)
        "historical-report-read",  # GET /api/reports/{report_id} (retired in ai; live copy is backend)
    }
)
_EXTERNAL_BOUNDARY_IDS = frozenset(
    {
        "public-analysis-run-create",  # backend POST /api/v1/runs
        "internal-release-evaluator",  # CI POST /internal/evaluator/analysis
    }
)


class _StubSessionResolver:
    """Enforce authentication with no valid sessions, so every caller is unauthenticated."""

    async def resolve_user_id(self, session_id: str | None) -> str | None:
        return None


def _ai_router_index(app) -> set[tuple[str, str]]:
    served: set[tuple[str, str]] = set()
    for route in app.routes:
        for method in getattr(route, "methods", set()) or set():
            served.add((method, getattr(route, "path", "")))
    return served


def test_declared_boundaries_are_partitioned_by_the_real_ai_router() -> None:
    """Every declared boundary is either served by the ai app or a known external surface.

    Removing/renaming an ai route, or accidentally implementing a cross-service route in
    this app, flips a boundary between the two sets and fails here.
    """

    served = _ai_router_index(create_app(InMemoryAnalysisJobStore()))

    ai_served = {
        boundary.boundary_id
        for boundary in APPROVED_EXECUTION_BOUNDARIES
        if (boundary.method, boundary.path) in served
    }
    external = {
        boundary.boundary_id
        for boundary in APPROVED_EXECUTION_BOUNDARIES
        if (boundary.method, boundary.path) not in served
    }

    assert ai_served == set(_AI_SERVED_BOUNDARY_IDS)
    assert external == set(_EXTERNAL_BOUNDARY_IDS)


def test_ai_served_create_boundaries_reject_unauthenticated_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ai create boundary accepts an unauthenticated write.

    This is the security property the declaration encodes: exactly one authenticated
    writer, and the public creators are retired.  It fails if a create route regresses
    into a public 2xx writer.
    """

    monkeypatch.setenv("AI_RELEASE_PROFILE", "release")
    app = create_app(InMemoryAnalysisJobStore(), session_resolver=_StubSessionResolver())
    client = TestClient(app, raise_server_exceptions=False)

    create_boundaries = [
        boundary
        for boundary in APPROVED_EXECUTION_BOUNDARIES
        if boundary.boundary_id in _AI_SERVED_BOUNDARY_IDS
        and boundary.kind in {"public_create", "authenticated_job_create"}
    ]
    assert create_boundaries, "no ai create boundary found to exercise"

    for boundary in create_boundaries:
        response = client.request(boundary.method, boundary.path, json={})
        assert not 200 <= response.status_code < 300, (
            boundary.boundary_id,
            response.status_code,
        )
        assert response.status_code in {401, 403, 410, 422}, (
            boundary.boundary_id,
            response.status_code,
        )


def test_retired_daily_digest_writer_stays_gone() -> None:
    """The declared ``allowed=False`` public digest writer returns 410, not a job."""

    client = TestClient(create_app(InMemoryAnalysisJobStore()), raise_server_exceptions=False)

    assert client.post("/ai/daily-digest", json={}).status_code == 410


def test_ai_report_projection_is_retired_here_not_a_mutable_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live read-only report projection is backend-owned (``/api/v1/reports``).

    The ai app retired its own ``/api/reports/{report_id}``; lock it as a non-mutating
    410 so it cannot regress into a second mutable report surface.  NOTE: the declared
    ``historical-report-read`` row is ``allowed=True`` because it describes the
    system-level projection now served by backend, not this retired ai route.
    """

    monkeypatch.setenv("AI_RELEASE_PROFILE", "release")
    client = TestClient(create_app(InMemoryAnalysisJobStore()), raise_server_exceptions=False)

    assert client.get("/api/reports/any-report-id").status_code == 410
