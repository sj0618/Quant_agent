import pytest

from quant_agent.data.lineage_quality import (
    LineageQualitySLOViolation,
    assess_lineage_quality,
    guard_downstream_result,
)


def test_complete_lineage_coverage_passes_the_slo() -> None:
    report = assess_lineage_quality(target_rows=10, lineage_rows=10)

    assert report.passed is True
    assert report.coverage_ratio == 1.0
    assert report.reason is None


def test_lineage_fail_closed_blocks_downstream_result_creation() -> None:
    report = assess_lineage_quality(target_rows=10, lineage_rows=9)
    created = []

    with pytest.raises(LineageQualitySLOViolation, match="below the required coverage"):
        guard_downstream_result(report, lambda: created.append("downstream-result"))

    assert created == []


def test_lineage_fail_closed_on_empty_or_overreported_input() -> None:
    empty = assess_lineage_quality(target_rows=0, lineage_rows=0)
    overreported = assess_lineage_quality(target_rows=10, lineage_rows=11)

    assert empty.passed is False
    assert overreported.passed is False
