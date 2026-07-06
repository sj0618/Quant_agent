from __future__ import annotations

from screening_pipeline_test_support import PRD_NAME, TEST_SPEC_NAME, assert_has_all, plan_text


def test_semantic_extraction_requirements_are_structured_not_free_form_only() -> None:
    combined = "\n".join([plan_text(PRD_NAME), plan_text(TEST_SPEC_NAME)])

    assert_has_all(
        combined,
        {
            "JSON-schema constrained",
            "semantic_slots",
            "confidence",
            "missing_slots",
            "contradictions",
            "source_needed",
            "extraction_method",
        },
    )


def test_strategy_family_slot_rules_cover_required_families() -> None:
    spec = plan_text(TEST_SPEC_NAME)

    assert_has_all(
        spec,
        {
            "Bollinger",
            "RSI",
            "MACD",
            "Moving average",
            "Volume breakout",
            "52-week high",
            "Disclosure/event",
            "Earnings event",
        },
    )
