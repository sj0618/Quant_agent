"""Release data-source manifest and cross-review validation contracts."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date
from hashlib import sha256
from typing import Any

RELEASE_MANIFEST_SCHEMA_VERSION = "release-data-source-manifest.v1"
LINEAGE_HASH_LENGTH = 64
REQUIRED_RELEASE_FIELDS = ("source", "as_of", "freshness", "lineage_hash")
FORBIDDEN_RELEASE_SOURCES = frozenset({"", "fixture", "mock", "proxy", "unknown"})
UNKNOWN_FRESHNESS = frozenset({"", "unknown", "missing"})


class ReleaseManifestValidationError(ValueError):
    """Raised when a release manifest cannot be used as release evidence."""


@dataclass(frozen=True)
class ReleaseDataSourceManifest:
    source: str
    as_of: date
    freshness: str
    lineage_hash: str
    fallback_count: int
    lineage_refs: tuple[str, ...] = ()
    source_version: str | None = None
    schema_version: str = RELEASE_MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["as_of"] = self.as_of.isoformat()
        payload["lineage_refs"] = list(self.lineage_refs)
        return payload


@dataclass(frozen=True)
class ReleaseManifestSampleAudit:
    sample_index: int
    missing_required_fields: tuple[str, ...]
    hash_matches: bool
    fallback_zero: bool
    validation_errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.missing_required_fields and self.hash_matches and self.fallback_zero and not self.validation_errors


@dataclass(frozen=True)
class ReleaseManifestAuditReport:
    sample_count: int
    required_field_missing_count: int
    hash_mismatch_count: int
    fallback_violation_count: int
    required_fields_present_rate: float
    hash_match_rate: float
    fallback_zero_rate: float
    valid: bool
    samples: tuple[ReleaseManifestSampleAudit, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["samples"] = [asdict(sample) | {"valid": sample.valid} for sample in self.samples]
        return payload


def _canonical_payload(manifest: ReleaseDataSourceManifest) -> dict[str, Any]:
    return {
        "as_of": manifest.as_of.isoformat(),
        "fallback_count": manifest.fallback_count,
        "freshness": manifest.freshness,
        "lineage_refs": list(manifest.lineage_refs),
        "schema_version": manifest.schema_version,
        "source": manifest.source,
        "source_version": manifest.source_version,
    }


def compute_lineage_hash(manifest: ReleaseDataSourceManifest | Mapping[str, Any]) -> str:
    normalized = manifest if isinstance(manifest, ReleaseDataSourceManifest) else _coerce_manifest(manifest)
    encoded = json.dumps(
        _canonical_payload(normalized), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_release_manifest(
    *,
    source: str,
    as_of: date | str,
    freshness: str,
    lineage_refs: Sequence[str] = (),
    source_version: str | None = None,
    fallback_count: int = 0,
) -> ReleaseDataSourceManifest:
    manifest = ReleaseDataSourceManifest(
        source=str(source).strip(),
        as_of=_parse_date(as_of),
        freshness=str(freshness).strip(),
        lineage_hash="0" * LINEAGE_HASH_LENGTH,
        fallback_count=fallback_count,
        lineage_refs=tuple(sorted({str(ref).strip() for ref in lineage_refs if str(ref).strip()})),
        source_version=source_version,
    )
    manifest = replace(manifest, lineage_hash=compute_lineage_hash(manifest))
    errors = validate_release_manifest(manifest)
    if errors:
        raise ReleaseManifestValidationError("; ".join(errors))
    return manifest


def validate_release_manifest(
    value: ReleaseDataSourceManifest | Mapping[str, Any] | None,
    *,
    require_release_source: bool = True,
) -> tuple[str, ...]:
    if value is None:
        return ("release manifest is missing",)
    try:
        manifest = value if isinstance(value, ReleaseDataSourceManifest) else _coerce_manifest(value)
    except (KeyError, TypeError, ValueError) as exc:
        return (f"release manifest schema error: {exc}",)

    errors: list[str] = []
    source = manifest.source.lower()
    if not manifest.source:
        errors.append("source is required")
    if require_release_source and source in FORBIDDEN_RELEASE_SOURCES:
        errors.append("fixture/mock/proxy/unknown source is forbidden in release manifest")
    if not manifest.freshness or manifest.freshness.lower() in UNKNOWN_FRESHNESS:
        errors.append("freshness is required and must be known")
    if manifest.fallback_count != 0:
        errors.append("release manifest fallback_count must be zero")
    if len(manifest.lineage_hash) != LINEAGE_HASH_LENGTH:
        errors.append("lineage_hash must be a SHA-256 hash")
    elif manifest.lineage_hash != compute_lineage_hash(manifest):
        errors.append("lineage_hash does not match canonical manifest fields")
    return tuple(errors)


def audit_release_manifest_samples(samples: Iterable[Mapping[str, Any]]) -> ReleaseManifestAuditReport:
    audited: list[ReleaseManifestSampleAudit] = []
    missing_count = 0
    hash_mismatch_count = 0
    fallback_violation_count = 0
    hash_checked_count = 0
    hash_match_count = 0
    fallback_zero_count = 0

    for sample_index, sample in enumerate(samples):
        missing = tuple(field for field in REQUIRED_RELEASE_FIELDS if sample.get(field) in (None, ""))
        missing_count += len(missing)
        errors = validate_release_manifest(sample)
        hash_matches = False
        fallback_zero = sample.get("fallback_count") == 0
        if not missing:
            try:
                manifest = _coerce_manifest(sample)
                hash_checked_count += 1
                hash_matches = manifest.lineage_hash == compute_lineage_hash(manifest)
                hash_match_count += int(hash_matches)
            except (TypeError, ValueError):
                pass
        if not fallback_zero:
            fallback_violation_count += 1
        else:
            fallback_zero_count += 1
        if not hash_matches and not missing:
            hash_mismatch_count += 1
        audited.append(
            ReleaseManifestSampleAudit(
                sample_index=sample_index,
                missing_required_fields=missing,
                hash_matches=hash_matches,
                fallback_zero=fallback_zero,
                validation_errors=errors,
            )
        )

    sample_count = len(audited)
    return ReleaseManifestAuditReport(
        sample_count=sample_count,
        required_field_missing_count=missing_count,
        hash_mismatch_count=hash_mismatch_count,
        fallback_violation_count=fallback_violation_count,
        required_fields_present_rate=(sample_count - sum(bool(item.missing_required_fields) for item in audited)) / sample_count if sample_count else 0.0,
        hash_match_rate=hash_match_count / hash_checked_count if hash_checked_count else 0.0,
        fallback_zero_rate=fallback_zero_count / sample_count if sample_count else 0.0,
        valid=bool(audited) and all(item.valid for item in audited),
        samples=tuple(audited),
    )


def _coerce_manifest(value: Mapping[str, Any]) -> ReleaseDataSourceManifest:
    return ReleaseDataSourceManifest(
        source=str(value["source"]).strip(),
        as_of=_parse_date(value["as_of"]),
        freshness=str(value["freshness"]).strip(),
        lineage_hash=str(value["lineage_hash"]),
        fallback_count=int(value.get("fallback_count", 0)),
        lineage_refs=tuple(sorted({str(ref).strip() for ref in value.get("lineage_refs", ()) if str(ref).strip()})),
        source_version=value.get("source_version"),
        schema_version=str(value.get("schema_version", RELEASE_MANIFEST_SCHEMA_VERSION)),
    )


def _parse_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
