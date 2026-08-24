from __future__ import annotations

from ai_graph.execution_boundary import (
    APPROVED_EXECUTION_BOUNDARIES,
    ExecutionBoundary,
    validate_execution_boundaries,
)


def test_approved_execution_boundary_has_no_public_create_and_one_internal_evaluator() -> None:
    result = validate_execution_boundaries()

    assert result.valid, result.errors
    assert result.summary.as_dict() == {
        "public_create_allowed": 0,
        "internal_evaluator_allowed": 1,
        "read_only_projection_count": 1,
        "read_only_projection_with_owner_auth_failure": 1,
    }


def test_public_create_cannot_be_enabled() -> None:
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
