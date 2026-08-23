from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ai_graph.on_demand_retirement import validate_on_demand_retirement_inventory

REPOSITORY_ROOT = Path(__file__).parents[2]
AI_ROOT = REPOSITORY_ROOT / "ai"
INVENTORY_PATH = REPOSITORY_ROOT / "docs/plans/quantagent-on-demand-retirement-inventory.md"


def _inventory_text() -> str:
    return INVENTORY_PATH.read_text(encoding="utf-8")


def test_all_ten_inventory_items_have_one_explicit_decision() -> None:
    result = validate_on_demand_retirement_inventory(_inventory_text())

    assert result.valid, result.errors
    assert result.summary.as_dict() == {
        "item_count": 10,
        "decision_counts": {"제거": 4, "보관": 2, "대체": 4},
    }


def test_non_contract_decision_is_rejected() -> None:
    inventory = "\n".join(
        line.replace("| 대체 |", "| 유지 |", 1) if "| OD-01 |" in line else line
        for line in _inventory_text().splitlines()
    )

    result = validate_on_demand_retirement_inventory(inventory)

    assert not result.valid
    assert any("제거, 보관, 대체" in error for error in result.errors)


def test_missing_inventory_item_is_rejected() -> None:
    inventory = "\n".join(line for line in _inventory_text().splitlines() if "| OD-10 |" not in line)

    result = validate_on_demand_retirement_inventory(inventory)

    assert not result.valid
    assert any("OD-10" in error for error in result.errors)


def test_duplicate_inventory_item_is_rejected() -> None:
    inventory = _inventory_text().replace("| OD-10 |", "| OD-09 |", 1)

    result = validate_on_demand_retirement_inventory(inventory)

    assert not result.valid
    assert any("duplicate OD IDs" in error for error in result.errors)


def test_cli_returns_machine_readable_pass_result() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_on_demand_retirement_inventory.py",
            "--inventory",
            str(INVENTORY_PATH),
        ],
        cwd=AI_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["valid"] is True
    assert payload["summary"]["item_count"] == 10
