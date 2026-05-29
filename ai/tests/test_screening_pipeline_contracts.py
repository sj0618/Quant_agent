from __future__ import annotations

from ai_graph.graph import run_analysis

from screening_pipeline_test_support import (
    ALLOWED_SOURCE_TYPES,
    FAILURE_CATEGORIES,
    FAILURE_FIELDS,
    PRD_NAME,
    REQUIRED_DATA_REQUIREMENT_FIELDS,
    REQUIRED_SOURCE_USAGE_FIELDS,
    TEST_SPEC_NAME,
    assert_has_all,
    assert_public_text_is_redacted,
    plan_text,
)


def test_plan_documents_define_node_refinement_contracts() -> None:
    prd = plan_text(PRD_NAME)
    spec = plan_text(TEST_SPEC_NAME)

    assert_has_all(prd, REQUIRED_DATA_REQUIREMENT_FIELDS)
    assert_has_all("\n".join([prd, spec]), REQUIRED_SOURCE_USAGE_FIELDS)
    assert_has_all(prd, FAILURE_CATEGORIES)
    assert_has_all(spec, REQUIRED_DATA_REQUIREMENT_FIELDS)
    assert_has_all(spec, REQUIRED_SOURCE_USAGE_FIELDS)
    assert_has_all(spec, FAILURE_FIELDS)


def test_public_envelope_keeps_existing_fields_and_internal_boundary() -> None:
    envelope = run_analysis("RSI가 30 이하인 KOSPI200 종목을 찾아줘", trace_id="screen-contract")
    dumped = envelope.model_dump(mode="json")

    assert set(dumped) == {
        "status",
        "trace_id",
        "schema_version",
        "user_payload",
        "strategy_spec",
        "debug_ref",
        "retryable",
    }
    assert dumped["debug_ref"]
    assert "internal_payload" not in dumped
    assert "node_outputs" not in dumped
    assert "llm_prompts" not in dumped


def test_diagnostic_contract_examples_are_machine_readable_and_redacted() -> None:
    data_requirement = {
        "family": "disclosure",
        "required": True,
        "availability": "partial",
        "owner": "ai_graph",
        "proxy_allowed": False,
        "proxy_used": False,
        "proxy_disclosure": {},
        "preferred_source": "dart",
        "fallback_sources": ["aoai_web_search"],
        "freshness_requirement": "latest_filing",
        "evidence_ref": "evidence:disclosure:latest-filing",
    }
    source_usage = {
        "source_type": "dart",
        "query": {"ticker": "005930", "window": "latest_filing"},
        "retrieved_at": "2026-05-29T00:00:00Z",
        "source_refs": ["dart:filing:example"],
        "confidence": 0.9,
        "freshness_status": "fresh",
        "fallback_used": False,
        "evidence_ref": "evidence:dart:example",
    }

    assert set(data_requirement) == REQUIRED_DATA_REQUIREMENT_FIELDS
    assert set(source_usage) == REQUIRED_SOURCE_USAGE_FIELDS
    assert source_usage["source_type"] in ALLOWED_SOURCE_TYPES
    assert_public_text_is_redacted(str(data_requirement))
    assert_public_text_is_redacted(str(source_usage))
