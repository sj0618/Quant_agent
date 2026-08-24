"""Release-time data source manifest and lineage integrity checks."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

RELEASE_PROFILE_ENV = "AI_RELEASE_PROFILE"
RELEASE_PROFILES = frozenset({"release", "production"})
LINEAGE_HASH_LENGTH = 64
LINEAGE_HASH_PATTERN = r"^[0-9a-f]{64}$"
SOURCE_MANIFEST_SCHEMA_VERSION = "release-source-manifest.v2"
RELEASE_SOURCE = "postgres"
RELEASE_FRESHNESS_VALUES = frozenset({"fresh", "eod_current"})


class ReleaseSourceManifest(BaseModel):
    """The non-secret provenance required before a release data load may proceed."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    as_of: date
    freshness: str = Field(min_length=1)
    # ``lineage_hash`` protects the manifest declaration.  These two values bind that
    # declaration to the concrete payload which the adapter returned.  A new valid
    # manifest hash for a different extract therefore cannot be attached to the
    # current pipeline data at release time.
    extract_hash: str = Field(pattern=LINEAGE_HASH_PATTERN)
    snapshot_id: str = Field(pattern=LINEAGE_HASH_PATTERN)
    lineage_hash: str = Field(pattern=LINEAGE_HASH_PATTERN)
    lineage_refs: list[str] = Field(default_factory=list)
    source_version: str | None = None
    schema_version: str = SOURCE_MANIFEST_SCHEMA_VERSION


def _hash_payload(manifest: ReleaseSourceManifest) -> dict[str, Any]:
    return manifest.model_dump(mode="json", exclude={"lineage_hash"})


def _canonicalize(value: Any) -> Any:
    """Return a deterministic, JSON-safe representation of an adapter payload."""

    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((_canonicalize(item) for item in value), key=_canonical_json)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    # Decimal and database driver scalars are intentionally converted without using
    # their repr(), which can contain driver-specific type decoration.
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def compute_extract_hash(extract_snapshot: Mapping[str, Any]) -> str:
    """Hash the non-secret, concrete data extract that drives a pipeline result."""

    return sha256(_canonical_json(_canonicalize(extract_snapshot)).encode("utf-8")).hexdigest()


