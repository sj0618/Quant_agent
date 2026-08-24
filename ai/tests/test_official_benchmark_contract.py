"""The official KOSPI/KOSDAQ TR benchmark contract, from the warehouse to the gate.

The primary benchmark used to be hardcoded unavailable, which made every automatic
request fail its acceptance gate regardless of performance. These tests pin the two ends
of the wiring that removed the deadlock: what the warehouse read returns when the tables
are missing, empty or present, and what the backtest does with the series once supplied.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_graph.data_sources.db import (
    OFFICIAL_BENCHMARK_INDEX_CODES,
    OFFICIAL_BENCHMARK_TR_VIEW,
    OFFICIAL_BENCHMARK_WEIGHT_VIEW,
    DataSourceConfig,
    PostgresPipelineDataSource,
    _official_benchmark_status,
)
from ai_graph.nodes import backtest as backtest_node
from ai_graph.schemas import (
    BacktestMetrics,
    CodeCandidate,
    Condition,
    ConditionOperator,
    StrategySpec,
)

WINDOW = {"start": date(2024, 1, 1), "end": date(2024, 6, 30), "session_count": 120}
DAILY_GROWTH = 1.001


def _sessions() -> list[str]:
    return [
        f"2024-{month:02d}-{day:02d}"
        for month in range(1, 7)
        for day in range(1, 21)
    ]


def _price_rows(sessions: list[str]) -> list[dict[str, object]]:
    return [
        {
            "date": session,
            "ticker": ticker,
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1_000_000.0,
        }
        for session in sessions
        for ticker in ("000001", "000002")
    ]


def _official_benchmark(
    sessions: list[str],
    *,
    kospi_base: float = 100.0,
    kosdaq_base: float = 250.0,
    weight_months: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Both legs growing at one identical rate.

    That makes the window's total return analytic - the compounded growth between the
    endpoints - no matter how the monthly rebalance splits the two legs, so the coverage
    assertions below do not silently depend on the rebalance arithmetic that
    test_backtest_optimization already covers.
    """

    all_sessions = _sessions()
    index_by_session = {session: index for index, session in enumerate(all_sessions)}
    months = weight_months or (
        "2023-12", "2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06",
    )
    return {
        "available": True,
        "unavailable_reason": None,
        "level_source": OFFICIAL_BENCHMARK_TR_VIEW,
        "weight_source": OFFICIAL_BENCHMARK_WEIGHT_VIEW,
        "index_codes": dict(OFFICIAL_BENCHMARK_INDEX_CODES),
        "window_start": "2024-01-01",
        "window_end": "2024-06-30",
        "weight_lag_months": 1,
        "kospi_tr": {
            session: kospi_base * DAILY_GROWTH ** index_by_session[session]
            for session in sessions
        },
        "kosdaq_tr": {
            session: kosdaq_base * DAILY_GROWTH ** index_by_session[session]
            for session in sessions
        },
        "monthly_weights": {month: [0.8, 0.2] for month in months},
    }


def _expected_total_return(sessions: list[str]) -> float:
    all_sessions = _sessions()
    index_by_session = {session: index for index, session in enumerate(all_sessions)}
    span = index_by_session[sessions[-1]] - index_by_session[sessions[0]]
    return DAILY_GROWTH ** span - 1.0


def test_supplied_official_series_makes_the_primary_benchmark_available() -> None:
    sessions = _sessions()
    context = backtest_node._build_benchmark_context(
        _price_rows(sessions), _official_benchmark(sessions)
    )
    provenance = backtest_node._benchmark_provenance(context)

    assert context.primary_available is True
    assert context.primary_unavailable_reason is None
    assert context.total_return == pytest.approx(_expected_total_return(sessions), abs=1e-6)
    assert provenance["primary"]["available"] is True
    assert provenance["primary"]["return"] == pytest.approx(context.total_return)
    assert provenance["primary"]["session_coverage"]["coverage_ratio"] == 1.0
    assert provenance["primary"]["session_coverage"]["covered_sessions"] == len(sessions)


