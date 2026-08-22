"""Sample audit for release source manifests."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.source_manifest import (
    ReleaseSourceManifest,
    compute_lineage_hash,
    validate_source_manifest,
)

REQUIRED_SOURCE_MANIFEST_FIELDS: tuple[str, ...] = (
    "source",
    "as_of",
    "freshness",
    "lineage_hash",
)


class SourceManifestSampleResult(BaseModel):
    """Evidence for one audited manifest sample."""

    model_config = ConfigDict(extra="forbid")

    sample_index: int = Field(ge=0)
    missing_required_fields: tuple[str, ...] = ()
    validation_errors: tuple[str, ...] = ()
    expected_lineage_hash: str | None = None
    actual_lineage_hash: str | None = None
    hash_matches: bool = False
    valid: bool = False


class SourceManifestAuditReport(BaseModel):
    """Aggregate QA evidence for a release manifest sample."""

    model_config = ConfigDict(extra="forbid")

    required_fields: tuple[str, ...] = REQUIRED_SOURCE_MANIFEST_FIELDS
    sample_count: int = Field(ge=0)
    required_field_missing_count: int = Field(ge=0)
    samples_with_missing_required_fields: int = Field(ge=0)
    hash_checked_count: int = Field(ge=0)
    hash_match_count: int = Field(ge=0)
    hash_mismatch_count: int = Field(ge=0)
    required_fields_present_rate: float = Field(ge=0, le=1)
    hash_match_rate: float = Field(ge=0, le=1)
    valid: bool
    samples: tuple[SourceManifestSampleResult, ...]


def _missing_required_fields(sample: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        field
        for field in REQUIRED_SOURCE_MANIFEST_FIELDS
        if field not in sample or sample[field] is None or sample[field] == ""
    )


def audit_source_manifest_samples(
    samples: Iterable[Mapping[str, Any]],
    *,
    release_profile: bool = True,
) -> SourceManifestAuditReport:
    """Audit required fields and recomputed lineage hashes for sample manifests."""

    results: list[SourceManifestSampleResult] = []
    missing_field_count = 0
    samples_with_missing = 0
    hash_checked_count = 0
    hash_match_count = 0

    for index, sample in enumerate(samples):
        missing = _missing_required_fields(sample)
        missing_field_count += len(missing)
        if missing:
            samples_with_missing += 1

        errors = validate_source_manifest(sample, release_profile=release_profile)
        expected_hash: str | None = None
        actual_hash = sample.get("lineage_hash")
        hash_matches = False
        if not missing:
            try:
                manifest = ReleaseSourceManifest.model_validate(sample)
                expected_hash = compute_lineage_hash(manifest)
                hash_matches = actual_hash == expected_hash
                hash_checked_count += 1
                hash_match_count += int(hash_matches)
            except ValueError:
                # The schema validation error is already included in errors.
                pass

        results.append(
            SourceManifestSampleResult(
                sample_index=index,
                missing_required_fields=missing,
                validation_errors=errors,
                expected_lineage_hash=expected_hash,
                actual_lineage_hash=str(actual_hash) if actual_hash is not None else None,
                hash_matches=hash_matches,
                valid=not missing and not errors and hash_matches,
            )
        )

    sample_count = len(results)
    present_rate = (
        (sample_count - samples_with_missing) / sample_count if sample_count else 0.0
    )
    hash_rate = hash_match_count / hash_checked_count if hash_checked_count else 0.0
    return SourceManifestAuditReport(
        sample_count=sample_count,
        required_field_missing_count=missing_field_count,
        samples_with_missing_required_fields=samples_with_missing,
        hash_checked_count=hash_checked_count,
        hash_match_count=hash_match_count,
        hash_mismatch_count=hash_checked_count - hash_match_count,
        required_fields_present_rate=present_rate,
        hash_match_rate=hash_rate,
        valid=bool(results) and all(result.valid for result in results),
        samples=tuple(results),
    )


def load_source_manifest_samples(path: str | Path) -> list[Mapping[str, Any]]:
    """Load a JSON list or an object containing a ``samples`` JSON list."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    samples = payload.get("samples") if isinstance(payload, Mapping) else payload
    if not isinstance(samples, list) or not all(isinstance(sample, Mapping) for sample in samples):
        raise ValueError("manifest sample file must contain a JSON list of objects")
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit release source manifest samples")
    parser.add_argument("sample_file", type=Path)
    args = parser.parse_args()
    report = audit_source_manifest_samples(load_source_manifest_samples(args.sample_file))
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
