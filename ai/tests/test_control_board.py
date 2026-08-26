from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from ai_graph.control_board import validate_control_board

REPOSITORY_ROOT = Path(__file__).parents[2]
AI_ROOT = REPOSITORY_ROOT / "ai"
BOARD_PATH = REPOSITORY_ROOT / "docs/plans/quantagent-production-control-board.md"


def _board_text() -> str:
    return BOARD_PATH.read_text(encoding="utf-8")


def _marker() -> dict:
    """Read the board's own JSON marker.

    Mutation fixtures below derive their targets from this rather than quoting one
    revision's bytes. A literal pinned to a past board silently stops matching when the
    board is legitimately updated, and a no-op replace makes a "must be rejected" test
    pass its input unchanged - so the assertion inverts and the suite fails on a valid
    board instead of catching an invalid one.
    """

    match = re.search(r"<!--\s*control-board:v1\s*(\{.*?\})\s*-->", _board_text(), re.DOTALL)
    assert match is not None, "board is missing its control-board:v1 marker"
    return json.loads(match.group(1))

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
    assert summary["state_transition_evidence_uri_count"] >= summary["state_transition_count"]
    assert summary["blocker_evidence_uri_count"] >= summary["blocker_count"] * 2
    assert summary["recurring_blocker_count"] <= summary["blocker_count"]
    assert summary["max_blocker_recurrence_count"] <= summary["blocker_recurrence_total"]


def test_missing_blocker_column_is_rejected() -> None:
    board = _board_text().replace('"owner": "윤서준"', '"actor": "윤서준"', 1)

    result = validate_control_board(board)

    assert not result.valid
    assert any("owner" in error for error in result.errors)


def test_empty_transition_evidence_uri_is_rejected() -> None:
    board = _board_text().replace(_marker()["transitions"][0]["evidence"][0], "", 1)

    result = validate_control_board(board)

    assert not result.valid
    assert any("evidence_uri" in error for error in result.errors)


def test_negative_recurrence_count_is_rejected() -> None:
    board = re.sub(r'"recurrenceCount": \d+', '"recurrenceCount": -1', _board_text(), count=1)

    result = validate_control_board(board)

    assert not result.valid
    assert any("recurrence_count" in error for error in result.errors)


def test_invalid_machine_marker_is_rejected() -> None:
    board = _board_text().replace('"schemaVersion": "quantagent-control-board.v1"', '"schemaVersion": "invalid"')

    result = validate_control_board(board)

    assert not result.valid
    assert any("schemaVersion" in error for error in result.errors)


def test_projection_sha_mismatch_is_rejected() -> None:
    short_sha = _marker()["snapshot"]["gitSha"][:7]
    board = _board_text().replace(f"`{short_sha}`", "`abcdef0`", 1)

    result = validate_control_board(board)

    assert not result.valid
    assert any("Git SHA" in error for error in result.errors)


def test_blocker_projection_reviewer_and_evidence_must_match_marker() -> None:
    marker = _marker()
    blocker = marker["blockers"][0]
    reviewer_tampered = _board_text().replace(
        f"| {blocker['lastReviewer']} |", "| wrong reviewer |", 1
    )
    evidence_tampered = _board_text().replace(
        f"`{blocker['evidence'][0]}`",
        f"`repo:wrong-evidence@{marker['snapshot']['gitSha']}`",
        1,
    )

    reviewer_result = validate_control_board(reviewer_tampered)
    evidence_result = validate_control_board(evidence_tampered)

    assert not reviewer_result.valid
    assert any("reviewer" in error for error in reviewer_result.errors)
    assert not evidence_result.valid
    assert any("evidence_uri" in error for error in evidence_result.errors)


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
