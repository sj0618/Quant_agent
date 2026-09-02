"""Two things the deployed site used to refuse, and the honesty each one has to keep.

"반도체 섹터에서 RSI 30 이하 종목 매수" was refused because no point-in-time sector
universe was reachable, and "PER 10 이하 저평가 가치주" because PER was not in the metric
vocabulary. The warehouse has both inputs - feature.wics_symbol_sector_history as
membership intervals, and DART annual EPS - so these pin that they are used, and used
point-in-time: sector membership by interval overlap rather than "what sector is it in
today", PER from the annual EPS filed as of the bar rather than the newest quarter.
"""

from datetime import date

import pytest

from ai_graph.data_sources.db import (
    DART_ANNUAL_REPORT_CODE,
    WICS_SECTOR_HISTORY_TABLE,
    DataSourceConfig,
    PipelineDataUnavailableError,
    PostgresPipelineDataSource,
    _attach_pointintime_financials,
    available_indicator_metrics,
)
from ai_graph.nodes.condition_compiler import canonical_metric, supported_metrics
from ai_graph.nodes.strategy_research import (
    StrategyResearchError,
    _allowed_metrics,
    _seal_research_response,
)

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


def _source(**config) -> PostgresPipelineDataSource:
    return PostgresPipelineDataSource(
        DataSourceConfig(database_dsn="postgresql://example", **config)
    )


# (a) the sector universe


def test_sector_membership_is_an_interval_overlap_not_the_current_sector() -> None:
    connection = RecordingConnection([{"symbol": "000660", "window_member_count": 166}])

    universe, descriptor = _source()._fetch_backtest_universe(connection, WINDOW, "반도체")

    assert universe == ["000660"]
    assert WICS_SECTOR_HISTORY_TABLE in connection.query
    # Survivorship-safe: a name that was in the sector for part of the window is a
    # member of it. Testing the sector "as of today" would drop exactly the names whose
    # membership ended, which is the bias the lifecycle universe exists to avoid.
    assert "w.valid_from <= %(window_end)s::date" in connection.query
    assert "(w.valid_to IS NULL OR w.valid_to >= %(window_start)s::date)" in connection.query
    assert connection.params["sector"] == "반도체"
    assert descriptor["sector"] == "반도체"
    assert descriptor["sector_membership"] == "wics_interval_overlapping_window"
    assert descriptor["selection"].endswith("sector_restricted")
    assert descriptor["member_count"] == 1
    assert descriptor["window_member_count"] == 166


def test_no_sector_leaves_the_krx_wide_universe_exactly_as_it_was() -> None:
    connection = RecordingConnection([{"symbol": "005930", "window_member_count": 1_717}])

    _, descriptor = _source()._fetch_backtest_universe(connection, WINDOW)

    # The filter is bound, not spliced, so an unrestricted load runs the same statement.
    assert connection.params["sector"] is None
    assert "%(sector)s::text IS NULL" in connection.query
    assert descriptor["selection"] == "lifecycle_pit_common_stock_window_top_traded"
    assert descriptor["sector"] is None


def test_an_empty_sector_universe_says_the_sector_rather_than_the_market() -> None:
    """A refusal has to name what was actually empty, or it reads as a broken warehouse."""

    class EmptyUniverse(PostgresPipelineDataSource):
        def _fetch_backtest_universe(self, _conn, _window, _sector=None):
            return [], {}

    with pytest.raises(PipelineDataUnavailableError) as failure:
        EmptyUniverse(DataSourceConfig(database_dsn="postgresql://example"))._load_pit_market(
            RecordingConnection(), WINDOW, "질의", (), False, {}, sector="반도체"
        )

    assert failure.value.reason == "pit_sector_universe_empty"
    assert "반도체" in str(failure.value)


# (b) PER


def test_per_is_priced_per_bar_from_the_annual_eps_known_that_day() -> None:
    rows = [
        {"ticker": "005930", "date": "2026-03-21", "raw_close": 80_000.0},
        {"ticker": "005930", "date": "2026-03-22", "raw_close": 80_000.0},
        {"ticker": "005930", "date": "2026-03-23", "raw_close": 40_000.0},
    ]
    _attach_pointintime_financials(
        rows,
        {"005930": [{"filed": date(2026, 3, 21), "ratios": {"eps": 8_000.0}}]},
    )

    # A date-only receipt is eligible on the next session, the same rule the other
    # forward-filled financials follow. PER cannot precede the filing.
    assert "per" not in rows[0]
    assert rows[1]["per"] == pytest.approx(10.0)
    # Same filing, different bar: PER moves with the price, not only with the filing.
    assert rows[2]["per"] == pytest.approx(5.0)


def test_per_is_unset_for_a_loss_maker_so_a_cheapness_rule_cannot_match_one() -> None:
    rows = [{"ticker": "000000", "date": "2026-03-23", "raw_close": 10_000.0}]
    _attach_pointintime_financials(
        rows,
        {"000000": [{"filed": date(2026, 3, 21), "ratios": {"eps": -500.0}}]},
    )

    assert "per" not in rows[0]


