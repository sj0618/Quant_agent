"""Does a bar that had not happened yet change a decision the strategy already made?

A backtest can only be trusted if the decision it records for a given day was reachable
with the information available on that day. The cheap way to find out is differential:
run the rule over the whole history, run it again over a history truncated at some date,
and compare the decisions on the days both runs share. A rule that reads only the past
produces identical decisions on those days. A rule that peeks produces different ones,
because the second run does not have the future the first one saw.

Truncation happens at the *end* on purpose. Cutting the start would shorten every
indicator's window at the beginning of the shorter run and report legitimate differences
as leakage; cutting the end leaves the shared prefix's history untouched.

What this cannot see is a branch that never ran. A condition that no bar satisfied
contributes no decision to compare, so silence here is not the same as absence of bias -
which is why `LookaheadEvidence` reports how many rows actually produced a signal and
refuses to summarize itself as "unbiased".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai_graph.nodes.backtest_features import PreparedFeatureStore
from ai_graph.schemas import CandidateParameters, StrategyIR

HOLD = 0
BUY = 1
SELL = -1

_ACTION_NAMES = {HOLD: "hold", BUY: "buy", SELL: "sell"}


@dataclass(frozen=True)
class LookaheadFinding:
    """One day/ticker where the truncated run disagreed with the full run."""

    date: str
    ticker: str
    baseline_action: str
    truncated_action: str


@dataclass(frozen=True)
class LookaheadEvidence:
    """What one truncation compared, what it found, and what it could not reach."""

    cutoff_date: str
    baseline_rows: int
    truncated_rows: int
    covered_rows: int
    covered_dates: int
    covered_signals: int
    silent_rows: int
    findings: tuple[LookaheadFinding, ...]
    limitations: tuple[str, ...]

    @property
    def differing_rows(self) -> int:
        return len(self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cutoff_date": self.cutoff_date,
            "baseline_rows": self.baseline_rows,
            "truncated_rows": self.truncated_rows,
            "covered_rows": self.covered_rows,
            "covered_dates": self.covered_dates,
            "covered_signals": self.covered_signals,
            "silent_rows": self.silent_rows,
            "differing_rows": self.differing_rows,
            "findings": [
                {
                    "date": finding.date,
                    "ticker": finding.ticker,
                    "baseline_action": finding.baseline_action,
                    "truncated_action": finding.truncated_action,
                }
                for finding in self.findings
            ],
            "limitations": list(self.limitations),
        }


def compare_runs(
    baseline_actions: Sequence[int],
    truncated_actions: Sequence[int],
    dates: Sequence[str],
    tickers: Sequence[str],
) -> tuple[LookaheadFinding, ...]:
    """Rows where the two runs disagree, over the prefix they both cover.

    The truncated store holds the first ``len(truncated_actions)`` rows of the same
    (date, ticker) ordering, so position ``i`` names the same row in both runs.
    """

    covered = len(truncated_actions)
    if covered > len(baseline_actions):
        raise ValueError("truncated run cannot cover more rows than the baseline")
    return tuple(
        LookaheadFinding(
            date=dates[index],
            ticker=tickers[index],
            baseline_action=_ACTION_NAMES.get(int(baseline_actions[index]), "unknown"),
            truncated_action=_ACTION_NAMES.get(int(truncated_actions[index]), "unknown"),
        )
        for index in range(covered)
        if int(baseline_actions[index]) != int(truncated_actions[index])
    )


def lookahead_evidence(
    rows: Sequence[Mapping[str, Any]],
    strategy_ir: StrategyIR,
    parameters: CandidateParameters,
    *,
    cutoff_date: str,
) -> LookaheadEvidence:
    """Run the rule twice - full history and history truncated at ``cutoff_date``."""

    baseline_store = PreparedFeatureStore(rows)
    baseline_actions = baseline_store.build_actions(strategy_ir, parameters)

    kept = [row for row in baseline_store.rows if str(row.get("date") or "") <= cutoff_date]
    if not kept:
        raise ValueError(f"no rows on or before cutoff_date={cutoff_date!r}")
    truncated_store = PreparedFeatureStore(kept, rows_are_sorted=True)
    truncated_actions = truncated_store.build_actions(strategy_ir, parameters)

    covered = len(kept)
    covered_signals = sum(1 for index in range(covered) if int(baseline_actions[index]) != HOLD)
    findings = compare_runs(
        baseline_actions,
        truncated_actions,
        baseline_store.dates,
        baseline_store.tickers,
    )
    return LookaheadEvidence(
        cutoff_date=cutoff_date,
        baseline_rows=len(baseline_store.rows),
        truncated_rows=covered,
        covered_rows=covered,
        covered_dates=len(set(baseline_store.dates[:covered])),
        covered_signals=covered_signals,
        silent_rows=covered - covered_signals,
        findings=findings,
        limitations=_limitations(covered, covered_signals),
    )


def _limitations(covered_rows: int, covered_signals: int) -> tuple[str, ...]:
    """State what this run did not reach, as counts rather than reassurance."""

    silent = covered_rows - covered_signals
    return (
        (
            f"검사 대상 {covered_rows}행 중 {silent}행은 어떤 신호도 내지 않았다. "
            "발화하지 않은 분기는 비교할 결정이 없으므로 look-ahead 여부를 판정하지 않았다."
        ),
        (
            "이 검사는 구조화(compiled_conditions) 평가 경로만 실행한다. "
            "생성 코드(backtest_code) 경로는 별도 실행이 필요하다."
        ),
        (
            "warm-up 부족은 여기서 드러나지 않는다. 두 실행이 같은 시작점을 공유하므로 "
            "창 길이 미만 구간의 부분 윈도우 값은 양쪽에서 동일하게 나타난다. "
            "이는 look-ahead와 다른 편향이며 QV-WRM-01에서 따로 다룬다."
        ),
        (
            "절단 지점 1개는 슬라이스 1개다. 다른 날짜에서만 드러나는 누출은 "
            "그 날짜로 다시 실행해야 관측된다."
        ),
    )
