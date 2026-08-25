"""Validate the ten-item on-demand analysis retirement inventory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RETIREMENT_ITEMS_HEADING = "결정 항목"
RETIREMENT_SUMMARY_HEADING = "결정 집계"
RETIREMENT_DECISIONS: tuple[str, ...] = ("제거", "보관", "대체")
RETIREMENT_ITEM_IDS: tuple[str, ...] = tuple(f"OD-{number:02d}" for number in range(1, 11))
RETIREMENT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "OD ID",
    "현재 경로·근거",
    "현재 공개 범위",
    "결정",
    "결정 근거",
    "대체 사용자 행동",
    "회귀 검사",
)
RETIREMENT_SUMMARY_COLUMNS: tuple[str, ...] = ("결정", "항목 수")


@dataclass(frozen=True)
class RetirementInventorySummary:
    """Visible counts for the inventory decision contract."""

    item_count: int
    decision_counts: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_count": self.item_count,
            "decision_counts": dict(self.decision_counts),
        }


@dataclass(frozen=True)
class RetirementInventoryValidation:
    valid: bool
    errors: tuple[str, ...]
    summary: RetirementInventorySummary

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "summary": self.summary.as_dict(),
        }


@dataclass(frozen=True)
class _MarkdownTable:
    headers: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


def _split_row(line: str) -> list[str]:
    content = line.strip()
    if not content.startswith("|"):
        return []
    return [cell.strip() for cell in content.strip("|").split("|")]


def _is_separator(line: str) -> bool:
    cells = _split_row(line)
    return bool(cells) and all(cell and set(cell) <= {"-", ":"} for cell in cells)


def _table_after_heading(markdown: str, heading: str) -> _MarkdownTable | None:
    lines = markdown.splitlines()
    target = f"## {heading}".casefold()
    heading_index = next(
        (index for index, line in enumerate(lines) if line.strip().casefold() == target),
        None,
    )
    if heading_index is None:
        return None

    table_start = None
    for index in range(heading_index + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("|"):
            table_start = index
            break
    if table_start is None:
        return None

    headers = tuple(_split_row(lines[table_start]))
    row_start = table_start + 1
    if row_start < len(lines) and _is_separator(lines[row_start]):
        row_start += 1

    rows: list[dict[str, str]] = []
    for line in lines[row_start:]:
        if not line.strip().startswith("|"):
            break
        values = _split_row(line)
        if len(values) != len(headers):
            rows.append({header: "" for header in headers})
            continue
        rows.append(dict(zip(headers, values, strict=True)))
    return _MarkdownTable(headers=headers, rows=tuple(rows))


def _parse_count(value: str, label: str, errors: list[str]) -> int:
    try:
        parsed = int(value)
    except ValueError:
        errors.append(f"{label} must be an integer.")
        return 0
    if parsed < 0:
        errors.append(f"{label} must be non-negative.")
        return 0
    return parsed


def _empty_summary() -> RetirementInventorySummary:
    return RetirementInventorySummary(
        item_count=0,
        decision_counts=tuple((decision, 0) for decision in RETIREMENT_DECISIONS),
    )


def _validate_item_table(
    table: _MarkdownTable | None,
    errors: list[str],
) -> RetirementInventorySummary:
    if table is None:
        errors.append("retirement item table is missing.")
        return _empty_summary()

    missing_columns = [column for column in RETIREMENT_REQUIRED_COLUMNS if column not in table.headers]
    if missing_columns:
        errors.append(f"retirement item table is missing columns: {', '.join(missing_columns)}.")
        return _empty_summary()

    if len(table.rows) != len(RETIREMENT_ITEM_IDS):
        errors.append(
            f"retirement item table must contain exactly {len(RETIREMENT_ITEM_IDS)} rows; "
            f"found {len(table.rows)}."
        )

    expected_ids = set(RETIREMENT_ITEM_IDS)
    seen_ids: list[str] = []
    decision_counts = {decision: 0 for decision in RETIREMENT_DECISIONS}
    for row_number, row in enumerate(table.rows, start=1):
        for column in RETIREMENT_REQUIRED_COLUMNS:
            if not row.get(column, "").strip():
                errors.append(f"retirement item row {row_number} has an empty {column}.")

        item_id = row.get("OD ID", "").strip()
        if item_id:
            seen_ids.append(item_id)
            if item_id not in expected_ids:
                errors.append(f"retirement item row {row_number} has an unexpected OD ID: {item_id}.")

        decision = row.get("결정", "").strip()
        if decision not in RETIREMENT_DECISIONS:
            errors.append(
                f"retirement item row {row_number} must choose exactly one of: "
                f"{', '.join(RETIREMENT_DECISIONS)}."
            )
        else:
            decision_counts[decision] += 1

    duplicates = sorted({item_id for item_id in seen_ids if seen_ids.count(item_id) > 1})
    if duplicates:
        errors.append(f"retirement item table has duplicate OD IDs: {', '.join(duplicates)}.")

    missing_ids = sorted(expected_ids - set(seen_ids))
    if missing_ids:
        errors.append(f"retirement item table is missing OD IDs: {', '.join(missing_ids)}.")

    return RetirementInventorySummary(
        item_count=len(table.rows),
        decision_counts=tuple((decision, decision_counts[decision]) for decision in RETIREMENT_DECISIONS),
    )


def _validate_summary_table(
    table: _MarkdownTable | None,
    summary: RetirementInventorySummary,
    errors: list[str],
) -> None:
    if table is None:
        errors.append("retirement summary table is missing.")
        return

    missing_columns = [column for column in RETIREMENT_SUMMARY_COLUMNS if column not in table.headers]
    if missing_columns:
        errors.append(f"retirement summary table is missing columns: {', '.join(missing_columns)}.")
        return

    values: dict[str, int] = {}
    for row_number, row in enumerate(table.rows, start=1):
        decision = row.get("결정", "").strip()
        if not decision:
            errors.append(f"retirement summary row {row_number} has an empty 결정.")
            continue
        if decision in values:
            errors.append(f"retirement summary table has duplicate 결정: {decision}.")
        values[decision] = _parse_count(row.get("항목 수", ""), f"retirement summary row {row_number}", errors)

    expected_values = dict(summary.decision_counts)
    expected_values["합계"] = summary.item_count
    for decision, expected_count in expected_values.items():
        if decision not in values:
            errors.append(f"retirement summary table is missing 결정: {decision}.")
        elif values[decision] != expected_count:
            errors.append(
                f"retirement summary for {decision} is {values[decision]}, expected {expected_count}."
            )


def validate_on_demand_retirement_inventory(markdown: str) -> RetirementInventoryValidation:
    """Validate the ten inventory rows and their visible decision aggregates."""

    errors: list[str] = []
    items = _table_after_heading(markdown, RETIREMENT_ITEMS_HEADING)
    summary_table = _table_after_heading(markdown, RETIREMENT_SUMMARY_HEADING)
    summary = _validate_item_table(items, errors)
    _validate_summary_table(summary_table, summary, errors)
    return RetirementInventoryValidation(valid=not errors, errors=tuple(errors), summary=summary)
