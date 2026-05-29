from ai_graph.graph import DEBUG_STORE, run_analysis


BOLLINGER_PROMPT = "볼린저 밴드 하단 이탈 뒤 종가가 하단 밴드 위로 재진입하며 반등하는 KOSPI200 종목을 찾아줘."


def test_bollinger_lower_band_reentry_preserves_semantic_slots_before_strategy() -> None:
    envelope = run_analysis(BOLLINGER_PROMPT, trace_id="trace-bollinger-reentry")

    assert envelope.status == "ready"
    assert envelope.semantic_slots is not None
    assert "bollinger" in envelope.semantic_slots.indicator
    assert "lower_band_reentry" in envelope.semantic_slots.event
    assert "close" in envelope.semantic_slots.price_basis
    assert envelope.semantic_slots.parse_status == "ready"
    assert envelope.strategy_spec is not None
    assert envelope.strategy_spec.strategy_id == "bollinger_lower_reentry_a"
    assert all(condition.left != "rsi" for condition in envelope.strategy_spec.entry_conditions)


def test_public_envelope_exposes_safe_diagnostics_without_internal_payload() -> None:
    envelope = run_analysis(BOLLINGER_PROMPT, trace_id="trace-safe-diagnostics")
    dumped = envelope.model_dump()

    assert dumped["data_requirements"]
    assert dumped["source_usage"]
    assert dumped["evidence_refs"]
    assert dumped["freshness_status"] in {"fresh", "unknown"}
    assert "internal_payload" not in dumped
    assert "node_outputs" not in dumped
    assert "llm_prompts" not in dumped

    debug_payload = DEBUG_STORE.get(envelope.debug_ref)
    assert debug_payload is not None
    assert debug_payload.validation["semantic_parse_status"] == "ready"
