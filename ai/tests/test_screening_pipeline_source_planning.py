from __future__ import annotations

from screening_pipeline_test_support import (
    FORBIDDEN_DB_REQUIREMENTS,
    PRD_NAME,
    REQUIRED_DATA_REQUIREMENT_FIELDS,
    TEST_SPEC_NAME,
    assert_has_all,
    plan_text,
)


def test_source_priority_fallback_matrix_is_documented_without_db_ownership_creep() -> None:
    combined = "\n".join([plan_text(PRD_NAME), plan_text(TEST_SPEC_NAME)])

    assert_has_all(
        combined,
        {
            "OHLCV/TA",
            "Internal DB",
            "KRX",
            "DART",
            "AOAI Web Search",
            "analyst evidence",
            "outside_owner",
            "product_data_gap",
        },
    )
    for forbidden in FORBIDDEN_DB_REQUIREMENTS:
        assert forbidden in combined, "forbidden DB requirements must stay documented as boundaries"


def test_proxy_disclosure_contract_blocks_silent_proxy_use() -> None:
    proxy_requirement = {
        "family": "fundamentals",
        "required": True,
        "availability": "partial",
        "owner": "product_data_gap",
        "proxy_allowed": True,
        "proxy_used": True,
        "proxy_disclosure": {
            "substituted_data": "fundamentals",
            "proxy_data": "technical_relative_strength",
            "reason": "fundamentals source unavailable",
        },
        "preferred_source": "internal_db",
        "fallback_sources": ["dart"],
        "freshness_requirement": "report_period",
        "evidence_ref": "evidence:proxy:fundamentals",
    }

    assert proxy_requirement["proxy_used"] is True
    assert proxy_requirement["proxy_disclosure"]
    assert set(proxy_requirement) == REQUIRED_DATA_REQUIREMENT_FIELDS
