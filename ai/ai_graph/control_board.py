"""Control-board parsing, validation, and evidence aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

STATE_TRANSITION_HEADING = "상태 전이 증적"
BLOCKER_HEADING = "Blocker 원장"
SUMMARY_HEADING = "집계"

STATE_TRANSITION_REQUIRED_COLUMNS: tuple[str, ...] = (
    "transition_id",
    "work_item_id",
    "previous_status",
    "new_status",
    "revision",
    "occurred_at",
    "evidence_uri",
    "actor",
    "reason",
)

BLOCKER_REQUIRED_COLUMNS: tuple[str, ...] = (
    "blocker_id",
    "status",
    "discovered_at",
    "discovery_evidence_uri",
    "affected_work",
    "next_check_at",
    "owner",
    "recurrence_count",
    "last_reviewer",
    "resolution_evidence_uri",
)

SUMMARY_REQUIRED_METRICS: tuple[str, ...] = (
    "state_transition_count",
    "state_transition_evidence_uri_count",
    "blocker_count",
    "blocker_evidence_uri_count",
    "blocker_recurrence_total",
    "recurring_blocker_count",
    "max_blocker_recurrence_count",
)


@dataclass(frozen=True)
class ControlBoardSummary:
    """Counts that must be visible on the board and reproducible from its rows."""

    state_transition_count: int
    state_transition_evidence_uri_count: int
    blocker_count: int
    blocker_evidence_uri_count: int
    blocker_recurrence_total: int
    recurring_blocker_count: int
    max_blocker_recurrence_count: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class ControlBoardValidation:
    valid: bool
    errors: tuple[str, ...]
    summary: ControlBoardSummary

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


def _missing_columns(table: _MarkdownTable | None, required: tuple[str, ...]) -> list[str]:
    if table is None:
        return list(required)
    return [column for column in required if column not in table.headers]


def _is_evidence_uri(value: str) -> bool:
    parsed = urlparse(value.strip())
    return bool(parsed.scheme and (parsed.netloc or parsed.path))


def _parse_non_negative_int(value: str, field: str, row_number: int, errors: list[str]) -> int:
    try:
        parsed = int(value)
    except ValueError:
        errors.append(f"{field} must be an integer at row {row_number}.")
        return 0
    if parsed < 0:
        errors.append(f"{field} must be non-negative at row {row_number}.")
        return 0
    return parsed


def _validate_required_values(
    table: _MarkdownTable | None,
    required: tuple[str, ...],
    label: str,
    errors: list[str],
) -> None:
    if table is None:
        errors.append(f"{label} table is missing.")
        return
    missing_columns = _missing_columns(table, required)
    if missing_columns:
        errors.append(f"{label} table is missing columns: {', '.join(missing_columns)}.")
        return
    if not table.rows:
        errors.append(f"{label} table must contain at least one row.")
        return
    for row_number, row in enumerate(table.rows, start=1):
        for column in required:
            if not row.get(column, "").strip():
                errors.append(f"{label} row {row_number} has an empty {column}.")


def _summary_from_rows(
    transitions: _MarkdownTable | None,
    blockers: _MarkdownTable | None,
    errors: list[str],
) -> ControlBoardSummary:
    transition_rows = transitions.rows if transitions is not None else ()
    blocker_rows = blockers.rows if blockers is not None else ()

    transition_evidence_count = 0
    for row_number, row in enumerate(transition_rows, start=1):
        evidence_uri = row.get("evidence_uri", "").strip()
        if _is_evidence_uri(evidence_uri):
            transition_evidence_count += 1
        elif evidence_uri:
            errors.append(f"state transition row {row_number} has an invalid evidence_uri.")

    blocker_evidence_count = 0
    recurrence_values: list[int] = []
    for row_number, row in enumerate(blocker_rows, start=1):
        for column in ("discovery_evidence_uri", "resolution_evidence_uri"):
            evidence_uri = row.get(column, "").strip()
            if _is_evidence_uri(evidence_uri):
                blocker_evidence_count += 1
            elif evidence_uri:
                errors.append(f"blocker row {row_number} has an invalid {column}.")
        recurrence_values.append(
            _parse_non_negative_int(
                row.get("recurrence_count", ""),
                "recurrence_count",
                row_number,
                errors,
            )
        )

    return ControlBoardSummary(
        state_transition_count=len(transition_rows),
        state_transition_evidence_uri_count=transition_evidence_count,
        blocker_count=len(blocker_rows),
        blocker_evidence_uri_count=blocker_evidence_count,
        blocker_recurrence_total=sum(recurrence_values),
        recurring_blocker_count=sum(value > 0 for value in recurrence_values),
        max_blocker_recurrence_count=max(recurrence_values, default=0),
    )


def _validate_summary_table(
    table: _MarkdownTable | None,
    summary: ControlBoardSummary,
    errors: list[str],
) -> None:
    if table is None:
        errors.append("summary table is missing.")
        return
    if "metric" not in table.headers or "value" not in table.headers:
        errors.append("summary table must contain metric and value columns.")
        return

    values: dict[str, int] = {}
    for row_number, row in enumerate(table.rows, start=1):
        metric = row.get("metric", "").strip()
        if not metric:
            errors.append(f"summary row {row_number} has an empty metric.")
            continue
        values[metric] = _parse_non_negative_int(row.get("value", ""), metric, row_number, errors)

    missing_metrics = [metric for metric in SUMMARY_REQUIRED_METRICS if metric not in values]
    if missing_metrics:
        errors.append(f"summary table is missing metrics: {', '.join(missing_metrics)}.")
    expected = summary.as_dict()
    for metric, expected_value in expected.items():
        if metric in values and values[metric] != expected_value:
            errors.append(
                f"summary metric {metric} is {values[metric]}, expected {expected_value}."
            )


def validate_control_board(markdown: str) -> ControlBoardValidation:
    """Validate required board columns and reproduce the visible aggregates."""

    errors: list[str] = []
    transitions = _table_after_heading(markdown, STATE_TRANSITION_HEADING)
    blockers = _table_after_heading(markdown, BLOCKER_HEADING)
    summary_table = _table_after_heading(markdown, SUMMARY_HEADING)

    _validate_required_values(
        transitions,
        STATE_TRANSITION_REQUIRED_COLUMNS,
        "state transition",
        errors,
    )
    _validate_required_values(blockers, BLOCKER_REQUIRED_COLUMNS, "blocker", errors)
    summary = _summary_from_rows(transitions, blockers, errors)
    _validate_summary_table(summary_table, summary, errors)
    return ControlBoardValidation(valid=not errors, errors=tuple(errors), summary=summary)