def test_official_series_does_not_move_the_auxiliary_proxy_legs() -> None:
    """The gate must start working without any number it already compared changing."""

    sessions = _sessions()
    rows = _price_rows(sessions)
    without = backtest_node._build_benchmark_context(rows)
    with_official = backtest_node._build_benchmark_context(rows, _official_benchmark(sessions))

    assert with_official.daily_returns == without.daily_returns
    assert with_official.selection_return == without.selection_return
    assert with_official.selection_days == without.selection_days
    assert with_official.auxiliary_label == without.auxiliary_label


def test_one_missing_interior_session_stays_inside_the_coverage_budget() -> None:
    sessions = _sessions()
    served = [session for session in sessions if session != "2024-03-10"]
    context = backtest_node._build_benchmark_context(
        _price_rows(sessions), _official_benchmark(served)
    )

    assert context.primary_available is True
    assert context.primary_coverage["covered_sessions"] == len(sessions) - 1
    assert context.primary_coverage["coverage_ratio"] >= (
        backtest_node.OFFICIAL_BENCHMARK_MIN_SESSION_COVERAGE
    )
    # Skipped, not filled forward: the endpoints still set the headline number.
    assert context.total_return == pytest.approx(_expected_total_return(sessions), abs=1e-6)


def test_coverage_below_the_floor_is_unavailable_with_the_measured_shortfall() -> None:
    sessions = _sessions()
    dropped = {"2024-03-10", "2024-03-11", "2024-03-12", "2024-03-13", "2024-03-14"}
    served = [session for session in sessions if session not in dropped]
    context = backtest_node._build_benchmark_context(
        _price_rows(sessions), _official_benchmark(served)
    )

    assert context.primary_available is False
    assert context.total_return is None
    assert "115/120" in context.primary_unavailable_reason
    assert context.primary_coverage["coverage_ratio"] == pytest.approx(115 / 120)


def test_an_uncovered_endpoint_is_rejected_even_inside_the_coverage_budget() -> None:
    sessions = _sessions()
    served = sessions[:-1]
    context = backtest_node._build_benchmark_context(
        _price_rows(sessions), _official_benchmark(served)
    )

    assert context.primary_available is False
    assert context.primary_coverage["coverage_ratio"] >= (
        backtest_node.OFFICIAL_BENCHMARK_MIN_SESSION_COVERAGE
    )
    assert context.primary_coverage["last_session_covered"] is False
    assert "endpoints" in context.primary_unavailable_reason


def test_a_traded_month_without_the_prior_months_weights_is_unavailable() -> None:
    sessions = _sessions()
    supplied = _official_benchmark(
        sessions, weight_months=("2023-12", "2024-01", "2024-03", "2024-04", "2024-05")
    )
    context = backtest_node._build_benchmark_context(_price_rows(sessions), supplied)

    # 2024-02 needs the 2024-01 row (present) and 2024-03 needs 2024-02 (missing), so the
    # curve refuses rather than carrying January's split into March.
    assert context.primary_available is False
    assert "missing lagged official benchmark weights for 2024-03" in (
        context.primary_unavailable_reason
    )


def test_monthly_weights_are_lagged_by_exactly_one_calendar_month() -> None:
    lagged = backtest_node._lagged_official_benchmark_weights(
        {"2023-12": [0.9, 0.1], "2024-01": [0.8, 0.2]},
        ["2024-01-02", "2024-01-31", "2024-02-01"],
    )

    assert lagged == {"2024-01": (0.9, 0.1), "2024-02": (0.8, 0.2)}


def test_previous_month_crosses_the_year_boundary() -> None:
    assert backtest_node._previous_month("2024-01") == "2023-12"
    assert backtest_node._previous_month("2024-11") == "2024-10"


def test_no_supplied_series_keeps_the_documented_unavailable_reason() -> None:
    sessions = _sessions()

    context = backtest_node._build_benchmark_context(_price_rows(sessions))

    assert context.primary_available is False
    assert context.primary_coverage is None
    assert context.primary_unavailable_reason == (
        backtest_node.PRIMARY_BENCHMARK_MISSING_INPUT_REASON
    )


def test_warehouse_reason_is_carried_through_instead_of_a_generic_message() -> None:
    context = backtest_node._build_benchmark_context(
        _price_rows(_sessions()),
        {
            "available": False,
            "unavailable_reason": f"{OFFICIAL_BENCHMARK_TR_VIEW} could not be read (UndefinedTable)",
        },
    )

    assert context.primary_available is False
    assert OFFICIAL_BENCHMARK_TR_VIEW in context.primary_unavailable_reason