def build_pipeline_extract_snapshot(
    *,
    price_rows: Sequence[Mapping[str, Any]],
    screening_candidates: Sequence[Mapping[str, Any]],
    l4_evidence: Sequence[Mapping[str, Any]],
    macro_snapshot: Mapping[str, Any] | None,
    data_availability: Mapping[str, Any],
    required_tickers: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the exact adapter payload covered by a source manifest.

    Metadata is deliberately excluded: it contains the manifest itself and is a
    declaration about the data, not the data used to calculate the response.
    """

    return {
        "price_rows": list(price_rows),
        "screening_candidates": list(screening_candidates),
        "l4_evidence": list(l4_evidence),
        "macro_snapshot": dict(macro_snapshot) if macro_snapshot is not None else None,
        "data_availability": dict(data_availability),
        # The release currentness check is only meaningful relative to the complete
        # backtest universe.  Binding the intended ticker set into the extract keeps a
        # manifest from silently treating one current ticker as proof for all of them.
        "required_tickers": sorted({str(ticker).zfill(6) for ticker in required_tickers}),
    }


def compute_snapshot_id(
    *,
    source: str,
    as_of: date | str,
    freshness: str,
    lineage_refs: Sequence[str],
    source_version: str | None,
    extract_hash: str,
) -> str:
    """Return immutable identity for one source declaration and concrete extract."""

    return sha256(
        _canonical_json(
            {
                "source": source,
                "as_of": str(as_of),
                "freshness": freshness,
                "lineage_refs": sorted({str(ref) for ref in lineage_refs if str(ref).strip()}),
                "source_version": source_version,
                "extract_hash": extract_hash,
            }
        ).encode("utf-8")
    ).hexdigest()


def compute_lineage_hash(manifest: ReleaseSourceManifest | Mapping[str, Any]) -> str:
    """Return the canonical SHA-256 of every manifest field except its stored hash."""

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
    extract_snapshot: Mapping[str, Any],
) -> ReleaseSourceManifest:
    """Build a stable manifest from adapter facts and the returned data extract."""

    normalized_refs = sorted({str(ref) for ref in lineage_refs if str(ref).strip()})
    extract_hash = compute_extract_hash(extract_snapshot)
    snapshot_id = compute_snapshot_id(
        source=source,
        as_of=as_of,
        freshness=freshness,
        lineage_refs=normalized_refs,
        source_version=source_version,
        extract_hash=extract_hash,
    )

    manifest = ReleaseSourceManifest(
        source=source,
        as_of=as_of,
        freshness=freshness,
        extract_hash=extract_hash,
        snapshot_id=snapshot_id,
        lineage_hash="0" * LINEAGE_HASH_LENGTH,
        lineage_refs=normalized_refs,
        source_version=source_version,
    )
    return manifest.model_copy(update={"lineage_hash": compute_lineage_hash(manifest)})


def validate_source_manifest(
    value: ReleaseSourceManifest | Mapping[str, Any] | None,
    *,
    release_profile: bool = False,
) -> tuple[str, ...]:
    """Validate schema, integrity and the stricter release-source policy."""

    if value is None:
        return ("source manifest is missing",)
    try:
        manifest = (
            value
            if isinstance(value, ReleaseSourceManifest)
            else ReleaseSourceManifest.model_validate(value)
        )
    except ValidationError:
        return ("source manifest schema error",)

    errors: list[str] = []
    if manifest.lineage_hash != compute_lineage_hash(manifest):
        errors.append("source manifest lineage_hash does not match canonical fields")
    expected_snapshot_id = compute_snapshot_id(
        source=manifest.source,
        as_of=manifest.as_of,
        freshness=manifest.freshness,
        lineage_refs=manifest.lineage_refs,
        source_version=manifest.source_version,
        extract_hash=manifest.extract_hash,
    )
    if manifest.snapshot_id != expected_snapshot_id:
        errors.append("source manifest snapshot_id does not match canonical fields")
    if release_profile:
        if manifest.source != RELEASE_SOURCE:
            errors.append("release source manifest requires postgres source")
        if manifest.freshness not in RELEASE_FRESHNESS_VALUES:
            errors.append("release source manifest freshness must be current")
        if not manifest.lineage_refs:
            errors.append("release source manifest lineage_refs are required")
        if not manifest.source_version:
            errors.append("release source manifest source_version is required")
    return tuple(errors)


def validate_release_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    extract_snapshot: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Validate manifest, adapter metadata, and the concrete loaded extract.

    The data snapshot is supplied by the graph after loading, rather than recovered
    from manifest metadata.  This makes a freshly computed manifest for stale or
    unrelated data fail unless it matches the actual payload being analysed.
    """

    if not isinstance(metadata, Mapping):
        return ("pipeline metadata is missing",)
    manifest_value = metadata.get("source_manifest")
    errors = list(validate_source_manifest(manifest_value, release_profile=True))
    if manifest_value is None:
        return tuple(errors)
    try:
        manifest = ReleaseSourceManifest.model_validate(manifest_value)
    except ValidationError:
        return tuple(errors)

    source = metadata.get("source")
    if source != manifest.source:
        errors.append("source manifest source does not match adapter metadata")
    as_of = metadata.get("source_snapshot_as_of")
    if str(as_of) != manifest.as_of.isoformat():
        errors.append("source manifest as_of does not match adapter metadata")
    freshness = metadata.get("source_snapshot_freshness")
    if freshness != manifest.freshness:
        errors.append("source manifest freshness does not match adapter metadata")
    source_version = metadata.get("source_snapshot_version")
    if source_version != manifest.source_version:
        errors.append("source manifest source_version does not match adapter metadata")
    if extract_snapshot is None:
        errors.append("release extract snapshot is missing")
        return tuple(errors)

    actual_extract_hash = compute_extract_hash(extract_snapshot)
    if actual_extract_hash != manifest.extract_hash:
        errors.append("source manifest extract_hash does not match loaded data")
    expected_snapshot_id = compute_snapshot_id(
        source=str(source),
        as_of=str(as_of),
        freshness=str(freshness),
        lineage_refs=manifest.lineage_refs,
        source_version=source_version if isinstance(source_version, str) else None,
        extract_hash=actual_extract_hash,
    )
    if expected_snapshot_id != manifest.snapshot_id:
        errors.append("source manifest snapshot_id does not match loaded data")
    errors.extend(_ticker_currentness_errors(extract_snapshot, expected_as_of=manifest.as_of))
    return tuple(errors)


def _ticker_currentness_errors(
    extract_snapshot: Mapping[str, Any], *, expected_as_of: date
) -> tuple[str, ...]:
    """Fail closed if any required ticker lacks a bar for the declared latest session."""

    raw_tickers = extract_snapshot.get("required_tickers")
    if not isinstance(raw_tickers, Sequence) or isinstance(raw_tickers, str):
        return ("release extract snapshot required_tickers is missing",)
    required_tickers = {str(ticker).zfill(6) for ticker in raw_tickers if str(ticker).strip()}
    if not required_tickers:
        return ("release extract snapshot required_tickers is missing",)

    raw_rows = extract_snapshot.get("price_rows")
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, str):
        return ("release extract snapshot price_rows is missing",)
    latest_by_ticker: dict[str, date] = {}
    for row in raw_rows:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").zfill(6)
        row_date = _extract_row_date(row)
        if ticker not in required_tickers or row_date is None:
            continue
        latest_by_ticker[ticker] = max(latest_by_ticker.get(ticker, row_date), row_date)

    stale_or_missing = sorted(
        ticker for ticker in required_tickers if latest_by_ticker.get(ticker) != expected_as_of
    )
    if stale_or_missing:
        return (
            "release extract snapshot does not cover every required ticker through manifest as_of",
        )
    return ()


def _extract_row_date(row: Mapping[str, Any]) -> date | None:
    raw = row.get("date") or row.get("time") or row.get("as_of_date")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if raw is None:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def is_release_profile(environ: Mapping[str, str] | None = None) -> bool:
    values = environ if environ is not None else os.environ
    return values.get(RELEASE_PROFILE_ENV, "").strip().lower() in RELEASE_PROFILES
