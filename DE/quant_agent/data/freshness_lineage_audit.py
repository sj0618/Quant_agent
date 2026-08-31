"""Deterministic freshness and lineage audit for release evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from typing import Any

AUDIT_SCHEMA_VERSION = "freshness-lineage-audit.v1"
REVIEWER_FIELDS = ("reviewer_id", "reviewed_at", "decision", "evidence")
REQUIRED_SOURCE = "postgres"
FORBIDDEN_SOURCES = frozenset({"", "fixture", "mock", "proxy", "unknown"})
FRESHNESS_PASS_STATUSES = frozenset({"fresh", "within_slo"})
FRESHNESS_KNOWN_STATUSES = FRESHNESS_PASS_STATUSES | {"stale"}
LINEAGE_HASH_LENGTH = 64


@dataclass(frozen=True)
class SampleAudit:
    sample_index: int
    source: str
    as_of: str
    freshness: str
    source_valid: bool
    as_of_valid: bool
    freshness_valid: bool
    lineage_hash_matches: bool
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = list(self.errors)
        payload["valid"] = self.valid
        return payload


@dataclass(frozen=True)
class AuditRun:
    sample_count: int
    valid_sample_count: int
    source_valid_count: int
    as_of_valid_count: int
    freshness_valid_count: int
    lineage_hash_match_count: int
    result_hash: str
    provenance_trace_hash: str
    samples: tuple[SampleAudit, ...]

    @property
    def valid(self) -> bool:
        return self.sample_count > 0 and self.valid_sample_count == self.sample_count

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["samples"] = [sample.to_dict() for sample in self.samples]
        payload["valid"] = self.valid
        return payload


@dataclass(frozen=True)
class FreshnessLineageAuditReport:
    schema_version: str
    first_run: AuditRun
    second_run: AuditRun
    result_hash_equal: bool
    provenance_trace_hash_equal: bool
    reviewer: dict[str, str]
    reviewer_valid: bool
    reviewer_errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return (
            self.first_run.valid
            and self.second_run.valid
            and self.result_hash_equal
            and self.provenance_trace_hash_equal
            and self.reviewer_valid
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": "pass" if self.passed else "fail",
            "qa_contract": {
                "source_as_of_freshness_hash_rerun": self.first_run.valid and self.second_run.valid,
                "result_hash_equal": self.result_hash_equal,
                "provenance_trace_hash_equal": self.provenance_trace_hash_equal,
                "reviewer_record_present": self.reviewer_valid,
            },
            "first_run": self.first_run.to_dict(),
            "second_run": self.second_run.to_dict(),
            "rerun": {
                "result_hash_equal": self.result_hash_equal,
                "provenance_trace_hash_equal": self.provenance_trace_hash_equal,
            },
            "reviewer": self.reviewer,
            "reviewer_errors": list(self.reviewer_errors),
        }


def compute_lineage_hash(sample: Mapping[str, Any]) -> str:
    """Hash the immutable source/as-of/freshness lineage declaration."""

    canonical = {
        "as_of": str(sample.get("as_of", "")),
        "freshness": str(sample.get("freshness", "")).strip().lower(),
        "lineage_refs": sorted(
            str(value).strip() for value in sample.get("lineage_refs", ()) if str(value).strip()
        ),
        "source": str(sample.get("source", "")).strip().lower(),
        "source_version": sample.get("source_version"),
    }
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def audit_freshness_lineage(
    samples: Sequence[Mapping[str, Any]],
    reviewer: Mapping[str, Any],
) -> FreshnessLineageAuditReport:
    """Audit one immutable manifest twice and compare result/provenance hashes."""

    immutable_samples = tuple(dict(sample) for sample in samples)
    first_run = _run_once(immutable_samples)
    second_run = _run_once(immutable_samples)
    reviewer_errors = _validate_reviewer(reviewer)
    normalized_reviewer = {
        field: str(reviewer.get(field, "")).strip() for field in REVIEWER_FIELDS
    }
    return FreshnessLineageAuditReport(
        schema_version=AUDIT_SCHEMA_VERSION,
        first_run=first_run,
        second_run=second_run,
        result_hash_equal=first_run.result_hash == second_run.result_hash,
        provenance_trace_hash_equal=first_run.provenance_trace_hash == second_run.provenance_trace_hash,
        reviewer=normalized_reviewer,
        reviewer_valid=not reviewer_errors,
        reviewer_errors=reviewer_errors,
    )


def _run_once(samples: Sequence[Mapping[str, Any]]) -> AuditRun:
    audited = tuple(_audit_sample(index, sample) for index, sample in enumerate(samples))
    result_hash = _stable_hash([sample.to_dict() for sample in audited])
    provenance_trace_hash = _stable_hash(
        [
            {
                "as_of": sample.as_of,
                "freshness": sample.freshness,
                "lineage_hash": str(original.get("lineage_hash", "")),
                "sample_index": sample.sample_index,
                "source": sample.source,
            }
            for sample, original in zip(audited, samples, strict=True)
        ]
    )
    return AuditRun(
        sample_count=len(audited),
        valid_sample_count=sum(sample.valid for sample in audited),
        source_valid_count=sum(sample.source_valid for sample in audited),
        as_of_valid_count=sum(sample.as_of_valid for sample in audited),
        freshness_valid_count=sum(sample.freshness_valid for sample in audited),
        lineage_hash_match_count=sum(sample.lineage_hash_matches for sample in audited),
        result_hash=result_hash,
        provenance_trace_hash=provenance_trace_hash,
        samples=audited,
    )


def _audit_sample(sample_index: int, sample: Mapping[str, Any]) -> SampleAudit:
    source = str(sample.get("source", "")).strip()
    as_of = str(sample.get("as_of", "")).strip()
    freshness = str(sample.get("freshness", "")).strip().lower()
    errors: list[str] = []
    source_valid = source.lower() == REQUIRED_SOURCE and source.lower() not in FORBIDDEN_SOURCES
    if not source_valid:
        errors.append("source must be postgres for a server release audit")
    try:
        date.fromisoformat(as_of)
        as_of_valid = True
    except ValueError:
        as_of_valid = False
        errors.append("as_of must be an ISO date")
    freshness_valid = freshness in FRESHNESS_PASS_STATUSES
    if freshness not in FRESHNESS_KNOWN_STATUSES:
        errors.append("freshness must be fresh, within_slo, or stale")
    elif not freshness_valid:
        errors.append("stale freshness cannot pass a release audit")
    declared_hash = str(sample.get("lineage_hash", "")).strip().lower()
    lineage_hash_matches = (
        len(declared_hash) == LINEAGE_HASH_LENGTH and declared_hash == compute_lineage_hash(sample)
    )
    if not lineage_hash_matches:
        errors.append("lineage_hash does not match the canonical source/as_of/freshness input")
    return SampleAudit(
        sample_index=sample_index,
        source=source,
        as_of=as_of,
        freshness=freshness,
        source_valid=source_valid,
        as_of_valid=as_of_valid,
        freshness_valid=freshness_valid,
        lineage_hash_matches=lineage_hash_matches,
        errors=tuple(errors),
    )


def _validate_reviewer(reviewer: Mapping[str, Any]) -> tuple[str, ...]:
    errors = [
        f"reviewer field is required: {field}"
        for field in REVIEWER_FIELDS
        if not str(reviewer.get(field, "")).strip()
    ]
    reviewed_at = str(reviewer.get("reviewed_at", "")).strip()
    if reviewed_at:
        try:
            date.fromisoformat(reviewed_at)
        except ValueError:
            errors.append("reviewed_at must be an ISO date")
    if str(reviewer.get("decision", "")).strip().lower() != "approved":
        errors.append("reviewer decision must be approved")
    return tuple(errors)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
