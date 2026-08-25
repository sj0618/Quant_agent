from __future__ import annotations

from screening_pipeline_test_support import PRD_NAME, TEST_SPEC_NAME, assert_has_all, plan_text


def test_source_adapter_failure_subcauses_are_stable() -> None:
    expected_subcauses = {
        "krx_api_error",
        "dart_api_error",
        "websearch_unavailable",
        "external_source_rate_limited",
        "source_mapping_gap",
        "disclosure_mapping_gap",
        "freshness_gap",
        "parser_low_confidence",
        "source_conflict",
    }
    combined = "\n".join([plan_text(PRD_NAME), plan_text(TEST_SPEC_NAME)])

    assert_has_all(combined, expected_subcauses)
