"""Control-board parsing, validation, and evidence aggregation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
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

_MARKER_PATTERN = re.compile(r"<!--\s*control-board:v1\s*(\{.*?\})\s*-->", re.DOTALL)
_MARKER_TRANSITION_FIELDS = (
    "id",
    "taskId",
    "from",
    "to",
    "at",
    "gitSha",
    "owner",
    "reviewer",
    "limitation",
)
_MARKER_BLOCKER_FIELDS = (
    "id",
    "owner",
    "reason",
    "openedAt",
    "nextReviewAt",
    "lastReviewer",
    "releaseDisposition",
    "limitation",
)
_MARKER_TRANSITION_PROJECTION_HEADING = "상태 전이 기록"
_MARKER_BLOCKER_PROJECTION_HEADING = "차단·재발 기록"


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


def _marker_payload(markdown: str, errors: list[str]) -> Mapping[str, Any] | None:
    match = _MARKER_PATTERN.search(markdown)
    if match is None:
        errors.append("control-board:v1 marker is missing or malformed.")
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        errors.append("control-board:v1 marker contains invalid JSON.")
        return None
    if not isinstance(payload, Mapping):
        errors.append("control-board:v1 marker must contain an object.")
        return None
    return payload


def _marker_text(
    row: Mapping[str, Any], field: str, *, label: str, row_number: int, errors: list[str]
) -> None:
    if not isinstance(row.get(field), str) or not str(row[field]).strip():
        errors.append(f"{label} row {row_number} has an empty {field}.")


def _marker_evidence(
    row: Mapping[str, Any], *, label: str, row_number: int, errors: list[str]
) -> int:
    evidence = row.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, str) or not evidence:
        errors.append(f"{label} row {row_number} has no evidence_uri.")
        return 0
    valid_count = 0
    for value in evidence:
        if not isinstance(value, str) or not _is_evidence_uri(value):
            errors.append(f"{label} row {row_number} has an invalid evidence_uri.")
        else:
            valid_count += 1
    return valid_count


def _validate_marker_evidence_revision(
    row: Mapping[str, Any], *, snapshot_sha: str, label: str, row_number: int, errors: list[str]
) -> None:
    evidence = row.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, str):
        return
    for value in evidence:
        if not isinstance(value, str):
            continue
        _base, separator, revision = value.rpartition("@")
        if not separator or revision != snapshot_sha:
            errors.append(f"{label} row {row_number} evidence_uri must bind snapshot Git SHA.")


def _table_cell(row: Mapping[str, str], header: str) -> str:
    return row.get(header, "").strip().strip("`")


def _projection_evidence_matches(marker_row: Mapping[str, Any], displayed: str) -> bool:
    base, separator, revision = displayed.rpartition("@")
    evidence = marker_row.get("evidence")
    if not separator or not isinstance(evidence, Sequence) or isinstance(evidence, str):
        return False
    return any(
        isinstance(item, str)
        and item.startswith(f"{base}@")
        and item.rpartition("@")[2].startswith(revision)
        for item in evidence
    )


def _validate_marker_projection(
    markdown: str,
    *,
    transitions: Sequence[Any],
    blockers: Sequence[Any],
    snapshot_sha: str,
    errors: list[str],
) -> None:
    """Keep the reader-facing tables synchronized with the machine marker."""

    transition_table = _table_after_heading(markdown, _MARKER_TRANSITION_PROJECTION_HEADING)
    if transition_table is None:
        errors.append("state transition projection table is missing.")
    elif len(transition_table.rows) != len(transitions):
        errors.append("state transition projection row count does not match marker.")
    else:
        for row_number, (marker_row, table_row) in enumerate(
            zip(transitions, transition_table.rows, strict=True), start=1
        ):
            if not isinstance(marker_row, Mapping):
                continue
            if _table_cell(table_row, "Record ID") != str(marker_row.get("id") or ""):
                errors.append(f"state transition projection row {row_number} id does not match marker.")
            if _table_cell(table_row, "대상 ID") != str(marker_row.get("taskId") or ""):
                errors.append(f"state transition projection row {row_number} work item does not match marker.")
            if _table_cell(table_row, "Owner") != str(marker_row.get("owner") or ""):
                errors.append(f"state transition projection row {row_number} owner does not match marker.")
            if _table_cell(table_row, "Independent reviewer") != str(marker_row.get("reviewer") or ""):
                errors.append(f"state transition projection row {row_number} reviewer does not match marker.")
            if not snapshot_sha.startswith(_table_cell(table_row, "Git SHA")):
                errors.append(f"state transition projection row {row_number} Git SHA does not match marker.")
            if not _projection_evidence_matches(marker_row, _table_cell(table_row, "증적 URI")):
                errors.append(f"state transition projection row {row_number} evidence_uri does not match marker.")

    blocker_table = _table_after_heading(markdown, _MARKER_BLOCKER_PROJECTION_HEADING)
    if blocker_table is None:
        errors.append("blocker projection table is missing.")
    elif len(blocker_table.rows) != len(blockers):
        errors.append("blocker projection row count does not match marker.")
    else:
        for row_number, (marker_row, table_row) in enumerate(
            zip(blockers, blocker_table.rows, strict=True), start=1
        ):
            if not isinstance(marker_row, Mapping):
                continue
            if _table_cell(table_row, "Blocker ID") != str(marker_row.get("id") or ""):
                errors.append(f"blocker projection row {row_number} id does not match marker.")
            if _table_cell(table_row, "Owner") != str(marker_row.get("owner") or ""):
                errors.append(f"blocker projection row {row_number} owner does not match marker.")
            if _table_cell(table_row, "마지막 검토자") != str(
                marker_row.get("lastReviewer") or ""
            ):
                errors.append(f"blocker projection row {row_number} reviewer does not match marker.")
            if not snapshot_sha.startswith(_table_cell(table_row, "Git SHA")):
                errors.append(f"blocker projection row {row_number} Git SHA does not match marker.")
            if not _projection_evidence_matches(marker_row, _table_cell(table_row, "해제 증적 URI")):
                errors.append(f"blocker projection row {row_number} evidence_uri does not match marker.")


def _validate_marker_board(markdown: str) -> ControlBoardValidation:
    """Validate the current JSON marker without discarding its Markdown projection.

    The marker is the machine-readable source of truth.  The adjacent Korean tables are
    a human projection and intentionally use localized headers, so forcing them into
    the retired English-table parser would make a newer board appear invalid.
    """

    errors: list[str] = []
    payload = _marker_payload(markdown, errors)
    if payload is None:
        return ControlBoardValidation(
            valid=False,
            errors=tuple(errors),
            summary=ControlBoardSummary(0, 0, 0, 0, 0, 0, 0),
        )
    if payload.get("schemaVersion") != "quantagent-control-board.v1":
        errors.append("control-board:v1 schemaVersion is invalid.")
    snapshot = payload.get("snapshot")
    snapshot_sha = ""
    if not isinstance(snapshot, Mapping):
        errors.append("control-board:v1 snapshot is missing.")
    else:
        for field in ("gitSha", "limitation", "scope"):
            _marker_text(snapshot, field, label="snapshot", row_number=1, errors=errors)
        if not isinstance(snapshot.get("localOnly"), bool):
            errors.append("snapshot localOnly must be a boolean.")
        snapshot_sha = str(snapshot.get("gitSha") or "")

    raw_transitions = payload.get("transitions")
    transitions = raw_transitions if isinstance(raw_transitions, list) else []
    if not transitions:
        errors.append("state transition table must contain at least one row.")
    transition_evidence_count = 0
    for row_number, row in enumerate(transitions, start=1):
        if not isinstance(row, Mapping):
            errors.append(f"state transition row {row_number} must be an object.")
            continue
        for field in _MARKER_TRANSITION_FIELDS:
            _marker_text(row, field, label="state transition", row_number=row_number, errors=errors)
        transition_evidence_count += _marker_evidence(
            row, label="state transition", row_number=row_number, errors=errors
        )
        if snapshot_sha and row.get("gitSha") != snapshot_sha:
            errors.append(f"state transition row {row_number} Git SHA does not match snapshot.")
        _validate_marker_evidence_revision(
            row,
            snapshot_sha=snapshot_sha,
            label="state transition",
            row_number=row_number,
            errors=errors,
        )

    raw_blockers = payload.get("blockers")
    blockers = raw_blockers if isinstance(raw_blockers, list) else []
    if not blockers:
        errors.append("blocker table must contain at least one row.")
    blocker_evidence_count = 0
    recurrence_values: list[int] = []
    for row_number, row in enumerate(blockers, start=1):
        if not isinstance(row, Mapping):
            errors.append(f"blocker row {row_number} must be an object.")
            continue
        for field in _MARKER_BLOCKER_FIELDS:
            _marker_text(row, field, label="blocker", row_number=row_number, errors=errors)
        evidence_count = _marker_evidence(row, label="blocker", row_number=row_number, errors=errors)
        blocker_evidence_count += evidence_count
        if evidence_count < 2:
            errors.append(f"blocker row {row_number} requires discovery and current-state evidence_uri.")
        recurrence = row.get("recurrenceCount")
        if not isinstance(recurrence, int) or isinstance(recurrence, bool) or recurrence < 0:
            errors.append(f"recurrence_count must be non-negative at row {row_number}.")
        else:
            recurrence_values.append(recurrence)
        _validate_marker_evidence_revision(
            row,
            snapshot_sha=snapshot_sha,
            label="blocker",
            row_number=row_number,
            errors=errors,
        )

    summary = ControlBoardSummary(
        state_transition_count=len(transitions),
        state_transition_evidence_uri_count=transition_evidence_count,
        blocker_count=len(blockers),
        blocker_evidence_uri_count=blocker_evidence_count,
        blocker_recurrence_total=sum(recurrence_values),
        recurring_blocker_count=sum(value > 0 for value in recurrence_values),
        max_blocker_recurrence_count=max(recurrence_values, default=0),
    )
    _validate_marker_projection(
        markdown,
        transitions=transitions,
        blockers=blockers,
        snapshot_sha=snapshot_sha,
        errors=errors,
    )
    return ControlBoardValidation(valid=not errors, errors=tuple(errors), summary=summary)


def validate_control_board(markdown: str) -> ControlBoardValidation:
    """Validate required board columns and reproduce the visible aggregates."""

    if "control-board:v1" in markdown:
        return _validate_marker_board(markdown)

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