def _automatic_metrics(total_return: float) -> BacktestMetrics:
    return BacktestMetrics(
        sharpe_ratio=0.9,
        max_drawdown=-0.25,
        win_rate=0.55,
        total_return=total_return,
        in_sample_sharpe=0.8,
        out_sample_sharpe=0.7,
        degradation=0.1,
        in_sample_return=0.30,
        out_sample_return=0.23,
        in_sample_benchmark_return=0.20,
        out_sample_benchmark_return=0.10,
        in_sample_excess_return=0.10,
        out_sample_excess_return=0.13,
        benchmark_period_count=8,
        benchmark_period_win_rate=0.50,
        benchmark_period_loss_rate=0.375,
        in_sample_benchmark_period_count=5,
        in_sample_benchmark_period_win_rate=0.60,
        in_sample_benchmark_period_loss_rate=0.40,
        out_sample_benchmark_period_count=3,
        out_sample_benchmark_period_win_rate=2 / 3,
        out_sample_benchmark_period_loss_rate=1 / 3,
    )


def _automatic_result(context, total_return: float) -> SimpleNamespace:
    return SimpleNamespace(
        strategy_a=SimpleNamespace(selection_mode="automatic"),
        selected_candidate=SimpleNamespace(
            candidate_id="official-benchmark", metrics=_automatic_metrics(total_return)
        ),
        engine_summary={"effective_trade_count": 20},
        backtest_payload={"benchmark": backtest_node._benchmark_provenance(context)},
    )


def test_automatic_gate_can_finally_pass_once_the_official_series_is_supplied() -> None:
    sessions = _sessions()
    rows = _price_rows(sessions)
    supplied = backtest_node._build_benchmark_context(rows, _official_benchmark(sessions))
    missing = backtest_node._build_benchmark_context(rows)

    # Same metrics either way: what changes is only whether the primary benchmark exists.
    assert backtest_node._passes_objective_floor(_automatic_result(supplied, 0.60)) is True
    assert backtest_node._passes_objective_floor(_automatic_result(missing, 0.60)) is False


def test_automatic_gate_still_fails_a_strategy_that_loses_to_the_official_benchmark() -> None:
    sessions = _sessions()
    context = backtest_node._build_benchmark_context(
        _price_rows(sessions), _official_benchmark(sessions)
    )
    losing = _expected_total_return(sessions) - 0.01

    assert backtest_node._passes_objective_floor(_automatic_result(context, losing)) is False


class _BenchmarkConnection:
    """Answers only the two benchmark statements; everything else returns nothing."""

    def __init__(self, *, level_rows=None, weight_rows=None, missing_views=()):
        self.level_rows = level_rows if level_rows is not None else []
        self.weight_rows = weight_rows if weight_rows is not None else []
        self.missing_views = tuple(missing_views)
        self.aborted = False
        self.rollbacks = 0
        self.statements: list[str] = []

    def rollback(self):
        self.rollbacks += 1
        self.aborted = False

    def execute(self, query, params=None):
        self.statements.append(query)
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        if "set_config('statement_timeout'" in query:
            return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: None)
        for view in self.missing_views:
            if view in query:
                self.aborted = True
                raise RuntimeError(f'relation "{view}" does not exist')
        if OFFICIAL_BENCHMARK_TR_VIEW in query:
            return SimpleNamespace(fetchall=lambda: self.level_rows, fetchone=lambda: None)
        if OFFICIAL_BENCHMARK_WEIGHT_VIEW in query:
            return SimpleNamespace(fetchall=lambda: self.weight_rows, fetchone=lambda: None)
        return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: None)


def _source() -> PostgresPipelineDataSource:
    return PostgresPipelineDataSource(DataSourceConfig(database_dsn="postgresql://example"))


def _level_rows() -> list[dict[str, object]]:
    return [
        {"index_code": "KOSPI_TR", "trade_date": date(2024, 1, 2), "tr_value": Decimal("100")},
        {"index_code": "KOSDAQ_TR", "trade_date": date(2024, 1, 2), "tr_value": Decimal("250")},
        {"index_code": "KOSPI_TR", "trade_date": date(2024, 1, 3), "tr_value": Decimal("101")},
        {"index_code": "KOSDAQ_TR", "trade_date": date(2024, 1, 3), "tr_value": Decimal("249")},
    ]


