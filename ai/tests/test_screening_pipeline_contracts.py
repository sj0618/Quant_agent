from ai_graph.graph import DEBUG_STORE, build_source_usage, run_analysis
from ai_graph.schemas import DataRequirement


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


def test_fixture_source_usage_does_not_claim_internal_database(monkeypatch) -> None:
    for env_name in ("AI_DATABASE_DSN", "QUANT_DB_DSN", "DATABASE_URL"):
        monkeypatch.delenv(env_name, raising=False)

    envelope = run_analysis(BOLLINGER_PROMPT, trace_id="trace-fixture-source-usage")

    assert envelope.source_usage
    assert all(usage.source_type == "none" for usage in envelope.source_usage)
    assert all(usage.fallback_used for usage in envelope.source_usage)
    assert all(usage.freshness_status == "unknown" for usage in envelope.source_usage)


def test_postgres_source_usage_does_not_invent_freshness_without_an_as_of_date() -> None:
    requirement = DataRequirement(
        family="ohlcv_ta",
        availability="available",
        owner="ai_graph",
        preferred_source="internal_db",
        fallback_sources=["krx"],
        freshness_requirement="same_trading_day",
        source_confidence_floor=0.85,
        evidence_ref="data-plan:ohlcv_ta",
    )

    usage = build_source_usage(
        "RSI가 35 이하인 전체 종목",
        [requirement],
        trace_id="trace-postgres-unknown-freshness",
        pipeline_metadata={
            "source": "postgres",
            "price_source": "feature.kis_adjusted_ohlcv_daily",
        },
    )

    assert usage[0].source_type == "internal_db"
    assert usage[0].freshness_status == "unknown"
