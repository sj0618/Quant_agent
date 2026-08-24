"""The look-ahead harness must find a leak, and must not claim more than it checked."""

from array import array

import pytest

from ai_graph.lookahead import (
    LookaheadFinding,
    compare_runs,
    lookahead_evidence,
)
from ai_graph.schemas import CandidateParameters, Condition, StrategyIR


def _rows(count: int = 60) -> list[dict]:
    rows: list[dict] = []
    price = 1000.0
    for index in range(count):
        price *= 1.01 if index % 3 else 0.985
        rows.append(
            {
                "date": f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}",
                "ticker": "000660",
                "open": price,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": 1_000_000.0,
                "rsi": 25.0 if index % 5 == 0 else 60.0,
                "sma20": price * 0.98,
                "sma50": price * 0.97,
                "sma200": price * 0.95,
            }
        )
    return rows


def _strategy() -> StrategyIR:
    return StrategyIR(
        strategy_id="lookahead-probe",
        entry_feature="close",
        exit_feature="close",
        proxy_feature="close",
        entry_conditions=[Condition(left="rsi", operator="lte", right=30)],
        exit_conditions=[Condition(left="rsi", operator="gte", right=55)],
    )


def _parameters() -> CandidateParameters:
    return CandidateParameters(
        profile="compiled_conditions",
        lookback=20,
        threshold=0.1,
        stop_loss_pct=0.08,
        take_profit_pct=0.2,
        max_positions=5,
    )


def test_compare_runs_names_the_row_where_the_two_runs_disagree() -> None:
    """The detector itself, on fabricated arrays, so a clean report means something."""

    findings = compare_runs(
        array("b", [0, 1, 0, -1]),
        array("b", [0, 0, 0]),
        ("2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"),
        ("000660", "000660", "000660", "000660"),
    )

    assert findings == (
        LookaheadFinding(
            date="2026-01-02",
            ticker="000660",
            baseline_action="buy",
            truncated_action="hold",
        ),
    )
    # The row past the cutoff is outside the covered window and is not a finding.
    assert all(finding.date != "2026-01-04" for finding in findings)


def test_compare_runs_refuses_a_truncation_longer_than_the_baseline() -> None:
    with pytest.raises(ValueError):
        compare_runs(array("b", [0]), array("b", [0, 0]), ("d",), ("t",))


def test_lookahead_evidence_reports_coverage_and_named_limitations() -> None:
    """A clean result is a coverage statement, not a claim of no bias."""

    rows = _rows()
    evidence = lookahead_evidence(
        rows, _strategy(), _parameters(), cutoff_date="2026-01-20"
    )

    assert evidence.cutoff_date == "2026-01-20"
    assert evidence.baseline_rows == len(rows)
    assert 0 < evidence.covered_rows < evidence.baseline_rows
    assert evidence.covered_rows == evidence.truncated_rows
    assert evidence.covered_signals + evidence.silent_rows == evidence.covered_rows
    # The four required limitations are always present, including on a clean run, so a
    # reader never sees "0 findings" without what the run could not reach.
    assert len(evidence.limitations) == 4
    assert any("발화하지 않은" in item for item in evidence.limitations)
    assert any("QV-WRM-01" in item for item in evidence.limitations)

    exported = evidence.as_dict()
    assert exported["differing_rows"] == len(evidence.findings)
    assert exported["limitations"] == list(evidence.limitations)


def test_lookahead_evidence_rejects_a_cutoff_before_the_first_bar() -> None:
    with pytest.raises(ValueError):
        lookahead_evidence(_rows(), _strategy(), _parameters(), cutoff_date="2020-01-01")
