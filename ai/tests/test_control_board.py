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


def test_sample_blocker_has_every_required_column_and_matching_aggregates() -> None:
    result = validate_control_board(_board_text())

    assert result.valid, result.errors
    assert result.summary.as_dict() == {
        "state_transition_count": 1,
        "state_transition_evidence_uri_count": 1,
        "blocker_count": 1,
        "blocker_evidence_uri_count": 2,
        "blocker_recurrence_total": 2,
        "recurring_blocker_count": 1,
        "max_blocker_recurrence_count": 2,
    }


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
    board = _board_text().replace(
        "| blocker_recurrence_total | 2 |",
        "| blocker_recurrence_total | 3 |",
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
    assert payload["summary"]["blocker_recurrence_total"] == 2