def test_absent_benchmark_tables_are_unavailable_with_a_reason_not_an_exception() -> None:
    connection = _BenchmarkConnection(missing_views=(OFFICIAL_BENCHMARK_TR_VIEW,))

    descriptor = _source()._fetch_official_benchmark(connection, WINDOW)

    assert descriptor["available"] is False
    assert OFFICIAL_BENCHMARK_TR_VIEW in descriptor["unavailable_reason"]
    assert "does not exist" in descriptor["unavailable_reason"]
    # A failed statement aborts the transaction and drops the transaction-local timeout.
    assert connection.rollbacks == 1
    assert "set_config('statement_timeout'" in connection.statements[-1]


def test_absent_weight_table_is_reported_against_its_own_view() -> None:
    connection = _BenchmarkConnection(
        level_rows=_level_rows(), missing_views=(OFFICIAL_BENCHMARK_WEIGHT_VIEW,)
    )

    descriptor = _source()._fetch_official_benchmark(connection, WINDOW)

    assert descriptor["available"] is False
    assert OFFICIAL_BENCHMARK_WEIGHT_VIEW in descriptor["unavailable_reason"]
    assert connection.rollbacks == 1


def test_empty_tr_table_names_both_index_codes_and_the_window() -> None:
    connection = _BenchmarkConnection(level_rows=[])

    descriptor = _source()._fetch_official_benchmark(connection, WINDOW)

    assert descriptor["available"] is False
    assert "KOSPI_TR" in descriptor["unavailable_reason"]
    assert "KOSDAQ_TR" in descriptor["unavailable_reason"]
    assert "2024-01-01" in descriptor["unavailable_reason"]
    assert connection.rollbacks == 0


def test_one_index_without_rows_is_not_treated_as_a_covered_benchmark() -> None:
    connection = _BenchmarkConnection(
        level_rows=[row for row in _level_rows() if row["index_code"] == "KOSPI_TR"],
        weight_rows=[{
            "month": date(2023, 12, 1),
            "kospi_weight": Decimal("0.8"),
            "kosdaq_weight": Decimal("0.2"),
        }],
    )

    descriptor = _source()._fetch_official_benchmark(connection, WINDOW)

    assert descriptor["available"] is False
    assert "KOSDAQ_TR" in descriptor["unavailable_reason"]
    assert "KOSPI_TR" not in descriptor["unavailable_reason"]


def test_loaded_tables_produce_iso_keyed_series_and_unlagged_month_keys() -> None:
    connection = _BenchmarkConnection(
        level_rows=_level_rows(),
        weight_rows=[
            {
                "month": date(2023, 12, 1),
                "kospi_weight": Decimal("0.81"),
                "kosdaq_weight": Decimal("0.19"),
            },
            {
                "month": date(2024, 1, 1),
                "kospi_weight": Decimal("0.80"),
                "kosdaq_weight": Decimal("0.20"),
            },
        ],
    )

    descriptor = _source()._fetch_official_benchmark(connection, WINDOW)

    assert descriptor["available"] is True
    assert descriptor["unavailable_reason"] is None
    assert descriptor["kospi_tr"] == {"2024-01-02": 100.0, "2024-01-03": 101.0}
    assert descriptor["kosdaq_tr"] == {"2024-01-02": 250.0, "2024-01-03": 249.0}
    assert descriptor["monthly_weights"] == {"2023-12": [0.81, 0.19], "2024-01": [0.80, 0.20]}
    assert descriptor["weight_lag_months"] == 1
    weight_statement = next(
        statement
        for statement in connection.statements
        if OFFICIAL_BENCHMARK_WEIGHT_VIEW in statement
    )
    # The first traded month rebalances on the month before the window opens.
    assert "INTERVAL '1 month'" in weight_statement


