"""How much data one analysis is allowed to read, and on what basis it is chosen.

A five-year full-universe load (1,717 PIT members, 3.2M price rows, four TA families
and every DART filing) took the production node 875 seconds and ~21GB before the
backtest even started, and then crashed on a bar that had no raw execution price. These
tests pin the four decisions that fixed it: a bound lookback, a point-in-time liquidity
cap on the universe, an inner join to raw OHLCV, and a sealed V1 rule that says which
metrics it actually needs.
"""

from datetime import date

import pytest

from ai_graph.data_sources.db import (
    AI_BACKTEST_LOOKBACK_YEARS_ENV,
    AI_BACKTEST_UNIVERSE_MAX_TICKERS_ENV,
    DataSourceConfig,
    PostgresPipelineDataSource,
    backtest_window_policy_id,
)

WINDOW = {"start": date(2025, 8, 12), "end": date(2026, 8, 11), "session_count": 246}


class RecordingConnection:
    """Captures the statement and its bind parameters, and answers with `rows`."""

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


# (a) window length


def test_window_binds_the_configured_lookback_years() -> None:
    connection = RecordingConnection([
        {"session_start": date(2025, 8, 12), "session_end": date(2026, 8, 11), "session_count": 246}
    ])

    window = _source(backtest_lookback_years=2)._resolve_backtest_window(connection)

    assert window["session_count"] == 246
    assert "make_interval(years => %s)" in connection.query
    # Bound, not interpolated: the length is configuration, so it must not reach the
    # statement text.
    assert "INTERVAL '" not in connection.query
    assert connection.params == [2]


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("0", 1), ("-3", 1), ("1", 1), ("3", 3), ("9", 3), ("", 1)],
)
def test_lookback_years_clamp_instead_of_failing_the_deployment(configured, expected) -> None:
    """An out-of-range env value must narrow the read, not take the service down."""

    config = DataSourceConfig.from_env(
        {"AI_DATABASE_DSN": "postgresql://example", AI_BACKTEST_LOOKBACK_YEARS_ENV: configured}
    )

    assert config.backtest_lookback_years == expected


def test_window_policy_id_carries_the_lookback_it_was_produced_under() -> None:
    """Two runs with different lookbacks must not claim the same reproducibility id."""

    assert backtest_window_policy_id(1) == "krx_pit_common_stock_1y_kst_settled_session_v3"
    assert backtest_window_policy_id(3) != backtest_window_policy_id(1)


# (b) universe cap


def test_universe_ranks_by_pre_window_traded_value_and_caps_in_the_database() -> None:
    connection = RecordingConnection([
        {"symbol": f"{i:06d}", "window_member_count": 1_717} for i in range(200)
    ])

    universe, descriptor = _source()._fetch_backtest_universe(connection, WINDOW)

    assert len(universe) == 200
    # The database ranks and caps; returning all 1,717 members to sort them in Python
    # is the load this cap exists to avoid.
    assert "avg(p.adj_close * p.adj_volume)" in connection.query
    assert "ORDER BY traded_value DESC NULLS LAST" in connection.query
    assert "LIMIT %(cap)s" in connection.query
    assert connection.params["cap"] == 200
    assert connection.params["ranking_sessions"] == 60
    # Point in time: the ranking window ends at the window start, so the selection uses
    # nothing that happened during the period being tested.
    assert "trade_date <= %(window_start)s::date" in connection.query
    # A name delisted during the window keeps its rows; only a listing that ended before
    # the window carries none at all.
    assert "(h.valid_to IS NULL OR h.valid_to >= %(window_start)s::date)" in connection.query
    assert "core.symbol_security_type_history" in connection.query


def test_universe_descriptor_reports_what_the_cap_cut() -> None:
    connection = RecordingConnection([
        {"symbol": "000660", "window_member_count": 1_717},
        {"symbol": "005930", "window_member_count": 1_717},
    ])

    _, descriptor = _source(backtest_universe_max_tickers=2)._fetch_backtest_universe(
        connection, WINDOW
    )

    assert descriptor["selection"] == "lifecycle_pit_common_stock_window_top_traded"
    assert descriptor["member_count"] == 2
    assert descriptor["window_member_count"] == 1_717
    assert descriptor["excluded_member_count"] == 1_715
    assert descriptor["max_tickers"] == 2
    assert descriptor["ranking_sessions"] == 60
    assert descriptor["ranking_window_end"] == "2025-08-12"
    assert descriptor["delisting_policy"] == "official-event-then-final-close-v1"


