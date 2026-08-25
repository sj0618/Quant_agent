from ai_graph.data_sources.sectors import clear_sector_cache
from ai_graph.graph import build_strategy_spec, parse_semantic_slots, strategy_candidate_cards


def setup_function() -> None:
    clear_sector_cache()


def test_parse_semantic_slots_extracts_sector() -> None:
    slots = parse_semantic_slots(
        "반도체 섹터에서 RSI 30 이하로 과매도된 종목 찾아줘", trace_id="trace-slot-sector"
    )

    assert slots.sector == "반도체"


def test_parse_semantic_slots_sector_is_none_when_absent() -> None:
    slots = parse_semantic_slots(
        "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어",
        trace_id="trace-slot-no-sector",
    )

    assert slots.sector is None
    assert "universe" not in slots.model_dump()


def test_parse_semantic_slots_extracts_rsi_threshold_without_mentioning_30() -> None:
    slots = parse_semantic_slots(
        "RSI 70 이상이면 사고 싶어", trace_id="trace-slot-rsi-70-only"
    )

    assert "rsi" in slots.indicator
    assert "rsi >= 70" in slots.threshold


def test_build_strategy_spec_propagates_sector() -> None:
    query = "반도체 섹터에서 RSI 30 이하로 과매도된 종목 찾아줘"
    slots = parse_semantic_slots(query, trace_id="trace-spec-sector")

    spec = build_strategy_spec(
        query, variant="A", semantic_slots=slots.model_dump()
    )

    assert spec.sector == "반도체"
    assert "universe" not in spec.model_dump()
    assert "반도체" in spec.name


def test_build_strategy_spec_does_not_create_a_market_scope_field() -> None:
    query = "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어"
    slots = parse_semantic_slots(query, trace_id="trace-spec-kospi200")

    spec = build_strategy_spec(
        query, variant="A", semantic_slots=slots.model_dump()
    )

    assert spec.sector is None
    assert "universe" not in spec.model_dump()


def test_strategy_candidate_cards_without_screening_data_is_unchanged() -> None:
    query = "저평가주 사줘"

    baseline = strategy_candidate_cards(query)
    with_none = strategy_candidate_cards(query, screening_candidates=None, sector=None)

    assert [card.model_dump() for card in baseline] == [card.model_dump() for card in with_none]


def test_strategy_candidate_cards_attaches_sector_filtered_matches() -> None:
    screening_candidates = [
        {
            "ticker": "000660",
            "name": "SK하이닉스",
            "market": "KOSPI",
            "sector": "반도체",
            "as_of_date": "2026-05-20",
        },
        {
            "ticker": "051910",
            "name": "LG화학",
            "market": "KOSPI",
            "sector": "화학",
            "as_of_date": "2026-05-20",
        },
    ]

    cards = strategy_candidate_cards(
        "반도체 섹터에서 RSI 과매도 종목 찾아줘",
        screening_candidates=screening_candidates,
        sector="반도체",
    )

    assert cards[0].sector == "반도체"
    assert [match.ticker for match in cards[0].matches] == ["000660"]
    assert "반도체" in cards[0].title


def test_strategy_candidate_cards_keep_every_condition_match() -> None:
    screening_candidates = [
        {
            "ticker": f"{index:06d}",
            "name": f"종목 {index}",
            "market": "KOSPI",
            "sector": "반도체",
            "as_of_date": "2026-05-20",
        }
        for index in range(1, 13)
    ]

    cards = strategy_candidate_cards(
        "반도체 조건 종목을 모두 찾아줘",
        screening_candidates=screening_candidates,
        sector="반도체",
    )

    assert [match.ticker for match in cards[0].matches] == [
        f"{index:06d}" for index in range(1, 13)
    ]
