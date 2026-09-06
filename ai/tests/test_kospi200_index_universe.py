"""KOSPI200 as a universe constraint, and the honesty it has to keep.

The deployed site refused "RSI(14)가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 파는
전략" because "KOSPI200 종목" is a point-in-time constituent filter the research grammar
could not seal. It now can - but only when feature.krx_index_membership_history holds
KOSPI200 intervals. On a warehouse without them the request is refused before any
research runs, with the missing membership named as the reason, rather than being
widened to the whole market or approximated by market cap.
"""

from datetime import date

import pytest

from ai_graph.data_sources.db import (
    WICS_SECTOR_HISTORY_TABLE,
    DataSourceConfig,
    PipelineDataUnavailableError,
    PostgresPipelineDataSource,
)
from ai_graph.data_sources.index_universes import (
    INDEX_MEMBERSHIP_HISTORY_TABLE,
    clear_index_universe_cache,
    extract_index_universe_from_query,
    get_known_index_universes,
)
from ai_graph.nodes import strategy_research
from ai_graph.nodes.strategy_research import (
    StrategyResearchError,
    _RepairableStrategyResearchError,
    _seal_research_response,
    research_strategy_execution_spec,
)
from ai_graph.research_contract import _no_run_parse

QUERY = "RSI(14)가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 파는 전략"
WINDOW = {"start": date(2025, 8, 12), "end": date(2026, 8, 11), "session_count": 246}


class RecordingConnection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.query = ""
        self.params: object = None

    def execute(self, query, params=None):
        self.query, self.params = query, params
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


def _source() -> PostgresPipelineDataSource:
    return PostgresPipelineDataSource(DataSourceConfig(database_dsn="postgresql://example"))


# (a) the loader


def test_index_membership_is_an_interval_overlap_bound_to_the_index_code() -> None:
    connection = RecordingConnection([{"symbol": "005930", "window_member_count": 212}])

    universe, descriptor = _source()._fetch_backtest_universe(
        connection, WINDOW, None, "KOSPI200"
    )

    assert universe == ["005930"]
    assert INDEX_MEMBERSHIP_HISTORY_TABLE in connection.query
    assert "im.index_code = %(index_universe)s" in connection.query
    # Survivorship-safe like the sector filter: a name that was a constituent for part
    # of the window is a member, not only the names in the index today.
    assert "im.valid_from <= %(window_end)s::date" in connection.query
    assert "(im.valid_to IS NULL OR im.valid_to >= %(window_start)s::date)" in connection.query
    assert connection.params["index_universe"] == "KOSPI200"
    assert descriptor["index_universe"] == "KOSPI200"
    assert descriptor["index_membership_source"] == INDEX_MEMBERSHIP_HISTORY_TABLE
    assert descriptor["index_membership"] == "interval_overlapping_window"
    assert descriptor["selection"] == (
        "lifecycle_pit_common_stock_window_top_traded_index_restricted"
    )
    assert descriptor["window_member_count"] == 212


def test_without_an_index_the_optional_membership_table_is_not_named_at_all() -> None:
    """The table is optional. PostgreSQL rejects a statement that names a missing table
    even behind a NULL parameter, so an unrestricted load must not mention it."""

    connection = RecordingConnection([{"symbol": "005930", "window_member_count": 1_717}])

    _, descriptor = _source()._fetch_backtest_universe(connection, WINDOW)

    assert INDEX_MEMBERSHIP_HISTORY_TABLE not in connection.query
    assert connection.params["index_universe"] is None
    assert descriptor["index_universe"] is None
    assert descriptor["index_membership_source"] is None
    assert descriptor["selection"] == "lifecycle_pit_common_stock_window_top_traded"


def test_a_sector_and_an_index_compose_into_one_universe() -> None:
    connection = RecordingConnection([{"symbol": "000660", "window_member_count": 9}])

    _, descriptor = _source()._fetch_backtest_universe(connection, WINDOW, "반도체", "KOSPI200")

    assert WICS_SECTOR_HISTORY_TABLE in connection.query
    assert INDEX_MEMBERSHIP_HISTORY_TABLE in connection.query
    assert connection.params["sector"] == "반도체"
    assert connection.params["index_universe"] == "KOSPI200"
    assert descriptor["selection"].endswith("_sector_restricted_index_restricted")


def test_an_empty_index_universe_says_the_index_rather_than_the_market() -> None:
    class EmptyUniverse(PostgresPipelineDataSource):
        def _fetch_backtest_universe(self, _conn, _window, _sector=None, index_universe=None):
            return [], {}

    with pytest.raises(PipelineDataUnavailableError) as failure:
        EmptyUniverse(DataSourceConfig(database_dsn="postgresql://example"))._load_pit_market(
            RecordingConnection(), WINDOW, "질의", (), False, {}, index_universe="KOSPI200"
        )

    assert failure.value.reason == "pit_index_universe_empty"
    assert "KOSPI200" in str(failure.value)


# (b) what the warehouse offers


def test_index_universes_are_offered_exactly_when_membership_rows_exist() -> None:
    clear_index_universe_cache()
    assert get_known_index_universes(RecordingConnection([{"index_code": "KOSPI200"}])) == [
        "KOSPI200"
    ]

    class MissingTable:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError('relation "feature.krx_index_membership_history" does not exist')

    clear_index_universe_cache()
    # No static fallback: an index the loader cannot filter by is not offered.
    assert get_known_index_universes(MissingTable()) == []
    clear_index_universe_cache()
    assert get_known_index_universes(RecordingConnection([])) == []


