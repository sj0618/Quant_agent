"""Fail-closed lineage quality SLO enforcement for ingestion outputs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, TypeVar

DEFAULT_MIN_LINEAGE_COVERAGE = 1.0
T = TypeVar("T")


class LineageQualitySLOViolation(RuntimeError):
    """Raised before an ingestion result can be consumed downstream."""


@dataclass(frozen=True)
class LineageQualityReport:
    target_rows: int
    lineage_rows: int
    coverage_ratio: float
    min_coverage: float
    passed: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_lineage_quality(
    *,
    target_rows: int,
    lineage_rows: int,
    min_coverage: float = DEFAULT_MIN_LINEAGE_COVERAGE,
) -> LineageQualityReport:
    if target_rows < 0 or lineage_rows < 0:
        raise ValueError("lineage row counts must be non-negative")
    if not 0.0 <= min_coverage <= 1.0:
        raise ValueError("min_coverage must be between 0 and 1")
    coverage = lineage_rows / target_rows if target_rows else 0.0
    passed = target_rows > 0 and lineage_rows <= target_rows and coverage >= min_coverage
    reason = None if passed else "lineage quality SLO is below the required coverage"
    return LineageQualityReport(
        target_rows=target_rows,
        lineage_rows=lineage_rows,
        coverage_ratio=coverage,
        min_coverage=min_coverage,
        passed=passed,
        reason=reason,
    )


def require_lineage_quality(report: LineageQualityReport) -> LineageQualityReport:
    if not report.passed:
        raise LineageQualitySLOViolation(report.reason or "lineage quality SLO failed")
    return report


def guard_downstream_result(
    report: LineageQualityReport,
    result_factory: Callable[[], T],
) -> T:
    """Create a downstream result only after the lineage SLO has passed."""

    require_lineage_quality(report)
    return result_factory()
