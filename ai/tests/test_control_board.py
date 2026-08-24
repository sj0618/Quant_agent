from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ai_graph.control_board import validate_control_board

REPOSITORY_ROOT = Path(__file__).parents[2]
AI_ROOT = REPOSITORY_ROOT / "ai"
BOARD_PATH = REPOSITORY_ROOT / "docs/plans/quantagent-production-control-board.md"


def _board_text() -> str:
    return BOARD_PATH.read_text(encoding="utf-8")


def test_board_is_valid_and_every_row_carries_its_required_evidence() -> None:
    """The board is a live ledger, so assert invariants rather than today's counts.

    These used to be frozen literals, which meant recording a real blocker - the one
    thing the ledger exists for - failed the suite.
    """

    result = validate_control_board(_board_text())

    assert result.valid, result.errors
    summary = result.summary.as_dict()
    assert set(summary) == {
        "state_transition_count",
        "state_transition_evidence_uri_count",
        "blocker_count",
        "blocker_evidence_uri_count",
        "blocker_recurrence_total",
        "recurring_blocker_count",
        "max_blocker_recurrence_count",
    }
    assert summary["state_transition_count"] >= 1
    assert summary["blocker_count"] >= 1
    # Every transition carries an evidence URI, and every blocker carries both a
    # discovery and a current-state/resolution URI.
    assert summary["state_transition_evidence_uri_count"] == summary["state_transition_count"]
    assert summary["blocker_evidence_uri_count"] == summary["blocker_count"] * 2
    assert summary["recurring_blocker_count"] <= summary["blocker_count"]
    assert summary["max_blocker_recurrence_count"] <= summary["blocker_recurrence_total"]


def test_missing_blocker_column_is_rejected() -> None:
    board = _board_text().replace(" | owner |", " |", 1)

    result = validate_control_board(board)

    assert not result.valid
    assert any("owner" in error for error in result.errors)


def test_empty_transition_evidence_uri_is_rejected() -> None:
    board = _board_text().replace(
        "| evidence://PM-BOARD-01-transition-001 |",
        "|  |",
        1,
    )

    result = validate_control_board(board)

    assert not result.valid
    assert any("evidence_uri" in error for error in result.errors)


def test_negative_recurrence_count_is_rejected() -> None:
    board = _board_text().replace(
        "| schedule-evidence-manager | 2 |",
        "| schedule-evidence-manager | -1 |",
        1,
    )

    result = validate_control_board(board)

    assert not result.valid
    assert any("recurrence_count" in error for error in result.errors)


def test_visible_aggregate_mismatch_is_rejected() -> None:
    board = _board_text()
    published = validate_control_board(board).summary.blocker_recurrence_total
    board = board.replace(
        f"| blocker_recurrence_total | {published} |",
        f"| blocker_recurrence_total | {published + 1} |",
        1,
    )

    result = validate_control_board(board)

    assert not result.valid
    assert any("blocker_recurrence_total" in error for error in result.errors)


def test_cli_returns_machine_readable_pass_result() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_control_board.py",
            "--board",
            str(BOARD_PATH),
        ],
        cwd=AI_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["valid"] is True
    assert payload["summary"] == validate_control_board(_board_text()).summary.as_dict()