def test_universe_max_tickers_is_configurable() -> None:
    config = DataSourceConfig.from_env(
        {"AI_DATABASE_DSN": "postgresql://example", AI_BACKTEST_UNIVERSE_MAX_TICKERS_ENV: "50"}
    )

    assert config.backtest_universe_max_tickers == 50


# (c) raw execution rows


def test_price_rows_require_a_raw_execution_bar() -> None:
    """An adjusted-only bar cannot be executed, so it must not be loaded.

    The backtest refused these with `raw_execution_unavailable:2021-09-01/044990`, after
    the loader had already paid to carry them through the whole feature frame.
    """

    connection = RecordingConnection()

    rows, sessions = _source()._fetch_price_rows(
        connection, ["000660"], {}, "RSI", WINDOW, (), requires_financials=False
    )

    assert rows == []
    assert sessions == WINDOW["session_count"]
    assert "JOIN core.ohlcv_daily raw" in connection.query
    assert "LEFT JOIN core.ohlcv_daily" not in connection.query


# (d) sealed V1 metric plan


def test_data_node_reads_the_sealed_v1_rule_before_loading(monkeypatch) -> None:
    """An RSI rule must load the momentum family only - not four TA families and DART.

    This is the spec the production FE path seals for an explicit rule, and it reached
    the loader with no plan at all, so every V1 run paid for the full-universe read.
    """

    from ai_graph.data_sources.db import indicator_families_for_metrics
    from ai_graph.graph import data_node

    spec = {
        "market": "KRX",
        "timeframe": "daily",
        "entry_conditions": [
            {"metric": "rsi", "comparator": "lte", "value": 30.0, "lookback": 14, "role": "entry"}
        ],
        "exit_conditions": [
            {"metric": "rsi", "comparator": "gte", "value": 70.0, "lookback": 14, "role": "exit"}
        ],
    }
    captured: dict[str, object] = {}

    def stop_after_capture(query, trace_id, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("data loader captured")

    monkeypatch.setattr("ai_graph.graph.load_pipeline_data_from_env", stop_after_capture)

    with pytest.raises(RuntimeError, match="data loader captured"):
        data_node(
            {
                "user_query": "RSI 30 이하 매수 70 이상 매도 전략을 검증해줘",
                "trace_id": "sealed-v1-plan",
                "execution_spec": spec,
            }
        )

    assert captured["required_metrics"] == ("rsi",)
    assert captured["requires_financials"] is False
    # V1 executes on raw prices, so it never takes the OHLCV-only projection.
    assert captured["compact_price_rows"] is False
    # The current-day screen is still presentation context for a V1 run.
    assert captured["screen_current"] is True
    assert indicator_families_for_metrics(("rsi",), include_default=False) == ("momentum",)


def test_data_node_asks_for_dart_only_when_the_sealed_v1_rule_names_a_fundamental(
    monkeypatch,
) -> None:
    from ai_graph.graph import data_node

    spec = {
        "market": "KRX",
        "timeframe": "daily",
        "entry_conditions": [
            {"metric": "roe", "comparator": "gte", "value": 0.1, "lookback": 14, "role": "entry"}
        ],
        "exit_conditions": [
            {"metric": "roe", "comparator": "lt", "value": 0.05, "lookback": 14, "role": "exit"}
        ],
    }
    captured: dict[str, object] = {}

    def stop_after_capture(query, trace_id, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("data loader captured")

    monkeypatch.setattr("ai_graph.graph.load_pipeline_data_from_env", stop_after_capture)

    with pytest.raises(RuntimeError, match="data loader captured"):
        data_node(
            {
                "user_query": "ROE 10% 이상이면 매수하는 전략을 검증해줘",
                "trace_id": "sealed-v1-fundamental",
                "execution_spec": spec,
            }
        )

    assert captured["required_metrics"] == ("roe",)
    assert captured["requires_financials"] is True
