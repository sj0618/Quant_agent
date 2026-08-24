"""Release-time data source manifest contract and lineage hash helpers."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import date
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

RELEASE_PROFILE_ENV = "AI_RELEASE_PROFILE"
RELEASE_PROFILES = frozenset({"release", "production"})
LINEAGE_HASH_LENGTH = 64
LINEAGE_HASH_PATTERN = r"^[0-9a-f]{64}$"
SOURCE_MANIFEST_SCHEMA_VERSION = "release-source-manifest.v1"
FORBIDDEN_RELEASE_SOURCES = frozenset({"fixture", "unknown", ""})


class ReleaseSourceManifest(BaseModel):
    """The minimum provenance required for a release data load."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    as_of: date
    freshness: str = Field(min_length=1)
    lineage_hash: str = Field(pattern=LINEAGE_HASH_PATTERN)
    lineage_refs: list[str] = Field(default_factory=list)
    source_version: str | None = None
    schema_version: str = SOURCE_MANIFEST_SCHEMA_VERSION


def _hash_payload(manifest: ReleaseSourceManifest) -> dict[str, Any]:
    return manifest.model_dump(mode="json", exclude={"lineage_hash"})


def compute_lineage_hash(manifest: ReleaseSourceManifest | Mapping[str, Any]) -> str:
    """Return the SHA-256 of every manifest field except its stored hash."""

    normalized = (
        manifest
        if isinstance(manifest, ReleaseSourceManifest)
        else ReleaseSourceManifest.model_validate(manifest)
    )
    canonical = json.dumps(
        _hash_payload(normalized),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def build_source_manifest(
    *,
    source: str,
    as_of: date | str,
    freshness: str,
    lineage_refs: Sequence[str] = (),
    source_version: str | None = None,
) -> ReleaseSourceManifest:
    """Build a manifest and calculate its hash from canonical fields."""

    manifest = ReleaseSourceManifest(
        source=source,
        as_of=as_of,
        freshness=freshness,
        lineage_hash="0" * LINEAGE_HASH_LENGTH,
        lineage_refs=sorted({str(ref) for ref in lineage_refs if str(ref).strip()}),
        source_version=source_version,
    )
    return manifest.model_copy(update={"lineage_hash": compute_lineage_hash(manifest)})


def validate_source_manifest(
    value: ReleaseSourceManifest | Mapping[str, Any] | None,
    *,
    release_profile: bool = False,
) -> tuple[str, ...]:
    """Validate required fields, the lineage hash, and release source policy."""

    if value is None:
        return ("source manifest is missing",)
    try:
        manifest = (
            value
            if isinstance(value, ReleaseSourceManifest)
            else ReleaseSourceManifest.model_validate(value)
        )
    except ValidationError as exc:
        return (f"source manifest schema error: {exc}",)

    errors: list[str] = []
    expected_hash = compute_lineage_hash(manifest)
    if manifest.lineage_hash != expected_hash:
        errors.append("source manifest lineage_hash does not match canonical fields")
    if release_profile:
        if manifest.source in FORBIDDEN_RELEASE_SOURCES:
            errors.append("fixture or unknown source is forbidden in release profile")
        if manifest.freshness in {"", "unknown"}:
            errors.append("release source manifest freshness must be known")
    return tuple(errors)


def validate_release_metadata(metadata: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Validate the manifest embedded in a pipeline metadata object."""

    if not isinstance(metadata, Mapping):
        return ("pipeline metadata is missing",)
    return validate_source_manifest(metadata.get("source_manifest"), release_profile=True)


def is_release_profile(environ: Mapping[str, str] | None = None) -> bool:
    values = environ if environ is not None else os.environ
    return values.get(RELEASE_PROFILE_ENV, "").strip().lower() in RELEASE_PROFILES
