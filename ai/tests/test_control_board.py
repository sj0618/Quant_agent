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
    board = _board_text().replace(
        "repo:scripts/check-production-plan.mjs@f02672878f10ee038133b917a18d333e061187bc",
        "",
        1,
    )

    result = validate_control_board(board)

    assert not result.valid
    assert any("evidence_uri" in error for error in result.errors)


def test_negative_recurrence_count_is_rejected() -> None:
    board = _board_text().replace(
        '"recurrenceCount": 1',
        '"recurrenceCount": -1',
        1,
    )

    result = validate_control_board(board)

    assert not result.valid
    assert any("recurrence_count" in error for error in result.errors)


def test_invalid_machine_marker_is_rejected() -> None:
    board = _board_text().replace('"schemaVersion": "quantagent-control-board.v1"', '"schemaVersion": "invalid"')

    result = validate_control_board(board)

    assert not result.valid
    assert any("schemaVersion" in error for error in result.errors)


def test_projection_sha_mismatch_is_rejected() -> None:
    board = _board_text().replace("`f026728`", "`abcdef0`", 1)

    result = validate_control_board(board)

    assert not result.valid
    assert any("Git SHA" in error for error in result.errors)


def test_blocker_projection_reviewer_and_evidence_must_match_marker() -> None:
    reviewer_tampered = _board_text().replace(
        "| 1 | Codex local verifier (not independent approval) |",
        "| 1 | wrong reviewer |",
        1,
    )
    evidence_tampered = _board_text().replace(
        "`repo:docs/plans/quantagent-production-qa-local-evidence-contract-20260824.md@"
        "f02672878f10ee038133b917a18d333e061187bc`",
        "`repo:wrong-evidence@f02672878f10ee038133b917a18d333e061187bc`",
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
