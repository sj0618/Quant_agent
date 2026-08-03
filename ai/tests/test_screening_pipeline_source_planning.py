import pytest

from ai_graph.data_sources import screening_data_families, screening_profile
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


def test_plan_covers_strategies_phrased_outside_the_slot_keyword_table() -> None:
    """The plan must describe the run that actually executes.

    "반도체 섹터 주도주 중 상대강도 강한 종목" sets no semantic slot - none of
    상대강도/주도주 appear in the indicator keyword table - so the plan came back empty
    and the run reported "조회할 데이터 항목 0종". The loader meanwhile screened the
    whole universe on price/TA and backtested 233 names, because it routes on the
    screening profile and never reads the plan. Grounding the plan in that same profile
    is what keeps the two describing one run.
    """

    query = "반도체 섹터 주도주 중 상대강도 강한 종목을 찾아줘."
    slots = parse_semantic_slots(query, trace_id="trace-leader-rs")

    assert slots.indicator == []  # the reason the old plan came out empty
    assert screening_profile(query) == "relative_strength"

    requirements = plan_data_requirements(slots, query=query)

    assert [requirement.family for requirement in requirements] == ["ohlcv_ta"]


@pytest.mark.parametrize(
    "query",
    [
        "반도체 섹터 주도주 중 상대강도 강한 종목을 찾아줘.",
        "저PER 고ROE 종목 골라줘",
        "코스피 시장에서 살만한 종목 추천해줘",
        "요즘 뜨는 종목 알려줘",
    ],
)
def test_every_screenable_query_plans_at_least_one_data_family(query: str) -> None:
    """No screenable request may plan zero families - that is the 0종 report.

    An empty plan now stops the run instead of being ignored, so a query that the
    loader would happily screen must never produce one.
    """

    slots = parse_semantic_slots(query, trace_id="trace-nonempty")
    requirements = plan_data_requirements(slots, query=query)

    assert requirements, f"planned no data for a screenable query: {query!r}"
    assert set(screening_data_families(query)) <= {r.family for r in requirements}