def test_non_positive_or_unparseable_levels_are_dropped_not_carried() -> None:
    connection = _BenchmarkConnection(
        level_rows=[
            *_level_rows(),
            {"index_code": "KOSPI_TR", "trade_date": date(2024, 1, 4), "tr_value": Decimal("0")},
            {"index_code": "KOSDAQ_TR", "trade_date": date(2024, 1, 4), "tr_value": None},
        ],
        weight_rows=[{
            "month": date(2023, 12, 1),
            "kospi_weight": Decimal("0.8"),
            "kosdaq_weight": Decimal("0.2"),
        }],
    )

    descriptor = _source()._fetch_official_benchmark(connection, WINDOW)

    assert "2024-01-04" not in descriptor["kospi_tr"]
    assert "2024-01-04" not in descriptor["kosdaq_tr"]


def test_metadata_summary_reports_shape_without_republishing_the_series() -> None:
    descriptor = _official_benchmark(_sessions())

    summary = _official_benchmark_status(descriptor)

    assert summary["available"] is True
    assert summary["kospi_tr_sessions"] == 120
    assert summary["kosdaq_tr_sessions"] == 120
    assert summary["monthly_weight_months"] == 7
    assert "kospi_tr" not in summary
    assert summary["level_source"] == OFFICIAL_BENCHMARK_TR_VIEW


def _session_strategy() -> StrategySpec:
    return StrategySpec(
        strategy_id="benchmark-session",
        name="Benchmark session",
        market="KRX",
        timeframe="daily",
        entry_conditions=[Condition(left="rsi", operator=ConditionOperator.LTE, right=40.0)],
        exit_conditions=[Condition(left="rsi", operator=ConditionOperator.GTE, right=70.0)],
        indicators=["rsi"],
        risk_constraints={"max_position_pct": 0.2},
        confidence=0.9,
    )


def _session_rows() -> list[dict[str, object]]:
    return [
        {
            "date": session,
            "ticker": f"{ticker_index:06d}",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0 + ticker_index,
            "volume": 1_000_000.0,
            "rsi": 45.0,
        }
        for session in _sessions()[:20]
        for ticker_index in range(1, 4)
    ]


def test_disk_cache_key_separates_runs_with_and_without_the_official_benchmark() -> None:
    """A cached engine summary carries the provenance it was computed with.

    Without this the first run's "primary benchmark unavailable" summary would be
    replayed for hours after the series was loaded.
    """

    strategy = _session_strategy()
    rows = _session_rows()
    candidate = CodeCandidate(
        candidate_id="cache-key", variant="A",
        code="def build_signals(prices):\n    return []\n", validation_ok=True,
    )
    sessions = sorted({str(row["date"]) for row in rows})

    with backtest_node._CandidateBacktestSession(strategy, rows) as without:
        without_key = without._disk_cache_key(candidate, "selection")
        repeated_key = without._disk_cache_key(candidate, "selection")
    with backtest_node._CandidateBacktestSession(
        strategy, rows, official_benchmark=_official_benchmark(sessions)
    ) as supplied:
        assert supplied.benchmark_context.primary_available is True
        supplied_key = supplied._disk_cache_key(candidate, "selection")

    # Same inputs still key identically, so an ordinary re-run keeps hitting the cache.
    assert without_key == repeated_key
    assert supplied_key != without_key


def test_migration_defines_the_views_and_columns_the_reader_selects() -> None:
    sql = (
        Path(__file__).parents[2] / "DE/migrations/013_krx_official_benchmark_tr.sql"
    ).read_text(encoding="utf-8")

    assert f"CREATE OR REPLACE VIEW {OFFICIAL_BENCHMARK_TR_VIEW} AS" in sql
    assert f"CREATE OR REPLACE VIEW {OFFICIAL_BENCHMARK_WEIGHT_VIEW} AS" in sql
    for column in ("index_code", "trade_date", "tr_value"):
        assert column in sql.split(f"CREATE OR REPLACE VIEW {OFFICIAL_BENCHMARK_TR_VIEW} AS")[1]
    weights_block = sql.split(f"CREATE OR REPLACE VIEW {OFFICIAL_BENCHMARK_WEIGHT_VIEW} AS")[1]
    for column in ("month", "kospi_weight", "kosdaq_weight"):
        assert column in weights_block
    # Weights are stored unlagged; the reader applies the one-month lag.
    assert "index_benchmark_weight_monthly_month_is_first_day" in sql
    assert "index_total_return_daily_value_positive" in sql