def test_the_spellings_users_type_resolve_to_one_index_code() -> None:
    for spelling in ("KOSPI200", "kospi 200", "코스피200", "코스피 200"):
        assert extract_index_universe_from_query(f"RSI 30 이하 {spelling} 종목") == "KOSPI200"
    assert extract_index_universe_from_query("코스닥150 종목 중 RSI 30 이하") == "KOSDAQ150"
    # A market is not an index; "코스피 종목" stays the KRX-wide PIT universe.
    assert extract_index_universe_from_query("RSI 30 이하 코스피 종목") is None


# (c) research


class _NeverCalledClient:
    def generate_json(self, _request):
        raise AssertionError("provider boundary reached")


class _ScriptedClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def generate_json(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def _payload(*, index_universe=None):
    candidate = {
        "candidate_id": "research-candidate-1",
        "title": "KOSPI200 RSI 과매도 반등",
        "hypothesis": "과매도 구간의 대형주는 단기 되돌림이 있다.",
        "counter_hypothesis": "추세 하락에서는 과매도가 이어진다.",
        "entry_conditions": [{"left": "rsi", "operator": "lte", "right": 30}],
        "exit_conditions": [{"left": "rsi", "operator": "gte", "right": 70}],
        "required_metrics": ["rsi"],
        "assumptions": ["KOSPI200 PIT 구성종목 기준"],
        "source_ids": ["source-1"],
        "backtest_years": 2,
        "backtest_period_basis": "테스트 AI가 데이터 조회 전에 2년을 선택했습니다.",
    }
    if index_universe is not None:
        candidate["index_universe"] = index_universe
    return {
        "resolution_summary": "RSI(14) 평균회귀 규칙을 KOSPI200 유니버스로 옮겼다.",
        "sources": [
            {
                "source_id": "source-1",
                "title": "RSI",
                "url": "https://example.com/rsi",
                "claim": "RSI 30 이하는 과매도로 읽힌다.",
            }
        ],
        "candidates": [candidate],
    }


def test_a_kospi200_request_is_refused_before_research_when_membership_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(strategy_research, "get_known_index_universes", list)

    with pytest.raises(StrategyResearchError) as failure:
        research_strategy_execution_spec(
            query=QUERY, available_metrics=["rsi"], llm_client=_NeverCalledClient()
        )

    assert failure.value.cause_code == "research_index_universe_unavailable"
    assert not isinstance(failure.value, _RepairableStrategyResearchError)
    assert "KOSPI200" in str(failure.value)
    assert "point-in-time membership" in str(failure.value)
    assert INDEX_MEMBERSHIP_HISTORY_TABLE in str(failure.value)
    # And the user reads that reason, not "we researched it but cannot run it".
    parsed = _no_run_parse(failure.value)
    assert parsed.clarification_required
    assert "구성종목" in parsed.explanation
    assert parsed.unsupported_conditions[0].reason.startswith("이 배포에는 KOSPI200")


def test_a_kospi200_request_seals_when_membership_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(strategy_research, "get_known_index_universes", lambda: ["KOSPI200"])
    client = _ScriptedClient(_payload(index_universe="KOSPI200"))

    spec = research_strategy_execution_spec(
        query=QUERY, available_metrics=["rsi"], llm_client=client
    )

    assert spec.candidates[0].index_universe == "KOSPI200"
    assert spec.candidates[0].sector is None
    context = client.requests[0].variables_jsonb["untrusted_quoted_context"]
    assert context["allowed_index_universes"] == ["KOSPI200"]


def test_a_dropped_index_universe_gets_the_one_repair_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without it the run would report a KRX-wide backtest as a KOSPI200 one."""

    monkeypatch.setattr(strategy_research, "get_known_index_universes", lambda: ["KOSPI200"])
    client = _ScriptedClient(_payload(), _payload(index_universe="KOSPI200"))

    spec = research_strategy_execution_spec(
        query=QUERY, available_metrics=["rsi"], llm_client=client
    )

    assert len(client.requests) == 2
    failure = client.requests[1].variables_jsonb["untrusted_quoted_context"]
    assert failure["previous_validation_failure"]["code"] == "research_index_universe_dropped"
    assert failure["allowed_index_universes"] == ["KOSPI200"]
    assert spec.candidates[0].index_universe == "KOSPI200"


def test_an_index_the_warehouse_does_not_know_is_refused_at_seal_time() -> None:
    with pytest.raises(StrategyResearchError) as failure:
        _seal_research_response(
            _payload(index_universe="KOSDAQ150"),
            query="코스닥150 종목 중 RSI 30 이하 매수",
            allowed_metrics=("rsi",),
            allowed_index_universes=("KOSPI200",),
        )

    assert failure.value.cause_code == "research_index_universe_unavailable"
    # A repair turn cannot add membership rows, so this one is terminal.
    assert not isinstance(failure.value, _RepairableStrategyResearchError)


def test_the_prompt_tells_the_model_a_market_name_is_not_an_index() -> None:
    """Observed on the deployed release: with an empty ``allowed_index_universes`` the
    model refused "코스피 종목" as an unavailable KOSPI universe filter. The default PIT
    universe already is the KOSPI/KOSDAQ market, and the prompt has to say so."""

    prompt = strategy_research.STRATEGY_RESEARCH_SYSTEM_PROMPT
    assert "A bare market name - 코스피/KOSPI, 코스닥/KOSDAQ" in prompt
    assert "is NOT an index and needs no ``index_universe``" in prompt
    assert "never a reason to refuse a market-wide or market-named request" in prompt
    assert extract_index_universe_from_query("RSI 30 이하 코스피 종목") is None


def test_a_request_without_an_index_is_untouched_by_the_gate() -> None:
    spec = _seal_research_response(
        _payload(),
        query="RSI(14)가 30 이하로 떨어진 코스피 종목을 사고, 70 이상이면 파는 전략",
        allowed_metrics=("rsi",),
        allowed_index_universes=(),
    )

    assert spec.candidates[0].index_universe is None
