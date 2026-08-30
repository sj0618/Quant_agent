"""Approved execution boundary contract for release and read-only report access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BoundaryKind = Literal["public_create", "internal_evaluator", "read_only_projection"]
PUBLIC_CREATE_RETIREMENT_SCHEMA = "execution-boundary.v1"


def retired_public_create_detail(
    *,
    boundary_id: str,
    path: str,
    read_only_alternative: str,
) -> dict[str, str]:
    """Return the stable response body for a retired public writer."""

    return {
        "code": "public_create_retired",
        "message": "새 분석 생성은 제공하지 않습니다. 보관된 읽기 전용 결과만 조회할 수 있습니다.",
        "boundary_id": boundary_id,
        "path": path,
        "read_only_alternative": read_only_alternative,
        "schema_version": PUBLIC_CREATE_RETIREMENT_SCHEMA,
    }


class ExecutionBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    boundary_id: str = Field(min_length=1)
    kind: BoundaryKind
    method: Literal["GET", "POST"]
    path: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    auth: str = Field(min_length=1)
    failure_delivery: str = Field(min_length=1)
    allowed: bool
    write_allowed: bool


APPROVED_EXECUTION_BOUNDARIES: tuple[ExecutionBoundary, ...] = (
    ExecutionBoundary(
        boundary_id="public-analysis-create",
        kind="public_create",
        method="POST",
        path="/analysis-jobs",
        owner="none",
        auth="none",
        failure_delivery="410_feature_disabled_with_read_only_alternative",
        allowed=False,
        write_allowed=False,
    ),
    ExecutionBoundary(
        boundary_id="public-daily-digest-create",
        kind="public_create",
        method="POST",
        path="/ai/daily-digest",
        owner="none",
        auth="none",
        failure_delivery="410_feature_disabled_with_read_only_alternative",
        allowed=False,
        write_allowed=False,
    ),
    ExecutionBoundary(
        boundary_id="public-analysis-run-create",
        kind="public_create",
        method="POST",
        path="/api/v1/runs",
        owner="none",
        auth="none",
        failure_delivery="410_feature_disabled_with_read_only_alternative",
        allowed=False,
        write_allowed=False,
    ),
    ExecutionBoundary(
        boundary_id="public-research-job-create",
        kind="public_create",
        method="POST",
        path="/api/research/jobs",
        owner="none",
        auth="none",
        failure_delivery="410_feature_disabled_with_read_only_alternative",
        allowed=False,
        write_allowed=False,
    ),
    ExecutionBoundary(
        boundary_id="internal-release-evaluator",
        kind="internal_evaluator",
        method="POST",
        path="/internal/evaluator/analysis",
        owner="data_ai_trust_lead",
        auth="local_ci_or_approved_operator",
        failure_delivery="evaluator_fail_control_board_blocker",
        allowed=True,
        write_allowed=True,
    ),
    ExecutionBoundary(
        boundary_id="historical-report-read",
        kind="read_only_projection",
        method="GET",
        path="/api/reports/{report_id}",
        owner="ux_verification_lead",
        auth="existing_authenticated_user",
        failure_delivery="stale_or_unavailable_reason_with_next_action",
        allowed=True,
        write_allowed=False,
    ),
)


@dataclass(frozen=True)
class ExecutionBoundarySummary:
    public_create_allowed: int
    internal_evaluator_allowed: int
    read_only_projection_count: int
    read_only_projection_with_owner_auth_failure: int

    def as_dict(self) -> dict[str, int]:
        return {
            "public_create_allowed": self.public_create_allowed,
            "internal_evaluator_allowed": self.internal_evaluator_allowed,
            "read_only_projection_count": self.read_only_projection_count,
            "read_only_projection_with_owner_auth_failure": self.read_only_projection_with_owner_auth_failure,
        }


@dataclass(frozen=True)
class ExecutionBoundaryValidation:
    valid: bool
    errors: tuple[str, ...]
    summary: ExecutionBoundarySummary

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "summary": self.summary.as_dict(),
        }


def validate_execution_boundaries(
    boundaries: tuple[ExecutionBoundary, ...] = APPROVED_EXECUTION_BOUNDARIES,
) -> ExecutionBoundaryValidation:
    errors: list[str] = []
    public_create_allowed = sum(
        boundary.allowed for boundary in boundaries if boundary.kind == "public_create"
    )
    internal_evaluator_allowed = sum(
        boundary.allowed for boundary in boundaries if boundary.kind == "internal_evaluator"
    )
    read_only_boundaries = [
        boundary for boundary in boundaries if boundary.kind == "read_only_projection"
    ]
    read_only_with_fields = sum(
        bool(boundary.owner and boundary.auth and boundary.failure_delivery)
        for boundary in read_only_boundaries
    )

    if public_create_allowed != 0:
        errors.append("public create boundary count must be zero")
    if internal_evaluator_allowed != 1:
        errors.append("exactly one internal evaluator boundary must be allowed")
    for boundary in read_only_boundaries:
        if boundary.method != "GET" or boundary.write_allowed:
            errors.append(f"read-only boundary is writable: {boundary.boundary_id}")
        if not boundary.owner or not boundary.auth or not boundary.failure_delivery:
            errors.append(f"read-only boundary lacks owner/auth/failure: {boundary.boundary_id}")
    if read_only_boundaries and read_only_with_fields != len(read_only_boundaries):
        errors.append("every read-only projection must carry owner/auth/failure")
    if not read_only_boundaries:
        errors.append("read-only projection boundary is missing")

    summary = ExecutionBoundarySummary(
        public_create_allowed=public_create_allowed,
        internal_evaluator_allowed=internal_evaluator_allowed,
        read_only_projection_count=len(read_only_boundaries),
        read_only_projection_with_owner_auth_failure=read_only_with_fields,
    )
    return ExecutionBoundaryValidation(valid=not errors, errors=tuple(errors), summary=summary)