def test_per_uses_the_as_reported_close_not_the_split_adjusted_one() -> None:
    """EPS is filed unadjusted; pairing it with a back-adjusted close invents a PER."""

    rows = [{"ticker": "005930", "date": "2026-03-23", "close": 1_600.0, "raw_close": 80_000.0}]
    _attach_pointintime_financials(
        rows,
        {"005930": [{"filed": date(2026, 3, 21), "ratios": {"eps": 8_000.0}}]},
    )

    assert rows[0]["per"] == pytest.approx(10.0)


def test_eps_is_read_from_the_annual_report_only() -> None:
    """A quarterly EPS is a three-month figure; mixing the two moves PER by ~4x."""

    connection = RecordingConnection()
    _source()._fetch_financial_timeline(connection, ["005930"])

    assert "CASE WHEN report_code = %s THEN" in connection.query
    assert connection.params[0] == DART_ANNUAL_REPORT_CODE


def test_annual_eps_survives_the_quarterly_filings_that_follow_it() -> None:
    """The forward-fill swaps the whole ratio dict, so EPS has to be carried forward."""

    connection = RecordingConnection([
        {
            "symbol": "005930", "filed": date(2026, 3, 10), "equity": 100.0,
            "liabilities": None, "profit_loss": None, "revenue": None,
            "operating_income": None, "annual_eps": 6_605.0,
        },
        {
            "symbol": "005930", "filed": date(2026, 5, 15), "equity": 100.0,
            "liabilities": None, "profit_loss": None, "revenue": None,
            "operating_income": None, "annual_eps": None,
        },
    ])

    timeline = _source()._fetch_financial_timeline(connection, ["005930"])

    assert [filing["ratios"]["eps"] for filing in timeline["005930"]] == [6_605.0, 6_605.0]


def test_per_is_a_compiler_metric_and_an_alias_resolves_to_it() -> None:
    assert "per" in supported_metrics()
    assert canonical_metric("PE_Ratio") == "per"


def test_per_is_offered_to_research_exactly_when_dart_filings_exist() -> None:
    class Catalog:
        def __init__(self, *, financials: bool) -> None:
            self.financials = financials
            self._last = ""

        def execute(self, query, params=None):
            self._last = query
            return self

        def fetchall(self):
            return []

        def fetchone(self):
            return {"present": self.financials}

    assert "per" in available_indicator_metrics(Catalog(financials=True), as_of=date(2026, 8, 11))
    assert "per" not in available_indicator_metrics(
        Catalog(financials=False), as_of=date(2026, 8, 11)
    )
    # And the research node keeps it once the server has advertised it.
    assert "per" in _allowed_metrics(["per", "rsi"])


# (c) the refusal that must stay


def _payload(*, sector=None, metric="per"):
    candidate = {
        "candidate_id": "research-candidate-1",
        "title": "저평가 가치주",
        "hypothesis": "싼 이익 배수는 되돌아온다.",
        "counter_hypothesis": "싼 배수는 이익 훼손의 신호일 수 있다.",
        "entry_conditions": [{"left": metric, "operator": "lte", "right": 10}],
        "exit_conditions": [{"left": metric, "operator": "gt", "right": 20}],
        "required_metrics": [metric],
        "assumptions": ["PIT DART 연간 EPS 기준"],
        "source_ids": ["source-1"],
    }
    if sector is not None:
        candidate["sector"] = sector
    return {
        "resolution_summary": "저PER 전략을 검증 가능한 규칙으로 옮겼다.",
        "sources": [
            {
                "source_id": "source-1",
                "title": "Value investing",
                "url": "https://example.com/value",
                "claim": "낮은 PER은 가치 지표로 쓰인다.",
            }
        ],
        "candidates": [candidate],
    }


def test_a_named_sector_is_sealed_onto_the_candidate() -> None:
    spec = _seal_research_response(
        _payload(sector="반도체", metric="rsi"),
        query="반도체 섹터에서 RSI 30 이하 종목 매수",
        allowed_metrics=("rsi",),
        allowed_sectors=("반도체", "화학"),
    )

    assert spec.candidates[0].sector == "반도체"


def test_a_sector_the_warehouse_does_not_know_is_still_refused() -> None:
    with pytest.raises(StrategyResearchError) as failure:
        _seal_research_response(
            _payload(sector="우주항공", metric="rsi"),
            query="우주항공 섹터에서 RSI 30 이하 종목 매수",
            allowed_metrics=("rsi",),
            allowed_sectors=("반도체", "화학"),
        )

    assert failure.value.cause_code == "research_sector_unsupported"


def test_a_named_sector_cannot_be_quietly_dropped_into_a_market_wide_test() -> None:
    """Without the sector the run would report a KRX-wide backtest as a sector one."""

    with pytest.raises(StrategyResearchError) as failure:
        _seal_research_response(
            _payload(metric="rsi"),
            query="반도체 섹터에서 RSI 30 이하 종목 매수",
            allowed_metrics=("rsi",),
            allowed_sectors=("반도체", "화학"),
        )

    assert failure.value.cause_code == "research_sector_dropped"


def test_a_per_rule_seals_when_the_deployment_has_financials() -> None:
    spec = _seal_research_response(
        _payload(),
        query="PER 10 이하 저평가 가치주 매수 전략",
        allowed_metrics=("per",),
        allowed_sectors=("반도체",),
    )

    assert spec.candidates[0].required_metrics == ["per"]
    assert spec.candidates[0].sector is None
