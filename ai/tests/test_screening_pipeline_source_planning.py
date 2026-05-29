from ai_graph.graph import parse_semantic_slots, plan_data_requirements, data_source_inventory


def test_source_inventory_contains_internal_and_external_adapter_contracts() -> None:
    inventory = data_source_inventory()
    assert {source["source_type"] for source in inventory} >= {
        "internal_db",
        "krx",
        "dart",
        "aoai_web_search",
        "analyst_evidence",
    }


def test_data_planner_maps_technical_and_fundamental_families_without_schema_migration() -> None:
    slots = parse_semantic_slots(
        "저PER·고ROE·부채비율 100% 이하이고 볼린저 하단 재진입한 KOSPI200 종목",
        trace_id="trace-source-plan",
    )
    requirements = plan_data_requirements(slots)
    by_family = {requirement.family: requirement for requirement in requirements}

    assert by_family["ohlcv_ta"].preferred_source == "internal_db"
    assert "krx" in by_family["ohlcv_ta"].fallback_sources
    assert by_family["fundamentals"].preferred_source == "dart"
    assert by_family["fundamentals"].owner == "product_data_gap"
    assert all("schema" not in requirement.evidence_ref.lower() for requirement in requirements)
