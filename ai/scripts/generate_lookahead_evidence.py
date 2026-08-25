#!/usr/bin/env python
"""Emit the QV-BIAS-01 look-ahead artifact as JSON on stdout.

The input is a declared deterministic series, not market data: the repo's only price
fixture is four rows with no ticker, which cannot carry a rolling window. That makes the
output an S-tier contract artifact - it shows the harness ran and what it covered, and it
is not a statement about production data. A release-grade run has to read the same
PostgreSQL EOD extract the engine reads, on the server.

Usage:
    ai/.venv/bin/python ai/scripts/generate_lookahead_evidence.py [--cutoff YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_graph.lookahead import lookahead_evidence
from ai_graph.schemas import CandidateParameters, Condition, StrategyIR

SERIES = "deterministic_synthetic.v1: close *= 1.01 on two of every three sessions, *= 0.985 otherwise; rsi = 25 every fifth session else 60"
TICKERS = ("000660", "005930", "035420")
SESSIONS = 90


def _rows() -> list[dict]:
    rows: list[dict] = []
    for offset, ticker in enumerate(TICKERS):
        price = 1000.0 + 100.0 * offset
        for index in range(SESSIONS):
            price *= 1.01 if index % 3 else 0.985
            rows.append(
                {
                    "date": f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}",
                    "ticker": ticker,
                    "open": price,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "volume": 1_000_000.0,
                    "rsi": 25.0 if (index + offset) % 5 == 0 else 60.0,
                    "sma20": price * 0.98,
                    "sma50": price * 0.97,
                    "sma200": price * 0.95,
                }
            )
    return rows


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", default="2026-02-15")
    cutoff = parser.parse_args().cutoff

    strategy = StrategyIR(
        strategy_id="qv-bias-01-probe",
        entry_feature="close",
        exit_feature="close",
        proxy_feature="close",
        entry_conditions=[Condition(left="rsi", operator="lte", right=30)],
        exit_conditions=[Condition(left="rsi", operator="gte", right=55)],
    )
    parameters = CandidateParameters(
        profile="compiled_conditions",
        lookback=20,
        threshold=0.1,
        stop_loss_pct=0.08,
        take_profit_pct=0.2,
        max_positions=5,
    )
    evidence = lookahead_evidence(_rows(), strategy, parameters, cutoff_date=cutoff)

    json.dump(
        {
            "wbs_id": "QV-BIAS-01",
            "method": "end_truncation_differential",
            "generated_at": datetime.now(UTC).isoformat(),
            "git_sha": _git("rev-parse", "HEAD"),
            "input": {
                "grade": "fixture",
                "release_eligible": False,
                "series": SERIES,
                "tickers": list(TICKERS),
                "sessions_per_ticker": SESSIONS,
            },
            "evaluated_rule": {
                "path": "compiled_conditions",
                "entry": "rsi <= 30",
                "exit": "rsi >= 55",
            },
            "result": evidence.as_dict(),
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
